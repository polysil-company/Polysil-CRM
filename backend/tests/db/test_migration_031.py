"""Migration 031 (FS-022): payments, executed as the roles that touch them."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db import test_migration_018 as m18

pytestmark = [pytest.mark.db, pytest.mark.rls]


async def _receipt(db: AsyncSession, partner: str | None, by: str) -> str:
    return str((await db.execute(text(
        "INSERT INTO payment (partner_id, mode, ref_no, received_on, amount, remark, entered_by) "
        "VALUES (CAST(:p AS uuid), 'neft', :r, current_date, 100, 'internal', CAST(:b AS uuid)) RETURNING id"),
        {"p": partner, "r": "UTR" + uuid.uuid4().hex[:8], "b": by})).scalar_one())


async def _count(db: AsyncSession, who: str, sql: str, params: dict[str, Any]) -> int:
    await m13._as(db, who)
    n = int((await db.execute(text(sql), params)).scalar_one())
    await m13._as_owner(db)
    return n


async def _other_district_manager(db: AsyncSession) -> str:
    tag = uuid.uuid4().hex[:8]
    district = str((await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"), {"n": f"m031_{tag}"})).scalar_one())
    office = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"m031_office_{tag}", "t": district})).scalar_one())
    return await m13._user(db, "district_manager", office, tag)


async def test_receipts_follow_the_dealer_and_stop_at_the_district(db: AsyncSession) -> None:
    w = await m18._world(db)
    pid = await _receipt(db, w.partner, w.admin)
    q, x = "SELECT count(*) FROM payment WHERE id = CAST(:x AS uuid)", {"x": pid}
    assert await _count(db, w.admin, q, x) == 1
    assert await _count(db, w.dm, q, x) == 1, "the dealer serves the manager's area (review B-5)"
    assert await _count(db, await _other_district_manager(db), q, x) == 0, "another district reads nothing"
    assert await _count(db, w.dealer, q, x) == 1, "the dealer reads its own (review B-4)"
    assert await _count(db, w.officer, q, x) == 0, "a field officer holds no payments.view"


async def test_nobody_writes_the_tables_directly(db: AsyncSession) -> None:
    w = await m18._world(db)
    pid = await _receipt(db, w.partner, w.admin)
    await m13._as(db, w.admin)
    await m13._refused(db, "INSERT INTO payment (mode, received_on, amount, entered_by, ref_no) VALUES ('neft', current_date, 1, CAST(:u AS uuid), 'x')",
                       {"u": w.admin}, "42501")
    await m13._refused(db, "UPDATE payment SET amount = 1 WHERE id = CAST(:p AS uuid)", {"p": pid}, "42501")
    await m13._refused(db, "DELETE FROM payment WHERE id = CAST(:p AS uuid)", {"p": pid}, "42501")
    await m13._as_owner(db)


async def test_the_payments_scope_equals_the_orders_scope_for_every_role(db: AsyncSession) -> None:
    """Review B-5: the order arm of the read policy relies on it."""
    rows = (await db.execute(text(
        "SELECT r.code, p.scope::text, o.scope::text FROM role r "
        "JOIN role_permission p ON p.role_id = r.id AND p.module = 'payments' AND p.action = 'view' AND p.deleted_at IS NULL "
        "LEFT JOIN role_permission o ON o.role_id = r.id AND o.module = 'sales_orders' AND o.action = 'view' AND o.deleted_at IS NULL"))).all()
    assert rows
    assert [r for r in rows if r[1] != r[2]] == [], rows


@pytest.mark.parametrize("call", ["SELECT payment_record('{}'::jsonb)",
                                  "SELECT payment_void(gen_random_uuid(), 'x')",
                                  "SELECT payment_allocate(gen_random_uuid(), '[]'::jsonb)",
                                  "SELECT order_payment_schedule_set(gen_random_uuid(), '[]'::jsonb)"])
async def test_the_definers_refuse_a_manager(db: AsyncSession, call: str) -> None:
    w = await m18._world(db)
    await m13._as(db, w.dm)
    await m13._refused(db, call, {}, "42501")
    await m13._as_owner(db)


@pytest.mark.parametrize("sig", ["order_payment_position(uuid, date)", "payment_record(jsonb)",
                                 "payment_allocate(uuid, jsonb)", "payment_void(uuid, text)",
                                 "order_payment_schedule_set(uuid, jsonb)", "payment_apply(payment, jsonb, boolean)",
                                 "payment_partner_name(uuid)",
                                 "refuse_partner_change_when_paid()"])
async def test_every_definer_is_pinned_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
    assert row[0] is True and any(c.startswith("search_path=") for c in row[1]) and row[2] is False


async def test_the_position_is_null_without_payments_view(db: AsyncSession) -> None:
    w = await m18._world(db)
    await m13._as(db, w.officer)
    rows = (await db.execute(text("SELECT * FROM order_payment_position(gen_random_uuid(), current_date)"))).all()
    await m13._as_owner(db)
    assert rows == []


async def test_payable_is_the_total_less_applied_benefits(db: AsyncSession) -> None:
    """GAP-206, closed by the merge with session B: a scheme or reward benefit lowers
    what is owed (ADR-050), a reversed one does not, and instalments stop at it."""
    w = await m13._world(db)
    order = await m13._order(db, w, qty=10)        # total 1,050.00
    await m13._submit(db, w, order)
    # a benefit row without building a scheme: the pairing CHECK goes for this
    # transaction only, which the fixture rolls back
    await db.execute(text("ALTER TABLE scheme_benefit DROP CONSTRAINT ck_scheme_benefit_redemption"))
    for amount, status in ((50, "applied"), (30, "reversed")):
        await db.execute(text(
            "INSERT INTO scheme_benefit (sales_order_id, kind, basis, amount, status, reversed_at) "
            "VALUES (CAST(:o AS uuid), 'discount', 1050, :a, :s, CASE WHEN :s = 'reversed' THEN now() END)"),
            {"o": order, "a": amount, "s": status})
    await m13._as(db, w.accounts)
    payable = (await db.execute(text("SELECT payable FROM order_payment_position(CAST(:o AS uuid), current_date)"),
                                {"o": order})).scalar_one()
    assert payable == 1000
    await m13._refused(db, "SELECT order_payment_schedule_set(CAST(:o AS uuid), '[{\"due_on\": \"2030-01-01\", \"amount\": \"1000.01\"}]'::jsonb)",
                       {"o": order}, "PAYSP")
    await m13._as_owner(db)
