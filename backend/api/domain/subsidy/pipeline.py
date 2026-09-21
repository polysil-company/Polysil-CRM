"""The seven-block pipeline, Drip and Mini Sprinkler (FS-008 rules 3, 3b, 5 to 9,
12 to 17). One function reproduces two workbooks; the rounding policy is the
only thing that differs between them (rule 4).

Per crop, the summary sheet's column: A the crop's share of the head unit, B the
field lines, A+B with its 2.5 % + 2.5 %, C the installation with the same, the
total with GST, D insurance at 0.28 % with 9 % + 9 %, E inspection at 0.4 % of
A+B+G (floored where the system floors it), F the crop's share of farmer
education, G the sump; the cost of MIS, the GST totals, the grand total. Then the
Jantri figures and the category table.

The total column is computed from the summed inputs the way the workbook's
column K computes it, not by adding the crop columns (rule 3b); where the two
differ by rounding the response says so.
"""

from __future__ import annotations

from decimal import Decimal

from api.domain.subsidy.categories import category_rows
from api.domain.subsidy.jantri import Matrix2D, bilinear
from api.domain.subsidy.money import ZERO, round2
from api.domain.subsidy.types import (
    Blocks,
    CropInput,
    CropResult,
    JantriFigures,
    Masters,
    QuotationInput,
    QuotationResult,
    SubsidyError,
    SystemPolicy,
)

RESIDUAL_KEYS: tuple[str, ...] = (
    "head_unit", "field_unit", "a_plus_b", "cgst_ab", "sgst_ab", "installation", "cgst_c", "sgst_c",
    "total_abc_gst", "insurance", "cgst_d", "sgst_d", "inspection", "cgst_e", "sgst_e", "education",
    "sump", "cost_excl_gst", "total_cgst", "total_sgst", "total_gst", "total_incl_gst",
)


def seven_block(q: QuotationInput, masters: Masters, policy: SystemPolicy) -> QuotationResult:
    if not q.crops:
        raise SubsidyError("no_crops", "at least one crop", "crops")
    if not isinstance(masters.regular, Matrix2D) or not isinstance(masters.seven_year, Matrix2D):
        raise SubsidyError("matrix_shape", f"{policy.system_type} needs two-dimensional matrices")
    rounding = policy.rounding
    areas_total = sum((c.area for c in q.crops), ZERO)
    if areas_total <= 0:
        raise SubsidyError("zero_area", "the total area is zero", "crops")
    # Rule 12: the head unit is shared by area over the group, else over the crops (GAP-085).
    divisor = q.group_total_area if q.group_total_area is not None else areas_total
    if divisor < areas_total:
        raise SubsidyError("group_area_below_crops",
                           "the group's total area is smaller than the crops' areas",
                           "group_total_area")
    head_total = sum((rounding.line("head", ln.rate * ln.qty) for ln in q.head_lines), ZERO)

    warnings: list[str] = []
    seven_year_ok = policy.seven_year_area_min <= areas_total <= policy.seven_year_area_max
    if not seven_year_ok:
        warnings.append(f"seven_year_not_applicable: total area {areas_total:.3f} Ha is outside "
                        f"{policy.seven_year_area_min} to {policy.seven_year_area_max} Ha")
    if policy.warn_sump_divergence and q.sump_rate_per_ha > 0:
        warnings.append("sump_ignored_by_workbook: the sump joins the cap here; the workbook's "
                        "sump term references an empty cell (GAP-082)")

    crops = tuple(_crop(c, q, masters, policy, head_total=head_total, divisor=divisor,
                        areas_total=areas_total, seven_year_ok=seven_year_ok) for c in q.crops)
    total = _total(crops, q, policy, head_total=head_total, divisor=divisor,
                   areas_total=areas_total)
    warnings.extend(_residuals(crops, total))
    return QuotationResult(q.system_type, crops, total, None, tuple(warnings))


def _crop(c: CropInput, q: QuotationInput, masters: Masters, policy: SystemPolicy, *,
          head_total: Decimal, divisor: Decimal, areas_total: Decimal,
          seven_year_ok: bool) -> CropResult:
    if c.area <= 0:
        raise SubsidyError("zero_area", "a crop's area must be positive", "area")
    r = policy.rounding
    field_lines = sum((r.line("field", ln.rate * ln.qty) for ln in c.lines), ZERO)
    blocks = _blocks(policy, head_share=head_total * c.area / divisor, field=field_lines,
                     installation=r.line("installation", q.installation_rate_per_ha * c.area),
                     education=r.block("education_split",
                                       policy.education_amount * c.area / areas_total),
                     sump=r.block("sump", q.sump_rate_per_ha * c.area))
    jantri = _jantri(c, q, masters, policy, seven_year_ok=seven_year_ok)
    categories = category_rows(masters.categories, cost=blocks.cost_excl_gst,
                               total_gst=blocks.total_gst, sump=blocks.sump, area=c.area,
                               jantri=jantri, seven_year_applicable=seven_year_ok,
                               gsdma_max_area=policy.gsdma_max_area)
    return CropResult(c.crop, c.inter_crop, c.area, c.lateral_spacing, jantri, blocks, categories,
                      jantri.warnings)


