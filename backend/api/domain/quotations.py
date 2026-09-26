"""The quotation lifecycle and its pure rules (FS-005 3 and 6). No SQLAlchemy.

The state table is the source for the service's checks and for the database
trigger's second enforcement (ADR-039): migration 012's
`refuse_sent_quotation_edit()` carries the same pairs, and
tests/db/test_migration_012.py holds the two equal.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import secrets
from decimal import ROUND_HALF_UP, Decimal

# ── the lifecycle (FS-005 3) ─────────────────────────────────────────────────

TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"sent"}),
    "sent": frozenset({"viewed", "accepted", "rejected", "negotiation", "expired"}),
    "viewed": frozenset({"accepted", "rejected", "negotiation", "expired"}),
    "negotiation": frozenset({"accepted", "rejected", "expired"}),
}

# accepted, rejected and expired accept no transition
TERMINAL: frozenset[str] = frozenset({"accepted", "rejected", "expired"})

# what the customer's answer may be, through POST /transition
DECISIONS: frozenset[str] = frozenset({"accepted", "rejected", "negotiation"})

# where a new version may start from (rule 10, GAP-114): not from a draft, which
# is edited, and not from an accepted document, which is a commitment
REVISABLE: frozenset[str] = frozenset({"sent", "viewed", "negotiation", "rejected", "expired"})

# rule 9, the client's answer of 4 Sep
VALIDITY_DAYS = 45

# rule 18: the two sales types priced today; the other four name their question
SALES_TYPES_ACCEPTED: frozenset[str] = frozenset({"commercial", "industrial"})
SALES_TYPE_BLOCKED_ON: dict[str, str] = {
    "export": "question 14.5: zero-rated under a LUT, or IGST charged and refunded",
    "marketing": "questions 6.11 and 14.6: the 50/50 split, limits and approval",
    "sample": "question 6.12: charged or free, and who approves",
    "subsidised": "Milestone 3: the subsidised quotation is built on the FS-008 calculator",
}

# the lead's inquiry type is the quotation's default sales type
INQUIRY_TO_SALES_TYPE: dict[str, str] = {
    "commercial": "commercial", "industrial": "industrial", "subsidised": "subsidised",
}

# the lead stages a quotation may be created on (rule 1) and the ones the lead
# lock refuses outright (GAP-119); new and contacted are lead_not_qualified
CREATABLE_ON: frozenset[str] = frozenset({"qualified", "quoted", "negotiation", "won"})
LEAD_NOT_OPEN: frozenset[str] = frozenset({"lost", "dormant", "merged"})

# what the API reports for the worker's own rendering state (round 4 B-5)
PDF_STATE_PUBLIC: dict[str, str] = {"rendering": "pending"}


def can_transition(frm: str, to: str) -> bool:
    return to in TRANSITIONS.get(frm, frozenset())


def is_expired(valid_until: dt.date | None, today: dt.date) -> bool:
    """Past validity, whatever the stored status says (rule 10). `today` is
    today_ist(), never current_date."""
    return valid_until is not None and valid_until < today


def valid_until(sent_on: dt.date) -> dt.date:
    return sent_on + dt.timedelta(days=VALIDITY_DAYS)


# ── the share link (rule 13) ─────────────────────────────────────────────────

def share_token() -> str:
    """32 random bytes, URL-safe, 43 characters. Minted at send, stored in clear:
    a capability to read one PDF, and anyone who can read the table can read the
    quotation anyway."""
    return secrets.token_urlsafe(32)


def limiter_key(token: str) -> str:
    """The token never becomes a Redis key (edge case 18)."""
    return hashlib.sha256(token.encode()).hexdigest()[:32]


def share_url(public_web_url: str, token: str) -> str:
    return f"{public_web_url.rstrip('/')}/q/{token}"


# ── the PDF (rule 3) ─────────────────────────────────────────────────────────

def storage_key(quotation_id: str, version: int, lease: str) -> str:
    """One object per lease. A worker whose lease was reclaimed writes beside the
    published document, never over it: the render carries the day it was made, so
    two renders of one version are not the same bytes (cross-vendor A-4). A
    stale attempt leaves an orphan object, which is cheaper than a wrong one."""
    return f"quotations/{quotation_id}/v{version}-{lease}.pdf"


_UNSAFE = re.compile(r"[^A-Za-z0-9]+")


def pdf_filename(quote_no: str, version: int) -> str:
    return f"{_UNSAFE.sub('-', quote_no).strip('-')}-v{version}.pdf"


# ── the public projection (§4) ───────────────────────────────────────────────

# Every key the public JSON may carry. A property test asserts none of the party
# columns is here: a link forwarded to the wrong person learns a number and a
# total, not who the farmer is.
PUBLIC_FIELDS: tuple[str, ...] = (
    "quote_no", "version", "status", "sales_type", "seller", "sent_at", "valid_until",
    "expired", "superseded", "totals", "line_count", "pdf_ready", "pdf_url",
)
PARTY_COLUMNS: frozenset[str] = frozenset({
    "party_name", "party_mobile", "party_address", "party_gstin", "lead_id", "lines",
    "owner_user_id", "terms",
})


# ── discount approval (FS-013 rule 2a) ───────────────────────────────────────

_PCT = Decimal("0.01")


def effective_discount_pct(gross: Decimal, discount: Decimal) -> Decimal:
    """What the customer saves off the list price across the three tiers, in percent,
    to two places, half up. 0 on a zero gross. For display: the gate below is exact."""
    if gross == 0:
        return Decimal("0.00")
    return (discount * 100 / gross).quantize(_PCT, rounding=ROUND_HALF_UP)


def discount_approval_required(gross: Decimal, discount: Decimal,
                               owner_limit_pct: Decimal | None) -> bool:
    """Exact, no rounding: a discount a hair above the limit needs approval even when
    it displays as the limit. None is no limit."""
    if owner_limit_pct is None:
        return False
    return discount * 100 > owner_limit_pct * gross
