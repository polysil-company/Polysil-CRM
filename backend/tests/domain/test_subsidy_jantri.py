"""The Jantri against the workbooks' own figures and the rules' boundaries
(FS-008 section 10, the domain rows). No database: the matrices come from the
committed fixture the extractor wrote from the client's workbooks."""

from __future__ import annotations

import json
import pathlib
from decimal import Decimal

import pytest

from api.domain.subsidy.jantri import (
    Matrix2D,
    OutsideTable,
    area_bracket,
    bilinear,
    lookup_1d,
    spacing_bracket,
    table_1d,
)
from tests.domain.subsidy_masters import fixture

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "subsidy"
MATRICES = json.loads((FIXTURES / "matrices.json").read_text(encoding="utf-8"))
D = Decimal


def _matrix(system: str, variant: str) -> Matrix2D:
    m = MATRICES[system][variant]
    return Matrix2D.from_rows(m["areas"], [(r["spacing"], r["costs"]) for r in m["rows"]])


def _expected(system: str, key: str) -> Decimal:
    """A cell of one sample quotation. Those fixtures carry the client's own rates
    and are kept out of the shared snapshot, so a test that reads one skips when
    they are absent; everything below that only needs the matrices still runs."""
    return D(str(fixture(system)["expected"][key]["value"]))


def _close(a: Decimal, b: Decimal, tol: str = "0.000001") -> bool:
    return abs(a - b) <= D(tol)


def has(code: str, warnings: tuple[str, ...]) -> bool:
    """A warning is `code: sentence`; the code is the stable half."""
    return any(w.split(":", 1)[0] == code for w in warnings)


DRIP = _matrix("drip", "regular")
DRIP7 = _matrix("drip", "seven_year")
MINI = _matrix("mini_sprinkler", "regular")
MINI7 = _matrix("mini_sprinkler", "seven_year")


# ── the workbooks' own figures ───────────────────────────────────────────────

def test_the_drip_regular_jantri_of_the_sample() -> None:
    """'New Subsidy Calculation C1'!C30 at 1.61 Ha and the spacing the workbook
    used, MAX(standard 5, designed 1.37) = 5."""
    got = bilinear(DRIP, area=D("1.61"), spacing=D("5"))
    assert _close(got.unit_cost, _expected("drip", "jantri.crop1.regular"))
    assert got.warnings == ()


def test_the_drip_seven_year_jantri_of_the_sample() -> None:
    """'7 Year Jantri Calculation C1'!C34 at 1.61 Ha and the designed spacing
    floored at 1.2: 1.37."""
    got = bilinear(DRIP7, area=D("1.61"), spacing=D("1.37"), scale_above_max=False)
    assert _close(got.unit_cost, _expected("drip", "seven_year.crop1.unit_cost"))


def test_the_mini_regular_jantri_of_the_sample() -> None:
    """'New Subsidy Calculation'!G30 at 0.8 Ha and 7.5 m, the smallest row: the
    clamp and the workbook agree exactly on the row itself."""
    got = bilinear(MINI, area=D("0.8"), spacing=D("7.5"))
    assert _close(got.unit_cost, _expected("mini_sprinkler", "jantri.crop1.regular"))
    assert not has("spacing_outside_table", got.warnings)


def test_the_mini_seven_year_jantri_of_the_sample() -> None:
    """'7 Year Jantri Calculation'!G34 at 0.8 Ha and the designed spacing floored
    at 8."""
    got = bilinear(MINI7, area=D("0.8"), spacing=D("8"), scale_above_max=False)
    assert _close(got.unit_cost, _expected("mini_sprinkler", "seven_year.crop1.unit_cost"))


def test_the_sprinkler_lookups_of_the_sample() -> None:
    regular = table_1d((r["area"], r["cost"]) for r in MATRICES["sprinkler"]["regular"]["rows"])
    seven = table_1d((r["area"], r["cost"]) for r in MATRICES["sprinkler"]["seven_year"]["rows"])
    assert lookup_1d(regular, D("1.000")) == _expected("sprinkler", "jantri.regular")
    assert lookup_1d(seven, D("1")) == _expected("sprinkler", "jantri.seven_year")
    assert lookup_1d(regular, D("1.1")) is None
    assert lookup_1d(regular, D("2.01")) == D("33297.63")
    # the workbook's own float noise, kept as the cell holds it
    assert lookup_1d(regular, D("0.6")) == D("16533.333333333332")


