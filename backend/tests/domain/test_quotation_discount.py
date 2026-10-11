"""FS-013 rule 2a: the effective discount to two places for display, and the gate
exact, with no rounding."""

from __future__ import annotations

import random
from decimal import Decimal
from fractions import Fraction

import pytest

from api.domain.quotations import discount_approval_required, effective_discount_pct

D = Decimal


@pytest.mark.parametrize(("gross", "discount", "shown"), [
    ("1000.00", "100.00", "10.00"),
    ("1857.42", "269.32", "14.50"),     # the three-tier sample line: 14.4997... rounds up
    ("3.00", "1.00", "33.33"),
    ("200.00", "0.01", "0.01"),         # 0.005 rounds half up
    ("0.00", "0.00", "0.00"),           # a zero gross is 0, not a division error
    ("100.00", "0.00", "0.00"),
])
def test_the_effective_discount_is_shown_to_two_places_half_up(gross: str, discount: str,
                                                               shown: str) -> None:
    assert effective_discount_pct(D(gross), D(discount)) == D(shown)


@pytest.mark.parametrize(("gross", "discount", "limit", "required"), [
    ("1000.00", "100.00", "10", False),     # exactly at the limit is within it
    ("1000.00", "100.01", "10", True),      # a paisa above needs approval
    ("3000.00", "300.04", "10", True),      # 10.0013 % shows as 10.00 and still needs it
    ("1000.00", "999.99", None, False),     # no limit
    ("1000.00", "0.01", "0", True),         # a zero limit: any discount needs approval
    ("0.00", "0.00", "0", False),           # nothing to approve on nothing
])
def test_the_gate_is_exact(gross: str, discount: str, limit: str | None, required: bool) -> None:
    assert discount_approval_required(D(gross), D(discount), None if limit is None else D(limit)) \
        is required


def test_the_gate_agrees_with_exact_fractions_across_many_figures() -> None:
    rng = random.Random(13)
    for _ in range(5000):
        gross = D(rng.randint(1, 10_000_000)) / 100
        discount = min(gross, D(rng.randint(0, 10_000_000)) / 100)
        limit = D(rng.randint(0, 2000)) / 100
        exact = Fraction(str(discount)) * 100 > Fraction(str(limit)) * Fraction(str(gross))
        assert discount_approval_required(gross, discount, limit) is exact, (gross, discount, limit)
        shown = effective_discount_pct(gross, discount)
        assert abs(Fraction(str(shown)) - Fraction(str(discount)) * 100 / Fraction(str(gross))) \
            <= Fraction(1, 200), (gross, discount, shown)
