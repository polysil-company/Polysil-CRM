"""Payments (FS-022): Accounts records money received, spreads it over orders, and
plans instalments; managers and dealers read their own. Recorded, never collected."""

# ruff: noqa: E501  (route signatures and their descriptions)

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas import payments as sch
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.services import payments as service

router = APIRouter(prefix="/payments", tags=["payments"])
orders = APIRouter(prefix="/orders", tags=["payments"])
partners = APIRouter(prefix="/partners", tags=["payments"])

Id = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not in your permissions."},
    404: {"model": ErrorResponse, "description": "Not in your scope."},
    422: {"model": ErrorResponse, "description": "A rule refused it; see `code` and `fields`."},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    409: {"model": ErrorResponse, "description": "See `code`: order_not_payable, duplicate_reference, already_void, order_has_payments."},
}


async def _idem(db: Any, claims: Any, idem: str, route: str, body: BaseModel,
                work: Callable[[], Awaitable[BaseModel]], status: int = 200) -> Response:
    async def run() -> tuple[int, dict[str, Any]]:
        out = await work()
        return status, {"data": out.model_dump(mode="json", by_alias=True)}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=payload_digest(body.model_dump(mode="json")), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("", status_code=201, response_model=Envelope[sch.Payment], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("payments", "create"))])
async def record_payment(body: sch.PaymentIn, db: DbSession, caller: CallerDep, claims: Claims,
                         idem: IdemKey) -> Response:
    """Record one receipt and spread it over orders. Part of it may stay on the
    dealer's account. A receipt with no dealer pays direct orders and is allocated
    in full. `422 over_allocated`, `must_allocate`, `partner_mismatch`,
    `ref_required`; `409 order_not_payable`, `duplicate_reference`."""
    return await _idem(db, claims, idem, "POST /api/v1/payments", body,
                       lambda: service.record(db, caller, body), status=201)


@router.post("/{payment_id}/allocations", response_model=Envelope[sch.Payment], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("payments", "create"))])
async def allocate_payment(payment_id: Id, body: sch.AllocateIn, db: DbSession, caller: CallerDep,
                           claims: Claims, idem: IdemKey) -> Response:
    """Spread what is left of a receipt over more orders."""
    return await _idem(db, claims, idem, f"POST /api/v1/payments/{payment_id}/allocations", body,
                       lambda: service.allocate(db, caller, payment_id, body))


@router.post("/{payment_id}/void", response_model=Envelope[sch.Payment], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("payments", "edit"))])
async def void_payment(payment_id: Id, body: sch.VoidIn, db: DbSession, caller: CallerDep,
                       claims: Claims, idem: IdemKey) -> Response:
    """Void a receipt entered by mistake; re-enter it correctly. Its allocations stop
    counting. `409 already_void`."""
    return await _idem(db, claims, idem, f"POST /api/v1/payments/{payment_id}/void", body,
                       lambda: service.void(db, caller, payment_id, body))


@router.get("", response_model=sch.PaymentPage, responses=_ERRORS,
            dependencies=[Depends(require("payments", "view"))])
async def list_payments(db: DbSession, caller: CallerDep,
                        partner_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                        sales_order_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                        include_voided: bool = False,
                        limit: Annotated[int, Query(ge=1, le=100)] = 50,
                        cursor: Annotated[str | None, Query()] = None) -> sch.PaymentPage:
    """Receipts, newest first, in your scope."""
    return await service.list_payments(db, caller, partner_id=partner_id, sales_order_id=sales_order_id,
                                       include_voided=include_voided, limit=limit, cursor=cursor)


@router.get("/{payment_id}", response_model=Envelope[sch.Payment], responses=_ERRORS,
            dependencies=[Depends(require("payments", "view"))])
async def get_payment(payment_id: Id, db: DbSession, caller: CallerDep) -> Envelope[sch.Payment]:
    """One receipt with its allocations."""
    return Envelope(data=await service._payment(db, caller, payment_id))


@orders.put("/{order_id}/payment-schedule", response_model=Envelope[sch.OrderPayments], responses=_MUTATION_ERRORS,
            dependencies=[Depends(require("payments", "edit"))])
async def set_schedule(order_id: Id, body: sch.ScheduleIn, db: DbSession, caller: CallerDep,
                       claims: Claims, idem: IdemKey) -> Response:
    """Replace the order's planned instalments: 0 to 5, each a date and an amount.
    `422 schedule_over_payable`; `409 order_not_payable`."""
    return await _idem(db, claims, idem, f"PUT /api/v1/orders/{order_id}/payment-schedule", body,
                       lambda: service.set_schedule(db, caller, order_id, body))


@partners.get("/{partner_id}/credit", response_model=Envelope[sch.PartnerCredit], responses=_ERRORS)
async def partner_credit(partner_id: Id, db: DbSession, caller: CallerDep) -> Envelope[sch.PartnerCredit]:
    """A dealer's credit limit, what it owes on open orders less its receipts, and
    what is left (FS-027). For Accounts, and for staff who manage dealers and can
    see this one. A dealer, a distributor or a field officer gets 403: credit terms
    are never shown to them."""
    return Envelope(data=await service.credit(db, caller, partner_id))


@partners.get("/{partner_id}/ledger", response_model=Envelope[sch.Ledger], responses=_ERRORS,
              dependencies=[Depends(require("payments", "view"))])
async def partner_ledger(partner_id: Id, db: DbSession, caller: CallerDep,
                         from_: Annotated[dt.date | None, Query(alias="from")] = None,
                         to: dt.date | None = None) -> Envelope[sch.Ledger]:
    """The dealer's orders and receipts with a running balance. Positive: the dealer
    owes. Orders count on approval at their total; cancelled ones never."""
    return Envelope(data=await service.ledger(db, caller, partner_id, start=from_, end=to))
