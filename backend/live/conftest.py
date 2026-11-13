"""The live checks' own fixtures (FS-065 rules 11, 12, 16, 17, 26).

This directory is outside `testpaths`. It runs only when `deploy_staging.py verify`
points it at a box with `LIVE_BASE_URL` and `LIVE_TARGET`, and without both it
refuses outright rather than skipping: a missing box must never read as a green run.

Nothing here imports from `tests/`. That conftest builds database users and talks
to a local PgBouncer, and neither exists on the machine running these checks.

One sign-in serves the whole run, and the logout runs even when the run is stopped
early, because a stopped run still leaves a 30-day session behind otherwise.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import time
from collections.abc import Iterator, Mapping
from typing import Any

import httpx
import pytest

from live.client import API, LiveClient, LiveTimeoutError, SignInError
from live.guard import GuardError, require_environment, require_usable_account
from live.redact import describe

REQUIRED = ("LIVE_BASE_URL", "LIVE_TARGET")
ENVIRONMENTS = ("local", "staging", "production")
# Under the 15-minute access token, so no check ever needs a refresh (rule 16), and
# under scripts/live_verify.py's 660 s limit, so the teardown that signs out runs
# before that limit kills the process (code review F3).
BUDGET_SECONDS = 540
INDIA = dt.timezone(dt.timedelta(hours=5, minutes=30))

# What the report says production does not prove (rule 17).
PRODUCTION_LIMITS = (
    "Modules not released on production answer 403; their queries never run there.",
    "The portal paths are not called on production.",
    "Scoping between users is not checked on production; the journey's negative "
    "cases run on staging only.",
)

_RUN: dict[str, Any] = {}


def pytest_configure(config: pytest.Config) -> None:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        pytest.exit(f"live checks refused: {' and '.join(missing)} not set. "
                    "Run them through `deploy_staging.py verify`, which sets both.",
                    returncode=4)
    target = os.environ["LIVE_TARGET"]
    if target not in ENVIRONMENTS:
        pytest.exit(f"live checks refused: LIVE_TARGET is {target!r}, "
                    f"not one of {', '.join(ENVIRONMENTS)}", returncode=4)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Read-only first, then the journey: a staging run proves the box answers
    before it writes anything to it."""
    items.sort(key=lambda item: item.path.name == "test_journey.py")


def india_today() -> dt.date:
    return dt.datetime.now(INDIA).date()


def resolve_query(query: Mapping[str, str], values: Mapping[str, str]) -> dict[str, str]:
    """The inventory's query with every `@name` replaced. An unknown placeholder
    raises: sending the literal would turn a missing lookup into a 422 nobody reads."""
    out: dict[str, str] = {}
    for key, value in query.items():
        if value.startswith("@"):
            if value not in values:
                raise KeyError(f"no value for {value} (query parameter {key})")
            out[key] = values[value]
        else:
            out[key] = value
    return out


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def target() -> str:
    return os.environ["LIVE_TARGET"]


@pytest.fixture(scope="session")
def client(target: str) -> Iterator[LiveClient]:
    """The read-only client, with the run's 10-minute budget as its deadline."""
    live = LiveClient(os.environ["LIVE_BASE_URL"], target, read_only=True,
                      deadline=time.monotonic() + BUDGET_SECONDS)
    _RUN["client"] = live
    try:
        yield live
    finally:
        live.close()


@pytest.fixture(scope="session")
def health(client: LiveClient, target: str) -> dict[str, Any]:
    """`/health` through the same base URL the checks use. A wrong box stops the run."""
    try:
        return require_environment(client, target)
    except (GuardError, LiveTimeoutError) as exc:
        pytest.exit(f"guard: {exc}", returncode=1)
    except httpx.TransportError as exc:
        # one stop with its reason, not a traceback per test (code review F11)
        pytest.exit(f"guard: {client.base_url}/health did not answer "
                    f"({type(exc).__name__})", returncode=1)


@pytest.fixture(scope="session")
def signed_in(client: LiveClient, health: dict[str, Any]) -> Iterator[LiveClient]:
    """The one sign-in of the run. Any failure stops the run; nothing retries (rule 12)."""
    email = os.environ.get("LIVE_CHECK_EMAIL", "")
    password = os.environ.get("LIVE_CHECK_PASSWORD", "")
    if not email or not password:
        pytest.exit("live checks refused: LIVE_CHECK_EMAIL and LIVE_CHECK_PASSWORD are not set",
                    returncode=4)
    try:
        client.login(email, password)
    except (SignInError, LiveTimeoutError) as exc:
        pytest.exit(f"sign-in failed, not retried: {exc}", returncode=1)
    try:
        yield client
    finally:
        _logout(client)


@pytest.fixture(scope="session")
def me(signed_in: LiveClient) -> dict[str, Any]:
    try:
        return require_usable_account(signed_in)
    except (GuardError, LiveTimeoutError) as exc:
        pytest.exit(str(exc), returncode=1)


@pytest.fixture(scope="session")
def placeholders(signed_in: LiveClient, me: dict[str, Any]) -> dict[str, str]:
    """The values behind `@name` in the inventory, read with GETs from the lookups."""
    today = india_today()
    values = {"@today": today.isoformat(),
              "@yesterday": (today - dt.timedelta(days=1)).isoformat()}
    territories = f"{API}/lookups/territories"
    district = _first(signed_in, territories, {"level": "district", "limit": "1"})
    if district is not None:
        values["@district_id"] = str(district["id"])
        parent = district.get("parent") or {}
        if parent.get("level") == "state":
            values["@state_id"] = str(parent["id"])
    if "@state_id" not in values:
        state = _first(signed_in, territories, {"level": "state", "limit": "1"})
        if state is not None:
            values["@state_id"] = str(state["id"])
    if me.get("id"):
        values["@user_id"] = str(me["id"])
    # any lead the account can see; a box with none yet leaves it unresolved and
    # the paths that need it are reported as skipped
    lead = _first(signed_in, f"{API}/leads", {"limit": "1"})
    if lead is not None:
        values["@lead_id"] = str(lead["id"])
    return values


def _first(client: LiveClient, path: str, params: dict[str, str]) -> dict[str, Any] | None:
    response = client.get(path, params=params)
    if response.status_code != 200:
        raise AssertionError(f"placeholder lookup failed: {describe(response)}")
    rows = response.json().get("data") or []
    return rows[0] if rows else None


def _logout(client: LiveClient) -> None:
    # A timed-out logout still shows: it is listed as sent, and the run has failed.
    if client.signed_in and not client.signed_out:
        with contextlib.suppress(LiveTimeoutError):
            client.logout()


# ── the end of the run ──────────────────────────────────────────────────────

def pytest_sessionfinish(session: pytest.Session) -> None:
    """The logout again, for a run stopped by `pytest.exit` before the session
    fixture's teardown could run. `logout()` refuses a second call, so a run that
    already signed out is untouched."""
    live = _RUN.get("client")
    if isinstance(live, LiveClient):
        _logout(live)


def pytest_terminal_summary(terminalreporter: Any) -> None:
    live = _RUN.get("client")
    writes = live.writes if isinstance(live, LiveClient) else []
    terminalreporter.section("live checks: non-GET requests sent")
    for line in writes or ["none"]:
        terminalreporter.write_line(f"  {line}")
    if os.environ.get("LIVE_TARGET") == "production":
        terminalreporter.section("live checks: not covered on production")
        for line in PRODUCTION_LIMITS:
            terminalreporter.write_line(f"  {line}")
