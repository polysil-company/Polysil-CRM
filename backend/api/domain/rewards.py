"""Reward points (FS-032): the arithmetic, without a database.

The database does every write (migration 036): earning in triggers, spending through
`reward_spend()` under a per-holder lock. These functions state the same rules in
Python so the service can validate a request and the tests can check the SQL against
hand-worked figures.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

# The SQLSTATEs migration 036 raises, and what each is to the API: (status, code)
SQLSTATE_TO_ERROR: dict[str, tuple[int, str]] = {
    "RWDIN": (422, "insufficient_points"),
    "RWDMX": (422, "over_redeem_limit"),
    "RWDEX": (409, "points_on_order"),
    "RWDOR": (422, "not_partners_order"),
    "RWDGF": (422, "gift_unavailable"),
    "RWDCL": (409, "redemption_closed"),
    "RWDNF": (404, "not_found"),
    "RWDVL": (422, "validation_error"),
    "RWDIU": (409, "rule_in_use"),
}


def points_for(value: Decimal, per_amount: Decimal, points: int) -> int:
    """Rule 2: whole blocks of `per_amount` in the value, times the points. Never a
    fraction of a point."""
    if value <= 0 or per_amount <= 0:
        return 0
    blocks = (value / per_amount).to_integral_value(rounding=ROUND_FLOOR)
    return int(blocks) * points


def redemption_split(points: int, point_value: Decimal,
                     payable_left: Decimal) -> tuple[Decimal, int]:
    """At submit: the rupees applied and the points used. Mirrors 036's trigger arm:
    the points' value or the payable left, whichever is less; the points used are the
    applied amount over the point value, rounded up; the rest go back."""
    amount = min((Decimal(points) * point_value).quantize(Decimal("0.01")), payable_left)
    if amount <= 0:
        return Decimal("0.00"), 0
    used = int((amount / point_value).to_integral_value(rounding=ROUND_CEILING))
    return amount, used


@dataclass(frozen=True)
class Lot:
    points: int
    expired_due: bool


def expiry(lots: Sequence[Lot], spent: int, already_expired: int) -> list[int]:
    """Plan review S1: per holder, lots in expiry order. A due lot expires what is
    left of it after everything spent, oldest first. Mirrors `reward_points_expire()`."""
    out: list[int] = []
    cumulative = 0
    expired = already_expired
    for lot in lots:
        cumulative += lot.points
        if not lot.expired_due:
            out.append(0)
            continue
        take = max(0, min(lot.points, cumulative - spent - expired))
        expired += take
        out.append(take)
    return out
