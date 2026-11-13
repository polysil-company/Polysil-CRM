"""Warranty arithmetic (FS-046). Pure: no database, no clock of its own."""

from __future__ import annotations

import calendar
import datetime as dt
from typing import Literal

MAX_MONTHS = 120

DispatchStatus = Literal["active", "expired", "none", "unknown"]
LineStatus = Literal[DispatchStatus, "not_dispatched"]
ClaimStatus = Literal["in_warranty", "expired", "none", "unknown"]


def add_months(day: dt.date, months: int) -> dt.date:
    """The same day `months` later, clamped to the month's last day (31 Jan + 1 = 28 or 29 Feb)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def end_date(start: dt.date, months: int) -> dt.date | None:
    """The last covered day (FS-046 rule 3): start plus the months, less one day;
    but when the start's day does not exist in the end month, the month end itself.
    1 Jan + 1 ends 31 Jan; 31 Jan + 1 ends 28 Feb; 29 Feb 2024 + 12 ends 28 Feb 2025;
    1 Mar 2027 + 12 ends 29 Feb 2028. None for 0 months: no warranty. The SQL twin
    warranty_end() is authoritative; a test holds the two equal."""
    if not 0 <= months <= MAX_MONTHS:
        raise ValueError(f"months must be 0 to {MAX_MONTHS}")
    if months == 0:
        return None
    later = add_months(start, months)
    return later if later.day < start.day else later - dt.timedelta(days=1)


def status_on(months: int | None, end: dt.date | None, day: dt.date) -> DispatchStatus:
    """A dispatch's status on a day. Covered through the end date, inclusive.
    months None: no term was in force on the start day."""
    if months is None:
        return "unknown"
    if months == 0 or end is None:
        return "none"
    return "active" if day <= end else "expired"


def claim_status(months: int | None, end: dt.date | None, raised_on: dt.date) -> ClaimStatus:
    """A complaint line on the day raised. A day before the start counts as in
    warranty (edge EC-11)."""
    if months is None:
        return "unknown"
    if months == 0 or end is None:
        return "none"
    return "in_warranty" if raised_on <= end else "expired"
