"""The Sprinkler pipeline: blocks A and B, quantities derived from area, a
one-dimensional Jantri (FS-008 rules 18 to 22).

`BOQ!H16:J25` derive every line: the quantity from the quantity matrix at the
exact area, the rate from the component rates by pipe size (75 mm up to 2.0 Ha,
90 mm from 2.01, rule 19) or by nozzle type, the amount rounded. Then `R20:R31`:
A = lines + transportation with 2.5 % + 2.5 %, B = inspection at 0.4 % of A
floored at 200 with 9 % + 9 %, the cost of SIS, the GST totals, the grand
total; every cell rounded but the inspection itself. The categories cap on
`MIN(cost, area Jantri)`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from api.domain.subsidy.categories import category_rows
from api.domain.subsidy.defaults import SPRINKLER_COMPONENT_ORDER
from api.domain.subsidy.jantri import Matrix2D, lookup_1d
from api.domain.subsidy.money import ZERO
from api.domain.subsidy.types import (
    Blocks,
    CropResult,
    JantriFigures,
    Masters,
    QuantityMatrix,
    QuotationInput,
    QuotationResult,
    SprinklerFigures,
    SprinklerLine,
    SubsidyError,
    SystemPolicy,
)

NOZZLES = ("plastic", "brass")


def size_for(area: Decimal, band_ha: Decimal) -> int:
    """Rule 19: 'SPRINKLER 13.06.2026'!E6 = 75 MM heads the columns up to 2.0 Ha,
    N6 = 90 MM from 2.01 (GAP-083)."""
    return 75 if area <= band_ha else 90


def quantities_for(matrix: QuantityMatrix, area: Decimal, *,
                   required: bool = True) -> Mapping[str, Decimal]:
    """Rule 18: exact match on the tabulated area, as `MATCH(..., 0)` matches.
    `required` is `subsidy_parameter.exact_area_match_required`, which is where
    the client's answer to GAP-076 will land."""
    if area not in matrix.areas:
        if required:
            raise SubsidyError("exact_area_match_required", _steps_message(matrix.areas, area),
                               "area")
        raise SubsidyError("exact_area_match_required",
                           "rounding an off-step area is not built; see GAP-076", "area")
    return {code: row[area] for code, row in matrix.rows.items()}


def _steps_message(areas: tuple[Decimal, ...], area: Decimal) -> str:
    return (f"Sprinkler areas are tabulated at {', '.join(str(a) for a in areas)} Ha; "
            f"{area} is not one of them")


def field_inspection(q: QuotationInput, masters: Masters, policy: SystemPolicy) -> QuotationResult:
    if len(q.crops) != 1:
        raise SubsidyError("crop_count", "Sprinkler quotes one crop", "crops")
    if q.nozzle not in NOZZLES:
        raise SubsidyError("nozzle", "nozzle must be plastic or brass", "nozzle")
    if masters.quantities is None or isinstance(masters.regular, Matrix2D) \
            or isinstance(masters.seven_year, Matrix2D):
        raise SubsidyError("matrix_shape",
                           "sprinkler needs a quantity matrix and one-dimensional tables")
    crop = q.crops[0]
    if crop.area <= 0:
        raise SubsidyError("zero_area", "a crop's area must be positive", "area")
    r = policy.rounding
    area = crop.area
    size = size_for(area, policy.pipe_size_band_ha)
    qty = quantities_for(masters.quantities, area, required=policy.exact_area_match_required)

    lines: list[SprinklerLine] = []
    for code in SPRINKLER_COMPONENT_ORDER:
        if code == "nozzle":
            rate = masters.rate_for("nozzle", nozzle=q.nozzle)
            quantity = qty[f"nozzle_{q.nozzle}"]
        else:
            rate = masters.rate_for(code, pipe_size_mm=size)
            quantity = qty[code]
        lines.append(SprinklerLine(code, rate.description, rate.uom, quantity, rate.rate,
                                   r.line("field", rate.rate * quantity)))
    before_transport = sum((ln.amount for ln in lines), ZERO)          # BOQ!J24
    transport = masters.rate_for("transport")
    # J25 = ROUND(I25*H25,2), where H25 = J11, the area. The quantity matrix carries
    # the same figure per column, and reading it there means a workbook revision to
    # that row is honoured rather than silently ignored (code review F-11).
    transport_qty = qty.get("transport", area)
    lines.append(SprinklerLine("transport", transport.description, transport.uom, transport_qty,
                               transport.rate, r.line("transport", transport.rate * transport_qty)))

    a = before_transport + lines[-1].amount                              # R20 = J26
    cgst_a = r.block("gst_ab", a * policy.gst_material_half)             # R21, R22
    with_gst = r.block("dbt", a + cgst_a + cgst_a)                       # R23, J29
    inspection_before = r.block("inspection", a * policy.inspection_rate)   # Q46 = R20*0.4/100
    inspection = max(inspection_before, policy.inspection_floor)         # R24
    cgst_b = r.block("gst_e", inspection * policy.gst_service_half)      # R25, R26
    cost = r.block("cost_of_mis", a + inspection)                        # R27
    total_cgst = r.block("gst_totals", cgst_a + cgst_b)                  # R28, R29
    total_gst = r.block("total_gst", total_cgst + total_cgst)            # R30
    blocks = Blocks(
        field_unit=a, a_plus_b=a, cgst_ab=cgst_a, sgst_ab=cgst_a, total_abc_gst=with_gst,
        inspection_before_floor=inspection_before, inspection=inspection, cgst_e=cgst_b,
        sgst_e=cgst_b,
        cost_excl_gst=cost, total_cgst=total_cgst, total_sgst=total_cgst, total_gst=total_gst,
        total_incl_gst=r.block("total_incl_gst", cost + total_gst),     # R31
    )

    regular = lookup_1d(masters.regular, area)
    seven_year = lookup_1d(masters.seven_year, area)
    if regular is None or seven_year is None:
        raise SubsidyError("exact_area_match_required",
                           _steps_message(tuple(masters.regular), area), "area")
    seven_year_ok = policy.seven_year_area_min <= area <= policy.seven_year_area_max
    jantri = JantriFigures(regular, regular, regular, seven_year if seven_year_ok else None,
                           ZERO, crop.lateral_spacing, None)
    categories = category_rows(masters.categories, cost=cost, total_gst=total_gst, sump=ZERO,
                               area=area, jantri=jantri, seven_year_applicable=seven_year_ok,
                               gsdma_max_area=None)
    result = CropResult(crop.crop, crop.inter_crop, area, crop.lateral_spacing, jantri, blocks,
                        categories, ())
    figures = SprinklerFigures(size, tuple(lines), before_transport, with_gst)
    warnings = () if seven_year_ok else ("seven_year_not_applicable: area outside the window",)
    return QuotationResult(q.system_type, (result,), blocks, figures, warnings)
