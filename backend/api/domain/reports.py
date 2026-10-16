"""Reports (FS-024): the arithmetic that needs no database.

Percentages are Decimal with one place, half up, as strings in the API. Days are
IST calendar days, inclusive at both ends.
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

IST: Final = dt.timezone(dt.timedelta(hours=5, minutes=30))
DEFAULT_DAYS: Final = 30
MAX_DAYS: Final = 366
ROW_CAP: Final = 1000

# follow-up ageing (REQ-1206): (name, from days overdue, to days overdue inclusive)
AGEING: Final = (("overdue_1_2", 1, 2), ("overdue_3_7", 3, 7), ("overdue_8_30", 8, 30),
                 ("overdue_31_plus", 31, None))


def pct(part: int | Decimal, whole: int | Decimal) -> Decimal:
    """part / whole * 100, one place. Zero when there is no whole."""
    if not whole:
        return Decimal("0.0")
    return (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def window(start: dt.date | None, end: dt.date | None, today: dt.date) -> tuple[dt.date, dt.date]:
    """The inclusive IST date window: the last 30 days by default. A window longer
    than a year, or backwards, is refused by the caller (ValueError)."""
    end = end or today
    start = start or end - dt.timedelta(days=DEFAULT_DAYS - 1)
    if start > end:
        raise ValueError("from is after to")
    if (end - start).days + 1 > MAX_DAYS:
        raise ValueError("at most a year")
    return start, end


def instants(start: dt.date, end: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """The window as a half-open instant range [start 00:00 IST, end+1 00:00 IST)."""
    return (dt.datetime.combine(start, dt.time(0), tzinfo=IST),
            dt.datetime.combine(end + dt.timedelta(days=1), dt.time(0), tzinfo=IST))


def ageing_bucket(due: dt.datetime, now: dt.datetime) -> str | None:
    """Which bucket an open task falls in: `due_today`, an overdue bucket, or None
    when it is due later. Days are IST calendar days."""
    days = (now.astimezone(IST).date() - due.astimezone(IST).date()).days
    if days < 0:
        return None
    if days == 0:
        return "due_today"
    for name, lo, hi in AGEING:
        if days >= lo and (hi is None or days <= hi):
            return name
    raise AssertionError("unreachable")
