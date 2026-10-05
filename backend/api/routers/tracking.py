"""Field tracking (FS-021): the Android app's contract and the managers' map.

Duty, location batches, visits with photos, the team map, a day's route, consent,
the policy and the view log. A person records only their own; managers read their
team. Every look at someone else's whereabouts is logged."""

# ruff: noqa: E501  (route signatures and their descriptions)

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.config import get_settings
from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.domain import complaints as uploads
from api.idempotency import payload_digest, run_idempotent
from api.schemas import tracking as sch
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.complaints import AttachmentLink
from api.schemas.leads import UUID_RE
from api.services import tracking as service
from api.storage import get_storage
from api.upload_limit import BodyTooLarge

me = APIRouter(prefix="/me", tags=["tracking"])
router = APIRouter(prefix="/tracking", tags=["tracking"])
locations = APIRouter(prefix="/locations", tags=["tracking"])
visits = APIRouter(prefix="/visits", tags=["tracking"])

Id = Annotated[str, Path(pattern=UUID_RE)]
Cursor = Annotated[str | None, Query(description="From the previous page's next_cursor.")]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "This role does not track."},
    404: {"model": ErrorResponse, "description": "Not yours, or not in your team."},
    422: {"model": ErrorResponse, "description": "A rule refused it; see `code` and `fields`."},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    409: {"model": ErrorResponse, "description": "See `code`. Never retry a 4xx under the same key."},
}


async def _idem(db: Any, claims: Any, idem: str, route: str, digest: str,
                work: Callable[[], Awaitable[tuple[int, BaseModel]]]) -> Response:
    async def run() -> tuple[int, dict[str, Any]]:
        status, out = await work()
        return status, {"data": out.model_dump(mode="json", by_alias=True)}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=digest, work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


def _digest(body: BaseModel) -> str:
    return payload_digest(body.model_dump(mode="json"))


# ── config, consent, policy ─────────────────────────────────────────────────

@me.get("/tracking-config", response_model=Envelope[sch.TrackingConfig], responses=_ERRORS)
async def tracking_config(db: DbSession, caller: CallerDep) -> Envelope[sch.TrackingConfig]:
    """What the app needs before tracking: the plugin's filters, working hours,
    whether consent is needed, and the open duty. Call at app start and after every
    duty start. Answers for every staff user; `tracking_allowed: false` means hide
    the duty toggle."""
    return Envelope(data=await service.config(db, caller))


@router.post("/consent", status_code=201, response_model=Envelope[sch.Consent], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("tracking", "create"))])
async def give_consent(body: sch.ConsentIn, db: DbSession, caller: CallerDep, claims: Claims,
                       idem: IdemKey) -> Response:
    """Accept the current consent version, or withdraw (`accepted: false`).
    Withdrawing ends any open duty. `422 consent_version`: accept the version the
    config names."""
    async def work() -> tuple[int, BaseModel]:
        return 201, await service.consent(db, caller, body)
    return await _idem(db, claims, idem, "POST /api/v1/tracking/consent", _digest(body), work)


@router.get("/policy", response_model=Envelope[sch.Policy], responses=_ERRORS)
async def get_policy(db: DbSession, caller: CallerDep) -> Envelope[sch.Policy]:
    """The tracking policy in force: intervals, hours, retention, photo rule, consent."""
    return Envelope(data=await service.policy(db, caller))


@router.put("/policy", response_model=Envelope[sch.Policy], responses=_MUTATION_ERRORS,
            dependencies=[Depends(require("masters", "edit"))])
async def put_policy(body: sch.PolicyIn, db: DbSession, caller: CallerDep, claims: Claims,
                     idem: IdemKey) -> Response:
    """Add a policy version from `effective_from`. Versions are never edited. A new
    `consent_version` asks everyone again at their next duty start.
    `409 policy_exists`: a version already starts at that instant."""
    async def work() -> tuple[int, BaseModel]:
        return 200, await service.set_policy(db, caller, body)
    return await _idem(db, claims, idem, "PUT /api/v1/tracking/policy", _digest(body), work)


# ── duty ────────────────────────────────────────────────────────────────────

