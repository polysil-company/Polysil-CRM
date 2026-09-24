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

# Every id the client sends is validated to this shape, so a malformed id is a
# 422 with the envelope rather than a driver error and a 500 (cross-vendor P2).
UUID_RE = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


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
    territory_id: Annotated[str, Field(pattern=UUID_RE,
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
    total: int | None = Field(
        default=None,
        description="How many rows match, across all pages. **Only present when you ask for "
                    "it with `?include_total=true`**, because counting a scoped table costs a "
                    "scan and most screens do not need it. Null otherwise.")
    total_capped: bool = Field(
        default=False,
        description="True when there are more rows than `total` says. The count stops at a "
                    "ceiling so one query can never run away on a large account, so render "
                    "`total` as \"1000+\" rather than an exact figure when this is set.")


class LeadStats(BaseModel):
    """Counts over the same scope and filters as the list, for the pipeline board
    and the dashboard tiles. Every stage and priority is present, 0 when empty."""

    total: int = Field(description="Leads matching the filters.")
    by_stage: dict[str, int] = Field(
        description="Every stage. merged is 0 unless the stage filter asks for it, "
                    "as on the list.")
    by_priority: dict[str, int] = Field(description="hot, warm and cold.")
    unassigned: int = Field(description="Leads with no owner: the assignment queue.")


class LeadPage(BaseModel):
    """The lead list. Keyset paging by (created_at desc, id); there is no total,
    because counting a scoped table on every page is the cost this avoids."""

    data: list[Lead]
    meta: PageMeta


class TerritoryParent(BaseModel):
    id: str
    name: str
    level: str


class PartnerPick(BaseModel):
    """A row of GET /lookups/partners, for the partner picker on assign. Only the
    partners you can see: a dealer its own subtree, a district manager the
    partners in its territories, an admin all of them."""

    id: str
    code: str
    name: str
    partner_type: str = Field(description="distributor, dealer or sub_dealer.")
    territory: TerritoryParent | None = None


class TerritoryPick(BaseModel):
    """A row of GET /lookups/territories, for the territory picker on the new-lead form."""

    id: str
    name: str
    level: str = Field(description="state, district, taluka or village.")
    code: str | None = None
    parent: TerritoryParent | None = None


# ── lifecycle ────────────────────────────────────────────────────────────────

TransitionTarget = Literal["contacted", "qualified", "quoted", "negotiation", "won", "lost"]


class LeadTransition(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    to_stage: Annotated[TransitionTarget, Field(
        description="The stage to move to. Only the moves the lifecycle allows are "
        "accepted; anything else is 422 invalid_transition.")]
    lost_reason_id: Annotated[str | None, Field(default=None, pattern=UUID_RE,
        description="Required when to_stage is lost: an active reason from "
        "GET /lookups/lost-reasons.")]
    lost_note: Annotated[str | None, Field(default=None, max_length=2000,
        description="Optional free text kept with a lost lead and on its timeline.")]
    expected_stage: Annotated[str | None, Field(default=None,
        description="Optional. If given and the lead has already moved past it, the "
        "call is refused with 409 stage_changed rather than acting on a stale view.")]


class LeadReopen(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    note: Annotated[str | None, Field(default=None, max_length=2000,
        description="Optional. Why the lead is being reopened; kept on the timeline.")]


class LeadNote(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    note: Annotated[str, Field(min_length=1, max_length=2000,
        description="The note text. Becomes a timeline entry and bumps the lead's "
        "last-activity time.")]


class TimelineEvent(BaseModel):
    """One entry on a lead's timeline. `actor` is who did it; `payload` carries the
    event's own detail (the stage change, the note text, and so on)."""

    id: str
    kind: str = Field(description="e.g. lead.created, lead.stage_changed, lead.note_added.")
    occurred_at: str
    actor: UserRef | None = Field(default=None, description="Who caused the event, if known.")
    payload: dict[str, object] = Field(default_factory=dict)


class TimelinePage(BaseModel):
    data: list[TimelineEvent]
    meta: PageMeta


# ── assignment ───────────────────────────────────────────────────────────────

class LeadAssign(BaseModel):
    """Give the lead an owner, a partner, or both. A field sent as null clears it;
    a field left out is unchanged. At least one must be sent."""

    owner_user_id: Annotated[str | None, Field(default=None, pattern=UUID_RE,
        description="A staff user from GET /leads/assignees, or null to unassign.")]
    assigned_partner_id: Annotated[str | None, Field(default=None, pattern=UUID_RE,
        description="A channel partner from GET /lookups/partners, or null to clear.")]


class Assignee(BaseModel):
    id: str
    full_name: str
    org_unit: OrgUnitRef | None = None


# ── edit ─────────────────────────────────────────────────────────────────────

class LeadPatch(BaseModel):
    """Correct the lead's own fields. Send only what changes: a field left out is
    unchanged. email, village and estimated_value may be sent null to clear them;
    the others are required on a lead and cannot be cleared. The stage, owner and
    partner have their own endpoints."""

    model_config = ConfigDict(str_strip_whitespace=True)

    farmer_name: Annotated[str | None, Field(default=None, min_length=1, max_length=200)]
    mobile: Annotated[str | None, Field(default=None,
        description="Any Indian form; stored as +91XXXXXXXXXX.")]
    email: Annotated[str | None, Field(default=None, max_length=254)]
    territory_id: Annotated[str | None, Field(default=None, pattern=UUID_RE,
        description="Moving the lead re-routes its owning org unit; it must stay in your scope.")]
    village: Annotated[str | None, Field(default=None, max_length=200)]
    inquiry_type: InquiryType | None = None
    mis_system: Annotated[str | None, Field(default=None, description="A code from the lookup.")]
    source: Annotated[str | None, Field(default=None, description="A code from the lookup.")]
    estimated_value: Annotated[Decimal | None, Field(default=None, ge=0,
        description="Decimal string. Feeds the priority score.")]


# ── duplicates ───────────────────────────────────────────────────────────────

class DuplicatePair(BaseModel):
    """A pending pair in the review queue. Both leads are in your scope; that is
    the link table's own rule, so a pair never names a lead you could not open."""

    link_id: str
    signal: Literal["mobile", "email", "name_geo"] = Field(
        description="What matched: the mobile, the email, or name plus village nearby.")
    score: str | None = Field(default=None, description="Match strength, a decimal string.")
    state: Literal["pending", "merged", "dismissed"]
    created_at: str
    lead_a: Lead
    lead_b: Lead


class DuplicatePage(BaseModel):
    data: list[DuplicatePair]
    meta: PageMeta


class DismissResult(BaseModel):
    link_id: str
    state: Literal["dismissed"] = "dismissed"


class LeadMerge(BaseModel):
    into_lead_id: Annotated[str, Field(pattern=UUID_RE,
        description="The survivor. This lead becomes its merged loser and keeps pointing at it.")]


# ── lookup admin (masters.edit) ──────────────────────────────────────────────

class LookupCreate(BaseModel):
    """Add a row to a lookup list. Rows are added and switched off, never renamed
    or deleted: a lead keeps the reason it was lost with (ADR-033)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    code: Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$",
        description="Stable machine code, lowercase with underscores. Cannot change later.")]
    name: Annotated[str, Field(min_length=1, max_length=100, description="Display name.")]
    sort_order: Annotated[int | None, Field(default=None,
        description="Sources and reasons only. Lower sorts first.")]
    quality: Annotated[Decimal | None, Field(default=None, ge=0, le=1,
        description="Sources only. The source-quality factor in the score, 0 to 1.")]
    kind: Annotated[Literal["won", "lost"] | None, Field(default=None,
        description="Reasons only. Defaults to lost.")]


class LookupUpdate(BaseModel):
    """Switch a row on or off, or reorder it. Names are never edited in place."""

    is_active: bool | None = None
    sort_order: int | None = None
    quality: Annotated[Decimal | None, Field(default=None, ge=0, le=1,
        description="Sources only.")]


class ScoringItem(BaseModel):
    key: str = Field(description="w_source, w_value, w_speed, w_engagement, value_cap, "
                     "speed_fast_hours, speed_slow_hours, engagement_cap, threshold_hot, "
                     "threshold_warm.")
    value: str = Field(description="Decimal string.")


class ScoringPatch(BaseModel):
    values: dict[str, Decimal] = Field(
        description="Keys to change, each with its new value. Unknown keys are refused.")
