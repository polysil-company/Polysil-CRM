"""The commercial GST engine (FS-010 section 10, the tax rows; PRICE-1, PRICE-2).

This is the module where a bug is a legal problem rather than a commercial one, so
the assertions are about the two things a reader would otherwise have to take on
trust: **that the three printed figures reconcile**, and **that the document total
is the sum of rounded lines rather than a recomputation**.

Every figure quoted here was computed from the rule, then confirmed against the
engine. Where two defensible methods disagree, the test asserts which one we chose
and records the consequence, so nobody "harmonises" it later.
"""

from __future__ import annotations

import itertools
from decimal import ROUND_HALF_EVEN, Decimal

import pytest

from api.domain.money import round2
from api.domain.pricing.tax import (
    MAX_DOCUMENT_TOTAL,
    MAX_LINE_TOTAL,
    MAX_QTY,
    compute_line,
    document_totals,
    half,
)
from api.domain.pricing.types import PricingError

D = Decimal
ZERO = D(0)

# The slabs migration 010 allows. 0.25 is the only one whose half needs three
# decimals, and it does not apply to this catalogue.
SLABS = [D(s) for s in ("0", "0.25", "3", "5", "12", "18", "28")]


def line(rate: str, qty: str, *, pct: str = "0", slab: str = "5", intra: bool = True):
    return compute_line(rate=D(rate), qty=D(qty), discount_pct=D(pct), slab=D(slab),
                        intra_state=intra)


# ── rule 7: the printed figures reconcile ────────────────────────────────────

def test_the_three_printed_figures_add_up() -> None:
    """The golden case from the spec. Gross has five decimal places before
    rounding (103.70595), which is where the orders diverge."""
    got = line("103.19", "1.005", pct="2.50")
    assert (got.gross, got.discount, got.taxable) == (D("103.71"), D("2.59"), D("101.12"))
    assert got.gross - got.discount == got.taxable


@pytest.mark.parametrize(("rate", "qty", "pct"), list(itertools.product(
    ("103.19", "1.84", "1521.24", "0.01", "999.99"),
    ("1.005", "18", "0.333", "1", "200"),
    ("0", "2.50", "7.125", "33.333", "100"),
)))
def test_gross_less_discount_is_always_the_taxable_value(rate: str, qty: str, pct: str) -> None:
    """The property the print order exists to guarantee, over 75 combinations.
    Rounding once at the end instead breaks it on about a fifth of them."""
    got = line(rate, qty, pct=pct)
    assert got.gross - got.discount == got.taxable
    assert got.taxable == got.taxable.quantize(D("0.01"))


def test_rounding_once_at_the_end_would_give_a_different_answer() -> None:
    """Not a test of our code, but of why the rule says what it says. If this ever
    stops differing, the golden case above has lost its point."""
    rate, qty, pct = D("103.19"), D("1.005"), D("2.50")
    one_shot = round2(rate * qty - rate * qty * pct / 100)
    printed = line("103.19", "1.005", pct="2.50").taxable
    assert one_shot == D("101.11") and printed == D("101.12")


def test_the_rounding_is_half_up_and_not_bankers() -> None:
    """A taxable value of 1.00 at 5 % puts each component on exactly half a paisa:
    0.025. Half-up gives 0.03, banker's gives 0.02."""
    got = line("1.00", "1", slab="5")
    assert got.cgst == D("0.03")
    assert (D("0.025")).quantize(D("0.01"), rounding=ROUND_HALF_EVEN) == D("0.02")


# ── rule 9: the split, and the two consequences we own ───────────────────────

def test_intra_state_is_two_equal_components_and_inter_state_is_one() -> None:
    intra = line("103.19", "18", slab="5", intra=True)
    inter = line("103.19", "18", slab="5", intra=False)

    assert intra.taxable == inter.taxable == D("1857.42")
    assert (intra.cgst, intra.sgst, intra.igst) == (D("46.44"), D("46.44"), ZERO)
    assert (inter.cgst, inter.sgst, inter.igst) == (ZERO, ZERO, D("92.87"))
    assert intra.total == D("1950.30")
    assert inter.total == D("1950.29")


@pytest.mark.parametrize("slab", SLABS)
def test_cgst_always_equals_sgst(slab: Decimal) -> None:
    """Per-component rounding makes them equal by construction. The other method,
    halving a rounded total, makes them differ by a paisa. This asserts which we
    chose."""
    got = compute_line(rate=D("103.19"), qty=D("1.005"), discount_pct=D("2.5"),
                       slab=slab, intra_state=True)
    assert got.cgst == got.sgst


