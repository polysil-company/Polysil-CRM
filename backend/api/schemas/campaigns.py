# ruff: noqa: E501  (field declarations)

"""Campaigns (FS-040): request and response shapes. Money is a decimal string."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.leads import UUID_RE, TerritoryRef

CampaignType = Literal["exhibition", "agri_fair", "farmer_meeting", "dealer_meet", "promo_drive",
                       "digital", "print", "other"]
Money = Decimal


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200, description="Unique, case ignored.")
    type: CampaignType = Field(description="exhibition, agri_fair, farmer_meeting, dealer_meet, promo_drive, digital, print or other.")
    territory_id: str | None = Field(default=None, pattern=UUID_RE, description="Where it is held. Any level. Optional.")
    start_date: dt.date = Field(description="IST date.")
    end_date: dt.date | None = Field(default=None, description="Not before start_date. Optional.")
    cost_planned: Money = Field(default=Decimal("0.00"), ge=0, max_digits=14, decimal_places=2, description="Rupees, a decimal string.")
    cost_actual: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2, description="Rupees, once known.")
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _one_space(cls, v: str) -> str:
        return " ".join(v.split())


class CampaignPatch(BaseModel):
    """Send only what changes. end_date, territory_id, cost_actual and description
    may be sent null to clear them."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: CampaignType | None = None
    territory_id: str | None = Field(default=None, pattern=UUID_RE)
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    cost_planned: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    cost_actual: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = Field(default=None, description="false switches it off: staff can no longer put it on a lead or a QR code. A QR code already linked keeps bringing leads under it.")

    @field_validator("name")
    @classmethod
    def _one_space(cls, v: str | None) -> str | None:
        return " ".join(v.split()) if v is not None else v


class CampaignSummary(BaseModel):
    leads: int = Field(description="Leads you can see that name this campaign.")
    won: int
    lost: int
    open: int
    sales_value: str | None = Field(description="Orders on those leads that count as sales, under the company's sale setting. Null without sales_orders.")
    cost_per_lead: str | None = Field(description="Cost (actual, else planned) over leads. Null without campaigns.view, or with no leads.")
    cost_per_won: str | None = Field(description="Cost over won leads. Null without campaigns.view, or with no wins.")


class Campaign(BaseModel):
    id: str
    name: str
    type: str
    territory: TerritoryRef | None
    start_date: str
    end_date: str | None
    cost_planned: str | None = Field(description="Null unless you have campaigns.view.")
    cost_actual: str | None = Field(description="Null until entered, or without campaigns.view.")
    description: str | None
    is_active: bool
    lead_count: int = Field(description="Leads you can see that name it.")
    created_at: str
    updated_at: str
    summary: CampaignSummary | None = Field(default=None, description="Only on GET /campaigns/{id}.")