@router.post("/duty/start", status_code=201, response_model=Envelope[sch.Duty], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("tracking", "create"))])
async def duty_start(body: sch.DutyStart, db: DbSession, caller: CallerDep, claims: Claims,
                     idem: IdemKey) -> Response:
    """Go on duty. `201` with the new session, or `200` with the session already
    open, whose id may differ from the one sent: use the answer's id for every
    point. `409 consent_required`: accept the current consent first."""
    async def work() -> tuple[int, BaseModel]:
        duty, new = await service.duty_start(db, caller, body)
        return (201 if new else 200), duty
    return await _idem(db, claims, idem, "POST /api/v1/tracking/duty/start", _digest(body), work)


@router.post("/duty/end", response_model=Envelope[sch.Duty], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("tracking", "edit"))])
async def duty_end(body: sch.DutyEnd, db: DbSession, caller: CallerDep, claims: Claims,
                   idem: IdemKey) -> Response:
    """Go off duty. Ending an ended session answers it unchanged.
    `404 duty_not_found`: not one of your sessions."""
    async def work() -> tuple[int, BaseModel]:
        return 200, await service.duty_end(db, caller, body)
    return await _idem(db, claims, idem, "POST /api/v1/tracking/duty/end", _digest(body), work)


# ── location batches ────────────────────────────────────────────────────────

@locations.post("/batch", response_model=Envelope[sch.BatchResult], responses=_MUTATION_ERRORS,
                dependencies=[Depends(require("tracking", "create"))])
async def location_batch(body: sch.BatchIn, db: DbSession, caller: CallerDep, claims: Claims,
                         idem: IdemKey) -> Response:
    """Upload stored points, oldest first, up to 500. Always a full answer: delete
    every point it counts or names on the phone. A rejected point is never accepted
    later. When `duty.ended_at` is set, stop tracking. Use a new key per distinct
    payload (the sha256 of the sorted point ids). `422 batch_too_large`: split.
    `422 bad_clock`: the phone's clock is more than a day off."""
    async def work() -> tuple[int, BaseModel]:
        return 200, await service.batch(db, caller, body)
    return await _idem(db, claims, idem, "POST /api/v1/locations/batch", _digest(body), work)


# ── visits ──────────────────────────────────────────────────────────────────

@visits.post("", status_code=201, response_model=Envelope[sch.Visit], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("tracking", "create"))])
async def check_in(body: sch.VisitIn, db: DbSession, caller: CallerDep, claims: Claims,
                   idem: IdemKey) -> Response:
    """Check in at a lead, a dealer or a named place, with the phone's fix. No duty
    needed. The same id again answers `200`. `409 visit_open`: check out of the
    visit in `error.fields.visit_id` first. `409 consent_required`. `404`: the lead,
    dealer or task is not one you can see, or the task is not yours."""
    async def work() -> tuple[int, BaseModel]:
        visit, new = await service.check_in(db, caller, body)
        return (201 if new else 200), visit
    return await _idem(db, claims, idem, "POST /api/v1/visits", _digest(body), work)


@visits.post("/{visit_id}/check-out", response_model=Envelope[sch.Visit], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("tracking", "edit"))])
async def check_out(visit_id: Id, body: sch.CheckOut, db: DbSession, caller: CallerDep, claims: Claims,
                    idem: IdemKey) -> Response:
    """Close your open visit with an outcome. `409 visit_closed`: already closed.
    `409 photo_required`: the policy wants a photo first."""
    async def work() -> tuple[int, BaseModel]:
        return 200, await service.check_out(db, caller, visit_id, body)
    return await _idem(db, claims, idem, f"POST /api/v1/visits/{visit_id}/check-out", _digest(body), work)


@visits.post("/{visit_id}/photos", status_code=201, response_model=Envelope[sch.VisitPhoto],
             responses={**_MUTATION_ERRORS,
                        413: {"model": ErrorResponse, "description": "Over 10 MB."},
                        503: {"model": ErrorResponse, "description": "`storage_unavailable`: retry later."}},
             dependencies=[Depends(require("tracking", "create"))])
