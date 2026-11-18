"""Property tests for the GST engine (test build-out 4, FS-010 rules 7, 9, 11).

The example tests pin figures the client's workbooks give. These state what must
hold for every line Hypothesis can think of: the printed columns add up, every
figure is in paise, CGST equals SGST, the cascade is what the steps say, and a bad
input is a PricingError, never a crash.
"""

# ruff: noqa: E501  (strategies read better on one line)

from __future__ import annotations

from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from api.domain.money import CENT, HUNDRED, ZERO, round2
from api.domain.pricing.tax import (
    GST_SLABS,
    MAX_LINE_TOTAL,
    MAX_QTY,
    compute_freight,
    compute_line,
    document_totals,
)
from api.domain.pricing.types import PricingError

PAISA = Decimal("0.01")

rates = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("250000"), places=2)
qtys = st.decimals(min_value=Decimal("0.001"), max_value=Decimal("5000"), places=3)
pcts = st.decimals(min_value=ZERO, max_value=HUNDRED, places=2)
slabs = st.sampled_from(GST_SLABS)
cascades = st.lists(pcts, min_size=1, max_size=3)


def _paise(x: Decimal) -> bool:
    return x == x.quantize(CENT)


@settings(max_examples=600)
@given(rate=rates, qty=qtys, tiers=cascades, slab=slabs, intra=st.booleans())
def test_the_printed_columns_add_up_in_paise(rate: Decimal, qty: Decimal, tiers: list[Decimal],
                                              slab: Decimal, intra: bool) -> None:
    assume(round2(rate * qty) <= MAX_LINE_TOTAL)
    ln = compute_line(rate=rate, qty=qty, discounts=tiers, slab=slab, intra_state=intra)
    assert ln.gross == round2(rate * qty)
    assert ln.gross - ln.discount == ln.taxable
    assert ln.taxable + ln.cgst + ln.sgst + ln.igst == ln.total
    for figure in (ln.gross, ln.discount, ln.taxable, ln.cgst, ln.sgst, ln.igst, ln.total):
        assert _paise(figure) and figure >= ZERO
    if intra:
        assert ln.cgst == ln.sgst and ln.igst == ZERO
        assert ln.cgst_rate == ln.sgst_rate == slab / 2
    else:
        assert ln.cgst == ln.sgst == ZERO and ln.igst_rate == slab


@settings(max_examples=400)
@given(rate=rates, qty=qtys, tiers=cascades, slab=slabs)
def test_the_cascade_is_what_its_steps_say(rate: Decimal, qty: Decimal, tiers: list[Decimal],
                                           slab: Decimal) -> None:
    assume(round2(rate * qty) <= MAX_LINE_TOTAL)
    ln = compute_line(rate=rate, qty=qty, discounts=tiers, slab=slab, intra_state=False)
    balance = ln.gross
    assert len(ln.steps) == len(tiers)
    for step, pct in zip(ln.steps, tiers, strict=True):
        assert step.pct == pct
        assert step.amount == round2(balance * pct / HUNDRED)
        balance -= step.amount
        assert step.after == balance
    assert sum((s.amount for s in ln.steps), ZERO) == ln.discount
    assert ln.taxable == balance


@settings(max_examples=400)
@given(rate=rates, qty=qtys, pct=pcts, slab=slabs)
def test_intra_and_inter_state_tax_differ_by_at_most_a_paisa(rate: Decimal, qty: Decimal, pct: Decimal,
                                                             slab: Decimal) -> None:
    """Per-component rounding: two half-slab roundings against one whole-slab one."""
    assume(round2(rate * qty) <= MAX_LINE_TOTAL)
    intra = compute_line(rate=rate, qty=qty, discount_pct=pct, slab=slab, intra_state=True)
    inter = compute_line(rate=rate, qty=qty, discount_pct=pct, slab=slab, intra_state=False)
    assert intra.taxable == inter.taxable
    assert abs((intra.cgst + intra.sgst) - inter.igst) <= PAISA


