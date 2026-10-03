# ruff: noqa: E501  (field declarations)

"""Marketing material (FS-034): request and response shapes. Money is a decimal string."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.leads import UUID_RE, PageMeta


class MaterialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[A-Za-z0-9_-]{2,40}$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    unit: str = Field(default="Nos", min_length=1, max_length=20)
    price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    company_share_pct: Decimal = Field(default=Decimal("50"), ge=0, le=100, max_digits=6, decimal_places=3)


class MaterialPatch(BaseModel):
    """`price` or `company_share_pct` starts a new price from today; the old one ends
    yesterday. The rest edits the item."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    company_share_pct: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=3)
    is_active: bool | None = None


class Material(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    unit: str
    price: str | None = Field(description="Today's price. Null if none is in force.")
    company_share_pct: str | None
    image_url: str | None = Field(default=None, description="Not built yet (GAP-329).")
    is_active: bool
    is_provisional: bool = Field(description="A stand-in price: show it as indicative.")


class LineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str = Field(pattern=UUID_RE)
    qty: int = Field(ge=1, le=100000)


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partner_id: str | None = Field(default=None, pattern=UUID_RE,
                                   description="Staff: the dealer it is for, or null for an "
                                               "office's own use. Ignored for a partner user.")
    lines: list[LineIn] = Field(min_length=1, max_length=50)
    remark: str | None = Field(default=None, max_length=1000)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remark: str | None = Field(default=None, max_length=1000)


class DispatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dispatched_on: dt.date = Field(description="Not in the future.")
    reference: str = Field(min_length=1, max_length=200)


class Ref(BaseModel):
    id: str
    name: str | None


class MaterialRef(BaseModel):
    id: str
    code: str
    name: str


class Line(BaseModel):
    id: str
    material: MaterialRef
    unit: str
    qty: int
    price: str
    value: str
    company_share_pct: str
    company_share: str
    dealer_share: str


class Totals(BaseModel):
    value: str
    company_share: str
    dealer_share: str


class DecisionOut(BaseModel):
    status: Literal["approved", "rejected"]
    by: Ref | None = Field(description="Null for a partner user (question 15.14).")
    at: str
    remark: str | None


class DispatchOut(BaseModel):
    dispatched_on: str
    reference: str
    by: Ref | None


class Can(BaseModel):
    approve: bool
    reject: bool
    cancel: bool
    dispatch: bool


class MarketingOrder(BaseModel):
    id: str
    order_no: str
    status: Literal["submitted", "approved", "rejected", "cancelled", "dispatched"]
    partner: Ref | None
    requested_by: Ref
    office: Ref
    lines: list[Line]
    totals: Totals
    remark: str | None
    is_provisional: bool
    decision: DecisionOut | None
    dispatch: DispatchOut | None
    cancel_remark: str | None
    can: Can = Field(description="Which buttons this caller may use now.")
    created_at: str


class MarketingOrderSummary(BaseModel):
    id: str
    order_no: str
    status: Literal["submitted", "approved", "rejected", "cancelled", "dispatched"]
    partner: Ref | None
    requested_by: Ref
    office: Ref
    totals: Totals
    is_provisional: bool
    created_at: str


class MarketingOrderPage(BaseModel):
    data: list[MarketingOrderSummary]
    meta: PageMeta
