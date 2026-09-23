"""Request and response shapes for /quotations and /public/q (FS-005 4).

The frontend builds against these. Field descriptions become the field notes in
the generated API doc (CLAUDE.md 2.3). Money is a decimal string at two places,
rates and percentages at three, never a float (rule 4). Every mutation on an
existing quotation accepts `expected_status`.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from api.schemas.leads import (
    UUID_RE,
    OrgUnitRef,
    PageMeta,
    PartnerRef,
    Stage,
    TerritoryRef,
    UserRef,
)
from api.schemas.products import MAX_LINES, _places

SalesType = Literal["commercial", "industrial", "export", "subsidised", "marketing", "sample"]
Status = Literal["draft", "sent", "viewed", "accepted", "rejected", "negotiation", "expired"]
Decision = Literal["accepted", "rejected", "negotiation"]
PdfState = Literal["pending", "ready", "failed"]
Channel = Literal["whatsapp", "none"]

_GSTIN_RE = r"^[0-9]{2}[A-Za-z]{5}[0-9]{4}[A-Za-z][0-9A-Za-z]{3}$"


# ── requests ─────────────────────────────────────────────────────────────────

class Party(BaseModel):
    """Who the quotation is addressed to. Copied from the lead at creation and
    editable while draft; printed as it stands at send (rule 3)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=200)]
    mobile: Annotated[str, Field(
        description="Any Indian form; stored as +91XXXXXXXXXX. The WhatsApp link goes here.")]
    address: Annotated[str | None, Field(default=None, max_length=500)]
    gstin: Annotated[str | None, Field(
        default=None, pattern=_GSTIN_RE,
        description="A company buyer's GSTIN, upper-cased on save and printed if given.")]


