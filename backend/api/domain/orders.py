"""Sales orders, approvals and dispatch (FS-011): the rules that need no database.

The state machine itself lives in migration 013's trigger and definers, because
the database is the second enforcer (ADR-039); this module holds what the service
checks first and what it maps the database's refusals to.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Final

# rule 18 / GAP-121: the two order types priced today; the rest name their question
TYPES_ACCEPTED: Final = frozenset({"commercial", "industrial"})
TYPE_BLOCKED_ON: Final[dict[str, str]] = {
    "export": "the export tax treatment (question 14.5)",
    "sample": "who approves samples and whether they are charged (question 6.12)",
    "marketing_material": "the marketing material split and limits (question 6.11)",
    "subsidised": "the subsidy stages (Milestone 3)",
    "replacement": "complaints (W5)",
}

# rule 15: a direct order's lead is open and qualified or later
LEAD_STAGES_ORDERABLE: Final = frozenset({"qualified", "quoted", "negotiation", "won"})

# FS-011 4: what the service refuses before the definer is asked
PARTY_FIELDS_FROM_QUOTATIONS: Final = ("partner_id", "place_of_supply_territory_id",
                                       "seller_gstin_id", "price_effective_date",
                                       "owner_org_unit_id", "territory_id")

PORTAL_REMARK: Final = "Returned for changes; your contact at Polysil will explain."

# question 15.14: a partner sees that an order was decided, never by whom
_DECIDER_KINDS: Final = frozenset({"order.returned", "order.approved",
                                    # FS-013: the discount's decision is internal too
                                    "quotation.approval_approved",
                                    "quotation.approval_returned"})


def actor_hidden_from_partner(kind: str) -> bool:
    """True for the events whose actor is an approver: every approval event, and
    the order's return and approval, which the deciding step writes."""
    return kind.startswith("approval.") or kind in _DECIDER_KINDS

# The SQLSTATEs migration 013 raises, and what each is to the API: (status, code).
# 403 and 404 carry no code of their own beyond the envelope's.
SQLSTATE_TO_ERROR: Final[dict[str, tuple[int, str]]] = {
    "ORDNS": (409, "order_not_draft"),
    "ORDNA": (422, "no_approver"),
    "ORDST": (422, "territory_without_state_code"),
    "ORDDS": (409, "order_dispatched"),
    "ORDCN": (409, "order_not_cancellable"),
    "ORDSB": (409, "order_was_submitted"),
    "ORDND": (409, "order_not_dispatchable"),
    "ORDCL": (409, "order_closed"),
    "ORDSC": (409, "status_changed"),
    "ORDNF": (404, "not_found"),
    "ORQNF": (404, "not_found"),
    "ORQNA": (422, "quotation_not_accepted"),
    "ORQON": (409, "quotation_on_order"),
    "APRPD": (409, "approval_pending"),
    "APRCL": (409, "request_closed"),
    "APRSD": (409, "step_already_decided"),
    "APREU": (409, "earlier_step_undecided"),
    "APRRM": (422, "remark_required"),
    "APRNF": (404, "not_found"),
    # FS-013, quotation discount approval
    "APRFC": (409, "figures_changed"),
    "APRNR": (409, "approval_not_required"),
    "APRNA": (422, "no_approver"),
    "QTNDR": (409, "quotation_not_draft"),
    "QTNF0": (404, "not_found"),
    "DSPLN": (422, "line_not_on_order"),
    "DSPOV": (422, "over_open_quantity"),
    "DSPPR": (422, "unit_precision"),
    "DSPVD": (409, "dispatch_voided"),
    "DSPNF": (404, "not_found"),
}


def dispatch_line_problems(line_ids: Sequence[str]) -> dict[str, str]:
    """Edge case 9, before the definer: at least one line, each at most once."""
    if not line_ids:
        return {"lines": "At least one line."}
    seen: set[str] = set()
    out: dict[str, str] = {}
    for i, line in enumerate(line_ids):
        if line in seen:
            out[f"lines[{i}].order_line_id"] = "This line is already in the dispatch."
        seen.add(line)
    return out


def dispatched_pct(ordered: Decimal, sent: Decimal) -> int:
    """How much of the ordered quantity has left, 0 to 100, rounded down, so an
    order shows 100 only when everything went."""
    if ordered <= 0:
        return 0
    pct = int(sent * 100 / ordered)
    return max(0, min(100, pct))


def open_quantity(qty: Decimal, sent: Decimal, short: Decimal) -> Decimal:
    """What can still ship on a line. Never below zero: the database refuses the
    dispatch that would take it there, and this is only a display."""
    return max(Decimal("0"), qty - short - sent)


# ── the order PDF (FS-012) ───────────────────────────────────────────────────

_UNSAFE = re.compile(r"[^A-Za-z0-9]+")


def pdf_storage_key(order_id: str, lease: str) -> str:
    """One object per lease, like the quotation's: a stale worker writes beside the
    published document, never over it."""
    return f"orders/{order_id}/{lease}.pdf"


def pdf_filename(order_no: str) -> str:
    return f"{_UNSAFE.sub('-', order_no).strip('-')}.pdf"
