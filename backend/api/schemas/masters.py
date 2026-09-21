"""Request and response shapes for /org-units, /territories and /partners (FS-006 4).

The frontend builds against these. Field descriptions become the field notes in the
generated API doc (CLAUDE.md 2.3). Money is a decimal string, never a float (rule 4).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.leads import UUID_RE, PageMeta, TerritoryRef

TerritoryLevel = Literal["state", "district", "taluka", "village"]
PartnerType = Literal["distributor", "dealer", "sub_dealer"]


# ── offices ──────────────────────────────────────────────────────────────────

class OrgUnitParent(BaseModel):
    id: str
    name: str


class OrgUnit(BaseModel):
    """An office, in lists and on its own. `is_open` is `deleted_at IS NULL` and
    `closed_at` is that timestamp: there is no separate column."""

    id: str
    name: str
    role_level: int = Field(description="1 field up to 5 head office; the level of the "
                                        "role that runs it.")
    parent: OrgUnitParent | None = Field(description="Null at a root.")
    territory: TerritoryRef | None = Field(
        description="The territory a sales-line office covers; null for an HQ unit.")
    is_open: bool
    closed_at: str | None
    active_users: int = Field(description="Active, non-deleted people anchored here. "
                                          "An office with any cannot be closed.")
    created_at: str


class OrgUnitPage(BaseModel):
    data: list[OrgUnit]
    meta: PageMeta


class OrgUnitCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=200,
                               description="Unique among its siblings, case-insensitively.")]
    role_level: Annotated[int, Field(ge=1, le=5)]
    parent_id: Annotated[str | None, Field(default=None, pattern=UUID_RE,
                                           description="An open office, or null for a root.")]
    territory_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="The territory this office covers; leave null for an HQ unit.")]


class OrgUnitPatch(BaseModel):
    """Send only what changes. `parent_id: null` makes the office a root."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=200)]
    parent_id: Annotated[str | None, Field(default=None, pattern=UUID_RE)]
    territory_id: Annotated[str | None, Field(default=None, pattern=UUID_RE)]


# ── territories ──────────────────────────────────────────────────────────────

class Territory(BaseModel):
    id: str
    name: str
    level: TerritoryLevel
    code: str | None = Field(description="A state's code numbers its leads "
                                         "(POL/<code>/<FY>/<n>); optional elsewhere.")
    parent: TerritoryRef | None = Field(description="Null for a state.")
    code_locked: bool = Field(description="True once a lead has been numbered under this "
                                          "state: the code can no longer change.")
    created_at: str


class TerritoryPage(BaseModel):
    data: list[Territory]
    meta: PageMeta


class TerritoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=200,
                               description="Unique among its siblings, case-insensitively.")]
    level: TerritoryLevel
    parent_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="The territory one level up: a district under a state, a taluka "
        "under a district, a village under a taluka. Null for a state.")]
    code: Annotated[str | None, Field(
        default=None, min_length=1, max_length=12,
        description="Unique per level. Stored upper-case. A state needs one before leads "
        "can be numbered under it.")]


class TerritoryPatch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=200)]
    code: Annotated[str | None, Field(
        default=None, min_length=1, max_length=12,
        description="Refused on a state once a lead has been numbered under it.")]


# ── partners ─────────────────────────────────────────────────────────────────

class PartnerParent(BaseModel):
    id: str
    name: str
    partner_type: str


class Partner(BaseModel):
    """A channel partner. `credit_limit` and `payment_terms_days` are null for a
    partner caller reading its own subtree; staff see them."""

    id: str
    code: str
    name: str
    partner_type: PartnerType
    price_tier: str = Field(description="Always the partner type (ADR-030).")
    parent: PartnerParent | None
    territory: TerritoryRef | None
    contact_name: str | None
    mobile: str | None = Field(description="91XXXXXXXXXX, no plus.")
    email: str | None
    address: str | None
    gstin: str | None
    pan: str | None
    is_gst_registered: bool
    credit_limit: str | None = Field(description="Rupees, a decimal string. Stored, not "
                                                 "enforced (H12). Staff readers only.")
    payment_terms_days: int | None = Field(description="Staff readers only.")
    is_active: bool
    users: int = Field(description="Active partner users anchored here.")
    created_at: str


class PartnerPage(BaseModel):
    data: list[Partner]
    meta: PageMeta


class PartnerStateChange(Partner):
    """The shape close and reopen answer with."""

    users_inactive: int = Field(description="Partner users anchored here who are inactive. "
                                            "Reopening restores none of them.")


class PartnerCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    parent_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="The partner one type up (a dealer under a distributor). Null for a "
        "distributor. A dealer or distributor creating from the portal must name itself.")]
    partner_type: PartnerType
    code: Annotated[str, Field(min_length=1, max_length=32, description="Unique.")]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    territory_id: Annotated[str, Field(pattern=UUID_RE)]
    contact_name: Annotated[str | None, Field(default=None, max_length=200)]
    mobile: Annotated[str | None, Field(default=None, max_length=32,
                                        description="Any Indian form.")]
    email: Annotated[str | None, Field(default=None, max_length=254)]
    address: Annotated[str | None, Field(default=None, max_length=1000)]
    gstin: Annotated[str | None, Field(default=None, max_length=15,
                                       description="15 characters; checked for shape.")]
    pan: Annotated[str | None, Field(default=None, max_length=10)]
    is_gst_registered: bool = False
    credit_limit: Annotated[Decimal | None, Field(default=None, ge=0,
                                                  description="Staff only. Rupees.")]
    payment_terms_days: Annotated[int | None, Field(default=None, ge=0, le=365,
                                                    description="Staff only.")]


class PartnerPatch(BaseModel):
    """Send only what changes. A partner editing itself may send name, contact_name,
    mobile, email, address, gstin and pan; the rest is refused by field name.
    `partner_type` and `parent_id` never change (rules 21 and GAP-038)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=200)]
    contact_name: Annotated[str | None, Field(default=None, max_length=200)]
    mobile: Annotated[str | None, Field(default=None, max_length=32)]
    email: Annotated[str | None, Field(default=None, max_length=254)]
    address: Annotated[str | None, Field(default=None, max_length=1000)]
    gstin: Annotated[str | None, Field(default=None, max_length=15)]
    pan: Annotated[str | None, Field(default=None, max_length=10)]
    is_gst_registered: bool | None = None
    territory_id: Annotated[str | None, Field(default=None, pattern=UUID_RE,
                                              description="Staff only.")]
    credit_limit: Annotated[Decimal | None, Field(default=None, ge=0,
                                                  description="Staff only.")]
    payment_terms_days: Annotated[int | None, Field(default=None, ge=0, le=365,
                                                    description="Staff only.")]
