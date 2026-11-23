# ruff: noqa: E501  (field declarations)

"""The customer record (FS-041): request and response shapes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.leads import UUID_RE, PageMeta, TerritoryRef, TimelineEvent

CustomerType = Literal["farmer", "institution", "company"]
ConsentChannel = Literal["whatsapp", "form", "verbal", "written"]


class Customer(BaseModel):
    """A farmer or buyer, made when one of their leads reached qualified. Name, email,
    area and address are the customer's own and show to everyone who sees any of its
    leads."""

    id: str
    customer_type: str = Field(description="farmer, institution or company.")
    name: str
    mobile: str = Field(description="E.164. The customer's identity: one customer per number.")
    email: str | None
    territory: TerritoryRef | None
    village: str | None
    address: str | None
    survey_no: str | None
    consent_given_at: str | None = Field(description="When consent was recorded. Null: not given, or withdrawn.")
    consent_channel: str | None = Field(description="whatsapp, form, verbal or written.")
    lead_count: int = Field(description="Its leads you can see, not counting deleted or merged ones.")
    created_at: str
    updated_at: str


class CustomerPage(BaseModel):
    data: list[Customer]
    meta: PageMeta


class CustomerLead(BaseModel):
    id: str
    inquiry_no: str
    stage: str
    source: str = Field(description="The lead source code: what brought this enquiry (REQ-108).")
    campaign_name: str | None
    created_at: str


class CustomerQuotation(BaseModel):
    id: str
    quote_no: str | None
    status: str
    total: str
    lead_id: str
    sent_at: str | None


class CustomerOrder(BaseModel):
    id: str
    order_no: str | None
    status: str
    total: str
    lead_id: str
    submitted_at: str | None


class CustomerDetail(Customer):
    leads: list[CustomerLead] = Field(description="Its leads you can see, newest first, at most 100.")
    quotations: list[CustomerQuotation] = Field(description="Quotations on those leads you can see, newest first, at most 100.")
    orders: list[CustomerOrder] = Field(description="Orders on those leads you can see, newest first, at most 100. An order with no lead is not here (GAP-262).")


class CustomerTimelineEvent(TimelineEvent):
    lead_id: str | None = Field(default=None, description="The lead it happened on; null for the customer's own events.")
    inquiry_no: str | None = None


class CustomerTimeline(BaseModel):
    data: list[CustomerTimelineEvent]
    meta: PageMeta


class CustomerPatch(BaseModel):
    """Send only what changes. email, territory_id, village, address and survey_no may
    be sent null to clear them. The mobile is not editable here (GAP-261)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_type: CustomerType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    territory_id: str | None = Field(default=None, pattern=UUID_RE, description="An active district, taluka or village.")
    village: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    survey_no: str | None = Field(default=None, max_length=100)
    consent_given: bool | None = Field(default=None, description="true records consent now (needs consent_channel); false withdraws it. Re-sending true with the same channel keeps the first date.")
    consent_channel: ConsentChannel | None = Field(default=None, description="Required with consent_given: true.")

    @field_validator("name")
    @classmethod
    def _one_space(cls, v: str | None) -> str | None:
        return " ".join(v.split()) if v is not None else v
