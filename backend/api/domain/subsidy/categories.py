"""The category table (FS-008 rules 10, 10b, 11, 17, 21).

One row per category. Regular rows cap the subsidy on the Jantri with the sump
(and, when a per-hectare cap is configured, on area times the cap); the farmer's
share subtracts the sump because it is the farmer's own. Seven-year rows cap on
the seven-year Jantri and apply only inside the area window. Every row carries
the workbook's exact figures (`exact`) and the paisa figures the quotation
prints (`money`), which tie: `subsidy + farmer_share - total_gst + sump =
cost` holds on the rounded values because every term of that identity is
rounded first and the share is derived last (rule 10b).

FS-056 adds two cap modes for other states' workbooks. `incl_gst`: the subsidy
caps on MIN(unit cost, total incl GST), no sump, and the share is that total
less the subsidy (floored at 0 where the workbook wraps it in MAX). Then
`unit_cost_only` (RJ drip): the subsidy is the percent of the unit cost, uncapped,
and the share MAX(total - subsidy, 0). A flat charge outside the cap (CG's
inspection) is added to the share in both.

FS-063 adds `excl_gst` (AP): the subsidy caps on MIN(unit cost, cost before GST)
and an optional rupee ceiling; the farmer pays the cost less the subsidy plus his
fraction of the GST. The state pays the rest of the GST (`state_gst`).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from api.domain.subsidy.money import ZERO, as_pct, round2
from api.domain.subsidy.types import Category, CategoryMoney, CategoryResult, JantriFigures

NOT_APPLICABLE = CategoryMoney(ZERO, ZERO, ZERO, None)
SEVEN_YEAR_OUTSIDE_WINDOW = "area_outside_7y_window"
CAP_MODES = ("ggrc", "incl_gst", "unit_cost_only", "excl_gst")


def category_rows(categories: tuple[Category, ...], *, cost: Decimal, total_gst: Decimal,
                  sump: Decimal, area: Decimal, jantri: JantriFigures,
                  seven_year_applicable: bool,
                  gsdma_max_area: Decimal | None, cap_mode: str = "ggrc",
                  share_floor_zero: bool = False,
                  share_extra: Decimal = ZERO, subsidy_cap: Decimal | None = None,
                  farmer_gst_fraction: Decimal = Decimal(1),
                  round_rupee: bool = False) -> tuple[CategoryResult, ...]:
    if cap_mode not in CAP_MODES:
        raise ValueError(f"unknown cap mode {cap_mode!r}")
    if cap_mode == "excl_gst":
        if not 0 <= farmer_gst_fraction <= 1:
            raise ValueError(f"farmer_gst_fraction {farmer_gst_fraction} is outside 0 to 1")
        return tuple(_excl_gst_row(cat, cost=cost, gst=total_gst, area=area,
                                   basis=jantri.regular_for_cap, floor=share_floor_zero,
                                   ceiling=subsidy_cap, fraction=farmer_gst_fraction,
                                   round_rupee=round_rupee)
                     for cat in sorted(categories, key=lambda c: c.sort_order)
                     if cat.variant != "seven_year")
    if cap_mode != "ggrc":
        return tuple(_state_row(cat, total=cost + total_gst, cost=cost, area=area,
                                basis=jantri.regular_for_cap, cap_mode=cap_mode,
                                floor=share_floor_zero or cap_mode == "unit_cost_only",
                                extra=share_extra)
                     for cat in sorted(categories, key=lambda c: c.sort_order)
                     if cat.variant != "seven_year")
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


def _state_row(cat: Category, *, total: Decimal, cost: Decimal, area: Decimal, basis: Decimal,
               cap_mode: str, floor: bool, extra: Decimal) -> CategoryResult:
    """FS-056 rules 2 to 4."""
    pct = as_pct(cat.pct)
    candidates = [basis * pct] if cap_mode == "unit_cost_only" else [basis * pct, total * pct]
    if cat.per_ha_cap is not None:
        candidates.append(area * cat.per_ha_cap)
    subsidy = min(candidates)

    def share_of(t: Decimal, s: Decimal) -> Decimal:
        rest = t - s
        return (max(rest, ZERO) if floor else rest) + extra

    exact = CategoryMoney(subsidy, share_of(total, subsidy),
                          subsidy / total * 100 if total else ZERO, None)
    total2, subsidy2 = round2(total), round2(subsidy)
    money = CategoryMoney(subsidy2, share_of(total2, subsidy2) - extra + round2(extra),
                          round2(subsidy2 / total2 * 100) if total2 else ZERO, None)
    return CategoryResult(cat.code, cat.name, cat.pct, cat.variant, True, None, exact, money)


def state_gst(cost: Decimal, gst: Decimal, fraction: Decimal) -> Decimal:
    """FS-063 rule 3: the GST the state pays, on paisa figures, taken as the
    remainder so subsidy + share + state GST = the printed total exactly."""
    if fraction >= 1:
        return ZERO
    return round2(cost + gst) - round2(cost) - round2(gst * fraction)


def _excl_gst_row(cat: Category, *, cost: Decimal, gst: Decimal, area: Decimal, basis: Decimal,
                  floor: bool, ceiling: Decimal | None, fraction: Decimal,
                  round_rupee: bool) -> CategoryResult:
    """FS-063 rules 1 to 5. AP sprinkler 'Unit Cost & Calculation'!J8 =
    MIN(MIN(I6,I7)*I8,19000), K8 = I7 - J8 + I28; AP drip K79 = 90 % x guided cost."""
    pct = as_pct(cat.pct)
    candidates = [basis * pct, cost * pct]
    if cat.per_ha_cap is not None:
        candidates.append(area * cat.per_ha_cap)
    if ceiling is not None:
        candidates.append(ceiling)
    subsidy = max(min(candidates), ZERO)
    if round_rupee:
        subsidy = subsidy.quantize(Decimal(1), rounding=ROUND_HALF_UP)

    def share_of(c: Decimal, s: Decimal, g: Decimal) -> Decimal:
        rest = c - s + g
        return max(rest, ZERO) if floor else rest

    farmer_gst = gst * fraction
    exact = CategoryMoney(subsidy, share_of(cost, subsidy, farmer_gst),
                          subsidy / cost * 100 if cost else ZERO, None)
    # the total is printed as round2(cost + gst); the share takes round2(cost) and the
    # state GST the remainder (state_gst), so the three printed figures add up
    cost2, subsidy2 = round2(cost), round2(subsidy)
    farmer_gst2 = round2(cost + gst) - cost2 - state_gst(cost, gst, fraction)
    money = CategoryMoney(subsidy2, share_of(cost2, subsidy2, farmer_gst2),
                          round2(subsidy2 / cost2 * 100) if cost2 else ZERO, None)
    return CategoryResult(cat.code, cat.name, cat.pct, cat.variant, True, None, exact, money)


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
