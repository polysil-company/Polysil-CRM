"""The lead endpoints, and the lookups the forms read (FS-003 section 4).

Thin on purpose: parse, gate, delegate, shape. Every transaction belongs to a
dependency, every rule to the service or the database.

**The docstrings below become prose in `docs/api/leads.md`** (CLAUDE.md 2.3), the
document the frontend track builds against. They say what the endpoint is *for*.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import (
    UUID_RE,
    Assignee,
    DismissResult,
    DuplicatePage,
    Lead,
    LeadAssign,
    LeadCreate,
    LeadMerge,
    LeadNote,
    LeadPage,
    LeadPatch,
    LeadReopen,
    LeadTransition,
    LookupCreate,
    LookupItem,
    LookupUpdate,
    PartnerPick,
    ScoringItem,
    ScoringPatch,
    TerritoryPick,
    TimelineEvent,
    TimelinePage,
)
from api.services import leads as service

router = APIRouter(prefix="/leads", tags=["leads"])
lookups = APIRouter(prefix="/lookups", tags=["lookups"])

# Path ids are validated here, so a malformed id is a 422 with the envelope rather
# than a uuid bind error and a 500 (cross-vendor P2). Body ids carry the same
# pattern in the schemas.
LeadId = Annotated[str, Path(pattern=UUID_RE)]
LinkId = Annotated[str, Path(pattern=UUID_RE)]
ItemId = Annotated[str, Path(pattern=UUID_RE)]

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
               409: {"model": ErrorResponse,
                     "description": "The key was used for a different body."}},
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
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

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
    owner_user_id: Annotated[str | None, Query(pattern=UUID_RE,
                                                description="Leads owned by this user.")] = None,
    owner: Annotated[str | None, Query(
        description="`none` for the unassigned list a manager works from.")] = None,
    territory_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
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


# Declared before the /{lead_id} routes so the literal path wins the match.
@router.get("/assignees", response_model=Envelope[list[Assignee]], responses=_ERRORS,
            dependencies=[Depends(require("leads", "edit"))])
async def list_assignees(db: DbSession, caller: CallerDep) -> Envelope[list[Assignee]]:
    """The owner picker: the staff you may assign a lead to. Every active staff user
    for a global assigner, your own org subtree for a district manager, nobody for
    other scopes. Names and org units only, no contact details.
    """
    return Envelope(data=await service.assignees(db, caller))


@router.get("/duplicates", response_model=DuplicatePage, responses=_ERRORS,
            dependencies=[Depends(require("leads", "view"))])
async def duplicate_queue(
    db: DbSession, caller: CallerDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
) -> DuplicatePage:
    """The duplicate review queue: pending pairs where both leads are in your
    scope, newest first. From here, dismiss a pair or merge one lead into the other.
    """
    return await service.duplicates(db, caller, limit=limit, cursor=cursor)


@router.get(
    "/{lead_id}",
    response_model=Envelope[Lead],
    responses={**_ERRORS, 404: {"model": ErrorResponse, "description": "Not in your scope."}},
    dependencies=[Depends(require("leads", "view"))],
)
async def get_lead(lead_id: LeadId, db: DbSession, caller: CallerDep) -> Envelope[Lead]:
    """One lead in full, with its people, duplicates and current stage.

    A lead outside your scope is `404`, the same answer as one that does not
    exist: the two are indistinguishable on purpose, so a 404 leaks no existence.
    Every key is always present; `null` means "not set", never "not visible".
    """
    return Envelope(data=await service.get_lead(db, caller, lead_id))


_LEAD_ERRORS = {**_ERRORS,
                400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
                404: {"model": ErrorResponse, "description": "Not in your scope."},
                409: {"model": ErrorResponse, "description": "Key reused, or the stage moved on."}}


@router.post("/{lead_id}/transition", response_model=Envelope[Lead], responses=_LEAD_ERRORS,
             dependencies=[Depends(require("leads", "edit"))])
async def transition(
    lead_id: LeadId, body: LeadTransition, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Move a lead along its lifecycle: contact it, qualify it, or mark it lost.

    Only the moves the lifecycle allows are accepted. Marking a lead **lost** needs
    a `lost_reason_id`. Stages from **quoted** onward are refused with
    `quotation_required` until quotations ship. Pass `expected_stage` to act only if
    the lead has not moved since you loaded it; if it has, you get `409 stage_changed`
    with the current stage in `fields.stage`.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        lead = await service.transition_lead(db, caller, lead_id, body)
        return status.HTTP_200_OK, {"data": lead.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"POST /api/v1/leads/{lead_id}/transition",
        payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("/{lead_id}/reopen", response_model=Envelope[Lead], responses=_LEAD_ERRORS,
             dependencies=[Depends(require("leads", "edit"))])
async def reopen(
    lead_id: LeadId, body: LeadReopen, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Bring a lost lead back. It returns to the stage it was lost from, its lost
    reason and note move to the timeline, and its reopen count goes up. Only a lost
    lead can be reopened; anything else is `422 stage_terminal`.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        lead = await service.reopen_lead(db, caller, lead_id, body)
        return status.HTTP_200_OK, {"data": lead.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"POST /api/v1/leads/{lead_id}/reopen",
        payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("/{lead_id}/notes", response_model=Envelope[TimelineEvent],
             status_code=status.HTTP_201_CREATED, responses=_LEAD_ERRORS,
             dependencies=[Depends(require("leads", "edit"))])
async def add_note(
    lead_id: LeadId, body: LeadNote, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Add a note to a lead. It becomes a timeline entry and bumps the lead's
    last-activity time. Returns the created event.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        event = await service.add_note(db, caller, lead_id, body)
        return status.HTTP_201_CREATED, {"data": event.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"POST /api/v1/leads/{lead_id}/notes",
        payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("/{lead_id}/assign", response_model=Envelope[Lead], responses=_LEAD_ERRORS,
             dependencies=[Depends(require("leads", "edit"))])
async def assign(
    lead_id: LeadId, body: LeadAssign, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Give the lead an owner, a partner, or both.

    Who you may name depends on your scope: a global assigner may pick any active
    staff user, a district manager only someone in their own org subtree, and
    other scopes cannot set an owner at all. The partner must be one you can see.
    Send a field as `null` to clear it; leave it out to keep it.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        lead = await service.assign_lead(db, caller, lead_id, body)
        return status.HTTP_200_OK, {"data": lead.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"POST /api/v1/leads/{lead_id}/assign",
        payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.patch("/{lead_id}", response_model=Envelope[Lead], responses=_LEAD_ERRORS,
              dependencies=[Depends(require("leads", "edit"))])
async def patch(
    lead_id: LeadId, body: LeadPatch, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Correct the lead's own fields. Send only what changes; a field left out is
    unchanged. email, village and estimated_value may be sent null to clear them.
    The stage, owner and partner have their own endpoints so the timeline names
    the change. A closed lead (won, lost, merged) is `422 stage_terminal`.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        lead = await service.patch_lead(db, caller, lead_id, body)
        return status.HTTP_200_OK, {"data": lead.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"PATCH /api/v1/leads/{lead_id}",
        payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_LEAD_ERRORS,
               dependencies=[Depends(require("leads", "delete"))])
async def delete(
    lead_id: LeadId, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
) -> Response:
    """Soft-delete a lead. Needs the `leads.delete` permission. Afterwards the lead
    is hidden from everyone without that permission, and its pending duplicate
    pairs are closed so no one's review queue holds an entry they cannot act on.
    Always `204`, including on a repeat.
    """
    async def work() -> tuple[int, dict]:
        await service.delete_lead(db, caller, lead_id)
        return status.HTTP_204_NO_CONTENT, {}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"DELETE /api/v1/leads/{lead_id}",
        payload_hash=payload_digest({}), work=work)
    if outcome.status_code == status.HTTP_204_NO_CONTENT:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("/duplicates/{link_id}/dismiss", response_model=Envelope[DismissResult],
             responses=_LEAD_ERRORS, dependencies=[Depends(require("leads", "edit"))])
async def dismiss_duplicate(
    link_id: LinkId, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Mark a duplicate pair as not a duplicate. Both leads stay as they are; the
    pair leaves the queue and both timelines record the dismissal.
    """
    async def work() -> tuple[int, dict]:
        res = await service.dismiss_duplicate(db, caller, link_id)
        return status.HTTP_200_OK, {"data": res.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub,
        route=f"POST /api/v1/leads/duplicates/{link_id}/dismiss",
        payload_hash=payload_digest({}), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("/{lead_id}/merge", response_model=Envelope[Lead], responses=_LEAD_ERRORS,
             dependencies=[Depends(require("leads", "edit"))])
async def merge(
    lead_id: LeadId, body: LeadMerge, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Merge this lead (the loser) into another (the survivor). Staff only.

    The loser is marked merged and points at the survivor; every pending
    duplicate pair of the loser is re-pointed at the survivor or closed; the
    survivor's timeline gains the loser's history. Returns the survivor. Neither
    lead may be won, lost or already merged (`422 merge_terminal`), and a lead
    cannot merge into itself (`422 merge_self`).
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        lead = await service.merge_lead(db, caller, lead_id, body)
        return status.HTTP_200_OK, {"data": lead.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"POST /api/v1/leads/{lead_id}/merge",
        payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("/{lead_id}/timeline", response_model=TimelinePage, responses=_LEAD_ERRORS,
            dependencies=[Depends(require("leads", "view"))])
async def get_timeline(
    lead_id: LeadId, db: DbSession, caller: CallerDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
) -> TimelinePage:
    """A lead's history, newest first, including the events of any lead merged into
    it. Keyset-paged: pass the previous page's `meta.next_cursor` as `cursor`.
    """
    return await service.timeline(db, caller, lead_id, limit=limit, cursor=cursor)


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
    """The reasons a lead can be marked lost with. Switched-off reasons are included
    with `is_active` false, so the admin list and the form share one call; the form
    shows active ones only, because losing with an inactive reason is refused.
    """
    return Envelope(data=await service.list_lost_reasons(db))


@lookups.get("/territories", response_model=Envelope[list[TerritoryPick]], responses=_ERRORS)
async def territories(
    db: DbSession,
    _: Claims,
    level: Annotated[str | None, Query(description="state, district, taluka or village.")] = None,
    parent_id: Annotated[str | None, Query(pattern=UUID_RE,
                                            description="Only children of this territory.")] = None,
    q: Annotated[str | None, Query(description="Name substring.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Envelope[list[TerritoryPick]]:
    """The territory picker for the new-lead form. Pick a district, then its
    talukas by passing `parent_id`, or search by name with `q`."""
    return Envelope(data=await service.list_territories(
        db, level=level, parent_id=parent_id, q=q, limit=limit))


@lookups.get("/partners", response_model=Envelope[list[PartnerPick]], responses=_ERRORS,
             dependencies=[Depends(require("leads", "view"))])
async def partners(
    db: DbSession,
    _: Claims,
    q: Annotated[str | None, Query(description="Name or code substring.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Envelope[list[PartnerPick]]:
    """The partner picker for assigning a lead to a channel partner. You see only
    the partners in your own scope: a dealer its subtree, a district manager the
    partners in its territories, an admin all of them.
    """
    return Envelope(data=await service.list_partners(db, q=q, limit=limit))


# ── maintaining the lists (masters.edit) ─────────────────────────────────────
#
# Add and switch off, never rename or delete: the row a lead already points at
# must keep its name (ADR-033). Every write is audited.

_ADMIN = [Depends(require("masters", "edit"))]
_ADMIN_ERRORS = {**_ERRORS,
                 400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
                 404: {"model": ErrorResponse, "description": "No such row."}}


async def _create(db: DbSession, claims: Claims, idem: IdemKey, path: str, table: str,
                  body: LookupCreate) -> JSONResponse:
    async def work() -> tuple[int, dict]:
        item = await service.create_lookup(db, table, body)
        return status.HTTP_201_CREATED, {"data": item.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"POST /api/v1/lookups/{path}",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


async def _update(db: DbSession, claims: Claims, idem: IdemKey, path: str, table: str,
                  item_id: ItemId, body: LookupUpdate) -> JSONResponse:
    async def work() -> tuple[int, dict]:
        item = await service.update_lookup(db, table, item_id, body)
        return status.HTTP_200_OK, {"data": item.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"PATCH /api/v1/lookups/{path}/{item_id}",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@lookups.post("/lost-reasons", response_model=Envelope[LookupItem],
              status_code=status.HTTP_201_CREATED, responses=_ADMIN_ERRORS, dependencies=_ADMIN)
async def add_lost_reason(body: LookupCreate, db: DbSession, claims: Claims,
                          idem: IdemKey) -> JSONResponse:
    """Add a reason a lead can be marked lost with. `kind` defaults to lost."""
    return await _create(db, claims, idem, "lost-reasons", "won_lost_reason", body)


@lookups.patch("/lost-reasons/{item_id}", response_model=Envelope[LookupItem],
               responses=_ADMIN_ERRORS, dependencies=_ADMIN)
async def edit_lost_reason(item_id: ItemId, body: LookupUpdate, db: DbSession, claims: Claims,
                           idem: IdemKey) -> JSONResponse:
    """Switch a reason on or off, or reorder it. Names never change in place."""
    return await _update(db, claims, idem, "lost-reasons", "won_lost_reason", item_id, body)


@lookups.post("/lead-sources", response_model=Envelope[LookupItem],
              status_code=status.HTTP_201_CREATED, responses=_ADMIN_ERRORS, dependencies=_ADMIN)
async def add_lead_source(body: LookupCreate, db: DbSession, claims: Claims,
                          idem: IdemKey) -> JSONResponse:
    """Add a lead source. `quality` (0 to 1) is its factor in the priority score."""
    return await _create(db, claims, idem, "lead-sources", "lead_source", body)


@lookups.patch("/lead-sources/{item_id}", response_model=Envelope[LookupItem],
               responses=_ADMIN_ERRORS, dependencies=_ADMIN)
async def edit_lead_source(item_id: ItemId, body: LookupUpdate, db: DbSession, claims: Claims,
                           idem: IdemKey) -> JSONResponse:
    """Switch a source on or off, reorder it, or retune its quality factor."""
    return await _update(db, claims, idem, "lead-sources", "lead_source", item_id, body)


@lookups.post("/mis-systems", response_model=Envelope[LookupItem],
              status_code=status.HTTP_201_CREATED, responses=_ADMIN_ERRORS, dependencies=_ADMIN)
async def add_mis_system(body: LookupCreate, db: DbSession, claims: Claims,
                         idem: IdemKey) -> JSONResponse:
    """Add a micro-irrigation system to the list."""
    return await _create(db, claims, idem, "mis-systems", "mis_system", body)


@lookups.patch("/mis-systems/{item_id}", response_model=Envelope[LookupItem],
               responses=_ADMIN_ERRORS, dependencies=_ADMIN)
async def edit_mis_system(item_id: ItemId, body: LookupUpdate, db: DbSession, claims: Claims,
                          idem: IdemKey) -> JSONResponse:
    """Switch a system on or off."""
    return await _update(db, claims, idem, "mis-systems", "mis_system", item_id, body)


@lookups.get("/scoring", response_model=Envelope[list[ScoringItem]], responses=_ERRORS)
async def get_scoring(db: DbSession, _: Claims) -> Envelope[list[ScoringItem]]:
    """The priority-score weights, caps and thresholds. Readable by anyone signed
    in; changed only with `masters.edit`."""
    return Envelope(data=await service.get_scoring(db))


@lookups.patch("/scoring", response_model=Envelope[list[ScoringItem]],
               responses=_ADMIN_ERRORS, dependencies=_ADMIN)
async def patch_scoring(body: ScoringPatch, db: DbSession, claims: Claims,
                        idem: IdemKey) -> JSONResponse:
    """Retune the score. Send only the keys that change. Caps and hour bands must
    stay positive; weights must not be negative. Takes effect on the next score
    computation (the next create, transition, note, assign or reopen).
    """
    async def work() -> tuple[int, dict]:
        items = await service.patch_scoring(db, body)
        return status.HTTP_200_OK, {"data": [i.model_dump(mode="json") for i in items]}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="PATCH /api/v1/lookups/scoring",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
