"""Migration 046 (FS-026): the fully-dispatched date and the paid date that the
sale setting reads, executed as the roles that touch them."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13

pytestmark = [pytest.mark.db, pytest.mark.rls]

RECORD = "SELECT dispatch_record(CAST(:o AS uuid), CAST(:p AS jsonb))"


def _dispatch(line: str, qty: str, at: str) -> str:
    return json.dumps({"dc_no": "DC-" + uuid.uuid4().hex[:6], "dispatched_at": at,
                       "lines": [{"order_line_id": line, "qty": qty}]})


async def _fully(db: AsyncSession, order: str) -> object:
    return (await db.execute(text("SELECT fully_dispatched_at FROM sales_order WHERE id = CAST(:o AS uuid)"),
                             {"o": order})).scalar_one()


async def test_the_date_is_the_last_live_dispatch_and_a_void_clears_it(db: AsyncSession) -> None:
    w = await m13._world(db)
    order = await m13._approved(db, w, qty=10)
    line = await m13._line(db, order)
    await m13._as(db, w.dispatcher)
    await db.execute(text(RECORD), {"o": order, "p": _dispatch(line, "4", "2026-01-10T10:00:00+05:30")})
    await m13._as_owner(db)
    assert await _fully(db, order) is None, "partly dispatched: not yet"
    await m13._as(db, w.dispatcher)
    last = (await db.execute(text(RECORD), {"o": order, "p": _dispatch(line, "6", "2026-01-15T10:00:00+05:30")})).scalar_one()
    await m13._as_owner(db)
    assert await m13._status(db, order) == "dispatched"
    got = (await db.execute(text("SELECT fully_dispatched_at = TIMESTAMPTZ '2026-01-15 10:00+05:30' FROM sales_order "
                                 "WHERE id = CAST(:o AS uuid)"), {"o": order})).scalar_one()
    assert got, "the last dispatch's time"
    last_id = last["id"] if isinstance(last, dict) else (await db.execute(text(
        "SELECT id FROM dispatch WHERE sales_order_id = CAST(:o AS uuid) ORDER BY dispatched_at DESC LIMIT 1"),
        {"o": order})).scalar_one()
    await m13._as(db, w.dispatcher)
    await db.execute(text("SELECT dispatch_void(CAST(:d AS uuid), 'Wrong DC')"), {"d": str(last_id)})
    await m13._as_owner(db)
    assert await m13._status(db, order) == "partially_dispatched"
    assert await _fully(db, order) is None, "the void reopened the order"


async def test_closed_short_with_nothing_shipped_has_no_date_and_the_check_holds(db: AsyncSession) -> None:
    w = await m13._world(db)
    order = await m13._approved(db, w, qty=10)
    await m13._as(db, w.dispatcher)
    await db.execute(text("SELECT order_close_short(CAST(:o AS uuid), 'Discontinued')"), {"o": order})
    await m13._as_owner(db)
    assert await m13._status(db, order) == "closed_short"
    assert await _fully(db, order) is None, "nothing shipped, so no sale under any mode (B-3)"
    other = await m13._approved(db, w, qty=5)
    msg = await m13._refused(db, "UPDATE sales_order SET fully_dispatched_at = now() WHERE id = CAST(:o AS uuid)",
                             {"o": other}, "23514")
    assert "ck_sales_order_fully_dispatched" in msg, "the CHECK, not the edit guard"


async def _receipt(db: AsyncSession, order: str, amount: str, day: str) -> str:
    return str((await db.execute(text("SELECT payment_record(CAST(:p AS jsonb))"), {"p": json.dumps({
        "partner_id": None, "mode": "neft", "ref_no": "UTR" + uuid.uuid4().hex[:10], "received_on": day,
        "amount": amount, "allocations": [{"sales_order_id": order, "amount": amount}]})})).scalar_one())


async def test_the_paid_date_is_the_receipt_day_that_covers_payable(db: AsyncSession) -> None:
    """Plan review B-4: the later-dated receipt entered first must not date the sale
    to the earlier receipt's day; the answer is the day the running total covers."""
    w = await m13._world(db)
    order = await m13._order(db, w, qty=10)          # total 1,050.00
    await m13._submit(db, w, order)
    paid = "SELECT order_paid_at(CAST(:o AS uuid)) = TIMESTAMPTZ '2026-10-03 00:00+05:30' FROM (SELECT 1) x"
    await m13._as(db, w.accounts)
    late = await _receipt(db, order, "450.00", "2026-10-03")       # entered first
    assert (await db.execute(text("SELECT order_paid_at(CAST(:o AS uuid))"), {"o": order})).scalar_one() is None
    await _receipt(db, order, "600.00", "2026-10-01")
    assert (await db.execute(text(paid), {"o": order})).scalar_one(), "3 Oct, not 1 Oct"
    await m13._as_owner(db)
    await m13._as(db, w.officer)                      # no payments.view: a day, not an amount (rule 11)
    assert (await db.execute(text(paid), {"o": order})).scalar_one()
    await m13._as_owner(db)
    elsewhere = await m13._world(db)
    await m13._as(db, elsewhere.officer)              # cannot see the order: nothing at all
    assert (await db.execute(text("SELECT order_paid_at(CAST(:o AS uuid))"), {"o": order})).scalar_one() is None
    await m13._as_owner(db)
    await m13._as(db, w.accounts)
    await db.execute(text("SELECT payment_void(CAST(:p AS uuid), 'Bounced')"), {"p": late})
    assert (await db.execute(text("SELECT order_paid_at(CAST(:o AS uuid))"), {"o": order})).scalar_one() is None, \
        "the void uncovers it"
    await m13._as_owner(db)


