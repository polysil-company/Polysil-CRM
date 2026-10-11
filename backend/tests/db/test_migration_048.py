"""Migration 048 (FS-028): holidays in the working hours, the holiday definers, and
the escalation sweep with its recipients, executed as the roles that touch them."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.domain import complaints as domain
from tests.db import test_migration_013 as m13
from tests.db import test_migration_019 as m19

pytestmark = [pytest.mark.db, pytest.mark.rls]

SWEEP = "SELECT complaint_escalate_due(now() + interval '30 days', 1000)"


async def _holiday(db: AsyncSession, day: dt.date, w: m19.World) -> None:
    """As the table owner: the definers refuse past days, a test needs any day."""
    await db.execute(text("INSERT INTO holiday (day, name, created_by) VALUES (:d, 'Test', CAST(:u AS uuid))"),
                     {"d": day, "u": w.admin})


async def _sweep(db: AsyncSession) -> int:
    await m13._as(db, get_settings().system_user_id)
    n = int((await db.execute(text(SWEEP))).scalar_one())
    await m13._as_owner(db)
    return n


async def _mode(db: AsyncSession, mode: str) -> None:
    await db.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = 'complaint_escalation'"),
                     {"v": json.dumps(mode)})


async def _told(db: AsyncSession, cid: str, target: str) -> set[str]:
    return {str(r) for r in (await db.execute(text(
        "SELECT n.recipient_id FROM notification n JOIN activity_event e ON e.id = n.event_id "
        "WHERE e.entity_id = CAST(:c AS uuid) AND e.kind = 'complaint.escalated' AND e.payload ->> 'target' = :t"),
        {"c": cid, "t": target})).scalars()}


async def test_a_holiday_is_skipped_like_a_sunday_in_both_twins(db: AsyncSession) -> None:
    w = await m19._world(db)
    await _holiday(db, dt.date(2026, 10, 5), w)            # a Monday
    start = dt.datetime(2026, 10, 3, 18, 0, tzinfo=domain.IST)   # Saturday, half an hour to close
    sql = (await db.execute(text("SELECT complaint_add_working_hours(:s, 4)"), {"s": start})).scalar_one()
    holidays = frozenset((await db.execute(text("SELECT day FROM holiday"))).scalars())
    assert sql == domain.add_working_hours(start, 4, holidays)
    assert sql.astimezone(domain.IST) == dt.datetime(2026, 10, 6, 13, 0, tzinfo=domain.IST), \
        "half an hour on Saturday, then Tuesday from 09:30: Sunday and the holiday skipped"


async def test_a_run_of_holidays_raises_rather_than_hangs(db: AsyncSession) -> None:
    """Plan review B-2: the scan is bounded at 400 days in both twins."""
    w = await m19._world(db)
    first = dt.date(2030, 1, 1)
    days = [first + dt.timedelta(days=i) for i in range(405) if (first + dt.timedelta(days=i)).isoweekday() != 7]
    await db.execute(text("INSERT INTO holiday (day, name, created_by) SELECT d, 'Closed', CAST(:u AS uuid) FROM unnest(CAST(:ds AS date[])) d"),
                     {"ds": days, "u": w.admin})
    start = dt.datetime(2030, 1, 1, 10, 0, tzinfo=domain.IST)
    await m13._refused(db, "SELECT complaint_add_working_hours(:s, 1)", {"s": start}, "22023")
    with pytest.raises(ValueError, match="no working day"):
        domain.add_working_hours(start, 1, frozenset(days))


async def test_holidays_are_kept_by_masters_editors_for_future_days_only(db: AsyncSession) -> None:
    w = await m19._world(db)
    today = domain.ist_today(dt.datetime.now(dt.UTC))
    ahead = today + dt.timedelta(days=30)
    while ahead.isoweekday() == 7:
        ahead += dt.timedelta(days=1)
    sunday = ahead + dt.timedelta(days=(7 - ahead.isoweekday()))
    add = "SELECT holiday_add(:d, :n)"
    await m19._refused(db, w.officer, add, {"d": ahead, "n": "Diwali"}, "42501")
    await m19._refused(db, w.admin, add, {"d": today, "n": "Closure"}, "HOLPS")
    await m19._refused(db, w.admin, add, {"d": sunday, "n": "Sunday"}, "HOLSU")
    await m19._call(db, w.admin, add, {"d": ahead, "n": " Diwali "})
    assert (await db.execute(text("SELECT name FROM holiday WHERE day = :d"), {"d": ahead})).scalar_one() == "Diwali"
    await m19._refused(db, w.admin, add, {"d": ahead, "n": "Again"}, "HOLEX")
    await m13._as(db, w.dealer_user)
    assert (await db.execute(text("SELECT count(*) FROM holiday WHERE day = :d"), {"d": ahead})).scalar_one() == 1, \
        "a dealer reads holidays: its complaints' due times reflect them"
    await m13._as_owner(db)
    await _holiday(db, today - dt.timedelta(days=1) if (today - dt.timedelta(days=1)).isoweekday() != 7 else today - dt.timedelta(days=2), w)
    past = (await db.execute(text("SELECT max(day) FROM holiday WHERE day <= :t"), {"t": today})).scalar_one()
    await m19._refused(db, w.admin, "SELECT holiday_remove(:d)", {"d": past}, "HOLPS")
    await m19._call(db, w.admin, "SELECT holiday_remove(:d)", {"d": ahead})
    await m19._refused(db, w.admin, "SELECT holiday_remove(:d)", {"d": ahead}, "HOLNF")


async def test_a_missed_target_rings_once_for_the_owner_and_the_checkers(db: AsyncSession) -> None:
    w = await m19._world(db)
    await _mode(db, "bell")
    cid = await m19._complaint(db, w, severity="high")
    await m19._call(db, w.officer, m19.SUBMIT, {"c": cid})
    await _sweep(db)
    row = await m19._row(db, cid)
    assert row.response_escalated_at is not None and row.resolution_escalated_at is not None
    told = await _told(db, cid, "response")
    assert {w.officer, w.dm} <= told, "the owner and the manager who checks it"
    assert w.dealer_user not in told
    await _sweep(db)
    assert (await db.execute(text("SELECT count(*) FROM activity_event WHERE entity_id = CAST(:c AS uuid) AND kind = 'complaint.escalated'"),
                             {"c": cid})).scalar_one() == 2, "once per target, not once per run"


async def test_with_qc_the_qc_managers_and_the_checking_manager_hear_of_it(db: AsyncSession) -> None:
    """Plan review B-1: the check bell's helper answers only while submitted."""
    w = await m19._world(db)
    await _mode(db, "bell")
    cid = await m19._complaint(db, w, severity="high")
    await m19._call(db, w.officer, m19.SUBMIT, {"c": cid})
    await m19._call(db, w.dm, m19.CHECK, m19._check(cid))
    await _sweep(db)
    row = await m19._row(db, cid)
    assert row.status == "under_qc" and row.response_escalated_at is None, "the response was given at the check"
    assert row.resolution_escalated_at is not None
    told = await _told(db, cid, "resolution")
    assert {w.qc, w.dm, w.officer} <= told, told


