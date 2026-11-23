"""Targets (FS-025): months, metrics, and the open window, without a database."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Final, Literal

Metric = Literal["order_value", "orders", "leads_won", "visits"]
METRICS: Final[tuple[Metric, ...]] = ("order_value", "orders", "leads_won", "visits")
COUNTS: Final = frozenset({"orders", "leads_won", "visits"})
AHEAD_MONTHS: Final = 12


def parse_month(raw: str) -> dt.date:
    """`YYYY-MM` to the first of the month. ValueError otherwise."""
    if len(raw) != 7 or raw[4] != "-":
        raise ValueError("a month is YYYY-MM")
    return dt.date(int(raw[:4]), int(raw[5:]), 1)


def month_index(d: dt.date) -> int:
    return d.year * 12 + d.month - 1


def month_problem(month: dt.date, today: dt.date, *, global_scope: bool) -> str | None:
    """None when targets may be set for `month`: from this month to 12 ahead;
    an earlier month only at global scope (GAP-233)."""
    gap = month_index(month) - month_index(today)
    if gap > AHEAD_MONTHS:
        return "more than 12 months ahead"
    if gap < 0 and not global_scope:
        return "month_closed"
    return None


def value_problem(metric: str, value: Decimal) -> str | None:
    if metric not in METRICS:
        return "unknown metric"
    if value < 0:
        return "negative"
    if metric in COUNTS and value != value.to_integral_value():
        return "a whole number"
    if metric == "order_value" and value != value.quantize(Decimal("0.01")):
        return "at most two decimal places"
    return None


def month_end(month: dt.date) -> dt.date:
    nxt = dt.date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)
