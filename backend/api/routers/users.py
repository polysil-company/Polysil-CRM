"""The people endpoints, and the roles lookup (FS-006 section 4).

Thin on purpose: parse, gate, delegate, shape. Every transaction belongs to a
dependency, every rule to the service or the database.

**The docstrings below become prose in `docs/api/users.md`** (CLAUDE.md 2.3), the
document the frontend track builds against. They say what the endpoint is *for*.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, redacted_digest, run_idempotent
from api.routers.exporting import XLSX_RESPONSE, export, filters_of
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.users import (
    HandoverRequest,
    HandoverResult,
    PasswordSet,
    PasswordSetResult,
    RevokeResult,
    RoleItem,
    UnlockResult,
    UserCreate,
    UserDetail,
    UserPage,
    UserPatch,
)
from api.services import exports
from api.services import users as service

router = APIRouter(prefix="/users", tags=["users"])
roles = APIRouter(prefix="/lookups", tags=["lookups"])

UserId = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse,
          "description": "The action is not in your permissions, or a temporary "
                         "password must be changed first (`password_change_required`)."},
    422: {"model": ErrorResponse, "description": "A field failed validation; see `fields`."},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    404: {"model": ErrorResponse, "description": "No such person in your scope."},
    409: {"model": ErrorResponse, "description": "The key was used for a different body."},
}


def _reply(outcome: object) -> JSONResponse:
    return JSONResponse(outcome.body, status_code=outcome.status_code)  # type: ignore[attr-defined]


@router.get("", response_model=UserPage, responses=_ERRORS,
            dependencies=[Depends(require("users", "view"))])
async def list_users(
    db: DbSession,
    caller: CallerDep,
    q: Annotated[str | None, Query(description="Name, email or mobile substring.")] = None,
    user_type: Annotated[str | None, Query(
        description="staff, partner_user or consumer. Left out, the list is staff and "
                    "partner users: farmers' portal accounts (FS-044) only when asked.")] = None,
    role: Annotated[str | None, Query(description="A role code.")] = None,
    org_unit_id: Annotated[str | None, Query(pattern=UUID_RE,
                                              description="Staff anchored on this office.")] = None,
    partner_id: Annotated[str | None, Query(pattern=UUID_RE,
                                             description="Users anchored on this partner.")] = None,
    is_active: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
) -> UserPage:
    """The people list, newest first. Live people only; the system principal never
    appears. `open_leads` is filled for staff and null for partner users.

    Keyset pagination by `(created_at desc, id)`: pass `meta.next_cursor` back as
    `cursor`; it is absent on the last page. An empty list means nobody is in your
    scope, which is not an error; a 403 means you may not view people at all.
    """
    return await service.list_users(
        db, caller, q=q, user_type=user_type, role=role, org_unit_id=org_unit_id,
        partner_id=partner_id, is_active=is_active, limit=limit, cursor=cursor)


@router.get("/export", response_class=Response, responses={**_ERRORS, **XLSX_RESPONSE},
            dependencies=[Depends(require("users", "view"))])
async def export_users(
    db: DbSession, caller: CallerDep,
    filters: Annotated[dict[str, Any], Depends(filters_of(list_users))],
) -> Response:
    """Download the user list as an Excel file, with the same filters as the list.

    The file holds exactly the rows the list would show for these filters, across
    every page, and nothing outside your scope. Call it with `fetch` and the bearer
    token, then save the blob. More than 5,000 rows is `422 export_too_large`:
    narrow the filters. An empty list gives a file with the header row only.
    """
    return await export(list_users, stem="users", title="Users", columns=exports.USERS,
                        user_id=caller.user_id, filters=filters, db=db, caller=caller)


@router.get("/{user_id}", response_model=Envelope[UserDetail],
            responses={**_ERRORS, 404: _MUTATION_ERRORS[404]},
            dependencies=[Depends(require("users", "view"))])
async def get_user(user_id: UserId, db: DbSession, caller: CallerDep) -> Envelope[UserDetail]:
    """One person: identity, role, office or partner, territories, who created them.
    If you hold `users.edit` the answer also carries `locked_until` (a live sign-in
    lockout, staff only) and `active_sessions`. A deleted person is returned only to
    a `users.delete` holder, with `deleted_at` set.
    """
    return Envelope(data=await service.get_user(db, caller, user_id))


@router.post("", response_model=Envelope[UserDetail], status_code=status.HTTP_201_CREATED,
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("users", "create"))])
async def create_user(
    body: UserCreate, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Create a staff member or a partner user.

    A staff member needs an email, a non-portal role, an open office and a
    temporary password of at least 12 characters; tell them the password out of
    band. They must change it at first sign-in, and until they do every other call
    they make answers `403 password_change_required`. A partner user needs an
    Indian mobile and an active partner; the role is the partner's type and is
    never sent. Send `mobile` in any Indian form.

    **`Idempotency-Key` is required.** A retry with the same key and body replays
    the stored `201`; the same key with a different body (a different password
    counts) is `409`.
    """
    payload_hash = redacted_digest(body.model_dump(mode="json", exclude_unset=True), ["password"])

    async def work() -> tuple[int, dict]:
        user = await service.create_user(db, caller, body)
        return status.HTTP_201_CREATED, {"data": user.model_dump(mode="json")}

    return _reply(await run_idempotent(
        db, key=idem, user_id=claims.sub, route="POST /api/v1/users",
        payload_hash=payload_hash, work=work))


