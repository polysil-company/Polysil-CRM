"""Tasks and the planner (FS-014): the rules that need no database.

Days are Indian calendar days (rule 8). The stand-in numbers are GAP-143's; each
is a constant here so a setting can replace it.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

IST: Final = dt.timezone(dt.timedelta(hours=5, minutes=30))

TITLE_MAX: Final = 200
TEXT_MAX: Final = 2000
ATTENDEES_MAX: Final = 50
ATTENDEE_MAX: Final = 120
REOPEN_WINDOW: Final = dt.timedelta(days=7)          # GAP-143
OVERDUE_LOOKBACK: Final = dt.timedelta(days=90)      # GAP-143
DEFAULT_DUE_TIME: Final = dt.time(18, 0)             # GAP-143: a date without a time
DUE_WINDOW: Final = dt.timedelta(days=730)           # two years either side, the service's

TASK_TYPES: Final = ("call", "visit", "meeting", "followup", "other")
MINUTES_OUTCOME: Final = "Minutes recorded"


def day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """The IST day as a half-open instant range [start, end)."""
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=IST)
    return start, start + dt.timedelta(days=1)


def due_from_date(day: dt.date) -> dt.datetime:
    """A due date given without a time is due at 18:00 IST (rule 8, GAP-143)."""
    return dt.datetime.combine(day, DEFAULT_DUE_TIME, tzinfo=IST)


def due_problem(due_at: dt.datetime, now: dt.datetime) -> str | None:
    """None when a due time is acceptable. Naive datetimes are refused; past ones
    are allowed, for logging what was done; two years either side is the bound."""
    if due_at.tzinfo is None or due_at.utcoffset() is None:
        return "give a timezone, for example +05:30"
    if abs(due_at - now) > DUE_WINDOW:
        return "within two years of today"
    return None


def is_overdue(status: str, due_at: dt.datetime, now: dt.datetime) -> bool:
    """In a list: open and past its due time (rule 7)."""
    return status == "open" and due_at < now


def overdue_window(day: dt.date, today: dt.date) -> tuple[dt.datetime, dt.datetime] | None:
    """For a planner date: open tasks due in [start of day - 90 days, start of day)
    are overdue. A future date has none, so a task is either due that day or
    overdue, never both (EC-8)."""
    if day > today:
        return None
    start, _ = day_bounds(day)
    return start - OVERDUE_LOOKBACK, start


def reopen_allowed(completed_at: dt.datetime, now: dt.datetime) -> bool:
    return now - completed_at <= REOPEN_WINDOW


def link_problem(lead_id: str | None, partner_id: str | None, order_id: str | None,
                 task_type: str, meeting_type_id: str | None) -> dict[str, str]:
    """Rules 2 and 5, before the database's CHECKs: at most one link, and a
    meeting type exactly on a meeting on a lead."""
    fields: dict[str, str] = {}
    if sum(x is not None for x in (lead_id, partner_id, order_id)) > 1:
        fields["lead_id"] = "a task hangs off one thing: a lead, a dealer or an order"
    wants_type = task_type == "meeting" and lead_id is not None
    if wants_type and meeting_type_id is None:
        fields["meeting_type_id"] = "required for a meeting on a lead"
    if meeting_type_id is not None and not wants_type:
        fields["meeting_type_id"] = "only for a meeting on a lead"
    return fields


def clean_attendees(names: list[str]) -> list[str]:
    """Trimmed, blanks dropped (EC-7). The caps are the schema's."""
    return [n.strip() for n in names if n and n.strip()]
