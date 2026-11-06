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

from api.domain.subsidy.categories import category_rows, state_gst
from api.domain.subsidy.defaults import SPRINKLER_COMPONENT_ORDER
from api.domain.subsidy.jantri import Matrix2D, RowTable, between_1d, lookup_1d
from api.domain.subsidy.money import ZERO, round2
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
SET_SIZES = (63, 75, 90, 110)      # FS-056 rule 7


def size_for(area: Decimal, band_ha: Decimal) -> int:
    """Rule 19: 'SPRINKLER 13.06.2026'!E6 = 75 MM heads the columns up to 2.0 Ha,
    N6 = 90 MM from 2.01 (GAP-083)."""
    return 75 if area <= band_ha else 90


def required_rates(areas: tuple[Decimal, ...],
                   band_ha: Decimal) -> tuple[tuple[str, int | None, str | None], ...]:
    """Every `rate_for` lookup `field_inspection` can make over these tabulated
    areas, as (code, pipe size, nozzle). The readiness panel checks a new scheme
    against this list, so it names the rate a calculation would refuse on
    (FS-039 §4). A test holds it equal to what `field_inspection` asks for."""
    sizes = sorted({size_for(a, band_ha) for a in areas})
    out: list[tuple[str, int | None, str | None]] = []
    for code in SPRINKLER_COMPONENT_ORDER:
        if code == "nozzle":
            out.extend(("nozzle", None, n) for n in NOZZLES)
        else:
            out.extend((code, s, None) for s in sizes)
    out.append(("transport", None, None))
    return tuple(out)


def missing_quantity_rows(matrix: QuantityMatrix, *, every_part: bool = True) -> tuple[str, ...]:
    """The rows `field_inspection` reads that the table lacks, or holds without
    every tabulated area: each one would be a KeyError mid-calculation (FS-039
    code review F-1). Transport is optional: the area stands in for it. Any row
    present must hold every area, since `quantities_for` reads every row."""
    wanted = [c for c in SPRINKLER_COMPONENT_ORDER if c != "nozzle"]
    wanted += [f"nozzle_{n}" for n in NOZZLES]
    if not every_part:
        # FS-056: a state sheet quotes the parts it lists; each must cover every area
        wanted = []
    wanted += sorted(c for c in matrix.rows if c not in wanted)
    rows = matrix.rows
    return tuple(code for code in wanted
                 if code not in rows or any(a not in rows[code] for a in matrix.areas))


def quantities_for(matrix: QuantityMatrix, area: Decimal, *,
                   required: bool = True) -> Mapping[str, Decimal]:
    """Rule 18: exact match on the tabulated area, as `MATCH(..., 0)` matches.
    `required` is `subsidy_parameter.exact_area_match_required`. Off it (FS-055
    rule 20, GAP-076), an area between two steps takes the next step up: the
    field needs at least that much material, and part of a pipe is not supplied.
    Outside the table stays refused."""
    if area in matrix.areas:
        return {code: row[area] for code, row in matrix.rows.items()}
    if required or not matrix.areas or not matrix.areas[0] < area < matrix.areas[-1]:
        raise SubsidyError("exact_area_match_required", _steps_message(matrix.areas, area), "area")
    upper = min(a for a in matrix.areas if a > area)
    return {code: row[upper] for code, row in matrix.rows.items()}


def _steps_message(areas: tuple[Decimal, ...], area: Decimal) -> str:
    return (f"Sprinkler areas are tabulated at {', '.join(str(a) for a in areas)} Ha; "
            f"{area} is not one of them")


