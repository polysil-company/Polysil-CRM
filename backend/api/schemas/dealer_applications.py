# ruff: noqa: E501  (field declarations)

"""Dealer applications (FS-051): staff start one, the applicant fills it through a
link, a State Manager or above decides."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from api.schemas.leads import UUID_RE, UserRef
from api.schemas.messages import _no_nul

Status = Literal["draft", "submitted", "returned", "approved", "rejected", "withdrawn"]
FirmType = Literal["proprietorship", "partnership", "llp", "company"]
_Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), AfterValidator(_no_nul)]
_Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000), AfterValidator(_no_nul)]


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    firm_name: _Text200
    contact_name: _Text200
    mobile: Annotated[str, Field(max_length=32, description="Any Indian form; it becomes the dealer's login.")]
    territory_id: Annotated[str, Field(pattern=UUID_RE)]
    lead_id: Annotated[str | None, Field(default=None, pattern=UUID_RE)] = None


class ApplicationFields(BaseModel):
    """The applicant's fields. Send only what changes; an empty string clears."""
    model_config = ConfigDict(extra="forbid")
    firm_name: _Text200 | None = None
    contact_name: _Text200 | None = None
    firm_type: FirmType | None = None
    gst_registered: bool | None = None
    gstin: Annotated[str | None, Field(default=None, max_length=15, description="Checked for shape and check character.")]
    pan: Annotated[str | None, Field(default=None, max_length=10)]
    address: Annotated[str | None, Field(default=None, max_length=1000)]
    pincode: Annotated[str | None, Field(default=None, max_length=6)]
    email: Annotated[str | None, Field(default=None, max_length=254)]
    godown_address: Annotated[str | None, Field(default=None, max_length=1000)]
    years_in_business: Annotated[int | None, Field(default=None, ge=0, le=150)]
    current_brands: Annotated[str | None, Field(default=None, max_length=500)]
    notes: _Text | None = None
    bank_account_name: Annotated[str | None, Field(default=None, max_length=200)]
    bank_account_no: Annotated[str | None, Field(default=None, max_length=20)]
    bank_ifsc: Annotated[str | None, Field(default=None, max_length=11)]


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject", "return"]
    remark: Annotated[str | None, Field(default=None, max_length=1000, description="Required to reject or return.")]
    parent_id: Annotated[str | None, Field(default=None, pattern=UUID_RE, description="An active distributor; null: directly under Polysil.")]
    code: Annotated[str | None, Field(default=None, max_length=32, description="The partner code; null: the next DLR-<state>-0001.")]


class Remark(BaseModel):
    model_config = ConfigDict(extra="forbid")
    remark: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class GstLookup(BaseModel):
    gstin: str
    valid: bool
    reason: str | None = Field(description="Why it is not valid.")
    state_code: str | None
    pan: str | None
    lookup: Literal["found", "not_found", "unavailable"] = Field(
        description="unavailable until a GST data provider is configured (GAP-292): then type the names.")
    legal_name: str | None = None
    trade_name: str | None = None
    address: str | None = None
    status: str | None = None


class Application(BaseModel):
    id: str
    status: Status
    firm_name: str
    contact_name: str
    mobile: str
    territory: dict[str, str] = Field(description="{id, name}.")
    lead_id: str | None
    firm_type: str | None
    gst_registered: bool
    gstin: str | None
    pan: str | None
    address: str | None
    pincode: str | None
    email: str | None
    godown_address: str | None
    years_in_business: int | None
    current_brands: str | None
    notes: str | None
    bank_account_name: str | None
    bank_account_no: str | None = Field(description="Masked to the last 4 digits unless you can decide or edit partners.")
    bank_ifsc: str | None
    gst_lookup: dict[str, object] | None
    gst_state_mismatch: bool
    missing: list[str] = Field(description="What is still needed to submit.")
    partner_id: str | None
    user_id: str | None
    decided_by: UserRef | None
    decided_at: str | None
    decision_remark: str | None
    link_expires_at: str
    apply_url: str | None = Field(default=None, description="Only right after creating or renewing: the token is not stored.")
    created_by: UserRef | None
    created_at: str
    can: dict[str, bool] = Field(description="edit, decide, withdraw, renew.")


class ApplicationRow(BaseModel):
    id: str
    status: Status
    firm_name: str
    contact_name: str
    territory_name: str
    created_at: str
    submitted_at: str | None


class ApplicantSession(BaseModel):
    session: str = Field(description="Send as X-Apply-Session on every later call, for 2 hours.")
