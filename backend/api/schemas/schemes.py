"""Schemes (FS-031): the request and response shapes.

**These descriptions become the field notes in `docs/api/schemes.md`**, the
contract the frontend builds against. Money and figures are decimal strings.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.leads import PageMeta

SchemeType = Literal["order_discount", "order_points", "next_order", "period"]
Metric = Literal["order_value", "product_qty"]
BenefitKind = Literal["pct", "flat", "points"]
Period = Literal["month", "quarter"]
TargetType = Literal["territory", "partner_type", "partner", "product", "product_category"]

_CODE = r"^[A-Za-z0-9_-]{2,40}$"


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: Metric = Field(default="order_value", description="order_value: the counted lines' "
                           "taxable value, before GST. product_qty: their quantity.")
    min: Decimal = Field(default=Decimal("0"), ge=0, max_digits=17, decimal_places=3,
                         description="Inclusive. 0 means any order.")
    max: Decimal | None = Field(default=None, ge=0, max_digits=17, decimal_places=3,
                                description="Inclusive. Null for no upper limit.")


class Benefit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: BenefitKind = Field(description="pct of the counted value, a flat amount, or points.")
    value: Decimal = Field(gt=0, max_digits=17, decimal_places=3,
                           description="The percentage, the rupees, or the points.")
    cap: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2,
                                description="The most one benefit is worth, in rupees. "
                                            "Not for points.")
    entitlement_days: int | None = Field(
        default=None, ge=1, le=3650,
        description="Next-order and period credits: days the credit stays usable. "
                    "Defaults to 90. Null for the other types.")


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TargetType = Field(description="territory (a state, district or taluka; matches "
                             "anything under it), partner_type (distributor, dealer or "
                             "sub_dealer), partner (and its subtree), product, product_category.")
    id: str = Field(min_length=1, max_length=64,
                    description="The id, or for partner_type the type's name.")


class SchemeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=_CODE, description="Unique. Letters, digits, - and _.")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    scheme_type: SchemeType = Field(description="order_discount (type 1), order_points "
                                    "(type 2), next_order (type 3), period (type 4).")
    condition: Condition = Field(default_factory=Condition)
    benefit: Benefit
    period: Period | None = Field(default=None, description="Type 4 only.")
    valid_from: dt.date
    valid_to: dt.date | None = Field(default=None, description="Null for open-ended. "
                                     "Required for a period scheme.")
    priority: int = Field(default=100, ge=0, le=10000, description="Lower runs first.")
    stackable: bool = Field(default=False, description="Whether another order discount "
                            "may apply beside it.")
    targets: list[Target] = Field(default_factory=list, max_length=200,
                                  description="[] means everyone. Same type OR'd, "
                                              "different types AND'd.")


class SchemePatch(BaseModel):
    """Any create field. On a scheme that has given anything, only `valid_to`
    (earlier, not before today) and `is_active` are accepted: `409 scheme_in_use`."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    scheme_type: SchemeType | None = None
    condition: Condition | None = None
    benefit: Benefit | None = None
    period: Period | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)
    stackable: bool | None = None
    is_active: bool | None = None
    targets: list[Target] | None = Field(default=None, max_length=200)


class SchemeRef(BaseModel):
    id: str
    code: str
    name: str


class ConditionOut(BaseModel):
    metric: Metric
    min: str
    max: str | None


class BenefitOut(BaseModel):
    kind: BenefitKind
    value: str
    cap: str | None
    entitlement_days: int | None


class Scheme(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    scheme_type: SchemeType
    condition: ConditionOut
    benefit: BenefitOut
    period: Period | None
    valid_from: str
    valid_to: str | None
    priority: int
    stackable: bool
    is_active: bool
    is_current: bool = Field(description="Active, and today is within its dates.")
    used: bool = Field(description="It has given a benefit. Then only the end date and "
                                   "the active flag can change.")
    targets: list[Target] = Field(description="A partner user never sees partner targets.")
    created_at: str


class SchemePage(BaseModel):
    data: list[Scheme]
    meta: PageMeta


class PreviewDiscount(BaseModel):
    scheme: SchemeRef
    basis: str = Field(description="The counted lines' taxable value.")
    amount: str


class PreviewEntitlement(BaseModel):
    entitlement_id: str
    scheme: SchemeRef
    amount: str


class PreviewOnDelivery(BaseModel):
    scheme: SchemeRef
    kind: Literal["points", "next_order_credit"]
    points: int | None = Field(description="Points earned when the order is delivered.")
    basis: str


class OrderSchemePreview(BaseModel):
    """What submit would store now. Nothing is stored by reading it."""

    discounts: list[PreviewDiscount]
    entitlements: list[PreviewEntitlement]
    on_delivery: list[PreviewOnDelivery] = Field(
        description="Earned when the order is delivered, worked on the full quantity; "
                    "the real figure uses what is dispatched.")
    total_benefit: str
    payable: str = Field(description="The order total minus the benefits.")


class Standing(BaseModel):
    period_start: str
    period_end: str
    metric: Metric
    achieved: str
    min: str
    max: str | None
    qualifies: bool


class PartnerRefLite(BaseModel):
    id: str
    name: str


class OrderRefLite(BaseModel):
    id: str
    order_no: str | None


class Entitlement(BaseModel):
    id: str
    scheme: SchemeRef
    partner: PartnerRefLite
    kind: Literal["pct", "flat"] = Field(description="pct of the order it is used on, or "
                                                     "a flat amount.")
    value: str
    cap: str | None
    status: Literal["available", "consumed", "expired", "reversed"]
    earned_at: str
    expires_at: str
    source_order: OrderRefLite | None = Field(description="The order that earned it (type 3).")
    period_start: str | None = Field(description="The period that earned it (type 4).")
    period_end: str | None
    consumed_order: OrderRefLite | None


class EntitlementPage(BaseModel):
    data: list[Entitlement]
    meta: PageMeta


class OrderBenefit(BaseModel):
    """A benefit on an order. It reduces `payable`; it never changes the invoice."""

    id: str
    kind: Literal["discount", "entitlement_used", "reward_redemption"]
    scheme: SchemeRef | None = Field(description="Null for reward points (FS-032).")
    amount: str
    status: Literal["applied", "reversed"]
    applied_at: str
