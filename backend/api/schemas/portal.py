# ruff: noqa: E501  (field declarations)

"""The consumer portal (FS-044): a farmer's own record. Money is a decimal string."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PortalMe(BaseModel):
    name: str
    mobile: str
    email: str | None
    village: str | None
    territory_name: str | None
    consent_given_at: str | None
    consent_channel: str | None


class PortalConsent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent_given: bool = Field(description="true records consent now (channel portal); false withdraws it.")


class PortalEnquiry(BaseModel):
    inquiry_no: str
    status: str = Field(description="in_progress, won or closed.")
    system: str = Field(description="The irrigation system asked about.")
    created_at: str


class PortalQuotation(BaseModel):
    quote_no: str | None
    status: str = Field(description="sent, accepted or closed.")
    total: str | None = Field(description="Null on a dealer's quotation.")
    sent_at: str | None
    valid_until: str | None
    link: str | None = Field(description="The page the farmer was sent; null on a dealer's quotation.")


class PortalDispatch(BaseModel):
    dc_no: str | None
    dispatched_at: str


class PortalOrder(BaseModel):
    order_no: str
    status: str = Field(description="in_progress, being_revised, dispatched, closed or cancelled.")
    total: str | None = Field(description="Null on a dealer's order.")
    submitted_at: str | None
    dispatches: list[PortalDispatch]


class PortalComplaint(BaseModel):
    complaint_no: str
    status: str = Field(description="in_progress or closed.")
    raised_at: str | None
