"""Complaints (FS-015): the request and response shapes the frontend builds on."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.domain import complaints as domain
from api.schemas.approvals import Approval
from api.schemas.leads import UUID_RE, PageMeta, UserRef
from api.schemas.tasks import LeadLink, OrderLink, PartnerLink

Severity = Literal["low", "medium", "high"]
Status = Literal["draft", "submitted", "under_qc", "qc_approved", "qc_rejected", "cancelled",
                 "remedy_pending", "closed"]
Kind = Literal["photo", "document", "challan"]
_Id = Annotated[str, Field(pattern=UUID_RE)]
_Text = Annotated[str, Field(min_length=1, max_length=domain.TEXT_MAX)]
_Short = Annotated[str, Field(min_length=1, max_length=60)]
_Qty = Annotated[Decimal, Field(max_digits=14, decimal_places=3)]


class LineIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    product_id: _Id
    supplied_qty: _Qty = Field(description="More than zero.")
    defective_qty: _Qty = Field(description="Zero or more, not more than supplied.")
    failure_frequency: Annotated[str | None, Field(default=None, max_length=domain.FREQUENCY_MAX)]
    remark: Annotated[str | None, Field(default=None, max_length=500)]


class _Header(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    description: _Text | None = None
    contact_name: Annotated[str | None, Field(default=None, min_length=1,
                                              max_length=domain.CONTACT_NAME_MAX)]
    contact_mobile: str | None = Field(default=None, description="An Indian mobile; stored as "
                                                                 "+91XXXXXXXXXX.")
    territory_id: _Id | None = Field(default=None, description="Where the material is installed.")
    partner_id: _Id | None = Field(default=None, description="The dealer involved. A dealer "
                                                             "never sends it: it is their own.")
    lead_id: _Id | None = None
    sales_order_id: _Id | None = Field(default=None, description="Fills the challan and supply "
                                                                 "date from its latest dispatch.")
    dc_no: _Short | None = Field(default=None, description="Required to submit.")
    supply_date: dt.date | None = Field(default=None, description="Required to submit.")
    reg_no: Annotated[str | None, Field(default=None, max_length=60)]
    pims_no: Annotated[str | None, Field(default=None, max_length=60)]
    sample_courier_date: dt.date | None = None
    sample_courier_detail: Annotated[str | None, Field(default=None, max_length=500)]


class ComplaintCreate(_Header):
    complaint_type_id: _Id
    severity: Severity = "medium"
    description: _Text
    contact_name: Annotated[str, Field(min_length=1, max_length=domain.CONTACT_NAME_MAX)]
    contact_mobile: str
    territory_id: _Id
    lines: Annotated[list[LineIn], Field(min_length=1, max_length=domain.MAX_LINES)]


class ComplaintPatch(_Header):
    complaint_type_id: _Id | None = None
    severity: Severity | None = None


class LinesReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: Annotated[list[LineIn], Field(min_length=1, max_length=domain.MAX_LINES)]


class CheckIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    decision: Literal["approve", "return"]
    remark: _Text = Field(description="Shown to the raiser, a dealer included.")
    severity: Severity | None = Field(default=None, description="With approve only.")
    owner_user_id: _Id | None = Field(default=None, description="With approve only, when the "
                                                                "complaint has no owner. From "
                                                                "GET /complaints/{id}/assignees.")
    internal_note: Annotated[str | None, Field(default=None, max_length=domain.TEXT_MAX,
                                               description="Staff only; never shown to a "
                                                           "dealer.")]


class QcIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    verdict: Literal["approved", "rejected"]
    remark: _Text
    sample_received_on: dt.date | None = None
    tested_on: dt.date | None = None
    field_visit_on: dt.date | None = None
    internal_note: Annotated[str | None, Field(default=None, max_length=domain.TEXT_MAX)]


class CancelIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    reason: _Text


class ReopenIn(BaseModel):
    """FS-036: why it is being reopened. Kept on the complaint."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    reason: _Text


_Remark = Annotated[str, Field(min_length=1, max_length=1000)]


