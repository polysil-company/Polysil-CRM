"""Payments (FS-022): receipts, allocations, instalments, the order's position, the ledger."""

# ruff: noqa: E501  (field descriptions are the generated API doc)

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.domain import payments as domain
from api.schemas.leads import UUID_RE, PageMeta, UserRef

_Id = Annotated[str, Field(pattern=UUID_RE)]
Mode = Literal["neft", "upi", "cheque", "cash", "adjustment"]
Status = Literal["not_applicable", "unpaid", "part_paid", "paid", "overpaid"]
Money = Annotated[Decimal, Field(gt=0, max_digits=14, description="Rupees, at most two decimal places, as a string.")]


class _In(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _two_places(v: Decimal) -> Decimal:
    if not domain.two_places(v):
        raise ValueError("at most two decimal places")
    return v


class AllocationIn(_In):
    sales_order_id: _Id
    amount: Money

    _places = field_validator("amount")(_two_places)


class PaymentIn(_In):
    partner_id: _Id | None = Field(default=None, description="The dealer. Null for a direct (farmer) order's payment, which must then be allocated in full.")
    mode: Mode
    ref_no: Annotated[str | None, Field(default=None, min_length=1, max_length=100, description="UTR, UPI or cheque number. Required for neft, upi and cheque.")]
    received_on: dt.date
    amount: Money
    is_short_payment: bool = Field(default=False, description="Recorded as given; it changes no figure (GAP-208).")
    remark: Annotated[str | None, Field(default=None, max_length=2000, description="Internal. Never shown to a dealer.")]
    allocations: Annotated[list[AllocationIn], Field(default_factory=list, max_length=50)]

    _places = field_validator("amount")(_two_places)


class AllocateIn(_In):
    allocations: Annotated[list[AllocationIn], Field(min_length=1, max_length=50)]


class VoidIn(_In):
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class InstalmentIn(_In):
    due_on: dt.date
    amount: Money
    note: Annotated[str | None, Field(default=None, max_length=200)]

    _places = field_validator("amount")(_two_places)


class ScheduleIn(_In):
    instalments: Annotated[list[InstalmentIn], Field(max_length=5, description="0 to 5; replaces the plan.")]


class PartnerName(BaseModel):
    id: str
    name: str


class OrderNo(BaseModel):
    id: str
    order_no: str | None


class AllocationOut(BaseModel):
    sales_order: OrderNo
    amount: str
    order_balance: str | None = Field(description="The order's balance now. Null when you may not see the order.")


class Voided(BaseModel):
    at: str
    by: UserRef | None
    reason: str | None = Field(description="Null for a dealer.")


class Payment(BaseModel):
    id: str
    partner: PartnerName | None
    mode: Mode
    ref_no: str | None
    received_on: str
    amount: str
    allocated: str
    unallocated: str
    is_short_payment: bool
    remark: str | None = Field(description="Null for a dealer.")
    entered_by: UserRef | None
    entered_at: str
    voided: Voided | None
    allocations: list[AllocationOut]


class PaymentPage(BaseModel):
    data: list[Payment]
    meta: PageMeta


class InstalmentOut(BaseModel):
    seq: int
    due_on: str
    amount: str
    note: str | None
    covered: bool = Field(description="Received has reached this instalment, taken in due order.")


class ReceiptOut(BaseModel):
    payment_id: str
    received_on: str
    mode: Mode
    ref_no: str | None
    amount: str = Field(description="What this receipt put on this order.")
    is_short_payment: bool


class OrderPayments(BaseModel):
    payable: str = Field(description="The order total; 0 when cancelled. Less scheme benefits once schemes land.")
    received: str
    balance: str
    status: Status
    overdue: bool
    overdue_amount: str
    schedule: list[InstalmentOut]
    receipts: list[ReceiptOut]


class LedgerRowOut(BaseModel):
    on: str
    kind: Literal["order", "benefit", "receipt"] = Field(
        description="`order` debits its total; `benefit` credits a scheme or reward benefit on it "
                    "(ADR-050); `receipt` credits a payment.")
    ref: str
    debit: str | None
    credit: str | None
    balance: str = Field(description="Positive: the dealer owes. Negative: the dealer's credit.")


class PartnerCredit(BaseModel):
    """A dealer's credit position now (FS-027). For Accounts, and for staff who edit
    dealers and can see this one; never for a dealer or a distributor."""

    partner_id: str
    credit_limit: str | None = Field(description="The dealer's limit; null when none is set, "
                                                 "and then the dealer is never checked.")
    exposure: str = Field(description="Owed on the dealer's open orders less its live receipts. "
                                      "Negative: the dealer is in credit.")
    available: str | None = Field(description="Limit less exposure; null when there is no limit. "
                                              "Negative: over the limit.")
    check: str = Field(description="The company setting dealer_credit_check: off, warn or block.")


class Ledger(BaseModel):
    partner: PartnerName
    from_: str | None = Field(alias="from")
    to: str | None
    opening_balance: str
    rows: list[LedgerRowOut]
    closing_balance: str
    unallocated: str = Field(description="Live receipts not yet spread over orders. Information only.")

    model_config = ConfigDict(populate_by_name=True)
