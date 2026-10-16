"""The two guards on `live/inventory.json` (FS-065 rule 8).

The live checks call every parameterless GET on a deployed box, production included,
and production must not be written to. A list kept by hand drifts: a new route is
missed, or a GET that writes is called. So:

  * completeness: the file names every parameterless GET in the schema, nothing
    else, and each entry is well formed. `public` is derived from the route's
    dependencies, never from its path (rule 14).
  * no checked path writes: every path the live checks call on production runs
    here with its request transaction set READ ONLY as the first statement. A write
    raises SQLSTATE 25006 and fails the test. A path that did not answer 200 was
    not exercised, so it must say why in an `unproven` note.

The arrangement is proven to bite by `/tracking/team/latest`, which inserts a
`tracking_view_log` row on every call (rule 9).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import inspect
import json
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, ExceptionContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from api.db.session import engine
from api.deps import get_db
from api.main import app
from api.services.clock import today_ist
from live import inventory
from scripts.seed_prod import RELEASED
from tests.api.conftest import V1, Admin, _login

READ_ONLY_VIOLATION = "25006"
SKIP_KEYS = {"production", "staging", "all"}
ENTRY_KEYS = {"query", "public", "skip", "forbidden", "unproven"}
# What the live suite resolves at run time. A new placeholder needs a resolver there
# first; this list is how the two stay in step.
PLACEHOLDERS = {"@district_id", "@state_id", "@today", "@yesterday", "@user_id", "@lead_id"}


def _routes() -> dict[str, Any]:
    """Every schema route by full path. FastAPI 0.141 nests included routers lazily,
    so `app.routes` holds `_IncludedRouter` branches; `effective_candidates()` gives
    each branch's routes with the mounted path and the full dependency tree."""

    def flat(routes: list[Any]) -> Iterator[Any]:
        for r in routes:
            if hasattr(r, "effective_candidates"):
                yield from flat(r.effective_candidates())
            elif getattr(r, "dependant", None) is not None and r.include_in_schema:
                yield r

    return {r.path: r for r in flat(app.routes) if "GET" in r.methods}


def _gates(route: Any) -> list[list[tuple[str, str]]]:
    """Each permission gate on the route, as the (module, action) pairs that open
    it. `require(m, a)` is one pair; `require_any(...)` is several, any one of which
    opens it. Read from the closures `api/deps.py` builds."""
    gates: list[list[tuple[str, str]]] = []
    stack = list(route.dependant.dependencies)
    while stack:
        d = stack.pop()
        stack.extend(d.dependencies)
        call = d.call
        qualname = getattr(call, "__qualname__", "")
        if qualname not in ("require.<locals>.dep", "require_any.<locals>.dep"):
            continue
        cells = inspect.getclosurevars(call).nonlocals
        if "pairs" in cells:
            gates.append([tuple(pair) for pair in cells["pairs"]])
        else:
            gates.append([(cells["module"], cells["action"])])
    return gates


def forbidden_on_production(route: Any) -> bool:
    """Production's roles hold the released modules only (`scripts/seed_prod.py`),
    and `require` has no administrator bypass: a gate none of whose modules is
    released answers 403 `insufficient_permission` there."""
    return any(all(module not in RELEASED for module, _ in gate) for gate in _gates(route))


def _get_routes() -> dict[str, Any]:
    return _routes()


def _needs_token(route: Any) -> bool:
    """`get_db` is the one dependency that refuses a request without a token."""
    stack = list(route.dependant.dependencies)
    while stack:
        d = stack.pop()
        if d.call is get_db:
            return True
        stack.extend(d.dependencies)
    return False


# ── completeness ─────────────────────────────────────────────────────────────

def test_the_inventory_lists_every_parameterless_get_and_nothing_else() -> None:
    listed = set(inventory.load())
    in_schema = inventory.schema_paths(app.openapi())
    assert in_schema - listed == set(), "add these to live/inventory.json"
    assert listed - in_schema == set(), "these are not in the schema any more"


def test_every_entry_is_well_formed() -> None:
    raw: dict[str, dict[str, Any]] = json.loads(inventory.PATH.read_text(encoding="utf-8"))
    problems: list[str] = []
    for path, e in raw.items():
        if not path.startswith("/api/v1/") or "{" in path:
            problems.append(f"{path}: not a full parameterless path")
        if set(e) - ENTRY_KEYS or not {"query", "public", "skip", "forbidden"} <= set(e):
            problems.append(f"{path}: keys {sorted(e)}")
            continue
        if not isinstance(e["public"], bool):
            problems.append(f"{path}: public is not true or false")
        for name, value in e["query"].items():
            if not isinstance(value, str):
                problems.append(f"{path}: query {name} is not a string")
            elif value.startswith("@") and value not in PLACEHOLDERS:
                problems.append(f"{path}: query {name} uses unknown placeholder {value}")
        for env, reason in e["skip"].items():
            if env not in SKIP_KEYS:
                problems.append(f"{path}: skip key {env!r}")
            if not isinstance(reason, str) or not reason.strip():
                problems.append(f"{path}: skip {env} has no reason")
        if not isinstance(e["forbidden"], list):
            problems.append(f"{path}: forbidden is not a list")
        else:
            problems += [f"{path}: forbidden {env!r}" for env in e["forbidden"]
                         if env not in inventory.ENVIRONMENTS]
        if "unproven" in e and (not isinstance(e["unproven"], str) or not e["unproven"].strip()):
            problems.append(f"{path}: unproven has no reason")
    assert problems == []


