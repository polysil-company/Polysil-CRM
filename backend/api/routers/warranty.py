# ruff: noqa: E501  (field descriptions and embedded SQL)

"""Warranty (FS-046): the periods, and an order's warranty line by line."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Response
from fastapi.responses import JSONResponse

from api.deps import Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.warranty import OrderWarranty, WarrantyTerm, WarrantyTermIn
from api.services import warranty as service

terms = APIRouter(prefix="/warranty-terms", tags=["warranty"])
orders = APIRouter(prefix="/orders", tags=["warranty"])

Id = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse,
          "description": "`idempotency_key_required`: a write sent without an Idempotency-Key."},
    403: {"model": ErrorResponse, "description": "Reading needs masters.view; setting needs masters.edit."},
    409: {"model": ErrorResponse, "description": "`term_exists`: one already starts that day for that category."},
    422: {"model": ErrorResponse,
          "description": "`validation_failed`: `effective_from` before tomorrow (IST), `months` outside "
                         "0 to 120, or an unknown `product_category_id`."},
}


@terms.get("", response_model=Envelope[list[WarrantyTerm]], responses=_ERRORS,
           dependencies=[Depends(require("masters", "view"))])
async def list_terms(db: DbSession) -> Envelope[list[WarrantyTerm]]:
    """The warranty periods, in force and past. The row with no category is the
    default for every category without its own. 0 months means no warranty. A row is
    in force from `effective_from` up to the day before `effective_to`. Needs
    masters.view: this is the admin screen; everyone else reads warranty on the
    order and the complaint."""
    return Envelope(data=await service.terms(db))


@terms.post("", status_code=201, response_model=Envelope[list[WarrantyTerm]], responses=_ERRORS,
            dependencies=[Depends(require("masters", "edit"))])
async def set_term(body: WarrantyTermIn, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Set a category's period (or the default's) from a date, tomorrow or later.
    The period in force ends that day. Products already dispatched keep the period
    in force on their start day. Returns the whole list."""
    async def work() -> tuple[int, dict[str, Any]]:
        rows = await service.set_term(db, body)
        return 201, {"data": [r.model_dump(mode="json") for r in rows]}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="POST /api/v1/warranty-terms",
        payload_hash=payload_digest(body.model_dump(mode="json")), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@orders.get("/{order_id}/warranty", response_model=Envelope[OrderWarranty],
            responses={403: {"model": ErrorResponse, "description": "Needs sales_orders.view and dispatch.view."},
                       404: {"model": ErrorResponse, "description": "No such order, or not visible."}},
            # plan review M-3: without dispatch.view every line would read not_dispatched
            dependencies=[Depends(require("sales_orders", "view")), Depends(require("dispatch", "view"))])
async def order_warranty(order_id: Id, db: DbSession) -> Envelope[OrderWarranty]:
    """The order's warranty, line by line: each live dispatch with its start, end
    and status, the line's status, and the complaints raised on that product. For
    the order page's Warranty tab."""
    return Envelope(data=await service.order_warranty(db, order_id))