def field_inspection(q: QuotationInput, masters: Masters, policy: SystemPolicy) -> QuotationResult:
    if len(q.crops) != 1:
        raise SubsidyError("crop_count", "Sprinkler quotes one crop", "crops")
    nozzle = q.nozzle
    if nozzle is None and policy.pipe_size_from_input and masters.quantities is not None:
        # FS-056: a state sheet lists one nozzle; that one is quoted
        listed = [n for n in NOZZLES if f"nozzle_{n}" in masters.quantities.rows]
        nozzle = listed[0] if len(listed) == 1 else None
    if nozzle not in NOZZLES:
        raise SubsidyError("nozzle", "nozzle must be plastic or brass", "nozzle")
    if masters.quantities is None or isinstance(masters.regular, Matrix2D) \
            or isinstance(masters.seven_year, Matrix2D | RowTable) \
            or (masters.seven_year is None and policy.cap_mode == "ggrc"):
        raise SubsidyError("matrix_shape",
                           "sprinkler needs a quantity matrix and one-dimensional tables")
    crop = q.crops[0]
    if crop.area <= 0:
        raise SubsidyError("zero_area", "a crop's area must be positive", "area")
    r = policy.rounding
    area = crop.area
    notes: list[str] = []
    if policy.pipe_size_from_input:
        # FS-056 rule 7: the user picks the set size, as the CG, RJ and UP sheets ask
        if q.pipe_size_mm is None:
            raise SubsidyError("pipe_size_required", "this scheme's sprinkler needs the set size",
                               "pipe_size_mm")
        if q.pipe_size_mm not in SET_SIZES:
            raise SubsidyError("pipe_size", "the set size is 63, 75, 90 or 110 mm", "pipe_size_mm")
        size = q.pipe_size_mm
    else:
        size = size_for(area, policy.pipe_size_band_ha)
        if q.pipe_size_mm is not None and q.pipe_size_mm != size:
            notes.append(f"pipe_size_ignored: this scheme sets the size by area; {size} mm used")
    qty = quantities_for(masters.quantities, area, required=policy.exact_area_match_required)
    between = area not in masters.quantities.areas

    lines: list[SprinklerLine] = []
    for code in SPRINKLER_COMPONENT_ORDER:
        if policy.pipe_size_from_input and code != "nozzle" and code not in qty:
            continue        # FS-056: a part the state sheet does not quote
        if code == "nozzle":
            rate = masters.rate_for("nozzle", nozzle=nozzle)
            quantity = qty[f"nozzle_{nozzle}"]
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
    transport_qty = area if between else qty.get("transport", area)   # FS-055 rule 20
    if policy.transport_flat:
        transport_qty = Decimal(1)       # FS-063 EC-3: AP's J22 is 'Fix', at any area
    lines.append(SprinklerLine("transport", transport.description, transport.uom, transport_qty,
                               transport.rate, r.line("transport", transport.rate * transport_qty)))

    a = before_transport + lines[-1].amount                              # R20 = J26
    if policy.rates_include_gst:
        return _gst_inclusive(q, masters, policy, size=size, area=area, lines=lines, a=a,
                              qty_between=between, notes=notes, nozzle=nozzle)
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
        gst_paid_by_state=state_gst(cost, total_gst, policy.farmer_gst_fraction),   # FS-063
    )

    seven_year_ok = policy.seven_year_area_min <= area <= policy.seven_year_area_max
    regular: Decimal | None
    seven_year: Decimal | None
    if isinstance(masters.regular, RowTable):
        # FS-056 rule 8: set size x area; no cell for the size is a unit cost of 0
        regular = masters.regular.stepped(str(size), area)
        if regular is None:
            notes.append(f"no_unit_cost_for_size: the table has no {size} mm value at {area} Ha; "
                         "the unit cost is 0")
            regular = ZERO
        seven_year, seven_year_ok = ZERO, False
    else:
        if between:
            # FS-055 rule 20: the unit cost pro rata between the two steps (PMKSY §9.5)
            regular = between_1d(masters.regular, area)
            seven_year = (between_1d(masters.seven_year, area)
                          if masters.seven_year is not None else None)
            if seven_year is None and not seven_year_ok:
                seven_year = ZERO
        else:
            regular = lookup_1d(masters.regular, area)
            seven_year = (lookup_1d(masters.seven_year, area)
                          if masters.seven_year is not None else None)
        if masters.seven_year is None:
            seven_year, seven_year_ok = ZERO, False
        if regular is None or seven_year is None:
            raise SubsidyError("exact_area_match_required",
                               _steps_message(tuple(masters.regular), area), "area")
    jantri = JantriFigures(regular, regular, regular, seven_year if seven_year_ok else None,
                           ZERO, crop.lateral_spacing, None)
    categories = category_rows(masters.categories, cost=cost, total_gst=total_gst, sump=ZERO,
                               area=area, jantri=jantri, seven_year_applicable=seven_year_ok,
                               gsdma_max_area=None, cap_mode=policy.cap_mode,
                               share_floor_zero=policy.share_floor_zero,
                               subsidy_cap=policy.subsidy_cap,
                               farmer_gst_fraction=policy.farmer_gst_fraction,
                               round_rupee=policy.subsidy_round_rupee)
    result = CropResult(crop.crop, crop.inter_crop, area, crop.lateral_spacing, jantri, blocks,
                        categories, ())
    figures = SprinklerFigures(size, tuple(lines), before_transport, with_gst, nozzle)
    warnings: tuple[str, ...] = () if seven_year_ok or policy.cap_mode != "ggrc" else (
        "seven_year_not_applicable: area outside the window",)
    warnings += tuple(notes)
    if between:
        warnings += (f"area_between_steps: {area} Ha is between table steps; quantities use the "
                     "next step up and the unit cost is pro rata between the two",)
    return QuotationResult(q.system_type, (result,), blocks, figures, warnings)