async def test_off_rings_nothing_and_only_the_system_sweeps(db: AsyncSession) -> None:
    w = await m19._world(db)
    cid = await m19._complaint(db, w, severity="high")
    await m19._call(db, w.officer, m19.SUBMIT, {"c": cid})
    await _mode(db, "off")
    assert await _sweep(db) == 0
    assert (await m19._row(db, cid)).response_escalated_at is None
    await m19._refused(db, w.admin, SWEEP, {}, "42501")


async def test_a_new_due_time_clears_the_stamp(db: AsyncSession) -> None:
    w = await m19._world(db)
    await _mode(db, "bell")
    cid = await m19._complaint(db, w, severity="high")
    await m19._call(db, w.officer, m19.SUBMIT, {"c": cid})
    await _sweep(db)
    await db.execute(text("UPDATE complaint SET response_due_at = response_due_at + interval '1 day' WHERE id = CAST(:c AS uuid)"), {"c": cid})
    row = await m19._row(db, cid)
    assert row.response_escalated_at is None and row.resolution_escalated_at is not None, \
        "only the target whose due time moved can ring again"


async def test_a_continued_reopen_stamps_a_past_target_without_a_bell(db: AsyncSession) -> None:
    """Question 2, GAP-248: the old clock continues, so its past target is not news."""
    w = await m19._world(db)
    await _mode(db, "bell")
    cid = await m19._complaint(db, w, severity="high")
    await m19._call(db, w.officer, m19.SUBMIT, {"c": cid})
    await m19._call(db, w.dm, m19.CHECK, m19._check(cid))
    await m19._call(db, w.qc, m19.QC, {"c": cid, "v": "rejected", "n": None})
    await db.execute(text("UPDATE complaint SET first_submitted_at = now() - interval '30 days', "
                          "clock_from = now() - interval '30 days' WHERE id = CAST(:c AS uuid)"), {"c": cid})
    await db.execute(text("UPDATE app_setting SET value = '\"continue\"' WHERE key = 'complaint_reopen_clock'"))
    await m19._call(db, w.support, "SELECT complaint_reopen(CAST(:c AS uuid), 'Failed again', NULL)", {"c": cid})
    row = await m19._row(db, cid)
    assert row.status == "submitted" and row.response_due_at < dt.datetime.now(dt.UTC)
    assert row.response_escalated_at is not None and row.resolution_escalated_at is not None
    assert (await db.execute(text("SELECT count(*) FROM activity_event WHERE entity_id = CAST(:c AS uuid) AND kind = 'complaint.escalated'"),
                             {"c": cid})).scalar_one() == 0, "stamped, not rung"
    await _sweep(db)
    assert (await db.execute(text("SELECT count(*) FROM activity_event WHERE entity_id = CAST(:c AS uuid) AND kind = 'complaint.escalated'"),
                             {"c": cid})).scalar_one() == 0, "and the next sweep stays silent"


