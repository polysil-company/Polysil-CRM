"""/conversations and /staff-directory (FS-019): staff messages, one to one and
in groups (FS-048)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import CallerDep, Claims, DbSession, IdemKey
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.messages import (
    AddMembers,
    Conversation,
    ConversationList,
    CreateGroup,
    MarkRead,
    Member,
    Message,
    MessagePage,
    Person,
    RenameGroup,
    SendMessage,
    StartConversation,
    UnreadTotal,
)
from api.services import messages as service

router = APIRouter(prefix="/conversations", tags=["messages"])
directory = APIRouter(tags=["messages"])

ConversationId = Annotated[str, Path(pattern=UUID_RE)]
UserId = Annotated[str, Path(pattern=UUID_RE)]

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
        if isinstance(out, list):
            return code, {"data": [x.model_dump(mode="json") for x in out]}
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
    """Your conversations, one to one and groups, most recent first (at most 100),
    with each one's unread count and the total. A one-to-one conversation opened but
    never written in is not listed; a group is listed from its creation. Poll for new
    messages; there is no push."""
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


@router.get("/{conversation_id}", response_model=Envelope[Conversation], responses=_ERRORS)
async def get_conversation(conversation_id: ConversationId, db: DbSession,
                           caller: CallerDep) -> Envelope[Conversation]:
    """One of your conversations: the colleague, the last message and your unread
    count. Works before anyone has written in it, so a thread opened from a link or
    after a reload can name whom it writes to. `404` when it is not yours."""
    return Envelope(data=await service.get(db, caller, conversation_id))


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


# ── groups (FS-048) ──────────────────────────────────────────────────────────

@router.post("/groups", response_model=Envelope[Conversation], status_code=201, responses=_ERRORS)
async def create_group(body: CreateGroup, db: DbSession, caller: CallerDep, claims: Claims,
                       idem: IdemKey) -> JSONResponse:
    """Start a group: a name and 1 to 49 colleagues. You are added and manage it.
    `422` on `member_ids` for anyone who is not active staff. Two calls make two
    groups; the Idempotency-Key covers a retry."""
    async def work() -> tuple[int, Any]:
        return 201, await service.create_group(db, caller, body)
    return await _idem(db, claims, idem, "POST /api/v1/conversations/groups", body, work)


@router.patch("/{conversation_id}", response_model=Envelope[Conversation], responses=_ERRORS)
async def rename_group(conversation_id: ConversationId, body: RenameGroup, db: DbSession,
                       caller: CallerDep, claims: Claims, idem: IdemKey) -> JSONResponse:
    """Rename a group. The manager only (`403`); `422 not_a_group` for a one-to-one
    conversation; `404` when you are not in it."""
    async def work() -> tuple[int, Any]:
        return 200, await service.rename(db, caller, conversation_id, body)
    return await _idem(db, claims, idem, f"PATCH /api/v1/conversations/{conversation_id}",
                       body, work)


@router.get("/{conversation_id}/members", response_model=Envelope[list[Member]], responses=_ERRORS)
async def list_members(conversation_id: ConversationId, db: DbSession,
                       caller: CallerDep) -> Envelope[list[Member]]:
    """Everyone who has been in the group, current members first. Use it to name
    each message's sender. `404` for a group you are not in, or a one-to-one
    conversation."""
    return Envelope(data=await service.members(db, caller, conversation_id))


@router.post("/{conversation_id}/members", response_model=Envelope[list[Member]],
             responses=_ERRORS)
async def add_members(conversation_id: ConversationId, body: AddMembers, db: DbSession,
                      caller: CallerDep, claims: Claims, idem: IdemKey) -> JSONResponse:
    """Add colleagues; any member may. Someone already in is ignored; someone who left
    comes back and sees the whole history. `422 group_full` past 50, and then nobody
    is added. Answers the member list."""
    async def work() -> tuple[int, Any]:
        return 200, await service.add_members(db, caller, conversation_id, body)
    return await _idem(db, claims, idem, f"POST /api/v1/conversations/{conversation_id}/members",
                       body, work)


@router.delete("/{conversation_id}/members/{user_id}", status_code=204, responses=_ERRORS)
async def remove_member(conversation_id: ConversationId, user_id: UserId, db: DbSession,
                        caller: CallerDep, claims: Claims, idem: IdemKey) -> Response:
    """Your own id: leave the group; it disappears for you, history included. Someone
    else's: the manager removes them (`403` otherwise). When the manager leaves, the
    longest-standing active member takes over. `404` when either of you is not in."""
    async def work() -> tuple[int, dict[str, Any]]:
        await service.remove_member(db, caller, conversation_id, user_id)
        return 204, {}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub,
        route=f"DELETE /api/v1/conversations/{conversation_id}/members/{user_id}",
        payload_hash=payload_digest({}), work=work)
    if outcome.status_code == 204:
        return Response(status_code=204)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
