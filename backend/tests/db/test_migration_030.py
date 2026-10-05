"""Migration 030 (FS-021): field tracking's tables, executed as the roles that touch
them. The negatives are the point: a sibling office, another person's row, a
dealer, the board, and app_role against the purge."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db import test_migration_018 as m18

pytestmark = [pytest.mark.db, pytest.mark.rls]


async def _duty(db: AsyncSession, user: str, office: str, *, ended: bool = False) -> str:
    did = str(uuid.uuid4())
    await db.execute(text(
        "INSERT INTO duty_session (id, user_id, org_unit_id, device_id, started_at, ended_at, end_reason) "
        "VALUES (CAST(:d AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), 'device-0001', now() - interval '2 hours', "
        "CASE WHEN :e THEN now() END, CASE WHEN :e THEN 'user'::duty_end_reason END)"),
        {"d": did, "u": user, "o": office, "e": ended})
    return did


async def _point(db: AsyncSession, user: str, office: str, duty: str, age: str = "1 hour") -> str:
    pid = str(uuid.uuid4())
    await db.execute(text(
        "INSERT INTO location_point (id, user_id, org_unit_id, duty_id, device_id, recorded_at, lat, lng) "
        f"VALUES (CAST(:p AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), CAST(:d AS uuid), 'device-0001', now() - interval '{age}', 23.02, 72.57)"),
        {"p": pid, "u": user, "o": office, "d": duty})
    return pid


async def _count(db: AsyncSession, who: str, sql: str, params: dict[str, Any]) -> int:
    await m13._as(db, who)
    n = int((await db.execute(text(sql), params)).scalar_one())
    await m13._as_owner(db)
    return n


async def test_each_scope_reads_what_it_should_and_a_sibling_office_nothing(db: AsyncSession) -> None:
    w = await m18._world(db)
    da, db_ = await _duty(db, w.officer, w.a), await _duty(db, w.officer_b, w.b)
    pa, pb = await _point(db, w.officer, w.a, da), await _point(db, w.officer_b, w.b, db_)
    q = "SELECT count(*) FROM location_point WHERE id = ANY(CAST(:ids AS uuid[]))"
    ids = {"ids": [pa, pb]}
    assert await _count(db, w.officer, q, ids) == 1, "an officer reads their own only"
    assert await _count(db, w.officer_b, q, ids) == 1
    assert await _count(db, w.dm, q, ids) == 1, "a district manager reads their office, not the sibling"
    assert await _count(db, w.dm_b, q, ids) == 1
    assert await _count(db, w.admin, q, ids) == 2, "admin reads everyone"
    assert await _count(db, w.dealer, q, ids) == 0, "a dealer reads nothing"
    q2 = "SELECT count(*) FROM duty_session WHERE id = ANY(CAST(:ids AS uuid[]))"
    ids2 = {"ids": [da, db_]}
    assert await _count(db, w.dm, q2, ids2) == 1
    assert await _count(db, w.dealer, q2, ids2) == 0


async def test_nobody_writes_a_row_for_someone_else_at_any_scope(db: AsyncSession) -> None:
    """Review B-1: generated write branches check the office, not the person."""
    w = await m18._world(db)
    da = await _duty(db, w.officer, w.a)
    for who in (w.dm, w.admin):
        await m13._as(db, who)
        await m13._refused(db,
            "INSERT INTO location_point (id, user_id, org_unit_id, duty_id, device_id, recorded_at, lat, lng) "
            "VALUES (gen_random_uuid(), CAST(:u AS uuid), CAST(:o AS uuid), CAST(:d AS uuid), 'device-0001', now(), 1, 1)",
            {"u": w.officer, "o": w.a, "d": da}, "42501")
        await m13._refused(db,
            "INSERT INTO duty_session (id, user_id, org_unit_id, device_id, started_at) "
            "VALUES (gen_random_uuid(), CAST(:u AS uuid), CAST(:o AS uuid), 'device-0001', now())",
            {"u": w.officer, "o": w.a}, "42501")
        r = await db.execute(text("UPDATE duty_session SET last_point_at = now() WHERE id = CAST(:d AS uuid)"),
                             {"d": da})
        assert r.rowcount == 0, "a manager sees the session but may not change it"
        await m13._refused(db,
            "INSERT INTO visit (id, user_id, org_unit_id, place_name, checkin_at, checkin_lat, checkin_lng) "
            "VALUES (gen_random_uuid(), CAST(:u AS uuid), CAST(:o AS uuid), 'Farm', now(), 1, 1)",
            {"u": w.officer, "o": w.a}, "42501")
        await m13._as_owner(db)


async def test_points_are_never_updated_or_deleted_by_app_role(db: AsyncSession) -> None:
    w = await m18._world(db)
    pid = await _point(db, w.officer, w.a, await _duty(db, w.officer, w.a))
    await m13._as(db, w.officer)
    await m13._refused(db, "UPDATE location_point SET lat = 0 WHERE id = CAST(:p AS uuid)", {"p": pid}, "42501")
    await m13._refused(db, "DELETE FROM location_point WHERE id = CAST(:p AS uuid)", {"p": pid}, "42501")
    await m13._as_owner(db)


async def test_the_board_and_functional_roles_hold_no_tracking(db: AsyncSession) -> None:
    rows = (await db.execute(text(
        "SELECT DISTINCT r.code FROM role_permission rp JOIN role r ON r.id = rp.role_id "
        "WHERE rp.module = 'tracking' AND rp.deleted_at IS NULL ORDER BY 1"))).scalars().all()
    assert set(rows) <= {"field_officer", "district_manager", "state_manager", "regional_manager",
                         "admin_sales", "md_ceo"}, rows
    assert "board" not in rows and "account_manager" not in rows


async def test_the_view_log_is_written_by_readers_and_read_only_company_wide(db: AsyncSession) -> None:
    w = await m18._world(db)
    await m13._as(db, w.dm)
    await db.execute(text(
        "INSERT INTO tracking_view_log (viewer_id, subject_user_id, what) VALUES (CAST(:me AS uuid), CAST(:s AS uuid), 'route')"),
        {"me": w.dm, "s": w.officer})
    assert (await db.execute(text("SELECT count(*) FROM tracking_view_log"))).scalar_one() == 0, \
        "a manager writes the log but cannot read it"
    await m13._refused(db, "INSERT INTO tracking_view_log (viewer_id, subject_user_id, what) "
                           "VALUES (CAST(:o AS uuid), CAST(:s AS uuid), 'route')",
                       {"o": w.admin, "s": w.officer}, "42501")
    await m13._as_owner(db)
    assert await _count(db, w.admin, "SELECT count(*) FROM tracking_view_log WHERE viewer_id = CAST(:v AS uuid)",
                        {"v": w.dm}) == 1
    await m13._as(db, w.officer)
    await m13._refused(db, "INSERT INTO tracking_view_log (viewer_id, what) VALUES (CAST(:me AS uuid), 'team')",
                       {"me": w.dealer}, "42501")
    await m13._as_owner(db)


@pytest.mark.parametrize("call", ["SELECT * FROM tracking_open_duties()",
                                  "SELECT tracking_auto_end(gen_random_uuid(), now())",
                                  "SELECT visit_auto_close(now())",
                                  "SELECT location_point_purge(10)"])
async def test_the_worker_definers_refuse_a_person(db: AsyncSession, call: str) -> None:
    w = await m18._world(db)
    await m13._as(db, w.admin)
    await m13._refused(db, call, {}, "42501")
    await m13._as_owner(db)


@pytest.mark.parametrize("sig", ["tracking_open_duties()", "tracking_auto_end(uuid, timestamptz)",
                                 "visit_auto_close(timestamptz)", "location_point_purge(int)",
                                 "duty_end_on_deactivate()"])
async def test_every_new_definer_is_pinned_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
    assert row[0] is True and any(c.startswith("search_path=") for c in row[1]) and row[2] is False


async def test_deactivating_a_user_ends_their_duty(db: AsyncSession) -> None:
    w = await m18._world(db)
    da = await _duty(db, w.officer, w.a)
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = CAST(:u AS uuid)"), {"u": w.officer})
    row = (await db.execute(text("SELECT ended_at IS NOT NULL, end_reason::text FROM duty_session WHERE id = CAST(:d AS uuid)"),
                            {"d": da})).one()
    assert tuple(row) == (True, "deactivated")
    n = (await db.execute(text("SELECT count(*) FROM activity_event WHERE entity_id = CAST(:d AS uuid) AND kind = 'duty.ended'"),
                          {"d": da})).scalar_one()
    assert n == 1


async def test_the_purge_deletes_old_points_and_leaves_the_latest_marker(db: AsyncSession) -> None:
    w = await m18._world(db)
    da = await _duty(db, w.officer, w.a)
    old = await _point(db, w.officer, w.a, da, age="200 days")
    fresh = await _point(db, w.officer, w.a, da, age="1 hour")
    await db.execute(text(
        "INSERT INTO tracking_latest (user_id, org_unit_id, duty_id, recorded_at, lat, lng) "
        "VALUES (CAST(:u AS uuid), CAST(:o AS uuid), CAST(:d AS uuid), now() - interval '200 days', 1, 1) "
        "ON CONFLICT (user_id) DO NOTHING"), {"u": w.officer, "o": w.a, "d": da})
    await db.execute(text("SELECT set_config('app.current_user_id', '26809c63-290b-5bd9-9d6a-a717dc0b32e3', true)"))
    while (await db.execute(text("SELECT location_point_purge(50000)"))).scalar_one() == 50000:
        pass
    left = set((await db.execute(text("SELECT id::text FROM location_point WHERE id = ANY(CAST(:i AS uuid[]))"),
                                 {"i": [old, fresh]})).scalars().all())
    assert left == {fresh}
    assert (await db.execute(text("SELECT count(*) FROM tracking_latest WHERE user_id = CAST(:u AS uuid)"),
                             {"u": w.officer})).scalar_one() == 1


async def test_visit_events_reach_staff_on_the_lead_timeline_but_not_a_dealer(db: AsyncSession) -> None:
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    await db.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) WHERE id = CAST(:l AS uuid)"),
                     {"p": w.partner, "l": lead})
    vid = str(uuid.uuid4())
    await db.execute(text(
        "INSERT INTO visit (id, user_id, org_unit_id, lead_id, checkin_at, checkin_lat, checkin_lng) "
        "VALUES (CAST(:v AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), CAST(:l AS uuid), now(), 23, 72)"),
        {"v": vid, "u": w.officer, "o": w.a, "l": lead})
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('visit', CAST(:v AS uuid), CAST(:l AS uuid), 'visit.checked_in', CAST(:u AS uuid), '{}')"),
        {"v": vid, "l": lead, "u": w.officer})
    q = "SELECT count(*) FROM lead_timeline(CAST(:l AS uuid), NULL, NULL, 100) WHERE kind = 'visit.checked_in'"
    assert await _count(db, w.dm, q, {"l": lead}) == 1
    assert await _count(db, w.dealer, q, {"l": lead}) == 0, "a dealer never sees a visit"


async def test_a_sibling_office_reads_no_visit_latest_or_consent(db: AsyncSession) -> None:
    """Code review F-4: the negatives beyond points and duty."""
    w = await m18._world(db)
    vid = str(uuid.uuid4())
    await db.execute(text(
        "INSERT INTO visit (id, user_id, org_unit_id, place_name, checkin_at, checkin_lat, checkin_lng) "
        "VALUES (CAST(:v AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), 'Farm', now(), 23, 72)"),
        {"v": vid, "u": w.officer, "o": w.a})
    await db.execute(text(
        "INSERT INTO tracking_latest (user_id, org_unit_id, recorded_at, lat, lng) "
        "VALUES (CAST(:u AS uuid), CAST(:o AS uuid), now(), 23, 72) ON CONFLICT (user_id) DO NOTHING"),
        {"u": w.officer, "o": w.a})
    await db.execute(text(
        "INSERT INTO tracking_consent (user_id, org_unit_id, version, accepted) "
        "VALUES (CAST(:u AS uuid), CAST(:o AS uuid), 'v1', true)"), {"u": w.officer, "o": w.a})
    checks = {"SELECT count(*) FROM visit WHERE id = CAST(:x AS uuid)": vid,
              "SELECT count(*) FROM tracking_latest WHERE user_id = CAST(:x AS uuid)": w.officer,
              "SELECT count(*) FROM tracking_consent WHERE user_id = CAST(:x AS uuid)": w.officer}
    for sql, x in checks.items():
        assert await _count(db, w.dm, sql, {"x": x}) >= 1, sql
        assert await _count(db, w.dm_b, sql, {"x": x}) == 0, sql
        assert await _count(db, w.dealer, sql, {"x": x}) == 0, sql


async def test_the_latest_marker_only_moves_forward(db: AsyncSession) -> None:
    """Review EC-15: an older batch arriving late never moves the marker back."""
    w = await m18._world(db)
    await m13._as(db, w.officer)
    upsert = ("INSERT INTO tracking_latest (user_id, org_unit_id, recorded_at, lat, lng) "
              "VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :at, :lat, 72) ON CONFLICT (user_id) DO UPDATE SET "
              "recorded_at = excluded.recorded_at, lat = excluded.lat WHERE excluded.recorded_at > tracking_latest.recorded_at")
    import datetime as dt
    now = dt.datetime.now(dt.UTC)
    await db.execute(text(upsert), {"u": w.officer, "o": w.a, "at": now, "lat": 23.5})
    await db.execute(text(upsert), {"u": w.officer, "o": w.a, "at": now - dt.timedelta(hours=1), "lat": 22.0})
    lat = (await db.execute(text("SELECT lat FROM tracking_latest WHERE user_id = CAST(:u AS uuid)"),
                            {"u": w.officer})).scalar_one()
    await m13._as_owner(db)
    assert float(lat) == 23.5


async def test_only_people_who_track_give_consent(db: AsyncSession) -> None:
    """Code review F-6: a dealer cannot write a consent row."""
    w = await m18._world(db)
    await m13._as(db, w.dealer)
    await m13._refused(db, "INSERT INTO tracking_consent (user_id, version, accepted) VALUES (CAST(:u AS uuid), 'v1', true)",
                       {"u": w.dealer}, "42501")
    await m13._as_owner(db)
