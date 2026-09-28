"""FS-017's arithmetic: the relative change, the rate and the rounding (review B-3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from api.domain.dashboard import delta_percent, money, one_place, rate


@pytest.mark.parametrize(("current", "previous", "want"), [
    ("42", "36", "16.7"),          # 16.666... half up
    ("36", "42", "-14.3"),
    ("5", "0", None),              # no previous period: no change to show
    ("0", "8", "-100.0"),
    ("8", "8", "0.0"),
    ("11.9", "12.4", "-4.0"),       # a rate is compared relatively too
])
def test_delta_percent(current: str, previous: str, want: str | None) -> None:
    assert delta_percent(Decimal(current), Decimal(previous)) == want


def test_half_up_not_half_even_and_never_minus_zero() -> None:
    assert one_place(Decimal("16.65")) == "16.7", "Python's default would give 16.6"
    assert one_place(Decimal("-0.04")) == "0.0"
    assert one_place(Decimal("-0.05")) == "-0.1"


def test_rate_and_money() -> None:
    assert rate(0, 0) == 0, "an empty bucket is 0.0, not a division error"
    assert one_place(rate(1, 3)) == "33.3"
    assert money(None) == "0.00" and money(Decimal("1234.5")) == "1234.50"
