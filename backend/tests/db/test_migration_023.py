"""Migration 023 (FS-018): notifications, executed as the roles that touch them."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db import test_migration_018 as m18

pytestmark = [pytest.mark.db, pytest.mark.rls]


async def _event(db: AsyncSession, w: m18.World, lead: str, kind: str = "lead.stage_changed") -> str:
    return str((await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('lead', CAST(:l AS uuid), CAST(:l AS uuid), :k, CAST(:a AS uuid), '{}'::jsonb) RETURNING id"),
        {"l": lead, "k": kind, "a": w.dm})).scalar_one())


async def _notify(db: AsyncSession, event: str, to: str, decided: bool) -> None:
    await db.execute(text(
        "SELECT notify_one(e, CAST(:to AS uuid), 'order_returned', 'Order X was returned', NULL, "
        "'lead', e.entity_id, 'X', :d) FROM activity_event e WHERE e.id = CAST(:e AS uuid)"),
        {"e": event, "to": to, "d": decided})


async def test_a_dealer_is_never_told_who_decided(db: AsyncSession) -> None:
    """Review B-2: the actor is dropped at write time for a partner recipient."""
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    ev = await _event(db, w, lead)
    await _notify(db, ev, w.dealer, True)
    await _notify(db, ev, w.officer, True)
    rows = dict((await db.execute(text(
        "SELECT recipient_id::text, (actor_id, actor_name) FROM notification WHERE event_id = CAST(:e AS uuid)"),
        {"e": ev})).all())
    assert rows[w.dealer] == (None, None), rows
    assert rows[w.officer][0] is not None, "staff are told"


async def test_nobody_is_told_of_their_own_action_and_the_inactive_are_skipped(db: AsyncSession) -> None:
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    ev = await _event(db, w, lead)
    await _notify(db, ev, w.dm, False)          # the actor
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = CAST(:u AS uuid)"), {"u": w.officer_b})
    await _notify(db, ev, w.officer_b, False)
    n = (await db.execute(text("SELECT count(*) FROM notification WHERE event_id = CAST(:e AS uuid)"), {"e": ev})).scalar_one()
    assert n == 0


async def test_only_the_recipient_reads_and_only_read_at_changes(db: AsyncSession) -> None:
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    ev = await _event(db, w, lead)
    await _notify(db, ev, w.officer, False)
    await m13._as(db, w.officer_b)
    assert (await db.execute(text("SELECT count(*) FROM notification WHERE event_id = CAST(:e AS uuid)"), {"e": ev})).scalar_one() == 0
    r = await db.execute(text("UPDATE notification SET read_at = now() WHERE event_id = CAST(:e AS uuid)"), {"e": ev})
    assert r.rowcount == 0, "not theirs to mark"
    await m13._as_owner(db)
    await m13._as(db, w.officer)
    await m13._refused(db, "UPDATE notification SET title = 'x' WHERE event_id = CAST(:e AS uuid)", {"e": ev}, "42501")
    await m13._refused(db, "INSERT INTO notification (recipient_id, event_id, kind, title) "
                           "VALUES (CAST(:u AS uuid), gen_random_uuid(), 'x', 'x')", {"u": w.officer}, "42501")
    await m13._refused(db, "SELECT count(*) FROM notification_failure", {}, "42501")
    await m13._as_owner(db)
