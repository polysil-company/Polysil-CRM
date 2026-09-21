"""The rules the three sample quotations cannot reach (FS-008 section 10, the
"domain, boundary" and "domain, properties" rows).

The golden fixtures all share one shape: a zero sump, integer head quantities,
areas inside every window, one nozzle, one pipe size and no inter-crop. A code
review mutation-tested the golden suite by deleting one mechanism at a time from
the live engine, and ten of thirteen deletions left it green - among them the
inter-crop lookup, worth 78,780 rupees on the client's own sample, and the
derivation that acceptance criterion SUB-6 exists to protect.

**Every test here is written so that removing the mechanism it names turns it
red.** Where a figure is quoted, it was computed from the workbook's own cells.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import ROUND_HALF_EVEN, Decimal

import pytest

from api.domain.subsidy.categories import category_rows
from api.domain.subsidy.jantri import Matrix2D, bilinear
from api.domain.subsidy.money import round2
from api.domain.subsidy.pipeline import seven_block
from api.domain.subsidy.sprinkler import field_inspection
from api.domain.subsidy.types import (
    Category,
    CropInput,
    JantriFigures,
    Line,
    QuotationResult,
    SubsidyError,
)
from tests.domain.subsidy_masters import masters, needs_samples, policy, quotation

pytestmark = needs_samples

D = Decimal
ZERO = D(0)


def code(warning: str) -> str:
    """A warning is `code: sentence`; the code is the stable half."""
    return warning.split(":", 1)[0]


def codes(result: QuotationResult, crop: int = 0) -> set[str]:
    return {code(w) for w in (*result.warnings, *result.crops[crop].warnings)}


def run(system: str, **over: object) -> QuotationResult:
    base = quotation(system)
    engine = field_inspection if system == "sprinkler" else seven_block
    return engine(replace(base, **over), masters(system), policy(system))


def one_crop(system: str, **crop_over: object) -> QuotationResult:
    base = quotation(system)
    return run(system, crops=(replace(base.crops[0], **crop_over),))


# ── rule 6: the inter-crop sets the standard spacing ─────────────────────────

def test_the_inter_crop_sets_the_standard_spacing_not_the_main_crop() -> None:
    """`'New Subsidy Calculation C1'!C55` reads `C48`, the inter-crop, and falls
    back to `C47` only when there is none. Reading `C47` alone is 78,780 rupees of
    subsidy on this very quotation."""
    alone = one_crop("drip", inter_crop=None)
    paired = one_crop("drip", inter_crop="Chillies")

    assert alone.crops[0].jantri.spacing_standard == D("5")
    assert alone.crops[0].jantri.spacing_for_subsidy == D("5")
    assert alone.crops[0].jantri.regular == D("74503.04")

    assert paired.crops[0].jantri.spacing_standard == D("1.35")
    assert paired.crops[0].jantri.spacing_for_subsidy == D("1.37")
    assert round2(paired.crops[0].jantri.regular) == D("187045.62")

    gap = paired.crops[0].categories[0].money.subsidy - alone.crops[0].categories[0].money.subsidy
    assert gap == D("78779.80")


def test_an_unknown_crop_is_refused_rather_than_given_a_standard_of_zero() -> None:
    with pytest.raises(SubsidyError) as err:
        one_crop("drip", crop="Mangoo")
    assert err.value.code == "crop_not_found"


def test_no_crop_at_all_is_a_standard_of_zero_as_the_workbook_has_it() -> None:
    """"Select Crop here" is a real state in the sheet, and its standard is 0, so
    the designed spacing wins outright."""
    got = one_crop("drip", crop=None, inter_crop=None)
    assert got.crops[0].jantri.spacing_standard == ZERO
    assert got.crops[0].jantri.spacing_for_subsidy == D("1.37")


# ── rule 2: which lines a system rounds ──────────────────────────────────────

def test_a_mini_head_line_is_unrounded_and_the_same_line_as_a_field_line_is_not() -> None:
    """`'Quo A'!J25 = H25*I25` for a head line against `J58 = ROUND(H58*I58,2)` for
    a field line. The sample cannot tell them apart, because every head quantity in
    it is an integer."""
    line = Line("Fractional item", "Hac", D("908.42"), D("0.8"))   # 726.736
    base = quotation("mini_sprinkler")
    single = replace(base.crops[0], lines=(), area=D("1"))

    as_head = seven_block(replace(base, head_lines=(line,), crops=(single,), group_total_area=D(1)),
                          masters("mini_sprinkler"), policy("mini_sprinkler"))
    as_field = seven_block(replace(base, head_lines=(), crops=(replace(single, lines=(line,)),),
                                   group_total_area=D(1)),
                           masters("mini_sprinkler"), policy("mini_sprinkler"))
    assert as_head.crops[0].blocks.head_unit == D("726.736")
    assert as_field.crops[0].blocks.field_unit == D("726.74")


def test_drip_rounds_no_line_at_all() -> None:
    line = Line("Fractional item", "Hac", D("908.42"), D("0.8"))
    base = quotation("drip")
    got = seven_block(replace(base, head_lines=(line,),
                              crops=(replace(base.crops[0], lines=(line,)),)),
                      masters("drip"), policy("drip"))
    assert got.crops[0].blocks.field_unit == D("726.736")


# ── rule 4: half-up, not banker's ────────────────────────────────────────────

def test_the_education_split_proves_the_rounding_is_half_up() -> None:
    """Two areas whose splits land exactly on the half, in opposite directions:
    609.375 and 390.625. Half-up gives 609.38 and 390.63; banker's would give
    390.62, and the residual would vanish with it."""
    base = quotation("drip")
    crops = (replace(base.crops[0], area=D("0.624")), replace(base.crops[1], area=D("0.400")))
    got = seven_block(replace(base, crops=crops, group_total_area=D("2")),
                      masters("drip"), policy("drip"))
    assert got.crops[0].blocks.education == D("609.38")
    assert got.crops[1].blocks.education == D("390.63")
    assert got.total.education == D("1000")
    assert "rounding_residual" in codes(got)


def test_round2_is_half_away_from_zero_where_the_two_modes_differ() -> None:
    for value, half_up in (("609.375", "609.38"), ("390.625", "390.63"), ("25.005", "25.01")):
        assert round2(D(value)) == D(half_up)
        if D(value).quantize(D("0.01"), rounding=ROUND_HALF_EVEN) != D(half_up):
            return
    pytest.fail("no case here separates half-up from banker's rounding")


# ── rule 3b: the total column is not the sum of the crop columns ─────────────

def test_the_total_education_is_the_amount_itself_not_the_sum_of_the_splits() -> None:
    """`'Quo Summary'!K34` reads the amount. Summing the rounded splits prints
    1000.01, and the response says so rather than hiding it."""
    base = quotation("drip")
    crops = (replace(base.crops[0], area=D("0.624")), replace(base.crops[1], area=D("0.400")))
    got = seven_block(replace(base, crops=crops, group_total_area=D("2")),
                      masters("drip"), policy("drip"))
    summed = sum((c.blocks.education for c in got.crops), ZERO)
    assert summed == D("1000.01") and got.total.education == D("1000")
    assert any("education" in w for w in got.warnings)


def test_a_single_crop_quotation_has_no_residual_at_all() -> None:
    assert "rounding_residual" not in codes(run("mini_sprinkler"))


# ── rules 8 and 9: the sump, and the pro-rate below 0.2 Ha ───────────────────

def test_the_sump_joins_the_cap_and_leaves_the_farmer_share() -> None:
    """Rule 9. The workbook's Mini formula points at an empty cell, so this is a
    recorded divergence and it carries a warning."""
    without = run("mini_sprinkler")
    with_sump = run("mini_sprinkler", sump_rate_per_ha=D("5000"))

    assert with_sump.crops[0].blocks.sump == D("4000")
    assert with_sump.crops[0].jantri.regular_with_sump == \
        without.crops[0].jantri.regular + D("4000")
    gained = (with_sump.crops[0].categories[0].money.subsidy
              - without.crops[0].categories[0].money.subsidy)
    assert gained == D("2800.00"), "70 % of the 4000 the sump adds to the cap"
    assert "sump_ignored_by_workbook" in codes(with_sump)


def test_the_mini_pro_rate_below_two_tenths_of_a_hectare() -> None:
    """Rule 8: the workbook's branch takes the 0.2 column, then `M31` scales it by
    area / 0.2. The two steps compose in that order."""
    at_step = one_crop("mini_sprinkler", area=D("0.200"))
    below = one_crop("mini_sprinkler", area=D("0.100"))
    just_below = one_crop("mini_sprinkler", area=D("0.199"))

    assert at_step.crops[0].jantri.regular_for_cap == D("39239.000")
    assert below.crops[0].jantri.regular == D("39239")
    assert below.crops[0].jantri.regular_for_cap == D("19619.5")
    assert just_below.crops[0].jantri.regular_for_cap == D("39042.805")
    assert "area_below_table" in codes(below)
    assert "area_below_table" not in codes(at_step)


def test_drip_does_not_pro_rate_below_two_tenths_of_a_hectare() -> None:
    below = one_crop("drip", area=D("0.100"))
    assert below.crops[0].jantri.regular_for_cap == below.crops[0].jantri.regular


# ── rules 10, 14, 15: the seven-year window and its spacing floor ────────────

def test_the_seven_year_window_is_the_total_area_not_the_crops_own() -> None:
    """Rule 14: a crop of 0.150 Ha inside a total of 1.150 still gets its 7-year
    rows, and the interpolation uses the crop's own area."""
    base = quotation("drip")
    crops = (replace(base.crops[0], area=D("0.150")), replace(base.crops[1], area=D("1.000")))
    got = seven_block(replace(base, crops=crops, group_total_area=D("2")),
                      masters("drip"), policy("drip"))
    small = got.crops[0]
    assert small.jantri.seven_year is not None, "the total is inside the window"
    assert [r.applicable for r in small.categories if r.variant == "seven_year"] == [True, True]
    assert "area_below_table" in codes(got), "the crop itself is below the table"


