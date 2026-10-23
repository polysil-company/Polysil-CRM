"""Schemes (FS-031): the master, standings and entitlements.

The order's own scheme panel is `GET /orders/{id}/schemes`, in the orders router.

**The docstrings below become prose in `docs/api/schemes.md`** (CLAUDE.md 2.3).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.schemes import (
    EntitlementPage,
    Scheme,
    SchemeCreate,
    SchemePage,
    SchemePatch,
    Standing,
)
from api.services import schemes as service

router = APIRouter(prefix="/schemes", tags=["schemes"])
entitlements = APIRouter(prefix="/scheme-entitlements", tags=["schemes"])

Id = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "The action is not in your permissions."},
    422: {"model": ErrorResponse, "description": "A field failed validation; see `fields`."},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    404: {"model": ErrorResponse, "description": "No such scheme in your scope."},
    409: {"model": ErrorResponse, "description": "`code_taken`, `scheme_in_use`, or the key "
                                                 "was used for a different body."},
}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[Scheme],
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("schemes", "create"))])
async def create_scheme(body: SchemeCreate, db: DbSession, caller: CallerDep, claims: Claims,
                        idem: IdemKey) -> JSONResponse:
    """Create a scheme: what it gives, on what condition, to whom and when.

    Valid combinations of `scheme_type` and `benefit.kind`:

    | scheme_type | benefit.kind | worked out |
    |---|---|---|
    | order_discount | pct, flat | when the order is submitted |
    | order_points | points | when the order is delivered |
    | next_order | pct, flat | earned at delivery, used on a later order |
    | period | pct, flat, points | after each month or quarter ends |

    A wrong combination is `422` naming the field. A scheme benefit reduces what the
    dealer owes (`payable` on the order); it never changes the invoice.
    """
    async def work() -> tuple[int, dict[str, Any]]:
        out = await service.create_scheme(db, caller, body)
        return status.HTTP_201_CREATED, {"data": out.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="POST /api/v1/schemes",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("", response_model=SchemePage, responses=_ERRORS,
            dependencies=[Depends(require("schemes", "view"))])
async def list_schemes(
    db: DbSession,
    status_: Annotated[Literal["active", "inactive", "current"] | None, Query(
        alias="status", description="`current` is active and today within its dates.")] = None,
    scheme_type: Annotated[str | None, Query(description="One scheme type.")] = None,
    q: Annotated[str | None, Query(description="Code or name.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
) -> SchemePage:
    """The schemes, newest first, keyset-paged. Staff see every scheme. **A partner
    user sees only the active schemes that target it**: its partner, its type, or a
    territory at or above its own; and never a scheme's partner targets."""
    return await service.list_schemes(db, status=status_, scheme_type=scheme_type, q=q,
                                      cursor=cursor, limit=limit)


@router.get("/{scheme_id}", response_model=Envelope[Scheme], responses=_ERRORS,
            dependencies=[Depends(require("schemes", "view"))])
async def get_scheme(scheme_id: Id, db: DbSession) -> Envelope[Scheme]:
    """One scheme. `used` says whether it has given anything yet."""
    return Envelope(data=await service.get_scheme(db, scheme_id))


@router.patch("/{scheme_id}", response_model=Envelope[Scheme], responses=_MUTATION_ERRORS,
              dependencies=[Depends(require("schemes", "edit"))])
async def patch_scheme(scheme_id: Id, body: SchemePatch, db: DbSession, caller: CallerDep,
                       claims: Claims, idem: IdemKey) -> JSONResponse:
    """Change a scheme. Send only what changes; `targets`, if sent, replaces the list.

    Once a scheme has given a benefit, only `valid_to` (earlier, and not before
    today) and `is_active` can change: anything else is `409 scheme_in_use`. End it
    and create a new one instead. Deactivating stops new benefits; credits already
    earned stay usable.
    """
    async def work() -> tuple[int, dict[str, Any]]:
        out = await service.patch_scheme(db, caller, scheme_id, body)
        return status.HTTP_200_OK, {"data": out.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"PATCH /api/v1/schemes/{scheme_id}",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("/{scheme_id}/standing", response_model=Envelope[Standing], responses=_ERRORS,
            dependencies=[Depends(require("schemes", "view"))])
async def get_standing(
    scheme_id: Id, db: DbSession, caller: CallerDep,
    partner_id: Annotated[str | None, Query(
        pattern=UUID_RE, description="Staff: the partner. Ignored for a partner user, "
                                     "who always gets its own.")] = None,
) -> Envelope[Standing]:
    """A partner's progress in a period scheme's current month or quarter: what it
    has had delivered so far, against the target. For the dealer portal's progress
    bar. `422 not_a_period_scheme` for any other type."""
    return Envelope(data=await service.standing(db, caller, scheme_id, partner_id))


@entitlements.get("", response_model=EntitlementPage, responses=_ERRORS,
                  dependencies=[Depends(require("schemes", "view"))])
async def list_entitlements(
    db: DbSession,
    partner_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    status_: Annotated[Literal["available", "consumed", "expired", "reversed"] | None, Query(
        alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
) -> EntitlementPage:
    """Credits earned now and used on a later order (next-order and period schemes),
    newest first. Staff see the partners they can see; a partner user its own
    subtree. An available credit is used automatically on the partner's next order,
    earliest expiry first; one worth more than that order's payable waits for a
    bigger order."""
    return await service.list_entitlements(db, partner_id=partner_id, status=status_,
                                           cursor=cursor, limit=limit)
