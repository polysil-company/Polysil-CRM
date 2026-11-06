"""Request and response shapes for /users, /auth/password and /lookups/roles (FS-006 4).

The frontend builds against these. Field descriptions become the field notes in the
generated API doc (CLAUDE.md 2.3), so they say what a field is for.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.leads import UUID_RE, OrgUnitRef, PageMeta, TerritoryRef, UserRef

UserType = Literal["staff", "partner_user"]


class RoleRef(BaseModel):
    code: str = Field(description="Stable identifier, e.g. district_manager.")
    name: str = Field(description="Display name.")


class PartnerRef(BaseModel):
    id: str
    name: str | None = Field(
        default=None,
        description="Null when the partner row is outside your partners scope.")


class UserRow(BaseModel):
    """A person in the list. Every key is always present; null means 'not set',
    never 'hidden'."""

    id: str
    user_type: UserType
    full_name: str
    email: str | None = Field(description="Staff sign in with it. Stored lower-case.")
    mobile: str | None = Field(
        description="Partner users sign in with it by OTP. 91XXXXXXXXXX, no plus.")
    role: RoleRef | None
    org_unit: OrgUnitRef | None = Field(
        description="The office a staff member is anchored on; null for a partner user.")
    partner: PartnerRef | None = Field(
        description="The partner a partner user is anchored on; null for staff.")
    is_active: bool
    must_change_password: bool = Field(
        description="A temporary password set by an administrator is still in force.")
    last_login_at: str | None
    open_leads: int | None = Field(
        description="Leads this staff member owns that are not won, lost or merged. "
        "Null for a partner user, who owns no leads.")


class UserDetail(UserRow):
    """The list row plus the territories, the audit fields, and, for `users.edit`
    holders, the lockout state and the live session count."""

    territories: list[TerritoryRef] = Field(
        description="The territories a staff member reads at territory scope.")
    locked_until: str | None = Field(
        default=None,
        description="Staff only, and only when you hold users.edit: the end of a live "
        "sign-in lockout (five failed passwords in fifteen minutes), else null.")
    active_sessions: int | None = Field(
        default=None,
        description="Live sessions, when you hold users.edit; null otherwise.")
    password_changed_at: str | None
    created_at: str
    deleted_at: str | None = Field(
        description="Set once the person is soft-deleted. Deleted people are returned "
        "only to users.delete holders, and never in the list.")
    created_by: UserRef | None


class UserPage(BaseModel):
    """The people list. Keyset paging by (created_at desc, id); no total."""

    data: list[UserRow]
    meta: PageMeta


class UserCreate(BaseModel):
    """No model-wide whitespace stripping: it would trim the password before it is
    hashed while sign-in keeps the spaces (cross-vendor P2-5). The service trims
    the name and normalises the identifiers itself."""

    user_type: UserType = Field(
        description="staff or partner_user. Consumers are not created here.")
    full_name: Annotated[str, Field(min_length=1, max_length=200)]
    email: Annotated[str | None, Field(
        default=None, max_length=254,
        description="Staff only. Trimmed and lower-cased; unique among live people.")]
    mobile: Annotated[str | None, Field(
        default=None, max_length=32,
        description="Partner users only (optional on staff). Any Indian form: 10 digits, "
        "or with 0, 91 or +91. Stored as 91XXXXXXXXXX. Unique among live people.")]
    role: Annotated[str | None, Field(
        default=None, max_length=64,
        description="Staff only: a code from GET /lookups/roles that is not a portal "
        "role. A partner user's role is its partner's type and is never sent.")]
    org_unit_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE, description="Staff only: an open office.")]
    partner_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE, description="Partner users only: an active partner.")]
    territory_ids: Annotated[list[Annotated[str, Field(pattern=UUID_RE)]], Field(
        default_factory=list, max_length=200,
        description="Staff only. A role that reads any module at territory scope needs "
        "at least one, or the person sees nothing there.")]
    password: Annotated[str | None, Field(
        default=None, max_length=128,
        description="Staff only. A temporary password of at least 12 characters, told "
        "to the person out of band; they must change it at first sign-in.")]


class UserPatch(BaseModel):
    """Correct a person. Send only what changes; a field left out is unchanged."""

    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: Annotated[str | None, Field(default=None, min_length=1, max_length=200)]
    email: Annotated[str | None, Field(default=None, max_length=254,
                                       description="Staff only.")]
    mobile: Annotated[str | None, Field(default=None, max_length=32,
                                        description="Any Indian form.")]
    role: Annotated[str | None, Field(
        default=None, max_length=64,
        description="Staff only, and never your own. A partner user's role follows "
        "its partner.")]
    org_unit_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE, description="Staff only: an open office. Never your own.")]
    partner_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="Partner users only: an active partner. Never your own.")]
    territory_ids: Annotated[list[Annotated[str, Field(pattern=UUID_RE)]] | None, Field(
        default=None, max_length=200,
        description="Staff only. Replaces the whole set. Never your own.")]
    is_active: Annotated[bool | None, Field(
        default=None,
        description="false deactivates (every session is signed out first), true "
        "reactivates into an open office or active partner. Never your own.")]


class PasswordSet(BaseModel):
    password: Annotated[str, Field(
        max_length=128,
        description="A new temporary password, at least 12 characters. Every session "
        "of the person is signed out; they sign in with it and must change it.")]


class PasswordSetResult(BaseModel):
    id: str
    must_change_password: Literal[True] = True
    sessions_revoked: int


class RevokeResult(BaseModel):
    id: str
    sessions_revoked: int = Field(description="Sessions that were live and are now signed out.")


class UnlockResult(BaseModel):
    id: str
    was_locked: bool = Field(description="Whether a lockout was in force when you cleared it.")


class HandoverRequest(BaseModel):
    to_user_id: Annotated[str, Field(
        pattern=UUID_RE,
        description="An active staff member whose role can work leads, from "
        "GET /leads/assignees. Not the leaver.")]
    deactivate: bool = Field(
        default=False,
        description="Also deactivate the leaver once nothing remains. Refused while "
        "`remaining` is above zero, and never for your own row.")


class HandoverResult(BaseModel):
    leads_moved: int = Field(description="Open leads moved by this call, at most 500.")
    remaining: int = Field(
        description="Open leads the leaver still owns. Repeat the call with a new "
        "Idempotency-Key until it is 0.")
    tasks_moved: int = Field(default=0, description="Open tasks moved. All of them go on "
                             "every call.")
    deactivated: bool


class RoleItem(BaseModel):
    code: str = Field(description="Send this as `role` on POST /users.")
    name: str
    level: int = Field(description="1 field officer up to 5 head office.")
    is_functional: bool
    is_portal: bool = Field(
        description="A partner user's role. Filter these out of the staff form; the "
        "server refuses one on a staff member regardless.")


# ── FS-080: the org chart ────────────────────────────────────────────────────

class OrgChartPerson(BaseModel):
    """Someone on the chart. Name, role and office only: no contact details."""

    id: str
    full_name: str
    role: RoleRef
    level: int = Field(description="The role's level: 1 field officer up to 5 head office.")
    org_unit: OrgUnitRef = Field(description="The office they sit in. Never null for staff.")


class OrgChartNode(OrgChartPerson):
    manager_ids: list[str] = Field(
        description="Who this person reports to, sorted by name then id: the tree's edges. "
        "Draw the person under the first and show the rest as 'also reports to'. Every id "
        "is the subject, someone in `managers`, `people` or `co_managers`. Empty for a "
        "root of the company view.")
    direct_reports: int = Field(description="People whose `manager_ids` include this person.")
    team_size: int = Field(
        description="Everyone below this person at any depth, each counted once even when "
        "two managers share them.")


class RoleCount(BaseModel):
    role: RoleRef
    count: int


class OrgChartTotals(BaseModel):
    people: int = Field(description="The number of entries in `people`.")
    by_role: list[RoleCount] = Field(description="`people` counted by role, highest level first.")


class OrgChart(BaseModel):
    subject: OrgChartPerson | None = Field(
        description="Whose picture this is. Null in the company view.")
    managers: list[list[OrgChartPerson]] = Field(
        description="The chain above the subject, nearest first. A step holds more than "
        "one person when two people at the same level in one office both manage, sorted "
        "by name then id. Empty in the company view and for someone at the top.")
    people: list[OrgChartNode] = Field(
        description="Everyone below the subject at any depth, or the whole company. Sorted "
        "by level (highest first), then name, then id. Build the tree from `manager_ids`.")
    co_managers: list[OrgChartPerson] = Field(
        description="People named in some `manager_ids` who appear nowhere else: for "
        "example a second District Manager who shares one of your reports.")
    totals: OrgChartTotals
    unplaced: list[OrgChartPerson] = Field(
        description="Company view only: active staff on the System office, who cannot be "
        "placed. Not in `people` or `totals`. Give them a real office.")


class SetupItem(BaseModel):
    id: str = Field(description="The person's or partner's id, to link to their page.")
    name: str
    detail: str = Field(description="Role and office for a person, area or type for a partner.")


class SetupCheck(BaseModel):
    code: str = Field(description="staff_without_area, staff_without_territories, "
                      "staff_skipping_a_level, unplaced_staff or partners_without_area.")
    title: str = Field(description="One line for the card.")
    why: str = Field(description="What goes wrong while this stays unfixed, in plain words.")
    count: int
    items: list[SetupItem] = Field(description="The first 100, sorted by name.")


class SetupReport(BaseModel):
    ok: bool = Field(description="True when every check's count is 0.")
    checks: list[SetupCheck] = Field(
        description="Every check, always, in a fixed order. `partners_without_area` is left "
                    "out when you do not hold partners.view at global scope.")
