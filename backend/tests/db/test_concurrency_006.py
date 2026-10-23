"""Rule 19 under concurrency: a lead mutation locks the row FOR UPDATE, so a second
caller waits and then validates against the stage the first one left (EC-1).

Two sessions, ordered by an event rather than a sleep (ISS-060). Session A moves a
new lead to contacted and holds its transaction open; session B tries the same
move at the same time. With the lock B blocks until A commits, then reads
`contacted` and is refused (contacted -> contacted is not a move). Without the
lock B reads the stale `new`, succeeds, and both write: last write wins silently.
Executed with the lock removed from `_lock()`: this test then fails (ISS-068).

Commits, so it cleans up after itself.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.db.session import enter_role
from api.errors import ValidationFailed
from api.schemas.leads import LeadTransition
from api.services import leads as service

pytestmark = pytest.mark.db

HOLD = 0.8


@pytest_asyncio.fixture
async def owned_lead(sessions: Callable[[], AsyncSession]) -> AsyncIterator[dict[str, str]]:
    """A committed staff user with leads edit:own, and a new lead they own."""
    tag = uuid.uuid4().hex[:8]
    s = sessions()
    territory = (await s.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"conc6_{tag}"})).scalar_one()
    org = (await s.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"conc6_{tag}", "t": territory})).scalar_one()
    role = (await s.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'Field Officer', 1) RETURNING id"),
        {"c": f"conc6_{tag}"})).scalar_one()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'own'), (:r, 'leads', 'edit', 'own')"), {"r": role})
    user = (await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Conc Officer', :r, :o) RETURNING id"),
        {"e": f"conc6_{tag}@polysil.in", "r": role, "o": org})).scalar_one()
    lead = (await s.execute(text(
        "INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id, "
        "farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id) VALUES "
        "(:no, 'new', 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
        "(SELECT id FROM lead_source WHERE code = 'employee'), 'Conc Farmer', :mob, :t, :u, :o) "
        "RETURNING id"),
        {"no": f"CONC-{tag}", "mob": "+9198" + f"{uuid.uuid4().int % 10**8:08d}",
         "t": territory, "u": user, "o": org})).scalar_one()
    await s.commit()
    ids = {"user": str(user), "org": str(org), "lead": str(lead), "role": str(role),
           "territory": str(territory)}
    try:
        yield ids
    finally:
        c = sessions()
        for stmt in (
            "DELETE FROM activity_event WHERE lead_id = CAST(:lead AS uuid)",
            "DELETE FROM lead WHERE id = CAST(:lead AS uuid)",
            "DELETE FROM app_user WHERE id = CAST(:user AS uuid)",
            "DELETE FROM role_permission WHERE role_id = CAST(:role AS uuid)",
            "DELETE FROM role WHERE id = CAST(:role AS uuid)",
            "DELETE FROM org_unit WHERE id = CAST(:org AS uuid)",
            "DELETE FROM territory WHERE id = CAST(:territory AS uuid)",
        ):
            await c.execute(text(stmt), ids)
        await c.commit()


async def _enter(s: AsyncSession, user_id: str) -> None:
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})
    await enter_role(s, "app_role")


def _caller(ids: dict[str, str]) -> Caller:
    return Caller(user_id=ids["user"], org_unit_id=ids["org"], partner_id=None,
                  scopes={"leads": "own"}, deletes=frozenset())


async def test_a_second_transition_waits_for_the_lock_then_sees_the_new_stage(
        sessions: Callable[[], AsyncSession], owned_lead: dict[str, str]) -> None:
    a_locked = asyncio.Event()
    caller = _caller(owned_lead)
    body = LeadTransition(to_stage="contacted")
    outcome: dict[str, object] = {}

    async def session_a() -> None:
        s = sessions()
        async with s.begin():
            await _enter(s, owned_lead["user"])
            await service.transition_lead(s, caller, owned_lead["lead"], body)  # holds the lock
            a_locked.set()
            await asyncio.sleep(HOLD)
        # commit: the lead is now contacted

    async def session_b() -> None:
        await a_locked.wait()
        s = sessions()
        try:
            async with s.begin():
                await _enter(s, owned_lead["user"])
                await service.transition_lead(s, caller, owned_lead["lead"], body)
            outcome["result"] = "applied"
        except ValidationFailed as exc:
            outcome["result"] = exc.code

    await asyncio.gather(session_a(), session_b())

    # B waited for A, then validated against `contacted`, which cannot move to
    # contacted again. Without the lock B reads the stale `new` and applies.
    assert outcome["result"] == "invalid_transition", outcome

    c = sessions()
    stage = (await c.execute(text("SELECT stage::text FROM lead WHERE id = CAST(:l AS uuid)"),
                             {"l": owned_lead["lead"]})).scalar_one()
    n_changes = (await c.execute(text(
        "SELECT count(*) FROM activity_event WHERE lead_id = CAST(:l AS uuid) "
        "AND kind = 'lead.stage_changed'"), {"l": owned_lead["lead"]})).scalar_one()
    await c.rollback()
    assert stage == "contacted" and n_changes == 1, "exactly one write happened"


# ── concurrent merges (cross-vendor P1) ──────────────────────────────────────

@pytest_asyncio.fixture
async def merge_trio(sessions: Callable[[], AsyncSession]) -> AsyncIterator[dict[str, str]]:
    """A committed global-edit staff user and three open leads they own."""
    tag = uuid.uuid4().hex[:8]
    s = sessions()
    territory = (await s.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"mrg6_{tag}"})).scalar_one()
    org = (await s.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"mrg6_{tag}", "t": territory})).scalar_one()
    role = (await s.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'Admin', 5) RETURNING id"),
        {"c": f"mrg6_{tag}"})).scalar_one()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'global'), (:r, 'leads', 'edit', 'global')"), {"r": role})
    user = (await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Merge Admin', :r, :o) RETURNING id"),
        {"e": f"mrg6_{tag}@polysil.in", "r": role, "o": org})).scalar_one()
    leads = []
    for i in range(3):
        leads.append(str((await s.execute(text(
            "INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id, "
            "farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id) VALUES "
            "(:no, 'new', 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
            "(SELECT id FROM lead_source WHERE code = 'employee'), 'Farmer', :mob, :t, :u, :o) "
            "RETURNING id"),
            {"no": f"MRG-{tag}-{i}", "mob": "+9198" + f"{uuid.uuid4().int % 10**8:08d}",
             "t": territory, "u": user, "o": org})).scalar_one()))
    await s.commit()
    ids = {"user": str(user), "org": str(org), "role": str(role), "territory": str(territory),
           "a": leads[0], "b": leads[1], "c": leads[2]}
    try:
        yield ids
    finally:
        c = sessions()
        trio = "(CAST(:a AS uuid), CAST(:b AS uuid), CAST(:c AS uuid))"
        for stmt in (
            f"DELETE FROM activity_event WHERE lead_id IN {trio}",
            f"DELETE FROM lead_duplicate_link WHERE lead_a_id IN {trio} OR lead_b_id IN {trio}",
            f"UPDATE lead SET merged_into_id = NULL, stage = 'new' WHERE id IN {trio}",
            f"DELETE FROM lead WHERE id IN {trio}",
            "DELETE FROM app_user WHERE id = CAST(:user AS uuid)",
            "DELETE FROM role_permission WHERE role_id = CAST(:role AS uuid)",
            "DELETE FROM role WHERE id = CAST(:role AS uuid)",
            "DELETE FROM org_unit WHERE id = CAST(:org AS uuid)",
            "DELETE FROM territory WHERE id = CAST(:territory AS uuid)",
        ):
            await c.execute(text(stmt), ids)
        await c.commit()


async def test_concurrent_merges_cannot_form_a_chain(
        sessions: Callable[[], AsyncSession], merge_trio: dict[str, str]) -> None:
    """A -> B held open while B -> C starts. lead_merge() locks both participants
    in id order, so the second waits and then re-points A at C. Without the locks,
    B -> C's flattening cannot see A's uncommitted pointer and A -> B -> C forms,
    which loses A from C's timeline (cross-vendor P1)."""
    first_locked = asyncio.Event()
    t = merge_trio

    async def first() -> None:        # A -> B, held open past B -> C's start
        s = sessions()
        async with s.begin():
            await _enter(s, t["user"])
            await s.execute(text("SELECT lead_merge(CAST(:l AS uuid), CAST(:v AS uuid))"),
                            {"l": t["a"], "v": t["b"]})
            first_locked.set()
            await asyncio.sleep(HOLD)

    async def second() -> None:       # B -> C, must wait for the first to commit
        await first_locked.wait()
        s = sessions()
        async with s.begin():
            await _enter(s, t["user"])
            await s.execute(text("SELECT lead_merge(CAST(:l AS uuid), CAST(:v AS uuid))"),
                            {"l": t["b"], "v": t["c"]})

    await asyncio.gather(first(), second())

    c = sessions()
    rows = {str(r[0]): (str(r[1]) if r[1] else None) for r in (await c.execute(text(
        "SELECT id, merged_into_id FROM lead WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))"),
        {"a": t["a"], "b": t["b"]})).all()}
    await c.rollback()
    assert rows[t["a"]] == t["c"] and rows[t["b"]] == t["c"], f"flat group expected, got {rows}"
