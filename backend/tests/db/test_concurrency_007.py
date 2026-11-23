"""FS-006's mechanisms that only exist under concurrency (section 10, the
concurrency row; code review F-1).

Every sequential test would pass with the locks removed: two calls in one
transaction never contend. Each test here forces genuine overlap on two
connections, through the real service functions where the mechanism lives in
the service (the handover's id-ordered lock on both people) and through raw SQL
where it lives in a trigger (the anchor share lock).

The order is made deterministic with an Event, not a sleep: the first connection
signals once its statement has returned (its locks are held), the second starts
only then, and the first commits a little later. So the second either blocks on
the lock and re-reads the committed state, or it does not, and the assertion
tells which. A stagger alone lost that race through the tunnel's latency.

These commit, so they clean up after themselves. The fixture is a committed
administrator with users and leads at global, two field officers in one office,
and a coded state above the office's district so leads can be numbered.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.db.session import enter_role
from api.domain.leads import financial_year
from api.schemas.leads import LeadAssign
from api.schemas.users import HandoverRequest
from api.services import leads as leads_service
from api.services import users as users_service

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

# How long the first connection keeps its transaction open after signalling: long
# enough that the second is provably inside its statement, waiting on the lock.
HOLD = 0.8


@dataclass
class World:
    admin: str
    officer_a: str
    officer_b: str
    org_unit: str
    district: str
    leads_a: list[str]
    leads_b: list[str]


async def _as(db: AsyncSession, user_id: str) -> None:
    """What get_db does: the claim, then app_role, transaction-local."""
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})
    await enter_role(db, "app_role")


def _caller(world: World) -> Caller:
    return Caller(world.admin, world.org_unit, None,
                  scopes={"users": "global", "leads": "global"},
                  deletes=frozenset({"users", "leads"}))


async def _lead(s: AsyncSession, world: World, owner: str, tag: str) -> str:
    return str((await s.execute(text(
        "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, "
        "farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id, created_by) "
        "VALUES (:no, 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
        "(SELECT id FROM lead_source WHERE code = 'employee'), 'Farmer', :mob, :t, :o, :ou, :c) "
        "RETURNING id"),
        {"no": f"CONC7-{tag}", "mob": "+9198" + f"{uuid.uuid4().int % 10**8:08d}",
         "t": world.district, "o": owner, "ou": world.org_unit, "c": world.admin})).scalar_one())


@pytest_asyncio.fixture
async def world(sessions: Callable[[], AsyncSession]) -> AsyncIterator[World]:
    tag = uuid.uuid4().hex[:8]
    s = sessions()
    state = (await s.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": f"conc7_state_{tag}", "c": "Z" + tag[:3].upper()})).scalar_one()
    district = (await s.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
        {"n": f"conc7_{tag}", "p": state})).scalar_one()
    org = (await s.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"conc7_{tag}", "t": district})).scalar_one()
    admin_role = (await s.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'Conc Admin', 5) RETURNING id"),
        {"c": f"conc7_adm_{tag}"})).scalar_one()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'users', 'view', 'global'), (:r, 'users', 'edit', 'global'), "
        "(:r, 'leads', 'view', 'global'), (:r, 'leads', 'edit', 'global'), "
        "(:r, 'leads', 'create', 'global')"), {"r": admin_role})
    fo_role = (await s.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'Conc Officer', 1) RETURNING id"),
        {"c": f"conc7_fo_{tag}"})).scalar_one()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'own'), (:r, 'leads', 'edit', 'own')"), {"r": fo_role})
    ids = {}
    for who, role in (("admin", admin_role), ("a", fo_role), ("b", fo_role)):
        ids[who] = str((await s.execute(text(
            "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, "
            "org_unit_id) VALUES ('staff', :e, 'x', :n, :r, :o) RETURNING id"),
            {"e": f"conc7_{who}_{tag}@polysil.in", "n": who, "r": role, "o": org})).scalar_one())
    w = World(ids["admin"], ids["a"], ids["b"], str(org), str(district), [], [])
    for i in range(3):
        w.leads_a.append(await _lead(s, w, w.officer_a, f"A{i}-{tag}"))
        w.leads_b.append(await _lead(s, w, w.officer_b, f"B{i}-{tag}"))
    await s.commit()
    try:
        yield w
    finally:
        c = sessions()
        people = [w.admin, w.officer_a, w.officer_b]
        for stmt, params in (
            ("DELETE FROM activity_event WHERE lead_id IN (SELECT id FROM lead "
             "WHERE created_by = CAST(:a AS uuid))", {"a": w.admin}),
            ("DELETE FROM lead WHERE created_by = CAST(:a AS uuid)", {"a": w.admin}),
            ("DELETE FROM activity_event WHERE entity_id = ANY(CAST(:p AS uuid[])) "
             "OR actor_id = ANY(CAST(:p AS uuid[]))", {"p": people}),
            ("DELETE FROM session WHERE user_id = ANY(CAST(:p AS uuid[]))", {"p": people}),
            ("DELETE FROM app_user WHERE id = ANY(CAST(:p AS uuid[]))", {"p": people}),
            ("DELETE FROM role_permission WHERE role_id IN (:r1, :r2)",
             {"r1": admin_role, "r2": fo_role}),
            ("DELETE FROM role WHERE id IN (:r1, :r2)", {"r1": admin_role, "r2": fo_role}),
            ("DELETE FROM org_unit WHERE id = :o", {"o": org}),
            ("DELETE FROM territory WHERE id = :d", {"d": district}),
            ("DELETE FROM territory WHERE id = :s", {"s": state}),
        ):
            await c.execute(text(stmt), params)
        await c.commit()


async def _handover(s: AsyncSession, world: World, leaver: str, target: str, *,
                    after: asyncio.Event | None = None, ready: asyncio.Event | None = None,
                    hold: float = 0.0, deactivate: bool = False) -> dict:
    """The service call, under the admin's claim, on its own connection. `after`
    is waited on before the call; `ready` is set once the call has returned, with
    its locks held; the transaction stays open for `hold` before committing."""
    if after is not None:
        await after.wait()
    await _as(s, world.admin)
    try:
        result = await users_service.handover(
            s, _caller(world), leaver, HandoverRequest(to_user_id=target, deactivate=deactivate))
    except DBAPIError as exc:
        await s.rollback()
        if ready is not None:
            ready.set()
        return {"error": str(getattr(exc.orig, "sqlstate", "")) + " " + str(exc.orig)[:120]}
    if ready is not None:
        ready.set()
    await asyncio.sleep(hold)
    await s.commit()
    return result.model_dump()


async def test_two_reciprocal_handovers_queue_instead_of_deadlocking(
        sessions: Callable[[], AsyncSession], world: World) -> None:
    """Rule 20: one handover at a time (an advisory lock taken before any row),
    then both people FOR UPDATE in id order in one statement, then the leads. Both
    calls start at once here, so their lock acquisition overlaps; whichever gets
    the advisory lock moves three leads and the other, queued, then moves six."""
    a, b = sessions(), sessions()
    got = await asyncio.gather(
        _handover(a, world, world.officer_a, world.officer_b, hold=HOLD),
        _handover(b, world, world.officer_b, world.officer_a),
    )
    assert all("error" not in g for g in got), got
    check = sessions()
    owners = (await check.execute(text(
        "SELECT owner_user_id::text, count(*) FROM lead WHERE created_by = :a "
        "GROUP BY owner_user_id"), {"a": world.admin})).all()
    await check.rollback()
    assert sorted(int(n) for _, n in owners) == [6], owners
    assert sorted(g["leads_moved"] for g in got) == [3, 6], got


async def test_opposite_order_row_locks_deadlock_which_the_handover_lock_prevents(
        sessions: Callable[[], AsyncSession], world: World) -> None:
    """The two-statement shape rev 7 had (lock the leaver, then the target)
    deadlocks under reciprocal calls, and PostgreSQL says so (40P01). That is why
    the service takes one advisory lock and one ordered statement; the test above
    holds the property, this one holds the hazard as an executed fact."""
    a, b = sessions(), sessions()
    a_first, b_first = asyncio.Event(), asyncio.Event()

    async def run(s: AsyncSession, first: str, second: str, mine: asyncio.Event,
                  theirs: asyncio.Event) -> str:
        await s.execute(text("SELECT 1 FROM app_user WHERE id = :x FOR UPDATE"), {"x": first})
        mine.set()
        await theirs.wait()
        try:
            await s.execute(text("SELECT 1 FROM app_user WHERE id = :y FOR UPDATE"), {"y": second})
        except DBAPIError as exc:
            await s.rollback()
            return str(getattr(exc.orig, "sqlstate", ""))
        await s.commit()
        return "ok"

    got = await asyncio.gather(
        run(a, world.officer_a, world.officer_b, a_first, b_first),
        run(b, world.officer_b, world.officer_a, b_first, a_first),
    )
    assert sorted(got) == ["40P01", "ok"], got


async def test_a_deactivating_handover_beats_an_assign_to_the_leaver(
        sessions: Callable[[], AsyncSession], world: World) -> None:
    """A-9: the assign shares the candidate's row after the handover has it FOR
    UPDATE, so it waits, re-reads the deactivated row and refuses; a lead never
    ends up owned by a person the handover just deactivated."""
    fresh = sessions()
    lead = await _lead(fresh, world, world.officer_b, "fresh-" + uuid.uuid4().hex[:6])
    await fresh.commit()
    held = asyncio.Event()

    async def assign(s: AsyncSession) -> str:
        await held.wait()
        await _as(s, world.admin)
        try:
            await leads_service.assign_lead(
                s, _caller(world), lead, LeadAssign(owner_user_id=world.officer_a))
        except Exception as exc:  # the refusal is the assertion
            await s.rollback()
            return type(exc).__name__ + ": " + str(getattr(exc, "fields", ""))
        await s.commit()
        return "assigned"

    a, b = sessions(), sessions()
    handover, assigned = await asyncio.gather(
        _handover(a, world, world.officer_a, world.officer_b, ready=held, hold=HOLD,
                  deactivate=True),
        assign(b),
    )
    assert handover.get("deactivated") is True, handover
    assert assigned.startswith("ValidationFailed"), assigned
    check = sessions()
    owner = (await check.execute(text("SELECT owner_user_id::text FROM lead WHERE id = :l"),
                                 {"l": lead})).scalar_one()
    active = (await check.execute(text("SELECT is_active FROM app_user WHERE id = :u"),
                                  {"u": world.officer_a})).scalar_one()
    await check.rollback()
    assert owner == world.officer_b and active is False


async def _run(s: AsyncSession, sql: str, params: dict, *, after: asyncio.Event | None,
               ready: asyncio.Event | None, hold: float) -> str:
    """One statement on one connection, ordered by the events like _handover."""
    if after is not None:
        await after.wait()
    try:
        await s.execute(text(sql), params)
    except DBAPIError as exc:
        await s.rollback()
        if ready is not None:
            ready.set()
        return "refused: " + str(exc.orig)[:200]
    if ready is not None:
        ready.set()
    await asyncio.sleep(hold)
    await s.commit()
    return "committed"


async def test_an_office_closing_and_a_person_created_into_it_never_both_win(
        sessions: Callable[[], AsyncSession], world: World) -> None:
    """A-9: the role-family trigger shares the office row, the close guard reads
    the people. Whichever holds the row first wins; the other waits on it, re-reads
    the committed state and is refused. Both orders."""
    office = sessions()
    org = (await office.execute(text(
        "INSERT INTO org_unit (name, role_level, parent_id) VALUES (:n, 1, :p) RETURNING id"),
        {"n": f"conc7_close_{uuid.uuid4().hex[:6]}", "p": world.org_unit})).scalar_one()
    role = (await office.execute(text("SELECT role_id FROM app_user WHERE id = :u"),
                                 {"u": world.officer_a})).scalar_one()
    await office.commit()
    insert = ("INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, "
              "org_unit_id) VALUES ('staff', :e, 'x', 'New', :r, :o) RETURNING id")
    close = "UPDATE org_unit SET deleted_at = now() WHERE id = :o RETURNING id"

    try:
        # order 1: the close holds the row; the create waits on its share lock, then
        # sees the office closed
        held = asyncio.Event()
        a, b = sessions(), sessions()
        got = await asyncio.gather(
            _run(a, close, {"o": org}, after=None, ready=held, hold=HOLD),
            _run(b, insert, {"e": f"conc7_n1_{uuid.uuid4().hex[:6]}@polysil.in", "r": role,
                             "o": org}, after=held, ready=None, hold=0),
        )
        assert got[0] == "committed" and "office is closed" in got[1], got
        reopen = sessions()
        await reopen.execute(text("UPDATE org_unit SET deleted_at = NULL WHERE id = :o"),
                             {"o": org})
        await reopen.commit()

        # order 2: the create holds the share lock; the close waits, then sees an
        # active person
        held = asyncio.Event()
        a, b = sessions(), sessions()
        got = await asyncio.gather(
            _run(a, insert, {"e": f"conc7_n2_{uuid.uuid4().hex[:6]}@polysil.in", "r": role,
                             "o": org}, after=None, ready=held, hold=HOLD),
            _run(b, close, {"o": org}, after=held, ready=None, hold=0),
        )
        assert got[0] == "committed" and "active users are anchored" in got[1], got
        check = sessions()
        bad = (await check.execute(text(
            "SELECT count(*) FROM app_user u JOIN org_unit o ON o.id = u.org_unit_id "
            "WHERE o.id = :o AND u.is_active AND o.deleted_at IS NOT NULL"),
            {"o": org})).scalar_one()
        await check.rollback()
        assert bad == 0
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM app_user WHERE org_unit_id = :o"), {"o": org})
        await c.execute(text("DELETE FROM org_unit WHERE id = :o"), {"o": org})
        await c.commit()


async def test_a_state_code_edit_and_the_first_lead_serialise_in_both_orders(
        sessions: Callable[[], AsyncSession], world: World) -> None:
    """Rule 15 under concurrency (cross-vendor P2-3). The lead path reads the state
    code through lead_state_code(), which shares the state row: an edit that
    arrives while the first number is being allocated waits and is then refused by
    the counter it finds; an edit that lands first makes the read wait and return
    the new code, so the number is issued under it."""
    setup = sessions()
    state = str((await setup.execute(text("SELECT parent_id FROM territory WHERE id = :d"),
                                     {"d": world.district})).scalar_one())
    old_code = (await setup.execute(text("SELECT code::text FROM territory WHERE id = :s"),
                                    {"s": state})).scalar_one()
    await setup.rollback()
    new_code = "Z" + uuid.uuid4().hex[:3].upper()
    fy = financial_year(datetime.now(UTC))

    async def allocate(s: AsyncSession, *, after: asyncio.Event | None,
                       ready: asyncio.Event | None, hold: float) -> tuple[str, str]:
        if after is not None:
            await after.wait()
        await _as(s, world.admin)
        code = (await s.execute(text("SELECT lead_state_code(CAST(:d AS uuid))"),
                                {"d": world.district})).scalar_one()
        number = (await s.execute(text("SELECT lead_allocate_inquiry_no(:c, :fy)"),
                                  {"c": code, "fy": fy})).scalar_one()
        if ready is not None:
            ready.set()
        await asyncio.sleep(hold)
        await s.commit()
        return code, number

    edit = "UPDATE territory SET code = :c WHERE id = :s"
    try:
        # order 1: the lead is being numbered; the edit waits, then meets the counter
        held = asyncio.Event()
        a, b = sessions(), sessions()
        (code, number), edited = await asyncio.gather(
            allocate(a, after=None, ready=held, hold=HOLD),
            _run(b, edit, {"c": new_code, "s": state}, after=held, ready=None, hold=0),
        )
        assert code == old_code and f"/{old_code}/" in number, (code, number)
        assert "numbered under this code" in edited, edited
        cleanup = sessions()
        await cleanup.execute(text("DELETE FROM inquiry_counter WHERE state_code = :c"),
                              {"c": old_code})
        await cleanup.commit()

        # order 2: the edit holds the row; the read waits, returns the new code, and
        # the number is issued under it
        held = asyncio.Event()
        a, b = sessions(), sessions()
        edited, (code, number) = await asyncio.gather(
            _run(a, edit, {"c": new_code, "s": state}, after=None, ready=held, hold=HOLD),
            allocate(b, after=held, ready=None, hold=0),
        )
        assert edited == "committed" and code == new_code and f"/{new_code}/" in number, \
            (edited, code, number)
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM inquiry_counter WHERE state_code IN (:a, :b)"),
                        {"a": old_code, "b": new_code})
        await c.execute(text(edit), {"c": old_code, "s": state})
        await c.commit()
