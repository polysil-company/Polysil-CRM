# ruff: noqa: E501  (field declarations)

"""The consumer portal (FS-044): a farmer's own record. Money is a decimal string."""

from __future__ import annotations

from typing import Literal

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


class PortalRating(BaseModel):
    target: Literal["installation", "service"]
    order_no: str | None = Field(description="Installation: the order rated.")
    complaint_no: str | None = Field(description="Service: the complaint rated.")
    score: int = Field(description="1 to 5 stars.")
    comment: str | None = Field(description="His own words; null when an officer recorded the rating for him.")
    entered_via: Literal["portal", "staff"] = Field(description="portal: he rated it here; staff: an officer recorded it for him.")
    created_at: str = Field(description="IST, +05:30.")


class PortalRatingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["installation", "service"] = Field(description="installation: a dispatched order; service: a closed complaint.")
    order_no: str | None = Field(default=None, max_length=40, description="Installation: the order's number, as the orders list gives it.")
    complaint_no: str | None = Field(default=None, max_length=40, description="Service: the complaint's number.")
    score: int = Field(ge=1, le=5, description="1 to 5 stars.")
    comment: str | None = Field(default=None, max_length=1000, description="Optional.")
