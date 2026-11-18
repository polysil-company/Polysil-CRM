"""084: a person's open leads follow them to a new office; closed leads stay, and
the lead's quotations follow it (012). Run as the owner, like the other migration
tests, so only the trigger decides."""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.db


async def test_open_leads_follow_the_owner_and_closed_ones_stay(db: AsyncSession) -> None:
    tag = uuid.uuid4().hex[:8]
    t = str((await db.execute(text(
        "SELECT id FROM territory WHERE level = 'district' AND deleted_at IS NULL LIMIT 1"))).scalar_one())
    made = []
    for k in ("a", "b"):
        made.append(str((await db.execute(text(
            "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 1, CAST(:t AS uuid)) RETURNING id"),
            {"n": f"t084 {k} {tag}", "t": t})).scalar_one()))
    a, b = made
    fo = str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, 'Mover', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'field_officer' RETURNING id"),
        {"e": f"t084_{tag}@polysil.in", "o": a})).scalar_one())
    src = str((await db.execute(text("SELECT id FROM lead_source ORDER BY id LIMIT 1"))).scalar_one())
    leads = {}
    for stage in ("new", "won", "contacted"):
        leads[stage] = str((await db.execute(text(
            "INSERT INTO lead (inquiry_no, farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id, "
            "  inquiry_type, mis_system_id, lead_source_id, stage, won_at) "
            "VALUES (:no, 'Farmer', :m, CAST(:t AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), 'commercial', (SELECT id FROM mis_system ORDER BY id LIMIT 1), "
            "  CAST(:s AS uuid), CAST(:st AS lead_stage), CASE WHEN :st = 'won' THEN now() END) RETURNING id"),
            {"no": f"T084/{tag}/{stage}", "m": "+9197" + f"{uuid.uuid4().int % 10**8:08d}", "t": t, "u": fo,
             "o": a, "s": src, "st": stage})).scalar_one())

    await db.execute(text("UPDATE app_user SET org_unit_id = CAST(:b AS uuid) WHERE id = CAST(:u AS uuid)"), {"b": b, "u": fo})

    office = {}
    for k, v in leads.items():
        office[k] = str((await db.execute(text("SELECT owner_org_unit_id FROM lead WHERE id = CAST(:l AS uuid)"), {"l": v})).scalar_one())
    assert office == {"new": b, "won": a, "contacted": b}
    events = (await db.execute(text(
        "SELECT lead_id::text, payload ->> 'previous_org_unit_id' AS prev FROM activity_event "
        "WHERE kind = 'lead.rehomed' AND lead_id = ANY(CAST(:ids AS uuid[]))"), {"ids": list(leads.values())})).all()
    assert {e.lead_id for e in events} == {leads["new"], leads["contacted"]}
    assert {e.prev for e in events} == {a}


async def test_a_move_into_an_office_with_no_area_moves_nothing(db: AsyncSession) -> None:
    """Code review F-1: rule 4 keeps a lead at the office covering its territory
    when the owner's office covers none, so such a move must not pull it to HQ."""
    tag = uuid.uuid4().hex[:8]
    t = str((await db.execute(text(
        "SELECT id FROM territory WHERE level = 'district' AND deleted_at IS NULL LIMIT 1"))).scalar_one())
    area = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 1, CAST(:t AS uuid)) RETURNING id"),
        {"n": f"t084 area {tag}", "t": t})).scalar_one())
    bare = []
    for k in ("a", "b"):
        bare.append(str((await db.execute(text(
            "INSERT INTO org_unit (name, role_level) VALUES (:n, 1) RETURNING id"),
            {"n": f"t084 bare {k} {tag}"})).scalar_one()))
    who = str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, 'Accounts', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'account_manager' RETURNING id"),
        {"e": f"t084b_{tag}@polysil.in", "o": bare[0]})).scalar_one())
    src = str((await db.execute(text("SELECT id FROM lead_source ORDER BY id LIMIT 1"))).scalar_one())
    lead = str((await db.execute(text(
        "INSERT INTO lead (inquiry_no, farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id, "
        "  inquiry_type, mis_system_id, lead_source_id) "
        "VALUES (:no, 'Farmer', :m, CAST(:t AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), 'commercial', "
        "  (SELECT id FROM mis_system ORDER BY id LIMIT 1), CAST(:s AS uuid)) RETURNING id"),
        {"no": f"T084B/{tag}", "m": "+9197" + f"{uuid.uuid4().int % 10**8:08d}", "t": t, "u": who,
         "o": area, "s": src})).scalar_one())
    await db.execute(text("UPDATE app_user SET org_unit_id = CAST(:b AS uuid) WHERE id = CAST(:u AS uuid)"),
                     {"b": bare[1], "u": who})
    office = str((await db.execute(text("SELECT owner_org_unit_id FROM lead WHERE id = CAST(:l AS uuid)"),
                                   {"l": lead})).scalar_one())
    assert office == area