class RemedyIn(BaseModel):
    """FS-015b: what QC decides for a `qc_approved` complaint."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    kind: Literal["refund", "replacement", "none"] = Field(description=(
        "`refund`: an amount through approval. `replacement`: a free order of the defective "
        "lines. `none`: close the complaint now."))
    amount: Decimal | None = Field(default=None, gt=0, lt=Decimal("1e12"), decimal_places=2,
                                   description="Refund only: rupees, two decimals at most.")
    payee_name: Annotated[str, Field(min_length=1, max_length=200)] | None = Field(
        default=None, description="Refund only: who is paid.")
    paid_through_partner_id: str | None = Field(
        default=None, pattern=UUID_RE, description="Refund only: the dealer it is paid through.")
    remark: _Remark = Field(description="Why this remedy.")


class WithdrawIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    remark: _Remark


class TypeRef(BaseModel):
    id: str
    code: str
    name: str


class Ref(BaseModel):
    id: str
    name: str


class ProductRef(BaseModel):
    id: str
    description: str | None


class Line(BaseModel):
    id: str
    product: ProductRef
    uom: str | None
    supplied_qty: str
    defective_qty: str
    failure_frequency: str | None
    remark: str | None


class Attachment(BaseModel):
    id: str
    kind: Kind
    filename: str
    content_type: str
    size_bytes: int
    preview: bool = Field(description="False for HEIC: show a file icon, not a thumbnail.")
    uploaded_by: UserRef | None
    uploaded_at: str


class AttachmentLink(BaseModel):
    url: str = Field(description="Valid ten minutes. Use it as an image source or a download; "
                                 "never fetch it with the bearer token.")
    expires_at: str


class Check(BaseModel):
    decision: Literal["approve", "return"]
    remark: str
    by: UserRef | None = Field(description="Null for a dealer.")
    at: str
    internal_note: str | None = Field(default=None, description="Staff only; absent for a dealer.")


class Quality(BaseModel):
    verdict: Literal["approved", "rejected"]
    remark: str
    sample_received_on: str | None
    tested_on: str | None
    field_visit_on: str | None
    by: UserRef | None = Field(description="Null for a dealer.")
    at: str
    internal_note: str | None = Field(default=None, description="Staff only; absent for a dealer.")


class Cancellation(BaseModel):
    reason: str
    by: UserRef | None
    at: str


class Sla(BaseModel):
    policy: Literal["set", "none"] = Field(description="`none`: no target applied; show "
                                                       "\"no target\", never red.")
    response_due_at: str | None
    responded_at: str | None
    response_breached: bool
    resolution_due_at: str | None
    resolved_at: str | None
    resolution_breached: bool


class Can(BaseModel):
    edit: bool
    submit: bool
    check: bool
    qc: bool
    cancel: bool
    delete: bool
    upload: bool
    remedy: bool = Field(description="Choose a remedy (FS-015b).")
    withdraw: bool = Field(description="Withdraw the pending remedy.")
    reopen: bool = Field(
        default=False, description="Reopen a closed or rejected complaint (FS-036).")


class RemedyOrder(BaseModel):
    id: str
    order_no: str | None
    status: str


class Refund(BaseModel):
    amount: str
    payee_name: str | None = Field(description="Null for a dealer.")
    paid_through: Ref | None = Field(description="Null for a dealer.")
    approval: Approval | None = Field(description="This refund's own request. Null for a dealer.")
    payment_reference: str | None = Field(description="The Account Manager's remark once "
                                          "paid. Null for a dealer.")


class Replacement(BaseModel):
    order: RemedyOrder | None


class Remedy(BaseModel):
    id: str
    kind: Literal["refund", "replacement", "none"]
    status: Literal["pending", "completed", "rejected", "withdrawn", "cancelled"]
    remark: str | None = Field(description="Null for a dealer.")
    refund: Refund | None
    replacement: Replacement | None
    chosen_by: UserRef | None = Field(description="Null for a dealer.")
    chosen_at: str
    completed_at: str | None


class Complaint(BaseModel):
    doc_type: Literal["complaint"] = Field(
        default="complaint", description="Tells a decided refund apart in `DecisionResult`.")
    id: str
    complaint_no: str | None = Field(description="Null until the first submit.")
    status: Status
    complaint_type: TypeRef
    severity: Severity
    description: str
    contact_name: str
    contact_mobile: str
    territory: Ref
    partner: PartnerLink | None
    lead: LeadLink | None
    sales_order: OrderLink | None
    dc_no: str | None
    supply_date: str | None
    reg_no: str | None
    pims_no: str | None
    sample_courier_date: str | None
    sample_courier_detail: str | None
    lines: list[Line]
    attachments: list[Attachment]
    check: Check | None = Field(description="The manager's decision since the latest submit.")
    quality: Quality | None
    cancellation: Cancellation | None = Field(
        default=None, description="Why and by whom, once cancelled.")
    sla: Sla | None = Field(description="Null before the first submit.")
    submit_count: int
    owner: UserRef | None
    owner_org_unit: Ref
    raised_by: UserRef | None
    remedy: Remedy | None = Field(default=None, description="The live or the last remedy.")
    closed_at: str | None = None
    reopen_count: int = Field(default=0, description="Times reopened (FS-036).")
    reopened_at: str | None = None
    reopen_reason: str | None = Field(
        default=None, description="Why it was last reopened. Staff only.")
    can: Can
    created_at: str
    updated_at: str
    submitted_at: str | None


class ComplaintSummary(BaseModel):
    """A list row."""
    id: str
    complaint_no: str | None
    status: Status
    complaint_type: TypeRef
    severity: Severity
    contact_name: str
    partner: PartnerLink | None
    owner: UserRef | None
    first_submitted_at: str | None
    breached: bool = Field(description="Either target missed.")
    created_at: str


class ComplaintPage(BaseModel):
    data: list[ComplaintSummary]
    meta: PageMeta


class Stats(BaseModel):
    by_status: dict[str, int]
    breached: int
    no_target: int
    storage_available: bool = Field(description="False: hide the upload button.")


class SlaPolicy(BaseModel):
    id: str
    severity: Severity
    complaint_type_id: str | None
    response_hours: int
    resolution_hours: int
    business_hours_only: bool
    effective_from: str
    effective_to: str | None


class SlaPolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    complaint_type_id: _Id | None = None
    response_hours: Annotated[int, Field(ge=1, le=8760)]
    resolution_hours: Annotated[int, Field(ge=1, le=8760)]
    business_hours_only: bool = True
    effective_from: dt.date


class Assignee(BaseModel):
    id: str
    full_name: str
    org_unit_id: str | None
