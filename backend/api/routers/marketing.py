# ruff: noqa: E501  (route signatures)

"""Marketing material (FS-034): the catalogue and the orders.

**The docstrings below become prose in `docs/api/marketing.md`** (CLAUDE.md 2.3).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.routers.exporting import XLSX_RESPONSE, export, filters_of
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.marketing import (
    Decision,
    DispatchIn,
    MarketingOrder,
    MarketingOrderCreate,
    MarketingOrderPage,
    Material,
    MaterialCreate,
    MaterialPatch,
)
from api.services import exports
from api.services import marketing as service

materials = APIRouter(prefix="/marketing-materials", tags=["marketing material"])
router = APIRouter(prefix="/marketing-orders", tags=["marketing material"])

Id = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not permitted; `own_order`, `not_your_approval`."},
    404: {"model": ErrorResponse, "description": "Not found in your scope."},
    409: {"model": ErrorResponse, "description": "`status_changed`, `code_taken`, `price_changed_today`."},
    422: {"model": ErrorResponse, "description": "`material_inactive`, `remark_required`, a field."},
}


async def _idem(db: Any, claims: Any, idem: str, route: str, body: BaseModel | None,
                work: Callable[[], Awaitable[tuple[int, dict[str, Any]]]]) -> Response:
    digest = payload_digest(body.model_dump(mode="json", exclude_unset=True) if body else {})
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=digest, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@materials.get("", response_model=Envelope[list[Material]], responses=_ERRORS,
               dependencies=[Depends(require("marketing_material", "view"))])
async def list_materials(db: DbSession, active: Annotated[bool | None, Query()] = None) -> Envelope[list[Material]]:
    """The catalogue with today's price and company share. A partner user sees active items only."""
    return Envelope(data=await service.list_materials(db, active))


# `edit`, not `create`: every ordering role holds `create` (plan review blocker)
@materials.post("", status_code=201, response_model=Envelope[Material], responses=_ERRORS,
                dependencies=[Depends(require("marketing_material", "edit"))])
async def create_material(body: MaterialCreate, db: DbSession, caller: CallerDep, claims: Claims,
                          idem: IdemKey) -> Response:
    """Add a catalogue item with its price from today."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 201, {"data": (await service.create_material(db, caller, body)).model_dump(mode="json")}
    return await _idem(db, claims, idem, "POST /api/v1/marketing-materials", body, work)


@materials.patch("/{material_id}", response_model=Envelope[Material], responses=_ERRORS,
                 dependencies=[Depends(require("marketing_material", "edit"))])
async def patch_material(material_id: Id, body: MaterialPatch, db: DbSession, caller: CallerDep,
                         claims: Claims, idem: IdemKey) -> Response:
    """Change an item. A new `price` or `company_share_pct` starts from today; orders
    already placed keep their own figures. Once a day: `409 price_changed_today`."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 200, {"data": (await service.patch_material(db, caller, material_id, body)).model_dump(mode="json")}
    return await _idem(db, claims, idem, f"PATCH /api/v1/marketing-materials/{material_id}", body, work)


@router.post("", status_code=201, response_model=Envelope[MarketingOrder], responses=_ERRORS,
             dependencies=[Depends(require("marketing_material", "create"))])
async def create_order(body: MarketingOrderCreate, db: DbSession, caller: CallerDep, claims: Claims,
                       idem: IdemKey) -> Response:
    """Order marketing material. A partner user orders for itself; staff for a dealer
    or, with no `partner_id`, for their office's own use (then the company pays all).
    Prices and shares are copied onto the lines. The order goes straight to the
    District Manager over the office; there is no draft."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 201, {"data": (await service.create_order(db, caller, body)).model_dump(mode="json")}
    return await _idem(db, claims, idem, "POST /api/v1/marketing-orders", body, work)


@router.get("", response_model=MarketingOrderPage, responses=_ERRORS,
            dependencies=[Depends(require("marketing_material", "view"))])
async def list_orders(
    db: DbSession, caller: CallerDep,
    status_: Annotated[str | None, Query(alias="status", description="Comma-separated statuses.")] = None,
    partner_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    awaiting: Annotated[Literal["me"] | None, Query(description="`me`: the ones you may approve now.")] = None,
    mine: Annotated[bool, Query(description="Only the ones you asked for.")] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> MarketingOrderPage:
    """Marketing orders in your scope, newest first: staff see every order, a partner
    user its own subtree's."""
    return await service.list_orders(db, caller, status=status_, partner_id=partner_id, awaiting=awaiting,
                                     mine=mine, cursor=cursor, limit=limit)


@router.get("/export", response_class=Response, responses={**_ERRORS, **XLSX_RESPONSE},
            dependencies=[Depends(require("marketing_material", "view"))])
async def export_orders(db: DbSession, caller: CallerDep,
                        filters: Annotated[dict[str, Any], Depends(filters_of(list_orders))]) -> Response:
    """Marketing orders as Excel, with the same filters (FS-030)."""
    return await export(list_orders, stem="marketing-orders", title="Marketing orders",
                        columns=exports.MARKETING_ORDERS, user_id=caller.user_id, filters=filters,
                        db=db, caller=caller)


@router.get("/{order_id}", response_model=Envelope[MarketingOrder], responses=_ERRORS,
            dependencies=[Depends(require("marketing_material", "view"))])
async def get_order(order_id: Id, db: DbSession, caller: CallerDep) -> Envelope[MarketingOrder]:
    """One order with its lines, the decision, the dispatch and `can`."""
    return Envelope(data=await service.get_order(db, caller, order_id))


def _action(action: str, doc: str) -> None:
    async def endpoint(order_id: Id, body: Decision, db: DbSession, caller: CallerDep, claims: Claims,
                       idem: IdemKey) -> Response:
        async def work() -> tuple[int, dict[str, Any]]:
            out = await service.act(db, caller, order_id, action, body.remark)
            return 200, {"data": out.model_dump(mode="json")}
        return await _idem(db, claims, idem, f"POST /api/v1/marketing-orders/{order_id}/{action}", body, work)
    endpoint.__doc__ = doc
    endpoint.__name__ = f"{action}_marketing_order"
    router.post(f"/{{order_id}}/{action}", response_model=Envelope[MarketingOrder], responses=_ERRORS,
                dependencies=[Depends(require("marketing_material", "view"))])(endpoint)


_action("approve", "The District Manager over the order's office (or above it, or an admin) approves. "
                   "Not your own order: `403 own_order`.")
_action("reject", "Reject with a remark (required).")
_action("cancel", "The requester cancels while submitted; the marketing team cancels an approved one, with a remark.")


@router.post("/{order_id}/dispatch", response_model=Envelope[MarketingOrder], responses=_ERRORS,
             dependencies=[Depends(require("marketing_material", "edit"))])
async def dispatch(order_id: Id, body: DispatchIn, db: DbSession, caller: CallerDep, claims: Claims,
                   idem: IdemKey) -> Response:
    """The marketing team marks an approved order sent, with the date and a reference."""
    async def work() -> tuple[int, dict[str, Any]]:
        out = await service.act(db, caller, order_id, "dispatch", None, body.dispatched_on, body.reference)
        return 200, {"data": out.model_dump(mode="json")}
    return await _idem(db, claims, idem, f"POST /api/v1/marketing-orders/{order_id}/dispatch", body, work)
