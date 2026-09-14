"""Request and response shapes for /leads (FS-003 4).

The frontend builds against these. Field descriptions become the field notes in the
generated API doc (CLAUDE.md 2.3), so they say what a field is for. Money and scores
are decimal strings, never floats (rule 4).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

InquiryType = Literal["commercial", "subsidised", "industrial"]
Stage = Literal["new", "contacted", "qualified", "quoted", "negotiation",
                "won", "lost", "merged", "dormant"]
Priority = Literal["hot", "warm", "cold"]


class LeadCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    farmer_name: Annotated[str, Field(min_length=1, max_length=200,
        description="The enquirer's name. Shown on the lead and on generated documents.")]
    mobile: Annotated[str, Field(
        description="Any Indian form: 10 digits, or with 0, 91 or +91. Spaces, "
        "dashes and brackets are fine. Stored as +91XXXXXXXXXX.",
        examples=["9876543210"])]
    email: Annotated[str | None, Field(default=None, max_length=254,
        description="Optional. Used for duplicate matching.")]
    territory_id: Annotated[str, Field(
        description="The taluka or district the farmer is in, from GET /lookups/territories.")]
    village: Annotated[str | None, Field(default=None, max_length=200,
        description="Optional. Used for duplicate matching.")]
    inquiry_type: Annotated[InquiryType, Field(
        description="commercial, subsidised or industrial.")]
    mis_system: Annotated[str, Field(
        description="The micro-irrigation system, a code from GET /lookups/mis-systems.",
        examples=["drip"])]
    source: Annotated[str | None, Field(default=None,
        description="A code from GET /lookups/lead-sources. Defaults by who you are: "
        "employee for staff, dealer for a partner user.")]
    estimated_value: Annotated[Decimal | None, Field(default=None, ge=0,
        description="Optional rupee value, a decimal string. Feeds the priority score.",
        examples=["125000.00"])]
    note: Annotated[str | None, Field(default=None, max_length=2000,
        description="Optional. Becomes the first entry on the lead's timeline.")]


class UserRef(BaseModel):
    id: str
    full_name: str


class TerritoryRef(BaseModel):
    id: str
    name: str
    level: str = Field(description="state, district or taluka.")


class OrgUnitRef(BaseModel):
    id: str
    name: str


class PartnerRef(BaseModel):
    id: str
    name: str
    partner_type: str = Field(description="distributor, dealer or sub_dealer.")


class ReasonRef(BaseModel):
    id: str
    code: str
    name: str


class MergedRef(BaseModel):
    id: str
    inquiry_no: str


class DuplicateRef(BaseModel):
    link_id: str
    lead_id: str
    inquiry_no: str
    signal: Literal["mobile", "email", "name_geo"]
    score: str | None = Field(default=None, description="Match strength, a decimal string.")
    state: Literal["pending", "merged", "dismissed"]


class Lead(BaseModel):
    """Every key is always present; null means 'not set', never 'hidden'."""

    id: str
    inquiry_no: str = Field(examples=["POL/GJ/2026-27/00123"])
    stage: Stage
    inquiry_type: InquiryType
    mis_system: str = Field(description="The code.")
    source: str = Field(description="The code.")
    farmer_name: str
    mobile: str = Field(description="E.164, e.g. +919876543210.")
    email: str | None
    territory: TerritoryRef
    village: str | None
    owner: UserRef | None = Field(description="The staff owner, or null if unassigned.")
    owner_org_unit: OrgUnitRef
    assigned_partner: PartnerRef | None
    score: str | None = Field(description="Decimal string, or null before scoring.")
    priority: Priority | None
    estimated_value: str | None
    lost_reason: ReasonRef | None
    lost_note: str | None
    reopen_count: int
    merged_into: MergedRef | None = Field(
        description="Set on a merged lead; links to the survivor.")
    first_contacted_at: str | None
    last_activity_at: str
    created_at: str
    created_by: UserRef | None
    duplicates: list[DuplicateRef] = Field(
        default_factory=list,
        description="Pending duplicate links whose other lead you can also see.")


class LookupItem(BaseModel):
    """A row of an editable list. Sources also carry a quality factor; reasons a kind."""

    id: str
    code: str
    name: str
    is_active: bool = True


class PageMeta(BaseModel):
    limit: int = Field(description="The page size that was applied.")
    next_cursor: str | None = Field(
        default=None,
        description="Pass this back as ?cursor= for the next page. Absent on the last page.")


class LeadPage(BaseModel):
    """The lead list. Keyset paging by (created_at desc, id); there is no total,
    because counting a scoped table on every page is the cost this avoids."""

    data: list[Lead]
    meta: PageMeta


class TerritoryParent(BaseModel):
    id: str
    name: str
    level: str


class TerritoryPick(BaseModel):
    """A row of GET /lookups/territories, for the territory picker on the new-lead form."""

    id: str
    name: str
    level: str = Field(description="state, district, taluka or village.")
    code: str | None = None
    parent: TerritoryParent | None = None
