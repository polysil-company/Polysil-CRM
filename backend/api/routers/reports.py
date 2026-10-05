"""Reports (FS-024) and the 360° lead view.

Live aggregates scoped as the lists are. A figure the caller has no right to is
null, never 0; a report whose base module the caller lacks is 403. Excel answers
501 until the shared exports writer is on main (GAP-220)."""

# ruff: noqa: E501  (route signatures and their descriptions)

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from api.deps import CallerDep, DbSession, require
from api.schemas.auth import ErrorResponse
from api.schemas.leads import UUID_RE
from api.services import reports as service

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require("reports", "view"))])
leads = APIRouter(prefix="/leads", tags=["reports"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "No reports.view, or not the report's base module, or a dealer on a staff report."},
    422: {"model": ErrorResponse, "description": "A bad window or filter."},
    501: {"model": ErrorResponse, "description": "`export_not_ready`: Excel is not available yet."},
}

From = Annotated[dt.date | None, Query(alias="from", description="IST date, inclusive. Default: 30 days before `to`.")]
To = Annotated[dt.date | None, Query(description="IST date, inclusive. Default: today.")]
Territory = Annotated[str | None, Query(description="Up to 20 territory ids, comma-separated; in or under any.")]
Owner = Annotated[str | None, Query(pattern=UUID_RE, description="One person.")]
Format = Annotated[Literal["json", "xlsx"], Query(alias="format", description="xlsx answers 501 until exports land.")]


def _filters(start: dt.date | None, end: dt.date | None, territory_id: str | None,
             owner_id: str | None) -> service.Filters:
    return service.Filters(start=start, end=end, territory_id=territory_id, owner_id=owner_id)


def _answer(data: dict[str, Any], fmt: str) -> JSONResponse:
    if fmt == "xlsx":
        return JSONResponse({"error": {"code": "export_not_ready",
                                       "message": "Excel download is not available yet."}}, status_code=501)
    return JSONResponse({"data": data})


@router.get("/lead-conversion", responses=_ERRORS)
async def lead_conversion(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                          territory_id: Territory = None, owner_id: Owner = None, fmt: Format = "json",
                          group_by: Literal["source", "owner", "territory"] = "source") -> JSONResponse:
    """Leads created in the window, per source, owner or territory: how many reached
    each stage, won, lost and are open, and the conversion rate."""
    return _answer(await service.lead_conversion(db, caller, _filters(from_, to, territory_id, owner_id), group_by), fmt)


@router.get("/salesperson-performance", responses=_ERRORS)
async def salesperson_performance(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                                  territory_id: Territory = None, owner_id: Owner = None,
                                  fmt: Format = "json") -> JSONResponse:
    """Per person: leads created and won, quotations sent, orders, visits, tasks done
    and overdue. A figure you may not see is null. Staff only."""
    return _answer(await service.salesperson_performance(db, caller, _filters(from_, to, territory_id, owner_id)), fmt)


@router.get("/lost-leads", responses=_ERRORS)
async def lost_leads(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                     territory_id: Territory = None, owner_id: Owner = None, fmt: Format = "json",
                     group_by: Literal["reason", "owner"] = "reason") -> JSONResponse:
    """Leads lost in the window, per reason or owner, with the days to loss and the
    stage they dropped off at."""
    return _answer(await service.lost_leads(db, caller, _filters(from_, to, territory_id, owner_id), group_by), fmt)


@router.get("/follow-ups", responses=_ERRORS)
async def follow_ups(db: DbSession, caller: CallerDep, owner_id: Owner = None, fmt: Format = "json") -> JSONResponse:
    """Open tasks per person, as of now: due today and overdue by age. Staff only."""
    return _answer(await service.follow_ups(db, caller, _filters(None, None, None, owner_id)), fmt)


@router.get("/dealer-performance", responses=_ERRORS)
async def dealer_performance(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                             territory_id: Territory = None, fmt: Format = "json") -> JSONResponse:
    """Per dealer: orders and value in the window, value shipped, leads assigned, and
    the all-time received and balance."""
    return _answer(await service.dealer_performance(db, caller, _filters(from_, to, territory_id, None)), fmt)


@router.get("/territory-performance", responses=_ERRORS)
async def territory_performance(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                                territory_id: Territory = None, fmt: Format = "json",
                                level: Literal["district", "taluka"] = "district") -> JSONResponse:
    """Per district or taluka: leads, won, conversion, orders and value. Staff only."""
    return _answer(await service.territory_performance(db, caller, _filters(from_, to, territory_id, None), level), fmt)


@router.get("/complaints", responses=_ERRORS)
async def complaints(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                     territory_id: Territory = None, owner_id: Owner = None, fmt: Format = "json",
                     group_by: Literal["type", "status", "severity"] = "type") -> JSONResponse:
    """Complaints first submitted in the window: resolved, within SLA, response
    breaches, and refunds paid."""
    return _answer(await service.complaints(db, caller, _filters(from_, to, territory_id, owner_id), group_by), fmt)


@leads.get("/{lead_id}/360", responses=_ERRORS,
           dependencies=[Depends(require("leads", "view")), Depends(require("reports", "view"))])
async def lead_360(lead_id: Annotated[str, Path(pattern=UUID_RE)], db: DbSession, caller: CallerDep) -> JSONResponse:
    """The lead with summary tiles and other leads on the same mobile. The timeline is
    `GET /leads/{id}/timeline`. Needs `leads.view` and `reports.view`. A tile you
    may not see is null."""
    return JSONResponse({"data": await service.lead_360(db, caller, lead_id)})
