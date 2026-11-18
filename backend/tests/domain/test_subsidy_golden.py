"""The three workbooks, reproduced to the paisa (FS-008 section 10, SUB-1, SUB-2).

Every assertion names the cell it reproduces. A cell the workbook rounds is
compared exactly; a cell it does not round is compared against the engine's
unrounded value within 1e-6, so the engine is never bent to a float (rule 25).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from api.domain.subsidy.money import round2
from api.domain.subsidy.pipeline import seven_block
from api.domain.subsidy.sprinkler import field_inspection
from api.domain.subsidy.types import Blocks, QuotationResult
from tests.domain.subsidy_masters import (
    cell,
    fixture,
    masters,
    needs_samples,
    policy,
    quotation,
)

pytestmark = needs_samples

D = Decimal
TOL = D("0.000001")

# The summary sheet's rows, in order, against the engine's block names.
ROW_TO_BLOCK = {
    18: "head_unit", 19: "field_unit", 20: "a_plus_b", 21: "cgst_ab", 22: "sgst_ab",
    23: "installation", 24: "cgst_c", 25: "sgst_c", 26: "total_abc_gst", 27: "insurance",
    28: "cgst_d", 29: "sgst_d", 30: "inspection_before_floor", 31: "inspection", 32: "cgst_e",
    33: "sgst_e", 34: "education", 35: "sump", 36: "cost_excl_gst", 37: "total_cgst",
    38: "total_sgst", 39: "total_gst", 40: "total_incl_gst",
}


def _assert_cell(got: Decimal, want: dict[str, object], where: str) -> None:
    expected = D(str(want["value"]))
    if want["kind"] == "rounded":
        assert got == expected, f"{where} {want['cell']}: {got} != {expected}"
    else:
        assert abs(got - expected) <= TOL, f"{where} {want['cell']}: {got} != {expected}"


def _assert_column(fix: dict[str, object], prefix: str, blocks: Blocks, column: str) -> None:
    expected = fix["expected"]
    assert isinstance(expected, dict)
    seen = 0
    for row, name in ROW_TO_BLOCK.items():
        key = f"{prefix}.{column}{row}"
        if key not in expected:
            continue
        _assert_cell(getattr(blocks, name), expected[key], key)
        seen += 1
    assert seen >= 20, f"{prefix}: only {seen} cells asserted"


# ── Drip: two crops and the total column ─────────────────────────────────────

@pytest.fixture(scope="module")
def drip() -> QuotationResult:
    return seven_block(quotation("drip"), masters("drip"), policy("drip"))


def test_the_drip_workbook_summary_columns(drip: QuotationResult) -> None:
    """'Quo Summary'!I18:I40, J18:J40 and K18:K40."""
    fix = fixture("drip")
    _assert_column(fix, "summary.crop1", drip.crops[0].blocks, "I")
    _assert_column(fix, "summary.crop2", drip.crops[1].blocks, "J")
    _assert_column(fix, "summary.total", drip.total, "K")


def test_the_drip_jantri_and_spacings(drip: QuotationResult) -> None:
    """'New Subsidy Calculation C1'!C30:C32, C55:C56 and the C2 sheet's."""
    fix = fixture("drip")
    for i, tag in enumerate(("crop1", "crop2")):
        j = drip.crops[i].jantri
        _assert_cell(j.regular, cell(fix, f"jantri.{tag}.regular"), tag)
        _assert_cell(j.regular_with_sump, cell(fix, f"jantri.{tag}.regular_with_sump"), tag)
        _assert_cell(j.spacing_standard, cell(fix, f"jantri.{tag}.standard_spacing"), tag)
        _assert_cell(j.spacing_for_subsidy, cell(fix, f"jantri.{tag}.spacing_for_subsidy"), tag)
        assert j.seven_year is not None
        _assert_cell(j.seven_year, cell(fix, f"seven_year.{tag}.unit_cost"), tag)
        assert j.seven_year_spacing is not None
        _assert_cell(j.seven_year_spacing, cell(fix, f"seven_year.{tag}.spacing"), tag)


