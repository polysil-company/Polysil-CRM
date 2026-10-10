# ruff: noqa: E501  (field descriptions and embedded SQL)

"""Warranty (FS-046) request and response shapes."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LineStatus = Literal["active", "expired", "none", "unknown", "not_dispatched"]
DispatchStatus = Literal["active", "expired", "none", "unknown"]
ClaimStatus = Literal["in_warranty", "expired", "none", "unknown"]


class CategoryRef(BaseModel):
    id: str
    code: str
    name: str


class WarrantyTerm(BaseModel):
    id: str
    product_category: CategoryRef | None = Field(description="Null: the default for every category without its own term.")
    months: int = Field(description="0 means no warranty.")
    effective_from: str = Field(description="First day in force, ISO date.")
    effective_to: str | None = Field(description="First day no longer in force (exclusive); null while open.")


class WarrantyTermIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_category_id: str | None = Field(None, description="Null sets the default.")
    months: int = Field(ge=0, le=120, description="0 to 120. 0 means no warranty.")
    effective_from: dt.date = Field(description="Tomorrow (IST) or later: a term never restates a recorded dispatch.")


class ProductRef(BaseModel):
    id: str
    description: str


class WarrantyDispatch(BaseModel):
    dispatch_id: str
    dispatch_no: str
    qty: str = Field(description="Quantity of this line in the dispatch, a decimal string.")
    start: str = Field(description="The DC date, else the dispatch day in IST.")
    start_basis: Literal["dc_date", "dispatched_at"] = Field(description="Where the start came from.")
    end: str | None = Field(description="The last covered day. Null for no warranty or no term.")
    months: int | None = Field(description="The period in force on the start day. Null: no term then.")
    status: DispatchStatus


class Claim(BaseModel):
    complaint_id: str
    complaint_no: str | None
    status: str = Field(description="The complaint's status.")
    raised_on: str | None = Field(description="The first submit day, IST.")
    defective_qty: str
    warranty_status: ClaimStatus = Field(description="On the day raised, against this order's latest-ending dispatch of the product. On a replacement order the replaced complaint is compared with the replacement's dispatch, so it reads in warranty.")


class WarrantyLine(BaseModel):
    order_line_id: str
    product: ProductRef
    qty_ordered: str
    qty_dispatched: str = Field(description="Across live dispatches.")
    dispatches: list[WarrantyDispatch]
    status: LineStatus = Field(description="From the latest-ending live dispatch of this product on the order.")
    claims: list[Claim] = Field(description="Submitted complaints on this product, linked to this order or replaced by it.")


class ComplaintRef(BaseModel):
    complaint_id: str
    complaint_no: str | None


class OrderWarranty(BaseModel):
    order_id: str
    order_no: str | None = Field(description="Null while the order is a draft.")
    order_type: str = Field(description="As on GET /orders/{id}.")
    replacement_for: ComplaintRef | None = Field(description="The complaint this replacement order was made for.")
    lines: list[WarrantyLine]


class LineWarranty(BaseModel):
    status: ClaimStatus = Field(description="On the day the complaint was raised (its first submit, or today for a draft).")
    start: str | None
    end: str | None
    months: int | None
    basis: Literal["dispatch", "supply_date"] | None = Field(description="Where the start came from.")
