"""Shapes for /subsidy-applications, /subsidy-stages and /subsidy-document-types
(FS-009). Money and areas are decimal strings (rule 4)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from api.schemas.leads import UUID_RE, UserRef
from api.schemas.subsidy import CalculateRequest

Status = Literal["open", "full_fp_received", "cancelled"]


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: Annotated[str, Field(pattern=UUID_RE, description="A subsidised lead that is "
                                  "qualified, quoted, in negotiation or won.")]
    category_code: Annotated[str, Field(min_length=1, max_length=60, description=(
        "The farmer's category, from the calculation's `categories[].code`, for example "
        "`small_farmer`. It must apply on every crop."))]
    calculation: CalculateRequest = Field(description="The FS-008 request, as for "
                                          "POST /subsidy/calculate. Run again here and stored.")
    survey_no: Annotated[str | None, Field(default=None, max_length=100)]


class StageRef(BaseModel):
    seq: int
    code: str
    name: str
    since: str = Field(description="The business date of the latest entry.")


class Category(BaseModel):
    code: str
    name: str
    pct: str


class Figures(BaseModel):
    total_cost: str = Field(description="The calculation's total including GST.")
    subsidy: str = Field(description="The chosen category's subsidy, summed over the crops.")
    farmer_share: str = Field(description="The chosen category's farmer share, summed over "
                              "the crops.")


class Ref(BaseModel):
    id: str
    name: str


class LeadRef(BaseModel):
    id: str
    inquiry_no: str


class TerritoryRef(BaseModel):
    id: str
    name: str
    level: str


class DocumentCount(BaseModel):
    uploaded: int = Field(description="Checklist items with at least one file.")
    listed: int = Field(description="Active checklist items.")


class Ageing(BaseModel):
    days_in_stage: int = Field(description="Today (IST) less the current stage's business date.")
    days_since_inward: int | None = Field(description="Today less the App. Inward Date, or "
                                          "the first stage-4 entry's date without it.")


class Cancellation(BaseModel):
    reason: str


class Application(BaseModel):
    id: str
    application_no: str
    reg_no: str | None = Field(description="The department's registration number: the "
                               "latest Reg. No. entered at stage 4.")
    status: Status
    current_stage: StageRef
    scheme: str
    system_type: str
    category: Category
    lead: LeadRef
    farmer_name: str
    mobile: str
    village: str | None
    survey_no: str | None
    territory: TerritoryRef
    partner: Ref | None
    total_area: str
    group_total_area: str | None
    figures: Figures
    owner: UserRef | None
    owner_org_unit: Ref
    documents: DocumentCount
    ageing: Ageing
    full_fp_received_on: str | None
    created_at: str
    cancellation: Cancellation | None


class PageMeta(BaseModel):
    next_cursor: str | None


class ApplicationPage(BaseModel):
    data: list[Application]
    meta: PageMeta


class FieldDef(BaseModel):
    key: str
    label: str
    type: Literal["date", "text", "amount"]
    required: bool


class StageDef(BaseModel):
    seq: int
    code: str
    name: str
    fields: list[FieldDef]


class Entry(BaseModel):
    id: str
    stage: StageRef
    occurred_on: str
    values: dict[str, str | None] = Field(description="Dates as ISO dates, amounts as decimal "
                                          "strings, text as given; null when cleared.")
    remark: str | None
    entered_by: UserRef | None
    entered_at: str


Value = str | int | float | None


class StageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_code: Annotated[str, Field(min_length=1, max_length=60)]
    occurred_on: dt.date = Field(description="The business date, not after today in India.")
    values: dict[str, Value] = Field(default_factory=dict, description=(
        "Field key to value: dates as ISO dates, amounts as decimal strings, text. Null "
        "clears the field."))
    remark: Annotated[str | None,
                      StringConstraints(strip_whitespace=True, max_length=1000)] = Field(
        default=None, description="Required for a backward or same-stage entry.")


class Cancel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class DocumentType(BaseModel):
    id: str
    code: str
    name: str
    is_active: bool


class Document(BaseModel):
    id: str
    content_type: str
    size_bytes: int
    filename: str | None
    uploaded_by: UserRef | None
    created_at: str


class ChecklistItem(BaseModel):
    type: DocumentType
    files: list[Document]


class DocumentLink(BaseModel):
    url: str
    expires_at: str