def test_a_small_intra_state_line_carries_a_paisa_more_than_inter_state() -> None:
    """A stated consequence, not an accident: rounding each half separately rounds
    up twice. The client's own subsidy workbooks do the same thing."""
    intra = line("1.00", "1", slab="5", intra=True)
    inter = line("1.00", "1", slab="5", intra=False)
    assert intra.cgst + intra.sgst == D("0.06")
    assert inter.igst == D("0.05")
    assert intra.total - inter.total == D("0.01")


def test_the_halved_rate_is_exact_and_never_stored_rounded() -> None:
    """0.25 % is the one slab whose half needs three decimals. It does not apply to
    this catalogue, and the engine would still carry it correctly."""
    assert half(D("0.25")) == D("0.125")
    got = compute_line(rate=D("100000"), qty=D("1"), discount_pct=ZERO,
                       slab=D("0.25"), intra_state=True)
    assert got.cgst_rate == D("0.125")
    assert got.cgst == D("125.00")


@pytest.mark.parametrize("slab", SLABS)
def test_the_rates_returned_are_the_rates_applied(slab: Decimal) -> None:
    """They are returned so no client halves a slab in JavaScript."""
    intra = compute_line(rate=D("1000"), qty=D("1"), discount_pct=ZERO, slab=slab,
                         intra_state=True)
    assert intra.cgst_rate + intra.sgst_rate == slab
    assert intra.cgst == round2(intra.taxable * intra.cgst_rate / 100)
    inter = compute_line(rate=D("1000"), qty=D("1"), discount_pct=ZERO, slab=slab,
                         intra_state=False)
    assert inter.igst_rate == slab


def test_a_zero_rated_product_is_taxed_at_zero_and_still_totals() -> None:
    got = line("103.19", "18", slab="0")
    assert (got.cgst, got.sgst, got.igst) == (ZERO, ZERO, ZERO)
    assert got.total == got.taxable == D("1857.42")


def test_a_hundred_per_cent_discount_leaves_nothing_to_tax() -> None:
    """GAP-093: whether a free supply is taxable on the value of the goods is the
    client's accountant's question. Today the taxable value is zero."""
    got = line("103.19", "18", pct="100")
    assert (got.discount, got.taxable, got.total) == (D("1857.42"), ZERO, ZERO)


# ── the document total is the sum of rounded lines ───────────────────────────

def test_the_document_total_is_the_sum_of_rounded_lines_not_a_recomputation() -> None:
    """A hundred lines, four rates. The two methods differ by rupees, and the sum
    of the lines is the one an invoice prints."""
    rates = ("103.19", "1.84", "1521.24", "0.37")
    lines = tuple(line(rates[i % 4], "3", slab="5") for i in range(100))
    totals = document_totals(lines)

    assert totals.taxable == sum(ln.taxable for ln in lines)
    assert totals.cgst == sum(ln.cgst for ln in lines)
    assert totals.total == sum(ln.total for ln in lines)

    recomputed = round2(totals.taxable * D("2.5") / 100) * 2 + totals.taxable
    assert recomputed != totals.total, "the two methods must differ, or this proves nothing"
    assert abs(recomputed - totals.total) >= D("0.10")


def test_an_empty_document_totals_to_zero() -> None:
    totals = document_totals(())
    assert (totals.taxable, totals.total) == (ZERO, ZERO)


# ── rule 11: three bounds, not one ───────────────────────────────────────────

def test_a_quantity_beyond_the_bound_is_refused_and_does_not_raise_inside_the_engine() -> None:
    """`Decimal('103.19') * Decimal('1E+26')` then `round2` raises
    `InvalidOperation` at the default precision. That would be a 500 out of the one
    module where a bug is a legal problem, reached by one field."""
    with pytest.raises(PricingError) as err:
        line("103.19", "1E+26")
    assert err.value.code == "qty_too_large"
    assert err.value.field_path == "qty"


def test_the_quantity_bound_alone_does_not_bound_the_line_total() -> None:
    """Which is why rule 11 states three bounds. A rate is `numeric(14,2)` and
    admits twelve digits before the point, so a legal quantity and a legal rate
    still make an illegal line."""
    with pytest.raises(PricingError) as err:
        compute_line(rate=D("100000"), qty=MAX_QTY, discount_pct=ZERO, slab=D("5"),
                     intra_state=True)
    assert err.value.code == "line_total_too_large"
    assert MAX_QTY * D("100000") > MAX_LINE_TOTAL


