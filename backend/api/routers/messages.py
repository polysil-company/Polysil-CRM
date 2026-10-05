"""/conversations and /staff-directory (FS-019): one-to-one staff messages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import CallerDep, Claims, DbSession, IdemKey
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.messages import (
    Conversation,
    ConversationList,
    MarkRead,
    Message,
    MessagePage,
    Person,
    SendMessage,
    StartConversation,
    UnreadTotal,
)
from api.services import messages as service

router = APIRouter(prefix="/conversations", tags=["messages"])
directory = APIRouter(tags=["messages"])

ConversationId = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse,
          "description": "`idempotency_key_required`: a write sent without an Idempotency-Key."},
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Messages are for staff: every dealer, "
                                                 "distributor and sub-dealer gets this."},
    404: {"model": ErrorResponse, "description": "Not a conversation you are in."},
    422: {"model": ErrorResponse, "description": "A field needs correcting; see `fields`."},
}


async def _idem(db: DbSession, claims: Claims, idem: IdemKey, route: str, body: BaseModel,
                work: Callable[[], Awaitable[tuple[int, Any]]]) -> JSONResponse:
    async def run() -> tuple[int, dict]:
        code, out = await work()
        return code, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=payload_digest(body.model_dump(mode="json")),
                                   work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@directory.get("/staff-directory", response_model=Envelope[list[Person]], responses=_ERRORS)
async def staff_directory(db: DbSession, caller: CallerDep,
                          q: Annotated[str | None, Query(max_length=100,
                                                         description="Part of a name.")] = None,
                          limit: Annotated[int, Query(ge=1, le=100)] = 50,
                          ) -> Envelope[list[Person]]:
    """Colleagues you can message: every active staff member but you, by name."""
    return Envelope(data=await service.staff_directory(db, caller, q=q, limit=limit))


@router.get("", response_model=ConversationList, responses=_ERRORS)
async def list_conversations(db: DbSession, caller: CallerDep) -> ConversationList:
    """Your conversations, most recent first (at most 100), with each one's unread
    count and the total. A conversation opened but never written in is not listed.
    Poll for new messages; there is no push."""
    return await service.list_conversations(db, caller)


@router.post("", response_model=Envelope[Conversation], status_code=201, responses=_ERRORS)
async def start_conversation(body: StartConversation, db: DbSession, caller: CallerDep,
                             claims: Claims, idem: IdemKey) -> JSONResponse:
    """Open a conversation with a colleague, or get the one you already have
    (`200`; a new one is `201`). `422` on `participant_id` for yourself, or
    someone who is not active staff."""
    async def work() -> tuple[int, Any]:
        created, conv = await service.start(db, caller, body)
        return (201 if created else 200), conv
    return await _idem(db, claims, idem, "POST /api/v1/conversations", body, work)


@router.get("/{conversation_id}/messages", response_model=MessagePage, responses=_ERRORS)
async def list_messages(conversation_id: ConversationId, db: DbSession, caller: CallerDep,
                        cursor: Annotated[str | None, Query(description="From "
                                          "`meta.next_cursor`: older messages.")] = None,
                        limit: Annotated[int, Query(ge=1, le=100)] = 50) -> MessagePage:
    """A page of the thread, oldest first. The first page is the newest; follow
    `meta.next_cursor` for older ones."""
    return await service.messages(db, caller, conversation_id, cursor=cursor, limit=limit)


@router.post("/{conversation_id}/messages", response_model=Envelope[Message], status_code=201,
             responses=_ERRORS)
async def send_message(conversation_id: ConversationId, body: SendMessage, db: DbSession,
                       caller: CallerDep, claims: Claims, idem: IdemKey) -> JSONResponse:
    """Send a message, optionally linking a lead you can see (`422` on `resource`
    otherwise). `422 participant_inactive` when the colleague has left. Sending
    marks the conversation read for you."""
    async def work() -> tuple[int, Any]:
        return 201, await service.send(db, caller, conversation_id, body)
    return await _idem(db, claims, idem, f"POST /api/v1/conversations/{conversation_id}/messages",
                       body, work)


@router.post("/{conversation_id}/read", response_model=Envelope[UnreadTotal], responses=_ERRORS)
async def mark_read(conversation_id: ConversationId, body: MarkRead, db: DbSession,
                    caller: CallerDep, claims: Claims, idem: IdemKey) -> JSONResponse:
    """Mark the conversation read up to `up_to`, the newest message your screen
    shows; left out, everything so far. Send `up_to` whenever a thread is on
    screen: a message that arrives while this call runs then stays unread. Leave
    it out only for "mark all read" from the inbox. A mark never moves
    backwards. Answers your new unread total."""
    async def work() -> tuple[int, Any]:
        return 200, await service.mark_read(db, caller, conversation_id, body)
    return await _idem(db, claims, idem, f"POST /api/v1/conversations/{conversation_id}/read",
                       body, work)