def test_the_drip_category_tables(drip: QuotationResult) -> None:
    """'Quo Summary'!N29:R36 for crop 1 and N50:R57 for crop 2."""
    fix = fixture("drip")
    for crop, prefix, first in ((drip.crops[0], "categories.crop1", 29),
                                (drip.crops[1], "categories.crop2", 50)):
        for offset, row in enumerate(crop.categories):
            want = cell(fix, f"{prefix}.{first + offset}")
            assert row.name == want["name"]
            _assert_cell(row.exact.subsidy, want["subsidy"], f"{prefix} subsidy")
            _assert_cell(row.exact.farmer_share, want["farmer_share"], f"{prefix} share")
            assert row.applicable is True


def test_the_drip_capped_table_with_the_caps_configured(drip: QuotationResult) -> None:
    """'New Subsidy Calculation C1'!C34:C39, reproduced positionally with the caps
    and percentages read from the formulas (rule 11, GAP-084)."""
    from api.domain.subsidy.categories import category_rows
    from api.domain.subsidy.types import Category

    fix = fixture("drip")
    rows = [("70", "70000"), ("70", "80000"), ("70", "70000"),
            ("80", "80000"), ("90", "100000"), ("85", "100000")]
    for i, crop in enumerate(drip.crops):
        cats = tuple(Category(f"c{n}", f"c{n}", D(pct), "regular", D(cap), None, n)
                     for n, (pct, cap) in enumerate(rows))
        got = category_rows(cats, cost=crop.blocks.cost_excl_gst, total_gst=crop.blocks.total_gst,
                            sump=crop.blocks.sump, area=crop.area, jantri=crop.jantri,
                            seven_year_applicable=False, gsdma_max_area=None)
        for n, row in enumerate(got):
            want = cell(fix, f"capped.crop{i + 1}.{34 + n}")
            _assert_cell(row.exact.subsidy, want["value"], f"capped crop{i + 1} row {34 + n}")


# ── Mini Sprinkler ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def mini() -> QuotationResult:
    return seven_block(quotation("mini_sprinkler"), masters("mini_sprinkler"),
                       policy("mini_sprinkler"))


def test_the_mini_workbook_summary_column(mini: QuotationResult) -> None:
    """'Quo Summary'!I18:I40, where only the insurance block and two kinds of line
    are rounded (rule 4)."""
    _assert_column(fixture("mini_sprinkler"), "summary.crop1", mini.crops[0].blocks, "I")


def test_the_mini_jantri_and_category_table(mini: QuotationResult) -> None:
    """'New Subsidy Calculation'!G30:G32, `M31`, `L33:Q40` and the GSDMA column."""
    fix = fixture("mini_sprinkler")
    crop = mini.crops[0]
    _assert_cell(crop.jantri.regular, cell(fix, "jantri.crop1.regular"), "mini")
    _assert_cell(crop.jantri.regular_with_sump, cell(fix, "jantri.crop1.regular_with_sump"), "mini")
    _assert_cell(crop.jantri.regular_for_cap, cell(fix, "jantri.crop1.regular_prorated"), "mini")
    assert crop.jantri.seven_year is not None
    _assert_cell(crop.jantri.seven_year, cell(fix, "seven_year.crop1.unit_cost"), "mini")
    _assert_cell(crop.blocks.cost_excl_gst, cell(fix, "jantri.crop1.cost"), "mini")
    for offset, row in enumerate(crop.categories):
        want = cell(fix, f"categories.crop1.{33 + offset}")
        assert row.name == want["name"]
        _assert_cell(row.exact.subsidy, want["subsidy"], "mini subsidy")
        _assert_cell(row.exact.farmer_share, want["farmer_share"], "mini share")
        _assert_cell(row.exact.subsidy_pct / 100, want["subsidy_pct"], "mini pct")
        if offset < 6:
            gsdma = cell(fix, f"gsdma.crop1.{43 + offset}")
            assert row.exact.gsdma_farmer_share is not None
            _assert_cell(row.exact.gsdma_farmer_share, gsdma["gsdma_farmer_share"], "mini gsdma")


# ── Sprinkler ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sprinkler() -> QuotationResult:
    return field_inspection(quotation("sprinkler"), masters("sprinkler"), policy("sprinkler"))