def test_the_document_total_is_bounded_too() -> None:
    big = line("99999.99", "999", slab="5")
    with pytest.raises(PricingError) as err:
        document_totals(tuple([big] * 20))
    assert err.value.code == "document_total_too_large"
    assert big.total * 20 > MAX_DOCUMENT_TOTAL


@pytest.mark.parametrize(("kwargs", "code"), [
    ({"qty": "0"}, "qty_not_positive"),
    ({"qty": "-1"}, "qty_not_positive"),
    ({"rate": "0"}, "rate_not_positive"),
    ({"rate": "-1.00"}, "rate_not_positive"),
    ({"pct": "-0.01"}, "discount_out_of_range"),
    ({"pct": "100.01"}, "discount_out_of_range"),
])
def test_every_refusal_names_its_code(kwargs: dict[str, str], code: str) -> None:
    args = {"rate": "103.19", "qty": "18", "pct": "0"} | kwargs
    with pytest.raises(PricingError) as err:
        line(args["rate"], args["qty"], pct=args["pct"])
    assert err.value.code == code


def test_a_line_exactly_on_each_bound_is_accepted() -> None:
    """The boundary belongs to the allowed side, on all three."""
    assert line("1.00", str(MAX_QTY)).gross == D("1000000.00")
    ok = compute_line(rate=MAX_LINE_TOTAL, qty=D("1"), discount_pct=ZERO, slab=D("0"),
                      intra_state=True)
    assert ok.gross == MAX_LINE_TOTAL


def test_the_three_ceilings_are_the_figures_rule_11_names() -> None:
    """Written out, not read from the module.

    A test that asserts `MAX_DOCUMENT_TOTAL == MAX_DOCUMENT_TOTAL` passes against
    any value, which is how the document ceiling sat at ten times the figure rule
    11 states until a cross-vendor review priced two 75,000,000 lines and got an
    accepted document (September).
    """
    assert D("1000000") == MAX_QTY
    assert D("99999999.99") == MAX_LINE_TOTAL
    assert D("99999999.99") == MAX_DOCUMENT_TOTAL


def test_a_document_above_the_ceiling_is_refused_however_few_lines() -> None:
    """Two lines under the line ceiling can still break the document ceiling, and
    a zero slab is the case that gets there fastest."""
    big = compute_line(rate=D("75000000.00"), qty=D("1"), discount_pct=ZERO, slab=D("0"),
                       intra_state=True)
    assert big.total == D("75000000.00"), "each line is legal on its own"
    with pytest.raises(PricingError) as err:
        document_totals((big, big))
    assert err.value.code == "document_total_too_large"
    assert err.value.field_path == "lines"


def test_each_component_is_computed_at_half_the_rate_not_half_the_tax() -> None:
    """Rule 9, and the one mechanism the mutation check found untested.

    Halving the rate and halving the whole tax differ wherever the full tax lands
    on a half-paisa. Taxable 100.10 at 5 % is 5.005: computed at 2.5 % each side
    it is 2.50 and 2.50, and computing 5.01 and halving it gives 2.51 and 2.51 -
    two paise more tax than is due, on every such line.
    """
    line = compute_line(rate=D("100.10"), qty=D("1"), discount_pct=ZERO, slab=D("5"),
                        intra_state=True)
    assert line.taxable == D("100.10")
    assert line.cgst == line.sgst == D("2.50")
    assert line.cgst + line.sgst == D("5.00")

    whole = round2(line.taxable * D("5") / D("100"))
    assert whole == D("5.01"), "the full tax does round up, which is what makes this a test"
    assert line.cgst + line.sgst != whole


def test_the_document_total_covers_every_line_including_repeats() -> None:
    """A quotation may carry the same product twice, at the same quantity and the
    same rate, on two lines. Summing anything that collapses equal values loses
    one of them silently."""
    one = compute_line(rate=D("103.19"), qty=D("18"), discount_pct=ZERO, slab=D("5"),
                       intra_state=True)
    doubled = document_totals((one, one))
    assert doubled.total == one.total * 2
    assert doubled.taxable == one.taxable * 2
    assert doubled.cgst == one.cgst * 2
