"""Offices, territories and partners (FS-006 section 4).

Thin on purpose: parse, gate, delegate, shape. Reads on offices and territories
need only a session; their writes need `masters.edit`. Partners are read and
written under the partners permissions and scoped by the database underneath.

**The docstrings below become prose in the generated API docs** (CLAUDE.md 2.3).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import Outcome, payload_digest, run_idempotent
from api.routers.exporting import XLSX_RESPONSE, export, filters_of
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.masters import (
    OrgUnit,
    OrgUnitCreate,
    OrgUnitPage,
    OrgUnitPatch,
    Partner,
    PartnerCreate,
    PartnerPage,
    PartnerPatch,
    PartnerStateChange,
    Territory,
    TerritoryCreate,
    TerritoryPage,
    TerritoryPatch,
)
from api.services import exports
from api.services import masters as service

org_units = APIRouter(prefix="/org-units", tags=["org-units"])
territories = APIRouter(prefix="/territories", tags=["territories"])
partners = APIRouter(prefix="/partners", tags=["partners"])

ItemId = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "The action is not in your permissions."},
    422: {"model": ErrorResponse, "description": "A field failed validation; see `fields`."},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    404: {"model": ErrorResponse, "description": "No such row in your scope."},
    409: {"model": ErrorResponse, "description": "The key was used for a different body."},
}
_MASTERS = [Depends(require("masters", "edit"))]


def _reply(outcome: Outcome) -> JSONResponse:
    return JSONResponse(outcome.body, status_code=outcome.status_code)


# ── offices ──────────────────────────────────────────────────────────────────

@org_units.get("", response_model=OrgUnitPage, responses=_ERRORS)
async def list_org_units(
    db: DbSession, _: Claims,
    q: Annotated[str | None, Query(description="Name substring.")] = None,
    parent_id: Annotated[str | None, Query(pattern=UUID_RE,
                                            description="Children of this office.")] = None,
    is_open: Annotated[bool | None, Query(
        description="true for open offices only, false for closed.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
) -> OrgUnitPage:
    """The office tree, newest first, with active user counts. Readable by anyone
    signed in. Keyset-paged: pass `meta.next_cursor` back as `cursor`."""
    return await service.list_org_units(db, q=q, parent_id=parent_id, is_open=is_open,
                                        limit=limit, cursor=cursor)


@org_units.get("/{item_id}", response_model=Envelope[OrgUnit],
               responses={**_ERRORS, 404: _MUTATION_ERRORS[404]})
async def get_org_unit(item_id: ItemId, db: DbSession, _: Claims) -> Envelope[OrgUnit]:
    """One office: its parent, the territory it covers, whether it is open, and how
    many active people are anchored on it."""
    return Envelope(data=await service.get_org_unit(db, item_id))


@org_units.post("", response_model=Envelope[OrgUnit], status_code=status.HTTP_201_CREATED,
                responses=_MUTATION_ERRORS, dependencies=_MASTERS)
async def create_org_unit(body: OrgUnitCreate, db: DbSession, caller: CallerDep, claims: Claims,
                          idem: IdemKey) -> JSONResponse:
    """Add an office under an open parent (or as a root). The name must be unique
    among its siblings. **`Idempotency-Key` is required.**"""
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        row = await service.create_org_unit(db, caller, body)
        return status.HTTP_201_CREATED, {"data": row.model_dump(mode="json")}

    return _reply(await run_idempotent(db, key=idem, user_id=claims.sub,
                                       route="POST /api/v1/org-units",
                                       payload_hash=payload_hash, work=work))


@org_units.patch("/{item_id}", response_model=Envelope[OrgUnit], responses=_MUTATION_ERRORS,
                 dependencies=_MASTERS)
async def patch_org_unit(item_id: ItemId, body: OrgUnitPatch, db: DbSession, caller: CallerDep,
                         claims: Claims, idem: IdemKey) -> JSONResponse:
    """Rename an office, move it under another (`parent_id: null` makes it a root),
    or change the territory it covers. A move takes effect for scoping at once; a
    move under one of its own descendants is `422 fields.parent_id`."""
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        row = await service.patch_org_unit(db, caller, item_id, body)
        return status.HTTP_200_OK, {"data": row.model_dump(mode="json")}

    return _reply(await run_idempotent(db, key=idem, user_id=claims.sub,
                                       route=f"PATCH /api/v1/org-units/{item_id}",
                                       payload_hash=payload_hash, work=work))


@org_units.post("/{item_id}/close", response_model=Envelope[OrgUnit], responses=_MUTATION_ERRORS,
                dependencies=_MASTERS)
async def close_org_unit(item_id: ItemId, db: DbSession, caller: CallerDep, claims: Claims,
                         idem: IdemKey) -> JSONResponse:
    """Close an office. Refused (`422 fields.id`) while any active person is anchored
    on it: move or deactivate them first. Closing again is a no-op."""
    async def work() -> tuple[int, dict]:
        row = await service.close_org_unit(db, caller, item_id)
        return status.HTTP_200_OK, {"data": row.model_dump(mode="json")}

    return _reply(await run_idempotent(db, key=idem, user_id=claims.sub,
                                       route=f"POST /api/v1/org-units/{item_id}/close",
                                       payload_hash=payload_digest({}), work=work))


@org_units.post("/{item_id}/reopen", response_model=Envelope[OrgUnit],
                responses=_MUTATION_ERRORS, dependencies=_MASTERS)
async def reopen_org_unit(item_id: ItemId, db: DbSession, caller: CallerDep, claims: Claims,
                          idem: IdemKey) -> JSONResponse:
    """Reopen a closed office. It had no active people when it closed, so nothing
    else is restored."""
    async def work() -> tuple[int, dict]:
        row = await service.reopen_org_unit(db, caller, item_id)
        return status.HTTP_200_OK, {"data": row.model_dump(mode="json")}

    return _reply(await run_idempotent(db, key=idem, user_id=claims.sub,
                                       route=f"POST /api/v1/org-units/{item_id}/reopen",
                                       payload_hash=payload_digest({}), work=work))


# ── territories ──────────────────────────────────────────────────────────────

@territories.get("", response_model=TerritoryPage, responses=_ERRORS)
async def list_territories(
    db: DbSession, _: Claims,
    level: Annotated[str | None, Query(description="state, district, taluka or village.")] = None,
    parent_id: Annotated[str | None, Query(pattern=UUID_RE,
                                            description="Children of this territory.")] = None,
    q: Annotated[str | None, Query(description="Name or code substring.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
) -> TerritoryPage:
    """The territory tree for administration, newest first. The new-lead form keeps
    using `GET /lookups/territories`; this list carries `code_locked`."""
    return await service.list_territories(db, level=level, parent_id=parent_id, q=q,
                                          limit=limit, cursor=cursor)


@territories.get("/{item_id}", response_model=Envelope[Territory],
                 responses={**_ERRORS, 404: _MUTATION_ERRORS[404]})
async def get_territory(item_id: ItemId, db: DbSession, _: Claims) -> Envelope[Territory]:
    """One territory, with its parent and whether its code is locked."""
    return Envelope(data=await service.get_territory(db, item_id))


@territories.post("", response_model=Envelope[Territory], status_code=status.HTTP_201_CREATED,
                  responses=_MUTATION_ERRORS, dependencies=_MASTERS)
async def create_territory(body: TerritoryCreate, db: DbSession, caller: CallerDep,
                           claims: Claims, idem: IdemKey) -> JSONResponse:
    """Add a state (no parent), or a district, taluka or village under the level
    above. Names are unique among siblings and codes unique per level. A state
    without a code cannot number leads. **`Idempotency-Key` is required.**"""
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        row = await service.create_territory(db, caller, body)
        return status.HTTP_201_CREATED, {"data": row.model_dump(mode="json")}

    return _reply(await run_idempotent(db, key=idem, user_id=claims.sub,
                                       route="POST /api/v1/territories",
                                       payload_hash=payload_hash, work=work))


@territories.patch("/{item_id}", response_model=Envelope[Territory], responses=_MUTATION_ERRORS,
                   dependencies=_MASTERS)
async def patch_territory(item_id: ItemId, body: TerritoryPatch, db: DbSession,
                          caller: CallerDep, claims: Claims, idem: IdemKey) -> JSONResponse:
    """Rename a territory or set its code. A state's code is refused once a lead
    has been numbered under it (`422 fields.code`), because the inquiry numbers
    already carry it."""
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        row = await service.patch_territory(db, caller, item_id, body)
        return status.HTTP_200_OK, {"data": row.model_dump(mode="json")}

    return _reply(await run_idempotent(db, key=idem, user_id=claims.sub,
                                       route=f"PATCH /api/v1/territories/{item_id}",
                                       payload_hash=payload_hash, work=work))


# ── partners ─────────────────────────────────────────────────────────────────

@partners.get("", response_model=PartnerPage, responses=_ERRORS,
              dependencies=[Depends(require("partners", "view"))])
async def list_partners(
    db: DbSession, caller: CallerDep,
    q: Annotated[str | None, Query(description="Name, code or contact person substring.")] = None,
    partner_type: Annotated[str | None, Query(
        description="distributor, dealer or sub_dealer.")] = None,
    parent_id: Annotated[str | None, Query(pattern=UUID_RE,
                                            description="Children of this partner.")] = None,
    is_active: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
) -> PartnerPage:
    """The partners you can see, newest first: an admin all of them, a manager the
    ones in its territories, a distributor or dealer its own subtree. An empty list
    means nothing in your scope; 403 means you may not view partners at all."""
    return await service.list_partners(db, caller, q=q, partner_type=partner_type,
                                       parent_id=parent_id, is_active=is_active, limit=limit,
                                       cursor=cursor)


@partners.get("/export", response_class=Response, responses={**_ERRORS, **XLSX_RESPONSE},
              dependencies=[Depends(require("partners", "view"))])
async def export_partners(
    db: DbSession, caller: CallerDep,
    filters: Annotated[dict[str, Any], Depends(filters_of(list_partners))],
) -> Response:
    """Download the partner list as an Excel file, with the same filters as the list.

    The file holds exactly the rows the list would show for these filters, across
    every page, and nothing outside your scope. Call it with `fetch` and the bearer
    token, then save the blob. More than 5,000 rows is `422 export_too_large`:
    narrow the filters. An empty list gives a file with the header row only.
    """
    return await export(list_partners, stem="partners", title="Partners", columns=exports.PARTNERS,
                        user_id=caller.user_id, filters=filters, db=db, caller=caller)


@partners.get("/{item_id}", response_model=Envelope[Partner],
              responses={**_ERRORS, 404: _MUTATION_ERRORS[404]},
              dependencies=[Depends(require("partners", "view"))])
async def get_partner(item_id: ItemId, db: DbSession, caller: CallerDep) -> Envelope[Partner]:
    """One partner. `credit_limit` and `payment_terms_days` are shown to staff and
    null for a partner reading its own subtree."""
    return Envelope(data=await service.get_partner(db, caller, item_id))


@partners.post("", response_model=Envelope[Partner], status_code=status.HTTP_201_CREATED,
               responses=_MUTATION_ERRORS, dependencies=[Depends(require("partners", "create"))])
async def create_partner(body: PartnerCreate, db: DbSession, caller: CallerDep, claims: Claims,
                         idem: IdemKey) -> JSONResponse:
    """Add a partner. Staff add a distributor at the root or a dealer or sub-dealer
    under the type above; a distributor or dealer on the portal adds the next type
    down under itself. `price_tier` is set to the type. The code must be unique.
    **`Idempotency-Key` is required.**"""
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        row = await service.create_partner(db, caller, body)
        return status.HTTP_201_CREATED, {"data": row.model_dump(mode="json")}

    return _reply(await run_idempotent(db, key=idem, user_id=claims.sub,
                                       route="POST /api/v1/partners",
                                       payload_hash=payload_hash, work=work))


@partners.patch("/{item_id}", response_model=Envelope[Partner], responses=_MUTATION_ERRORS,
                dependencies=[Depends(require("partners", "edit"))])
async def patch_partner(item_id: ItemId, body: PartnerPatch, db: DbSession, caller: CallerDep,
                        claims: Claims, idem: IdemKey) -> JSONResponse:
    """Correct a partner. Send only what changes. A partner editing its own subtree
    may change name, contact name, mobile, email, address, GSTIN and PAN; credit
    terms, the territory and the type are staff-only or never change."""
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        row = await service.patch_partner(db, caller, item_id, body)
        return status.HTTP_200_OK, {"data": row.model_dump(mode="json")}

    return _reply(await run_idempotent(db, key=idem, user_id=claims.sub,
                                       route=f"PATCH /api/v1/partners/{item_id}",
                                       payload_hash=payload_hash, work=work))


@partners.post("/{item_id}/close", response_model=Envelope[PartnerStateChange],
               responses=_MUTATION_ERRORS, dependencies=[Depends(require("partners", "edit"))])
async def close_partner(item_id: ItemId, db: DbSession, caller: CallerDep, claims: Claims,
                        idem: IdemKey) -> JSONResponse:
    """Close a partner: it becomes inactive and every user anchored on it is
    signed out and deactivated. Staff only; a partner cannot close itself."""
    async def work() -> tuple[int, dict]:
        row = await service.close_partner(db, caller, item_id)
        return status.HTTP_200_OK, {"data": row.model_dump(mode="json")}

    return _reply(await run_idempotent(db, key=idem, user_id=claims.sub,
                                       route=f"POST /api/v1/partners/{item_id}/close",
                                       payload_hash=payload_digest({}), work=work))


@partners.post("/{item_id}/reopen", response_model=Envelope[PartnerStateChange],
               responses=_MUTATION_ERRORS, dependencies=[Depends(require("partners", "edit"))])
async def reopen_partner(item_id: ItemId, db: DbSession, caller: CallerDep, claims: Claims,
                         idem: IdemKey) -> JSONResponse:
    """Reopen a closed partner. Its people stay inactive; `users_inactive` says how
    many, and each is reactivated through `PATCH /users/{id}`."""
    async def work() -> tuple[int, dict]:
        row = await service.reopen_partner(db, caller, item_id)
        return status.HTTP_200_OK, {"data": row.model_dump(mode="json")}

    return _reply(await run_idempotent(db, key=idem, user_id=claims.sub,
                                       route=f"POST /api/v1/partners/{item_id}/reopen",
                                       payload_hash=payload_digest({}), work=work))
