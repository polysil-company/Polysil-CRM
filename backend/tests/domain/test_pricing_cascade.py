"""The three-tier discount cascade (FS-005 rule 6).

Each tier is a percentage of the running balance, and each amount is rounded to
the paisa before the next tier applies, so every printed column is a printed
figure and the columns add up. The client's own sheet applies the tiers to the
running balance too, and does not round between them; on its seven lines that
is one paisa on the document, recorded in the golden fixture (GAP-118).
"""

from __future__ import annotations

import itertools
import json
import pathlib
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

import pytest

from api.domain.money import round2
from api.domain.pricing.tax import MAX_TIERS, compute_line, document_totals
from api.domain.pricing.types import PricingError

D = Decimal
ZERO = D(0)
GOLDEN = pathlib.Path(__file__).parent / "golden" / "quotation_sheet.json"


def cascade(rate: str, qty: str, *tiers: str, slab: str = "5", intra: bool = True):
    return compute_line(rate=D(rate), qty=D(qty), discounts=tuple(D(t) for t in tiers),
                        slab=D(slab), intra_state=intra)


# ── the oracle: exact arithmetic, rounded at each step ───────────────────────

def _q2(x: Fraction) -> Fraction:
    """Round half up to two places, exactly, the way round2 does on a Decimal."""
    return Fraction(round2(Decimal(x.numerator) / Decimal(x.denominator)))


def oracle(rate: str, qty: str,
           tiers: tuple[str, ...]) -> tuple[Fraction, list[Fraction], Fraction]:
    gross = _q2(Fraction(rate) * Fraction(qty))
    balance = gross
    amounts = []
    for pct in tiers:
        amount = _q2(balance * Fraction(pct) / 100)
        balance -= amount
        amounts.append(amount)
    return gross, amounts, balance


@pytest.mark.parametrize(("rate", "qty", "tiers"), list(itertools.product(
    ("103.19", "35.00", "1521.24", "0.01", "999.99"),
    ("1.005", "2", "0.333", "18", "200"),
    (("10", "5", "3"), ("10.000", "5.000", "0.000"), ("33.333", "33.333", "33.333"),
     ("0", "0", "0"), ("100", "0", "0"), ("2.5", "7.125", "50"), ("0", "12.5", "0")),
)))
def test_every_tier_matches_the_oracle(rate: str, qty: str, tiers: tuple[str, ...]) -> None:
    got = cascade(rate, qty, *tiers)
    gross, amounts, balance = oracle(rate, qty, tiers)
    assert Fraction(got.gross) == gross
    assert [Fraction(s.amount) for s in got.steps] == amounts
    assert Fraction(got.taxable) == balance
    assert got.discount == sum((s.amount for s in got.steps), ZERO)
    assert got.gross - got.discount == got.taxable


def test_each_tier_is_taken_off_the_running_balance_not_the_gross() -> None:
    """The client's sheet, row 14: 35.00 x 2, then 10 %, 5 %, 3 %. The second tier
    is 3.15 on 63.00, not 3.50 on 70.00."""
    got = cascade("35.00", "2", "10", "5", "3")
    assert [(s.pct, s.amount, s.after) for s in got.steps] == [
        (D("10"), D("7.00"), D("63.00")),
        (D("5"), D("3.15"), D("59.85")),
        (D("3"), D("1.80"), D("58.05")),
    ]
    assert got.discount == D("11.95")
    assert got.taxable == D("58.05")


def test_the_spec_example_reproduces_exactly() -> None:
    """FS-005 §4: 103.19 x 18 at 10 % then 5 %."""
    got = cascade("103.19", "18", "10.000", "5.000", "0.000")
    assert (got.gross, got.taxable, got.discount) == (D("1857.42"), D("1588.10"), D("269.32"))
    assert [s.amount for s in got.steps] == [D("185.74"), D("83.58"), D("0.00")]
    assert [s.after for s in got.steps] == [D("1671.68"), D("1588.10"), D("1588.10")]
    assert (got.cgst, got.sgst, got.total) == (D("39.70"), D("39.70"), D("1667.50"))


# ── one tier is the cascade with two zero tiers ───────────────────────────────

