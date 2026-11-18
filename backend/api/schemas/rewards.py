"""Reward points (FS-032): the request and response shapes.

**These descriptions become the field notes in `docs/api/rewards.md`.** Points are
integers; money is a decimal string.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.leads import UUID_RE, PageMeta

_CODE = r"^[A-Za-z0-9_-]{2,40}$"


class RuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=_CODE)
    name: str = Field(min_length=1, max_length=200)
    holder: Literal["partner", "staff"] = Field(description="Who earns: the order's partner, "
                                                "or the staff owner of the order or lead.")
    basis: Literal["order_value", "lead_won"] = Field(
        description="order_value: on a delivered order's value before GST. lead_won: a flat "
                    "number of points when a lead is won (staff only).")
    points: int = Field(ge=1, le=1_000_000)
    per_amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2,
                                       description="order_value only: points per this many "
                                                   "rupees, whole blocks only.")
    valid_from: dt.date
    valid_to: dt.date | None = None
    expiry_days: int | None = Field(default=None, ge=1, le=3650,
                                    description="Days the points last. Null: they never expire.")


class RulePatch(BaseModel):
    """On a rule that has awarded points, only `valid_to` and `is_active` change:
    `409 rule_in_use`."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    points: int | None = Field(default=None, ge=1, le=1_000_000)
    per_amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    expiry_days: int | None = Field(default=None, ge=1, le=3650)
    is_active: bool | None = None


class Rule(BaseModel):
    id: str
    code: str
    name: str
    holder: Literal["partner", "staff"]
    basis: Literal["order_value", "lead_won"]
    points: int
    per_amount: str | None
    valid_from: str
    valid_to: str | None
    expiry_days: int | None
    is_active: bool
    used: bool = Field(description="It has awarded points. Then only the end date and the "
                                   "active flag can change.")


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point_value: Decimal = Field(gt=0, max_digits=10, decimal_places=2,
                                 description="Rupees one point is worth on an order.")
    max_redeem_pct: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2,
                                    description="The most of an order's total (GST included) "
                                                "points may pay.")


class SettingsOut(BaseModel):
    point_value: str
    max_redeem_pct: str
    effective_from: str


class GiftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    points_cost: int = Field(ge=1, le=10_000_000)


class GiftPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    points_cost: int | None = Field(default=None, ge=1, le=10_000_000)
    is_active: bool | None = None


class Gift(BaseModel):
    id: str
    name: str
    description: str | None
    points_cost: int
    is_active: bool


class Holder(BaseModel):
    type: Literal["partner", "user"]
    id: str
    name: str | None


class Balance(BaseModel):
    holder: Holder
    balance: int = Field(description="Every earned point, minus what is spent, held, "
                                     "reversed or expired. May be negative after a reversal.")
    point_value: str


class LedgerRow(BaseModel):
    id: str
    points: int
    kind: Literal["earned", "reversed", "redeemed", "released", "expired", "adjusted"]
    reason: str
    at: str
    expires_at: str | None


class LedgerPage(BaseModel):
    data: list[LedgerRow]
    meta: PageMeta


class Adjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partner_id: str | None = Field(default=None, pattern=UUID_RE)
    user_id: str | None = Field(default=None, pattern=UUID_RE)
    points: int = Field(description="Positive adds, negative takes away. Not zero.")
    reason: str = Field(min_length=1, max_length=500)


class OrderRedemptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    points: int = Field(ge=1, le=10_000_000)


class GiftRedemptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gift_id: str = Field(pattern=UUID_RE)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remark: str | None = Field(default=None, max_length=1000)


class Redemption(BaseModel):
    id: str
    kind: Literal["order", "gift"]
    holder: Holder
    points: int
    amount: str | None = Field(description="Order redemptions, once the order is submitted: "
                                           "the rupees taken off the payable.")
    status: Literal["pending", "applied", "fulfilled", "rejected", "withdrawn", "released"]
    gift: Gift | None
    sales_order: dict[str, str | None] | None
    remark: str | None
    decided_at: str | None
    created_at: str


class RedemptionPage(BaseModel):
    data: list[Redemption]
    meta: PageMeta
