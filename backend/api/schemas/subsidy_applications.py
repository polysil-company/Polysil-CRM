"""Shapes for /subsidy-applications, /subsidy-stages and /subsidy-document-types
(FS-009). Money and areas are decimal strings (rule 4)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints

from api.schemas.complaints import Ref as Ref
from api.schemas.leads import UUID_RE, UserRef
from api.schemas.leads import TerritoryRef as TerritoryRef
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


class ApplicationLeadRef(BaseModel):
    id: str
    inquiry_no: str


class DocumentCount(BaseModel):
    uploaded: int = Field(description="Checklist items with at least one file.")
    listed: int = Field(description="Active checklist items.")


class Ageing(BaseModel):
    days_in_stage: int = Field(description="Today (IST) less the current stage's business date.")
    days_since_inward: int | None = Field(description="Today less the App. Inward Date, or "
                                          "the first stage-4 entry's date without it.")


class ApplicationCancellation(BaseModel):
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
    lead: ApplicationLeadRef
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
    cancellation: ApplicationCancellation | None


class ApplicationPageMeta(BaseModel):
    next_cursor: str | None


class ApplicationPage(BaseModel):
    data: list[Application]
    meta: ApplicationPageMeta


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


# strings only: a JSON number would be a float on the way in, and lax mode reads
# `true` as 1 (PR 33 review)
Value = StrictStr | None


class StageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_code: Annotated[str, Field(min_length=1, max_length=60)]
    occurred_on: dt.date = Field(description="The business date, not after today in India.")
    values: dict[str, Value] = Field(default_factory=dict, description=(
        "Field key to value, every one a string: dates as ISO dates, amounts as decimal "
        "strings such as \"1250.50\", text. Null or blank clears the field."))
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