@pytest.mark.parametrize(("areas", "applies"), [
    (("0.090", "0.100"), False),   # total 0.190, below the window
    (("0.100", "0.100"), True),    # total 0.200, the endpoint is inside
    (("2.500", "2.500"), True),    # total 5.000, the other endpoint
    (("3.000", "3.000"), False),   # total 6.000, above
])
def test_the_seven_year_window_endpoints_are_inclusive(areas: tuple[str, str],
                                                       applies: bool) -> None:
    base = quotation("drip")
    crops = tuple(replace(c, area=D(a)) for c, a in zip(base.crops, areas, strict=True))
    got = seven_block(replace(base, crops=crops, group_total_area=D("10")),
                      masters("drip"), policy("drip"))
    seven = [r for r in got.crops[0].categories if r.variant == "seven_year"]
    assert all(r.applicable is applies for r in seven)
    if not applies:
        assert all(r.money.subsidy == ZERO and r.reason for r in seven)
        assert "seven_year_not_applicable" in codes(got)


def test_the_seven_year_spacing_is_the_designed_one_floored() -> None:
    """Rule 14 for Drip (floor 1.2) and rule 15 for Mini (floor 8). The regular
    table uses a different spacing entirely, so a floor that never fired would be
    invisible in the golden run."""
    tight = one_crop("drip", lateral_spacing=D("0.5"))
    assert tight.crops[0].jantri.seven_year_spacing == D("1.2")

    wide = one_crop("drip", lateral_spacing=D("3"))
    assert wide.crops[0].jantri.seven_year_spacing == D("3")

    mini = one_crop("mini_sprinkler", lateral_spacing=D("7.5"))
    assert mini.crops[0].jantri.seven_year_spacing == D("8")


