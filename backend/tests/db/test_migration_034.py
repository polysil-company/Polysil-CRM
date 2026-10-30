"""Migration 034 (FS-024): the lead's won and lost dates, on every path and in the backfill."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_018 as m18

pytestmark = pytest.mark.db

m034 = importlib.import_module("api.db.migrations.versions.034_reports")


async def _lead(db: AsyncSession, w: m18.World, stage: str = "new") -> str:
    return str((await db.execute(text(
        "INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id, "
        "farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id, created_by) "
        "VALUES (:no, CAST(:st AS lead_stage), 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
        "(SELECT id FROM lead_source WHERE code = 'employee'), 'Farmer', :mob, CAST(:t AS uuid), "
        "CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:o AS uuid)) RETURNING id"),
        {"no": f"R34-{uuid.uuid4().hex[:10]}", "st": stage, "mob": "+9197" + f"{uuid.uuid4().int % 10**8:08d}",
         "t": w.district, "o": w.officer, "ou": w.a})).scalar_one())


async def _dates(db: AsyncSession, lead: str) -> tuple[object, object]:
    r = (await db.execute(text("SELECT won_at, lost_at FROM lead WHERE id = CAST(:l AS uuid)"), {"l": lead})).one()
    return r.won_at, r.lost_at


async def _stage(db: AsyncSession, lead: str, stage: str) -> None:
    await db.execute(text(
        "UPDATE lead SET stage = CAST(:s AS lead_stage), lost_reason_id = CASE WHEN :s = 'lost' "
        "THEN (SELECT id FROM won_lost_reason WHERE kind = 'lost' AND is_active ORDER BY sort_order LIMIT 1) END "
        "WHERE id = CAST(:l AS uuid)"), {"s": stage, "l": lead})


async def test_lost_reopen_won_and_back_set_and_clear_the_dates(db: AsyncSession) -> None:
    """Review 2: every path is a plain UPDATE of stage, so one trigger covers them."""
    w = await m18._world(db)
    lead = await _lead(db, w)
    await _stage(db, lead, "lost")
    won, lost = await _dates(db, lead)
    assert won is None and lost is not None
    await _stage(db, lead, "contacted")          # a reopen
    assert await _dates(db, lead) == (None, None)
    await _stage(db, lead, "won")
    won, lost = await _dates(db, lead)
    assert won is not None and lost is None
    await _stage(db, lead, "negotiation")        # a won lead taken back
    assert await _dates(db, lead) == (None, None)


async def test_an_unrelated_update_keeps_the_date(db: AsyncSession) -> None:
    w = await m18._world(db)
    lead = await _lead(db, w)
    await _stage(db, lead, "won")
    before = await _dates(db, lead)
    await db.execute(text("UPDATE lead SET farmer_name = 'Renamed' WHERE id = CAST(:l AS uuid)"), {"l": lead})
    assert await _dates(db, lead) == before


async def test_the_backfill_takes_the_latest_event_then_updated_at(db: AsyncSession) -> None:
    w = await m18._world(db)
    with_events, without = await _lead(db, w), await _lead(db, w)
    await _stage(db, with_events, "won")
    await _stage(db, without, "lost")
    await db.execute(text("ALTER TABLE lead DISABLE TRIGGER trg_lead_stage_dates"))
    await db.execute(text("UPDATE lead SET won_at = NULL, lost_at = NULL WHERE id = ANY(CAST(:i AS uuid[]))"),
                     {"i": [with_events, without]})
    for at in ("2026-01-05 10:00+05:30", "2026-02-07 10:00+05:30"):
        await db.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload, occurred_at) "
            "VALUES ('lead', CAST(:l AS uuid), CAST(:l AS uuid), 'lead.stage_changed', CAST(:a AS uuid), "
            "'{\"from\": \"negotiation\", \"to\": \"won\"}', CAST(CAST(:at AS text) AS timestamptz))"),
            {"l": with_events, "a": w.officer, "at": at})
    for stmt in m034.BACKFILL:
        await db.execute(text(stmt))
    await db.execute(text("ALTER TABLE lead ENABLE TRIGGER trg_lead_stage_dates"))
    got = (await db.execute(text("SELECT won_at = TIMESTAMPTZ '2026-02-07 10:00+05:30' FROM lead WHERE id = CAST(:l AS uuid)"),
                            {"l": with_events})).scalar_one()
    assert got, "the latest event wins"
    got = (await db.execute(text("SELECT lost_at = updated_at FROM lead WHERE id = CAST(:l AS uuid)"),
                            {"l": without})).scalar_one()
    assert got, "no event: updated_at stands in"
