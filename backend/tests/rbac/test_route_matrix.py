"""The permission matrix as the API enforces it, route by route (test build-out 3).

`tests/db/test_matrix_005.py` proves the database answers every one of the 1,760
cells of RBAC.md section 6. This proves the other half: that every route asks.

1. **Every route is classified.** It carries a `require()` gate, or it is listed
   in UNGATED with the reason it checks access some other way. A new route that
   is neither fails here, so "forgot the gate" cannot ship quietly.
2. **Every gate names a real cell.** A typo such as `require("lead", "view")`
   refuses everyone, and nothing else would notice.
3. **Every staff role against every gated route, over HTTP.** `403
   insufficient_permission` exactly where RBAC.md leaves the cell blank, and
   never where it holds one. The negative cases are the ones that matter.

Partner roles sign in by WhatsApp code, so (3) covers the 13 staff and board
roles; the portal side is the parity suite's.
"""

# ruff: noqa: E501  (the allowlist reads better on one line per route)

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text

from api.domain.authz import ACTIONS, modules_in, roles_in
from scripts.generate_permission_seed import load_grants

GRANTS = load_grants()
GRANTED = {(g.role, g.module, g.action) for g in GRANTS}
MODULES = set(modules_in(GRANTS))
STAFF_ROLES = sorted(r for r in roles_in(GRANTS) if r not in {"distributor", "dealer", "sub_dealer"})
V1 = "/api/v1"
PASSWORD = "rbac matrix horse battery"

# Routes with no require() gate, and how each one checks access instead. A prefix
# covers every route under it.
UNGATED_PREFIXES: dict[str, str] = {
    "/api/v1/public/": "no sign-in by design: a share token, an applicant token or a WhatsApp code (FS-003a, FS-005, FS-051)",
    "/api/v1/auth/": "signing in, refreshing and signing out; /auth/me reads the caller's own row",
    "/api/v1/lookups/": "reference lists every signed-in user reads; RLS is the row floor",
    "/api/v1/portal/": "the partner's own portal: scoped by the partner claim in the service and by RLS (FS-044)",
    "/api/v1/conversations": "membership is checked per conversation in the service (FS-019, FS-048)",
    "/api/v1/dealer-applications": "the deciders and relaxers are settings, checked by dealer_application_can() (FS-051, FS-071)",
    "/api/v1/documents": "each document type takes its parent record's permission, checked in the service (FS-050)",
    "/api/v1/imports": "each import kind takes its target module's create permission, checked in the service (FS-062)",
    "/api/v1/notifications": "the caller's own bell (FS-018)",
    "/api/v1/me/": "the caller's own settings",
    "/api/v1/assistant": "navigation text only, filtered by the caller's permissions (FS-045)",
    "/api/v1/subsidy-masters/": "published scheme tables every staff user reads (FS-009a)",
    "/api/v1/subsidy-schemes": "published scheme definitions every staff user reads (FS-039)",
    "/api/v1/org-units": "the org tree, rows filtered by RLS (FS-006)",
    "/api/v1/territories": "the territory tree, rows filtered by RLS (FS-006)",
    "/api/v1/ratings": "a partner rates its own orders; staff read through RLS (FS-043)",
}
UNGATED: dict[str, str] = {
    "GET /api/v1/approvals/thresholds": "staff only, checked in the handler",
    "GET /api/v1/campaigns": "every staff user reads the list for the lead form's picker; cost hidden without campaigns.view (FS-040, RBAC.md note)",
    "GET /api/v1/campaigns/{campaign_id}": "as the list (FS-040)",
    "GET /api/v1/dashboard/overview": "each tile is null without its own module (FS-017)",
    "GET /api/v1/gstin/{gstin}": "any signed-in user; ISS-227",
    "GET /api/v1/holidays": "the company calendar, read by everyone (FS-028)",
    "GET /api/v1/leads/{lead_id}/documents": "the lead's documents, through the lead's RLS (FS-050)",
    "GET /api/v1/partners/{partner_id}/credit": "staff, or the partner itself, checked in the handler (FS-027)",
    "GET /api/v1/partners/{partner_id}/dealer-rating": "staff, or the partner itself, checked in the handler (FS-043)",
    "GET /api/v1/reward-settings": "read by every signed-in user to show points (FS-032)",
    "GET /api/v1/settings": "the admin switches the screens need; partners refused in the handler (FS-036)",
    "GET /api/v1/staff-directory": "staff only, for the chat picker (FS-019)",
    "GET /api/v1/tracking/policy": "the tracking policy a phone shows before consent (FS-021)",
}


def _flat(routes: list[Any]) -> Iterator[Any]:
    """FastAPI 0.141 nests included routers lazily (see test_live_inventory)."""
    for r in routes:
        if hasattr(r, "effective_candidates"):
            yield from _flat(r.effective_candidates())
        elif getattr(r, "dependant", None) is not None and r.include_in_schema:
            yield r


