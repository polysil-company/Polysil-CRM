"""FS-021's worker jobs against the database: an idle duty ends at its last point,
a busy one stays open, a day-old visit closes itself (review B-4, B-8)."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import worker.jobs.tracking as job

pytestmark = pytest.mark.db

Sessions = Callable[[], AsyncSession]


async def _person(s: AsyncSession) -> str:
    tag = uuid.uuid4().hex[:8]
    office = str((await s.execute(text(
        "INSERT INTO org_unit (name, role_level) VALUES (:n, 1) RETURNING id"), {"n": f"trk_{tag}"})).scalar_one())
    return str((await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, 'x', 'Tracking Job', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'field_officer' "
        "RETURNING id"), {"e": f"trk_{tag}@jobs.in", "o": office})).scalar_one())


async def _forget(s: AsyncSession, people: list[str]) -> None:
    """Code review F-7: the people and their rows go, so runs do not pile up."""
    p = {"p": people}
    for stmt in ("DELETE FROM activity_event WHERE entity_id IN (SELECT id FROM duty_session WHERE user_id = ANY(CAST(:p AS uuid[]))) "
                 "OR entity_id IN (SELECT id FROM visit WHERE user_id = ANY(CAST(:p AS uuid[])))",
                 "DELETE FROM visit WHERE user_id = ANY(CAST(:p AS uuid[]))",
                 "DELETE FROM duty_session WHERE user_id = ANY(CAST(:p AS uuid[]))"):
        await s.execute(text(stmt), p)
    offices = (await s.execute(text("SELECT org_unit_id FROM app_user WHERE id = ANY(CAST(:p AS uuid[]))"), p)).scalars().all()
    await s.execute(text("DELETE FROM app_user WHERE id = ANY(CAST(:p AS uuid[]))"), p)
    await s.execute(text("DELETE FROM org_unit WHERE id = ANY(CAST(:o AS uuid[]))"), {"o": list(offices)})
    await s.commit()


async def _duty(s: AsyncSession, user: str, started: dt.datetime, last: dt.datetime | None) -> str:
    did = str(uuid.uuid4())
    await s.execute(text(
        "INSERT INTO duty_session (id, user_id, device_id, started_at, last_point_at) "
        "VALUES (CAST(:d AS uuid), CAST(:u AS uuid), 'device-0001', :s, :l)"),
        {"d": did, "u": user, "s": started, "l": last})
    return did


async def test_an_idle_duty_ends_at_its_last_point_and_a_busy_one_stays(sessions: Sessions) -> None:
    s = sessions()
    # a Monday in IST; hours Mon to Sat 09:00 to 19:00 (the seeded policy)
    start = dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    quiet, busy = await _person(s), await _person(s)
    idle = await _duty(s, quiet, start, start.replace(hour=20, minute=10))
    working = await _duty(s, busy, start, start.replace(hour=20, minute=55))
    await s.commit()
    try:
        await job.tracking_auto_end({}, now=start.replace(hour=21), only=frozenset({idle, working}))
        rows = dict((await s.execute(text(
            "SELECT id::text, (ended_at, end_reason::text) FROM duty_session WHERE id = ANY(CAST(:i AS uuid[]))"),
            {"i": [idle, working]})).all())
        assert rows[idle] == (start.replace(hour=20, minute=10), "auto"), rows
        assert rows[working] == (None, None), "evening work that keeps sending is not cut off"
        events = (await s.execute(text(
            "SELECT count(*) FROM activity_event WHERE entity_id = CAST(:d AS uuid) AND kind = 'duty.ended'"),
            {"d": idle})).scalar_one()
        assert events == 1
    finally:
        await s.rollback()
        await _forget(s, [quiet, busy])
        await s.close()


async def test_a_day_old_visit_closes_itself(sessions: Sessions) -> None:
    s = sessions()
    user = await _person(s)
    vid = str(uuid.uuid4())
    checkin = dt.datetime.now(dt.UTC) - dt.timedelta(hours=13)
    await s.execute(text(
        "INSERT INTO visit (id, user_id, place_name, checkin_at, checkin_lat, checkin_lng) "
        "VALUES (CAST(:v AS uuid), CAST(:u AS uuid), 'Mandi', :c, 23, 72)"), {"v": vid, "u": user, "c": checkin})
    await s.commit()
    try:
        assert await job.visit_auto_close({}) >= 1
        row = (await s.execute(text("SELECT checkout_at, auto_closed FROM visit WHERE id = CAST(:v AS uuid)"),
                               {"v": vid})).one()
        assert row.auto_closed and row.checkout_at == checkin + dt.timedelta(hours=12)
    finally:
        await s.rollback()
        await _forget(s, [user])
        await s.close()
