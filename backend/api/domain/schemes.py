"""Schemes (FS-031): the rules that need no database.

What a scheme gives and when is worked out in SQL, by the functions the order-status
trigger calls (migration 033), so every path that moves an order is covered and the
preview reads the same functions. This module holds what the service checks before
a write, so a bad combination is a 422 naming the field rather than a CHECK
violation, and the period arithmetic the tests compare the SQL against.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

TYPES: Final = ("order_discount", "order_points", "next_order", "period")
KINDS_FOR_TYPE: Final[dict[str, frozenset[str]]] = {
    "order_discount": frozenset({"pct", "flat"}),
    "order_points": frozenset({"points"}),
    "next_order": frozenset({"pct", "flat"}),
    "period": frozenset({"pct", "flat", "points"}),
}
TARGET_TYPES: Final = ("territory", "partner_type", "partner", "product", "product_category")
PARTNER_TYPES: Final = frozenset({"distributor", "dealer", "sub_dealer"})
DEFAULT_ENTITLEMENT_DAYS: Final = 90          # GAP-307

# The SQLSTATE migration 033's triggers raise, and what it is to the API
SQLSTATE_IN_USE: Final = "SCHIU"


@dataclass(frozen=True)
class Terms:
    """The parts of a scheme whose combination is checked (FS-031 4, rule 20)."""

    scheme_type: str
    benefit_kind: str
    benefit_value: Decimal
    benefit_cap: Decimal | None
    entitlement_days: int | None
    period: str | None
    condition_min: Decimal
    condition_max: Decimal | None
    valid_from: dt.date
    valid_to: dt.date | None


def problems(t: Terms) -> dict[str, str]:
    """Field -> message for every rule the terms break. Empty when valid."""
    out: dict[str, str] = {}
    kinds = KINDS_FOR_TYPE.get(t.scheme_type)
    if kinds is None:
        return {"scheme_type": "Unknown scheme type."}
    if t.benefit_kind not in kinds:
        label = {"order_discount": "An order discount", "order_points": "A points scheme",
                 "next_order": "A next-order scheme", "period": "A period scheme"}[t.scheme_type]
        out["benefit.kind"] = f"{label} takes {' or '.join(sorted(kinds))}."
    if t.benefit_value <= 0:
        out["benefit.value"] = "Must be more than zero."
    elif t.benefit_kind == "pct" and t.benefit_value > 100:
        out["benefit.value"] = "A percentage is at most 100."
    elif t.benefit_kind == "points" and t.benefit_value != t.benefit_value.to_integral_value():
        out["benefit.value"] = "Points are whole numbers."
    if t.benefit_cap is not None:
        if t.benefit_kind == "points":
            out["benefit.cap"] = "A points benefit has no cap."
        elif t.benefit_cap <= 0:
            out["benefit.cap"] = "Must be more than zero."
    needs_days = t.scheme_type == "next_order" or (t.scheme_type == "period"
                                                   and t.benefit_kind != "points")
    if t.entitlement_days is not None and not needs_days:
        out["benefit.entitlement_days"] = "Only a benefit used on a later order expires."
    elif t.entitlement_days is not None and not 1 <= t.entitlement_days <= 3650:
        out["benefit.entitlement_days"] = "Between 1 and 3650 days."
    if t.scheme_type == "period":
        if t.period not in ("month", "quarter"):
            out["period"] = "A period scheme runs by month or quarter."
        if t.valid_to is None:
            out["valid_to"] = "A period scheme needs an end date."
    elif t.period is not None:
        out["period"] = "Only a period scheme has a period."
    if t.condition_min < 0:
        out["condition.min"] = "Cannot be negative."
    if t.condition_max is not None and t.condition_max < t.condition_min:
        out["condition.max"] = "Must be at least the minimum."
    if t.valid_to is not None and t.valid_to < t.valid_from:
        out["valid_to"] = "Must be on or after the start date."
    return out


def entitlement_days(t: Terms) -> int | None:
    """The stored value: the default where the type needs one and none was sent."""
    needs = t.scheme_type == "next_order" or (t.scheme_type == "period"
                                              and t.benefit_kind != "points")
    if not needs:
        return None
    return t.entitlement_days or DEFAULT_ENTITLEMENT_DAYS


def target_problems(targets: Sequence[tuple[str, str]]) -> dict[str, str]:
    """The target list's own rules; whether an id exists is the service's check."""
    out: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for i, (kind, value) in enumerate(targets):
        if kind not in TARGET_TYPES:
            out[f"targets[{i}].type"] = "Unknown target type."
        elif kind == "partner_type" and value not in PARTNER_TYPES:
            out[f"targets[{i}].id"] = "distributor, dealer or sub_dealer."
        if (kind, value) in seen:
            out[f"targets[{i}]"] = "Listed twice."
        seen.add((kind, value))
    if len(targets) > 200:
        out["targets"] = "At most 200 targets."
    return out


# ── periods (rule 11) ────────────────────────────────────────────────────────

def _period_start(day: dt.date, period: str) -> dt.date:
    if period == "month":
        return day.replace(day=1)
    # calendar quarters; April to June is the Indian financial year's first
    return day.replace(month=(day.month - 1) // 3 * 3 + 1, day=1)


def _add_months(day: dt.date, months: int) -> dt.date:
    y, m = divmod(day.month - 1 + months, 12)
    return day.replace(year=day.year + y, month=m + 1, day=1)


def periods(valid_from: dt.date, valid_to: dt.date, period: str,
            until: dt.date) -> Iterator[tuple[dt.date, dt.date]]:
    """Each period from the scheme's start up to `until`, clipped to its dates.
    Mirrors `scheme_periods()` in migration 033."""
    step = 1 if period == "month" else 3
    start = _period_start(valid_from, period)
    last = min(until, valid_to)
    while start <= last:
        end = _add_months(start, step) - dt.timedelta(days=1)
        yield max(start, valid_from), min(end, valid_to)
        start = _add_months(start, step)