def test_a_seven_year_clamp_is_reported_even_when_the_regular_table_clamps_too() -> None:
    """Both matrices stop at 12 m for Drip, so a 20 m spacing clamps twice. The
    prefixed code is the one that must survive."""
    got = one_crop("drip", lateral_spacing=D("20"))
    assert "spacing_outside_table" in codes(got)
    assert "seven_year_spacing_outside_table" in codes(got)


# ── rule 10b and SUB-6: the share is derived, not rounded ────────────────────

def test_the_farmer_share_is_derived_from_rounded_terms_not_rounded_itself() -> None:
    """Blocker B-2, asserted the only way that can fail: against the wrong answer.
    `round(c - s + g)` and `round(c) - round(s) + round(g)` differ whenever the
    fractional parts carry, and the tie-out identity is true of both, so an
    assertion written as the identity proves nothing."""
    cost, gst = D("10000.004"), D("0.004")
    cat = (Category("x", "x", D("70"), "regular"),)
    jantri = JantriFigures(D("999999"), D("999999"), D("999999"), None, ZERO, D("5"), None)
    row = category_rows(cat, cost=cost, total_gst=gst, sump=ZERO, area=D("1"), jantri=jantri,
                        seven_year_applicable=False, gsdma_max_area=None)[0]

    derived = round2(cost) - round2(row.exact.subsidy) + round2(gst)
    rounded_share = round2(cost - row.exact.subsidy + gst)
    assert derived != rounded_share, "the case has to be one where the two differ"
    assert row.money.farmer_share == derived
    assert row.money.subsidy + row.money.farmer_share - round2(gst) == round2(cost)