def _gst_inclusive(q: QuotationInput, masters: Masters, policy: SystemPolicy, *, size: int,
                   area: Decimal, lines: list[SprinklerLine], a: Decimal, qty_between: bool,
                   notes: list[str], nozzle: str | None) -> QuotationResult:
    """FS-056 rule 9, CG sprinkler: the rates carry 5 % GST, so the lines' sum is
    the cost (`'Quotation SIS-CG'!J21`); the flat inspection (J22) is outside the
    cap and on the farmer's share, which is floored at 0 (K8)."""
    crop = q.crops[0]
    gst = round2(a - a / (1 + policy.gst_inclusive_rate))
    blocks = Blocks(field_unit=a, a_plus_b=a - gst, flat_inspection=policy.flat_inspection,
                    cost_excl_gst=a - gst, total_cgst=gst / 2, total_sgst=gst / 2,
                    total_gst=gst, total_incl_gst=a)
    regular: Decimal | None = None
    if isinstance(masters.regular, RowTable):
        regular = masters.regular.stepped(str(size), area)
    if regular is None:
        notes.append(f"no_unit_cost_for_size: the table has no {size} mm value at {area} Ha; "
                     "the unit cost is 0")
        regular = ZERO
    jantri = JantriFigures(regular, regular, regular, None, ZERO, crop.lateral_spacing, None)
    categories = category_rows(masters.categories, cost=a - gst, total_gst=gst, sump=ZERO,
                               area=area, jantri=jantri, seven_year_applicable=False,
                               gsdma_max_area=None, cap_mode=policy.cap_mode,
                               share_floor_zero=policy.share_floor_zero,
                               share_extra=policy.flat_inspection)
    result = CropResult(crop.crop, crop.inter_crop, area, crop.lateral_spacing, jantri, blocks,
                        categories, ())
    figures = SprinklerFigures(size, tuple(lines), a - lines[-1].amount, a, nozzle)
    warnings = tuple(notes)
    if qty_between:
        warnings += (f"area_between_steps: {area} Ha is between table steps; quantities use the "
                     "next step up and the unit cost is pro rata between the two",)
    return QuotationResult(q.system_type, (result,), blocks, figures, warnings)
