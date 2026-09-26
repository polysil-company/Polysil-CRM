"""FS-014's pure rules: IST days, the default due time, the overdue window, the
reopen window, the link rules, and the due-date parse in the schema."""

from __future__ import annotations

import datetime as dt

import pytest

from api.domain import tasks as d
from api.schemas.tasks import ActionItemIn, TaskCreate, TaskPatch

UTC = dt.UTC
NOW = dt.datetime(2026, 9, 26, 12, 0, tzinfo=UTC)          # 17:30 IST


def test_an_ist_day_starts_at_midnight_ist_not_utc() -> None:
    start, end = d.day_bounds(dt.date(2026, 10, 2))
    assert start == dt.datetime(2026, 10, 1, 18, 30, tzinfo=UTC)
    assert end - start == dt.timedelta(days=1)


def test_a_date_alone_is_due_at_six_in_the_evening_ist() -> None:
    assert d.due_from_date(dt.date(2026, 10, 2)) == dt.datetime(2026, 10, 2, 12, 30, tzinfo=UTC)


@pytest.mark.parametrize(("due", "problem"), [
    (dt.datetime(2026, 10, 2, 10, 30), True),                          # naive
    (NOW - dt.timedelta(days=3), False),                               # past: logging what was done
    (NOW + d.DUE_WINDOW, False),
    (NOW + d.DUE_WINDOW + dt.timedelta(seconds=1), True),
    (NOW - d.DUE_WINDOW - dt.timedelta(seconds=1), True),
])
def test_due_problem(due: dt.datetime, problem: bool) -> None:
    assert (d.due_problem(due, NOW) is not None) is problem


def test_only_an_open_task_past_its_time_is_overdue() -> None:
    past = NOW - dt.timedelta(minutes=1)
    assert d.is_overdue("open", past, NOW)
    assert not d.is_overdue("open", NOW, NOW), "due this instant is not late yet"
    assert not d.is_overdue("done", past, NOW)
    assert not d.is_overdue("cancelled", past, NOW)


def test_the_overdue_window_ends_where_the_day_begins() -> None:
    today = dt.date(2026, 9, 26)
    start, _ = d.day_bounds(today)
    assert d.overdue_window(today, today) == (start - d.OVERDUE_LOOKBACK, start)
    assert d.overdue_window(today - dt.timedelta(days=1), today) is not None
    assert d.overdue_window(today + dt.timedelta(days=1), today) is None, "a future day has none"


def test_reopen_is_open_for_seven_days_to_the_second() -> None:
    assert d.reopen_allowed(NOW - d.REOPEN_WINDOW, NOW)
    assert not d.reopen_allowed(NOW - d.REOPEN_WINDOW - dt.timedelta(seconds=1), NOW)


@pytest.mark.parametrize(("lead", "partner", "order", "task_type", "mt", "fields"), [
    (None, None, None, "call", None, set()),
    ("l", "p", None, "call", None, {"lead_id"}),
    ("l", None, "o", "call", None, {"lead_id"}),
    ("l", None, None, "meeting", None, {"meeting_type_id"}),
    ("l", None, None, "meeting", "m", set()),
    (None, "p", None, "meeting", None, set()),     # a dealer meeting takes no type
    (None, "p", None, "meeting", "m", {"meeting_type_id"}),
    ("l", None, None, "call", "m", {"meeting_type_id"}),
])
def test_link_problem(lead: str | None, partner: str | None, order: str | None, task_type: str,
                      mt: str | None, fields: set[str]) -> None:
    assert set(d.link_problem(lead, partner, order, task_type, mt)) == fields


def test_attendees_are_trimmed_and_blanks_dropped() -> None:
    names = [" Kiritbhai ", "", "   ", "Pravinbhai"]
    assert d.clean_attendees(names) == ["Kiritbhai", "Pravinbhai"]


@pytest.mark.parametrize("model", [
    lambda v: TaskCreate(title="x", task_type="call", due_at=v).due_at,
    lambda v: TaskPatch(due_at=v).due_at,
    lambda v: ActionItemIn(title="x", due_at=v).due_at,
])
def test_a_bare_date_is_a_date_and_a_time_stays_a_time(model: object) -> None:
    """Found by the API tests: pydantic read "2026-10-02" as a naive midnight
    datetime, so the 18:00 default never applied and the timezone rule refused it."""
    parse = model  # type: ignore[assignment]
    assert parse("2026-10-02") == dt.date(2026, 10, 2)  # type: ignore[operator]
    assert parse("2026-10-02T00:00:00+05:30") == dt.datetime(  # type: ignore[operator]
        2026, 10, 2, tzinfo=d.IST), "midnight given with a zone stays midnight"
