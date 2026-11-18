"""GET /notifications and POST /notifications/read (FS-018): the bell."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from api.deps import Claims, DbSession, IdemKey
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.notifications import MarkRead, NotificationPage, UnreadCount
from api.services import notifications as service

router = APIRouter(prefix="/notifications", tags=["notifications"])

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse,
          "description": "`idempotency_key_required`: a write sent without an Idempotency-Key."},
    401: {"model": ErrorResponse, "description": "Not signed in."},
    422: {"model": ErrorResponse, "description": "A bad cursor, or both or neither of "
                                                 "`ids` and `all`."},
}


@router.get("", response_model=NotificationPage, responses=_ERRORS)
async def list_notifications(
        db: DbSession, _: Claims,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: Annotated[str | None, Query(description="From a previous page's "
                                            "`meta.next_cursor`.")] = None,
        unread: Annotated[bool, Query(description="Only the unread ones.")] = False,
) -> NotificationPage:
    """Your notifications, newest first, with your unread count. For the bell,
    poll `?limit=1` for the count; there is no push."""
    return await service.list_notifications(db, limit=limit, cursor=cursor, unread=unread)


@router.post("/read", response_model=Envelope[UnreadCount], responses=_ERRORS)
async def mark_read(body: MarkRead, db: DbSession, claims: Claims, idem: IdemKey) -> JSONResponse:
    """Mark some notifications read (`ids`), or all of them (`all: true`). Ids that
    are not yours, or already read, are ignored. Answers the new unread count."""
    async def work() -> tuple[int, dict]:
        out = await service.mark_read(db, body)
        return 200, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="POST /api/v1/notifications/read",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
