"""Staff messages (FS-019): one-to-one conversations under participant-only
policies. Writes to `conversation` go through its definers; `message` inserts
under its own policy, and a trigger stamps it under the conversation's lock."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.errors import ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import messages as sch
from api.services.leads import _decode_cursor, _encode_cursor

_LIMIT = 100


def _staff(caller: Caller) -> None:
    if caller.partner_id is not None or caller.org_unit_id is None:
        raise ForbiddenError("Messages are for Polysil staff.")


def _state(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _message(r: Any) -> sch.Message:
    return sch.Message(
        id=str(r.id), conversation_id=str(r.conversation_id), sender_id=str(r.sender_id),
        body=r.body,
        resource=sch.ResourceRef(type=r.resource_type, id=str(r.resource_id),
                                 label=r.resource_label) if r.resource_type else None,
        created_at=r.created_at.isoformat())


async def _unread(db: AsyncSession) -> dict[str, int]:
    """Per conversation: the other side's messages after my mark."""
    rows = (await db.execute(text(
        "SELECT p.conversation_id, count(m.id) AS n FROM conversation_peers() p "
        "JOIN message m ON m.conversation_id = p.conversation_id "
        "  AND m.sender_id <> app_current_user_id() "
        "  AND m.created_at > COALESCE(p.my_read_at, '-infinity') "
        "GROUP BY p.conversation_id"))).all()
    return {str(r.conversation_id): int(r.n) for r in rows}


async def list_conversations(db: AsyncSession, caller: Caller) -> sch.ConversationList:
    """Most recent first; a conversation opened but never used is not listed."""
    _staff(caller)
    peers = {str(p.conversation_id): p for p in
             (await db.execute(text("SELECT * FROM conversation_peers()"))).all()}
    unread = await _unread(db)
    convs = (await db.execute(text(
        "SELECT c.id, c.last_message_at, m.id AS m_id, m.conversation_id, m.sender_id, m.body, "
        "       m.resource_type, m.resource_id, m.resource_label, m.created_at "
        "  FROM conversation c "
        "  JOIN LATERAL (SELECT * FROM message x WHERE x.conversation_id = c.id "
        "                ORDER BY x.created_at DESC, x.id DESC LIMIT 1) m ON true "
        " WHERE c.last_message_at IS NOT NULL "
        " ORDER BY c.last_message_at DESC, c.id DESC LIMIT :lim"), {"lim": _LIMIT})).all()
    data = []
    for c in convs:
        p = peers.get(str(c.id))
        if p is None:
            continue
        last = sch.Message(
            id=str(c.m_id), conversation_id=str(c.conversation_id), sender_id=str(c.sender_id),
            body=c.body,
            resource=sch.ResourceRef(type=c.resource_type, id=str(c.resource_id),
                                     label=c.resource_label) if c.resource_type else None,
            created_at=c.created_at.isoformat())
        data.append(sch.Conversation(
            id=str(c.id), participant=_person(p), last_message=last,
            unread_count=unread.get(str(c.id), 0), updated_at=c.last_message_at.isoformat()))
    return sch.ConversationList(data=data,
                                meta=sch.ConversationMeta(unread_total=sum(unread.values())))


def _person(p: Any) -> sch.Person:
    return sch.Person(id=str(p.id), full_name=p.full_name, role_name=p.role_name,
                      org_unit_name=p.org_unit_name, is_active=bool(p.is_active))


async def _conversation(db: AsyncSession, conversation_id: str) -> sch.Conversation:
    peer = (await db.execute(text(
        "SELECT * FROM conversation_peers() WHERE conversation_id = CAST(:c AS uuid)"),
        {"c": conversation_id})).one_or_none()
    if peer is None:
        raise NotFoundError("No such conversation.")
    c = (await db.execute(text(
        "SELECT created_at, last_message_at FROM conversation WHERE id = CAST(:c AS uuid)"),
        {"c": conversation_id})).one()
    last = (await db.execute(text(
        "SELECT * FROM message WHERE conversation_id = CAST(:c AS uuid) "
        "ORDER BY created_at DESC, id DESC LIMIT 1"), {"c": conversation_id})).one_or_none()
    unread = (await _unread(db)).get(conversation_id, 0)
    return sch.Conversation(id=conversation_id, participant=_person(peer),
                            last_message=_message(last) if last else None,
                            unread_count=unread,
                            updated_at=(c.last_message_at or c.created_at).isoformat())


