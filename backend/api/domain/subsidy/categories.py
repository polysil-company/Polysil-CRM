"""The category table (FS-008 rules 10, 10b, 11, 17, 21).

One row per category. Regular rows cap the subsidy on the Jantri with the sump
(and, when a per-hectare cap is configured, on area times the cap); the farmer's
share subtracts the sump because it is the farmer's own. Seven-year rows cap on
the seven-year Jantri and apply only inside the area window. Every row carries
the workbook's exact figures (`exact`) and the paisa figures the quotation
prints (`money`), which tie: `subsidy + farmer_share - total_gst + sump =
cost` holds on the rounded values because every term of that identity is
rounded first and the share is derived last (rule 10b).
"""

from __future__ import annotations

from decimal import Decimal

from api.domain.subsidy.money import ZERO, as_pct, round2
from api.domain.subsidy.types import Category, CategoryMoney, CategoryResult, JantriFigures

NOT_APPLICABLE = CategoryMoney(ZERO, ZERO, ZERO, None)
SEVEN_YEAR_OUTSIDE_WINDOW = "area_outside_7y_window"


def category_rows(categories: tuple[Category, ...], *, cost: Decimal, total_gst: Decimal,
                  sump: Decimal, area: Decimal, jantri: JantriFigures,
                  seven_year_applicable: bool,
                  gsdma_max_area: Decimal | None) -> tuple[CategoryResult, ...]:
    rows = []
    for cat in sorted(categories, key=lambda c: c.sort_order):
        if cat.variant == "seven_year":
            if not seven_year_applicable or jantri.seven_year is None:
                rows.append(CategoryResult(cat.code, cat.name, cat.pct, cat.variant, False,
                                           SEVEN_YEAR_OUTSIDE_WINDOW, NOT_APPLICABLE,
                                           NOT_APPLICABLE))
                continue
            rows.append(_row(cat, cost=cost, total_gst=total_gst, sump=ZERO, area=area,
                             basis=jantri.seven_year, gsdma=None))
        else:
            gsdma = None
            if cat.gsdma_pct is not None:
                # Rule 17: Mini 'Quo Summary'!Q43 = IF(area<=2, cost*0.1 + gst - sump, 0)
                inside = gsdma_max_area is not None and area <= gsdma_max_area
                gsdma = (cost * as_pct(cat.gsdma_pct) + total_gst - sump) if inside else ZERO
            rows.append(_row(cat, cost=cost, total_gst=total_gst, sump=sump, area=area,
                             basis=jantri.regular_for_cap, gsdma=gsdma))
    return tuple(rows)


def _row(cat: Category, *, cost: Decimal, total_gst: Decimal, sump: Decimal, area: Decimal,
         basis: Decimal, gsdma: Decimal | None) -> CategoryResult:
    pct = as_pct(cat.pct)
    # Drip 'Quo Summary'!Q29 = MIN(O29*70%, $O$27*70%); the capped table adds C27*70000 (rule 11)
    candidates = [cost * pct, basis * pct]
    if cat.per_ha_cap is not None:
        candidates.append(area * cat.per_ha_cap)
    subsidy = min(candidates)
    share = cost - subsidy + total_gst - sump              # R29 = O29-Q29+P29-$I$35
    share_pct = subsidy / cost if cost else ZERO           # Mini Q33 = O33/M33
    exact = CategoryMoney(subsidy, share, share_pct * 100, gsdma)

    cost2, gst2, sump2, subsidy2 = round2(cost), round2(total_gst), round2(sump), round2(subsidy)
    share2 = cost2 - subsidy2 + gst2 - sump2
    pct2 = round2(subsidy2 / cost2 * 100) if cost2 else ZERO
    money = CategoryMoney(subsidy2, share2, pct2, round2(gsdma) if gsdma is not None else None)
    return CategoryResult(cat.code, cat.name, cat.pct, cat.variant, True, None, exact, money)
