"""FS-069: a line's chosen GST slab and the document's freight, in the engine.

The assertions are the ones a reader would otherwise take on trust: freight is
taxed exactly as a line of quantity one, its default slab is the highest among
the goods lines, and freight joins taxable, tax and total but never gross or
discount. That last one is what keeps a discount from slipping past its approval:
017 reads `discount / gross`.
"""

from __future__ import annotations

import datetime as dt
import itertools
from decimal import Decimal

import pytest

from api.domain.pricing.tax import (
    GST_SLABS,
    MAX_DOCUMENT_TOTAL,
    MAX_LINE_TOTAL,
    compute_freight,
    compute_line,
    default_freight_slab,
    document_totals,
)
from api.domain.pricing.types import (
    PricedLine,
    PriceList,
    PricingError,
    Product,
    Rate,
    TaxRate,
)
from api.domain.quotations import freight_rates, goods_subtotal, shared_rate

D = Decimal
ZERO = D(0)
DOMESTIC = [D(s) for s in ("0", "5", "18", "40")]


def freight(amount: str, slab: str, *, intra: bool = True, chosen: bool = True):
    return compute_freight(amount=D(amount), slab=D(slab), chosen=chosen, intra_state=intra)


# ── the 40 % slab ────────────────────────────────────────────────────────────

def test_the_slab_list_has_the_councils_40_and_keeps_the_old_slabs() -> None:
    assert D("40") in GST_SLABS
    assert {D("12"), D("28")} <= set(GST_SLABS)   # documents dated before 22 Sep 2025


@pytest.mark.parametrize("intra", [True, False])
def test_a_line_at_40_splits_into_two_halves_of_20(intra: bool) -> None:
    m = compute_line(rate=D("1000"), qty=D("1"), slab=D("40"), intra_state=intra)
    if intra:
        assert (m.cgst_rate, m.sgst_rate, m.cgst, m.sgst) == (D(20), D(20), D("200.00"),
                                                             D("200.00"))
    else:
        assert (m.igst_rate, m.igst) == (D(40), D("400.00"))
    assert m.total == D("1400.00")


# ── freight is a line of quantity one ────────────────────────────────────────

@pytest.mark.parametrize(("amount", "slab", "intra"), list(itertools.product(
    ("0.01", "1.00", "99.99", "1500.00", "12345.67"), DOMESTIC, (True, False))))
def test_freight_is_taxed_exactly_as_a_line_of_quantity_one(amount: str, slab: str,
                                                            intra: bool) -> None:
    f = freight(amount, slab, intra=intra)
    line = compute_line(rate=D(amount), qty=D("1"), slab=D(slab), intra_state=intra)
    assert f.money == line
    assert f.money.cgst == f.money.sgst
    assert f.money.total == f.money.taxable + f.money.cgst + f.money.sgst + f.money.igst
    assert f.money.discount == ZERO and f.money.taxable == D(amount)


def test_freight_at_18_intra_state() -> None:
    f = freight("1500.00", "18")
    assert (f.money.cgst, f.money.sgst, f.money.igst, f.money.total) == (
        D("135.00"), D("135.00"), ZERO, D("1770.00"))


@pytest.mark.parametrize("amount", ["0", "-1", "0.001", "10.555", str(MAX_LINE_TOTAL + D("0.01"))])
def test_freight_refuses_an_amount_that_is_not_rupees_and_paise_above_zero(amount: str) -> None:
    with pytest.raises(PricingError) as e:
        freight(amount, "18")
    assert e.value.code == "freight_amount_invalid"
    assert e.value.field_path == "freight.amount"


def test_freight_refuses_a_slab_the_council_does_not_have() -> None:
    with pytest.raises(PricingError) as e:
        freight("100", "7")
    assert e.value.code == "gst_slab_not_offered"


# ── the default slab ─────────────────────────────────────────────────────────

def test_the_default_is_the_highest_slab_among_the_lines() -> None:
    assert default_freight_slab([D(5), D(18), D(5)]) == D(18)
    assert default_freight_slab([D(0), D(0)]) == ZERO
    assert default_freight_slab([D(40), D(5)]) == D(40)


def test_freight_with_no_lines_is_refused_not_a_crash() -> None:
    with pytest.raises(PricingError) as e:
        default_freight_slab([])
    assert e.value.code == "freight_without_lines"


# ── the totals ───────────────────────────────────────────────────────────────

