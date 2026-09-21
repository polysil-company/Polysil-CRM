"""What a browser on another origin needs, and the two ways it silently fails.

Three settings have to agree before a frontend on `localhost:3000` can talk to an
API on `polysil-api.pranayx.tech` and *stay* signed in. Each of them fails in a
way that produces no error anywhere:

* **no CORS** and the browser refuses the call, with the only evidence in the
  developer's console;
* **`SameSite=Lax`** and sign-in succeeds, then the session dies at the first
  refresh, because a Lax cookie is not attached to a cross-site background
  request;
* **an untrusted proxy peer** and every caller shares one rate-limit bucket, with
  the endpoint still answering 202 once it trips (ISS-084).

The third is the one that would reach production unnoticed, so it is tested
hardest.
"""

from __future__ import annotations

import pytest
from fastapi import Request

from api.config import Settings, get_settings
from api.routers.auth import _client_ip, _is_trusted_peer, _trusted_networks

V1 = "/api/v1"
LOCAL_DB = "postgresql+asyncpg://u:p@127.0.0.1:6432/appdb"


def settings(**over: object) -> Settings:
    base: dict[str, object] = {"database_url": LOCAL_DB, "jwt_secret": "x" * 32}
    return Settings(**(base | over))   # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    get_settings.cache_clear()
    _trusted_networks.cache_clear()
    yield
    get_settings.cache_clear()
    _trusted_networks.cache_clear()


# ── the trusted peer, which decides whose rate-limit bucket a caller gets ────

def test_loopback_is_trusted_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.routers.auth.get_settings", settings)
    assert _is_trusted_peer("127.0.0.1")
    assert _is_trusted_peer("::1")