@router.patch("/{user_id}", response_model=Envelope[UserDetail], responses=_MUTATION_ERRORS,
              dependencies=[Depends(require("users", "edit"))])
async def patch_user(
    user_id: UserId, body: UserPatch, db: DbSession, caller: CallerDep, claims: Claims,
    idem: IdemKey,
) -> JSONResponse:
    """Correct a person. Send only what changes. `territory_ids` replaces the whole
    set. `is_active: false` signs them out everywhere first; `true` reactivates
    into an office that is open or a partner that is active. You cannot change your
    own role, office, partner, territories or active flag, and the last
    administrator cannot be deactivated or demoted (`422 fields.id`).
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        user = await service.patch_user(db, caller, user_id, body)
        return status.HTTP_200_OK, {"data": user.model_dump(mode="json")}

    return _reply(await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"PATCH /api/v1/users/{user_id}",
        payload_hash=payload_hash, work=work))


@router.post("/{user_id}/password", response_model=Envelope[PasswordSetResult],
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("users", "edit"))])
async def set_password(
    user_id: UserId, body: PasswordSet, db: DbSession, caller: CallerDep, claims: Claims,
    idem: IdemKey,
) -> JSONResponse:
    """Set a new temporary password for a staff member. Every session of theirs is
    signed out first; they sign in with the new password and must change it. A
    partner user signs in by OTP and has no password (`422 fields.user_type`).
    """
    payload_hash = redacted_digest(body.model_dump(mode="json"), ["password"])

    async def work() -> tuple[int, dict]:
        result = await service.set_password(db, caller, user_id, body.password)
        return status.HTTP_200_OK, {"data": result.model_dump(mode="json")}

    return _reply(await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"POST /api/v1/users/{user_id}/password",
        payload_hash=payload_hash, work=work))


@router.post("/{user_id}/sessions/revoke", response_model=Envelope[RevokeResult],
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("users", "edit"))])
async def revoke_sessions(
    user_id: UserId, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Sign a person out everywhere, now. Their next request on any device is a
    401 and their refresh tokens stop working."""
    async def work() -> tuple[int, dict]:
        result = await service.revoke_sessions(db, caller, user_id)
        return status.HTTP_200_OK, {"data": result.model_dump(mode="json")}

    return _reply(await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"POST /api/v1/users/{user_id}/sessions/revoke",
        payload_hash=payload_digest({}), work=work))


@router.post("/{user_id}/unlock", response_model=Envelope[UnlockResult],
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("users", "edit"))])
async def unlock(
    user_id: UserId, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Clear a staff member's sign-in lockout before the fifteen minutes pass. The
    failed attempts stay on record. A partner user has nothing to unlock
    (`422 fields.user_type`).
    """
    async def work() -> tuple[int, dict]:
        result = await service.unlock(db, caller, user_id)
        return status.HTTP_200_OK, {"data": result.model_dump(mode="json")}

    return _reply(await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"POST /api/v1/users/{user_id}/unlock",
        payload_hash=payload_digest({}), work=work))


@router.post("/{user_id}/handover", response_model=Envelope[HandoverResult],
             responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("users", "edit")), Depends(require("leads", "edit"))])
async def handover(
    user_id: UserId, body: HandoverRequest, db: DbSession, caller: CallerDep, claims: Claims,
    idem: IdemKey,
) -> JSONResponse:
    """Hand every open lead this person owns to someone else, for the leaver's last
    day. Pick the target from `GET /leads/assignees`. One call moves at most 500
    leads and answers `remaining`; repeat with a **new** `Idempotency-Key` until it
    is 0 (a replay under the same key returns the stored answer and moves nothing).
    `deactivate: true` also signs the leaver out and deactivates them, and is
    refused while anything remains. Zero leads to move is still a 200.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        result = await service.handover(db, caller, user_id, body)
        return status.HTTP_200_OK, {"data": result.model_dump(mode="json")}

    return _reply(await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"POST /api/v1/users/{user_id}/handover",
        payload_hash=payload_hash, work=work))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_MUTATION_ERRORS,
               dependencies=[Depends(require("users", "delete"))])
async def delete_user(
    user_id: UserId, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
) -> Response:
    """Soft-delete a person. They are signed out everywhere and disappear from the
    list; the row stays for the audit trail and the leads they created. Refused
    while they own an open lead (`422 fields.open_leads`, hand over first), for
    your own row, and for the last administrator. A repeat is `204`.
    """
    async def work() -> tuple[int, dict]:
        await service.delete_user(db, caller, user_id)
        return status.HTTP_204_NO_CONTENT, {}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"DELETE /api/v1/users/{user_id}",
        payload_hash=payload_digest({}), work=work)
    if outcome.status_code == status.HTTP_204_NO_CONTENT:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return _reply(outcome)


@roles.get("/roles", response_model=Envelope[list[RoleItem]], responses=_ERRORS)
async def list_roles(db: DbSession, _: Claims) -> Envelope[list[RoleItem]]:
    """The sixteen roles a person can hold, for the role picker. The staff form
    filters out `is_portal` roles; a partner user's role is derived from its
    partner and never chosen. The system principal's role is never listed.
    """
    return Envelope(data=await service.list_roles(db))
