"""api/domain/leads.py: the stage machine, mobile normalisation, the financial year
and the score. Pure, no database (FS-003 10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from api.domain.leads import (
    REOPENABLE,
    REQUIRES_QUOTATION,
    TERMINAL,
    TRANSITIONS,
    VIA_QUOTATION,
    MobileError,
    can_transition,
    financial_year,
    normalise_mobile,
    score,
)

# ── the stage machine ────────────────────────────────────────────────────────

def test_the_forward_path_and_lost_are_allowed() -> None:
    assert can_transition("new", "contacted")
    assert can_transition("contacted", "qualified")
    assert can_transition("qualified", "quoted")
    assert can_transition("quoted", "negotiation")
    assert can_transition("negotiation", "won")
    for frm in ("new", "contacted", "qualified", "quoted", "negotiation"):
        assert can_transition(frm, "lost")


def test_backward_and_skipping_moves_are_refused() -> None:
    assert not can_transition("qualified", "contacted")   # backward
    assert not can_transition("new", "qualified")         # skip
    assert not can_transition("new", "won")               # skip to terminal


def test_terminal_stages_have_no_transition_out() -> None:
    for term in TERMINAL:
        assert TRANSITIONS.get(term, frozenset()) == frozenset()
    assert can_transition("merged", "new") is False


def test_a_dormant_lead_can_only_be_lost_or_reopened() -> None:
    """FS-035: the worker parks a lead; a person loses it or reopens it, and no
    transition() call parks one or moves it anywhere else."""
    assert TRANSITIONS["dormant"] == frozenset({"lost"})
    assert "dormant" not in TERMINAL
    assert frozenset({"lost", "dormant"}) == REOPENABLE
    for frm in TRANSITIONS:
        assert not can_transition(frm, "dormant")


def test_the_quotation_gated_stages_are_marked() -> None:
    """FS-005: quoted and negotiation are reached through the quotation, never from
    the lead endpoint; won needs an accepted quotation on the lead."""
    assert set(VIA_QUOTATION) == {"quoted", "negotiation"}
    assert set(REQUIRES_QUOTATION) == {"won"}
    assert "won" in TRANSITIONS["quoted"], "a quotation accepted as sent skips negotiation"


# ── mobile normalisation ─────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "9876543210",
    "98765 43210",
    "+91-98765-43210",
    "+919876543210",
    "919876543210",
    "09876543210",
    "(0)98765.43210",
    "‎9876543210‏",           # WhatsApp bidi marks
    "+91 98765 43210",
    "٩٨٧٦٥٤٣٢١٠",  # arabic-indic 9876543210
])
def test_accepted_indian_forms_normalise_to_e164(raw: str) -> None:
    out = normalise_mobile(raw)
    assert out.startswith("+91") and len(out) == 13
    assert out[3] in "6789"


def test_devanagari_digits_normalise() -> None:
    # ९८७६५४३२१० = 9876543210
    assert normalise_mobile("९८७६५४३२१०") == "+919876543210"


@pytest.mark.parametrize("raw", [
    "",
    "12345",                 # too short
    "1234567890",            # starts with 1
    "5876543210",            # starts with 5
    "987654321",             # 9 digits
    "98765432101",           # 11 digits
    "+4479460000000",        # foreign
    "919876",                # 91 prefix but too short
])
def test_non_indian_or_malformed_is_refused(raw: str) -> None:
    with pytest.raises(MobileError):
        normalise_mobile(raw)


# ── financial year ───────────────────────────────────────────────────────────

def test_financial_year_is_the_ist_local_year() -> None:
    # 2026-04-01 00:30 IST is 2026-03-31 19:00 UTC: the new FY, not the old (EC-5).
    assert financial_year(datetime(2026, 3, 31, 19, 0, tzinfo=UTC)) == "2026-27"
    # a naive datetime is read as UTC
    assert financial_year(datetime(2026, 3, 31, 12, 0)) == "2025-26"
    # mid-year
    assert financial_year(datetime(2026, 9, 14, 6, 0, tzinfo=UTC)) == "2026-27"
    # 31 March 23:00 IST is still the old year
    assert financial_year(datetime(2026, 3, 31, 17, 0, tzinfo=UTC)) == "2025-26"
    # the century roll formats two digits
    assert financial_year(datetime(2099, 6, 1, tzinfo=UTC)) == "2099-00"


# ── score ────────────────────────────────────────────────────────────────────

CFG = {k: Decimal(v) for k, v in {
    "w_source": 25, "w_value": 35, "w_speed": 20, "w_engagement": 20,
    "value_cap": 500000, "speed_fast_hours": 24, "speed_slow_hours": 72,
    "engagement_cap": 10, "threshold_hot": 70, "threshold_warm": 40,
}.items()}
T0 = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)


def test_the_top_score_is_hot() -> None:
    total, band = score(source_quality=Decimal(1), estimated_value=Decimal(500000),
                        created_at=T0, first_contacted_at=T0 + timedelta(hours=1),
                        event_count=10, config=CFG)
    assert total == Decimal("100.00") and band == "hot"


def test_a_cold_lead() -> None:
    total, band = score(source_quality=Decimal("0.5"), estimated_value=None,
                        created_at=T0, first_contacted_at=None, event_count=0, config=CFG)
    # only source: 25 * 0.5 = 12.50
    assert total == Decimal("12.50") and band == "cold"


def test_response_speed_steps() -> None:
    def with_gap(hours: int) -> Decimal:
        return score(source_quality=Decimal(0), estimated_value=None, created_at=T0,
                     first_contacted_at=T0 + timedelta(hours=hours), event_count=0,
                     config=CFG)[0]
    assert with_gap(1) == Decimal("20.00")     # fast -> full 20
    assert with_gap(48) == Decimal("10.00")    # within slow -> half
    assert with_gap(100) == Decimal("0.00")    # beyond -> none


def test_value_and_engagement_clamp_at_the_cap() -> None:
    total, _ = score(source_quality=Decimal(0), estimated_value=Decimal(9_999_999),
                     created_at=T0, first_contacted_at=None, event_count=999, config=CFG)
    # value clamps to 1 (35), engagement clamps to 1 (20) -> 55
    assert total == Decimal("55.00")


def test_the_warm_boundary_is_inclusive() -> None:
    # source 1 -> 25, engagement 0.8 -> 16, total 41, at/above the warm threshold
    total, band = score(source_quality=Decimal(1), estimated_value=None, created_at=T0,
                        first_contacted_at=None, event_count=8, config=CFG)  # 25 + 20*0.8=16 -> 41
    assert total == Decimal("41.00") and band == "warm"
