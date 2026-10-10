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

# rule 18 / GAP-121: the order types priced today; the rest name their question.
# FS-042 added export and sample, each on a setting standing in for its question.
TYPES_ACCEPTED: Final = frozenset({"commercial", "industrial", "export", "sample"})
TYPE_BLOCKED_ON: Final[dict[str, str]] = {
    "marketing_material": "the marketing material split and limits (question 6.11)",
    "subsidised": "the subsidy stages (Milestone 3)",
    "replacement": "complaints (W5)",
}

# FS-042: the types only staff raise (GAP-370)
STAFF_ONLY_TYPES: Final = frozenset({"export", "sample"})
# the setting's value, as the treatment stored on the document (rule 2)
EXPORT_TREATMENT: Final[dict[str, str]] = {"lut": "export_lut", "igst": "export_igst"}
# a free sample is every line at 100 % off, tier one (rule 11; FS-015b's free order)
FREE_DISCOUNTS: Final = (Decimal(100), Decimal(0), Decimal(0))


def treatment_for(order_type: str, setting: str) -> str:
    """The tax treatment a new export document stores; domestic for every other
    type. Read once, at create (FS-042 rule 5)."""
    return EXPORT_TREATMENT[setting] if order_type == "export" else "domestic"


def export_problems(order_type: str, country: str | None, party_gstin: str | None
                    ) -> dict[str, tuple[str, str]]:
    """Rule 6, before the CHECK: field -> (code, message)."""
    out: dict[str, tuple[str, str]] = {}
    if order_type == "export":
        if not country or not 2 <= len(country.strip()) <= 60:
            out["export_country"] = ("export_country_required",
                                     "An export names the buyer's country (2 to 60 characters).")
        if party_gstin:
            out["party.gstin"] = ("export_party_gstin", "An export buyer has no Indian GSTIN.")
    elif country:
        out["export_country"] = ("export_country_not_export", "Only an export names a country.")
    return out


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
                                    "quotation.approval_returned",
                                    # FS-015: the check and the QC verdict (question 15.14's rule)
                                    "complaint.returned", "complaint.approved",
                                    "complaint.qc_approved", "complaint.qc_rejected",
                                    # FS-015b: the remedy and its approval
                                    "complaint.remedy_chosen", "complaint.refund_requested",
                                    "complaint.refund_paid", "complaint.refund_rejected",
                                    "complaint.remedy_withdrawn", "complaint.replacement_ordered",
                                    "complaint.replacement_cancelled", "complaint.closed",
                                    # a replacement cancelled by its approver or by QC
                                    # (PR 38 review): a dealer may see the order
                                    "order.replacement_cancelled",
                                    # FS-043 rule 14: who entered a customer's rating
                                    "rating.recorded"})


def actor_hidden_from_partner(kind: str) -> bool:
    """True for the events whose actor is an approver: every approval event, and
    the order's return and approval, which the deciding step writes."""
    return kind.startswith("approval.") or kind in _DECIDER_KINDS

# The SQLSTATEs migration 013 raises, and what each is to the API: (status, code).
# 403 and 404 carry no code of their own beyond the envelope's.
SQLSTATE_TO_ERROR: Final[dict[str, tuple[int, str]]] = {
    "ORDNS": (409, "order_not_draft"),
    "CRDLM": (409, "credit_limit_exceeded"),   # FS-027, the block setting
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
    # FS-023: dispatch_record resolves a warehouse (code review F-1)
    "STKWI": (409, "warehouse_inactive"),
    "STKNW": (409, "no_default_warehouse"),
    "STKNF": (422, "no_such_warehouse"),
    # FS-022: a paid order's dealer does not change (code review F-2)
    "PAYPC": (409, "order_has_payments"),
    # FS-036: amending an approved order (041)
    "ORDTF": (422, "order_type_fixed"),
    "ORDPA": (409, "order_has_payments"),
    # FS-042: export and sample orders (045)
    "ORDXS": (403, "type_staff_only"),
    "ORDSF": (422, "free_sample_priced"),
    "ORDSL": (422, "sample_over_limit"),
    "ORDLT": (422, "lut_missing"),
    "ORDLX": (422, "lut_line_taxed"),
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