def test_public_matches_what_the_route_depends_on() -> None:
    """Rule 14: a path is public when nothing in its dependency tree demands a token.
    Derived from the routes, so a router that moves to the anonymous session, or off
    it, fails here until the file says so."""
    routes = _routes()
    wrong = {p: e.public for p, e in inventory.load().items()
             if p in routes and e.public == _needs_token(routes[p])}
    assert wrong == {}, "public flag disagrees with the route's dependencies"


def test_forbidden_on_production_follows_the_release_scope() -> None:
    """Code review F1. An empty list made every unreleased module a failure on
    production, so every production deploy would have exited 1."""
    routes = _routes()
    wrong = {p: e.forbidden for p, e in inventory.load().items()
             if ("production" in e.forbidden) != forbidden_on_production(routes[p])}
    assert not wrong, f"forbidden lists out of step with seed_prod.RELEASED: {sorted(wrong)}"
    assert all(set(e.forbidden) <= {"production"} for e in inventory.load().values())


def test_the_gate_reader_sees_both_kinds_of_gate() -> None:
    """The derivation above is only as good as `_gates`: prove it reads a released
    `require`, an unreleased `require`, and a `require_any`."""
    routes = _routes()
    assert _gates(routes[f"{V1}/leads"]) == [[("leads", "view")]]
    assert forbidden_on_production(routes[f"{V1}/complaints"])
    assert not forbidden_on_production(routes[f"{V1}/leads"])
    assert any(len(g) > 1 for r in routes.values() for g in _gates(r)), \
        "no require_any gate found: the reader no longer sees them"


def test_every_query_key_is_a_declared_parameter() -> None:
    """Code review F7. FastAPI ignores an unknown query key, so a misspelt window
    key would let an export drain up to 5,001 rows on production unnoticed."""
    schema = app.openapi()["paths"]
    wrong = []
    for path, entry in inventory.load().items():
        declared = {prm["name"] for prm in schema[path]["get"].get("parameters", [])
                    if prm.get("in") == "query"}
        wrong += [f"{path}?{key}" for key in entry.query if key not in declared]
    assert not wrong, f"query keys the route does not declare: {wrong}"


def test_the_two_view_log_paths_and_the_portal_are_skipped_on_production() -> None:
    """Rules 3 and 9, by path: whatever these answer today, production never sees them."""
    entries = inventory.load()
    must_skip = {"/api/v1/tracking/team/latest", "/api/v1/visits",
                 *(p for p in entries if p.startswith("/api/v1/portal/"))}
    assert {p for p in must_skip if entries[p].skip_reason("production") is None} == set()


def test_exports_take_a_one_day_window_or_are_skipped_on_production() -> None:
    """Rule 13. An export's date filter is the only bound on what it drains."""
    loose = [p for p, e in inventory.load().items() if p.endswith("/export")
             and e.skip_reason("production") is None
             and sum(v == "@today" for v in e.query.values()) != 2]
    assert loose == []


# ── no checked path writes ───────────────────────────────────────────────────

@contextlib.contextmanager
def _read_only() -> Iterator[list[str]]:
    """Every session transaction opened inside the block starts with
    `SET TRANSACTION READ ONLY`, ahead of `get_db`'s claim lookup. Transaction-local,
    so nothing leaks through PgBouncer. Yields the SQLSTATE of every database error
    raised meanwhile, including one a service catches and turns into a 4xx."""
    states: list[str] = []

    def begin(_s: Session, _t: SessionTransaction, connection: Connection) -> None:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")

    def error(context: ExceptionContext) -> None:
        states.append(str(getattr(context.original_exception, "sqlstate", "") or ""))

    event.listen(Session, "after_begin", begin)
    event.listen(engine.sync_engine, "handle_error", error)
    try:
        yield states
    finally:
        event.remove(Session, "after_begin", begin)
        event.remove(engine.sync_engine, "handle_error", error)


