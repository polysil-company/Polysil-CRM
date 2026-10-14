"""The one HTTP client the live checks use (FS-065 rules 1, 10, 12, 16).

Read-only is enforced here, before a request leaves, rather than trusted to the
tests: a check that sends a POST by mistake on production has already written by
the time an assertion could notice. Two named exceptions exist, the sign-in and
the sign-out, once each, and every non-GET the client sends is recorded so the
report can list them.

No retries anywhere. A retried sign-in is how five failures lock the account for
fifteen minutes (rule 12), and a retried timeout doubles the time a dead box takes
to report.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from typing import Any

import httpx

from live.redact import describe, error_code

API = "/api/v1"
# Connect fails fast through a dead tunnel; reads allow an export to drain.
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
# The sign-out ignores the run's deadline: a run that spent its budget must still
# close its session, or a 30-day session is left on the box (code review F3).
LOGOUT_TIMEOUT = httpx.Timeout(10.0)


class ReadOnlyError(RuntimeError):
    """A write was attempted on a read-only client. Nothing was sent."""


class SignInError(RuntimeError):
    """The sign-in was refused. The run stops; it is never retried."""


class LiveTimeoutError(RuntimeError):
    """A request, or the run's budget, ran out of time."""


class LiveClient:
    """A thin wrapper over `httpx.Client`, bound to one base URL and one target.

    `base_url` is the box's root, where `/health` lives; API paths are passed in
    full (`/api/v1/...`). `deadline` is a `time.monotonic()` value: past it every
    request refuses, and no request may outlive it.
    """

    def __init__(self, base_url: str, environment: str, *, read_only: bool,
                 transport: httpx.BaseTransport | None = None,
                 timeout: httpx.Timeout = DEFAULT_TIMEOUT,
                 deadline: float | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.environment = environment
        self.read_only = read_only
        self.deadline = deadline
        self.writes: list[str] = []
        self.token: str | None = None
        self.signed_in = False
        self.signed_out = False
        self._timeout = timeout
        self._transport = transport
        # trust_env=False: no proxy or certificate setting from this shell's
        # environment comes between the guard and the box (code review F9)
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport,
                                  follow_redirects=False, trust_env=False)

    # ── the two named writes ────────────────────────────────────────────────

    def login(self, email: str, password: str) -> None:
        """`POST /auth/login`, once per client. Marked used before it is sent, so a
        refused sign-in cannot be followed by a second attempt."""
        if self.signed_in:
            raise ReadOnlyError("one sign-in per run: login() was already used")
        self.signed_in = True
        response = self._send("POST", f"{API}/auth/login",
                              json={"email": email, "password": password},
                              auth=False, allow_write=True)
        if response.status_code != 200:
            raise SignInError(describe(response))
        try:
            self.token = str(response.json()["data"]["access_token"])
        except (ValueError, KeyError, TypeError) as exc:
            raise SignInError(f"{describe(response)}: no access token in the reply") from exc

    def logout(self) -> httpx.Response:
        """`POST /auth/logout`, once per client. The server answers 204 either way."""
        if self.signed_out:
            raise ReadOnlyError("logout() was already used")
        self.signed_out = True
        try:
            return self._send("POST", f"{API}/auth/logout", auth=True, allow_write=True,
                              fixed_timeout=LOGOUT_TIMEOUT)
        finally:
            self.token = None

    def writer(self) -> LiveClient:
        """A client that may write, on the same sign-in and the same deadline.

        The journey uses it so a run still signs in once (rule 12). It cannot sign
        in or out itself; the session that owns the token does both.
        """
        child = LiveClient(self.base_url, self.environment, read_only=False,
                           transport=self._transport, timeout=self._timeout,
                           deadline=self.deadline)
        child.token = self.token
        child.signed_in = child.signed_out = True
        child.writes = self.writes
        return child

    # ── requests ────────────────────────────────────────────────────────────

    def get(self, path: str, *, params: Mapping[str, str] | None = None,
            auth: bool = True) -> httpx.Response:
        return self._send("GET", path, params=params, auth=auth)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._send("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._send("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._send("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._send("DELETE", path, **kwargs)

    def _send(self, method: str, path: str, *, auth: bool = True, allow_write: bool = False,
              headers: Mapping[str, str] | None = None,
              fixed_timeout: httpx.Timeout | None = None, **kwargs: Any) -> httpx.Response:
        method = method.upper()
        if method != "GET" and self.read_only and not allow_write:
            raise ReadOnlyError(f"{method} {path} refused: this client is read-only")
        timeout = fixed_timeout or self._remaining()
        sent = dict(headers or {})
        if auth and self.token:
            sent["Authorization"] = f"Bearer {self.token}"
        if method != "GET" and not allow_write:
            # Every mutation needs one (CLAUDE.md 4.1 rule 5); a fresh key per call
            # because nothing here retries.
            sent.setdefault("Idempotency-Key", uuid.uuid4().hex)
        if method != "GET":
            self.writes.append(f"{method} {httpx.URL(path).path}")
        try:
            return self._http.request(method, path, headers=sent, timeout=timeout, **kwargs)
        except httpx.TimeoutException as exc:
            raise LiveTimeoutError(f"{method} {httpx.URL(path).path} timed out "
                              f"({type(exc).__name__})") from exc

    def _remaining(self) -> httpx.Timeout:
        """The configured timeout, cut down to what is left of the run's budget."""
        if self.deadline is None:
            return self._timeout
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise LiveTimeoutError("the run's 10-minute budget is spent")

        def cap(value: float | None) -> float:
            return left if value is None else min(value, left)
        return httpx.Timeout(connect=cap(self._timeout.connect), read=cap(self._timeout.read),
                             write=cap(self._timeout.write), pool=cap(self._timeout.pool))

    def close(self) -> None:
        self._http.close()


# ── what a checked GET's answer means (rule 10) ─────────────────────────────

PASS, FAIL, EXPORT_TOO_LARGE = "pass", "fail", "export_too_large"


def judge(response: httpx.Response, environment: str,
          forbidden: tuple[str, ...]) -> tuple[str, str]:
    """`(outcome, detail)` for one checked path called with a token.

    200 passes. 403 passes only on an environment where the path is expected to be
    forbidden, and only with `insufficient_permission`: a temporary password answers
    403 `password_change_required` on every path, and must not look like a pass.
    `export_too_large` is its own outcome. Everything else fails.
    """
    status, code = response.status_code, error_code(response)
    detail = describe(response)
    if status == 200:
        return PASS, detail
    if status == 403 and environment in forbidden and code == "insufficient_permission":
        return PASS, f"{detail} (expected on {environment})"
    if status == 422 and code == "export_too_large":
        return EXPORT_TOO_LARGE, detail
    return FAIL, detail
