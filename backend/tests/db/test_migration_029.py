"""Migration 029 (ISS-108): the bell clears a decided approval, and keeps 026's arms."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_018 as m18

pytestmark = [pytest.mark.db]


def _m029() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "api/db/migrations/versions/029_notification_fixes.py"
    spec = importlib.util.spec_from_file_location("mig_029_for_tests", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _note(db: AsyncSession, to: str, kind: str, resource: str, rtype: str = "sales_order") -> str:
    return str((await db.execute(text(
        "INSERT INTO notification (recipient_id, event_id, kind, title, resource_type, resource_id) "
        "VALUES (CAST(:to AS uuid), gen_random_uuid(), :k, 'x', :t, CAST(:r AS uuid)) RETURNING id"),
        {"to": to, "k": kind, "t": rtype, "r": resource})).scalar_one())


async def _read(db: AsyncSession, nid: str) -> bool:
    return bool((await db.execute(text("SELECT read_at IS NOT NULL FROM notification WHERE id = CAST(:n AS uuid)"),
                                  {"n": nid})).scalar_one())


async def test_settle_clears_only_waiting_notifications_on_that_document(db: AsyncSession) -> None:
    w = await m18._world(db)
    doc, other = str(uuid.uuid4()), str(uuid.uuid4())
    waiting = await _note(db, w.dm, "approval_requested", doc)
    waiting_b = await _note(db, w.dm_b, "approval_requested", doc)   # anyone told of the step
    returned = await _note(db, w.officer, "order_returned", doc)
    elsewhere = await _note(db, w.dm, "approval_requested", other)
    same_id_other_type = await _note(db, w.dm, "approval_requested", doc, "quotation")
    await db.execute(text("SELECT notify_settle('sales_order', CAST(:d AS uuid))"), {"d": doc})
    assert await _read(db, waiting) and await _read(db, waiting_b)
    assert not await _read(db, returned), "only the waiting kind clears"
    assert not await _read(db, elsewhere)
    assert not await _read(db, same_id_other_type)


async def test_the_backfill_clears_a_waiting_notification_with_no_pending_request(db: AsyncSession) -> None:
    w = await m18._world(db)
    stale = await _note(db, w.dm, "approval_requested", str(uuid.uuid4()))
    lead_note = await _note(db, w.dm, "lead_note", str(uuid.uuid4()), "lead")
    await db.execute(text(_m029().BACKFILL))
    assert await _read(db, stale)
    assert not await _read(db, lead_note)


async def test_the_live_trigger_keeps_026s_refund_arms_and_settles_every_ending(db: AsyncSession) -> None:
    """029 patches 026's text, not 023's. A re-paste from 023 drops the refund arms."""
    body = (await db.execute(text("SELECT prosrc FROM pg_proc WHERE proname = 'notify_from_event'"))).scalar_one()
    assert "complaint.refund_paid" in body and "notify_settle" in body
    assert "' was returned'" not in body, "orders and discounts say was not approved"
    step = (await db.execute(text("SELECT prosrc FROM pg_proc WHERE proname = 'notify_step'"))).scalar_one()
    assert "A refund on complaint" in step and "Discount of " in step
    trig = (await db.execute(text(
        "SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE tgname = 'trg_notify_from_event'"))).scalar_one()
    for kind in _m029().ENDED:
        assert f"'{kind}'" in trig, kind
    assert "complaint.closed" in trig and "'refund'" in trig, "026's quiet refund close is kept"


async def test_notify_settle_is_internal(db: AsyncSession) -> None:
    pub, app = (await db.execute(text(
        "SELECT has_function_privilege('public', 'notify_settle(text, uuid)', 'EXECUTE'), "
        "has_function_privilege('app_role', 'notify_settle(text, uuid)', 'EXECUTE')"))).one()
    assert (pub, app) == (False, False)