def _gates(dependant: Any) -> list[list[tuple[str, str]]]:
    """Every require()/require_any() in the dependency tree, as (module, action)
    alternatives, read from the closure the factory built."""
    out: list[list[tuple[str, str]]] = []
    for d in dependant.dependencies:
        fn = d.call
        name = getattr(fn, "__qualname__", "")
        if name.startswith(("require.", "require_any.")):
            cells = {n: c.cell_contents for n, c in zip(fn.__code__.co_freevars, fn.__closure__ or (), strict=True)}
            out.append(list(cells["pairs"]) if "pairs" in cells else [(cells["module"], cells["action"])])
        out += _gates(d)
    return out


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    gates: tuple[tuple[tuple[str, str], ...], ...]


def _routes() -> list[Route]:
    from api.main import app
    out = []
    for r in _flat(app.routes):
        gates = tuple(tuple(g) for g in _gates(r.dependant))
        for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
            out.append(Route(m, r.path, gates))
    return sorted(out, key=lambda r: (r.path, r.method))


ROUTES = _routes()
GATED = [r for r in ROUTES if r.gates]


def _why_ungated(r: Route) -> str | None:
    key = f"{r.method} {r.path}"
    if key in UNGATED:
        return UNGATED[key]
    return next((why for p, why in UNGATED_PREFIXES.items() if r.path.startswith(p)), None)


# ── 1 and 2: no database ─────────────────────────────────────────────────────

def test_every_route_is_gated_or_says_why_not() -> None:
    loose = [f"{r.method} {r.path}" for r in ROUTES if not r.gates and _why_ungated(r) is None]
    assert loose == [], "add a require() gate, or a reason to UNGATED:\n" + "\n".join(loose)


def test_the_allowlist_holds_no_route_that_is_gated_or_gone() -> None:
    """An entry outliving its route, or a route that gained a gate, is stale."""
    keys = {f"{r.method} {r.path}": r for r in ROUTES}
    stale = [k for k in UNGATED if k not in keys or keys[k].gates]
    assert stale == []
    unused = [p for p in UNGATED_PREFIXES if not any(r.path.startswith(p) and not r.gates for r in ROUTES)]
    assert unused == []


def test_every_gate_names_a_module_and_action_of_the_matrix() -> None:
    bad = [(f"{r.method} {r.path}", m, a) for r in GATED for g in r.gates for m, a in g
           if m not in MODULES or a not in ACTIONS]
    assert bad == []


# A read that serves an action, gated on that action on purpose.
READ_FOR_AN_ACTION: dict[str, str] = {
    "/api/v1/approvals/pending": "the approver's own queue (FS-011)",
    "/api/v1/complaints/{complaint_id}/assignees": "the picker for the person who assigns (FS-015)",
    "/api/v1/leads/assignees": "the picker for the person who reassigns a lead (FS-003)",
    "/api/v1/tasks/assignees": "the picker for the person who creates a task (FS-014)",
}


def test_reads_are_gated_on_view() -> None:
    """A GET gated on create or edit would refuse a read-only role its own screen."""
    odd = [f"GET {r.path} {g}" for r in GATED if r.method == "GET" and r.path not in READ_FOR_AN_ACTION
           for g in r.gates if all(a != "view" for _, a in g)]
    assert odd == []


# ── 3: over HTTP ─────────────────────────────────────────────────────────────

# Refusals a handler adds on top of the gate: the cell is granted, and the route
# still answers 403 by a rule of its own. Each rule is worked out from the grants,
# not listed by role, so a matrix change moves the expectation with it.
VIEW_SCOPE = {(g.role, g.module): g.scope for g in GRANTS if g.action == "view"}

# api/services/reports.py _need(): a report also needs view on the modules it reads.
REPORT_NEEDS: dict[str, tuple[str, ...]] = {
    "lead-conversion": ("leads",), "lost-leads": ("leads",), "salesperson-performance": ("leads",),
    "follow-ups": ("tasks",), "dealer-performance": ("sales_orders", "partners"),
    "campaign-performance": ("leads",), "territory-performance": ("leads",),
    "complaints": ("complaints",), "sales-forecast": ("leads",), "insights": ("leads",),
}


def _team_view(role: str) -> bool:
    """api/services/tasks.py team(): tasks viewed at org_subtree or global (FS-014)."""
    return VIEW_SCOPE.get((role, "tasks")) in ("org_subtree", "global")


BEYOND_THE_MATRIX: dict[str, tuple[Any, str]] = {
    "GET /api/v1/planner/team": (_team_view, "the team view is for managers (FS-014)"),
    **{f"GET /api/v1/reports/{name}": (
        lambda role, mods=mods: all((role, m) in VIEW_SCOPE for m in mods),
        f"the report also needs view on {', '.join(mods)}") for name, mods in REPORT_NEEDS.items()},
}

