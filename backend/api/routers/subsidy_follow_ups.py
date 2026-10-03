# ruff: noqa: E501  (route signatures)

"""Subsidy follow-ups (FS-009a): ageing, the stage and supply reports, masters revisions.

**The docstrings below become prose in `docs/api/subsidy-reports.md`** (CLAUDE.md 2.3).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.routers.exporting import XLSX_RESPONSE, export, filters_of
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.subsidy_follow_ups import (
    AgePage,
    MatrixRevision,
    Revision,
    RevisionResult,
    StagePage,
    SupplyPage,
)
from api.services import exports
from api.services import subsidy_follow_ups as service

reports = APIRouter(prefix="/subsidy-reports", tags=["subsidy reports"])
masters = APIRouter(prefix="/subsidy-masters", tags=["subsidy masters"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not permitted."},
    409: {"model": ErrorResponse, "description": "`revision_on_start_date`, `later_revision_exists`."},
    422: {"model": ErrorResponse, "description": "`revision_in_past`, a field."},
}
_VIEW = [Depends(require("subsidy", "view"))]
Status = Annotated[Literal["open", "full_fp_received", "cancelled"] | None, Query()]


@reports.get("/ageing", response_model=AgePage, responses=_ERRORS, dependencies=_VIEW)
async def ageing(db: DbSession, status: Status = None,
                 stage: Annotated[str | None, Query(description="A stage code.")] = None,
                 q: Annotated[str | None, Query(description="Application, registration number or farmer.")] = None,
                 limit: Annotated[int, Query(ge=1, le=100)] = 50,
                 cursor: Annotated[str | None, Query()] = None) -> AgePage:
    """The client's six ageing figures per application (Application-Process-Flow rows
    107 to 112), newest first. `days` is null until the start date is recorded; an
    interval with no end counts to today and says `running`."""
    return await service.ageing(db, status=status, stage=stage, q=q, cursor=cursor, limit=limit)


@reports.get("/ageing/export", response_class=Response, responses={**_ERRORS, **XLSX_RESPONSE}, dependencies=_VIEW)
async def ageing_export(db: DbSession, caller: CallerDep,
                        filters: Annotated[dict[str, Any], Depends(filters_of(ageing))]) -> Response:
    """The ageing view as Excel, with the same filters."""
    return await export(ageing, stem="subsidy-ageing", title="Subsidy ageing", columns=exports.SUBSIDY_AGEING,
                        user_id=caller.user_id, filters=filters, db=db)


@reports.get("/stages", response_model=StagePage, responses=_ERRORS, dependencies=_VIEW)
async def stages(db: DbSession, status: Status = "open") -> StagePage:
    """The stage dashboard ("Dashboard-Stage Wise"): applications, money and the oldest
    days in each stage, in stage order. Only stages holding an application appear."""
    return await service.stage_report(db, status)


@reports.get("/stages/export", response_class=Response, responses={**_ERRORS, **XLSX_RESPONSE}, dependencies=_VIEW)
async def stages_export(db: DbSession, caller: CallerDep,
                        filters: Annotated[dict[str, Any], Depends(filters_of(stages))]) -> Response:
    """The stage report as Excel."""
    return await export(stages, stem="subsidy-stages", title="Subsidy stages", columns=exports.SUBSIDY_STAGES,
                        user_id=caller.user_id, filters=filters, db=db)


@reports.get("/supply", response_model=SupplyPage, responses=_ERRORS, dependencies=_VIEW)
async def supply(db: DbSession, status: Status = None) -> SupplyPage:
    """Supplied and not supplied, by district ("Report State Wise, Supply-Non Supply").
    Supplied means stage 7's supply date is recorded. Cancelled applications are left out."""
    return await service.supply_report(db, status)


@reports.get("/supply/export", response_class=Response, responses={**_ERRORS, **XLSX_RESPONSE}, dependencies=_VIEW)
async def supply_export(db: DbSession, caller: CallerDep,
                        filters: Annotated[dict[str, Any], Depends(filters_of(supply))]) -> Response:
    """The supply report as Excel."""
    return await export(supply, stem="subsidy-supply", title="Subsidy supply", columns=exports.SUBSIDY_SUPPLY,
                        user_id=caller.user_id, filters=filters, db=db)


Kind = Annotated[Literal["categories", "parameters", "component-rates", "crop-spacings"], Path()]
MatrixKind = Annotated[Literal["unit-cost-matrices", "quantity-matrices"], Path()]


@masters.get("/{kind}", response_model=Envelope[list[dict[str, Any]]], responses=_ERRORS)
async def list_master(kind: Kind, db: DbSession, _: Claims, scheme: Annotated[str, Query()] = "GGRC",
                      on: Annotated[dt.date | None, Query(description="The date in force; today by default.")] = None
                      ) -> Envelope[list[dict[str, Any]]]:
    """The rows of one subsidy master in force on a date."""
    return Envelope(data=await service.list_master(db, kind, scheme, on))


@masters.post("/{kind}/revisions", status_code=201, response_model=Envelope[RevisionResult], responses=_ERRORS,
              dependencies=[Depends(require("masters", "edit"))])
async def revise(kind: Kind, body: Revision, db: DbSession, caller: CallerDep, claims: Claims,
                 idem: IdemKey) -> Response:
    """Revise rows of a subsidy master from a date (today or later). Each row closes the
    row with the same key in force on that date and starts from it; rows not sent stay.
    Refused when a row with the key already starts that day or later. Calculations
    dated before the revision keep using the old rows."""
    async def work() -> tuple[int, dict[str, Any]]:
        out = await service.revise(db, caller.user_id, kind, body)
        return 201, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=f"POST /api/v1/subsidy-masters/{kind}/revisions",
                                   payload_hash=payload_digest(body.model_dump(mode="json")), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@masters.get("/{kind}/matrices", response_model=Envelope[list[dict[str, Any]]], responses=_ERRORS)
async def list_matrices(kind: MatrixKind, db: DbSession, _: Claims, scheme: Annotated[str, Query()] = "GGRC",
                        on: Annotated[dt.date | None, Query(description="The date in force; today by default.")] = None
                        ) -> Envelope[list[dict[str, Any]]]:
    """The Jantri (unit-cost) or quantity matrices in force on a date, with every cell,
    so the admin sees what a new matrix replaces."""
    return Envelope(data=await service.list_matrices(db, kind, scheme, on))


@masters.post("/{kind}/matrices", status_code=201, response_model=Envelope[RevisionResult], responses=_ERRORS,
              dependencies=[Depends(require("masters", "edit"))])
async def revise_matrix(kind: MatrixKind, body: MatrixRevision, db: DbSession, caller: CallerDep, claims: Claims,
                        idem: IdemKey) -> Response:
    """A new Jantri (unit-cost) or quantity matrix from a date, with all its cells. The
    matrix in force ends that day; a matrix's cells are never changed."""
    async def work() -> tuple[int, dict[str, Any]]:
        out = await service.revise_matrix(db, caller.user_id, kind, body)
        return 201, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=f"POST /api/v1/subsidy-masters/{kind}/matrices",
                                   payload_hash=payload_digest(body.model_dump(mode="json")), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
