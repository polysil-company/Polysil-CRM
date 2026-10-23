"""FS-063: the AP cap mode (`excl_gst`), the portal pipeline and AP sprinkler.

Synthetic figures run everywhere; the workbook checks need the withheld samples."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from api.domain.subsidy.categories import category_rows, state_gst
from api.domain.subsidy.money import RoundingPolicy, round2
from api.domain.subsidy.state_pipelines import portal_manual
from api.domain.subsidy.types import (
    Category,
    CropInput,
    JantriFigures,
    Line,
    Masters,
    QuotationInput,
    SubsidyError,
    SystemPolicy,
)
from tests.domain import state_masters as sm

D = Decimal
ZERO = D(0)



def _rows(*, cost: str, basis: str, pct: str = "50", ceiling: str | None = None,
          fraction: str = "0.5", rupee: bool = False, floor: bool = False):  # type: ignore[no-untyped-def]
    c = D(cost)
    gst = c * D("0.05")
    jantri = JantriFigures(D(basis), D(basis), D(basis), None, ZERO, ZERO, None)
    rows = category_rows((Category("c", "C", D(pct), "regular"),), cost=c, total_gst=gst,
                         sump=ZERO, area=D(1), jantri=jantri, seven_year_applicable=False,
                         gsdma_max_area=None, cap_mode="excl_gst", share_floor_zero=floor,
                         subsidy_cap=D(ceiling) if ceiling else None,
                         farmer_gst_fraction=D(fraction), round_rupee=rupee)
    return rows[0], c, gst


# ── rules 1 to 5 ─────────────────────────────────────────────────────────────

def test_the_subsidy_takes_the_lower_of_basis_and_cost() -> None:
    row, _, _ = _rows(cost="32155.81", basis="30405")
    assert row.exact.subsidy == D("15202.5")                 # 50 % of the unit cost
    row, _, _ = _rows(cost="20000", basis="30405")
    assert row.exact.subsidy == D("10000")                   # 50 % of the cost


def test_the_ceiling_caps_every_category() -> None:
    row, _, _ = _rows(cost="60000", basis="50000", ceiling="19000")
    assert row.exact.subsidy == D("19000")
    row, _, _ = _rows(cost="60000", basis="50000")
    assert row.exact.subsidy == D("25000"), "no ceiling row, no ceiling (EC-2)"


def test_the_farmer_pays_his_fraction_of_the_gst() -> None:
    row, c, gst = _rows(cost="32155.81", basis="30405")
    assert row.exact.farmer_share == c - D("15202.5") + gst / 2
    assert row.money.farmer_share == D("17757.21")           # K8 = 17,757.20525
    whole, c, gst = _rows(cost="32155.81", basis="30405", fraction="1")
    assert whole.exact.farmer_share == c - D("15202.5") + gst
    assert state_gst(c, gst, D(1)) == ZERO


@pytest.mark.parametrize("cost", ["10000.10", "20000.30", "32155.81", "134699.21", "99.99",
                                  "12345.67", "0.01", "777777.77"])
def test_subsidy_share_and_state_gst_make_the_printed_total(cost: str) -> None:
    """Rule 3, EC-1: odd half-paisa GST halves; the state's part is the remainder."""
    for fraction in ("0.5", "0.25", "1"):
        row, c, gst = _rows(cost=cost, basis="5000", fraction=fraction)
        total = round2(c + gst)
        f = D(fraction)
        assert row.money.subsidy + row.money.farmer_share + state_gst(c, gst, f) \
            == total, (cost, fraction)
        # code review F-2: the identity alone holds for any state_gst; pin both halves
        state = ZERO if f == 1 else total - round2(c) - round2(gst * f)
        assert state_gst(c, gst, f) == state, (cost, fraction)
        assert row.money.farmer_share == round2(c) - row.money.subsidy + round2(gst * f) \
            or f == 1, (cost, fraction)


def test_the_rupee_rounding_comes_before_the_share() -> None:
    row, _, _ = _rows(cost="134699.21", basis="134367", pct="90", rupee=True)
    assert row.money.subsidy == D("120930")                  # 120,930.30 on the portal is 120,930
    assert row.money.farmer_share == D("17136.69")
    assert row.money.subsidy_pct == D("89.78"), "subsidy / cost before GST (rule 5)"


def test_a_fraction_outside_zero_to_one_is_a_fault() -> None:
    with pytest.raises(ValueError):
        _rows(cost="100", basis="100", fraction="1.5")


# ── portal_manual (rules 7 to 11) ────────────────────────────────────────────

