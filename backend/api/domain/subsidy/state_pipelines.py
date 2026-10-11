"""Pipelines for other states' workbooks (FS-056).

`gst_inclusive_drip` is CG's drip quotation: line rates that already carry 5 %
GST, a fittings add-on on the subtotal, a flat inspection charge outside the cap
that the farmer pays, and a unit cost read from the spacing label's row at the
national area anchors, rounded to the rupee (`'Unit cost and Calculation'!B23`).

`unit_cost_only` is RJ's drip and mini sprinkler quotation: lines without GST,
one 5 % GST on their sum, and a subsidy that is the category percent of the unit
cost after the filter add-ons and the existing-equipment deductions, with no cap
at the cost (`'Unit Cost'!K26:K29`, `'DRIP QTY'!M`).

Both quote one crop, as the workbooks do.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from api.domain.subsidy.categories import category_rows
from api.domain.subsidy.jantri import RowTable
from api.domain.subsidy.money import ZERO, round2
from api.domain.subsidy.types import (
    Blocks,
    CropResult,
    JantriFigures,
    Masters,
    QuotationInput,
    QuotationResult,
    SubsidyError,
    SystemPolicy,
)

HALF = Decimal(2)


def _one_crop(q: QuotationInput, masters: Masters) -> tuple[RowTable, str]:
    if len(q.crops) != 1:
        raise SubsidyError("crop_count", "this scheme quotes one crop", "crops")
    if q.crops[0].area <= 0:
        raise SubsidyError("zero_area", "a crop's area must be positive", "area")
    if not isinstance(masters.regular, RowTable):
        raise SubsidyError("matrix_shape", "this scheme needs a unit cost table by spacing label")
    if not q.spacing_label or not q.spacing_label.strip():
        raise SubsidyError("spacing_label_required", "pick the spacing from the scheme's list",
                           "spacing_label")
    if masters.regular.row(q.spacing_label) is None:
        raise SubsidyError("spacing_label", f"{q.spacing_label.strip()!r} is not one of this "
                           "scheme's spacings", "spacing_label")
    return masters.regular, q.spacing_label


def _jantri(value: Decimal, spacing: Decimal, *, add_ons: Decimal = ZERO,
            deductions: Decimal = ZERO, final: Decimal | None = None,
            warnings: tuple[str, ...] = ()) -> JantriFigures:
    cap = value if final is None else final
    return JantriFigures(value, value, cap, None, ZERO, spacing, None, warnings,
                         add_ons=add_ons, deductions=deductions)


def gst_inclusive_drip(q: QuotationInput, masters: Masters,
                       policy: SystemPolicy) -> QuotationResult:
    table, label = _one_crop(q, masters)
    crop = q.crops[0]
    r = policy.rounding
    head = sum((r.line("head", ln.rate * ln.qty) for ln in q.head_lines), ZERO)
    field = sum((r.line("field", ln.rate * ln.qty) for ln in crop.lines), ZERO)
    subtotal = head + field                                         # I34
    fittings = subtotal * policy.fittings_rate                      # I35
    mis = subtotal + fittings                                       # I36, GST included
    # GST is inside the rates: shown, never added (rule 10)
    gst = round2(mis - mis / (1 + policy.gst_inclusive_rate))
    raw = table.anchored(label, crop.area, prorate_below=False, zero_above=False)
    if raw is None:
        raise SubsidyError("area_outside_table", "the area is outside this scheme's table", "area")
    unit_cost = raw.quantize(Decimal(1), rounding=ROUND_HALF_UP) if policy.unit_cost_round_rupee \
        else raw
    blocks = Blocks(head_unit=head, field_unit=field, a_plus_b=mis - gst, fittings=fittings,
                    flat_inspection=policy.flat_inspection, cost_excl_gst=mis - gst,
                    total_cgst=gst / HALF, total_sgst=gst / HALF, total_gst=gst,
                    total_incl_gst=mis)
    jantri = _jantri(unit_cost, crop.lateral_spacing)
    categories = category_rows(masters.categories, cost=mis - gst, total_gst=gst, sump=ZERO,
                               area=crop.area, jantri=jantri, seven_year_applicable=False,
                               gsdma_max_area=None, cap_mode=policy.cap_mode,
                               share_floor_zero=policy.share_floor_zero,
                               share_extra=policy.flat_inspection)
    result = CropResult(crop.crop, crop.inter_crop, crop.area, crop.lateral_spacing, jantri,
                        blocks, categories, ())
    return QuotationResult(q.system_type, (result,), blocks, None, ())


def unit_cost_only(q: QuotationInput, masters: Masters, policy: SystemPolicy) -> QuotationResult:
    table, label = _one_crop(q, masters)
    crop = q.crops[0]
    r = policy.rounding
    head = sum((r.line("head", ln.rate * ln.qty) for ln in q.head_lines), ZERO)
    field = sum((r.line("field", ln.rate * ln.qty) for ln in crop.lines), ZERO)
    gross = head + field                                            # K54
    gst = gross * policy.gst_inclusive_rate                         # K55, unrounded
    mis = gross + gst                                               # K56
    if mis <= 0:
        # FS-056 EC-12: a subsidy on nothing bought
        raise SubsidyError("zero_cost", "the quotation has no cost", "crops")
    warnings: list[str] = []
    raw = table.anchored(label, crop.area, prorate_below=policy.min_area_prorate,
                         zero_above=policy.zero_above_max_area)
    if raw is None:
        raise SubsidyError("area_outside_table", "the area is outside this scheme's table", "area")
    if policy.zero_above_max_area and raw == 0:
        warnings.append(f"area_above_table: {crop.area} Ha is above the table; the unit cost is 0")
    add_ons = ZERO                                                  # K27
    for code, m3 in (("hydrocyclone", q.hydrocyclone_m3), ("gravel_filter", q.gravel_filter_m3)):
        if m3 > 0:
            if m3 != m3.to_integral_value():
                raise SubsidyError(code, "a filter size is whole cubic metres", f"{code}_m3")
            add_ons += masters.rate_for(code, pipe_size_mm=int(m3)).rate
    deductions = ZERO
    if q.head_unit_existing:                                        # K28
        deductions += policy.head_unit_deduction
    if q.pvc_existing:                                              # K29, 'Unit Cost'!D38
        deductions += sum((c.rate for c in masters.component_rates if c.code == "pvc_deduction"),
                          ZERO)
    final = raw + add_ons - deductions
    if final < 0:
        warnings.append("unit_cost_below_zero: the deductions exceed the unit cost; 0 used")
        final = ZERO
    blocks = Blocks(head_unit=head, field_unit=field, a_plus_b=gross, cgst_ab=gst / HALF,
                    sgst_ab=gst / HALF, cost_excl_gst=gross, total_cgst=gst / HALF,
                    total_sgst=gst / HALF, total_gst=gst, total_incl_gst=mis)
    jantri = _jantri(raw, crop.lateral_spacing, add_ons=add_ons, deductions=deductions,
                     final=final, warnings=tuple(warnings))
    categories = category_rows(masters.categories, cost=gross, total_gst=gst, sump=ZERO,
                               area=crop.area, jantri=jantri, seven_year_applicable=False,
                               gsdma_max_area=None, cap_mode=policy.cap_mode,
                               share_floor_zero=policy.share_floor_zero)
    if any(c.exact.subsidy > mis for c in categories):
        warnings.append("subsidy_above_cost: the subsidy is above the cost, as the scheme's "
                        "sheet has it (GAP-458)")
    result = CropResult(crop.crop, crop.inter_crop, crop.area, crop.lateral_spacing, jantri,
                        blocks, categories, tuple(warnings))
    return QuotationResult(q.system_type, (result,), blocks, None, tuple(warnings))
