"""Request and response shapes for /orders, /approvals and /dispatches (FS-011 4).

The frontend builds against these; field descriptions become the field notes in
the generated API doc. Money is a decimal string at two places, quantities at
three, never a float (rule 4).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.approvals import Approval as Approval  # re-exported
from api.schemas.approvals import ApprovalStatus as ApprovalStatus  # re-exported
from api.schemas.approvals import ApprovalStep as ApprovalStep  # re-exported
from api.schemas.approvals import Decision
from api.schemas.complaints import Complaint
from api.schemas.leads import UUID_RE, OrgUnitRef, PageMeta, PartnerRef, TerritoryRef, UserRef
from api.schemas.products import MAX_LINES, _places
from api.schemas.quotations import Quotation, QuotationLineIn, Totals

OrderType = Literal["commercial", "industrial", "export", "sample", "marketing_material",
                    "subsidised", "replacement"]
OrderStatus = Literal["draft", "submitted", "approved", "partially_dispatched", "dispatched",
                      "closed_short", "cancelled"]
PaymentTerms = Literal["full_payment", "credit"]

_GSTIN_RE = r"^[0-9]{2}[A-Za-z]{5}[0-9]{4}[A-Za-z][0-9A-Za-z]{3}$"
_EXPECTED = "The status the screen showed; a different one is 409 status_changed."


# ── requests ─────────────────────────────────────────────────────────────────

class OrderParty(BaseModel):
    """The buyer on the order: the farmer for an order on one lead, the dealer for a
    consolidated order across several (FS-011 rule 2)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=200)]
    mobile: Annotated[str | None, Field(default=None, description="Any Indian form.")]
    address: Annotated[str | None, Field(default=None, max_length=500)]
    gstin: Annotated[str | None, Field(default=None, pattern=_GSTIN_RE)]


class OrderCreate(BaseModel):
    """A draft, from accepted quotations or from lines typed in; not both."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    order_type: OrderType = Field(
        default="commercial",
        description="commercial or industrial. The other five are refused with 422 "
                    "order_type_unsupported, naming the question each waits on.")
    quotation_ids: Annotated[list[Annotated[str, Field(pattern=UUID_RE)]], Field(
        default_factory=list, max_length=20,
        description="Accepted quotations that agree on partner, place of supply, seller, "
                    "price date, office and territory. Their lines are imported.")]
    lead_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="A direct order's lead, qualified or later. Leave out when ordering from "
                    "quotations: the lead comes from them.")]
    partner_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="OMIT for your own partner (a dealer) or none (staff). Null is a direct "
                    "sale, refused from a dealer.")]
    party: OrderParty | None = Field(
        default=None, description="Required for a direct order; from the quotations otherwise.")
    delivery_address: Annotated[str | None, Field(default=None, max_length=500)]
    place_of_supply_territory_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="Where the goods go. Required for a direct order.")]
    seller_gstin_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="The selling registration. Omit for the default one.")]
    price_effective_date: Annotated[dt.date | None, Field(
        default=None, description="A direct order's price date, today in India by default.")]
    payment_terms: PaymentTerms = Field(
        default="full_payment", description="Recorded, not enforced. There is no credit check.")
    remarks: Annotated[str | None, Field(default=None, max_length=2000)]
    lines: Annotated[list[QuotationLineIn], Field(
        default_factory=list, max_length=MAX_LINES,
        description="A direct order's lines, as on a quotation.")]

    @property
    def partner_given(self) -> bool:
        return "partner_id" in self.model_fields_set


class OrderPatch(BaseModel):
    """Change a draft's header; every change re-prices. On an order from quotations
    the fields they fix stay fixed (422 quotations_disagree)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    order_type: OrderType | None = None
    partner_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="Omit to keep. Null makes it a direct sale, which a dealer cannot do.")]
    party: OrderParty | None = None
    delivery_address: Annotated[str | None, Field(default=None, max_length=500)]
    place_of_supply_territory_id: Annotated[str | None, Field(default=None, pattern=UUID_RE)]
    seller_gstin_id: Annotated[str | None, Field(default=None, pattern=UUID_RE)]
    price_effective_date: dt.date | None = None
    payment_terms: PaymentTerms | None = None
    remarks: Annotated[str | None, Field(default=None, max_length=2000)]
    expected_status: OrderStatus | None = Field(default=None, description=_EXPECTED)

    @property
    def partner_given(self) -> bool:
        return "partner_id" in self.model_fields_set


class OrderLinesReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: Annotated[list[QuotationLineIn], Field(
        max_length=MAX_LINES, description="Every line; the draft's lines are replaced.")]
    expected_status: OrderStatus | None = Field(default=None, description=_EXPECTED)


class SubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_status: OrderStatus | None = Field(default=None, description=_EXPECTED)


