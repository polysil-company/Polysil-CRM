"""The printed sheet's rows (FS-064 rules 9, 12, 15). Pure: no database."""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

import pytest

from api.domain.pricing.tax import compute_line
from api.domain.quotations import print_lines, shared_rate, validity_days

P = Decimal("0.01")


def _line(rate: str, qty: str, d1: str = "0", d2: str = "0", d3: str = "0", **over: object) -> dict:
    c = compute_line(rate=Decimal(rate), qty=Decimal(qty),
                     discounts=(Decimal(d1), Decimal(d2), Decimal(d3)), slab=Decimal("5"),
                     intra_state=True)
    line: dict = {"line_no": 1, "description": "UPVC PIPE 90 MM", "uom": "MTR", "qty": qty,
                  "rate": rate, "gross": str(c.gross), "discount": str(c.discount),
                  "taxable": str(c.taxable), "cgst_rate": "2.500", "sgst_rate": "2.500",
                  "igst_rate": "0.000"}
    line.update(over)
    return line


def test_the_spec_fixture_line() -> None:
    """18 m at 103.19, 10 % then 5 %: 1857.42 less 269.32 is 1588.10."""
    [row] = print_lines([_line("103.19", "18.000", "10", "5")])
    assert (row.price, row.discount, row.total) == (
        Decimal("103.19"), Decimal("269.32"), Decimal("1588.10"))
    assert row.price_after == Decimal("88.23")
    assert row.uom == "MTR" and row.qty == Decimal("18.000")


@pytest.mark.parametrize(("d1", "d2", "d3"), [("10", "0", "0"), ("10", "5", "0"), ("10", "5", "3")])
def test_every_tier_folds_into_one_column(d1: str, d2: str, d3: str) -> None:
    line = _line("35", "2", d1, d2, d3)
    [row] = print_lines([line])
    assert row.discount == Decimal(line["discount"])
    assert row.total == Decimal(line["taxable"])
    assert row.price_after == (row.total / 2).quantize(P, rounding=ROUND_HALF_UP)


def test_no_discount_prints_the_rate_itself() -> None:
    """Edge case 6: 103.19 x 0.333 is 34.36, and 34.36 / 0.333 rounds to 103.18."""
    line = _line("103.19", "0.333")
    assert Decimal(line["taxable"]) == Decimal("34.36")
    [row] = print_lines([line])
    assert row.price_after == Decimal("103.19") == row.price and row.discount == 0


def test_the_price_after_discount_rounds_half_up() -> None:
    # 10.05 over 2 is 5.025: half up is 5.03, banker's would be 5.02
    [row] = print_lines([_line("6", "2", taxable="10.05", discount="1.95")])
    assert row.price_after == Decimal("5.03")


def test_a_zero_quantity_never_divides() -> None:
    line = _line("10", "1", "10")
    line["qty"] = "0"
    [row] = print_lines([line])
    assert row.price_after == Decimal("10")


@pytest.mark.parametrize("as_type", [str, Decimal, float])
def test_numbers_arrive_in_any_shape_and_leave_as_decimals(as_type: type) -> None:
    line = _line("103.19", "18.000", "10", "5")
    for key in ("qty", "rate", "discount", "taxable"):
        line[key] = as_type(line[key])
    line["line_no"] = "3"
    [row] = print_lines([line])
    assert row.line_no == 3
    for value in (row.qty, row.price, row.price_after, row.discount, row.total):
        assert isinstance(value, Decimal)
    assert row.price_after == Decimal("88.23") and row.total == Decimal("1588.10")


@pytest.mark.parametrize(("rate", "qty", "tiers"), [
    ("103.19", "18.000", ("10", "5", "0")), ("103.19", "600", ("10", "5", "0")),
    ("35", "2", ("10", "5", "3")), ("0.07", "1250.5", ("2.5", "0", "0")),
    ("99999.99", "999.999", ("12.5", "7.25", "1")), ("412.60", "0.333", ("0", "0", "0")),
])
def test_the_identity_printed_under_the_table_holds(rate: str, qty: str,
                                                    tiers: tuple[str, str, str]) -> None:
    """Rule 9a: Total Amt. is Price x Qty. less Discount. Amt., to the paisa, on
    every line; the rounded price after discount is what does not multiply back."""
    [row] = print_lines([_line(rate, qty, *tiers)])
    assert (row.price * row.qty).quantize(P, rounding=ROUND_HALF_UP) - row.discount == row.total


def test_the_rounded_price_does_not_multiply_back_on_a_long_line() -> None:
    """Why rule 9a exists: 600 m of the fixture line is 1.53 out."""
    [row] = print_lines([_line("103.19", "600", "10", "5")])
    assert row.total == Decimal("52936.47")
    assert row.price_after * row.qty == Decimal("52938.00")


def test_a_missing_unit_prints_nothing() -> None:
    [row] = print_lines([_line("10", "1", uom=None)])
    assert row.uom == ""


def test_a_shared_rate_is_named_and_a_mixed_one_is_not() -> None:
    five, eighteen = _line("10", "1"), _line("10", "1", cgst_rate="9.000", sgst_rate="9.000")
    assert shared_rate([five, five], "cgst_rate") == Decimal("2.500")
    assert shared_rate([five, eighteen], "cgst_rate") is None
    assert shared_rate([], "cgst_rate") is None
    # 2.5 and 2.500 are one rate
    assert shared_rate([five, _line("10", "1", cgst_rate=2.5)], "cgst_rate") == Decimal("2.5")


def test_validity_days() -> None:
    assert validity_days(dt.date(2026, 10, 1), dt.date(2026, 11, 15)) == 45
    assert validity_days(dt.date(2026, 10, 1), dt.date(2026, 10, 1)) == 0
    assert validity_days(dt.date(2026, 1, 31), dt.date(2026, 3, 1)) == 29
    assert validity_days(dt.date(2026, 10, 5), dt.date(2026, 10, 1)) == 0
