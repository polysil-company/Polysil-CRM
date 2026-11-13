"""Staff messages (FS-019): one-to-one conversations under participant-only
policies, and groups (FS-048) under member-only ones. Writes to `conversation`
and `conversation_member` go through their definers; `message` inserts under its
own policy, and a trigger stamps it under the conversation's lock."""

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


_MINE = ("SELECT conversation_id, my_read_at FROM conversation_peers() "
         "UNION ALL SELECT conversation_id, my_read_at FROM conversation_groups()")


async def _unread(db: AsyncSession) -> dict[str, int]:
    """Per conversation, pairs and groups: the others' messages after my mark."""
    rows = (await db.execute(text(
        f"SELECT p.conversation_id, count(m.id) AS n FROM ({_MINE}) p "
        "JOIN message m ON m.conversation_id = p.conversation_id "
        "  AND m.sender_id <> app_current_user_id() "
        "  AND m.created_at > COALESCE(p.my_read_at, '-infinity') "
        "GROUP BY p.conversation_id"))).all()
    return {str(r.conversation_id): int(r.n) for r in rows}


async def _groups(db: AsyncSession) -> dict[str, Any]:
    return {str(g.conversation_id): g for g in
            (await db.execute(text("SELECT * FROM conversation_groups()"))).all()}


def _group(g: Any, caller: Caller) -> sch.GroupInfo:
    manager = str(g.manager_id) if g.manager_id else None
    return sch.GroupInfo(name=g.name, member_count=int(g.member_count), manager_id=manager,
                         i_manage=manager == caller.user_id)


async def list_conversations(db: AsyncSession, caller: Caller) -> sch.ConversationList:
    """Most recent first; a conversation opened but never used is not listed."""
    _staff(caller)
    peers = {str(p.conversation_id): p for p in
             (await db.execute(text("SELECT * FROM conversation_peers()"))).all()}
    groups = await _groups(db)
    unread = await _unread(db)
    # a pair shows once written in; a group from its creation (FS-048 edge E-5)
    convs = (await db.execute(text(
        "SELECT c.id, c.kind, COALESCE(c.last_message_at, c.created_at) AS at, "
        "       m.id AS m_id, m.conversation_id, m.sender_id, m.body, "
        "       m.resource_type, m.resource_id, m.resource_label, m.created_at "
        "  FROM conversation c "
        "  LEFT JOIN LATERAL (SELECT * FROM message x WHERE x.conversation_id = c.id "
        "                ORDER BY x.created_at DESC, x.id DESC LIMIT 1) m ON true "
        " WHERE c.last_message_at IS NOT NULL OR c.kind = 'group' "
        " ORDER BY COALESCE(c.last_message_at, c.created_at) DESC, c.id DESC LIMIT :lim"),
        {"lim": _LIMIT})).all()
    data = []
    for c in convs:
        p, g = peers.get(str(c.id)), groups.get(str(c.id))
        if p is None and g is None:
            continue
        last = sch.Message(
            id=str(c.m_id), conversation_id=str(c.conversation_id), sender_id=str(c.sender_id),
            body=c.body,
            resource=sch.ResourceRef(type=c.resource_type, id=str(c.resource_id),
                                     label=c.resource_label) if c.resource_type else None,
            created_at=c.created_at.isoformat()) if c.m_id else None
        data.append(sch.Conversation(
            id=str(c.id), kind=c.kind, participant=_person(p) if p else None,
            group=_group(g, caller) if g else None, last_message=last,
            unread_count=unread.get(str(c.id), 0), updated_at=c.at.isoformat()))
    return sch.ConversationList(data=data,
                                meta=sch.ConversationMeta(unread_total=sum(unread.values())))


def _person(p: Any) -> sch.Person:
    return sch.Person(id=str(p.id), full_name=p.full_name, role_name=p.role_name,
                      org_unit_name=p.org_unit_name, is_active=bool(p.is_active))


