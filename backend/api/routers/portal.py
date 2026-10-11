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
