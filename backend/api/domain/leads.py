"""Lead logic, the pure half. No SQLAlchemy (rule 1), no I/O.

FS-003 3, 6. The stage machine, mobile normalisation, the Indian financial year and
the priority score live here so they run in thousands of cases with no database. The
service in api/services/leads.py calls these and owns the transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from api.domain.identity import MobileError as MobileError
from api.domain.identity import normalise_mobile as normalise_mobile

# ── the stage machine (FS-003 3) ─────────────────────────────────────────────

STAGES: tuple[str, ...] = ("new", "contacted", "qualified", "quoted", "negotiation",
                           "won", "lost", "merged", "dormant")

# from -> the stages a transition() call may move it to. merged is set only by a
# merge, dormant only by the worker, and a lost lead is reopened through its own
# endpoint, so none of those are transition targets here.
TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"contacted", "lost"}),
    "contacted": frozenset({"qualified", "lost"}),
    "qualified": frozenset({"quoted", "lost"}),
    # quoted -> won: a quotation accepted as sent never passes through negotiation,
    # and the flowchart's straight line would otherwise force a fake stage (FS-005 3)
    "quoted": frozenset({"negotiation", "won", "lost"}),
    "negotiation": frozenset({"won", "lost"}),
    # the worker parks a lead here; a person closes it as lost, or reopens it (FS-035)
    "dormant": frozenset({"lost"}),
}

# Stages a lead leaves through POST /leads/{id}/reopen: lost returns to the stage it
# was lost from, dormant to the stage it was swept from (FS-035 rule 10).
REOPENABLE: frozenset[str] = frozenset({"lost", "dormant"})

# won, lost and merged accept no transition and no edit; a lost lead is reopened.
TERMINAL: frozenset[str] = frozenset({"won", "lost", "merged"})

# Reached through the quotation, never from the lead endpoint: sending one moves
# the lead to quoted, a negotiation moves it on (FS-005 3). Refused here with
# quotation_required.
VIA_QUOTATION: frozenset[str] = frozenset({"quoted", "negotiation"})
# Reachable from the lead endpoint once an accepted quotation is linked
# (AC-LEAD-6, GAP-051 closed by FS-005); refused with quotation_required until then.
REQUIRES_QUOTATION: frozenset[str] = frozenset({"won"})

# A lead must carry all of these before it can be qualified (FS-003 3).
QUALIFICATION_FIELDS: tuple[str, ...] = (
    "farmer_name", "mobile", "territory_id", "mis_system_id", "inquiry_type")


def can_transition(frm: str, to: str) -> bool:
    """True if `frm -> to` is a move the stage machine allows."""
    return to in TRANSITIONS.get(frm, frozenset())


# ── mobile normalisation (FS-003 6 rule 1, EC-13, GAP-052) ───────────────────

# Moved to api/domain/identity.py (FS-006) and re-exported above (the explicit
# `import x as x` form) so the lead service and its tests keep importing from
# here. A lead stores the E.164 form with the plus.


# ── the Indian financial year (FS-003 6 rule 2, EC-5) ────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


def financial_year(at: datetime) -> str:
    """The Indian financial year (April to March) of `at`, as `2026-27`, computed
    from the IST-local date. A lead entered at 00:30 IST on 1 April is the new year
    although the server clock still reads 31 March (EC-5)."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    local = at.astimezone(IST)
    start = local.year if local.month >= 4 else local.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


# ── priority score (FS-003 6 rule 7, GAP-047) ────────────────────────────────

_ZERO = Decimal("0")
_ONE = Decimal("1")


def _clamp01(x: Decimal) -> Decimal:
    return max(_ZERO, min(_ONE, x))


def score(
    *,
    source_quality: Decimal,
    estimated_value: Decimal | None,
    created_at: datetime,
    first_contacted_at: datetime | None,
    event_count: int,
    config: dict[str, Decimal],
) -> tuple[Decimal, str]:
    """The weighted score and its band. Every number is a lead_score_rule row, so
    the client's admin retunes it without a release; these are the shape, not the
    values (GAP-047).

    source_quality is the source row's factor. enquiry_value scales the estimate
    against value_cap. response_speed is a step on hours to first contact.
    engagement scales the event count against engagement_cap.
    """
    value = _clamp01(estimated_value / config["value_cap"]) if estimated_value else _ZERO

    if first_contacted_at is None:
        speed = _ZERO
    else:
        hours = Decimal((first_contacted_at - created_at).total_seconds()) / Decimal(3600)
        if hours <= config["speed_fast_hours"]:
            speed = _ONE
        elif hours <= config["speed_slow_hours"]:
            speed = Decimal("0.5")
        else:
            speed = _ZERO

    engagement = _clamp01(Decimal(event_count) / config["engagement_cap"])

    raw = (config["w_source"] * _clamp01(source_quality)
           + config["w_value"] * value
           + config["w_speed"] * speed
           + config["w_engagement"] * engagement)
    # a whole number: staff read 27.5 as more precise than the weights are (walk R-12),
    # and the band follows the number they see
    total = raw.quantize(_ONE, rounding=ROUND_HALF_UP)

    if total >= config["threshold_hot"]:
        band = "hot"
    elif total >= config["threshold_warm"]:
        band = "warm"
    else:
        band = "cold"
    return total, band

# ── what a partner reads of a lead's history (ISS-107, GAP-284) ──────────────

# GAP-284: client question 20.1 is open. The suggested answer is applied: duplicate
# handling, staff notes and the lost reason are internal; the dealer's own words stay.
PARTNER_HIDDEN_KINDS: frozenset[str] = frozenset(
    {"lead.duplicate_flagged", "lead.duplicate_dismissed", "lead.merged"})
# the stage change stays (the dealer sees the lead is lost); its staff words do not
PARTNER_STRIPPED_KEYS: frozenset[str] = frozenset(
    {"lost_reason_id", "lost_reason", "lost_note", "note"})


def partner_timeline_entry(kind: str, payload: dict[str, object], *,
                           own: bool) -> dict[str, object] | None:
    """The entry as a partner caller reads it, or None when it is hidden. `own` is
    true when the caller wrote it: a partner always reads its own words."""
    if own:
        return payload
    if kind in PARTNER_HIDDEN_KINDS or kind == "lead.note_added":
        return None
    if kind in ("lead.stage_changed", "lead.reopened"):
        return {k: v for k, v in payload.items() if k not in PARTNER_STRIPPED_KEYS}
    return payload
