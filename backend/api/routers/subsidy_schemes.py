# ruff: noqa: E501  (route signatures)

"""Subsidy schemes (FS-039): setting up another state's subsidy scheme.

**The docstrings below become prose in `docs/api/subsidy-schemes.md`** (CLAUDE.md 2.3).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse

from api.deps import Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.subsidy_schemes import (
    LeadScheme,
    SchemeDetail,
    SchemeRow,
    SchemeUpdate,
    StageOut,
    StageRename,
    SubsidySchemeCreate,
)
from api.services import subsidy_schemes as service

router = APIRouter(prefix="/subsidy-schemes", tags=["subsidy schemes"])

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse,
          "description": "`idempotency_key_required`: a write sent without an Idempotency-Key."},
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not permitted."},
    404: {"model": ErrorResponse, "description": "No such scheme, stage or visible lead."},
    409: {"model": ErrorResponse, "description": (
        "`code_taken`, `state_has_scheme`, `unlinked_scheme_exists` (an active scheme has no "
        "state: link it first), `state_fixed`.")},
    422: {"model": ErrorResponse, "description": (
        "A field; `no_scheme_for_state`, `territory_without_state_code` on the lead's scheme.")},
}
_EDIT = [Depends(require("masters", "edit"))]
CodePath = Annotated[str, Path(max_length=20)]


async def _idempotent(db: Any, idem: str, claims: Any, route: str, body: Any, status: int,
                      work: Any) -> Response:
    async def run() -> tuple[int, dict[str, Any]]:
        out = await work()
        return status, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=payload_digest(body.model_dump(mode="json")), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("", response_model=Envelope[list[SchemeRow]], responses=_ERRORS)
async def list_schemes(db: DbSession, _: Claims) -> Envelope[list[SchemeRow]]:
    """Every subsidy scheme, active first, with whether it can calculate today. A
    scheme with `state: null` is the legacy one (GGRC before it is linked to Gujarat);
    while one exists, no other state's scheme can be added."""
    return Envelope(data=await service.list_schemes(db))


@router.get("/for-lead/{lead_id}", response_model=Envelope[LeadScheme], responses=_ERRORS)
async def for_lead(lead_id: Annotated[str, Path(pattern=r"^[0-9a-fA-F-]{36}$")], db: DbSession,
                   _: Claims) -> Envelope[LeadScheme]:
    """The scheme a subsidy application on this lead uses: the active scheme of the
    lead's state. Send its `code` as `scheme` in the calculation preview and in
    `POST /subsidy-applications`; another scheme is refused there."""
    return Envelope(data=await service.scheme_for_lead(db, lead_id))


@router.get("/{code}", response_model=Envelope[SchemeDetail], responses=_ERRORS)
async def get_scheme(code: CodePath, db: DbSession, _: Claims,
                     on: Annotated[dt.date | None, Query(description="Readiness on this date; today (IST) by default.")] = None
                     ) -> Envelope[SchemeDetail]:
    """One scheme with its readiness panel: per system, what a calculation would refuse
    on, in the order it would refuse. Each item names the masters table to fill
    (FS-009a revisions and matrices). And the scheme's application stages."""
    return Envelope(data=await service.get_scheme(db, code, on))


@router.post("", status_code=201, response_model=Envelope[SchemeDetail], responses=_ERRORS, dependencies=_EDIT)
async def create_scheme(body: SubsidySchemeCreate, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Add a state's subsidy scheme. The template's calculation settings and application
    stages are copied; no figure is. The new scheme refuses to calculate until its own
    figures are entered, and the detail lists what is missing."""
    return await _idempotent(db, idem, claims, "POST /api/v1/subsidy-schemes", body, 201,
                             lambda: service.create_scheme(db, body))


@router.patch("/{code}", response_model=Envelope[SchemeDetail], responses=_ERRORS, dependencies=_EDIT)
async def update_scheme(code: CodePath, body: SchemeUpdate, db: DbSession, claims: Claims,
                        idem: IdemKey) -> Response:
    """Rename a scheme, switch it off or on, or link a scheme that has no state to its
    state (once). Switching off stops new calculations and applications; existing
    applications carry on through their stages."""
    return await _idempotent(db, idem, claims, f"PATCH /api/v1/subsidy-schemes/{code}", body, 200,
                             lambda: service.update_scheme(db, code, body))


@router.patch("/{code}/stages/{stage_code}", response_model=Envelope[StageOut], responses=_ERRORS,
              dependencies=_EDIT)
async def rename_stage(code: CodePath, stage_code: Annotated[str, Path(max_length=60)], body: StageRename,
                       db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Rename one of the scheme's application stages. Its code, order and fields stay."""
    return await _idempotent(db, idem, claims, f"PATCH /api/v1/subsidy-schemes/{code}/stages/{stage_code}",
                             body, 200, lambda: service.rename_stage(db, code, stage_code, body))