# With the dummy id the definer refuses a record the caller cannot see with 403,
# not 404, so a granted role and a refused one answer alike. Over HTTP only the
# refusal is checked here; the grant side is the feature tests' (FS-011, FS-015).
RECORD_CHECKED: dict[str, str] = {
    "DELETE /api/v1/orders/{order_id}": "order_delete() refuses an order not visible with 42501",
    "GET /api/v1/complaints/{complaint_id}/assignees": "complaint_assignees() refuses with 42501",
}


def _allowed(role: str, r: Route) -> bool:
    extra = BEYOND_THE_MATRIX.get(f"{r.method} {r.path}")
    if extra and not extra[0](role):
        return False
    return all(any((role, m, a) in GRANTED for m, a in g) for g in r.gates)


_PARAM = re.compile(r"\{[^}]+\}")
DUMMY = "00000000-0000-4000-8000-000000000000"


@pytest_asyncio.fixture
async def account(request: pytest.FixtureRequest) -> AsyncIterator[str]:
    """A throwaway user of the test's role, on an existing office; removed after."""
    from api.db.session import async_session_factory
    role: str = request.node.callspec.params["role"]
    email = f"rbac_{role}_{uuid.uuid4().hex[:8]}@polysil.in"
    async with async_session_factory() as s:
        office = str((await s.execute(text(
            "SELECT id FROM org_unit WHERE deleted_at IS NULL ORDER BY role_level DESC, id LIMIT 1"))).scalar_one())
        uid = str((await s.execute(text(
            "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
            "SELECT 'staff', :e, :p, :n, r.id, CAST(:o AS uuid) FROM role r WHERE r.code = :c RETURNING id"),
            {"e": email, "p": PasswordHasher().hash(PASSWORD), "n": f"Rbac {role}", "c": role, "o": office})).scalar_one())
        await s.commit()
    try:
        yield email
    finally:
        async with async_session_factory() as s:
            for stmt in ("DELETE FROM tracking_view_log WHERE viewer_id = CAST(:u AS uuid)",
                         "DELETE FROM idempotency_record WHERE user_id = CAST(:u AS uuid)",
                         "DELETE FROM activity_event WHERE actor_id = CAST(:u AS uuid) OR entity_id = CAST(:u AS uuid)",
                         "DELETE FROM session WHERE user_id = CAST(:u AS uuid)",
                         "DELETE FROM login_attempt WHERE identifier = CAST(:e AS citext)",
                         "DELETE FROM app_user WHERE id = CAST(:u AS uuid)"):
                await s.execute(text(stmt), {"u": uid, "e": email})
            await s.commit()


async def _call(client: httpx.AsyncClient, headers: dict[str, str], r: Route) -> httpx.Response:
    path = _PARAM.sub(DUMMY, r.path)
    h = {**headers, "Idempotency-Key": uuid.uuid4().hex}
    if r.method in ("POST", "PUT", "PATCH"):
        return await client.request(r.method, path, headers=h, json={})
    return await client.request(r.method, path, headers=h)


def _refused(resp: httpx.Response) -> bool:
    if resp.status_code != 403:
        return False
    try:
        return bool(resp.json().get("error", {}).get("code") == "insufficient_permission")
    except ValueError:
        return False


@pytest.mark.db
@pytest.mark.rls
@pytest.mark.parametrize("role", STAFF_ROLES)
async def test_each_role_is_refused_exactly_where_the_matrix_is_blank(
        client: httpx.AsyncClient, account: str, role: str) -> None:
    login = await client.post(f"{V1}/auth/login", json={"email": account, "password": PASSWORD})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    wrong: list[str] = []
    for r in GATED:
        resp = await _call(client, headers, r)
        expected = not _allowed(role, r)
        if not expected and f"{r.method} {r.path}" in RECORD_CHECKED:
            continue
        if _refused(resp) != expected:
            wrong.append(f"{r.method} {r.path}: matrix says {'refuse' if expected else 'allow'}, "
                         f"API answered {resp.status_code} {resp.text[:120]}")
    assert wrong == [], f"{role}:\n" + "\n".join(wrong)


def test_the_exceptions_name_real_routes_and_roles() -> None:
    keys = {f"{r.method} {r.path}" for r in GATED}
    assert set(BEYOND_THE_MATRIX) <= keys
    assert set(READ_FOR_AN_ACTION) <= {r.path for r in GATED}
    assert set(RECORD_CHECKED) <= keys
    assert {f"GET /api/v1/reports/{n}" for n in REPORT_NEEDS} <= keys, "a report was renamed"
    assert all(m in MODULES for mods in REPORT_NEEDS.values() for m in mods)