@pytest.mark.parametrize("thousandths", range(0, 20))
def test_the_printed_figures_tie_for_costs_that_are_not_whole_paise(thousandths: int) -> None:
    """Section 10's property row: costs and GST drawn with more than two decimals,
    because two-decimal inputs cannot see the defect above."""
    cost = D("10000") + D(thousandths) / 1000
    gst = D("500") + D(thousandths) / 10000
    sump = D("7") + D(thousandths) / 100000
    jantri = JantriFigures(D("99999999"), D("99999999"), D("99999999"), D("99999999"),
                           ZERO, D("5"), None)
    for row in category_rows(masters("drip").categories, cost=cost, total_gst=gst, sump=sump,
                             area=D("1.5"), jantri=jantri, seven_year_applicable=True,
                             gsdma_max_area=None):
        term = round2(sump) if row.variant == "regular" else ZERO
        tie = row.money.subsidy + row.money.farmer_share - round2(gst) + term
        assert tie == round2(cost), f"{row.code} at {cost}"


def test_a_zero_cost_gives_a_zero_percentage_rather_than_a_division_error() -> None:
    jantri = JantriFigures(ZERO, ZERO, ZERO, None, ZERO, D("5"), None)
    rows = category_rows(masters("drip").categories, cost=ZERO, total_gst=ZERO, sump=ZERO,
                         area=D("1"), jantri=jantri, seven_year_applicable=False,
                         gsdma_max_area=None)
    assert all(r.money.subsidy_pct == ZERO for r in rows)


def test_a_higher_percentage_never_lowers_the_subsidy() -> None:
    got = run("drip")
    regular = [r for r in got.crops[0].categories if r.variant == "regular"]
    by_pct = sorted(regular, key=lambda r: r.pct)
    assert [r.money.subsidy for r in by_pct] == sorted(r.money.subsidy for r in by_pct)


def test_the_subsidy_never_exceeds_the_cost_times_the_percentage() -> None:
    got = run("drip")
    for crop in got.crops:
        for row in crop.categories:
            if row.applicable:
                assert row.exact.subsidy <= crop.blocks.cost_excl_gst * row.pct / 100


# ── rule 11: a configured per-hectare cap is a third term ────────────────────

def test_a_configured_cap_binds_and_a_null_one_does_not() -> None:
    got = run("drip")
    crop = got.crops[0]
    capped = Category("c", "c", D("70"), "regular", D("1000"))
    uncapped = Category("u", "u", D("70"), "regular", None)
    rows = category_rows((capped, uncapped), cost=crop.blocks.cost_excl_gst,
                         total_gst=crop.blocks.total_gst, sump=ZERO, area=crop.area,
                         jantri=crop.jantri, seven_year_applicable=False, gsdma_max_area=None)
    assert rows[0].exact.subsidy == crop.area * D("1000")
    assert rows[1].exact.subsidy > rows[0].exact.subsidy