@pytest_asyncio.fixture
async def raw_client() -> AsyncIterator[httpx.AsyncClient]:
    """The real app, but a 500 comes back as a response rather than a raised error,
    so the guard sees the status and the SQLSTATE together."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def everything(admin: Admin, sessions: Callable[[], AsyncSession]) -> Admin:
    """The admin given every permission any role holds, at global scope, so no write
    hides behind a 403. The admin fixture's teardown removes the role's rows."""
    s = sessions()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) "
        "SELECT DISTINCT CAST(:r AS uuid), module, action, CAST('global' AS permission_scope) "
        "FROM role_permission "
        "ON CONFLICT (role_id, module, action) DO UPDATE SET scope = EXCLUDED.scope"),
        {"r": admin.user.role_id})
    await s.commit()
    await s.close()
    return admin


async def _placeholders(sessions: Callable[[], AsyncSession], admin: Admin) -> dict[str, str]:
    s = sessions()
    try:
        district = (await s.execute(text(
            "SELECT d.id::text AS id, d.parent_id::text AS state FROM territory d "
            "JOIN territory p ON p.id = d.parent_id AND p.level = 'state' "
            "WHERE d.level = 'district' ORDER BY d.name, d.id LIMIT 1"))).one()
    finally:
        await s.close()
    today = today_ist()
    return {"@district_id": district.id, "@state_id": district.state,
            "@today": today.isoformat(), "@yesterday": (today - dt.timedelta(days=1)).isoformat(),
            "@user_id": admin.user.id}


async def _own_lead(client: httpx.AsyncClient, h: dict[str, str], district_id: str) -> str:
    """A lead of the test's own, made before the read-only window opens. The paths
    that take `@lead_id` need one, and a clean database has none."""
    systems = (await client.get(f"{V1}/lookups/mis-systems", headers=h)).json()["data"]
    r = await client.post(f"{V1}/leads", headers={**h, "Idempotency-Key": uuid.uuid4().hex},
                          json={"farmer_name": "Inventory Check", "territory_id": district_id,
                                "mobile": "98" + f"{uuid.uuid4().int % 10**8:08d}",
                                "inquiry_type": "commercial", "mis_system": systems[0]["code"]})
    assert r.status_code == 201, r.text
    return str(r.json()["data"]["id"])


def _query(entry: inventory.Entry, values: dict[str, str]) -> dict[str, str]:
    return {k: values[v] if v.startswith("@") else v for k, v in entry.query.items()}


def _code(r: httpx.Response) -> str:
    try:
        return str(r.json()["error"]["code"])
    except (ValueError, KeyError, TypeError):
        return ""


@pytest.mark.db
async def test_no_path_checked_on_production_writes(
        raw_client: httpx.AsyncClient, everything: Admin,
        sessions: Callable[[], AsyncSession]) -> None:
    """Rule 8, second guard. A guess about which GET writes does not pass this."""
    values = await _placeholders(sessions, everything)
    h = await _login(raw_client, everything.user.email, everything.user.password)
    # the fixture's own district: its teardown removes the leads made there
    values["@lead_id"] = await _own_lead(raw_client, h, everything.territory_id)
    checked = [e for e in inventory.load().values() if e.skip_reason("production") is None]

    writes: list[str] = []
    unexercised: list[str] = []
    stale: list[str] = []
    slow: list[tuple[float, str]] = []
    with _read_only() as states:
        for e in checked:
            states.clear()
            started = time.monotonic()
            r = await raw_client.get(e.path, params=_query(e, values),
                                     headers={} if e.public else h)
            slow.append((time.monotonic() - started, e.path))
            if READ_ONLY_VIOLATION in states:
                writes.append(f"{e.path} -> {r.status_code}")
            elif r.status_code != 200 and not e.unproven:
                unexercised.append(f"{e.path} -> {r.status_code} {_code(r)} {states}")
            elif r.status_code == 200 and e.unproven:
                stale.append(e.path)

    print(f"\nchecked {len(checked)} paths read-only; slowest: "
          + ", ".join(f"{p} {s:.1f}s" for s, p in sorted(slow, reverse=True)[:5]))
    for line in unexercised:
        print(f"  not exercised: {line}")
    for e in checked:
        if e.unproven:
            print(f"  unproven by note: {e.path}: {e.unproven}")
    for p in stale:
        print(f"  answered 200 but carries an unproven note: {p}")
    assert writes == [], "these GET paths write; skip them on production (rule 9)"
    assert unexercised == [], "not proven read-only; fix the query or add an unproven note"


@pytest.mark.db
async def test_the_read_only_guard_catches_a_get_that_writes(
        raw_client: httpx.AsyncClient, everything: Admin) -> None:
    """Proves the arrangement above bites. `/tracking/team/latest` logs every look at
    the team map, so under READ ONLY its insert fails with 25006, while a plain read
    in the same arrangement still answers 200."""
    h = await _login(raw_client, everything.user.email, everything.user.password)
    with _read_only() as states:
        me = await raw_client.get(f"{V1}/auth/me", headers=h)
        assert me.status_code == 200 and states == []
        r = await raw_client.get(f"{V1}/tracking/team/latest", headers=h)
    assert READ_ONLY_VIOLATION in states
    assert r.status_code == 500
