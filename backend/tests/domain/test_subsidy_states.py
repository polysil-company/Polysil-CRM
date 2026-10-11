"""FS-056: the CG, RJ and UP workbooks, reproduced to the paisa, and the rules
around them."""

from __future__ import annotations

from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

import pytest

from api.domain.subsidy.categories import category_rows
from api.domain.subsidy.jantri import RowTable
from api.domain.subsidy.types import Category, JantriFigures, SubsidyError
from tests.domain import state_masters as sm

D = Decimal
ZERO = D(0)


def r2(x: Decimal) -> Decimal:
    return x.quantize(D("0.01"), ROUND_HALF_UP)


@sm.needs_state_samples
@pytest.mark.parametrize("key", sm.ENTRIES)
def test_each_state_workbook_reproduces_to_the_paisa(key: str) -> None:
    expected = sm.SAMPLES[key]["example"]
    res = sm.run(key, sm.example(key))
    crop = res.crops[0]
    row = next(c for c in crop.categories if c.code == expected["category"])
    want = {k: D(v) for k, v in expected["expected"].items()}
    assert res.total.total_incl_gst == want["total_incl_gst"]
    assert crop.jantri.regular_for_cap == want["unit_cost"]
    assert row.exact.subsidy == want["subsidy"]
    assert row.exact.farmer_share == want["farmer_share"]
    assert (row.money.subsidy, row.money.farmer_share) == (r2(want["subsidy"]),
                                                           r2(want["farmer_share"]))


def test_every_state_entry_is_present() -> None:
    assert set(sm.ENTRIES) == {"CG/drip", "CG/sprinkler", "RJ/drip", "RJ/mini_sprinkler",
                               "RJ/sprinkler", "UP/drip", "UP/mini_sprinkler", "UP/sprinkler"}


# ── cap modes (rules 2 to 4) ─────────────────────────────────────────────────

def _jantri(value: str) -> JantriFigures:
    v = D(value)
    return JantriFigures(v, v, v, None, ZERO, ZERO, None)


def _one(cap_mode: str, *, cost: str, gst: str, basis: str, floor: bool = False,
         extra: str = "0", pct: str = "55") -> tuple[Decimal, Decimal]:
    rows = category_rows((Category("c", "C", D(pct), "regular"),), cost=D(cost),
                         total_gst=D(gst), sump=D("999"), area=D(1), jantri=_jantri(basis),
                         seven_year_applicable=False, gsdma_max_area=None, cap_mode=cap_mode,
                         share_floor_zero=floor, share_extra=D(extra))
    return rows[0].exact.subsidy, rows[0].exact.farmer_share


def test_incl_gst_caps_on_the_total_and_ignores_the_sump() -> None:
    sub, share = _one("incl_gst", cost="1000", gst="50", basis="2000")
    assert sub == D("577.50") and share == D("472.50"), "55 % of 1050; the sump plays no part"
    sub, share = _one("incl_gst", cost="1000", gst="50", basis="500", extra="295")
    assert sub == D("275") and share == D("1070"), "the unit cost binds; the flat charge is added"


def test_unit_cost_only_has_no_cap_and_floors_the_share() -> None:
    sub, share = _one("unit_cost_only", cost="1000", gst="50", basis="5000", pct="75")
    assert sub == D("3750") and share == ZERO


def test_an_unknown_cap_mode_is_a_fault() -> None:
    with pytest.raises(ValueError):
        _one("other", cost="1", gst="0", basis="1")


# ── label and size tables (rules 8, 11, 14) ──────────────────────────────────

def test_labels_match_without_case_or_spaces() -> None:
    t = RowTable({RowTable.key("1.2X0.30"): {D("1"): D("100")}})
    assert t.row("1.2x0.30") is not None and t.row(" 1.2 X 0.30 ") is not None


def test_a_label_table_prorates_below_and_zeroes_above_when_set() -> None:
    t = RowTable({"a": {D("0.2"): D("10000"), D("0.4"): D("18000")}})
    assert t.anchored("a", D("0.1"), prorate_below=True, zero_above=False) == D("5000")
    assert t.anchored("a", D("0.3"), prorate_below=True, zero_above=False) == D("14000")
    assert t.anchored("a", D("0.5"), prorate_below=True, zero_above=True) == ZERO
    assert t.anchored("a", D("0.1"), prorate_below=False, zero_above=False) is None


def test_a_size_table_with_a_blank_neighbour_is_none() -> None:
    t = RowTable({"63": {D("1.8"): D("100"), D("2"): D("120")}})
    assert t.stepped("63", D("1.9")) == D("110")
    assert t.stepped("63", D("2.1")) is None
    assert t.stepped("110", D("1")) is None


