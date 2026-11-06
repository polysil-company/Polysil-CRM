"""Payments (FS-022): the rules that need no database.

Money is Decimal throughout (CLAUDE.md 4.1 rule 4). Balances are derived from
payable, received and what the instalments say is due; nothing here is stored.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

Status = Literal["not_applicable", "unpaid", "part_paid", "paid", "overpaid"]

ZERO: Final = Decimal("0.00")
CENT: Final = Decimal("0.01")
MAX_INSTALMENTS: Final = 5
MODES: Final = ("neft", "upi", "cheque", "cash", "adjustment")
REF_REQUIRED: Final = frozenset({"neft", "upi", "cheque"})

# The SQLSTATEs migration 031 raises: (status, code)
SQLSTATE_TO_ERROR: Final[dict[str, tuple[int, str]]] = {
    "PAYOA": (422, "over_allocated"),
    "PAYMA": (422, "must_allocate"),
    "PAYNP": (409, "order_not_payable"),
    "PAYPM": (422, "partner_mismatch"),
    "PAYRF": (422, "ref_required"),
    "PAYDR": (409, "duplicate_reference"),
    "PAYAV": (409, "already_void"),
    "PAYSP": (422, "schedule_over_payable"),
    "PAYNF": (404, "not_found"),
    "PAYPC": (409, "order_has_payments"),
    "PAYRS": (422, "reason_required"),
}


def two_places(v: Decimal) -> bool:
    """A third decimal is refused, never rounded (review edge case 9)."""
    return v == v.quantize(CENT)


def status(payable: Decimal, received: Decimal) -> Status:
    """`not_applicable` first: a zero-value order (a replacement) is neither unpaid nor paid."""
    if payable <= 0:
        return "not_applicable"
    if received <= 0:
        return "unpaid"
    if received < payable:
        return "part_paid"
    if received == payable:
        return "paid"
    return "overpaid"


def overdue_amount(due: Decimal, received: Decimal) -> Decimal:
    """What the instalments due by today ask for beyond what was received."""
    return max(ZERO, due - received)


def balance(payable: Decimal, received: Decimal) -> Decimal:
    return payable - received


@dataclass(frozen=True)
class Instalment:
    seq: int
    due_on: dt.date
    amount: Decimal


def covered(instalments: Sequence[Instalment], received: Decimal) -> list[bool]:
    """Taken in due order, each is covered once received reaches the running sum.
    The answer is in the order given."""
    result = [False] * len(instalments)
    running = ZERO
    due_order = sorted(range(len(instalments)),
                       key=lambda k: (instalments[k].due_on, instalments[k].seq))
    for k in due_order:
        running += instalments[k].amount
        result[k] = received >= running
    return result


def schedule_problems(rows: Sequence[tuple[dt.date, Decimal]], payable: Decimal) -> dict[str, str]:
    """Before the definer: at most five, each positive with two places, the sum within payable."""
    out: dict[str, str] = {}
    if len(rows) > MAX_INSTALMENTS:
        out["instalments"] = f"up to {MAX_INSTALMENTS}"
    for i, (_, amount) in enumerate(rows):
        if amount <= 0 or not two_places(amount):
            out[f"instalments.{i}.amount"] = "positive, two decimal places"
    if not out and sum((a for _, a in rows), ZERO) > payable:
        out["instalments"] = "more than payable"
    return out


@dataclass(frozen=True)
class LedgerEntry:
    on: dt.date
    kind: Literal["order", "benefit", "receipt"]
    ref: str
    debit: Decimal | None
    credit: Decimal | None
    tiebreak: str = ""


@dataclass(frozen=True)
class LedgerRow:
    entry: LedgerEntry
    balance: Decimal


def ledger(entries: Iterable[LedgerEntry], *, start: dt.date | None,
           end: dt.date | None) -> tuple[Decimal, list[LedgerRow], Decimal]:
    """Opening (everything before `start`), the rows in [start, end] with a running
    balance, and the closing balance. Positive: the dealer owes. On one day an order
    comes before a receipt (review edge case 12)."""
    rank = {"order": 0, "benefit": 1, "receipt": 2}
    ordered = sorted(entries, key=lambda e: (e.on, rank[e.kind], e.tiebreak))
    opening, running = ZERO, ZERO
    rows: list[LedgerRow] = []
    for e in ordered:
        delta = (e.debit or ZERO) - (e.credit or ZERO)
        if start is not None and e.on < start:
            opening += delta
            continue
        if end is not None and e.on > end:
            continue
        running = (opening if not rows else running) + delta
        rows.append(LedgerRow(e, running))
    closing = rows[-1].balance if rows else opening
    return opening, rows, closing
