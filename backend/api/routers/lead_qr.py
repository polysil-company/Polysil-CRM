"""/lead-qr-codes: the printed codes that bring leads from a dealer's counter, a
banner or a leaflet (FS-003a §4). Staff only, under the leads scope."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.public_leads import QrCode, QrCodeCreate, QrCodeList
from api.services import public_leads as service

router = APIRouter(prefix="/lead-qr-codes", tags=["leads"])

_ERRORS: dict[int | str, dict[str, object]] = {
    422: {"model": ErrorResponse, "description": "A field."},
}


@router.post("", status_code=201, response_model=Envelope[QrCode], responses=_ERRORS,
             dependencies=[Depends(require("leads", "create"))])
async def create_qr(body: QrCodeCreate, db: DbSession, caller: CallerDep, claims: Claims,
                    idem: IdemKey) -> Response:
    """Make a code to print. `url` is what the QR image encodes; draw it on the page
    and offer a download. Leads from it are credited to `partner_id` when set."""
    async def work() -> tuple[int, dict[str, Any]]:
        qr = await service.create_qr(db, caller, body)
        return 201, {"data": qr.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="POST /api/v1/lead-qr-codes",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("", response_model=QrCodeList, responses=_ERRORS,
            dependencies=[Depends(require("leads", "view"))])
async def list_qr(db: DbSession) -> QrCodeList:
    """The codes in your scope, newest first, with how many leads each brought."""
    return await service.list_qr(db)
