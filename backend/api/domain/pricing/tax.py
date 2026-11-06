"""The commercial GST engine (FS-010 rules 7, 9, 11).

**The one module in this codebase where a bug is a legal problem rather than a
commercial one.** It takes `Decimal` and returns `Decimal`, it never sees the
database, and it has its own test file and its own mutation check.

Two decisions carry the whole thing, and both were arrived at by execution rather
than by reading a rule.

**Round in the order the invoice prints.** Gross, then the discount off the
rounded gross, then the taxable value as the difference:

    gross    = round2(rate * qty)
    discount = round2(gross * pct / 100)
    taxable  = gross - discount            # already two decimals

Rounding once at the end instead differs on 21 of 105 rate, quantity and
percentage combinations, and it produces a quotation whose three printed figures
do not add up. A document showing gross 103.71, less discount 2.59, taxable
101.11 is the paisa an auditor asks about. `taxable` needs no further rounding
because both its terms already have two decimals.

**Each tax component is computed at its own rate and rounded independently.** For
an intra-state supply that means half the slab twice, not the whole slab halved,
so **CGST always equals SGST**. Two consequences are owned here rather than
discovered later:

* on a small line the intra-state tax is a paisa more than the inter-state tax on
  the same value. Taxable 1.00 at 5 % gives 0.03 + 0.03 = 0.06 against IGST 0.05.
  That is correct under per-component rounding and it is what the client's own
  subsidy workbooks do (`'Quo Summary'!I21` and `I22` are the same formula twice);
* the halved rate is carried as an exact `Decimal` and never stored at two
  decimals. Of the slabs in force only 0.25 % halves to three places, and it does
  not apply to this catalogue, but storing the half would be the kind of rounding
  that is invisible until it is not.

**The document total is the sum of rounded lines, never a recomputation.** Those
differ by paise, and paise are what an auditor checks.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from api.domain.money import CENT, HUNDRED, ZERO, round2
from api.domain.pricing.types import (
    DiscountStep,
    DocumentTotals,
    FreightTax,
    LineTax,
    PricingError,
)

# The Council's slabs. 40 % is in force from 22 Sep 2025 (FS-069); 12 and 28 stay
# legal for documents dated before it. Migration 010's `ck_gst_rate_slab`, widened
# by 077, holds the same list.
GST_SLABS: tuple[Decimal, ...] = tuple(Decimal(s) for s in
                                       ("0", "0.25", "3", "5", "12", "18", "28", "40"))

# Rule 11. The quantity bound alone does not bound the line total, because a rate
# is `numeric(14,2)` and admits twelve digits before the point: executed, a
# quantity of 1E+26 makes `round2` raise `InvalidOperation` inside this module,
# and 1E+20 previews cleanly and then overflows the column at save.
MAX_QTY = Decimal("1000000")
MAX_LINE_TOTAL = Decimal("99999999.99")
# Rule 11 sets the document ceiling to the line ceiling, and this constant was ten
# times larger: two zero-rated 75,000,000 lines were accepted as a 150,000,000
# document (cross-vendor review, September).
MAX_DOCUMENT_TOTAL = Decimal("99999999.99")
# FS-005 rule 6: the client's format has three discount columns, not n.
MAX_TIERS = 3


def half(slab: Decimal) -> Decimal:
    """Half a slab, exactly. Never rounded, never stored."""
    return slab / 2


def compute_line(*, rate: Decimal, qty: Decimal, discount_pct: Decimal = ZERO,
                 discounts: Sequence[Decimal] | None = None, slab: Decimal,
                 intra_state: bool) -> LineTax:
    """One line's money, in the order the invoice prints it.

    `discounts` is the cascade: up to three percentages, each taken off the
    running balance and rounded to the paisa before the next applies (FS-005
    rule 6). `discount_pct` is the one-tier spelling, and one tier is the cascade
    with two zero tiers: `round2(balance * 0 / 100)` is exactly 0.00, so the
    figures are identical.
    """
    if qty <= 0:
        raise PricingError("qty_not_positive", "A quantity must be above zero.", "qty")
    if qty > MAX_QTY:
        raise PricingError("qty_too_large", f"A quantity may not exceed {MAX_QTY:f}.", "qty")
    if rate <= 0:
        raise PricingError("rate_not_positive", "A rate must be above zero.", "rate")
    tiers = tuple(discounts) if discounts is not None else (discount_pct,)
    if len(tiers) > MAX_TIERS:
        raise PricingError("too_many_discounts",
                           f"At most {MAX_TIERS} discount tiers.", "discounts")
    for i, pct in enumerate(tiers):
        if not ZERO <= pct <= HUNDRED:
            raise PricingError("discount_out_of_range",
                               "A discount must be between 0 and 100 per cent.",
                               "discount_pct" if i == 0 else f"discount{i + 1}_pct")

    gross = round2(rate * qty)
    if gross > MAX_LINE_TOTAL:
        raise PricingError(
            "line_total_too_large",
            f"A line total may not exceed {MAX_LINE_TOTAL:f}; this one is {gross:f}.", "qty")
    # The cascade. Each tier's amount is rounded before the next tier sees the
    # balance, so every printed column is a printed figure and the columns add up.
    # The client's own sheet applies each tier to the running balance (row 14:
    # 3.15 is 5 % of 63.00, not of 70.00) but does not round between tiers; on
    # its seven lines that is one paisa on the document (GAP-118).
    balance = gross
    steps: list[DiscountStep] = []
    for pct in tiers:
        amount = round2(balance * pct / HUNDRED)
        balance = balance - amount
        steps.append(DiscountStep(pct=pct, amount=amount, after=balance))
    discount = gross - balance
    taxable = balance

    if intra_state:
        component = round2(taxable * half(slab) / HUNDRED)
        return LineTax(gross=gross, discount=discount, taxable=taxable,
                       cgst_rate=half(slab), sgst_rate=half(slab), igst_rate=ZERO,
                       cgst=component, sgst=component, igst=ZERO,
                       total=taxable + component + component, steps=tuple(steps))
    igst = round2(taxable * slab / HUNDRED)
    return LineTax(gross=gross, discount=discount, taxable=taxable,
                   cgst_rate=ZERO, sgst_rate=ZERO, igst_rate=slab,
                   cgst=ZERO, sgst=ZERO, igst=igst,
                   total=taxable + igst, steps=tuple(steps))


def default_freight_slab(slabs: Sequence[Decimal]) -> Decimal:
    """FS-069 rule 7: the highest slab among the goods lines, each line's own slab,
    chosen or not, a zero-taxable line included. The owner's rule; the legal rule
    for a composite supply is the principal supply's rate (GAP-510)."""
    if not slabs:
        raise PricingError("freight_without_lines",
                           "Freight needs at least one goods line.", "freight")
    return max(slabs)


