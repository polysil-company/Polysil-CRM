"""Reports (FS-024) and the 360° lead view.

Live aggregates scoped as the lists are. A figure the caller has no right to is
null, never 0; a report whose base module the caller lacks is 403. `format=xlsx`
returns the same rows as a workbook through the list exports' writer (GAP-220)."""

# ruff: noqa: E501  (route signatures and their descriptions)

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse

from api.authz.predicate import Caller
from api.deps import CallerDep, DbSession, require
from api.routers.exporting import XLSX_RESPONSE
from api.schemas.auth import ErrorResponse
from api.schemas.leads import UUID_RE
from api.services import exports, report_exports
from api.services import reports as service

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require("reports", "view"))])
leads = APIRouter(prefix="/leads", tags=["reports"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "No reports.view, or not the report's base module, or a dealer on a staff report."},
    422: {"model": ErrorResponse, "description": "A bad window or filter."},
    200: {"description": "The report as JSON; with `format=xlsx`, the same rows as an Excel attachment.",
          "content": {"application/json": {}, **XLSX_RESPONSE[200]["content"]}},
}

From = Annotated[dt.date | None, Query(alias="from", description="IST date, inclusive. Default: 30 days before `to`.")]
To = Annotated[dt.date | None, Query(description="IST date, inclusive. Default: today.")]
Territory = Annotated[str | None, Query(description="Up to 20 territory ids, comma-separated; in or under any.")]
Owner = Annotated[str | None, Query(pattern=UUID_RE, description="One person.")]
Format = Annotated[Literal["json", "xlsx"], Query(alias="format", description="`xlsx`: the same rows as an Excel file, with a Total line and a note when only the first 1,000 rows were kept. A figure you may not see is an empty cell.")]


async def _filters(db: DbSession, start: dt.date | None, end: dt.date | None, territory_id: str | None,
                   owner_id: str | None) -> service.Filters:
    return await service.Filters(start=start, end=end, territory_id=territory_id,
                                 owner_id=owner_id).load_sale_mode(db)


async def _answer(data: dict[str, Any], fmt: str, report: str, caller: Caller) -> Response:
    if fmt != "xlsx":
        return JSONResponse({"data": data})
    rows = report_exports.rows(report, data)
    body = await asyncio.to_thread(exports.workbook, report.replace("-", " ").capitalize(),
                                   report_exports.columns(report, data), rows)
    exports.log_export(caller.user_id, f"report-{report}", data.get("filters") or {},
                       len(data.get("rows") or []))
    return Response(content=body, media_type=exports.XLSX_TYPE, headers={
        "Content-Disposition": f'attachment; filename="{exports.filename(f"report-{report}")}"'})


@router.get("/lead-conversion", responses=_ERRORS)
async def lead_conversion(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                          territory_id: Territory = None, owner_id: Owner = None, fmt: Format = "json",
                          group_by: Literal["source", "owner", "territory"] = "source") -> Response:
    """Leads created in the window, per source, owner or territory: how many reached
    each stage, won, lost and are open, and the conversion rate."""
    return await _answer(await service.lead_conversion(db, caller, await _filters(db, from_, to, territory_id, owner_id), group_by), fmt, "lead-conversion", caller)


@router.get("/salesperson-performance", responses=_ERRORS)
async def salesperson_performance(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                                  territory_id: Territory = None, owner_id: Owner = None,
                                  fmt: Format = "json") -> Response:
    """Per person: leads created and won, quotations sent, orders, visits, tasks done
    and overdue. A figure you may not see is null. Staff only."""
    return await _answer(await service.salesperson_performance(db, caller, await _filters(db, from_, to, territory_id, owner_id)), fmt, "salesperson-performance", caller)


@router.get("/lost-leads", responses=_ERRORS)
async def lost_leads(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                     territory_id: Territory = None, owner_id: Owner = None, fmt: Format = "json",
                     group_by: Literal["reason", "owner"] = "reason") -> Response:
    """Leads lost in the window, per reason or owner, with the days to loss and the
    stage they dropped off at."""
    return await _answer(await service.lost_leads(db, caller, await _filters(db, from_, to, territory_id, owner_id), group_by), fmt, "lost-leads", caller)


@router.get("/follow-ups", responses=_ERRORS)
async def follow_ups(db: DbSession, caller: CallerDep, owner_id: Owner = None, fmt: Format = "json") -> Response:
    """Open tasks per person, as of now: due today and overdue by age. Staff only."""
    return await _answer(await service.follow_ups(db, caller, await _filters(db, None, None, None, owner_id)), fmt, "follow-ups", caller)


@router.get("/dealer-performance", responses=_ERRORS)
async def dealer_performance(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                             territory_id: Territory = None, fmt: Format = "json") -> Response:
    """Per dealer: orders and value in the window, value shipped, leads assigned, and
    the all-time received and balance."""
    return await _answer(await service.dealer_performance(db, caller, await _filters(db, from_, to, territory_id, None)), fmt, "dealer-performance", caller)


@router.get("/campaign-performance", responses=_ERRORS)
async def campaign_performance(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                               territory_id: Territory = None, owner_id: Owner = None,
                               fmt: Format = "json") -> Response:
    """Per campaign: the leads you can see created in the window that name it, how far
    they got, their sales (whenever sold, under the company's sale setting), and cost
    per lead and per win. A campaign whose dates overlap the window shows with zeros
    (no end date is one day); with `owner_id`, only campaigns with leads show.
    Cost figures need campaigns.view; sales need sales_orders. Staff only."""
    return await _answer(await service.campaign_performance(db, caller, await _filters(db, from_, to, territory_id, owner_id)), fmt, "campaign-performance", caller)


@router.get("/territory-performance", responses=_ERRORS)
async def territory_performance(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                                territory_id: Territory = None, fmt: Format = "json",
                                level: Literal["district", "taluka"] = "district") -> Response:
    """Per district or taluka: leads, won, conversion, orders and value. Staff only."""
    return await _answer(await service.territory_performance(db, caller, await _filters(db, from_, to, territory_id, None), level), fmt, "territory-performance", caller)


@router.get("/complaints", responses=_ERRORS)
async def complaints(db: DbSession, caller: CallerDep, from_: From = None, to: To = None,
                     territory_id: Territory = None, owner_id: Owner = None, fmt: Format = "json",
                     group_by: Literal["type", "status", "severity"] = "type") -> Response:
    """Complaints first submitted in the window: resolved, within SLA, response
    breaches, and refunds paid."""
    return await _answer(await service.complaints(db, caller, await _filters(db, from_, to, territory_id, owner_id), group_by), fmt, "complaints", caller)


@leads.get("/{lead_id}/360", responses=_ERRORS,
           dependencies=[Depends(require("leads", "view")), Depends(require("reports", "view"))])
async def lead_360(lead_id: Annotated[str, Path(pattern=UUID_RE)], db: DbSession, caller: CallerDep) -> Response:
    """The lead with summary tiles and other leads on the same mobile. The timeline is
    `GET /leads/{id}/timeline`. Needs `leads.view` and `reports.view`. A tile you
    may not see is null."""
    return JSONResponse({"data": await service.lead_360(db, caller, lead_id)})
