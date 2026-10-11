"""/portal: a farmer's own record (FS-044). Sign in with the existing OTP routes.
Staff and dealers get `403 not_a_consumer`; while the portal is off, `403 portal_off`."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.portal import (
    PortalComplaint,
    PortalConsent,
    PortalEnquiry,
    PortalMe,
    PortalOrder,
    PortalQuotation,
    PortalRating,
    PortalRatingCreate,
)
from api.services import portal as service

router = APIRouter(prefix="/portal", tags=["portal"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse,
          "description": "Not signed in, or the portal was switched off: sign in again."},
    403: {"model": ErrorResponse,
          "description": "`not_a_consumer`: staff and dealers use the main app. `portal_off`: "
                         "the portal is switched off."},
}


@router.get("/me", response_model=Envelope[PortalMe], responses=_ERRORS)
async def me(db: DbSession, caller: CallerDep) -> Envelope[PortalMe]:
    """The farmer's own details and consent."""
    return Envelope(data=await service.me(db, caller))


@router.patch("/me", response_model=Envelope[PortalMe],
              responses={**_ERRORS, 400: {"model": ErrorResponse,
                                          "description": "No Idempotency-Key."}})
async def set_consent(body: PortalConsent, db: DbSession, caller: CallerDep, claims: Claims,
                      idem: IdemKey) -> Response:
    """Give consent (`true`) or withdraw it (`false`). Giving it again keeps the
    first date."""
    async def work() -> tuple[int, dict[str, Any]]:
        out = await service.set_consent(db, caller, body)
        return 200, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="PATCH /api/v1/portal/me",
        payload_hash=payload_digest(body.model_dump(mode="json")), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("/enquiries", response_model=Envelope[list[PortalEnquiry]], responses=_ERRORS)
async def enquiries(db: DbSession, caller: CallerDep) -> Envelope[list[PortalEnquiry]]:
    """The farmer's enquiries, once qualified, newest first."""
    return Envelope(data=await service.enquiries(db, caller))


@router.get("/quotations", response_model=Envelope[list[PortalQuotation]], responses=_ERRORS)
async def quotations(db: DbSession, caller: CallerDep) -> Envelope[list[PortalQuotation]]:
    """Quotations sent to the farmer, the current version of each."""
    return Envelope(data=await service.quotations(db, caller))


@router.get("/orders", response_model=Envelope[list[PortalOrder]], responses=_ERRORS)
async def orders(db: DbSession, caller: CallerDep) -> Envelope[list[PortalOrder]]:
    """The farmer's orders with their dispatches."""
    return Envelope(data=await service.orders(db, caller))


@router.get("/complaints", response_model=Envelope[list[PortalComplaint]], responses=_ERRORS)
async def complaints(db: DbSession, caller: CallerDep) -> Envelope[list[PortalComplaint]]:
    """Complaints on the farmer's enquiries or orders."""
    return Envelope(data=await service.complaints(db, caller))


@router.get("/ratings", response_model=Envelope[list[PortalRating]], responses=_ERRORS)
async def ratings(db: DbSession, caller: CallerDep) -> Envelope[list[PortalRating]]:
    """His ratings on his own orders and complaints, newest first: the ones he gave
    here and the ones an officer recorded for him. Show "Rated" and the stars beside
    the order or complaint with that number and target; offer "Rate" on the others
    once an order has a dispatch or a complaint is closed. A complaint listed as
    closed may have been cancelled or rejected: rating it answers `422 not_rateable`,
    and the button should go away."""
    return Envelope(data=await service.ratings(db, caller))


_RATE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "No Idempotency-Key."},
    404: {"model": ErrorResponse, "description": "No such order or complaint among his own."},
    409: {"model": ErrorResponse,
          "description": "`rating_exists`: rated already, by him or by an officer for him."},
    422: {"model": ErrorResponse,
          "description": "`not_rateable`: nothing has shipped, or the complaint is not "
                         "closed. Otherwise a field."},
}


@router.post("/ratings", status_code=201, response_model=Envelope[PortalRating],
             responses=_RATE_ERRORS)
async def rate(body: PortalRatingCreate, db: DbSession, caller: CallerDep, claims: Claims,
               idem: IdemKey) -> Response:
    """Rate an installation (an order with a dispatch) or a service visit (a closed
    complaint), 1 to 5 stars with an optional comment. Once only; it cannot be
    changed. Send the number from the orders or complaints list."""
    async def work() -> tuple[int, dict[str, Any]]:
        out = await service.rate(db, caller, body)
        return 201, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="POST /api/v1/portal/ratings",
        payload_hash=payload_digest(body.model_dump(mode="json")), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