@pytest.mark.parametrize(("holidays", "start", "hours"), [
    ([dt.date(2026, 10, 5)], dt.datetime(2026, 10, 5, 10, 0, tzinfo=domain.IST), 4),           # starts on a holiday
    ([dt.date(2026, 10, 5), dt.date(2026, 10, 7)], dt.datetime(2026, 10, 3, 18, 0, tzinfo=domain.IST), 18),  # spans two
    ([dt.date(2026, 10, 6)], dt.datetime(2026, 10, 5, 18, 45, tzinfo=domain.IST), 9),          # after closing, before one
    ([], dt.datetime(2026, 10, 5, 10, 0, tzinfo=domain.IST), 3200),                             # past 400 days of work
])
async def test_the_twins_agree_on_holiday_paths_and_long_targets(
        db: AsyncSession, holidays: list[dt.date], start: dt.datetime, hours: int) -> None:
    """Code review F-1 and F-3 h: the bound is on a run of closed days, so a long
    policy (the schema allows 8,760 hours) still computes, in both twins."""
    w = await m19._world(db)
    for d in holidays:
        await _holiday(db, d, w)
    sql = (await db.execute(text("SELECT complaint_add_working_hours(:s, :h)"), {"s": start, "h": hours})).scalar_one()
    seen = frozenset((await db.execute(text("SELECT day FROM holiday"))).scalars())
    assert sql == domain.add_working_hours(start, hours, seen)


async def test_a_returned_draft_escalates_its_resolution_target(db: AsyncSession) -> None:
    """GAP-248: a return leaves the resolution clock running (code review F-3 a)."""
    w = await m19._world(db)
    await _mode(db, "bell")
    cid = await m19._complaint(db, w, severity="high")
    await m19._call(db, w.officer, m19.SUBMIT, {"c": cid})
    await m19._call(db, w.dm, m19.CHECK, m19._check(cid, "return"))
    row = await m19._row(db, cid)
    assert row.status == "draft" and row.submit_count == 1
    await _sweep(db)
    row = await m19._row(db, cid)
    assert row.resolution_escalated_at is not None and row.response_escalated_at is None
    assert {w.officer, w.dm} <= await _told(db, cid, "resolution"), "the owner and the manager who returned it"


async def test_a_cancelled_complaint_never_escalates(db: AsyncSession) -> None:
    w = await m19._world(db)
    await _mode(db, "bell")
    cid = await m19._complaint(db, w, severity="high")
    await m19._call(db, w.officer, m19.SUBMIT, {"c": cid})
    await m19._call(db, w.officer, m19.CANCEL, {"c": cid})
    await _sweep(db)
    row = await m19._row(db, cid)
    assert row.response_escalated_at is None and row.resolution_escalated_at is None


async def test_the_deploy_stamps_old_breaches_without_ringing(db: AsyncSession) -> None:
    """Plan review R-3: 048's own statements, run against a back-dated complaint."""
    path = pathlib.Path(__file__).resolve().parents[2] / "api/db/migrations/versions/048_complaint_escalation.py"
    spec = importlib.util.spec_from_file_location("m048_for_test", path)
    assert spec and spec.loader
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    w = await m19._world(db)
    cid = await m19._complaint(db, w, severity="high")
    await m19._call(db, w.officer, m19.SUBMIT, {"c": cid})
    await db.execute(text("UPDATE complaint SET response_due_at = now() - interval '2 days', "
                          "resolution_due_at = now() - interval '1 day' WHERE id = CAST(:c AS uuid)"), {"c": cid})
    for stmt in mig.STAMP_OLD:
        await db.execute(text(stmt))
    row = await m19._row(db, cid)
    assert row.response_escalated_at is not None and row.resolution_escalated_at is not None
    assert (await db.execute(text("SELECT count(*) FROM activity_event WHERE entity_id = CAST(:c AS uuid) AND kind = 'complaint.escalated'"),
                             {"c": cid})).scalar_one() == 0


async def test_nobody_writes_holidays_directly(db: AsyncSession) -> None:
    """Code review F-4: only the definers write the calendar."""
    w = await m19._world(db)
    await m13._as(db, w.admin)
    await m13._refused(db, "INSERT INTO holiday (day, name, created_by) VALUES ('2031-01-06', 'x', CAST(:u AS uuid))",
                       {"u": w.admin}, "42501")
    await m13._as_owner(db)
