"""Migration 032 (FS-023): stock, executed as the roles that touch it."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db import test_migration_018 as m18

pytestmark = [pytest.mark.db, pytest.mark.rls]


async def test_a_dealer_reads_no_stock_and_staff_read_but_do_not_write(db: AsyncSession) -> None:
    """Review B-1: the portal stock row is gone."""
    w = await m18._world(db)
    await m13._as(db, w.dealer)
    assert (await db.execute(text("SELECT count(*) FROM warehouse"))).scalar_one() == 0
    assert (await db.execute(text("SELECT count(*) FROM stock_movement"))).scalar_one() == 0
    await m13._as_owner(db)
    await m13._as(db, w.officer)
    assert (await db.execute(text("SELECT count(*) FROM warehouse WHERE is_default"))).scalar_one() == 1, "MAIN is seeded"
    await m13._refused(db, "INSERT INTO stock_movement (warehouse_id, product_id, qty, kind) "
                           "SELECT w.id, p.id, 1, 'receipt' FROM warehouse w, product p LIMIT 1", {}, "42501")
    await m13._refused(db, "SELECT stock_record((SELECT id FROM warehouse WHERE is_default), 'receipt', NULL, NULL, '[]'::jsonb)",
                       {}, "42501")
    await m13._as_owner(db)


async def test_dispatch_lines_are_written_only_by_the_definer(db: AsyncSession) -> None:
    """The triggers run as the owner because every writer of dispatch_line is a definer."""
    held = (await db.execute(text("SELECT has_table_privilege('app_role', 'dispatch_line', 'INSERT')"))).scalar_one()
    assert held is False


async def test_the_board_and_portal_roles_hold_no_stock(db: AsyncSession) -> None:
    rows = (await db.execute(text(
        "SELECT r.code FROM role_permission rp JOIN role r ON r.id = rp.role_id WHERE rp.module = 'stock' "
        "AND r.code IN ('board', 'dealer', 'distributor', 'sub_dealer') AND rp.deleted_at IS NULL"))).scalars().all()
    assert rows == []


@pytest.mark.parametrize("sig", ["stock_record(uuid, text, text, text, jsonb)", "stock_on_hand(uuid, uuid)",
                                 "stock_committed(uuid, uuid)", "stock_default_warehouse()",
                                 "stock_on_dispatch_line()", "stock_on_dispatch_void()", "dispatch_record(uuid, jsonb)"])
async def test_every_definer_is_pinned_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
    assert row[0] is True and any(c.startswith("search_path=") for c in row[1]) and row[2] is False


async def test_dispatch_record_keeps_026s_replacement_progress(db: AsyncSession) -> None:
    """032 patches 026's text: a re-paste from 013 would drop the remedy arm."""
    body = (await db.execute(text("SELECT prosrc FROM pg_proc WHERE proname = 'dispatch_record'"))).scalar_one()
    assert "complaint_replacement_progress" in body and "stock_default_warehouse" in body