@pytest.mark.parametrize(("rate", "qty", "pct"), list(itertools.product(
    ("103.19", "1.84", "1521.24", "0.01", "999.99"),
    ("1.005", "18", "0.333", "1", "200"),
    ("0", "2.50", "7.125", "33.333", "100"),
)))
def test_one_tier_equals_the_old_engine_on_every_existing_case(rate: str, qty: str,
                                                                pct: str) -> None:
    one = compute_line(rate=D(rate), qty=D(qty), discount_pct=D(pct), slab=D("18"),
                       intra_state=True)
    three = cascade(rate, qty, pct, "0", "0", slab="18")
    assert (one.gross, one.discount, one.taxable, one.cgst, one.sgst, one.total) == (
        three.gross, three.discount, three.taxable, three.cgst, three.sgst, three.total)
    assert len(one.steps) == 1 and len(three.steps) == 3
    assert three.steps[1].amount == ZERO and three.steps[2].amount == ZERO


def test_a_zero_tier_is_still_a_step() -> None:
    """The response prints three columns whatever the percentages are."""
    got = cascade("100", "1", "0", "10", "0")
    assert [s.amount for s in got.steps] == [D("0.00"), D("10.00"), D("0.00")]
    assert [s.after for s in got.steps] == [D("100.00"), D("90.00"), D("90.00")]


def test_a_full_first_tier_leaves_nothing_for_the_others() -> None:
    got = cascade("250", "4", "100", "50", "50")
    assert got.taxable == ZERO and got.discount == got.gross == D("1000.00")
    assert got.total == ZERO


# ── refusals ──────────────────────────────────────────────────────────────────

def test_a_fourth_tier_is_refused() -> None:
    assert MAX_TIERS == 3
    with pytest.raises(PricingError) as exc:
        cascade("10", "1", "1", "1", "1", "1")
    assert exc.value.code == "too_many_discounts"


@pytest.mark.parametrize(("tiers", "field"), [
    (("101", "0", "0"), "discount_pct"),
    (("0", "-1", "0"), "discount2_pct"),
    (("0", "0", "100.001"), "discount3_pct"),
])
def test_an_out_of_range_tier_names_its_field(tiers: tuple[str, ...], field: str) -> None:
    with pytest.raises(PricingError) as exc:
        cascade("10", "1", *tiers)
    assert exc.value.code == "discount_out_of_range"
    assert exc.value.field_path == field


# ── the golden: the client's own sheet ────────────────────────────────────────

def test_the_clients_sheet_reproduces_to_the_paisa_and_the_delta_is_recorded() -> None:
    """Seven lines, (10, 5, 3), intra-state at 5 %. The sheet does not round
    between tiers; the engine does. The engine's answer is asserted exactly and
    the difference against the sheet is asserted too, so a change in either
    direction is noticed rather than absorbed.
    """
    fx = json.loads(GOLDEN.read_text(encoding="utf-8"))
    lines = tuple(
        compute_line(rate=D(ln["rate"]), qty=D(ln["qty"]),
                     discounts=tuple(D(p) for p in ln["discounts"]),
                     slab=D(ln["gst_slab"]), intra_state=fx["intra_state"])
        for ln in fx["lines"])
    for got, ln in zip(lines, fx["lines"], strict=True):
        sheet = ln["sheet"]
        assert got.gross == D(sheet["gross"])
        # the sheet's intermediates are unrounded floats shown at two places, so a
        # tier that lands on a half paisa (row 20: 1.845) prints either way there
        # and one way here; per line the two agree to the paisa, never further
        for step, key in zip(got.steps, ("d1", "d2", "d3"), strict=True):
            assert abs(step.amount - D(sheet[key])) <= D("0.01"), (ln, key)
        assert abs(got.taxable - D(sheet["final"])) <= D("0.01")

    totals = document_totals(lines)
    expected = fx["engine_totals_expected"]
    assert totals.taxable == D(expected["taxable"])
    assert totals.cgst + totals.sgst == D(expected["gst"])
    sheet_totals = fx["sheet_totals"]
    assert D(sheet_totals["final"]) - totals.taxable == D("0.01")
    assert D(sheet_totals["gst"]) - (totals.cgst + totals.sgst) == D("0.01")
    assert totals.gross == D(sheet_totals["gross"])
    assert totals.discount == totals.gross - totals.taxable


def test_the_sheet_totals_are_sums_not_recomputations() -> None:
    """Sanity on the fixture itself: the sheet's per-line d1 values sum to its
    row-24 d1, so the fixture was read from the right cells."""
    fx = json.loads(GOLDEN.read_text(encoding="utf-8"))
    d1 = sum(D(ln["sheet"]["d1"]) for ln in fx["lines"])
    assert d1.quantize(D("0.01"), rounding=ROUND_HALF_UP) == D(fx["sheet_totals"]["d1"])
