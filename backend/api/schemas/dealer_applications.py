# ruff: noqa: E501  (field declarations)

"""Partner applications (FS-051, FS-071): staff start one for a dealer or a
distributor, the applicant fills the data sheet through a link, the deposit is paid
or relaxed, and a role the settings name decides."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from api.schemas.leads import UUID_RE, UserRef
from api.schemas.messages import _no_nul

Status = Literal["draft", "submitted", "returned", "approved", "rejected", "withdrawn"]
FirmType = Literal["proprietorship", "partnership", "llp", "company"]
_Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), AfterValidator(_no_nul)]
_Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000), AfterValidator(_no_nul)]
PartnerType = Literal["dealer", "distributor"]
DepositStatus = Literal["paid", "waived", "pending", "not_required"]
_T32 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=32), AfterValidator(_no_nul)]
_T100 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100), AfterValidator(_no_nul)]
_T100R = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100), AfterValidator(_no_nul)]
_T200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200), AfterValidator(_no_nul)]
_T300R = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300), AfterValidator(_no_nul)]
_T1000 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000), AfterValidator(_no_nul)]

# Decimal strings: digits, at most 2 decimals; no sign, exponent or NaN (FS-071 E-17)
Lakhs = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{1,5}(\.[0-9]{1,2})?$")]
Area = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{1,7}(\.[0-9]{1,2})?$")]
Money = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{1,8}(\.[0-9]{1,2})?$")]


class WorkingCapitalRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facility: _T100R
    amount_lakhs: Lakhs


class ManpowerRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: _T100R
    qualification: _T100 | None = None
    work_type: _T100 | None = None
    experience_years: Annotated[int | None, Field(default=None, ge=0, le=80)] = None
    people: Annotated[int, Field(ge=1, le=9999)]


class InstallationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: Annotated[int, Field(ge=1950, le=2200, description="Not after this year.")]
    customers: Annotated[int, Field(ge=0, le=999999)]
    description: _T300R
    scope: Literal["supply", "installation", "both"]
    cost_lakhs: Lakhs


class DealerApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    firm_name: _Text200
    contact_name: _Text200
    mobile: Annotated[str, Field(max_length=32, description="Any Indian form; it becomes the dealer's login.")]
    territory_id: Annotated[str, Field(pattern=UUID_RE)]
    lead_id: Annotated[str | None, Field(default=None, pattern=UUID_RE)] = None
    partner_type: PartnerType = Field(default="dealer", description="The deposit due is copied from this type's setting now.")


class DealerApplicationFields(BaseModel):
    """The applicant's fields. Send only what changes. An empty string clears a text;
    `null` clears anything, and a list is replaced whole."""
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
    # FS-071: the data sheet
    telephone: _T32 | None = None
    established_on: dt.date | None = Field(default=None, description="From 1900, not after today.")
    bank_name: _T200 | None = None
    bank_branch: _T200 | None = None
    bank_address: _T1000 | None = None
    working_capital: Annotated[list[WorkingCapitalRow] | None, Field(default=None, max_length=10)] = None
    other_sources_lakhs: Lakhs | None = None
    two_wheelers: Annotated[int | None, Field(default=None, ge=0, le=999)] = None
    cars: Annotated[int | None, Field(default=None, ge=0, le=999)] = None
    other_vehicles: _T200 | None = None
    office_area: Area | None = None
    godown_area: Area | None = None
    area_unit: Literal["sq_m", "sq_ft"] | None = None
    manpower: Annotated[list[ManpowerRow] | None, Field(default=None, max_length=20)] = None
    previous_installations: Annotated[list[InstallationRow] | None, Field(default=None, max_length=50)] = None
    sales_executives: Annotated[int | None, Field(default=None, ge=0, le=9999)] = None
    technicians: Annotated[int | None, Field(default=None, ge=0, le=9999)] = None
    appointment_place: _T200 | None = None


class StaffApplicationFields(DealerApplicationFields):
    """Staff may also change the type, while draft or returned and before any deposit
    entry. The applicant's PATCH refuses it."""
    partner_type: PartnerType | None = None


class DepositRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Money = Field(description="Rupees, a decimal string above 0, at least the amount due.")
    paid_on: dt.date = Field(description="Not after today; not more than a year before the application.")
    reference: _T100 | None = None
    slip_id: Annotated[str, Field(pattern=UUID_RE, description="A deposit_slip document on this application.")]


class DepositRelaxation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_due: Money = Field(description="The new amount due, below the current one; 0 waives it.")
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000), AfterValidator(_no_nul)]


class DepositEntry(BaseModel):
    kind: Literal["payment", "relaxation"]
    amount: str | None = Field(default=None, description="A payment's amount.")
    paid_on: str | None = None
    reference: str | None = None
    slip_id: str | None = None
    from_due: str | None = Field(default=None, description="A relaxation's old amount due.")
    to: str | None = Field(default=None, description="A relaxation's new amount due.")
    reason: str | None = None
    by: UserRef | None = None
    at: str


class Deposit(BaseModel):
    status: DepositStatus
    amount_set: str = Field(description="Copied from the type's setting when the application was made.")
    amount_due: str = Field(description="After any relaxation.")
    paid_amount: str | None
    paid_on: str | None
    reference: str | None
    slip_id: str | None
    history: list[DepositEntry] = Field(description="Payments and relaxations, oldest first.")


class DealerApplicationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject", "return"]
    remark: Annotated[str | None, Field(default=None, max_length=1000, description="Required to reject or return.")]
    parent_id: Annotated[str | None, Field(default=None, pattern=UUID_RE, description="A dealer's active distributor; null: directly under Polysil. Always null for a distributor.")]
    code: Annotated[str | None, Field(default=None, max_length=32, description="The partner code; null: the next DLR-<state>-0001, or DIST-<state>-0001 for a distributor.")]


class DealerApplicationRemark(BaseModel):
    model_config = ConfigDict(extra="forbid")
    remark: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class DealerGstLookup(BaseModel):
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


class DealerApplication(BaseModel):
    id: str
    status: Status
    partner_type: PartnerType
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
    telephone: str | None
    established_on: str | None
    bank_name: str | None
    bank_branch: str | None
    bank_address: str | None
    working_capital: list[dict[str, object]] | None
    other_sources_lakhs: str | None
    working_capital_total_lakhs: str | None = Field(description="The rows plus other sources; null when neither is filled.")
    two_wheelers: int | None
    cars: int | None
    other_vehicles: str | None
    office_area: str | None
    godown_area: str | None
    area_unit: Literal["sq_m", "sq_ft"]
    manpower: list[dict[str, object]] | None
    previous_installations: list[dict[str, object]] | None
    sales_executives: int | None
    technicians: int | None
    appointment_place: str | None
    deposit: Deposit
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
    can: dict[str, bool] = Field(description="edit, decide, withdraw, renew, record_deposit, relax_deposit.")


class DealerApplicationRow(BaseModel):
    id: str
    status: Status
    partner_type: PartnerType
    deposit_status: DepositStatus
    firm_name: str
    contact_name: str
    territory_name: str
    created_at: str
    submitted_at: str | None


class DealerApplicantSession(BaseModel):
    session: str = Field(description="Send as X-Apply-Session on every later call, for 2 hours.")
