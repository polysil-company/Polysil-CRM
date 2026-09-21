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

from decimal import Decimal

from api.domain.money import HUNDRED, ZERO, round2
from api.domain.pricing.types import (
    DocumentTotals,
    LineTax,
    PricingError,
)

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


def half(slab: Decimal) -> Decimal:
    """Half a slab, exactly. Never rounded, never stored."""
    return slab / 2


def compute_line(*, rate: Decimal, qty: Decimal, discount_pct: Decimal, slab: Decimal,
                 intra_state: bool) -> LineTax:
    """One line's money, in the order the invoice prints it."""
    if qty <= 0:
        raise PricingError("qty_not_positive", "A quantity must be above zero.", "qty")
    if qty > MAX_QTY:
        raise PricingError("qty_too_large", f"A quantity may not exceed {MAX_QTY:f}.", "qty")
    if rate <= 0:
        raise PricingError("rate_not_positive", "A rate must be above zero.", "rate")
    if not ZERO <= discount_pct <= HUNDRED:
        raise PricingError("discount_out_of_range",
                           "A discount must be between 0 and 100 per cent.", "discount_pct")

    gross = round2(rate * qty)
    if gross > MAX_LINE_TOTAL:
        raise PricingError(
            "line_total_too_large",
            f"A line total may not exceed {MAX_LINE_TOTAL:f}; this one is {gross:f}.", "qty")
    discount = round2(gross * discount_pct / HUNDRED)
    taxable = gross - discount

    if intra_state:
        component = round2(taxable * half(slab) / HUNDRED)
        return LineTax(gross=gross, discount=discount, taxable=taxable,
                       cgst_rate=half(slab), sgst_rate=half(slab), igst_rate=ZERO,
                       cgst=component, sgst=component, igst=ZERO,
                       total=taxable + component + component)
    igst = round2(taxable * slab / HUNDRED)
    return LineTax(gross=gross, discount=discount, taxable=taxable,
                   cgst_rate=ZERO, sgst_rate=ZERO, igst_rate=slab,
                   cgst=ZERO, sgst=ZERO, igst=igst,
                   total=taxable + igst)


def document_totals(lines: tuple[LineTax, ...]) -> DocumentTotals:
    """The sum of rounded lines. Not a recomputation on the summed taxable value:
    those differ by paise, and a hundred-line document diverges by rupees."""
    totals = DocumentTotals(
        gross=sum((ln.gross for ln in lines), ZERO),
        discount=sum((ln.discount for ln in lines), ZERO),
        taxable=sum((ln.taxable for ln in lines), ZERO),
        cgst=sum((ln.cgst for ln in lines), ZERO),
        sgst=sum((ln.sgst for ln in lines), ZERO),
        igst=sum((ln.igst for ln in lines), ZERO),
        total=sum((ln.total for ln in lines), ZERO),
    )
    if totals.total > MAX_DOCUMENT_TOTAL:
        raise PricingError("document_total_too_large",
                           f"A document total may not exceed {MAX_DOCUMENT_TOTAL:f}.", "lines")
    return totals
