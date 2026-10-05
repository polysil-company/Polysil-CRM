"""Stock (FS-023): warehouses, movements, the stock list, availability."""

# ruff: noqa: E501  (field descriptions are the generated API doc)

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.leads import UUID_RE, PageMeta, UserRef

_Id = Annotated[str, Field(pattern=UUID_RE)]


class _In(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class WarehouseIn(_In):
    code: Annotated[str, Field(min_length=1, max_length=30, description="Unique, case-insensitive.")]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    territory_id: _Id | None = Field(default=None, description="Kept for routing orders by area later (GAP-218); nothing reads it yet.")
    is_default: bool = Field(default=False, description="Moves the default here.")
    is_active: bool = True


class WarehousePatch(_In):
    code: Annotated[str | None, Field(default=None, min_length=1, max_length=30)]
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=200)]
    territory_id: _Id | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class Warehouse(BaseModel):
    id: str
    code: str
    name: str
    territory_id: str | None
    is_default: bool
    is_active: bool


class WarehouseRef(BaseModel):
    id: str
    code: str
    name: str


class MovementLineIn(_In):
    product_id: _Id
    qty: Annotated[Decimal, Field(max_digits=14, description="In the product's unit. A receipt is positive; an adjustment may be negative.")]


class MovementIn(_In):
    warehouse_id: _Id
    kind: Literal["receipt", "adjustment"] = Field(description="An opening balance is a receipt referenced \"Opening\".")
    reference: Annotated[str | None, Field(default=None, max_length=200)]
    note: Annotated[str | None, Field(default=None, max_length=1000)]
    lines: Annotated[list[MovementLineIn], Field(min_length=1, max_length=200)]


class MovementOut(BaseModel):
    id: str
    product_id: str
    qty: str
    on_hand_after: str


class MovementsOut(BaseModel):
    movements: list[MovementOut]


class ProductRef(BaseModel):
    id: str
    code: str | None
    name: str


class StockRow(BaseModel):
    warehouse: WarehouseRef
    product: ProductRef
    on_hand: str
    committed: str = Field(description="What submitted, approved and partly dispatched orders for this warehouse still owe.")
    available: str = Field(description="On hand less committed. Negative is short.")
    uom: str


class StockPage(BaseModel):
    data: list[StockRow]
    meta: PageMeta


class AvailabilityItem(BaseModel):
    product_id: str
    available: str
    on_hand: str


class Availability(BaseModel):
    warehouse_id: str
    items: list[AvailabilityItem]


class LedgerMovement(BaseModel):
    id: str
    warehouse: WarehouseRef
    product: ProductRef
    qty: str
    kind: Literal["receipt", "adjustment", "dispatch", "dispatch_void"]
    reference: str | None
    note: str | None
    dispatch_no: str | None = Field(description="Set for dispatch movements.")
    order: str | None = Field(description="The order number, for dispatch movements.")
    created_by: UserRef | None
    created_at: str


class MovementPage(BaseModel):
    data: list[LedgerMovement]
    meta: PageMeta


class LineStock(BaseModel):
    available: str = Field(description="At the order's warehouse, now.")
    short: bool = Field(description="True when available is below what this line still needs.")