# ── rules 17 to 22: the Sprinkler ────────────────────────────────────────────

def test_the_pipe_size_follows_the_area_band_and_the_matrix_jumps_with_it() -> None:
    """Rule 19: the 2.0 to 2.01 step changes the size, and the quantity table steps
    down with it. Both totals are exact."""
    at_two = one_crop("sprinkler", area=D("2.0"))
    past_two = one_crop("sprinkler", area=D("2.01"))

    assert at_two.sprinkler is not None and past_two.sprinkler is not None
    assert (at_two.sprinkler.pipe_size_mm, past_two.sprinkler.pipe_size_mm) == (75, 90)
    assert (at_two.sprinkler.lines[0].qty, past_two.sprinkler.lines[0].qty) == (D("41"), D("34"))
    assert (at_two.sprinkler.lines[0].rate, past_two.sprinkler.lines[0].rate) == \
        (D("583.12"), D("691.62"))
    assert at_two.sprinkler.lines[0].amount == D("23907.92")
    assert past_two.sprinkler.lines[0].amount == D("23515.08")


def test_both_nozzle_types_reach_their_own_rate() -> None:
    """Rule 20. The two nozzle rows share a component name in the workbook, so a
    lookup by name alone would take whichever row came first."""
    plastic = run("sprinkler", nozzle="plastic")
    brass = run("sprinkler", nozzle="brass")
    assert plastic.sprinkler is not None and brass.sprinkler is not None
    assert plastic.sprinkler.lines[2].rate == D("104.17")
    assert brass.sprinkler.lines[2].rate == D("299.23")
    assert brass.total.cost_excl_gst > plastic.total.cost_excl_gst


def test_the_transport_quantity_is_the_area() -> None:
    got = one_crop("sprinkler", area=D("2.01"))
    assert got.sprinkler is not None
    assert got.sprinkler.lines[-1].component == "transport"
    assert got.sprinkler.lines[-1].qty == D("2.01")
    assert got.sprinkler.lines[-1].amount == round2(D("506.45") * D("2.01"))


def test_an_off_step_area_is_refused_with_the_steps_named() -> None:
    with pytest.raises(SubsidyError) as err:
        one_crop("sprinkler", area=D("1.1"))
    assert err.value.code == "exact_area_match_required"
    assert err.value.field_path == "area"
    assert "0.4" in err.value.message


def test_the_sprinkler_inspection_floor_holds_at_the_smallest_area() -> None:
    """Rule 5 and rule 21: 0.4 % of a small A is under 200, so the floor binds and
    `R24` prints 200 exactly."""
    small = one_crop("sprinkler", area=D("0.4"))
    assert small.total.inspection == D("200")
    assert small.total.inspection_before_floor < D("200")


def test_drip_has_no_inspection_floor() -> None:
    tiny = Line("One rupee", "Nos.", D("1.00"), D("1"))
    base = quotation("drip")
    got = seven_block(replace(base, head_lines=(),
                              crops=(replace(base.crops[0], lines=(tiny,)),
                                     replace(base.crops[1], lines=(tiny,))),
                              installation_rate_per_ha=ZERO),
                      masters("drip"), policy("drip"))
    assert got.crops[0].blocks.inspection < D("200")


# ── rule 12: the head unit and the group divisor ─────────────────────────────

@pytest.mark.parametrize("members", [3, 4, 10])
def test_the_head_shares_are_the_group_fraction(members: int) -> None:
    """The workbook's own sample divides by a group area larger than the crops, so
    the shares deliberately do not sum to the head unit; they sum to the head unit
    times the crops' fraction of the group."""
    base = quotation("drip")
    group = D(members)
    got = seven_block(replace(base, group_total_area=group), masters("drip"), policy("drip"))
    head_total = sum((ln.rate * ln.qty for ln in base.head_lines), ZERO)
    areas = sum((c.area for c in base.crops), ZERO)
    shares = sum((c.blocks.head_unit for c in got.crops), ZERO)
    assert shares == head_total * areas / group


