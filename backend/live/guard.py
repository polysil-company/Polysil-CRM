"""Which box the checks are talking to (FS-065 rules 15, 18, 19).

`/health` is read through the client's own base URL, never a second one: a guard
that asked a different address could pass while the checks hit another box, and a
wrong URL has to fail here instead (edge case 25).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from live.client import API, LiveClient
from live.redact import describe, redact


class GuardError(RuntimeError):
    """The box is not the one the run was told to check. Nothing further is sent."""


def read_health(client: LiveClient) -> dict[str, Any]:
    """The `/health` body, or a refusal naming why it could not be read."""
    response = client.get("/health", auth=False)
    if response.status_code != 200:
        raise GuardError(f"/health did not answer 200: {describe(response)}")
    try:
        body = response.json()
    except ValueError as exc:
        raise GuardError("/health did not answer JSON; is this URL the API?") from exc
    if not isinstance(body, dict):
        raise GuardError("/health answered JSON that is not an object")
    return body


def _check_runtime(body: Mapping[str, Any]) -> None:
    if body.get("pre_auth_containment") is not True:
        raise GuardError("/health reports pre_auth_containment off: the anon role is not set")
    if body.get("runtime_role") != "app_role":
        raise GuardError(redact(f"/health reports runtime_role {body.get('runtime_role')!r}, "
                                  "not app_role"))


def require_environment(client: LiveClient, expected: str) -> dict[str, Any]:
    """Refuse unless `/health` names `expected`, containment is on and the API runs
    as `app_role` (rule 15). Returns the body for the report."""
    body = read_health(client)
    found = body.get("environment")
    if found != expected:
        raise GuardError(redact(f"/health reports environment {found!r}, expected {expected!r}"))
    _check_runtime(body)
    return body


def require_journey_allowed(client: LiveClient, *, allow_local: bool = False) -> dict[str, Any]:
    """The check before the first write (rule 18).

    Only `staging` passes. `local` passes with `allow_local`, for a run against a
    developer's own stack. `production`, a missing key and a non-JSON body refuse.
    The box must also be the target the client was built for, so a staging run
    pointed at the wrong tunnel refuses rather than writing somewhere else.
    """
    body = read_health(client)
    found = body.get("environment")
    allowed = {"staging", "local"} if allow_local else {"staging"}
    if found not in allowed:
        raise GuardError(redact(f"journey refused: /health reports environment {found!r}; "
                                  "it writes on staging only"))
    if found != client.environment:
        raise GuardError(redact(f"journey refused: /health reports {found!r} but the run "
                                  f"targets {client.environment!r}"))
    _check_runtime(body)
    return body


def require_usable_account(client: LiveClient) -> dict[str, Any]:
    """`/auth/me` after the sign-in, or a refusal.

    A temporary password answers 403 on every other path. With a forbidden list
    in play that can read as a pass, so the run stops here instead (rule 11).
    """
    response = client.get(f"{API}/auth/me")
    if response.status_code != 200:
        raise GuardError(f"/auth/me failed after sign-in: {describe(response)}")
    try:
        me = response.json()["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise GuardError("/auth/me did not answer the envelope") from exc
    if me.get("must_change_password"):
        raise GuardError("the check account has a temporary password (must_change_password); "
                           "change it before running the live checks")
    return dict(me)


def require_test_mobile(environ: Mapping[str, str]) -> str:
    """`LIVE_TEST_MOBILE`, or a refusal. Staging sends real WhatsApp, so every
    record the journey makes carries this one number (rule 19)."""
    mobile = environ.get("LIVE_TEST_MOBILE", "").strip()
    digits = "".join(ch for ch in mobile if ch.isdigit())
    if len(digits) < 10:
        raise GuardError("journey refused: LIVE_TEST_MOBILE is not set to a mobile number")
    return mobile