class RemarkRequest(BaseModel):
    """Cancel, void and close short: the reason is required and kept."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    remark: Annotated[str, Field(min_length=1, max_length=2000,
                                 description="Why. Kept on the order and its timeline.")]
    expected_status: OrderStatus | None = Field(default=None, description=_EXPECTED)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    decision: Decision = Field(
        description="reject returns the order to draft with the remark as the reason.")
    remark: Annotated[str | None, Field(
        default=None, max_length=2000,
        description="Required to reject, and on every Accounts decision.")]


class DispatchLineIn(BaseModel):
    order_line_id: Annotated[str, Field(pattern=UUID_RE)]
    qty: Annotated[Decimal, Field(
        gt=0, description="At most the line's open quantity, in the line's unit "
                          "precision (uom_decimals).")]

    @field_validator("qty")
    @classmethod
    def _qty_places(cls, v: Decimal) -> Decimal:
        return _places(v, 3, "qty")


class DispatchCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    dc_no: Annotated[str | None, Field(default=None, max_length=200)]
    dc_date: dt.date | None = None
    invoice_no: Annotated[str | None, Field(
        default=None, max_length=200,
        description="The number your accounts system issued; this system does not issue "
                    "invoices.")]
    invoice_date: dt.date | None = None
    dispatched_at: dt.datetime = Field(description="When the goods left; not in the future.")
    transporter: Annotated[str | None, Field(default=None, max_length=200)]
    vehicle_no: Annotated[str | None, Field(default=None, max_length=200)]
    lines: Annotated[list[DispatchLineIn], Field(
        max_length=MAX_LINES, description="At least one; each order line at most once.")]


class ThresholdPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_type: Literal["sales_order", "quotation", "complaint"] = "sales_order"
    role: Literal["field_officer", "district_manager", "state_manager", "regional_manager",
                  "admin_sales"] = Field(
        description="An order's rows are for the three managers, and so are a refund's "
                    "(`complaint`, rupees). A quotation's are for any of the five: the field "
                    "officer's is the officer's own limit.")
    territory_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE, description="Null for the company-wide row.")]
    max_amount: Annotated[Decimal | None, Field(
        default=None, ge=0, description="Null for no ceiling. An order's is rupees "
                                        "including GST, above 0; a quotation's is a discount "
                                        "in percent, 0 to 100 (0: no discount without "
                                        "approval).")]


# ── responses ────────────────────────────────────────────────────────────────

class OrderLeadRef(BaseModel):
    id: str
    inquiry_no: str


class QuotationRef(BaseModel):
    id: str
    quote_no: str | None
    version: int


class OrderSeller(BaseModel):
    gstin: str
    legal_name: str
    address: str | None
    state_code: str


class OrderLine(BaseModel):
    """Every figure the order prints, and where its delivery stands."""

    id: str
    line_no: int
    product_id: str
    description: str
    hsn_code: str
    uom: str
    uom_decimals: int = Field(description="How many decimals the unit takes; 0 for pieces.")
    qty: str
    rate: str
    gross: str
    discount_pct: str
    discount1_amt: str
    after_discount1: str
    discount2_pct: str
    discount2_amt: str
    after_discount2: str
    discount3_pct: str
    discount3_amt: str
    discount: str
    taxable: str
    gst_slab: str
    cgst_rate: str
    sgst_rate: str
    igst_rate: str
    cgst: str
    sgst: str
    igst: str
    total: str
    provisional_fields: list[str] = Field(
        description="Figures from stand-in master data, such as rate or gst_slab.")
    qty_dispatched: str = Field(description="Sent on dispatches that are not voided.")
    qty_short: str = Field(description="Closed short: will never ship.")
    qty_open: str = Field(description="Still to ship: qty less dispatched less short.")


class LastRejection(BaseModel):
    remark: str = Field(description="For a dealer, a fixed text in place of the reason.")
    role: str
    at: str


class DispatchLineOut(BaseModel):
    order_line_id: str
    line_no: int
    qty: str


class DispatchOrderRef(BaseModel):
    id: str
    order_no: str | None
    party_name: str


class Dispatch(BaseModel):
    id: str
    order: DispatchOrderRef = Field(description="The order this dispatch shipped against.")
    dispatch_no: str = Field(description="The order number with a sequence, per order.")
    dc_no: str | None
    dc_date: str | None
    invoice_no: str | None
    invoice_date: str | None
    dispatched_at: str
    transporter: str | None
    vehicle_no: str | None
    dispatched_by: UserRef | None
    voided_at: str | None = Field(description="Set when voided; its quantities are open again.")
    void_remark: str | None
    lines: list[DispatchLineOut]
    warnings: list[str] = Field(
        default_factory=list,
        description="invoice_before_dc, duplicate_invoice_no. Recorded anyway.")


class OrderComplaintRef(BaseModel):
    id: str
    complaint_no: str | None


class Order(BaseModel):
    doc_type: Literal["sales_order"] = Field(
        default="sales_order", description="Always sales_order. Tells an order from a "
                                           "quotation where either can come back.")
    """The order. Every key is always present; null means not set or not visible."""

    id: str
    order_no: str | None = Field(description="Null until the first submit.")
    complaint: OrderComplaintRef | None = Field(
        default=None, description="A replacement order's complaint (FS-015b).")
    status: OrderStatus
    order_type: OrderType
    party: OrderParty = Field(description="The farmer on one lead; the dealer on a "
                                          "consolidated order.")
    partner: PartnerRef | None = Field(description="Null for a direct sale.")
    lead: OrderLeadRef | None = Field(description="Null for a consolidated order across "
                                                  "several leads.")
    quotations: list[QuotationRef] = Field(description="The quotations it was made from.")
    owner: UserRef | None
    owner_org_unit: OrgUnitRef
    territory: TerritoryRef
    delivery_address: str | None
    payment_terms: PaymentTerms
    seller: OrderSeller | None = Field(description="The selling registration at the tax date.")
    place_of_supply: TerritoryRef
    intra_state: bool
    price_effective_date: str
    tax_date: str | None = Field(description="The date GST was taken at: today on a draft, "
                                             "the submit date after.")
    is_provisional: bool = Field(description="A line uses stand-in prices or tax data.")
    lines: list[OrderLine]
    totals: Totals
    approval: Approval | None = Field(description="The latest request. Null on a draft "
                                                  "never submitted.")
    last_rejection: LastRejection | None = Field(
        description="Set while a rejected order is back in draft.")
    dispatches: list[Dispatch]
    warnings: list[str] = Field(description="repriced, discontinued_products, "
                                            "provisional_pricing. Shown, never blocking.")
    remarks: str | None
    pdf_state: Literal["none", "pending", "ready", "failed"] = Field(
        description="The approved order's PDF: none before approval, pending while the "
                    "worker renders it, ready to download, or failed.")
    pdf_error: str | None = Field(default=None, description="Why the PDF failed. Staff only.")
    confirmation: Literal["queued", "no_mobile", "disabled"] | None = Field(
        default=None, description="Whether the buyer was sent the WhatsApp confirmation on "
                                  "approval: queued, no_mobile (tell the officer to call), "
                                  "or disabled. Null before approval.")
    submitted_at: str | None
    approved_at: str | None
    cancelled_at: str | None
    cancel_remark: str | None
    closed_at: str | None
    close_remark: str | None
    created_at: str


class OrderSummary(BaseModel):
    id: str
    order_no: str | None
    status: OrderStatus
    order_type: OrderType
    party_name: str
    partner: PartnerRef | None
    owner: UserRef | None
    totals: Totals
    is_provisional: bool
    dispatched_pct: int = Field(description="Share of the ordered quantity sent, 0 to 100.")
    approval_waiting_on: str | None = Field(description="The role of the next undecided step.")
    submitted_at: str | None
    created_at: str


class OrderStats(BaseModel):
    """Counts over the same scope and filters as the order list."""

    total: int = Field(description="Orders matching the filters.")
    by_status: dict[str, int] = Field(description="Every status, 0 when empty.")
    waiting_on: dict[str, int] = Field(
        description="Submitted orders by the role whose approval step is next, e.g. "
                    "{\"district_manager\": 3, \"account_manager\": 1}.")


class OrderPage(BaseModel):
    data: list[OrderSummary]
    meta: PageMeta


class QueueDocument(BaseModel):
    id: str
    number: str | None
    party_name: str
    total: str
    is_provisional: bool
    raised_by: UserRef | None
    raised_at: str = Field(description="The submit time, or when a quotation's approval "
                                       "was asked.")
    discount_pct: str | None = Field(
        default=None, description="A quotation row: the effective discount asked for, in "
                                  "percent. Null on an order.")
    request_remark: str | None = Field(
        default=None, description="Why the approval was asked, as the person asking wrote "
                                  "it. Show it beside the figures. Null when none was given.")


class QueueRow(BaseModel):
    step_id: str
    seq: int
    role: str
    stalled: bool = Field(description="Nobody of the step's own role covers the order.")
    doc_type: str = Field(description="sales_order, or quotation for a discount approval "
                                      "(FS-013); the decision returns that document.")
    document: QueueDocument
    waiting_since: str = Field(description="When the step before it was decided, or the "
                                           "submit time for the first.")


class QueuePage(BaseModel):
    data: list[QueueRow]
    meta: PageMeta


class Threshold(BaseModel):
    doc_type: str
    role: str
    territory: TerritoryRef | None = Field(description="Null for the company-wide row.")
    max_amount: str | None = Field(description="Null for no ceiling. See unit.")
    unit: Literal["inr", "pct"] = Field(
        description="inr: an order's limit including GST. pct: a quotation's discount limit.")


class DispatchPage(BaseModel):
    data: list[Dispatch]
    meta: PageMeta


class DecisionResult(BaseModel):
    """The decided document: an order, or for a discount approval (FS-013) the
    quotation, or for a refund (FS-015b) the complaint. `data.doc_type` says which."""

    data: Annotated[Order | Quotation | Complaint, Field(discriminator="doc_type")]
