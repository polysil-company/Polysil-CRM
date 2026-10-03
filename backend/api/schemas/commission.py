"""Dealer commission and TOD (FS-033): request and response shapes. Money is a decimal string."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.leads import UUID_RE, PageMeta


class CommissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gi_fitting: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    pvc_hdpe_fitting: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    installation: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2,
        description="Null takes the installation from the stored calculation.")
    tod_base: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2,
                                     description="Null: the same as the commission base.")
    remark: str | None = Field(default=None, max_length=1000)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remark: str | None = Field(default=None, max_length=1000)


class Payment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paid_on: dt.date = Field(description="Not in the future.")
    payment_reference: str = Field(min_length=1, max_length=200)


class Ref(BaseModel):
    id: str
    name: str | None


class AppRef(BaseModel):
    id: str
    application_no: str
    reg_no: str | None


class Preview(BaseModel):
    partner: Ref
    cost_excl_gst: str = Field(description="calculation.total.blocks.cost_excl_gst: includes "
                                           "installation, insurance, inspection, education, sump.")
    a_plus_b: str | None = Field(description="Material only (head and field units).")
    installation: str
    commission_pct: str | None = Field(description="Null when no rate is in force: add one.")
    tod_pct: str | None
    rate_id: str | None


class Commission(BaseModel):
    id: str
    application: AppRef
    partner: Ref
    status: Literal["calculated", "approved", "returned", "paid", "cancelled"]
    cost_excl_gst: str
    a_plus_b: str | None
    gi_fitting: str
    pvc_hdpe_fitting: str
    installation: str
    commission_base: str
    commission_pct: str
    commission_amount: str
    tod_base: str
    tod_pct: str
    tod_amount: str
    total: str
    remark: str | None
    recorded_by: Ref
    recorded_at: str
    decided_by: Ref | None
    decided_at: str | None
    decision_remark: str | None
    paid_on: str | None
    payment_reference: str | None


class CommissionPage(BaseModel):
    data: list[Commission]
    meta: PageMeta


class RateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme: str = Field(default="GGRC", description="The subsidy scheme's code.")
    system_type: Literal["drip", "mini_sprinkler", "sprinkler"] | None = None
    partner_type: Literal["distributor", "dealer", "sub_dealer"] | None = None
    partner_id: str | None = Field(default=None, pattern=UUID_RE)
    commission_pct: Decimal = Field(ge=0, le=100, max_digits=6, decimal_places=3)
    tod_pct: Decimal = Field(ge=0, le=100, max_digits=6, decimal_places=3)
    effective_from: dt.date


class Rate(BaseModel):
    id: str
    scheme: str
    system_type: str | None
    partner_type: str | None
    partner: Ref | None
    commission_pct: str
    tod_pct: str
    effective_from: str