class QuotationLineIn(BaseModel):
    """One line as the builder posts it. `price_list_item_id` and `gst_rate_id`
    are what the preview returned; if either differs from what re-resolves, the
    save is refused with 409 rate_changed and the screen re-previews."""

    product_id: Annotated[str, Field(pattern=UUID_RE)]
    qty: Annotated[Decimal, Field(
        gt=0, description="At most as many decimals as the unit admits, and a multiple of "
                          "`pack_multiple` when the product sets one.")]
    discount_pct: Annotated[Decimal, Field(
        default=Decimal("0"), ge=0, le=100,
        description="The first discount tier, per cent off the gross.")]
    discount2_pct: Annotated[Decimal, Field(
        default=Decimal("0"), ge=0, le=100,
        description="The second tier, per cent off the balance after the first.")]
    discount3_pct: Annotated[Decimal, Field(
        default=Decimal("0"), ge=0, le=100,
        description="The third tier, per cent off the balance after the second.")]
    price_list_item_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="From the preview. Refused with rate_changed if it no longer resolves.")]
    gst_rate_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="From the preview. Refused with rate_changed if it no longer resolves.")]

    @field_validator("qty")
    @classmethod
    def _qty_places(cls, v: Decimal) -> Decimal:
        return _places(v, 3, "qty")

    @field_validator("discount_pct", "discount2_pct", "discount3_pct")
    @classmethod
    def _discount_places(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        return _places(v, 3, str(info.field_name))

    @property
    def discounts(self) -> tuple[Decimal, Decimal, Decimal]:
        return (self.discount_pct, self.discount2_pct, self.discount3_pct)


class QuotationCreate(BaseModel):
    """A draft on a lead. Everything but `lead_id` and `lines` defaults from the
    lead: the party, the place of supply, the partner and the sales type."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    lead_id: Annotated[str, Field(pattern=UUID_RE)]
    sales_type: Annotated[SalesType | None, Field(
        default=None,
        description="Defaults to the lead's inquiry type. commercial and industrial are "
                    "priced today; the others are refused with sales_type_unsupported "
                    "naming the question that blocks them.")]
    partner_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="OMIT the field for the lead's assigned partner. Send null for a direct "
                    "sale at the farmer tier. Decides the price tier and who sees the row.")]
    place_of_supply_territory_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="Where the goods are delivered. Defaults to the lead's territory.")]
    seller_gstin_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="Which of our registrations supplies. Defaults to the one in force.")]
    price_effective_date: Annotated[dt.date | None, Field(
        default=None,
        description="Price against the masters in force on this date. Today in India by "
                    "default; a future date is allowed and warns.")]
    party: Party | None = Field(default=None, description="Defaults from the lead.")
    terms: Annotated[str | None, Field(default=None, max_length=2000,
                                        description="Free text printed at the foot.")]
    lines: Annotated[list[QuotationLineIn], Field(
        default_factory=list, max_length=MAX_LINES,
        description="Zero to 200. A draft may be saved empty; sending needs at least one.")]

    @property
    def partner_given(self) -> bool:
        """Explicit null means a direct sale; an omitted field means the lead's partner."""
        return "partner_id" in self.model_fields_set


class QuotationPatch(BaseModel):
    """Change a draft's header. Every change re-prices the lines."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sales_type: SalesType | None = None
    partner_id: Annotated[str | None, Field(default=None, pattern=UUID_RE,
                                             description="Send null for a direct sale.")]
    place_of_supply_territory_id: Annotated[str | None, Field(default=None, pattern=UUID_RE)]
    seller_gstin_id: Annotated[str | None, Field(default=None, pattern=UUID_RE)]
    price_effective_date: dt.date | None = None
    party: Party | None = None
    terms: Annotated[str | None, Field(default=None, max_length=2000)]
    expected_status: Annotated[Status | None, Field(
        default=None, description="Act only if the quotation is still in this status; "
                                  "otherwise 409 status_changed.")]

    @property
    def partner_given(self) -> bool:
        return "partner_id" in self.model_fields_set


class LinesReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: Annotated[list[QuotationLineIn], Field(max_length=MAX_LINES,
                                                   description="The whole basket, in order.")]
    expected_status: Status | None = None


class SendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Annotated[Channel, Field(
        default="whatsapp",
        description="whatsapp: the link goes to the party's mobile once the PDF is ready. "
                    "none: no message; share the link yourself.")]
    expected_status: Status | None = None


class TransitionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    to: Annotated[Decision, Field(description="What the customer said.")]
    remark: Annotated[str | None, Field(default=None, max_length=1000)]
    expected_status: Status | None = None


class ReviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_effective_date: Annotated[dt.date | None, Field(
        default=None, description="Defaults to today: a revision is a new offer at today's "
                                  "rates.")]
    expected_status: Status | None = None


class DeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_status: Status | None = None


# ── responses ────────────────────────────────────────────────────────────────

class LeadRef(BaseModel):
    id: str
    inquiry_no: str
    stage: Stage


class SellerRef(BaseModel):
    """The registration supplying. The master while draft; the row's own snapshot
    once sent, so a later correction of the master changes nothing here."""

    id: str
    gstin: str
    legal_name: str
    address: str | None = None
    state: str = Field(description="The state code, e.g. GJ.")


class PlaceOfSupply(BaseModel):
    territory: TerritoryRef
    state: str = Field(description="The state code the tax is worked out against.")


class PriceListRef(BaseModel):
    id: str
    name: str


class QuotationLine(BaseModel):
    """Every figure the document prints, in print order. The three discount
    tiers are the client's own columns; `discount` is their sum and `taxable`
    the balance after the third."""

    line_no: int
    product_id: str
    description: str
    hsn_code: str
    uom: str
    qty: str
    rate: str
    gross: str
    discount_pct: str = Field(description="The first tier's percentage.")
    discount1_amt: str
    after_discount1: str
    discount2_pct: str
    discount2_amt: str
    after_discount2: str
    discount3_pct: str
    discount3_amt: str
    discount: str = Field(description="The three amounts summed. Not gross x discount_pct.")
    taxable: str
    gst_slab: str
    cgst_rate: str
    sgst_rate: str
    igst_rate: str
    cgst: str
    sgst: str
    igst: str
    total: str
    price_list_id: str
    price_list_item_id: str
    gst_rate_id: str
    provisional_fields: list[str]


class Totals(BaseModel):
    gross: str
    discount: str
    taxable: str
    cgst: str
    sgst: str
    igst: str
    total: str


class VersionRef(BaseModel):
    id: str
    version: int


class Quotation(BaseModel):
    """The document. Every key is always present; null means not set."""

    id: str
    quote_no: str | None = Field(description="Null while draft; allocated at send.")
    version: int
    status: Status
    sales_type: SalesType
    source: Literal["internal", "external"]
    lead: LeadRef | None = Field(description="Null when the lead is deleted or outside your "
                                             "lead scope.")
    party: Party
    partner: PartnerRef | None
    owner: UserRef | None = Field(description="The lead's owner; null while unassigned.")
    owner_org_unit: OrgUnitRef
    territory: TerritoryRef
    seller_gstin: SellerRef
    place_of_supply: PlaceOfSupply
    intra_state: bool
    price_effective_date: str
    price_list: PriceListRef | None = Field(description="Null when the lines drew from more "
                                                        "than one list.")
    price_list_ids: list[str]
    lines: list[QuotationLine]
    totals: Totals
    is_provisional: bool = Field(description="Any line carries a stand-in rate or slab. The "
                                             "PDF carries a banner; show the same.")
    warnings: list[str] = Field(description="Each is `code: sentence`.")
    terms: str | None
    valid_until: str | None
    sent_at: str | None
    viewed_at: str | None
    open_count: int
    accepted_at: str | None
    rejected_at: str | None
    decided_by: UserRef | None
    decision_remark: str | None
    supersedes: VersionRef | None
    superseded_by: VersionRef | None
    share_url: str | None = Field(description="Present on every read once sent.")
    pdf_state: PdfState | None = Field(description="pending | ready | failed once sent.")
    pdf_error: str | None
    created_at: str
    created_by: UserRef | None
    updated_at: str


class QuotationSummary(BaseModel):
    """The header, for lists and the versions strip."""

    id: str
    quote_no: str | None
    version: int
    status: Status
    sales_type: SalesType
    lead: LeadRef | None
    party_name: str
    party_mobile: str
    partner: PartnerRef | None
    owner: UserRef | None
    totals: Totals
    is_provisional: bool
    valid_until: str | None
    sent_at: str | None
    viewed_at: str | None
    pdf_state: PdfState | None
    superseded_by: VersionRef | None
    created_at: str


class QuotationPage(BaseModel):
    data: list[QuotationSummary]
    meta: PageMeta


class PdfLink(BaseModel):
    url: str = Field(description="Open it in a new tab. Valid for ten minutes.")
    expires_at: str
    filename: str


class PublicSeller(BaseModel):
    legal_name: str
    gstin: str


class PublicQuotation(BaseModel):
    """What the farmer's link shows before the PDF: no name, no mobile, no
    address, no lines. The PDF has all of it, one request further."""

    quote_no: str
    version: int
    status: Status
    sales_type: SalesType
    seller: PublicSeller
    sent_at: str | None
    valid_until: str | None
    expired: bool
    superseded: bool
    totals: Totals
    line_count: int
    pdf_ready: bool
    pdf_url: str