async def start(db: AsyncSession, caller: Caller,
                body: sch.StartConversation) -> tuple[bool, sch.Conversation]:
    """(created, the conversation): the existing one if the pair already talks."""
    _staff(caller)
    try:
        async with db.begin_nested():
            row = (await db.execute(text("SELECT * FROM conversation_open(CAST(:p AS uuid))"),
                                    {"p": body.participant_id})).one()
    except DBAPIError as exc:
        if _state(exc) == "MSGPT":
            raise ValidationFailed(
                fields={"participant_id": "not someone you can message"}) from exc
        if _state(exc) == "42501":
            raise ForbiddenError("Messages are for Polysil staff.") from exc
        raise
    return bool(row.created), await _conversation(db, str(row.id))


async def get(db: AsyncSession, caller: Caller, conversation_id: str) -> sch.Conversation:
    """One conversation the caller is in, written in or not (BE-021)."""
    _staff(caller)
    return await _conversation(db, conversation_id)


async def _peer(db: AsyncSession, conversation_id: str) -> Any:
    peer = (await db.execute(text(
        "SELECT * FROM conversation_peers() WHERE conversation_id = CAST(:c AS uuid)"),
        {"c": conversation_id})).one_or_none()
    if peer is None:
        raise NotFoundError("No such conversation.")
    return peer


async def messages(db: AsyncSession, caller: Caller, conversation_id: str, *,
                   cursor: str | None = None, limit: int = 50) -> sch.MessagePage:
    """The newest `limit` before the cursor, returned oldest first."""
    _staff(caller)
    await _peer(db, conversation_id)
    limit = max(1, min(limit, _LIMIT))
    params: dict[str, Any] = {"c": conversation_id, "lim": limit + 1}
    before = ""
    if cursor:
        at, mid = _decode_cursor(cursor)
        before = " AND (created_at, id) < (:at, CAST(:mid AS uuid))"
        params.update(at=at, mid=mid)
    rows = (await db.execute(text(
        "SELECT * FROM message WHERE conversation_id = CAST(:c AS uuid)" + before +
        " ORDER BY created_at DESC, id DESC LIMIT :lim"), params)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        oldest = rows[-1]
        next_cursor = _encode_cursor(oldest.created_at, str(oldest.id))
    return sch.MessagePage(data=[_message(r) for r in reversed(rows)],
                           meta=sch.MessageMeta(next_cursor=next_cursor))


async def send(db: AsyncSession, caller: Caller, conversation_id: str,
               body: sch.SendMessage) -> sch.Message:
    _staff(caller)
    peer = await _peer(db, conversation_id)
    if not peer.is_active:
        raise ValidationFailed("That colleague has left.", code="participant_inactive",
                               fields={"participant": "no longer active"})
    label = None
    if body.resource is not None:
        # a lead the sender cannot see is never linked (FS-019 rule 4)
        label = (await db.execute(text(
            "SELECT inquiry_no::text FROM lead WHERE id = CAST(:l AS uuid) AND lead_visible(id)"),
            {"l": body.resource.id})).scalar_one_or_none()
        if label is None:
            raise ValidationFailed(fields={"resource": "not a lead you can see"})
    row = (await db.execute(text(
        "INSERT INTO message (conversation_id, sender_id, body, resource_type, resource_id, "
        "resource_label) VALUES (CAST(:c AS uuid), app_current_user_id(), :b, :t, "
        "CAST(:r AS uuid), :lbl) RETURNING *"),
        {"c": conversation_id, "b": body.body, "t": "lead" if body.resource else None,
         "r": body.resource.id if body.resource else None, "lbl": label})).one()
    return _message(row)


async def mark_read(db: AsyncSession, caller: Caller, conversation_id: str,
                    body: sch.MarkRead) -> sch.UnreadTotal:
    _staff(caller)
    try:
        async with db.begin_nested():
            ok: bool = (await db.execute(text(
                "SELECT conversation_mark_read(CAST(:c AS uuid), CAST(:u AS uuid))"),
                {"c": conversation_id, "u": body.up_to})).scalar_one()
    except DBAPIError as exc:
        if _state(exc) == "MSGUP":
            raise ValidationFailed(fields={"up_to": "not a message of this conversation"}) from exc
        raise
    if not ok:
        raise NotFoundError("No such conversation.")
    return sch.UnreadTotal(unread_total=sum((await _unread(db)).values()))


async def staff_directory(db: AsyncSession, caller: Caller, *, q: str | None,
                          limit: int) -> list[sch.Person]:
    _staff(caller)
    rows = (await db.execute(text(
        "SELECT * FROM messages_staff_directory(:q, :lim)"), {"q": q or None, "lim": limit})).all()
    return [sch.Person(id=str(r.id), full_name=r.full_name, role_name=r.role_name,
                       org_unit_name=r.org_unit_name) for r in rows]