async def add_photo(visit_id: Id, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
                    file: Annotated[UploadFile, File()]) -> Response:
    """A photo of your visit: JPEG, PNG, WebP or HEIC, up to 10 MB, up to 3, until
    24 hours after check-in, open or closed. The same file again answers `200`.
    `409 photo_limit`, `409 photo_window_closed`."""
    data = await file.read(uploads.MAX_UPLOAD_BYTES + 1)
    if len(data) > uploads.MAX_UPLOAD_BYTES:
        raise BodyTooLarge()
    digest = payload_digest({"sha256": hashlib.sha256(data).hexdigest(), "filename": file.filename or ""})
    storage = get_storage(get_settings(), bounded=True)

    async def work() -> tuple[int, BaseModel]:
        photo, new = await service.add_photo(db, caller, visit_id, filename=file.filename, data=data,
                                             storage=storage)
        return (201 if new else 200), photo
    return await _idem(db, claims, idem, f"POST /api/v1/visits/{visit_id}/photos", digest, work)


@visits.get("", response_model=sch.VisitPage, responses=_ERRORS,
            dependencies=[Depends(require("tracking", "view"))])
async def list_visits(db: DbSession, caller: CallerDep,
                      user_id: Annotated[str | None, Query(pattern="^(me|" + UUID_RE.strip("^$") + ")$",
                                                           description="A person, or `me`.")] = None,
                      date: Annotated[dt.date | None, Query(description="An IST day.")] = None,
                      lead_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                      limit: Annotated[int, Query(ge=1, le=100)] = 50,
                      cursor: Cursor = None) -> sch.VisitPage:
    """Visits, newest first, within your team. Someone outside it gives an empty
    list. Reading another person's visits is logged."""
    return await service.list_visits(db, caller, user_id=user_id, day=date, lead_id=lead_id,
                                     limit=limit, cursor=cursor)


@visits.get("/{visit_id}", response_model=Envelope[sch.Visit], responses=_ERRORS,
            dependencies=[Depends(require("tracking", "view"))])
async def get_visit(visit_id: Id, db: DbSession, caller: CallerDep) -> Envelope[sch.Visit]:
    """One visit. Reading another person's is logged."""
    return Envelope(data=await service.get_visit(db, caller, visit_id))


@visits.get("/{visit_id}/photos/{photo_id}", response_model=Envelope[AttachmentLink], responses=_ERRORS,
            dependencies=[Depends(require("tracking", "view"))])
async def photo_link(visit_id: Id, photo_id: Id, db: DbSession) -> Envelope[AttachmentLink]:
    """A ten-minute link to the photo. Use it as an image source; never fetch it with
    the bearer token."""
    return Envelope(data=await service.photo_link(db, visit_id, photo_id, get_storage(get_settings())))


# ── team map, routes, the view log ──────────────────────────────────────────

@router.get("/team/latest", response_model=Envelope[list[sch.TeamMember]], responses=_ERRORS,
            dependencies=[Depends(require("tracking", "view"))])
async def team_latest(db: DbSession, caller: CallerDep) -> Envelope[list[sch.TeamMember]]:
    """Everyone you may track, with their last position while on duty. Poll every
    60 seconds at most. The read is logged."""
    return Envelope(data=await service.team_latest(db, caller))


@router.get("/users/{user_id}/route", response_model=Envelope[sch.Route], responses=_ERRORS,
            dependencies=[Depends(require("tracking", "view"))])
async def route(user_id: Id, db: DbSession, caller: CallerDep,
                date: Annotated[dt.date, Query(description="An IST day.")]) -> Envelope[sch.Route]:
    """One person's day: the path (at most 2,000 points), stops, visits, duty spans
    and distance. `404`: not in your team. Another person's route is logged."""
    return Envelope(data=await service.route(db, caller, user_id, date))


@router.get("/view-log", response_model=sch.ViewLogPage, responses=_ERRORS,
            dependencies=[Depends(require("tracking", "view"))])
async def view_log(db: DbSession, _: CallerDep,
                   subject_user_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                   limit: Annotated[int, Query(ge=1, le=100)] = 50,
                   cursor: Cursor = None) -> sch.ViewLogPage:
    """Who looked at whose route, visits or the team map, and when. Admin and MD
    read it; for anyone else it is empty."""
    return await service.view_log(db, subject_user_id=subject_user_id, limit=limit, cursor=cursor)