def test_the_sprinkler_derived_lines(sprinkler: QuotationResult) -> None:
    """'BOQ'!H16:J25: the quantity from the matrix, the rate from the size band,
    the amount rounded."""
    fix = fixture("sprinkler")
    assert sprinkler.sprinkler is not None
    assert sprinkler.sprinkler.pipe_size_mm == 75
    rows = [16, 17, 18, 19, 20, 21, 22, 23, 25]
    assert len(sprinkler.sprinkler.lines) == len(rows)
    for line, row in zip(sprinkler.sprinkler.lines, rows, strict=True):
        want = cell(fix, f"lines.{row}")
        assert line.description == want["description"], row
        assert line.uom == want["uom"], row
        _assert_cell(line.qty, want["qty"], f"line {row} qty")
        _assert_cell(line.rate, want["rate"], f"line {row} rate")
        _assert_cell(line.amount, want["amount"], f"line {row} amount")


def test_the_sprinkler_summary_chain(sprinkler: QuotationResult) -> None:
    """'BOQ'!J24, J29 and R20:R31, including the inspection floor at 200."""
    fix = fixture("sprinkler")
    b = sprinkler.total
    assert sprinkler.sprinkler is not None
    _assert_cell(sprinkler.sprinkler.field_unit_before_transport, cell(fix, "boq.J24"), "J24")
    _assert_cell(b.a_plus_b, cell(fix, "summary.R20"), "R20")
    _assert_cell(b.cgst_ab, cell(fix, "summary.R21"), "R21")
    _assert_cell(b.total_abc_gst, cell(fix, "summary.R23"), "R23")
    _assert_cell(sprinkler.sprinkler.dbt_farmer_payable, cell(fix, "boq.J29"), "J29")
    _assert_cell(b.inspection_before_floor, cell(fix, "inspection.computed"), "Q46")
    _assert_cell(b.inspection, cell(fix, "summary.R24"), "R24")
    _assert_cell(b.cgst_e, cell(fix, "summary.R25"), "R25")
    _assert_cell(b.cost_excl_gst, cell(fix, "summary.R27"), "R27")
    _assert_cell(b.total_cgst, cell(fix, "summary.R28"), "R28")
    _assert_cell(b.total_gst, cell(fix, "summary.R30"), "R30")
    _assert_cell(b.total_incl_gst, cell(fix, "summary.R31"), "R31")


def test_the_sprinkler_category_tables(sprinkler: QuotationResult) -> None:
    """'Farmer Share Calculation'!B6:D11 and B19:D20."""
    fix = fixture("sprinkler")
    crop = sprinkler.crops[0]
    _assert_cell(crop.jantri.regular, cell(fix, "jantri.regular"), "C4")
    assert crop.jantri.seven_year is not None
    _assert_cell(crop.jantri.seven_year, cell(fix, "jantri.seven_year"), "C17")
    regular = [r for r in crop.categories if r.variant == "regular"]
    seven = [r for r in crop.categories if r.variant == "seven_year"]
    for offset, row in enumerate(regular):
        want = cell(fix, f"categories.regular.{6 + offset}")
        assert row.name == want["name"]
        _assert_cell(row.exact.subsidy, want["subsidy"], "sprinkler subsidy")
        _assert_cell(row.exact.farmer_share, want["farmer_share"], "sprinkler share")
        _assert_cell(row.exact.subsidy_pct / 100, want["subsidy_pct"], "sprinkler pct")
    for offset, row in enumerate(seven):
        want = cell(fix, f"categories.seven_year.{19 + offset}")
        assert row.name == want["name"]
        _assert_cell(row.exact.subsidy, want["subsidy"], "sprinkler 7y subsidy")
        _assert_cell(row.exact.farmer_share, want["farmer_share"], "sprinkler 7y share")


# ── the printed figures tie (rule 10b, SUB-6) ────────────────────────────────

@pytest.mark.parametrize("system", ["drip", "mini_sprinkler", "sprinkler"])
def test_the_rounded_figures_tie_for_every_category(system: str) -> None:
    run = (field_inspection if system == "sprinkler" else seven_block)
    result = run(quotation(system), masters(system), policy(system))
    for crop in result.crops:
        cost = round2(crop.blocks.cost_excl_gst)
        for row in crop.categories:
            if not row.applicable:
                assert row.money.subsidy == 0 and row.money.farmer_share == 0
                continue
            sump = round2(crop.blocks.sump) if row.variant == "regular" else D(0)
            tie = row.money.subsidy + row.money.farmer_share - round2(crop.blocks.total_gst) + sump
            assert tie == cost, f"{system} {row.code}: {tie} != {cost}"
