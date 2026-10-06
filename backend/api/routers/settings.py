"""/settings: company-wide settings an administrator changes (FS-036)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.errors import ForbiddenError
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.settings import Setting, SettingsPatch
from api.services import settings as service

router = APIRouter(prefix="/settings", tags=["settings"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse,
          "description": "`idempotency_key_required`: a write sent without an Idempotency-Key."},
    403: {"model": ErrorResponse, "description": "Staff only; changing needs masters.edit."},
    422: {"model": ErrorResponse, "description": "An unknown key, or a value outside its rule."},
}


@router.get("", response_model=Envelope[list[Setting]], responses=_ERRORS)
async def list_settings(db: DbSession, caller: CallerDep) -> Envelope[list[Setting]]:
    """Every setting with its value and its rule. Render the list generically: a
    choice from `allowed`, a number between `min` and `max`, or role codes."""
    if caller.partner_id is not None:
        raise ForbiddenError("Settings are for staff.")
    return Envelope(data=await service.list_settings(db))


@router.patch("", response_model=Envelope[list[Setting]], responses=_ERRORS,
              dependencies=[Depends(require("masters", "edit"))])
async def patch_settings(body: SettingsPatch, db: DbSession, claims: Claims,
                         idem: IdemKey) -> Response:
    """Change one or more settings. All or nothing. Each change is recorded with
    the old and new value. Returns the full list."""
    async def work() -> tuple[int, dict[str, Any]]:
        items = await service.patch_settings(db, body)
        return 200, {"data": [i.model_dump(mode="json") for i in items]}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="PATCH /api/v1/settings",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
