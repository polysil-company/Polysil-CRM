"""The live checks' client, guard and redaction, without a box (FS-065 rules 1, 10 to 19, 26, 27).

Every request goes to an `httpx.MockTransport`, so nothing here touches a network.
The point of each test is a request that did not leave, or text that was not
printed: those are the properties a live run cannot show you afterwards.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from live.client import (
    EXPORT_TOO_LARGE,
    FAIL,
    PASS,
    LiveClient,
    LiveTimeoutError,
    ReadOnlyError,
    SignInError,
    judge,
)
from live.conftest import resolve_query
from live.guard import (
    GuardError,
    require_environment,
    require_journey_allowed,
    require_test_mobile,
    require_usable_account,
)
from live.redact import describe, redact

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://box.test"
TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.c2lnbmF0dXJlLWJ5dGVz"
HEALTHY = {"status": "ok", "environment": "staging", "pre_auth_containment": True,
           "runtime_role": "app_role", "whatsapp": "11za"}

Handler = Callable[[httpx.Request], httpx.Response]


def make(handler: Handler, *, environment: str = "staging", read_only: bool = True,
         deadline: float | None = None) -> tuple[LiveClient, list[httpx.Request]]:
    sent: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return handler(request)

    client = LiveClient(BASE, environment, read_only=read_only,
                        transport=httpx.MockTransport(record), deadline=deadline)
    return client, sent


def answer(status: int = 200, body: Any = None) -> Handler:
    return lambda request: httpx.Response(status, json=body if body is not None else {"data": []})


def box(health: Any = None, *, status: int = 200, text: str | None = None) -> Handler:
    """A box whose sign-in works and whose /health says what the test needs."""
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            if text is not None:
                return httpx.Response(status, text=text)
            return httpx.Response(status, json=HEALTHY if health is None else health)
        if request.url.path == "/api/v1/auth/login":
            return httpx.Response(200, json={"data": {"access_token": TOKEN, "expires_in": 900}})
        if request.url.path == "/api/v1/auth/logout":
            return httpx.Response(204)
        return httpx.Response(200, json={"data": []})
    return handle


# ── rule 1: read-only means nothing else leaves ─────────────────────────────

@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_read_only_client_refuses_every_write_before_sending(method: str) -> None:
    client, sent = make(box())
    with pytest.raises(ReadOnlyError, match=method.upper()):
        getattr(client, method)("/api/v1/leads", json={"farmer_name": "x"})
    assert sent == []
    assert client.writes == []


def test_read_only_client_sends_gets_with_the_token_and_no_idempotency_key() -> None:
    client, sent = make(box())
    client.login("check@polysil.in", "pw")
    assert client.get("/api/v1/leads", params={"limit": "1"}).status_code == 200
    assert sent[-1].method == "GET"
    assert sent[-1].headers["Authorization"] == f"Bearer {TOKEN}"
    assert "Idempotency-Key" not in sent[-1].headers


def test_get_without_auth_sends_no_token() -> None:
    client, sent = make(box())
    client.login("check@polysil.in", "pw")
    client.get("/api/v1/leads", auth=False)
    assert "Authorization" not in sent[-1].headers


def test_login_is_allowed_once_and_refused_the_second_time() -> None:
    client, sent = make(box())
    client.login("check@polysil.in", "pw")
    assert client.token == TOKEN
    with pytest.raises(ReadOnlyError, match="one sign-in"):
        client.login("check@polysil.in", "pw")
    assert [r.url.path for r in sent] == ["/api/v1/auth/login"]
    assert client.writes == ["POST /api/v1/auth/login"]


def test_a_refused_login_is_not_retried_and_prints_no_password() -> None:
    client, sent = make(answer(401, {"error": {"code": "invalid_credentials", "message": "no"}}))
    with pytest.raises(SignInError) as refused:
        client.login("check@polysil.in", "s3cret-password")
    assert "invalid_credentials" in str(refused.value)
    assert "s3cret-password" not in str(refused.value)
    assert "check@polysil.in" not in str(refused.value)
    with pytest.raises(ReadOnlyError):
        client.login("check@polysil.in", "s3cret-password")
    assert len(sent) == 1


def test_a_locked_account_stops_without_a_retry() -> None:
    client, sent = make(answer(423, {"error": {"code": "account_locked", "message": "no"}}))
    with pytest.raises(SignInError, match="account_locked"):
        client.login("check@polysil.in", "pw")
    assert len(sent) == 1


def test_logout_is_allowed_once_with_the_bearer_token() -> None:
    client, sent = make(box())
    client.login("check@polysil.in", "pw")
    assert client.logout().status_code == 204
    assert sent[-1].method == "POST" and sent[-1].url.path == "/api/v1/auth/logout"
    assert sent[-1].headers["Authorization"] == f"Bearer {TOKEN}"
    assert client.token is None
    with pytest.raises(ReadOnlyError):
        client.logout()
    assert client.writes == ["POST /api/v1/auth/login", "POST /api/v1/auth/logout"]


def test_journey_client_can_post_and_every_post_carries_an_idempotency_key() -> None:
    client, sent = make(box(), read_only=False)
    client.post("/api/v1/leads", json={"farmer_name": "LIVE-abc Farmer"})
    client.post("/api/v1/leads", json={"farmer_name": "LIVE-abc Farmer"})
    keys = [r.headers.get("Idempotency-Key") for r in sent]
    assert all(keys) and keys[0] != keys[1]
    assert client.writes == ["POST /api/v1/leads", "POST /api/v1/leads"]


def test_writer_shares_the_sign_in_and_cannot_sign_in_again() -> None:
    client, sent = make(box())
    client.login("check@polysil.in", "pw")
    writer = client.writer()
    writer.post("/api/v1/leads", json={})
    assert sent[-1].headers["Authorization"] == f"Bearer {TOKEN}"
    assert client.writes == ["POST /api/v1/auth/login", "POST /api/v1/leads"]
    with pytest.raises(ReadOnlyError):
        writer.login("check@polysil.in", "pw")
    with pytest.raises(ReadOnlyError):
        client.post("/api/v1/leads", json={})


# ── rule 16: timeouts and the budget ────────────────────────────────────────

def test_a_timeout_is_a_failure_with_its_reason() -> None:
    def hang(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    client, _ = make(hang)
    with pytest.raises(LiveTimeoutError, match=r"GET /api/v1/leads timed out \(ReadTimeout\)"):
        client.get("/api/v1/leads")


def test_a_spent_budget_refuses_before_sending() -> None:
    client, sent = make(box(), deadline=time.monotonic() - 1)
    with pytest.raises(LiveTimeoutError, match="budget"):
        client.get("/api/v1/leads")
    assert sent == []


def test_every_request_carries_a_timeout_no_longer_than_the_budget() -> None:
    client, sent = make(box(), deadline=time.monotonic() + 3)
    client.get("/api/v1/leads")
    timeouts = sent[0].extensions["timeout"]
    assert all(value is not None and value <= 3 for value in timeouts.values())


# ── rules 15 and 18: the guard ──────────────────────────────────────────────

def test_journey_guard_passes_for_staging() -> None:
    client, sent = make(box())
    assert require_journey_allowed(client)["environment"] == "staging"
    assert [r.url.path for r in sent] == ["/health"]
    assert "Authorization" not in sent[0].headers


def test_journey_guard_refuses_production() -> None:
    client, _ = make(box({**HEALTHY, "environment": "production"}), environment="production")
    with pytest.raises(GuardError, match="production"):
        require_journey_allowed(client)


def test_journey_guard_refuses_local_without_the_flag_and_passes_with_it() -> None:
    client, _ = make(box({**HEALTHY, "environment": "local"}), environment="local")
    with pytest.raises(GuardError, match="local"):
        require_journey_allowed(client)
    assert require_journey_allowed(client, allow_local=True)["environment"] == "local"


def test_journey_guard_refuses_a_box_that_is_not_the_target() -> None:
    client, _ = make(box(), environment="local")
    with pytest.raises(GuardError, match="targets 'local'"):
        require_journey_allowed(client, allow_local=True)


def test_guard_refuses_a_missing_environment_key() -> None:
    body = {k: v for k, v in HEALTHY.items() if k != "environment"}
    client, _ = make(box(body))
    with pytest.raises(GuardError, match="None"):
        require_journey_allowed(client)
    with pytest.raises(GuardError, match="None"):
        require_environment(client, "staging")


def test_guard_refuses_an_html_body() -> None:
    client, _ = make(box(text="<!doctype html><title>Polysil</title>"))
    with pytest.raises(GuardError, match="JSON"):
        require_journey_allowed(client)
    with pytest.raises(GuardError, match="JSON"):
        require_environment(client, "staging")


def test_guard_refuses_a_502() -> None:
    client, _ = make(box(status=502, text="Bad Gateway"))
    with pytest.raises(GuardError, match="502"):
        require_environment(client, "staging")


def test_guard_refuses_the_wrong_environment() -> None:
    client, _ = make(box())
    with pytest.raises(GuardError, match="expected 'production'"):
        require_environment(client, "production")


@pytest.mark.parametrize("change", [{"pre_auth_containment": False},
                                    {"pre_auth_containment": None},
                                    {"runtime_role": "polysil"},
                                    {"runtime_role": None}])
def test_guard_refuses_containment_off_or_another_runtime_role(change: dict[str, Any]) -> None:
    client, _ = make(box({**HEALTHY, **change}))
    with pytest.raises(GuardError):
        require_environment(client, "staging")
    with pytest.raises(GuardError):
        require_journey_allowed(client)


def test_guard_passes_a_healthy_box() -> None:
    client, _ = make(box())
    assert require_environment(client, "staging") == HEALTHY


# ── rule 11: a temporary password stops the run ─────────────────────────────

def test_a_temporary_password_is_refused() -> None:
    me = {"data": {"id": "u", "must_change_password": True, "permissions": []}}
    client, _ = make(answer(200, me))
    with pytest.raises(GuardError, match="must_change_password"):
        require_usable_account(client)


def test_a_normal_account_is_returned() -> None:
    me = {"data": {"id": "u", "must_change_password": False,
                   "permissions": [{"module": "leads", "actions": ["view"]}]}}
    client, _ = make(answer(200, me))
    assert require_usable_account(client)["id"] == "u"


# ── rule 19: the journey needs the one controlled mobile ────────────────────

@pytest.mark.parametrize("environ", [{}, {"LIVE_TEST_MOBILE": ""}, {"LIVE_TEST_MOBILE": "123"}])
def test_journey_refuses_without_a_test_mobile(environ: dict[str, str]) -> None:
    with pytest.raises(GuardError, match="LIVE_TEST_MOBILE"):
        require_test_mobile(environ)


def test_journey_takes_the_test_mobile() -> None:
    assert require_test_mobile({"LIVE_TEST_MOBILE": "+91 98765 43210"}) == "+91 98765 43210"


# ── rule 27: nothing secret is printed ──────────────────────────────────────

def test_redact_removes_a_jwt() -> None:
    assert redact(f"Bearer {TOKEN} expired") == "Bearer [token] expired"


@pytest.mark.parametrize("text", ["call +919876543210 now", "call 919876543210 now",
                                  "the farmer on 9876543210 rang back"])
def test_redact_removes_phone_numbers(text: str) -> None:
    out = redact(text)
    assert "9876543210" not in out and "[phone]" in out


def test_redact_removes_an_email() -> None:
    assert redact("sent to ops.team+live@polysil.in today") == "sent to [email] today"


def test_redact_keeps_ids_amounts_and_numbers_of_other_lengths() -> None:
    text = "lead 3f2b0c1e-1234-4abc-9def-123456789012 total 123456789012.50 count 12345"
    assert redact(text) == text


def test_describe_a_sign_in_prints_no_token() -> None:
    request = httpx.Request("POST", f"{BASE}/api/v1/auth/login")
    response = httpx.Response(200, json={"data": {"access_token": TOKEN}}, request=request)
    line = describe(response)
    assert line == "POST /api/v1/auth/login -> 200"
    assert "eyJ" not in line


def test_describe_a_failure_prints_path_status_and_code_only() -> None:
    request = httpx.Request("GET", f"{BASE}/api/v1/leads?q=9876543210")
    body = {"error": {"code": "insufficient_permission",
                      "message": "farmer 9876543210 asha@polysil.in"}}
    line = describe(httpx.Response(403, json=body, request=request))
    assert line == "GET /api/v1/leads -> 403 insufficient_permission"


# ── rule 10: what a checked GET's answer means ──────────────────────────────

def _response(status: int, code: str | None = None) -> httpx.Response:
    body = {"error": {"code": code, "message": "m"}} if code else {"data": []}
    return httpx.Response(status, json=body,
                          request=httpx.Request("GET", f"{BASE}/api/v1/commission/rates"))


@pytest.mark.parametrize(("status", "code", "environment", "forbidden", "outcome"), [
    (200, None, "production", (), PASS),
    (403, "insufficient_permission", "production", ("production",), PASS),
    (403, "insufficient_permission", "staging", ("production",), FAIL),
    (403, "password_change_required", "production", ("production",), FAIL),
    (500, None, "staging", (), FAIL),
    (502, None, "staging", (), FAIL),
    (404, "not_found", "staging", (), FAIL),
    (422, "export_too_large", "production", (), EXPORT_TOO_LARGE),
    (422, "validation_failed", "production", (), FAIL),
])
def test_judge(status: int, code: str | None, environment: str, forbidden: tuple[str, ...],
               outcome: str) -> None:
    assert judge(_response(status, code), environment, forbidden)[0] == outcome


# ── the inventory's placeholders ────────────────────────────────────────────

def test_resolve_query_fills_placeholders_and_sends_the_rest_as_is() -> None:
    values = {"@district_id": "d-1", "@today": "2026-10-14"}
    query = {"territory_id": "@district_id", "to": "@today", "limit": "1"}
    assert resolve_query(query, values) == {"territory_id": "d-1", "to": "2026-10-14",
                                            "limit": "1"}


def test_resolve_query_refuses_an_unknown_placeholder() -> None:
    with pytest.raises(KeyError, match="@state_id"):
        resolve_query({"state": "@state_id"}, {})


# ── the journey's PDF figures ───────────────────────────────────────────────

@pytest.mark.parametrize(("amount", "printed"), [
    ("1856.5", "1,856.50"), ("999", "999.00"), ("1234567.89", "12,34,567.89"),
    ("100000.00", "1,00,000.00"), ("0.10", "0.10"),
])
def test_inr_groups_like_the_pdf(amount: str, printed: str) -> None:
    from live.test_journey import inr
    assert inr(amount) == printed


@pytest.mark.parametrize(("pack", "qty"), [(None, "1"), ("100.000", "100"), ("0.500", "0.5")])
def test_quantity_has_no_trailing_decimals(pack: str | None, qty: str) -> None:
    from live.test_journey import quantity
    assert quantity(pack) == qty


# ── rule 26: the live suite refuses without a target, and collects with one ─

def _collect(extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("LIVE_")}
    env.update(extra)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "live", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120, check=False)


def test_live_suite_refuses_without_its_two_variables() -> None:
    done = _collect({})
    assert done.returncode == 4, done.stdout + done.stderr
    assert "LIVE_BASE_URL and LIVE_TARGET not set" in done.stdout + done.stderr


def test_live_suite_refuses_an_unknown_target() -> None:
    done = _collect({"LIVE_BASE_URL": "http://127.0.0.1:9", "LIVE_TARGET": "development"})
    assert done.returncode == 4
    assert "'development'" in done.stdout + done.stderr


@pytest.mark.skipif(not (ROOT / "live" / "inventory.json").exists(),
                    reason="live/inventory.json is not written yet")
def test_live_suite_collects_with_a_target_and_runs_read_only_first() -> None:
    done = _collect({"LIVE_BASE_URL": "http://127.0.0.1:9", "LIVE_TARGET": "staging"})
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    lines = [ln for ln in done.stdout.splitlines() if "::" in ln]
    inventory = json.loads((ROOT / "live" / "inventory.json").read_text(encoding="utf-8"))
    assert sum("test_readonly.py::test_get[" in ln for ln in lines) == len(inventory)
    journey = [i for i, ln in enumerate(lines) if ln.startswith("live/test_journey.py")]
    readonly = [i for i, ln in enumerate(lines) if ln.startswith("live/test_readonly.py")]
    assert journey and readonly and max(readonly) < min(journey)


# ── code review F3, F8, F9: the sign-out, the journey on production, the proxy ─

def test_a_spent_budget_still_signs_out() -> None:
    client, sent = make(box(), deadline=time.monotonic() + 60)
    client.login("check@polysil.in", "pw")
    client.deadline = time.monotonic() - 1
    with pytest.raises(LiveTimeoutError):
        client.get("/api/v1/leads")
    assert client.logout().status_code == 204
    assert sent[-1].url.path == "/api/v1/auth/logout"


def test_no_proxy_or_certificate_setting_comes_from_the_environment(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    client = LiveClient(BASE, "staging", read_only=True)
    assert client._http._trust_env is False
    assert not client._http._mounts


def test_describe_redacts_a_number_and_an_email_in_the_path() -> None:
    request = httpx.Request("GET", f"{BASE}/api/v1/partners/9876543210/asha@polysil.in")
    line = describe(httpx.Response(404, json={"error": {"code": "not_found"}}, request=request))
    assert "9876543210" not in line and "asha@polysil.in" not in line
    assert line.endswith("-> 404 not_found")


def test_the_journey_never_runs_on_production() -> None:
    # nothing listens on port 9: a journey that tried to run would error, not skip
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LIVE_", "PYTEST_"))}
    env.update(LIVE_BASE_URL="http://127.0.0.1:9", LIVE_TARGET="production",
               LIVE_CHECK_EMAIL="x@example.test", LIVE_CHECK_PASSWORD="pw",
               LIVE_TEST_MOBILE="919800000000", DEMO_PASSWORD="pw")
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "live/test_journey.py", "-q", "-rs",
         "--assert=plain", "-p", "no:cacheprovider"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120, check=False)
    out = done.stdout + done.stderr
    # 5: nothing was collected to run; the module skipped itself before any test
    assert done.returncode == 5, out[-2000:]
    assert "skipped" in out and " passed" not in out and "error" not in out.lower(), out[-2000:]
