# ruff: noqa: E501  (route signatures)

"""Dealer commission and TOD, subsidy stage 18 (FS-033).

**The docstrings below become prose in `docs/api/commission.md`** (CLAUDE.md 2.3).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import CallerDep, Claims, DbSession, IdemKey, require, require_any
from api.idempotency import payload_digest, run_idempotent
from api.routers.exporting import XLSX_RESPONSE, export, filters_of
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.commission import (
    Commission,
    CommissionIn,
    CommissionPage,
    Decision,
    Payment,
    Preview,
    Rate,
    RateIn,
)
from api.schemas.leads import UUID_RE
from api.services import commission as service
from api.services import exports

on_application = APIRouter(prefix="/subsidy-applications", tags=["dealer commission"])
router = APIRouter(prefix="/dealer-commissions", tags=["dealer commission"])
rates = APIRouter(prefix="/commission-rates", tags=["dealer commission"])

Id = Annotated[str, Path(pattern=UUID_RE)]
_READ = Depends(require_any(("subsidy", "view"), ("payments", "view")))

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not permitted, or `own_decision`."},
    404: {"model": ErrorResponse, "description": "Not found in your scope."},
    409: {"model": ErrorResponse, "description": "`not_closed`, `commission_exists`, `status_changed`."},
    422: {"model": ErrorResponse, "description": "`no_partner`, `no_rate`, `remark_required`, a field."},
}


async def _idem(db: Any, claims: Any, idem: str, route: str, body: BaseModel | None,
                work: Callable[[], Awaitable[tuple[int, dict[str, Any]]]]) -> Response:
    digest = payload_digest(body.model_dump(mode="json", exclude_unset=True) if body else {})
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=digest, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@on_application.get("/{app_id}/commission/preview", response_model=Envelope[Preview], responses=_ERRORS,
                    dependencies=[Depends(require("subsidy", "view"))])
async def preview(app_id: Id, db: DbSession) -> Envelope[Preview]:
    """Stage 18 before anything is typed: the cost before GST and the installation from
    the stored calculation, and the rate in force on the full-FP date.
    `409 not_closed` before full FP; `422 no_partner` without a dealer.
    `commission_pct` is null when no rate is in force."""
    return Envelope(data=await service.preview(db, app_id))


@on_application.get("/{app_id}/commission", response_model=Envelope[Commission], responses=_ERRORS,
                    dependencies=[Depends(require("subsidy", "view"))])
async def live(app_id: Id, db: DbSession) -> Envelope[Commission]:
    """The application's live commission, or `404` if none is recorded."""
    return Envelope(data=await service.live_for(db, app_id))


@on_application.post("/{app_id}/commission", status_code=201, response_model=Envelope[Commission],
                     responses=_ERRORS, dependencies=[Depends(require("subsidy", "edit"))])