def test_the_cg_label_table_reproduces_the_workbooks_grid() -> None:
    """Rule 11: anchors at 0.4, 1 to 5 Ha, straight line, to the rupee, gives the sheet's
    0.05 Ha cells. Spot cells taken from the workbook at 0.4, 0.65 and 2.35 Ha."""
    t = sm.unit_cost("CG/drip")
    assert isinstance(t, RowTable)
    label = next(iter(t.rows))
    row = t.rows[label]
    v = t.anchored(label, D("0.4"), prorate_below=False, zero_above=False)
    assert v == row[D("0.4")]
    mid = t.anchored(label, D("0.7"), prorate_below=False, zero_above=False)
    assert mid is not None and row[D("0.4")] < mid < row[D("1")]


# ── the pipelines' own rules ─────────────────────────────────────────────────

@sm.needs_state_samples
def test_rj_deductions_floor_the_unit_cost_at_zero() -> None:
    q = replace(sm.example("RJ/drip"), head_unit_existing=True, pvc_existing=True,
                hydrocyclone_m3=ZERO, gravel_filter_m3=ZERO)
    q = replace(q, crops=(replace(q.crops[0], area=D("0.01")),))
    res = sm.run("RJ/drip", q)
    assert res.crops[0].jantri.regular_for_cap == ZERO
    assert any(w.startswith("unit_cost_below_zero") for w in res.warnings)


@sm.needs_state_samples
def test_rj_refuses_a_filter_size_with_no_rate_and_a_zero_cost() -> None:
    with pytest.raises(SubsidyError):
        sm.run("RJ/drip", replace(sm.example("RJ/drip"), hydrocyclone_m3=D("21")))
    q = sm.example("RJ/drip")
    empty = replace(q, head_lines=(), crops=(replace(q.crops[0], lines=()),))
    with pytest.raises(SubsidyError) as err:
        sm.run("RJ/drip", empty)
    assert err.value.code == "zero_cost"


@sm.needs_state_samples
def test_a_state_sprinkler_needs_the_set_size() -> None:
    with pytest.raises(SubsidyError) as err:
        sm.run("UP/sprinkler", replace(sm.example("UP/sprinkler"), pipe_size_mm=None))
    assert err.value.code == "pipe_size_required" and err.value.field_path == "pipe_size_mm"


@sm.needs_state_samples
def test_a_size_with_no_unit_cost_gives_no_subsidy() -> None:
    q = sm.example("CG/sprinkler")
    m = sm.masters("CG/sprinkler")
    assert isinstance(m.regular, RowTable)
    no_75 = RowTable({k: v for k, v in m.regular.rows.items() if k != "75"})
    res = sm.run("CG/sprinkler", replace(q, pipe_size_mm=75), m=replace(m, regular=no_75))
    assert all(c.exact.subsidy == ZERO for c in res.crops[0].categories)
    assert any(w.startswith("no_unit_cost_for_size") for w in res.warnings)


@sm.needs_state_samples
def test_cg_drip_needs_a_known_label_and_one_crop() -> None:
    q = sm.example("CG/drip")
    for bad, code in ((replace(q, spacing_label=None), "spacing_label_required"),
                      (replace(q, spacing_label="9 x 9"), "spacing_label"),
                      (replace(q, crops=q.crops * 2), "crop_count")):
        with pytest.raises(SubsidyError) as err:
            sm.run("CG/drip", bad)
        assert err.value.code == code


def test_every_state_parameter_fits_the_column_exactly() -> None:
    """`subsidy_parameter.value` is numeric(16,6) from 071: four places stored UP's
    0.00169 insurance rate as 0.0017 and moved the subsidy by 46 paise."""
    for key, entry in sm.PUBLIC.items():
        for name, value in entry["parameters"].items():
            exponent = D(value).as_tuple().exponent
            assert isinstance(exponent, int) and exponent >= -6, (key, name, value)


@sm.needs_state_samples
@pytest.mark.parametrize("key", ["CG/sprinkler", "RJ/sprinkler", "UP/sprinkler"])
def test_a_state_sprinkler_takes_an_area_between_steps(key: str) -> None:
    """Code review F-3: FS-055 rule 20 holds for the state sheets too."""
    q = sm.example(key)
    q = replace(q, crops=(replace(q.crops[0], area=D("1.1")),))
    res = sm.run(key, q)
    assert any(w.startswith("area_between_steps") for w in res.warnings)


def test_cg_a_plus_b_is_the_material_without_gst() -> None:
    """Code review F-5, FS-056 rule 4a: commission reads it as excl GST."""
    if not sm.SAMPLES:
        pytest.skip("samples absent")
    res = sm.run("CG/drip", sm.example("CG/drip"))
    assert res.total.a_plus_b == res.total.cost_excl_gst
