"""Migration 018 (FS-014): tasks, the planner, meetings and minutes, executed as
the roles that call it. Two sibling offices in one district, so every scope has a
negative case: office A's manager must not see office B's tasks."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_012 as m12
from tests.db import test_migration_013 as m13

pytestmark = [pytest.mark.db, pytest.mark.rls]

GRANTED = ["task_link_visible_as(uuid,uuid,uuid,uuid)", "user_open_tasks(uuid)",
           "user_tasks_handover(uuid,uuid)"]
INTERNAL = ["task_visible(uuid)", "minutes_visible(uuid)", "task_follow_office()"]
SYSTEM_USER = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"
PRINCIPAL = "3f962ae5-f0d3-5583-91b5-5cea037139fc"


@dataclass
class World:
    district: str
    a: str          # office A
    b: str          # office B, a sibling: neither reaches the other
    officer: str    # field officer, A
    dm: str         # district manager, A
    officer_b: str
    dm_b: str
    admin: str      # admin_sales, global
    dealer: str     # a portal user
    partner: str    # the dealer's channel_partner


async def _world(db: AsyncSession) -> World:
    tag = uuid.uuid4().hex[:8]
    district = str((await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"m018_district_{tag}"})).scalar_one())
    offices = [str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"m018_office_{x}_{tag}", "t": district})).scalar_one()) for x in "ab"]
    a, b = offices
    officer = await m13._user(db, "field_officer", a, tag + "a")
    dm = await m13._user(db, "district_manager", a, tag + "a")
    officer_b = await m13._user(db, "field_officer", b, tag + "b")
    dm_b = await m13._user(db, "district_manager", b, tag + "b")
    admin = await m13._user(db, "admin_sales", a, tag + "a")
    partner = str((await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('distributor', :c, 'M018 Distributor', :t, 'distributor') RETURNING id"),
        {"c": f"M018{tag}", "t": district})).scalar_one())
    dealer = str((await db.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "SELECT 'partner_user', :m, 'M018 Partner', r.id, CAST(:p AS uuid) FROM role r "
        "WHERE r.code = 'distributor' RETURNING id"),
        {"m": "9197" + f"{uuid.uuid4().int % 10**8:08d}", "p": partner})).scalar_one())
    return World(district, a, b, officer, dm, officer_b, dm_b, admin, dealer, partner)


async def _lead(db: AsyncSession, w: World, owner: str, office: str | None = None) -> str:
    ids = SimpleNamespace(territory_id=w.district, org_unit_id=office or w.a)
    return await m12._lead(db, ids, owner_user_id=owner)  # type: ignore[arg-type]


async def _task(db: AsyncSession, *, to: str, by: str, office: str, lead: str | None = None,
                status: str = "open", task_type: str = "call") -> str:
    """As the table owner."""
    done = status == "done"
    return str((await db.execute(text(
        "INSERT INTO task (title, task_type, status, due_at, assigned_to, assigned_by, "
        "owner_org_unit_id, lead_id, meeting_type_id, completed_at, outcome, cancel_reason) "
        "VALUES ('Call the farmer', CAST(:tt AS task_type), CAST(:st AS task_status), now(), "
        "CAST(:to AS uuid), CAST(:by AS uuid), CAST(:ou AS uuid), CAST(:l AS uuid), "
        "CASE WHEN :tt = 'meeting' AND CAST(:l AS uuid) IS NOT NULL "
        "     THEN (SELECT id FROM meeting_type WHERE code = 'by_call') END, "
        "CASE WHEN :done THEN now() END, CASE WHEN :done THEN 'Spoke' END, "
        "CASE WHEN :st = 'cancelled' THEN 'Not needed' END) RETURNING id"),
        {"tt": task_type, "st": status, "to": to, "by": by, "ou": office, "l": lead,
         "done": done})).scalar_one())


async def _seen(db: AsyncSession, who: str, ids: list[str]) -> set[str]:
    await m13._as(db, who)
    rows = (await db.execute(text("SELECT id FROM task WHERE id = ANY(CAST(:i AS uuid[]))"),
                             {"i": ids})).all()
    await m13._as_owner(db)
    return {str(r.id) for r in rows}


async def _scalar(db: AsyncSession, who: str, sql: str, params: dict[str, Any]) -> Any:
    await m13._as(db, who)
    value = (await db.execute(text(sql), params)).scalar_one()
    await m13._as_owner(db)
    return value


# ── the surface ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sig", GRANTED + INTERNAL)
async def test_every_new_definer_is_pinned_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
    assert row[0], f"{sig} is SECURITY DEFINER"
    assert "search_path=public, pg_temp" in (row[1] or []), row[1]
    assert not row[2], f"{sig} is not PUBLIC-executable"


@pytest.mark.parametrize("sig", INTERNAL)
async def test_the_internal_functions_are_not_granted_to_app_role(db: AsyncSession, sig: str) -> None:
    held = (await db.execute(text("SELECT has_function_privilege('app_role', :s, 'EXECUTE')"),
                             {"s": sig})).scalar_one()
    assert not held


async def test_app_role_cannot_delete_a_task_or_minutes(db: AsyncSession) -> None:
    for table in ("task", "meeting_minutes"):
        held = (await db.execute(text("SELECT has_table_privilege('app_role', :t, 'DELETE')"),
                                 {"t": table})).scalar_one()
        assert not held, f"{table}: cancelled, never deleted"


# ── who sees which task ──────────────────────────────────────────────────────

async def test_each_scope_sees_what_it_should_and_nothing_else(db: AsyncSession) -> None:
    w = await _world(db)
    mine = await _task(db, to=w.officer, by=w.officer, office=w.a)
    managers = await _task(db, to=w.dm, by=w.dm, office=w.a)
    theirs = await _task(db, to=w.officer_b, by=w.dm_b, office=w.b)
    every = [mine, managers, theirs]
    assert await _seen(db, w.officer, every) == {mine}, "own: only what is assigned to me"
    assert await _seen(db, w.dm, every) == {mine, managers}, "office A, never office B"
    assert await _seen(db, w.dm_b, every) == {theirs}
    assert await _seen(db, w.admin, every) == set(every)
    assert await _seen(db, w.dealer, every) == set(), "portal roles hold no tasks"


async def test_an_officer_cannot_insert_a_task_for_someone_else(db: AsyncSession) -> None:
    w = await _world(db)
    await m13._as(db, w.officer)
    await m13._refused(db,
        "INSERT INTO task (title, task_type, due_at, assigned_to, assigned_by, owner_org_unit_id) "
        "VALUES ('x', 'call', now(), CAST(:to AS uuid), CAST(:me AS uuid), CAST(:ou AS uuid))",
        {"to": w.dm, "me": w.officer, "ou": w.a}, "42501")
    await m13._as_owner(db)


async def test_a_manager_cannot_move_a_task_into_another_office(db: AsyncSession) -> None:
    w = await _world(db)
    t = await _task(db, to=w.officer, by=w.dm, office=w.a)
    await m13._as(db, w.dm)
    await m13._refused(db, "UPDATE task SET owner_org_unit_id = CAST(:b AS uuid) WHERE id = CAST(:t AS uuid)",
                       {"b": w.b, "t": t}, "42501")
    await m13._as_owner(db)


@pytest.mark.parametrize(("sets", "name"), [
    ("lead_id = CAST(:l AS uuid), partner_id = CAST(:p AS uuid)", "ck_task_one_link"),
    ("gift_shown = true", "ck_task_gift"),
    ("status = 'done'", "ck_task_done"),
    ("status = 'cancelled'", "ck_task_cancel_reason"),
])
async def test_the_table_checks_hold(db: AsyncSession, sets: str, name: str) -> None:
    w = await _world(db)
    lead = await _lead(db, w, w.officer)
    t = await _task(db, to=w.officer, by=w.officer, office=w.a)
    message = await m13._refused(db, f"UPDATE task SET {sets} WHERE id = CAST(:t AS uuid)",
                                 {"t": t, "l": lead, "p": w.partner}, "23514")
    assert name in message


async def test_a_meeting_on_a_lead_needs_its_type_and_nothing_else_takes_one(db: AsyncSession) -> None:
    w = await _world(db)
    lead = await _lead(db, w, w.officer)
    message = await m13._refused(db,
        "INSERT INTO task (title, task_type, due_at, assigned_to, assigned_by, owner_org_unit_id, lead_id) "
        "VALUES ('Meet', 'meeting', now(), CAST(:o AS uuid), CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:l AS uuid))",
        {"o": w.officer, "ou": w.a, "l": lead}, "23514")
    assert "ck_task_meeting_type" in message
    call = await _task(db, to=w.officer, by=w.officer, office=w.a, lead=lead)
    message = await m13._refused(db,
        "UPDATE task SET meeting_type_id = (SELECT id FROM meeting_type WHERE code = 'by_call') "
        "WHERE id = CAST(:t AS uuid)", {"t": call}, "23514")
    assert "ck_task_meeting_type" in message


# ── assigning, and the link as the assignee sees it ─────────────────────────

async def test_who_a_manager_may_assign_to(db: AsyncSession) -> None:
    w = await _world(db)
    sql = "SELECT authz_user_assignable('tasks', CAST(:u AS uuid))"
    assert await _scalar(db, w.dm, sql, {"u": w.officer})
    assert not await _scalar(db, w.dm, sql, {"u": w.officer_b}), "not another office's officer"
    assert not await _scalar(db, w.admin, sql, {"u": SYSTEM_USER}), "never the System user"
    assert not await _scalar(db, w.admin, sql, {"u": PRINCIPAL}), "never the principal"
    assert not await _scalar(db, w.admin, sql, {"u": w.dealer}), "never a portal user"
    listed = await _scalar(db, w.admin,
                           "SELECT array_agg(id) FROM staff_directory('tasks')", {})
    assert SYSTEM_USER not in {str(x) for x in listed or []}


async def test_the_link_is_checked_as_the_assignee_and_the_claim_is_restored(db: AsyncSession) -> None:
    w = await _world(db)
    own_lead = await _lead(db, w, w.officer)
    other_lead = await _lead(db, w, w.dm)
    sql = "SELECT task_link_visible_as(CAST(:u AS uuid), CAST(:l AS uuid), NULL, NULL)"
    await m13._as(db, w.dm)
    assert (await db.execute(text(sql), {"u": w.officer, "l": own_lead})).scalar_one()
    assert not (await db.execute(text(sql), {"u": w.officer, "l": other_lead})).scalar_one(), \
        "the manager sees it; the officer does not"
    me = (await db.execute(text("SELECT app_current_user_id()"))).scalar_one()
    assert str(me) == w.dm, "the claim is back to the caller"
    await m13._refused(db, sql, {"u": w.officer_b, "l": own_lead}, "42501")
    await m13._as_owner(db)


# ── the lead timeline, minutes and names ─────────────────────────────────────

async def _event(db: AsyncSession, entity_type: str, entity: str, lead: str, actor: str) -> None:
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES (:et, CAST(:e AS uuid), CAST(:l AS uuid), :k, CAST(:a AS uuid), '{}')"),
        {"et": entity_type, "e": entity, "l": lead, "k": f"{entity_type}.created", "a": actor})


async def test_the_timeline_hides_a_task_the_reader_cannot_see(db: AsyncSession) -> None:
    w = await _world(db)
    lead = await _lead(db, w, w.officer)
    mine = await _task(db, to=w.officer, by=w.officer, office=w.a, lead=lead)
    managers = await _task(db, to=w.dm, by=w.dm, office=w.a, lead=lead)
    await _event(db, "task", mine, lead, w.officer)
    await _event(db, "task", managers, lead, w.dm)
    await m13._as(db, w.officer)
    shown = {str(r.entity_id) for r in (await db.execute(text(
        "SELECT entity_id FROM lead_timeline(CAST(:l AS uuid), NULL, NULL, 100) "
        "WHERE entity_type = 'task'"), {"l": lead})).all()}
    await m13._as_owner(db)
    assert shown == {mine}


async def test_minutes_are_for_staff_who_see_the_lead(db: AsyncSession) -> None:
    w = await _world(db)
    lead = await _lead(db, w, w.officer)
    insert = ("INSERT INTO meeting_minutes (lead_id, held_at, notes, created_by) "
              "VALUES (CAST(:l AS uuid), now(), 'Met', CAST(:me AS uuid)) RETURNING id")
    await m13._as(db, w.officer)
    minutes = str((await db.execute(text(insert), {"l": lead, "me": w.officer})).scalar_one())
    await m13._as(db, w.dm_b)
    await m13._refused(db, insert, {"l": lead, "me": w.dm_b}, "42501")
    await m13._as_owner(db)
    sql = "SELECT count(*) FROM meeting_minutes WHERE id = CAST(:m AS uuid)"
    assert await _scalar(db, w.dm, sql, {"m": minutes}) == 1
    assert await _scalar(db, w.dm_b, sql, {"m": minutes}) == 0, "not another office's lead"
    assert await _scalar(db, w.dealer, sql, {"m": minutes}) == 0, "minutes are internal"


async def test_the_people_on_a_task_are_named_for_whoever_sees_it(db: AsyncSession) -> None:
    w = await _world(db)
    await _task(db, to=w.officer, by=w.admin, office=w.a)
    sql = ("SELECT count(*) FROM people_names(CAST(:ids AS uuid[])) WHERE full_name IS NOT NULL "
           "AND id = CAST(:admin AS uuid)")
    assert await _scalar(db, w.officer, sql, {"ids": [w.admin], "admin": w.admin}) == 1


# ── merging and people leaving ───────────────────────────────────────────────

async def test_a_merge_moves_the_tasks_and_minutes_to_the_survivor(db: AsyncSession) -> None:
    w = await _world(db)
    loser, survivor = await _lead(db, w, w.officer), await _lead(db, w, w.officer)
    t = await _task(db, to=w.officer, by=w.officer, office=w.a, lead=loser)
    m = str((await db.execute(text(
        "INSERT INTO meeting_minutes (lead_id, held_at, notes, created_by) "
        "VALUES (CAST(:l AS uuid), now(), 'Met', CAST(:o AS uuid)) RETURNING id"),
        {"l": loser, "o": w.officer})).scalar_one())
    await m13._as(db, w.dm)
    await db.execute(text("SELECT lead_merge(CAST(:a AS uuid), CAST(:b AS uuid))"),
                     {"a": loser, "b": survivor})
    await m13._as_owner(db)
    moved = (await db.execute(text(
        "SELECT (SELECT lead_id FROM task WHERE id = CAST(:t AS uuid)), "
        "(SELECT lead_id FROM meeting_minutes WHERE id = CAST(:m AS uuid))"), {"t": t, "m": m})).one()
    assert [str(x) for x in moved] == [survivor, survivor]


async def test_an_office_move_takes_the_open_tasks_and_leaves_the_done_ones(db: AsyncSession) -> None:
    w = await _world(db)
    open_ = await _task(db, to=w.officer, by=w.dm, office=w.a)
    done = await _task(db, to=w.officer, by=w.dm, office=w.a, status="done")
    await m13._as(db, w.admin)       # as patch_user runs it, not as the table owner
    moved = await db.execute(text(
        "UPDATE app_user SET org_unit_id = CAST(:b AS uuid) WHERE id = CAST(:u AS uuid)"),
        {"b": w.b, "u": w.officer})
    assert moved.rowcount == 1
    await m13._as_owner(db)
    events = (await db.execute(text(
        "SELECT entity_id::text, actor_id::text, payload->>'previous_org_unit_id' FROM activity_event "
        "WHERE kind = 'task.rehomed' AND entity_id IN (CAST(:o AS uuid), CAST(:d AS uuid))"),
        {"o": open_, "d": done})).all()
    assert [tuple(e) for e in events] == [(open_, w.admin, w.a)], "one event, on the open task"
    rows = dict((await db.execute(text(
        "SELECT id::text, owner_org_unit_id::text FROM task WHERE id IN (CAST(:o AS uuid), CAST(:d AS uuid))"),
        {"o": open_, "d": done})).all())
    assert rows == {open_: w.b, done: w.a}
    assert await _seen(db, w.dm_b, [open_, done]) == {open_}, "the new manager sees it"
    assert await _seen(db, w.dm, [open_, done]) == {done}, "the old one keeps the history only"


async def test_the_handover_moves_every_open_task_and_says_so(db: AsyncSession) -> None:
    w = await _world(db)
    lead = await _lead(db, w, w.officer)
    moving = [await _task(db, to=w.officer, by=w.dm, office=w.a, lead=lead) for _ in range(2)]
    done = await _task(db, to=w.officer, by=w.dm, office=w.a, status="done")
    count = "SELECT user_open_tasks(CAST(:u AS uuid))"
    assert await _scalar(db, w.admin, count, {"u": w.officer}) == 2
    moved = await _scalar(db, w.admin, "SELECT user_tasks_handover(CAST(:f AS uuid), CAST(:t AS uuid))",
                          {"f": w.officer, "t": w.officer_b})
    assert moved == 2
    assert await _scalar(db, w.admin, count, {"u": w.officer}) == 0
    rows = (await db.execute(text(
        "SELECT assigned_to::text, owner_org_unit_id::text FROM task WHERE id = ANY(CAST(:i AS uuid[]))"),
        {"i": moving})).all()
    assert {tuple(r) for r in rows} == {(w.officer_b, w.b)}, "the receiver and their office"
    assert (await db.execute(text("SELECT assigned_to::text FROM task WHERE id = CAST(:d AS uuid)"),
                             {"d": done})).scalar_one() == w.officer
    events = (await db.execute(text(
        "SELECT count(*) FROM activity_event WHERE kind = 'task.reassigned' "
        "AND entity_id = ANY(CAST(:i AS uuid[])) AND payload->>'handover' = 'true' "
        "AND lead_id = CAST(:l AS uuid)"), {"i": moving, "l": lead})).scalar_one()
    assert events == 2


async def test_only_a_users_editor_moves_or_counts_someone_elses_tasks(db: AsyncSession) -> None:
    w = await _world(db)
    await _task(db, to=w.officer, by=w.dm, office=w.a)
    await m13._as(db, w.dm)
    await m13._refused(db, "SELECT user_tasks_handover(CAST(:f AS uuid), CAST(:t AS uuid))",
                       {"f": w.officer, "t": w.dm}, "42501")
    await m13._as(db, w.officer)
    await m13._refused(db, "SELECT user_open_tasks(CAST(:u AS uuid))", {"u": w.dm}, "42501")
    await m13._as_owner(db)


async def test_the_handover_refuses_a_receiver_who_is_not_active_staff(db: AsyncSession) -> None:
    w = await _world(db)
    await _task(db, to=w.officer, by=w.dm, office=w.a)
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = CAST(:u AS uuid)"),
                     {"u": w.officer_b})
    await m13._as(db, w.admin)
    for to in (w.officer_b, w.dealer):
        await m13._refused(db, "SELECT user_tasks_handover(CAST(:f AS uuid), CAST(:t AS uuid))",
                           {"f": w.officer, "t": to}, "42501")
    await m13._as_owner(db)


# ── the pasted literals are what the generator emits (ISS-071) ───────────────

def _norm(s: str) -> str:
    return " ".join(s.split())


def test_the_pasted_task_sql_matches_the_generator() -> None:
    from api.authz.modules import SPECS
    from api.authz.policy_sql import guard_sql, indexes_for, parent_guard_ddl, policies_for
    from tests.db.migration_grants import _load
    m = _load("018_tasks_planner")
    assert m is not None
    spec = SPECS["tasks"]
    assert [_norm(x) for x in policies_for(spec)] == [_norm(x) for x in m.TASK_POLICIES]
    assert [_norm(x) for x in indexes_for(spec)] == [_norm(x) for x in m.GENERATED_INDEXES]
    assert [_norm(x) for x in parent_guard_ddl(spec)] == [_norm(x) for x in m.PARENT_GUARD]
    body = next(f for f in m.FUNCTIONS if "FUNCTION task_visible" in f)
    assert _norm(guard_sql(spec)) in _norm(body)



# ── code review F-5, F-6 and the missing negatives ───────────────────────────

async def test_a_manager_cannot_update_another_offices_task(db: AsyncSession) -> None:
    w = await _world(db)
    theirs = await _task(db, to=w.officer_b, by=w.dm_b, office=w.b)
    await m13._as(db, w.dm)
    r = await db.execute(text("UPDATE task SET notes = 'x' WHERE id = CAST(:t AS uuid)"), {"t": theirs})
    await m13._as_owner(db)
    assert r.rowcount == 0, "the UPDATE policy's USING, not only its CHECK"


async def test_no_shared_task_no_name(db: AsyncSession) -> None:
    w = await _world(db)
    await _task(db, to=w.officer, by=w.admin, office=w.a)
    sql = ("SELECT full_name FROM people_names(CAST(:ids AS uuid[])) WHERE id = CAST(:u AS uuid)")
    named = await _scalar(db, w.officer_b, f"SELECT ({sql})", {"ids": [w.admin], "u": w.admin})
    assert named is None, "another office's officer shares no task with the admin"


async def test_each_task_column_has_one_index_and_the_people_lookups_have_theirs(
        db: AsyncSession) -> None:
    defs = [r[0] for r in (await db.execute(text(
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'task'"))).all()]
    for column in ("partner_id", "sales_order_id", "assigned_by", "completed_by"):
        single = [d for d in defs if d.split(" USING btree ")[1].startswith(f"({column})")]
        assert len(single) == 1, (column, single)