def _blocks(policy: SystemPolicy, *, head_share: Decimal, field: Decimal, installation: Decimal,
            education: Decimal, sump: Decimal) -> Blocks:
    """One column of the summary sheet from its five inputs (rule 3), rounded at
    the cells the policy names (rule 4)."""
    r = policy.rounding
    a_plus_b = r.block("a_plus_b", head_share + field)
    cgst_ab = r.block("gst_ab", a_plus_b * policy.gst_material_half)
    cgst_c = r.block("gst_c", installation * policy.gst_material_half)
    with_gst = a_plus_b + cgst_ab + cgst_ab + installation + cgst_c + cgst_c
    total_abc_gst = r.block("total_abc_gst", with_gst)
    insurance = r.block("insurance", total_abc_gst * policy.insurance_rate)
    cgst_d = r.block("gst_d", insurance * policy.gst_service_half)
    inspection_before = r.block("inspection", (a_plus_b + sump) * policy.inspection_rate)
    # Rule 5: the floor, and the floor at exact equality (the workbook's IF returns FALSE there)
    inspection = max(inspection_before, policy.inspection_floor)
    cgst_e = r.block("gst_e", inspection * policy.gst_service_half)
    mis = education + inspection + insurance + installation + a_plus_b + sump
    cost = r.block("cost_of_mis", mis)
    total_cgst = r.block("gst_totals", cgst_ab + cgst_c + cgst_d + cgst_e)
    total_gst = r.block("total_gst", total_cgst + total_cgst)
    return Blocks(
        head_unit=head_share, field_unit=field, a_plus_b=a_plus_b, cgst_ab=cgst_ab, sgst_ab=cgst_ab,
        installation=installation, cgst_c=cgst_c, sgst_c=cgst_c, total_abc_gst=total_abc_gst,
        insurance=insurance, cgst_d=cgst_d, sgst_d=cgst_d,
        inspection_before_floor=inspection_before,
        inspection=inspection, cgst_e=cgst_e, sgst_e=cgst_e, education=education, sump=sump,
        cost_excl_gst=cost, total_cgst=total_cgst, total_sgst=total_cgst, total_gst=total_gst,
        total_incl_gst=r.block("total_incl_gst", cost + total_gst),
    )


def _jantri(c: CropInput, q: QuotationInput, masters: Masters, policy: SystemPolicy, *,
            seven_year_ok: bool) -> JantriFigures:
    assert isinstance(masters.regular, Matrix2D) and isinstance(masters.seven_year, Matrix2D)
    # Rule 6: the inter-crop's standard when there is one, else the crop's; then the larger of
    # that and the designed spacing ('New Subsidy Calculation C1'!C55:C56).
    standard = masters.standard_spacing(c.inter_crop if c.inter_crop else c.crop)
    if policy.spacing_rule == "max_of_standard_and_design":
        spacing = max(standard, c.lateral_spacing)
    else:
        spacing = c.lateral_spacing
    regular = bilinear(masters.regular, area=c.area, spacing=spacing,
                       outside=policy.spacing_outside_table,
                       scale_above_max=policy.max_area_scaling)
    warnings = list(regular.warnings)
    # Rule 9: C32 = C30 + sump rate * area, the raw product, not the rounded block G
    with_sump = regular.unit_cost + q.sump_rate_per_ha * c.area
    for_cap = with_sump
    if policy.min_area_prorate and c.area < masters.regular.min_area:
        # Rule 8: Mini 'Quo Summary'!M31 = (G32/20)*area*100, the value times area / 0.2
        for_cap = with_sump * c.area / masters.regular.min_area

    seven_year = seven_year_spacing = None
    if seven_year_ok:
        # Rules 14, 15: the designed spacing floored, the crop's own area, no scaling
        seven_year_spacing = c.lateral_spacing
        if policy.seven_year_spacing_floor is not None:
            seven_year_spacing = max(seven_year_spacing, policy.seven_year_spacing_floor)
        sy = bilinear(masters.seven_year, area=c.area, spacing=seven_year_spacing,
                      outside=policy.spacing_outside_table, scale_above_max=False)
        seven_year = sy.unit_cost
        # The prefixed code is what is compared: testing the bare one meant a
        # 7-year clamp went unreported whenever the regular table clamped too,
        # which is exactly when it happens (code review F-4).
        warnings.extend(f"seven_year_{w}" for w in sy.warnings
                        if f"seven_year_{w}" not in warnings)
    return JantriFigures(regular.unit_cost, with_sump, for_cap, seven_year, standard, spacing,
                         seven_year_spacing, tuple(dict.fromkeys(warnings)))


def _total(crops: tuple[CropResult, ...], q: QuotationInput, policy: SystemPolicy, *,
           head_total: Decimal, divisor: Decimal, areas_total: Decimal) -> Blocks:
    """Column K: the same arithmetic on the summed inputs (rule 3b). The head is
    the sum of the shares (N31 = J31 + L31), the sump the sum of the crops' sumps
    (K35 = ROUND(J35 + I35, 2)), education the amount itself (K34)."""
    r = policy.rounding
    return _blocks(policy,
                   head_share=sum((c.blocks.head_unit for c in crops), ZERO),
                   field=sum((c.blocks.field_unit for c in crops), ZERO),
                   installation=r.line("installation", q.installation_rate_per_ha * areas_total),
                   education=policy.education_amount,
                   sump=r.block("sump", sum((c.blocks.sump for c in crops), ZERO)))


def _residuals(crops: tuple[CropResult, ...], total: Blocks) -> list[str]:
    out = []
    for key in RESIDUAL_KEYS:
        summed = round2(sum((getattr(c.blocks, key) for c in crops), ZERO))
        whole = round2(getattr(total, key))
        if summed != whole:
            out.append(f"rounding_residual: {key} of the crops sums to {summed}, the total column "
                       f"is {whole} (computed from the summed inputs)")
    return out
