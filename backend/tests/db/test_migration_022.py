"""Migration 022: the lead timeline names the actor of events a definer wrote,
for staff only."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db import test_migration_018 as m18

pytestmark = [pytest.mark.db, pytest.mark.rls]

PEOPLE = "SELECT id::text, name FROM lead_event_people(CAST(:l AS uuid))"


async def _unnamed_event(db: AsyncSession, lead: str, actor: str) -> None:
    """The shape of approval.decided and the other definer-written events."""
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('lead', CAST(:l AS uuid), CAST(:l AS uuid), 'quotation.approval_requested', "
        "CAST(:a AS uuid), '{}'::jsonb)"), {"l": lead, "a": actor})


async def test_staff_get_the_name_of_an_unnamed_events_actor(db: AsyncSession) -> None:
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    await _unnamed_event(db, lead, w.dm)
    await m13._as(db, w.officer)
    named = dict((await db.execute(text(PEOPLE), {"l": lead})).all())
    await m13._as_owner(db)
    assert w.dm in named, named


async def test_a_dealer_gets_no_actor_names(db: AsyncSession) -> None:
    """Question 15.14: these are mostly decider events."""
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    await db.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) WHERE id = CAST(:l AS uuid)"),
                     {"p": w.partner, "l": lead})
    await _unnamed_event(db, lead, w.dm)
    await m13._as(db, w.dealer)
    named = dict((await db.execute(text(PEOPLE), {"l": lead})).all())
    await m13._as_owner(db)
    assert w.dm not in named, named


async def test_an_event_that_carries_its_name_is_left_to_it(db: AsyncSession) -> None:
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('lead', CAST(:l AS uuid), CAST(:l AS uuid), 'lead.note_added', CAST(:a AS uuid), "
        "'{\"actor_name\": \"Asha\"}'::jsonb)"), {"l": lead, "a": w.dm})
    await m13._as(db, w.officer)
    named = dict((await db.execute(text(PEOPLE), {"l": lead})).all())
    await m13._as_owner(db)
    assert w.dm not in named, "only unnamed events are looked up"