POLICY = SystemPolicy("drip", RoundingPolicy(frozenset(), frozenset()), cap_mode="excl_gst",
                      farmer_gst_fraction=D("0.5"), subsidy_round_rupee=True)
MASTERS = Masters({}, None, (Category("eligible_90", "Eligible 90%", D(90), "regular"),))


def _portal(**kw: object) -> QuotationInput:
    base = QuotationInput(
        "drip", (CropInput(None, None, D("1.02"), "", D(5),
                           (Line("Plain lateral 16 mm", "No.", D("8.43"), D(2310)),)),),
        head_lines=(Line("Screen filter", "No.", D("2337.76"), D(1)),),
        guided_cost=D("20000"), fittings_amount=D("1000"))
    return replace(base, **kw)  # type: ignore[arg-type]


def test_the_portal_figures_are_taken_as_given() -> None:
    res = portal_manual(_portal(), MASTERS, POLICY)
    b = res.total
    assert b.cost_excl_gst == D("2337.76") + D("8.43") * 2310 + 1000
    assert b.fittings == D(1000) and b.total_gst == b.cost_excl_gst * D("0.05")
    row = res.crops[0].categories[0]
    assert row.money.subsidy == D(18000), "90 % of the guided cost, the lower"
    assert row.money.subsidy + row.money.farmer_share + b.gst_paid_by_state \
        == round2(b.total_incl_gst)


@pytest.mark.parametrize(("change", "code"), [
    ({"guided_cost": None}, "guided_cost_required"),
    ({"guided_cost": D(0)}, "guided_cost_required"),
    ({"fittings_amount": None}, "fittings_amount_required"),
    ({"fittings_amount": D(-1)}, "fittings_amount_required"),
    ({"head_lines": (), "crops": (CropInput(None, None, D(1), "", D(5), ()),)}, "zero_cost"),
    ({"crops": (CropInput(None, None, D(0), "", D(5), ()),)}, "zero_area"),
])
def test_the_portal_pipeline_refuses_what_it_cannot_use(change: dict[str, object],
                                                        code: str) -> None:
    with pytest.raises(SubsidyError) as err:
        portal_manual(_portal(**change), MASTERS, POLICY)
    assert err.value.code == code


def test_unlikely_portal_figures_warn() -> None:
    res = portal_manual(_portal(guided_cost=D("900000"), fittings_amount=D("500000")),
                        MASTERS, POLICY)
    assert any(w.startswith("guided_cost_above_cost") for w in res.warnings)
    assert any(w.startswith("fittings_above_material") for w in res.warnings)
    assert not portal_manual(_portal(), MASTERS, POLICY).warnings


# ── AP sprinkler on the workbook ─────────────────────────────────────────────

@sm.needs_state_samples
def test_ap_sprinkler_has_no_inspection_and_a_flat_transport() -> None:
    """EC-3, EC-5: inspection 0; transport 900 at a step and between steps."""
    res = sm.run("AP/sprinkler", sm.example("AP/sprinkler"))
    assert res.total.inspection == ZERO and res.total.cgst_e == ZERO
    assert round2(res.total.total_incl_gst) == D("33763.60")
    assert res.total.gst_paid_by_state == D("803.89")
    assert res.sprinkler is not None and res.sprinkler.lines[-1].amount == D(900)
    q = sm.example("AP/sprinkler")
    between = sm.run("AP/sprinkler", replace(q, crops=(replace(q.crops[0], area=D("1.1")),)))
    assert between.sprinkler is not None and between.sprinkler.lines[-1].amount == D(900)


@sm.needs_state_samples
def test_ap_sprinkler_above_two_hectares_has_no_unit_cost() -> None:
    """GAP-477: the sheet's table stops at 2 Ha; above it the subsidy is 0, warned."""
    q = sm.example("AP/sprinkler")
    res = sm.run("AP/sprinkler", replace(q, crops=(replace(q.crops[0], area=D(3)),)))
    assert all(c.money.subsidy == 0 for c in res.crops[0].categories)
    assert any(w.startswith("no_unit_cost_for_size") for w in res.warnings)


@sm.needs_state_samples
def test_ap_drip_reproduces_the_portal_to_the_paisa() -> None:
    """EC-1: the engine's own paisa figures, not only the portal's rupees."""
    res = sm.run("AP/drip", sm.example("AP/drip"))
    row = res.crops[0].categories[0]
    assert (row.money.subsidy, row.money.farmer_share) == (D(120930), D("17136.69"))
    assert res.total.gst_paid_by_state == D("3367.48")
