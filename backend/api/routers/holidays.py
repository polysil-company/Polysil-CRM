"""/holidays: the days complaint targets skip like Sundays (FS-028)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse

from api.deps import Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.holidays import Holiday, HolidayIn
from api.services import holidays as service

router = APIRouter(prefix="/holidays", tags=["holidays"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse,
          "description": "`idempotency_key_required`: a write sent without an Idempotency-Key."},
    403: {"model": ErrorResponse, "description": "Adding or removing needs masters.edit."},
    404: {"model": ErrorResponse, "description": "No holiday on that day."},
    409: {"model": ErrorResponse,
          "description": "`holiday_exists` on add; `holiday_in_past` removing today or "
                         "earlier."},
    422: {"model": ErrorResponse,
          "description": "`holiday_in_past` (today or earlier, IST) or `holiday_sunday` on "
                         "add; a bad name."},
}


@router.get("", response_model=Envelope[list[Holiday]], responses=_ERRORS)
async def list_holidays(
        db: DbSession, _claims: Claims,
        year: Annotated[int | None, Query(ge=2000, le=2100)] = None) -> Envelope[list[Holiday]]:
    """The company's holidays, in order; one year with `year`. Complaint targets
    count working hours and skip these days like Sundays. Any signed-in user."""
    return Envelope(data=await service.list_holidays(db, year))


@router.post("", status_code=201, response_model=Envelope[Holiday], responses=_ERRORS,
             dependencies=[Depends(require("masters", "edit"))])
async def add_holiday(body: HolidayIn, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Add a holiday after today. It applies to complaint targets set after it is
    added; targets already set do not move."""
    async def work() -> tuple[int, dict[str, Any]]:
        h = await service.add_holiday(db, body)
        return 201, {"data": h.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="POST /api/v1/holidays",
        payload_hash=payload_digest(body.model_dump(mode="json")), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.delete("/{day}", status_code=204, responses=_ERRORS,
               dependencies=[Depends(require("masters", "edit"))])
async def remove_holiday(day: Annotated[dt.date, Path()], db: DbSession, claims: Claims,
                         idem: IdemKey) -> Response:
    """Remove a future holiday. A past one stays: it explains targets already set."""
    async def work() -> tuple[int, dict[str, Any]]:
        await service.remove_holiday(db, day)
        return 204, {}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"DELETE /api/v1/holidays/{day.isoformat()}",
        payload_hash=payload_digest({"day": day.isoformat()}), work=work)
    if outcome.status_code == 204:
        return Response(status_code=204)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