# ── the brackets ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("area", "lo", "hi"), [
    ("0.1", "0.2", "0.4"), ("0.2", "0.2", "0.4"), ("0.3", "0.2", "0.4"), ("0.4", "0.4", "1"),
    ("1", "1", "2"), ("1.61", "1", "2"), ("4.999", "4", "5"), ("5", "5", None), ("7", "5", None),
])
def test_the_area_bracket_is_the_workbooks(area: str, lo: str, hi: str | None) -> None:
    got_lo, got_hi = area_bracket(DRIP.areas, D(area))
    assert (got_lo, got_hi) == (D(lo), D(hi) if hi else None)


@pytest.mark.parametrize(("spacing", "hi", "lo"), [
    ("13", "12", "10"), ("12", "12", "10"), ("11", "12", "10"), ("10", "10", "9"),
    ("5", "5", "4"), ("4.5", "5", "4"), ("1.37", "1.5", "1.2"), ("1.2", "1.2", "1"),
    ("1", "1", None), ("0.5", "1", None),
])
def test_the_spacing_bracket_is_the_workbooks(spacing: str, hi: str, lo: str | None) -> None:
    got_hi, got_lo = spacing_bracket(DRIP.spacings, D(spacing))
    assert (got_hi, got_lo) == (D(hi), D(lo) if lo else None)


# ── the boundaries, from the rules ───────────────────────────────────────────

def test_above_five_hectares_scales_the_five_hectare_value() -> None:
    at_five = bilinear(DRIP, area=D("5"), spacing=D("5")).unit_cost
    got = bilinear(DRIP, area=D("6"), spacing=D("5"))
    assert got.unit_cost == at_five * D("6") / D("5")
    assert has("area_above_table", got.warnings)


def test_the_sub_one_metre_guard_is_a_cliff_the_workbook_has() -> None:
    """Rule 7(a): at exactly 1 m the 1 m row interpolates on area; at 0.999 m the
    guard returns the 1 m row at the lower column, with no area interpolation."""
    at_one = bilinear(DRIP, area=D("1.61"), spacing=D("1"))
    below = bilinear(DRIP, area=D("1.61"), spacing=D("0.999"))
    assert _close(at_one.unit_cost, D("238452.59"))
    assert below.unit_cost == D("153773") and has("spacing_outside_table", below.warnings)


def test_the_sub_area_guard_is_a_cliff_the_workbook_has() -> None:
    """Rule 8: at 0.200 Ha and 4.5 m the value interpolates between the 5 and 4 m
    rows; at 0.199 Ha the guard returns the 5 m row's 0.2 column."""
    at = bilinear(DRIP, area=D("0.200"), spacing=D("4.5"))
    below = bilinear(DRIP, area=D("0.199"), spacing=D("4.5"))
    assert at.unit_cost == D("25225")
    assert below.unit_cost == D("24734") and has("area_below_table", below.warnings)


def test_below_the_smallest_row_the_engine_clamps_and_the_workbook_extrapolates() -> None:
    """Rule 7(b), Mini Sprinkler at 7 m: the workbook's next row is 0."""
    clamped = bilinear(MINI, area=D("0.8"), spacing=D("7"))
    at_row = bilinear(MINI, area=D("0.8"), spacing=D("7.5"))
    assert clamped.unit_cost == at_row.unit_cost and has("spacing_outside_table", clamped.warnings)
    workbook = bilinear(MINI, area=D("0.8"), spacing=D("7"), outside=OutsideTable.EXTRAPOLATE)
    assert _close(workbook.unit_cost, at_row.unit_cost * (D("1") - D("0.5") / D("7.5")))


def test_above_the_largest_row_the_engine_clamps_and_the_workbook_goes_negative() -> None:
    """Rule 7(c), the edge-case pass's finding: at 20 m the workbook's unit cost is
    below zero."""
    at_row = bilinear(MINI, area=D("0.8"), spacing=D("9"))
    clamped = bilinear(MINI, area=D("0.8"), spacing=D("20"))
    assert clamped.unit_cost == at_row.unit_cost and has("spacing_outside_table", clamped.warnings)
    workbook = bilinear(MINI, area=D("0.8"), spacing=D("20"), outside=OutsideTable.EXTRAPOLATE)
    assert workbook.unit_cost < 0


