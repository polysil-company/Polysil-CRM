"""Migration 024 (FS-019): conversations and messages, executed as app_role."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db import test_migration_018 as m18

pytestmark = [pytest.mark.db, pytest.mark.rls]


async def _pair(db: AsyncSession, w: m18.World) -> str:
    await m13._as(db, w.officer)
    cid = str((await db.execute(text("SELECT id FROM conversation_open(CAST(:p AS uuid))"), {"p": w.dm})).scalar_one())
    await db.execute(text("INSERT INTO message (conversation_id, sender_id, body) VALUES (CAST(:c AS uuid), app_current_user_id(), 'hi')"), {"c": cid})
    await m13._as_owner(db)
    return cid


async def test_nobody_else_reads_or_writes_a_conversation(db: AsyncSession) -> None:
    w = await m18._world(db)
    cid = await _pair(db, w)
    await m13._as(db, w.officer_b)
    assert (await db.execute(text("SELECT count(*) FROM message WHERE conversation_id = CAST(:c AS uuid)"), {"c": cid})).scalar_one() == 0
    await m13._refused(db, "INSERT INTO message (conversation_id, sender_id, body) VALUES (CAST(:c AS uuid), app_current_user_id(), 'x')", {"c": cid}, "42501")
    assert (await db.execute(text("SELECT conversation_mark_read(CAST(:c AS uuid), NULL)"), {"c": cid})).scalar_one() is False
    await m13._as_owner(db)


async def test_the_read_marks_move_only_through_the_definers(db: AsyncSession) -> None:
    """Review B-1: a column grant let one side reset the other's mark."""
    w = await m18._world(db)
    cid = await _pair(db, w)
    await m13._as(db, w.officer)
    await m13._refused(db, "UPDATE conversation SET a_read_at = now(), b_read_at = now() WHERE id = CAST(:c AS uuid)", {"c": cid}, "42501")
    await m13._refused(db, "UPDATE message SET body = 'edited' WHERE conversation_id = CAST(:c AS uuid)", {"c": cid}, "42501")
    await m13._refused(db, "DELETE FROM message WHERE conversation_id = CAST(:c AS uuid)", {"c": cid}, "42501")
    await m13._refused(db, "INSERT INTO message (conversation_id, sender_id, body) VALUES (CAST(:c AS uuid), CAST(:o AS uuid), 'as them')",
                       {"c": cid, "o": w.dm}, "42501")
    await m13._as_owner(db)


async def test_messages_are_stamped_in_order_and_the_sender_reads_their_own(db: AsyncSession) -> None:
    """Review B-2: created_at strictly increases, and the sender's mark is their message."""
    w = await m18._world(db)
    cid = await _pair(db, w)
    await m13._as(db, w.dm)
    for body in ("one", "two", "three"):
        await db.execute(text("INSERT INTO message (conversation_id, sender_id, body) VALUES (CAST(:c AS uuid), app_current_user_id(), :b)"),
                         {"c": cid, "b": body})
    await m13._as_owner(db)
    stamps = (await db.execute(text("SELECT created_at FROM message WHERE conversation_id = CAST(:c AS uuid) ORDER BY created_at"), {"c": cid})).scalars().all()
    assert len(stamps) == 4 and len(set(stamps)) == 4, "no two messages share a time, even in one transaction"
    c = (await db.execute(text("SELECT user_a, a_read_at, b_read_at, last_message_at FROM conversation WHERE id = CAST(:c AS uuid)"), {"c": cid})).one()
    dm_mark = c.a_read_at if str(c.user_a) == w.dm else c.b_read_at
    assert dm_mark == c.last_message_at == stamps[-1]


async def test_a_dealer_cannot_open_a_conversation(db: AsyncSession) -> None:
    w = await m18._world(db)
    await m13._as(db, w.dealer)
    await m13._refused(db, "SELECT * FROM conversation_open(CAST(:p AS uuid))", {"p": w.officer}, "42501")
    assert (await db.execute(text("SELECT count(*) FROM messages_staff_directory(NULL, 100)"))).scalar_one() == 0
    await m13._as_owner(db)
