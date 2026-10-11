"""Stock (FS-023): warehouses, recorded stock, the stock list and availability.
Staff only; dealers and the board hold no stock permission."""

# ruff: noqa: E501  (route signatures and their descriptions)

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.errors import ValidationFailed
from api.idempotency import payload_digest, run_idempotent
from api.schemas import stock as sch
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.services import stock as service

warehouses = APIRouter(prefix="/warehouses", tags=["stock"])
router = APIRouter(prefix="/stock", tags=["stock"])

Id = Annotated[str, Path(pattern=UUID_RE)]
_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not in your permissions."},
    404: {"model": ErrorResponse, "description": "No such warehouse or product."},
    422: {"model": ErrorResponse, "description": "A rule refused it; see `code` and `fields`."},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    409: {"model": ErrorResponse, "description": "See `code`: negative_stock, warehouse_inactive, product_inactive, default_warehouse, code_taken."},
}


async def _idem(db: Any, claims: Any, idem: str, route: str, body: BaseModel,
                work: Callable[[], Awaitable[BaseModel]], status: int = 200) -> Response:
    async def run() -> tuple[int, dict[str, Any]]:
        out = await work()
        return status, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=payload_digest(body.model_dump(mode="json")), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@warehouses.get("", response_model=Envelope[list[sch.Warehouse]], responses=_ERRORS,
                dependencies=[Depends(require("stock", "view"))])
async def list_warehouses(db: DbSession, include_inactive: bool = False) -> Envelope[list[sch.Warehouse]]:
    """The "Order to" picker. The default first."""
    return Envelope(data=await service.list_warehouses(db, include_inactive))


@warehouses.post("", status_code=201, response_model=Envelope[sch.Warehouse], responses=_MUTATION_ERRORS,
                 dependencies=[Depends(require("stock", "edit"))])
async def create_warehouse(body: sch.WarehouseIn, db: DbSession, caller: CallerDep, claims: Claims,
                           idem: IdemKey) -> Response:
    """Add a warehouse. `is_default: true` moves the default here."""
    return await _idem(db, claims, idem, "POST /api/v1/warehouses", body,
                       lambda: service.create_warehouse(db, caller, body), status=201)


@warehouses.patch("/{warehouse_id}", response_model=Envelope[sch.Warehouse], responses=_MUTATION_ERRORS,
                  dependencies=[Depends(require("stock", "edit"))])
async def update_warehouse(warehouse_id: Id, body: sch.WarehousePatch, db: DbSession, caller: CallerDep,
                           claims: Claims, idem: IdemKey) -> Response:
    """Edit, deactivate or make the default. `409 default_warehouse`: make another
    the default before deactivating this one."""
    return await _idem(db, claims, idem, f"PATCH /api/v1/warehouses/{warehouse_id}", body,
                       lambda: service.update_warehouse(db, caller, warehouse_id, body))


@router.post("/movements", status_code=201, response_model=Envelope[sch.MovementsOut], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("stock", "create"))])
async def record_movement(body: sch.MovementIn, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Stock in (a receipt; an opening balance is a receipt referenced "Opening") or
    a correction (an adjustment, which may be negative). Dispatches move stock by
    themselves. `409 negative_stock`, `warehouse_inactive`, `product_inactive`;
    `422 qty_precision`."""
    return await _idem(db, claims, idem, "POST /api/v1/stock/movements", body,
                       lambda: service.record(db, body), status=201)


@router.get("/movements", response_model=sch.MovementPage, responses=_ERRORS,
            dependencies=[Depends(require("stock", "view"))])
async def list_movements(db: DbSession,
                         warehouse_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                         product_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                         limit: Annotated[int, Query(ge=1, le=100)] = 50,
                         cursor: Annotated[str | None, Query()] = None) -> sch.MovementPage:
    """The stock ledger, newest first, with the dispatch and order behind each
    dispatch movement."""
    return await service.movements(db, warehouse_id=warehouse_id, product_id=product_id, limit=limit, cursor=cursor)


@router.get("", response_model=sch.StockPage, responses=_ERRORS,
            dependencies=[Depends(require("stock", "view"))])
async def stock_list(db: DbSession,
                     warehouse_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                     product_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                     short_only: bool = False,
                     limit: Annotated[int, Query(ge=1, le=200)] = 100,
                     cursor: Annotated[str | None, Query()] = None) -> sch.StockPage:
    """On hand, committed and available per warehouse and product. `short_only`:
    available below zero."""
    return await service.stock_list(db, warehouse_id=warehouse_id, product_id=product_id,
                                    short_only=short_only, limit=limit, cursor=cursor)


@router.get("/availability", response_model=Envelope[sch.Availability], responses=_ERRORS,
            dependencies=[Depends(require("stock", "view"))])
async def availability(db: DbSession,
                       product_ids: Annotated[str, Query(description="Comma-separated, up to 100.")],
                       warehouse_id: Annotated[str | None, Query(pattern=UUID_RE)] = None) -> Envelope[sch.Availability]:
    """The order form's call: what the warehouse (the default when omitted) has
    free per product. A warning only; it never blocks an order."""
    ids = [x.strip() for x in product_ids.split(",") if x.strip()]
    if not ids or len(ids) > 100 or not all(re.match(UUID_RE, x) for x in ids):
        raise ValidationFailed(fields={"product_ids": "1 to 100 product ids"})
    return Envelope(data=await service.availability(db, warehouse_id, ids))