async def _paid_on(db: AsyncSession, order: str) -> object:
    return (await db.execute(text("SELECT (order_paid_at(CAST(:o AS uuid)) AT TIME ZONE 'Asia/Kolkata')::date"),
                             {"o": order})).scalar_one()


async def test_benefits_move_the_paid_day_and_owing_nothing_has_none(db: AsyncSession) -> None:
    """Edges 10 and 11, GAP-239. The benefit row skips its scheme (constraint dropped
    in this rolled-back transaction); payable reads only kind, status and amount."""
    w = await m13._world(db)
    order = await m13._order(db, w, qty=10)          # total 1,050.00
    await m13._submit(db, w, order)
    await m13._as(db, w.accounts)
    await _receipt(db, order, "600.00", "2026-10-01")
    await _receipt(db, order, "450.00", "2026-10-05")
    assert str(await _paid_on(db, order)) == "2026-10-05"
    await m13._as_owner(db)
    await db.execute(text("ALTER TABLE scheme_benefit DROP CONSTRAINT ck_scheme_benefit_redemption"))
    await db.execute(text("ALTER TABLE scheme_benefit ALTER COLUMN scheme_id DROP NOT NULL"))
    benefit = (await db.execute(text("INSERT INTO scheme_benefit (sales_order_id, kind, basis, amount) "
                                     "VALUES (CAST(:o AS uuid), 'discount', 450, 450) RETURNING id"),
                                {"o": order})).scalar_one()
    await m13._as(db, w.accounts)
    assert str(await _paid_on(db, order)) == "2026-10-01", "payable 600 was covered on 1 Oct, not the last receipt's day"
    await m13._as_owner(db)
    await db.execute(text("UPDATE scheme_benefit SET amount = 1050 WHERE id = :b"), {"b": benefit})
    await m13._as(db, w.accounts)
    assert (await db.execute(text("SELECT order_paid_at(CAST(:o AS uuid))"), {"o": order})).scalar_one() is None, \
        "payable 0: never a sale under payment, though receipts exist"
    await m13._as_owner(db)


async def test_order_paid_at_is_a_pinned_definer(db: AsyncSession) -> None:
    row = (await db.execute(text("SELECT prosecdef, proconfig, has_function_privilege('public', p.oid, 'EXECUTE') "
                                 "FROM pg_proc p WHERE proname = 'order_paid_at'"))).one()
    assert row[0] and "search_path=public, pg_temp" in (row[1] or []), row
    assert not row[2], "EXECUTE revoked from PUBLIC"