def test_freight_joins_taxable_tax_and_total_but_never_gross_or_discount() -> None:
    a = compute_line(rate=D("1000"), qty=D("2"), discount_pct=D("10"), slab=D("5"),
                     intra_state=True)
    b = compute_line(rate=D("250"), qty=D("4"), slab=D("18"), intra_state=True)
    f = freight("500.00", "18")
    without = document_totals((a, b))
    t = document_totals((a, b), f)
    assert (t.gross, t.discount) == (without.gross, without.discount)
    assert t.taxable == without.taxable + D("500.00")
    assert (t.cgst, t.sgst) == (without.cgst + D("45.00"), without.sgst + D("45.00"))
    assert t.total == without.total + D("590.00")
    assert t.taxable == t.gross - t.discount + f.amount        # 077's header CHECK
    assert t.total == t.taxable + t.cgst + t.sgst + t.igst


def test_a_discount_share_is_unchanged_by_freight() -> None:
    """The approval reads discount / gross (017). Freight in gross would turn a
    20 % discount into 14.3 % with 40,000 of freight."""
    a = compute_line(rate=D("100000"), qty=D("1"), discount_pct=D("20"), slab=D("18"),
                     intra_state=True)
    t = document_totals((a,), freight("40000.00", "18"))
    assert t.discount / t.gross == D("0.2")


def test_the_document_ceiling_counts_freight() -> None:
    big = compute_line(rate=MAX_DOCUMENT_TOTAL - D("1000"), qty=D("1"), slab=D("0"),
                       intra_state=True)
    document_totals((big,))
    with pytest.raises(PricingError) as e:
        document_totals((big,), freight("2000.00", "0"))
    assert e.value.code == "document_total_too_large"


# ── a chosen line ────────────────────────────────────────────────────────────

def _priced(chosen: Decimal | None, *, provisional_tax: bool = False) -> PricedLine:
    pl = PriceList(id="pl", name="x", state_territory_id=None, channel_tier=None,
                   effective_from=dt.date(2026, 4, 1), effective_to=None, is_provisional=False)
    product = Product(id="p", description="pipe", uom_code="NOS", uom_decimals=0,
                      pack_multiple=None, is_active=True)
    tax = TaxRate(gst_rate_id="g", hsn_code="3917", slab=D("5"), is_provisional=provisional_tax)
    money = compute_line(rate=D("10"), qty=D("1"), slab=chosen if chosen is not None else D(5),
                         intra_state=True)
    return PricedLine(product=product, qty=D(1), discount_pct=ZERO,
                      rate=Rate(price_list_item_id="i", price_list=pl, rate=D("10")),
                      tax=tax, money=money, chosen_slab=chosen)


def test_a_chosen_line_reports_its_slab_and_keeps_the_hsns() -> None:
    p = _priced(D("18"))
    assert (p.slab, p.tax.slab, p.chosen) == (D(18), D(5), True)
    q = _priced(None)
    assert (q.slab, q.chosen) == (D(5), False)


def test_a_chosen_slab_is_never_a_stand_in() -> None:
    assert "gst_slab" in _priced(None, provisional_tax=True).provisional_fields
    assert "gst_slab" not in _priced(D(18), provisional_tax=True).provisional_fields


# ── the print helpers ────────────────────────────────────────────────────────

def test_the_goods_subtotal_takes_the_freight_back_out() -> None:
    assert goods_subtotal({"taxable": "1500.00", "freight_amount": "500.00"}) == D("1000.00")
    assert goods_subtotal({"taxable": "1500.00", "freight_amount": None}) == D("1500.00")
    assert goods_subtotal({"taxable": "1500.00"}) == D("1500.00")


def test_freight_rates_follow_the_slab_and_the_supply() -> None:
    intra = freight_rates({"freight_amount": "1", "freight_slab": "18", "intra_state": True})
    inter = freight_rates({"freight_amount": "1", "freight_slab": "18", "intra_state": False})
    assert intra == {"cgst_rate": D(9), "sgst_rate": D(9), "igst_rate": ZERO}
    assert inter == {"cgst_rate": ZERO, "sgst_rate": ZERO, "igst_rate": D(18)}
    assert freight_rates({"freight_amount": None}) is None


def test_one_rate_label_only_when_lines_and_freight_share_a_slab() -> None:
    lines = [{"cgst_rate": "9", "sgst_rate": "9", "igst_rate": "0"}] * 2
    same = freight_rates({"freight_amount": "1", "freight_slab": "18", "intra_state": True})
    other = freight_rates({"freight_amount": "1", "freight_slab": "5", "intra_state": True})
    assert shared_rate([*lines, same], "cgst_rate") == D(9)
    assert shared_rate([*lines, other], "cgst_rate") is None