def test_with_no_group_the_crops_take_the_whole_head_unit() -> None:
    base = quotation("drip")
    got = seven_block(replace(base, group_total_area=None), masters("drip"), policy("drip"))
    head_total = sum((ln.rate * ln.qty for ln in base.head_lines), ZERO)
    assert sum((c.blocks.head_unit for c in got.crops), ZERO) == head_total


def test_a_group_smaller_than_the_crops_is_refused() -> None:
    with pytest.raises(SubsidyError) as err:
        run("drip", group_total_area=D("1"))
    assert err.value.code == "group_area_below_crops"


# ── empty and single-line bills ──────────────────────────────────────────────

def test_a_quotation_with_no_lines_at_all_still_answers() -> None:
    base = quotation("drip")
    got = seven_block(replace(base, head_lines=(),
                              crops=(replace(base.crops[0], lines=()),),
                              installation_rate_per_ha=ZERO),
                      masters("drip"), policy("drip"))
    assert got.crops[0].blocks.a_plus_b == ZERO
    assert got.crops[0].blocks.cost_excl_gst > ZERO, "education still applies"


def test_one_line_is_enough() -> None:
    base = quotation("drip")
    got = seven_block(replace(base, head_lines=(),
                              crops=(replace(base.crops[0],
                                             lines=(Line("x", "Nos.", D("100.00"), D("3")),)),)),
                      masters("drip"), policy("drip"))
    assert got.crops[0].blocks.field_unit == D("300")


# ── rule 25: four decimals of storage move no paisa ──────────────────────────

def test_four_decimals_of_storage_change_no_paisa_at_any_percentage() -> None:
    """The claim §5 makes about `numeric(14,4)`, asserted at the stored cells **and
    at interpolated points**, since the cap uses interpolated values."""
    full = masters("drip").regular
    assert isinstance(full, Matrix2D)
    truncated = Matrix2D(full.spacings, full.areas,
                         {k: v.quantize(D("0.0001")) for k, v in full.cells.items()})
    percentages = [D(p) for p in ("45", "55", "70", "80", "85", "90")]

    for spacing, area in list(full.cells)[:40]:
        for pct in percentages:
            assert round2(full.at(spacing, area) * pct / 100) == \
                round2(truncated.at(spacing, area) * pct / 100)

    for area in ("0.35", "1.61", "2.75", "4.99"):
        for spacing in ("1.37", "3.5", "6.25"):
            a, b = (bilinear(m, area=D(area), spacing=D(spacing)).unit_cost
                    for m in (full, truncated))
            for pct in percentages:
                assert round2(a * pct / 100) == round2(b * pct / 100), (area, spacing, pct)


# ── one bill of quantities, two rounding policies ────────────────────────────

def test_the_same_bill_differs_by_the_paise_the_workbooks_differ_by() -> None:
    """Rule 4's whole point: the policy is the only difference between the two
    seven-block systems, and it is visible in the answer."""
    lines = (Line("Odd rate", "Hac", D("1521.24"), D("1.61")),
             Line("Another", "Mtr.", D("103.19"), D("18")))
    crop = CropInput("POTATO", None, D("1.61"), "", D("7.5"), lines)
    head = (Line("Head", "Nos.", D("908.42"), D("0.333")),)   # 302.50386, more than two decimals

    out = {}
    for system in ("drip", "mini_sprinkler"):
        base = quotation(system)
        out[system] = seven_block(
            replace(base, crops=(crop,), head_lines=head, group_total_area=D("1.61"),
                    installation_rate_per_ha=D("1895.11")),
            masters(system), policy(system))

    drip, mini = out["drip"].crops[0].blocks, out["mini_sprinkler"].crops[0].blocks
    assert drip.field_unit != mini.field_unit, "Mini rounds its field lines, Drip does not"
    assert drip.a_plus_b == round2(drip.head_unit + drip.field_unit), "Drip rounds A+B"
    assert mini.a_plus_b == mini.head_unit + mini.field_unit, "Mini leaves A+B alone"
    assert mini.a_plus_b.as_tuple().exponent < -2, "and this bill proves it, at five decimals"
    assert round2(drip.cost_excl_gst) != round2(mini.cost_excl_gst)