@settings(max_examples=300)
@given(rate=rates, qty=qtys, low=pcts, high=pcts, slab=slabs)
def test_a_bigger_discount_never_raises_the_taxable_value(rate: Decimal, qty: Decimal, low: Decimal,
                                                          high: Decimal, slab: Decimal) -> None:
    assume(round2(rate * qty) <= MAX_LINE_TOTAL)
    lo, hi = sorted((low, high))
    a = compute_line(rate=rate, qty=qty, discount_pct=lo, slab=slab, intra_state=True)
    b = compute_line(rate=rate, qty=qty, discount_pct=hi, slab=slab, intra_state=True)
    assert b.taxable <= a.taxable and b.total <= a.total


@given(rate=rates, qty=qtys, slab=slabs, intra=st.booleans())
def test_a_full_discount_leaves_nothing_to_tax(rate: Decimal, qty: Decimal, slab: Decimal, intra: bool) -> None:
    assume(round2(rate * qty) <= MAX_LINE_TOTAL)
    ln = compute_line(rate=rate, qty=qty, discount_pct=HUNDRED, slab=slab, intra_state=intra)
    assert ln.taxable == ln.total == ln.cgst == ln.igst == ZERO


@settings(max_examples=500)
@given(rate=st.decimals(min_value=Decimal("-1000"), max_value=Decimal("999999999999.99"), places=2),
       qty=st.decimals(min_value=Decimal("-10"), max_value=MAX_QTY * 10, places=3),
       tiers=st.lists(st.decimals(min_value=Decimal("-50"), max_value=Decimal("150"), places=2),
                      min_size=1, max_size=5),
       slab=slabs, intra=st.booleans())
def test_a_bad_line_is_a_pricing_error_never_a_crash(rate: Decimal, qty: Decimal, tiers: list[Decimal],
                                                     slab: Decimal, intra: bool) -> None:
    """Rule 11: whatever arrives, the answer is figures or a PricingError naming the
    field. An InvalidOperation or an overflow at save is the failure this guards."""
    try:
        ln = compute_line(rate=rate, qty=qty, discounts=tiers, slab=slab, intra_state=intra)
    except PricingError as exc:
        assert exc.args, "a PricingError carries its code"
        return
    assert ln.total <= MAX_LINE_TOTAL * 2 and _paise(ln.total)


@settings(max_examples=300)
@given(lines=st.lists(st.tuples(rates, qtys, pcts, slabs), min_size=1, max_size=12),
       freight=st.one_of(st.none(), st.decimals(min_value=Decimal("1"), max_value=Decimal("50000"), places=2)),
       intra=st.booleans())
def test_the_document_is_the_sum_of_its_rounded_lines(lines: list[tuple[Decimal, Decimal, Decimal, Decimal]],
                                                      freight: Decimal | None, intra: bool) -> None:
    """Never a recomputation on the summed taxable value; freight joins taxable and
    tax, never gross or discount (FS-069 rule 8)."""
    taxed = tuple(compute_line(rate=r, qty=q, discount_pct=p, slab=s, intra_state=intra)
                  for r, q, p, s in lines if round2(r * q) <= Decimal("5000000"))
    assume(taxed)
    f = (compute_freight(amount=freight, slab=max(s for *_, s in lines), chosen=False, intra_state=intra)
         if freight is not None else None)
    t = document_totals(taxed, f)
    assert t.gross == sum((ln.gross for ln in taxed), ZERO)
    assert t.discount == sum((ln.discount for ln in taxed), ZERO)
    extra = f.money.total if f else ZERO
    assert t.total == sum((ln.total for ln in taxed), ZERO) + extra
    assert t.taxable == t.gross - t.discount + (f.money.taxable if f else ZERO)
    assert t.taxable + t.cgst + t.sgst + t.igst == t.total


@given(st.decimals(min_value=Decimal("-1000000"), max_value=Decimal("1000000"), places=6))
def test_round2_is_half_away_from_zero_and_stable(x: Decimal) -> None:
    r = round2(x)
    assert _paise(r) and round2(r) == r
    assert abs(r - x) <= Decimal("0.005")
    if abs(r - x) == Decimal("0.005"):
        assert abs(r) > abs(x), "a half paisa rounds away from zero, never to even"
