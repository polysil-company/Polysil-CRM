"""Reward points (FS-032): the arithmetic, without a database.

The database does every write (migration 036): earning in triggers, spending through
`reward_spend()` under a per-holder lock. These functions state the same rules in
Python so the service can validate a request and the tests can check the SQL against
hand-worked figures.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

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


def redemption_split(points: int, point_value: Decimal, payable_left: Decimal,
                     limit: Decimal) -> tuple[Decimal, int]:
    """At submit: the rupees applied and the points used. Mirrors 036's trigger arm:
    the room is the least of the points' value, the payable left and the limit
    (max_redeem_pct of the total, rounded to the paisa); whole points only, so the
    points used are the room over the point value rounded down, and the amount is
    those points times the value (GAP-316). The rest go back."""
    room = min((Decimal(points) * point_value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
               payable_left, limit)
    if room <= 0:
        return Decimal("0.00"), 0
    used = int((room / point_value).to_integral_value(rounding=ROUND_FLOOR))
    return (Decimal(used) * point_value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), used


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
