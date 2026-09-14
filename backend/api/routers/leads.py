"""The lead endpoints, and the lookups the forms read (FS-003 section 4).

Thin on purpose: parse, gate, delegate, shape. Every transaction belongs to a
dependency, every rule to the service or the database.

**The docstrings below become prose in `docs/api/leads.md`** (CLAUDE.md 2.3), the
document the frontend track builds against. They say what the endpoint is *for*.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import Lead, LeadCreate, LeadPage, LookupItem, TerritoryPick
from api.services import leads as service

router = APIRouter(prefix="/leads", tags=["leads"])
lookups = APIRouter(prefix="/lookups", tags=["lookups"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "The action is not in your permissions."},
    422: {"model": ErrorResponse, "description": "A field failed validation; see `fields`."},
}


@router.post(
    "",
    response_model=Envelope[Lead],
    status_code=status.HTTP_201_CREATED,
    responses={**_ERRORS, 400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
               409: {"model": ErrorResponse, "description": "The key was used for a different body."}},
    dependencies=[Depends(require("leads", "create"))],
)
async def create_lead(
    body: LeadCreate, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Enter a lead by hand. Staff from the CRM, a partner user from the portal.

    The server fills in the inquiry number, the stage (`new`), the owner and the
    org unit (routed from the territory, never sent), the score and priority. A
    partner user's lead is anchored on their partner and auto-assigned to a field
    officer; a staff user owns the lead they create.

    Send `mobile` in any Indian form; it is stored as `+91XXXXXXXXXX`. Money and
    the score are decimal strings.

    **`Idempotency-Key` is required.** Retrying with the same key and body replays
    the stored `201` and creates nothing; the same key with a different body is
    `409`. So a mobile client that never saw the reply can retry safely.
    """
    payload_hash = payload_digest(body.model_dump(mode="json"))

    async def work() -> tuple[int, dict]:
        lead = await service.create_lead(db, caller, body)
        return status.HTTP_201_CREATED, {"data": lead.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="POST /api/v1/leads",
        payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get(
    "",
    response_model=LeadPage,
    responses=_ERRORS,
    dependencies=[Depends(require("leads", "view"))],
)
async def list_leads(
    db: DbSession,
    caller: CallerDep,
    stage: Annotated[str | None, Query(
        description="Comma-separated stages. Defaults to every stage except `merged`; "
        "`?stage=merged` lists the merge losers for an audit.")] = None,
    priority: Annotated[str | None, Query(description="hot, warm or cold.")] = None,
    owner_user_id: Annotated[str | None, Query(description="Leads owned by this user.")] = None,
    owner: Annotated[str | None, Query(
        description="`none` for the unassigned list a manager works from.")] = None,
    territory_id: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query(description="A source code.")] = None,
    inquiry_type: Annotated[str | None, Query()] = None,
    created_from: Annotated[str | None, Query(description="ISO date, inclusive.")] = None,
    created_to: Annotated[str | None, Query(description="ISO date, inclusive.")] = None,
    q: Annotated[str | None, Query(description="Name, mobile or inquiry number.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
) -> LeadPage:
    """The lead list, filtered and in scope.

    Keyset pagination by `(created_at desc, id)`: pass the previous page's
    `meta.next_cursor` as `cursor`; it is absent on the last page. There is no
    total. An empty list means nothing in your scope, which is not an error.
    """
    return await service.list_leads(
        db, caller, stage=stage, priority=priority, owner_user_id=owner_user_id,
        owner=owner, territory_id=territory_id, source=source, inquiry_type=inquiry_type,
        created_from=created_from, created_to=created_to, q=q, limit=limit, cursor=cursor)


@router.get(
    "/{lead_id}",
    response_model=Envelope[Lead],
    responses={**_ERRORS, 404: {"model": ErrorResponse, "description": "Not in your scope."}},
    dependencies=[Depends(require("leads", "view"))],
)
async def get_lead(lead_id: str, db: DbSession, caller: CallerDep) -> Envelope[Lead]:
    """One lead in full, with its people, duplicates and current stage.

    A lead outside your scope is `404`, the same answer as one that does not
    exist: the two are indistinguishable on purpose, so a 404 leaks no existence.
    Every key is always present; `null` means "not set", never "not visible".
    """
    return Envelope(data=await service.get_lead(db, caller, lead_id))


# ── lookups the forms read ───────────────────────────────────────────────────

@lookups.get("/lead-sources", response_model=Envelope[list[LookupItem]], responses=_ERRORS)
async def lead_sources(db: DbSession, _: Claims) -> Envelope[list[LookupItem]]:
    """The lead sources for the new-lead form's source picker."""
    return Envelope(data=await service.list_lead_sources(db))


@lookups.get("/mis-systems", response_model=Envelope[list[LookupItem]], responses=_ERRORS)
async def mis_systems(db: DbSession, _: Claims) -> Envelope[list[LookupItem]]:
    """The micro-irrigation systems for the new-lead form."""
    return Envelope(data=await service.list_mis_systems(db))


@lookups.get("/lost-reasons", response_model=Envelope[list[LookupItem]], responses=_ERRORS)
async def lost_reasons(db: DbSession, _: Claims) -> Envelope[list[LookupItem]]:
    """The active reasons a lead can be marked lost with."""
    return Envelope(data=await service.list_lost_reasons(db))


@lookups.get("/territories", response_model=Envelope[list[TerritoryPick]], responses=_ERRORS)
async def territories(
    db: DbSession,
    _: Claims,
    level: Annotated[str | None, Query(description="state, district, taluka or village.")] = None,
    parent_id: Annotated[str | None, Query(description="Only children of this territory.")] = None,
    q: Annotated[str | None, Query(description="Name substring.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Envelope[list[TerritoryPick]]:
    """The territory picker for the new-lead form. Pick a district, then its
    talukas by passing `parent_id`, or search by name with `q`."""
    return Envelope(data=await service.list_territories(
        db, level=level, parent_id=parent_id, q=q, limit=limit))
