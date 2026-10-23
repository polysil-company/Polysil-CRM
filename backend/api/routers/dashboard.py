"""GET /dashboard/overview (FS-017): the sign-in screen's figures."""

from __future__ import annotations

from enum import IntEnum
from typing import Annotated

from fastapi import APIRouter, Query

from api.deps import CallerDep, DbSession
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.dashboard import DashboardOverview
from api.services import dashboard as service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class Days(IntEnum):
    """An enum, not a Literal: a Literal of ints refuses the query string's "7"."""

    week = 7
    month = 30
    quarter = 90


_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    422: {"model": ErrorResponse, "description": "`days` is not 7, 30 or 90."},
}


@router.get("/overview", response_model=Envelope[DashboardOverview], responses=_ERRORS)
async def overview(db: DbSession, caller: CallerDep,
                   days: Annotated[Days, Query(
                       description="The period: the last 7, 30 or 90 IST days, today "
                       "included.")] = Days.month,
                   ) -> Envelope[DashboardOverview]:
    """The first screen after sign-in: pipeline value, new leads, conversion and
    overdue follow-ups with their change against the previous period, the
    pipeline by stage, leads by source, and the next follow-ups.

    Anyone signed in may call it; every figure is in your own scope. A role with no
    lead permission gets zeros, and one with no task permission gets no task
    figures, never a 403."""
    return Envelope(data=await service.overview(db, caller, int(days)))
