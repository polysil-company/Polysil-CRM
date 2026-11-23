"""Targets (FS-025): monthly targets per person, and achievement live."""

# ruff: noqa: E501  (route signatures and their descriptions)

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import ErrorResponse
from api.schemas.leads import UUID_RE
from api.services import targets as service

router = APIRouter(prefix="/targets", tags=["targets"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "`not_your_team`, or no targets permission."},
    404: {"model": ErrorResponse, "description": "No such person in your scope."},
    422: {"model": ErrorResponse, "description": "`month_closed`, `user_inactive`, or a bad value."},
}
Month = Annotated[str, Query(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")]


class TargetsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: Annotated[str, Field(pattern=UUID_RE)]
    month: Annotated[str, Field(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")]
    targets: dict[str, Decimal] = Field(description="Any of order_value (rupees), orders, leads_won, visits (whole numbers). Left-out metrics keep their value.")


@router.put("", responses=_ERRORS, dependencies=[Depends(require("targets", "create"))])
async def put_targets(body: TargetsIn, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey) -> Response:
    """Set a person's targets for a month: someone below you in office and rank
    (admin and MD: anyone). Each change is kept; the latest counts."""
    async def run() -> tuple[int, dict[str, Any]]:
        return 200, {"data": await service.set_targets(db, caller, body.user_id, body.month, body.targets)}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route="PUT /api/v1/targets",
                                   payload_hash=payload_digest(body.model_dump(mode="json")), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("", responses=_ERRORS, dependencies=[Depends(require("targets", "view"))])
async def get_targets(db: DbSession, caller: CallerDep, month: Month,
                      user_id: Annotated[str, Query(pattern=UUID_RE)]) -> JSONResponse:
    """A person's targets for the month, with who changed what and when."""
    return JSONResponse({"data": await service.get_targets(db, caller, user_id, month)})


@router.get("/achievement", responses=_ERRORS, dependencies=[Depends(require("targets", "view"))])
async def achievement(db: DbSession, caller: CallerDep, month: Month,
                      user_id: Annotated[str | None, Query(pattern=UUID_RE)] = None) -> JSONResponse:
    """Target, achieved so far and percentage per metric, for you and everyone below
    you, with or without a target. `achieved` is null for a module you may not see."""
    return JSONResponse({"data": await service.achievement(db, caller, month, user_id)})