@pytest.mark.parametrize("matrix", [DRIP, MINI], ids=["drip", "mini"])
def test_the_clamped_jantri_is_never_negative_and_monotone_in_spacing(matrix: Matrix2D) -> None:
    """A unit cost falls as spacing widens (fewer laterals per hectare) and never
    below zero, for every spacing from 0.1 to 50 m in tenths."""
    previous: Decimal | None = None
    spacing = D("1")
    while spacing <= D("50"):
        got = bilinear(matrix, area=D("1.5"), spacing=spacing).unit_cost
        assert got >= 0
        if previous is not None:
            assert got <= previous, spacing
        previous = got
        spacing += D("0.1")
    for tenth in range(1, 10):
        assert bilinear(matrix, area=D("1.5"), spacing=D(tenth) / 10).unit_cost >= 0


def test_the_spacing_weight_is_exact_at_a_row_and_halfway_between_two() -> None:
    at_row = bilinear(DRIP, area=D("3"), spacing=D("4"))
    assert at_row.unit_cost == DRIP.at(D("4"), D("3"))
    halfway = bilinear(DRIP, area=D("3"), spacing=D("4.5"))
    assert halfway.unit_cost == (DRIP.at(D("5"), D("3")) + DRIP.at(D("4"), D("3"))) / 2


def test_the_seven_year_table_has_no_one_metre_row_and_floors_are_the_callers() -> None:
    assert DRIP7.smallest_spacing == D("1.2") and DRIP.smallest_spacing == D("1")
    assert MINI7.spacings == (D("9"), D("8")) and MINI.spacings == (D("9"), D("8"), D("7.5"))


def test_interpolation_is_exact_where_the_exact_answer_terminates() -> None:
    """The half-paisa boundary the cross-vendor review found.

    Two chained divisions, one per axis, each rounding at 28 significant digits,
    left area 0.462 Ha at 1.45 m on 62971.24999999999999999999999 where the exact
    value is 62971.25. The 70 % subsidy then rounded down: 44079.87 rather than
    44079.88. One rupee a hundred times is a reconciliation.

    Both weights are now carried as exact ratios and divided once, so a value
    whose exact answer terminates inside 28 digits comes out exact.
    """
    from api.domain.money import round2

    got = bilinear(DRIP, area=D("0.462"), spacing=D("1.45")).unit_cost
    assert got == D("62971.25"), got
    assert round2(got * D("0.7")) == D("44079.88")


def test_interpolation_matches_exact_rational_arithmetic() -> None:
    """The defect class, checked against an oracle sharing none of its arithmetic.

    `Fraction` is exact, so it says what the bilinear answer *is*. Wherever that
    exact answer terminates inside the decimal context the engine must return it
    to the digit: those are the values that can sit on a half-paisa, and a hair
    either way is a rupee on the quotation.

    The grid is deliberate. Over 3,445 terminating values in it, the chained-
    division arithmetic this replaced was wrong on 160 - so a sparser sweep passes
    against the defect and proves nothing. Keep the thousandth-hectare step.
    """
    from fractions import Fraction

    F = Fraction  # noqa: N806 - the oracle reads better short

    def exact(area: Decimal, spacing: Decimal) -> F:
        a_lo, a_hi = area_bracket(DRIP.areas, area)
        s_hi, s_lo = spacing_bracket(DRIP.spacings, spacing)
        assert a_hi is not None and s_lo is not None, "the sweep stays inside the table"
        t = (F(area) - F(a_lo)) / (F(a_hi) - F(a_lo))
        w = (F(s_hi) - F(spacing)) / (F(s_hi) - F(s_lo))

        def along(s: Decimal) -> F:
            return F(DRIP.at(s, a_lo)) + (F(DRIP.at(s, a_hi)) - F(DRIP.at(s, a_lo))) * t

        return along(s_hi) + (along(s_lo) - along(s_hi)) * w

    terminating = 0
    for thousandths in range(200, 700, 3):          # 0.200 to 0.699 Ha
        area = D(thousandths).scaleb(-3)
        for hundredths in range(105, 300, 5):       # 1.05 to 2.95 m
            spacing = D(hundredths).scaleb(-2)
            want = exact(area, spacing)
            got = bilinear(DRIP, area=area, spacing=spacing).unit_cost
            # A fraction terminates as a decimal when its denominator is 2s and 5s.
            den = want.denominator
            for factor in (2, 5):
                while den % factor == 0:
                    den //= factor
            if den == 1:
                terminating += 1
                assert F(got) == want, (area, spacing, got, want)
            else:
                assert abs(F(got) - want) < F(1, 10**20), (area, spacing)
    assert terminating > 3000, terminating