def compute_freight(*, amount: Decimal, slab: Decimal, chosen: bool,
                    intra_state: bool) -> FreightTax:
    """FS-069 rules 5, 6 and 8: freight is taxed as a line of quantity one, with no
    discount, so it rounds and splits CGST and SGST exactly as a line does."""
    if amount <= 0 or amount != amount.quantize(CENT) or amount > MAX_LINE_TOTAL:
        raise PricingError(
            "freight_amount_invalid",
            f"Freight must be above zero, at most {MAX_LINE_TOTAL:f}, in rupees and paise.",
            "freight.amount")
    if slab not in GST_SLABS:
        raise PricingError("gst_slab_not_offered", f"{slab:f} % is not a GST slab.",
                           "freight.gst_slab")
    money = compute_line(rate=amount, qty=Decimal("1"), slab=slab, intra_state=intra_state)
    return FreightTax(amount=amount, slab=slab, chosen=chosen, money=money)


def document_totals(lines: tuple[LineTax, ...],
                    freight: FreightTax | None = None) -> DocumentTotals:
    """The sum of rounded lines. Not a recomputation on the summed taxable value:
    those differ by paise, and a hundred-line document diverges by rupees.

    Freight (FS-069 rule 8) joins taxable, the taxes and the total, never gross or
    discount: the discount approval reads `discount / gross` (017), and freight in
    `gross` would dilute a discount past its limit. So on the header
    `taxable = gross - discount + freight`."""
    extra = freight.money if freight is not None else None
    totals = DocumentTotals(
        gross=sum((ln.gross for ln in lines), ZERO),
        discount=sum((ln.discount for ln in lines), ZERO),
        taxable=sum((ln.taxable for ln in lines), ZERO) + (extra.taxable if extra else ZERO),
        cgst=sum((ln.cgst for ln in lines), ZERO) + (extra.cgst if extra else ZERO),
        sgst=sum((ln.sgst for ln in lines), ZERO) + (extra.sgst if extra else ZERO),
        igst=sum((ln.igst for ln in lines), ZERO) + (extra.igst if extra else ZERO),
        total=sum((ln.total for ln in lines), ZERO) + (extra.total if extra else ZERO),
    )
    if totals.total > MAX_DOCUMENT_TOTAL:
        raise PricingError("document_total_too_large",
                           f"A document total may not exceed {MAX_DOCUMENT_TOTAL:f}.", "lines")
    return totals