def test_a_container_address_is_not_trusted_by_default(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The default is right for a proxy on the host and wrong for one in a
    container, which is why the setting exists rather than the old constant."""
    monkeypatch.setattr("api.routers.auth.get_settings", settings)
    assert not _is_trusted_peer("172.18.0.5")


def test_a_named_container_network_is_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "api.routers.auth.get_settings",
        lambda: settings(trusted_proxy_peers=("127.0.0.1", "172.18.0.0/16")))
    assert _is_trusted_peer("172.18.0.5")
    assert not _is_trusted_peer("172.19.0.5"), "a neighbouring network is not the same network"


def test_a_public_address_is_never_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "api.routers.auth.get_settings",
        lambda: settings(trusted_proxy_peers=("172.18.0.0/16",)))
    assert not _is_trusted_peer("8.8.8.8")
    assert not _is_trusted_peer("not-an-address")


def _request(peer: str | None, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    scope = {"type": "http", "headers": headers,
             "client": (peer, 40000) if peer else None}
    return Request(scope)   # type: ignore[arg-type]


def test_a_trusted_proxy_hands_over_the_real_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "api.routers.auth.get_settings",
        lambda: settings(trusted_proxy_peers=("172.18.0.0/16",)))
    assert _client_ip(_request("172.18.0.5", "203.0.113.9")) == "203.0.113.9"


def test_an_untrusted_peer_keeps_its_own_address_and_the_header_is_ignored(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Otherwise anyone could choose their rate-limit bucket by sending a header."""
    monkeypatch.setattr("api.routers.auth.get_settings", settings)
    assert _client_ip(_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


def test_the_rightmost_entry_is_the_one_the_proxy_appended(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Everything left of it is whatever the client chose to send."""
    monkeypatch.setattr(
        "api.routers.auth.get_settings",
        lambda: settings(trusted_proxy_peers=("172.18.0.0/16",)))
    assert _client_ip(_request("172.18.0.5", "1.2.3.4, 203.0.113.9")) == "203.0.113.9"


def test_trusting_no_hops_ignores_the_header_entirely(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "api.routers.auth.get_settings",
        lambda: settings(trusted_proxy_peers=("172.18.0.0/16",), trusted_proxy_hops=0))
    assert _client_ip(_request("172.18.0.5", "203.0.113.9")) == "172.18.0.5"


def test_an_unparseable_peer_list_is_refused_at_startup() -> None:
    """A typo here fails silently otherwise: the header is simply never believed,
    and the symptom is one rate-limit bucket for everybody."""
    with pytest.raises(ValueError, match="not an address or CIDR"):
        settings(trusted_proxy_peers=("172.18.0.0/16", "caddy"))


@pytest.mark.parametrize(("raw", "expected"), [
    ("127.0.0.1,::1,172.18.0.0/16", ("127.0.0.1", "::1", "172.18.0.0/16")),
    ('["127.0.0.1","172.18.0.0/16"]', ("127.0.0.1", "172.18.0.0/16")),
    ("127.0.0.1", ("127.0.0.1",)),
    (" 127.0.0.1 , ::1 ", ("127.0.0.1", "::1")),
    ("", ()),
])
def test_a_list_setting_reads_as_commas_or_as_json(
        monkeypatch: pytest.MonkeyPatch, raw: str, expected: tuple[str, ...]) -> None:
    """Commas are what a person editing an env file writes; JSON is what pydantic
    wants. Accepting only the second failed at startup with a parse error naming
    neither format, on a box where the fix is a file nobody can see from here."""
    monkeypatch.setenv("DATABASE_URL", LOCAL_DB)
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("TRUSTED_PROXY_PEERS", raw)
    assert Settings().trusted_proxy_peers == expected   # type: ignore[call-arg]


# ── the cookie, which decides whether the session survives a refresh ─────────

def test_cross_site_over_plain_http_is_refused_at_startup() -> None:
    """`SameSite=None` needs `Secure`, `Secure` needs HTTPS. Allowed silently, the
    browser drops the cookie and the session dies with nothing in any log."""
    with pytest.raises(ValueError, match="needs Secure"):
        settings(refresh_cookie_samesite="none", environment="local")


def test_cross_site_is_allowed_where_there_is_tls() -> None:
    assert settings(refresh_cookie_samesite="none",
                    environment="staging").refresh_cookie_samesite == "none"


def test_the_default_is_the_same_origin_answer() -> None:
    assert settings().refresh_cookie_samesite == "lax"


# ── CORS, which decides whether the call happens at all ─────────────────────

def test_any_localhost_port_is_allowed_so_nobody_has_to_be_asked(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """A dev server moves between 3000, 5173 and whatever is free. Pinning one
    means asking the frontend developer every time it changes."""
    import re

    pattern = re.compile(r"http://(localhost|127\.0\.0\.1)(:\d+)?")
    for origin in ("http://localhost:3000", "http://localhost:5173",
                   "http://127.0.0.1:4200", "http://localhost"):
        assert pattern.fullmatch(origin), origin


def test_a_public_origin_is_not_matched_by_the_localhost_pattern() -> None:
    import re

    pattern = re.compile(r"http://(localhost|127\.0\.0\.1)(:\d+)?")
    for origin in ("http://evil.com", "http://localhost.evil.com",
                   "https://localhost:3000"):
        assert not pattern.fullmatch(origin), origin


def test_cors_is_present_by_default_for_the_developers_own_machine() -> None:
    from starlette.middleware.cors import CORSMiddleware

    from api.main import create_app

    get_settings.cache_clear()
    assert CORSMiddleware in [m.cls for m in create_app().user_middleware]


def test_cors_is_absent_when_nothing_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A same-origin or dev-server-proxied frontend needs none, and a build that
    allows nobody should not carry the surface at all."""
    from starlette.middleware.cors import CORSMiddleware

    import api.main

    monkeypatch.setattr(
        api.main, "get_settings",
        lambda: settings(cors_allow_localhost=False, cors_allow_origins=()))
    assert CORSMiddleware not in [m.cls for m in api.main.create_app().user_middleware]


def test_a_named_origin_turns_it_on_without_localhost(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """What a deployed frontend preview needs: its own origin and nothing else."""
    from starlette.middleware.cors import CORSMiddleware

    import api.main

    monkeypatch.setattr(
        api.main, "get_settings",
        lambda: settings(cors_allow_localhost=False,
                         cors_allow_origins=("https://polysil.vercel.app",)))
    middleware = [m for m in api.main.create_app().user_middleware
                  if m.cls is CORSMiddleware]
    assert len(middleware) == 1
    assert middleware[0].kwargs["allow_origins"] == ["https://polysil.vercel.app"]
    assert middleware[0].kwargs["allow_origin_regex"] is None
    assert middleware[0].kwargs["allow_credentials"] is True, "cookies need this"


def test_only_one_layer_rewrites_the_client_address() -> None:
    """Uvicorn's proxy-header middleware is on by default and trusts
    X-Forwarded-For from a loopback peer, so it rewrites `request.client` before
    `_is_trusted_peer` can look at the real TCP peer. On a loopback connection our
    own allowlist then reads an address the caller chose, and an empty
    TRUSTED_PROXY_PEERS stops protecting anything (cross-vendor review, September).

    There is no way to assert this from inside the app: the flag lives in the
    container command. So the command is the assertion. If a future change drops
    it, this is what says why it was there.
    """
    import pathlib

    dockerfile = (pathlib.Path(__file__).resolve().parents[2] / "infra" / "Dockerfile")
    command = [line for line in dockerfile.read_text(encoding="utf-8").splitlines()
               if line.startswith("CMD [") and "uvicorn" in line]
    assert len(command) == 1, command
    assert "--no-proxy-headers" in command[0]
    assert "--forwarded-allow-ips" not in command[0], (
        "that flag only matters when uvicorn is doing the rewriting, and it is not")


class TestCookieCredentialOrigin:
    """A cookie-authenticated endpoint refuses a browser request from an origin
    that may not spend the cookie.

    CORS does not cover this. CORS decides whether a page may *read* a response;
    a simple POST is sent regardless, and by the time the browser discards the
    answer the sign-out has happened. With `refresh_cookie_samesite = "none"` -
    which a frontend on another origin needs - any site could force a sign-out or
    rotate a session by submitting a form (cross-vendor review, September).
    """

    @staticmethod
    def _request(origin: str | None, host: str = "api.polysil.in"):
        from starlette.datastructures import Headers
        from starlette.requests import Request

        raw = [(b"host", host.encode())]
        if origin is not None:
            raw.append((b"origin", origin.encode()))
        return Request({"type": "http", "method": "POST", "path": "/api/v1/auth/logout",
                        "headers": Headers(raw=raw).raw, "query_string": b""})

    def _cross_site(self, monkeypatch: pytest.MonkeyPatch, origin: str | None,
                    **overrides: object) -> bool:
        import api.routers.auth as auth

        monkeypatch.setattr(auth, "get_settings", lambda: settings(**overrides))
        return auth._cross_site(self._request(origin))

    def test_no_origin_is_not_a_browser_and_is_allowed(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """curl, a mobile app, a server. A browser cannot omit Origin on a POST,
        so nothing is given away by allowing it."""
        assert self._cross_site(monkeypatch, None) is False

    def test_the_api_s_own_origin_is_allowed_on_either_scheme(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The interactive docs call these endpoints from the API's own origin,
        and with --no-proxy-headers the request's own scheme is the internal one,
        so the comparison is on the authority."""
        assert self._cross_site(monkeypatch, "https://api.polysil.in") is False
        assert self._cross_site(monkeypatch, "http://api.polysil.in") is False

    def test_a_named_origin_is_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._cross_site(monkeypatch, "https://polysil.vercel.app",
                                cors_allow_origins=("https://polysil.vercel.app",)) is False

    def test_localhost_is_allowed_on_any_port_while_that_is_on(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._cross_site(monkeypatch, "http://localhost:5173") is False
        assert self._cross_site(monkeypatch, "http://127.0.0.1:3000") is False

    def test_localhost_is_refused_once_that_is_off(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._cross_site(monkeypatch, "http://localhost:5173",
                                cors_allow_localhost=False) is True

    @pytest.mark.parametrize("origin", [
        "https://evil.example",
        "http://api.polysil.in.evil.example",
        "https://polysil.vercel.app.evil.example",
        "null",
    ])
    def test_another_origin_is_refused(self, monkeypatch: pytest.MonkeyPatch,
                                       origin: str) -> None:
        """Including the two shapes that read like ours and are not, and the
        `null` a sandboxed iframe sends."""
        assert self._cross_site(monkeypatch, origin,
                                cors_allow_origins=("https://polysil.vercel.app",)) is True


def test_health_reports_the_live_settings_not_the_ones_the_app_started_with() -> None:
    """The coupling this module caused, asserted so it cannot come back.

    `create_app` closes over a `Settings` instance. The settings are an
    lru_cache, and the fixture above clears it after every test here, so the app
    was left holding an object nothing else could reach: `/health` went on
    reporting a configuration that was no longer the live one, and a test in
    another module that changed the environment found the endpoint ignoring it.

    An endpoint whose whole job is reporting the current configuration has to
    read it at request time.
    """
    import inspect

    import api.main

    source = inspect.getsource(api.main.create_app)
    health = source.split('@app.get("/health"', 1)[1].split("return JSONResponse(body)", 1)[0]
    assert "get_settings()" in health, "health must resolve its settings per request"
    assert "settings.environment" not in health, "not from the factory's own instance"