async def record(app_id: Id, body: CommissionIn, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Record stage 18. Send the fittings (and the installation, if it differs from the
    calculation); the server works out the base, both amounts and the total.
    Recording again while it is `calculated` or `returned` replaces the figures and
    clears the previous decision. `409 commission_exists` once approved or paid."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 201, {"data": (await service.record(db, app_id, body)).model_dump(mode="json")}
    return await _idem(db, claims, idem, f"POST /api/v1/subsidy-applications/{app_id}/commission", body, work)


@router.get("", response_model=CommissionPage, responses=_ERRORS, dependencies=[_READ])
async def list_commissions(
    db: DbSession,
    status_: Annotated[str | None, Query(alias="status", description="Comma-separated: calculated,approved.")] = None,
    partner_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    paid_from: Annotated[str | None, Query(description="ISO date.")] = None,
    paid_to: Annotated[str | None, Query(description="ISO date, inclusive.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> CommissionPage:
    """The commission report: every commission on an application you can see, newest
    first. `?status=calculated` is Accounts' queue to approve; `?status=approved` the
    queue to pay."""
    return await service.list_commissions(db, status=status_, partner_id=partner_id, paid_from=paid_from,
                                          paid_to=paid_to, cursor=cursor, limit=limit)


@router.get("/export", response_class=Response, responses={**_ERRORS, **XLSX_RESPONSE}, dependencies=[_READ])
async def export_commissions(db: DbSession, caller: CallerDep,
                             filters: Annotated[dict[str, Any], Depends(filters_of(list_commissions))]) -> Response:
    """The commission report as Excel, with the same filters (FS-030)."""
    return await export(list_commissions, stem="dealer-commissions", title="Dealer commissions",
                        columns=exports.DEALER_COMMISSIONS, user_id=caller.user_id, filters=filters, db=db)


@router.get("/{commission_id}", response_model=Envelope[Commission], responses=_ERRORS, dependencies=[_READ])
async def get_commission(commission_id: Id, db: DbSession) -> Envelope[Commission]:
    """One commission."""
    return Envelope(data=await service.get(db, commission_id))


def _decision(action: str, perm: tuple[str, str], doc: str) -> Callable[..., Any]:
    async def endpoint(commission_id: Id, body: Decision, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
        async def work() -> tuple[int, dict[str, Any]]:
            out = await service.decide(db, commission_id, action, body.remark)
            return 200, {"data": out.model_dump(mode="json")}
        return await _idem(db, claims, idem, f"POST /api/v1/dealer-commissions/{commission_id}/{action}", body, work)
    endpoint.__doc__ = doc
    endpoint.__name__ = f"{action}_commission"
    router.post(f"/{{commission_id}}/{action}", response_model=Envelope[Commission], responses=_ERRORS,
                dependencies=[Depends(require(*perm))])(endpoint)
    return endpoint


_decision("approve", ("payments", "approve"),
          "Accounts approves a calculated commission. Not by anyone who recorded it: `403 own_decision`.")
_decision("return", ("payments", "approve"),
          "Accounts sends it back with a remark; the co-ordinator records it again.")
_decision("cancel", ("subsidy", "view"),
          "Cancel with a remark: the co-ordinator while calculated or returned, Accounts once approved. "
          "A new one may then be recorded.")


@router.post("/{commission_id}/pay", response_model=Envelope[Commission], responses=_ERRORS,
             dependencies=[Depends(require("payments", "edit"))])
async def pay(commission_id: Id, body: Payment, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Accounts marks an approved commission paid, with the date and the reference.
    Final. Only company-wide payments roles (Accounts, admin)."""
    async def work() -> tuple[int, dict[str, Any]]:
        out = await service.decide(db, commission_id, "pay", None, body.paid_on, body.payment_reference)
        return 200, {"data": out.model_dump(mode="json")}
    return await _idem(db, claims, idem, f"POST /api/v1/dealer-commissions/{commission_id}/pay", body, work)


@rates.get("", response_model=Envelope[list[Rate]], responses=_ERRORS,
           dependencies=[Depends(require_any(("subsidy", "view"), ("payments", "view"), ("masters", "edit")))])
async def list_rates(db: DbSession, scheme: Annotated[str, Query()] = "GGRC") -> Envelope[list[Rate]]:
    """Every commission rate of a scheme, newest first. The one used is the most
    specific in force on the full-FP date: one partner, then partner type, then
    system, then the scheme."""
    return Envelope(data=await service.list_rates(db, scheme))


@rates.post("", status_code=201, response_model=Envelope[Rate], responses=_ERRORS,
            dependencies=[Depends(require("masters", "edit"))])
async def add_rate(body: RateIn, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey) -> Response:
    """Add a rate from a date. Rates are never edited; a later one supersedes, a 0% one retires."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 201, {"data": (await service.add_rate(db, caller.user_id, body)).model_dump(mode="json")}
    return await _idem(db, claims, idem, "POST /api/v1/commission-rates", body, work)
