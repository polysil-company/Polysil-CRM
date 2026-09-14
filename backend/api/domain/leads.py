"""Lead logic, the pure half. No SQLAlchemy (rule 1), no I/O.

FS-003 3, 6. The stage machine, mobile normalisation, the Indian financial year and
the priority score live here so they run in thousands of cases with no database. The
service in api/services/leads.py calls these and owns the transaction.
"""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

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
    "quoted": frozenset({"negotiation", "lost"}),
    "negotiation": frozenset({"won", "lost"}),
}

# won, lost and merged accept no transition and no edit; a lost lead is reopened.
TERMINAL: frozenset[str] = frozenset({"won", "lost", "merged"})

# Moving into these needs an accepted quotation, and no quotation table exists yet,
# so the service refuses them with quotation_required until FS-005 (GAP-051).
REQUIRES_QUOTATION: frozenset[str] = frozenset({"quoted", "negotiation", "won"})

# A lead must carry all of these before it can be qualified (FS-003 3).
QUALIFICATION_FIELDS: tuple[str, ...] = (
    "farmer_name", "mobile", "territory_id", "mis_system_id", "inquiry_type")


def can_transition(frm: str, to: str) -> bool:
    """True if `frm -> to` is a move the stage machine allows."""
    return to in TRANSITIONS.get(frm, frozenset())


# ── mobile normalisation (FS-003 6 rule 1, EC-13, GAP-052) ───────────────────

class MobileError(ValueError):
    """A mobile that is not an Indian number. The service turns it into a 422 with
    fields.mobile."""


def normalise_mobile(raw: str) -> str:
    """Any Indian form a person types or pastes into +91XXXXXXXXXX.

    First NFKC-normalise and keep only digit values and a leading plus, so spaces,
    hyphens, brackets, dots, bidi marks and non-ASCII (Devanagari) digits all fall
    away. Then the Indian rules: a leading +91, 91 or 0 is stripped, and the ten
    digits must start 6 to 9. A foreign +<cc> number is refused (GAP-052).
    """
    if not raw:
        raise MobileError("mobile is required")
    s = unicodedata.normalize("NFKC", raw)
    had_plus = False
    seen_digit = False
    digits: list[str] = []
    for ch in s:
        value = unicodedata.digit(ch, None)
        if value is not None:
            digits.append(str(value))
            seen_digit = True
        elif ch == "+" and not seen_digit:
            had_plus = True
    d = "".join(digits)

    if had_plus:
        if d.startswith("91") and len(d) == 12:
            d = d[2:]
        else:
            # +<something else> is a foreign number, or a malformed +91 (GAP-052).
            raise MobileError("only Indian mobile numbers are accepted")
    elif d.startswith("91") and len(d) == 12:
        d = d[2:]
    elif d.startswith("0") and len(d) == 11:
        d = d[1:]

    if len(d) == 10 and d[0] in "6789":
        return "+91" + d
    raise MobileError("not an Indian mobile number")


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
    total = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if total >= config["threshold_hot"]:
        band = "hot"
    elif total >= config["threshold_warm"]:
        band = "warm"
    else:
        band = "cold"
    return total, band