async def _conversation(db: AsyncSession, conversation_id: str,
                        caller: Caller) -> sch.Conversation:
    peer, group = await _which(db, conversation_id)
    c = (await db.execute(text(
        "SELECT created_at, last_message_at FROM conversation WHERE id = CAST(:c AS uuid)"),
        {"c": conversation_id})).one()
    last = (await db.execute(text(
        "SELECT * FROM message WHERE conversation_id = CAST(:c AS uuid) "
        "ORDER BY created_at DESC, id DESC LIMIT 1"), {"c": conversation_id})).one_or_none()
    unread = (await _unread(db)).get(conversation_id, 0)
    return sch.Conversation(id=conversation_id, kind="group" if group else "direct",
                            participant=_person(peer) if peer else None,
                            group=_group(group, caller) if group else None,
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
    return bool(row.created), await _conversation(db, str(row.id), caller)


async def get(db: AsyncSession, caller: Caller, conversation_id: str) -> sch.Conversation:
    """One conversation the caller is in, written in or not (BE-021)."""
    _staff(caller)
    return await _conversation(db, conversation_id, caller)


async def _which(db: AsyncSession, conversation_id: str) -> tuple[Any, Any]:
    """(the other person, None) for a pair, (None, the group) for a group I am in;
    404 for anything else, a group I left included (FS-048 rule 4)."""
    peer = (await db.execute(text(
        "SELECT * FROM conversation_peers() WHERE conversation_id = CAST(:c AS uuid)"),
        {"c": conversation_id})).one_or_none()
    if peer is not None:
        return peer, None
    group = (await db.execute(text(
        "SELECT * FROM conversation_groups() WHERE conversation_id = CAST(:c AS uuid)"),
        {"c": conversation_id})).one_or_none()
    if group is None:
        raise NotFoundError("No such conversation.")
    return None, group


async def messages(db: AsyncSession, caller: Caller, conversation_id: str, *,
                   cursor: str | None = None, limit: int = 50) -> sch.MessagePage:
    """The newest `limit` before the cursor, returned oldest first."""
    _staff(caller)
    await _which(db, conversation_id)
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
    peer, _ = await _which(db, conversation_id)
    # a group stays writable when a member leaves the company (FS-048 rule 5)
    if peer is not None and not peer.is_active:
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
    try:
        async with db.begin_nested():
            row = (await db.execute(text(
                "INSERT INTO message (conversation_id, sender_id, body, resource_type, "
                "resource_id, resource_label) VALUES (CAST(:c AS uuid), app_current_user_id(), "
                ":b, :t, CAST(:r AS uuid), :lbl) RETURNING *"),
                {"c": conversation_id, "b": body.body, "t": "lead" if body.resource else None,
                 "r": body.resource.id if body.resource else None, "lbl": label})).one()
    except DBAPIError as exc:
        # left the group while sending: the stamp re-checks after its lock (FS-048 R-3)
        if _state(exc) == "MSGNF":
            raise NotFoundError("No such conversation.") from exc
        raise
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


# ── groups (FS-048) ──────────────────────────────────────────────────────────

async def _group_call(db: AsyncSession, sql: str, params: dict[str, Any], *,
                      field: str = "user_ids") -> Any:
    """One group definer, its refusals mapped. Run in a savepoint, so a refusal
    leaves the request's transaction usable."""
    try:
        async with db.begin_nested():
            return (await db.execute(text(sql), params)).scalar_one_or_none()
    except DBAPIError as exc:
        code = _state(exc)
        if code in ("MSGNF", "MSGNM"):
            raise NotFoundError("No such conversation or member.") from exc
        if code == "MSGPT":
            raise ValidationFailed(fields={field: "includes someone you cannot message"}) from exc
        if code == "MSGFL":
            raise ValidationFailed("A group holds at most 50 people.", code="group_full",
                                   fields={field: "too many"}) from exc
        if code == "MSGDR":
            raise ValidationFailed("Only a group has a name.", code="not_a_group",
                                   fields={"name": "a direct conversation has no name"}) from exc
        if code == "MSGST":
            raise ForbiddenError("Messages are for Polysil staff.") from exc
        if code == "42501":
            raise ForbiddenError("Only the group's manager can do that.") from exc
        raise


async def create_group(db: AsyncSession, caller: Caller, body: sch.CreateGroup) -> sch.Conversation:
    _staff(caller)
    gid = await _group_call(db, "SELECT group_create(:n, CAST(:u AS uuid[]))",
                            {"n": body.name, "u": body.member_ids}, field="member_ids")
    return await _conversation(db, str(gid), caller)


async def members(db: AsyncSession, caller: Caller, conversation_id: str) -> list[sch.Member]:
    """Everyone who has been in the group: current members first, then those who left."""
    _staff(caller)
    rows = (await db.execute(text("SELECT * FROM conversation_members(CAST(:c AS uuid))"),
                             {"c": conversation_id})).all()
    if not rows:
        raise NotFoundError("No such group.")
    return [sch.Member(person=_person(r), added_at=r.added_at.isoformat(),
                       left_at=r.left_at.isoformat() if r.left_at else None,
                       is_manager=bool(r.is_manager)) for r in rows]


async def add_members(db: AsyncSession, caller: Caller, conversation_id: str,
                      body: sch.AddMembers) -> list[sch.Member]:
    _staff(caller)
    await _group_call(db, "SELECT group_add(CAST(:c AS uuid), CAST(:u AS uuid[]))",
                      {"c": conversation_id, "u": body.user_ids})
    return await members(db, caller, conversation_id)


async def remove_member(db: AsyncSession, caller: Caller, conversation_id: str,
                        user_id: str) -> None:
    """Your own id: leave. Another's: the manager removes them."""
    _staff(caller)
    await _group_call(db, "SELECT group_leave(CAST(:c AS uuid), CAST(:u AS uuid))",
                      {"c": conversation_id, "u": user_id})


async def rename(db: AsyncSession, caller: Caller, conversation_id: str,
                 body: sch.RenameGroup) -> sch.Conversation:
    _staff(caller)
    await _group_call(db, "SELECT group_rename(CAST(:c AS uuid), :n)",
                      {"c": conversation_id, "n": body.name}, field="name")
    return await _conversation(db, conversation_id, caller)
