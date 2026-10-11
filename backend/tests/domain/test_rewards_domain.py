"""The rewards arithmetic, pure: what 036's submit arm spends (PR 11 review)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from api.domain.rewards import redemption_split

D = Decimal


@pytest.mark.parametrize(("points", "value", "left", "limit", "expected"), [
    # worked by hand: room 17.40 at Rs 1 a point is 17 whole points, Rs 17.00
    (500, D("1.00"), D("1000.00"), D("17.40"), (D("17.00"), 17)),
    # the points' own value is the least: all 40 spent
    (40, D("1.00"), D("1000.00"), D("100.00"), (D("40.00"), 40)),
    # the payable left is the least: 5.50 left spends 5 points, 0.50 is paid in cash
    (500, D("1.00"), D("5.50"), D("100.00"), (D("5.00"), 5)),
    # a point worth 0.75: room 50 holds 66 points (49.50), not 67 (50.25)
    (100, D("0.75"), D("1000.00"), D("50.00"), (D("49.50"), 66)),
    # less than one point of room spends nothing
    (500, D("1.00"), D("0.40"), D("100.00"), (D("0.00"), 0)),
    # nothing left to pay
    (500, D("1.00"), D("0.00"), D("100.00"), (D("0.00"), 0)),
])
def test_redemption_split_spends_whole_points_within_the_room(
        points: int, value: Decimal, left: Decimal, limit: Decimal,
        expected: tuple[Decimal, int]) -> None:
    assert redemption_split(points, value, left, limit) == expected


def test_a_point_is_never_spent_for_less_than_its_value() -> None:
    for room_paise in range(0, 5000, 7):
        room = D(room_paise) / 100
        amount, used = redemption_split(10_000, D("1.25"), room, D("1000000"))
        assert amount <= room
        assert amount == D(used) * D("1.25")
        assert room - amount < D("1.25")
