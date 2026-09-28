"""Migration 021 (FS-016): the crop list, the lead's crops and land, and the
people a lead's assignment events name, executed as the roles that call them."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db import test_migration_018 as m18

pytestmark = [pytest.mark.db, pytest.mark.rls]

PEOPLE = "SELECT id::text, name FROM lead_event_people(CAST(:l AS uuid))"


async def _assigned(db: AsyncSession, w: m18.World, lead: str) -> None:
    """A handover from the district manager to the officer, and a partner."""
    payload = {"owner_user_id": w.officer, "previous_owner_user_id": w.dm,
               "assigned_partner_id": w.partner, "handover": True}
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('lead', CAST(:l AS uuid), CAST(:l AS uuid), 'lead.assigned', CAST(:a AS uuid), CAST(:p AS jsonb))"),
        {"l": lead, "a": w.admin, "p": json.dumps(payload)})


async def test_whoever_sees_the_lead_gets_the_names_its_history_holds(db: AsyncSession) -> None:
    """Plan review B-2: read as the officer, whose users scope does not reach the
    district manager, the previous owner is still named (code review F-4a)."""
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    await _assigned(db, w, lead)
    await m13._as(db, w.officer)
    named = dict((await db.execute(text(PEOPLE), {"l": lead})).all())
    through_scope = (await db.execute(text(
        "SELECT count(*) FROM people_names(ARRAY[CAST(:u AS uuid)])"), {"u": w.dm})).scalar_one()
    await m13._as_owner(db)
    assert w.dm in named and w.officer in named, named
    assert through_scope == 0, "the ordinary lookup would not have named the previous owner"


async def test_a_malformed_old_payload_does_not_break_the_history(db: AsyncSession) -> None:
    """Code review F-1: one bad value was a 500 on every read of the lead."""
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    await _assigned(db, w, lead)
    for bad in ('""', '"not-a-uuid"', "123"):
        await db.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
            "VALUES ('lead', CAST(:l AS uuid), CAST(:l AS uuid), 'lead.assigned', CAST(:a AS uuid), "
            "CAST(:p AS jsonb))"), {"l": lead, "a": w.admin, "p": '{"owner_user_id": ' + bad + '}'})
    await m13._as(db, w.officer)
    named = dict((await db.execute(text(PEOPLE), {"l": lead})).all())
    await m13._as_owner(db)
    assert w.dm in named


async def test_a_dealer_is_not_told_a_competing_dealers_name(db: AsyncSession) -> None:
    """Code review F-3a: the lead was once another dealer's."""
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    other = str((await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, mobile, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'Rival Drip', :m, CAST(:t AS uuid), 'dealer') RETURNING id"),
        {"c": f"RIV{uuid.uuid4().hex[:8]}".upper(), "m": "9193" + f"{uuid.uuid4().int % 10**8:08d}",
         "t": w.district})).scalar_one())
    await db.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) WHERE id = CAST(:l AS uuid)"),
                     {"p": w.partner, "l": lead})
    for partner in (other, w.partner):
        await db.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
            "VALUES ('lead', CAST(:l AS uuid), CAST(:l AS uuid), 'lead.assigned', CAST(:a AS uuid), "
            "CAST(:p AS jsonb))"), {"l": lead, "a": w.dm, "p": json.dumps({"assigned_partner_id": partner})})
    await m13._as(db, w.dealer)
    named = dict((await db.execute(text(PEOPLE), {"l": lead})).all())
    await m13._as_owner(db)
    assert w.partner in named and other not in named, named
    await m13._as(db, w.dm)
    staff = dict((await db.execute(text(PEOPLE), {"l": lead})).all())
    await m13._as_owner(db)
    assert other in staff, "staff still see both"


async def test_nobody_is_named_for_a_lead_the_reader_cannot_see(db: AsyncSession) -> None:
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    await _assigned(db, w, lead)
    await m13._as(db, w.officer_b)
    named = (await db.execute(text(PEOPLE), {"l": lead})).all()
    await m13._as_owner(db)
    assert named == [], "another office's officer learns nobody"


async def test_the_crop_array_refuses_null_empty_and_eleven(db: AsyncSession) -> None:
    w = await m18._world(db)
    lead = await m18._lead(db, w, w.officer, w.a)
    for value in ([None], [""], [f"c{i}" for i in range(11)]):
        await m13._refused(db, "UPDATE lead SET crops = CAST(:v AS citext[]) WHERE id = CAST(:l AS uuid)",
                           {"v": value, "l": lead}, "23514")
    await m13._refused(db, "UPDATE lead SET land_acres = 100000 WHERE id = CAST(:l AS uuid)",
                       {"l": lead}, "23514")


async def test_the_crop_list_is_seeded_and_only_masters_edit_writes_it(db: AsyncSession) -> None:
    w = await m18._world(db)
    codes = set((await db.execute(text("SELECT code::text FROM crop"))).scalars())
    assert len(codes) >= 78 and "redgram_pigeonpea" in codes and "select_crop_here" not in codes
    await m13._refused(db, "INSERT INTO crop (code, name) VALUES ('UPPER_CASE', 'U')", {}, "23514")
    await m13._as(db, w.officer)
    await m13._refused(db, "INSERT INTO crop (code, name) VALUES ('zz_test', 'Z')", {}, "42501")
    await m13._as_owner(db)
