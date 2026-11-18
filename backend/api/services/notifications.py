"""In-app notifications (FS-018). Written by the `notify_from_event()` trigger in
the same transaction as their event; read and marked here, under the recipient-only
policies, so a caller only ever touches their own."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import notifications as sch
from api.schemas.leads import UserRef
from api.services.leads import _decode_cursor, _encode_cursor

_MAX = 100

_TS = sa.DateTime(timezone=True)
n_t = sa.table("notification", sa.column("id"), sa.column("recipient_id"),
               sa.column("created_at", _TS), sa.column("read_at", _TS))


async def unread_count(db: AsyncSession) -> int:
    return int((await db.execute(text(
        "SELECT count(*) FROM notification "
        "WHERE recipient_id = app_current_user_id() AND read_at IS NULL"))).scalar_one())


def _to_notification(r: Any) -> sch.Notification:
    return sch.Notification(
        id=str(r.id), kind=r.kind, title=r.title, body=r.body,
        actor=UserRef(id=str(r.actor_id), full_name=r.actor_name or "") if r.actor_id else None,
        resource=sch.ResourceRef(type=r.resource_type, id=str(r.resource_id),
                                 label=r.resource_label or "")
        if r.resource_type and r.resource_id else None,
        created_at=r.created_at.isoformat(),
        read_at=r.read_at.isoformat() if r.read_at else None)


async def list_notifications(db: AsyncSession, *, limit: int = 20, cursor: str | None = None,
                             unread: bool = False) -> sch.NotificationPage:
    """Newest first, keyset-paged by (created_at, id)."""
    limit = max(1, min(limit, _MAX))
    where = ["recipient_id = app_current_user_id()"]
    params: dict[str, Any] = {"lim": limit + 1}
    if unread:
        where.append("read_at IS NULL")
    if cursor:
        at, nid = _decode_cursor(cursor)
        where.append("(created_at, id) < (:at, CAST(:nid AS uuid))")
        params.update(at=at, nid=nid)
    rows = (await db.execute(text(
        "SELECT id, kind, title, body, actor_id, actor_name, resource_type, resource_id, "
        "resource_label, created_at, read_at FROM notification WHERE " + " AND ".join(where) +
        " ORDER BY created_at DESC, id DESC LIMIT :lim"), params)).all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.created_at, str(last.id))
        rows = rows[:limit]
    return sch.NotificationPage(
        data=[_to_notification(r) for r in rows],
        meta=sch.NotificationMeta(unread_count=await unread_count(db), next_cursor=next_cursor))


async def mark_read(db: AsyncSession, body: sch.MarkRead) -> sch.UnreadCount:
    """The policy limits the update to the caller's own rows; others are ignored."""
    if body.all:
        await db.execute(text(
            "UPDATE notification SET read_at = now() "
            "WHERE recipient_id = app_current_user_id() AND read_at IS NULL"))
    else:
        await db.execute(text(
            "UPDATE notification SET read_at = now() "
            "WHERE id = ANY(CAST(:ids AS uuid[])) AND read_at IS NULL"), {"ids": body.ids})
    return sch.UnreadCount(unread_count=await unread_count(db))
