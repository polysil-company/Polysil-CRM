"""Migration 047 (FS-027): the dealer's exposure, the check inside order_submit, and
who may read a dealer's credit, executed as the roles that touch them."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db import test_migration_031 as m31

pytestmark = [pytest.mark.db, pytest.mark.rls]


async def _dealer(db: AsyncSession, w: m13.World, limit: str | None) -> str:
    return str((await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier, credit_limit) "
        "VALUES ('distributor', :c, 'M047 Dealer', CAST(:t AS uuid), 'distributor', CAST(:l AS numeric)) RETURNING id"),
        {"c": f"M047{uuid.uuid4().hex[:8]}", "t": w.district, "l": limit})).scalar_one())


async def _mode(db: AsyncSession, mode: str) -> None:
    await db.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = 'dealer_credit_check'"),
                     {"v": json.dumps(mode)})


async def _exposure(db: AsyncSession, partner: str) -> Decimal:
    return Decimal((await db.execute(text("SELECT partner_credit_exposure(CAST(:p AS uuid))"), {"p": partner})).scalar_one())


async def _pay(db: AsyncSession, w: m13.World, partner: str, amount: str, order: str | None = None) -> str:
    await m13._as(db, w.accounts)
    allocs = [{"sales_order_id": order, "amount": amount}] if order else []
    pid = str((await db.execute(text("SELECT payment_record(CAST(:p AS jsonb))"), {"p": json.dumps({
        "partner_id": partner, "mode": "neft", "ref_no": "UTR" + uuid.uuid4().hex[:10], "received_on": "2026-10-01",
        "amount": amount, "allocations": allocs})})).scalar_one())
    await m13._as_owner(db)
    return pid


async def test_the_setting_row_and_the_definers_are_in_place(db: AsyncSession) -> None:
    """Edge 21: a missing row would fail every submit."""
    assert (await db.execute(text("SELECT app_setting_text('dealer_credit_check')"))).scalar_one() in ("off", "warn", "block")
    rows = (await db.execute(text(
        "SELECT proname, prosecdef, proconfig, has_function_privilege('public', p.oid, 'EXECUTE') FROM pg_proc p "
        "WHERE proname IN ('partner_credit_exposure', 'order_credit_check', 'partner_credit_position')"))).all()
    assert len(rows) == 3
    for name, definer, config, public in rows:
        assert definer and "search_path=public, pg_temp" in (config or []), name
        assert not public, f"{name}: EXECUTE revoked from PUBLIC"
    body = (await db.execute(text("SELECT pg_get_functiondef('order_submit(uuid)'::regprocedure)"))).scalar_one()
    assert body.count("PERFORM order_credit_check(p_order_id);") == 1


async def test_exposure_is_owed_less_receipts_and_money_on_a_cancelled_order_stays_a_credit(db: AsyncSession) -> None:
    """Plan review B-1: allocations drop out of the formula."""
    w = await m13._world(db)
    p = await _dealer(db, w, "100000")
    await _mode(db, "off")
    a = await m13._order(db, w, qty=10, partner=p)       # 1,050.00
    await m13._submit(db, w, a)
    assert await _exposure(db, p) == Decimal("1050.00")
    await _pay(db, w, p, "1050.00", a)
    assert await _exposure(db, p) == 0
    await m13._as(db, w.officer)
    await db.execute(text("SELECT order_cancel(CAST(:o AS uuid), 'Farmer withdrew')"), {"o": a})
    await m13._as_owner(db)
    assert await m13._status(db, a) == "cancelled"
    assert await _exposure(db, p) == Decimal("-1050.00"), "the dealer paid; it is in credit, as on its ledger"
    advance = await _pay(db, w, p, "500.00")
    assert await _exposure(db, p) == Decimal("-1550.00")
    await m13._as(db, w.accounts)
    await db.execute(text("SELECT payment_void(CAST(:p AS uuid), 'Bounced')"), {"p": advance})
    await m13._as_owner(db)
    assert await _exposure(db, p) == Decimal("-1050.00"), "a voided receipt counts for nothing"
    draft = await m13._order(db, w, qty=10, partner=p)
    assert await _exposure(db, p) == Decimal("-1050.00"), "a draft owes nothing yet"
    assert draft


async def test_block_rolls_back_the_submit_and_warn_writes_the_flag(db: AsyncSession) -> None:
    w = await m13._world(db)
    p = await _dealer(db, w, "1500")
    await _mode(db, "warn")
    a = await m13._order(db, w, qty=10, partner=p)
    await m13._submit(db, w, a)
    b = await m13._order(db, w, qty=10, partner=p)
    await m13._submit(db, w, b)
    flags = dict((await db.execute(text("SELECT id::text, over_credit_limit FROM sales_order WHERE id = ANY(CAST(:i AS uuid[]))"),
                                   {"i": [a, b]})).all())
    assert flags == {a: False, b: True}, "the second takes the dealer to 2,100 against 1,500"
    await _mode(db, "block")
    c = await m13._order(db, w, qty=10, partner=p)
    await m13._as(db, w.officer)
    msg = await m13._refused(db, "SELECT order_submit(CAST(:o AS uuid))", {"o": c}, "CRDLM")
    await m13._as_owner(db)
    assert "This order would take the dealer over its credit limit." in msg and "1500" not in msg
    row = (await db.execute(text("SELECT status::text, order_no FROM sales_order WHERE id = CAST(:o AS uuid)"), {"o": c})).one()
    assert row == ("draft", None), "the whole submit rolled back"


async def test_a_zero_limit_is_cash_only_and_an_advance_covers_it(db: AsyncSession) -> None:
    """GAP-240: 0 is no credit; null is no limit."""
    w = await m13._world(db)
    p = await _dealer(db, w, "0")
    await _mode(db, "block")
    a = await m13._order(db, w, qty=10, partner=p)
    await m13._as(db, w.officer)
    await m13._refused(db, "SELECT order_submit(CAST(:o AS uuid))", {"o": a}, "CRDLM")
    await m13._as_owner(db)
    await _pay(db, w, p, "1050.00")                     # an advance
    await m13._submit(db, w, a)
    assert (await db.execute(text("SELECT over_credit_limit FROM sales_order WHERE id = CAST(:o AS uuid)"), {"o": a})).scalar_one() is False


async def test_a_dealer_never_reads_its_own_credit(db: AsyncSession) -> None:
    """Plan review B-2: portal roles hold partners.edit at partner_subtree."""
    w = await m13._world(db)
    p = await _dealer(db, w, "5000")
    dealer = str((await db.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "SELECT 'partner_user', :m, 'M047 Dealer User', r.id, CAST(:p AS uuid) FROM role r WHERE r.code = 'distributor' RETURNING id"),
        {"m": "9197" + f"{uuid.uuid4().int % 10**8:08d}", "p": p})).scalar_one())
    q = "SELECT * FROM partner_credit_position(CAST(:p AS uuid))"
    await m13._as(db, w.accounts)
    assert (await db.execute(text(q), {"p": p})).one()[0] == Decimal("5000")
    await m13._as_owner(db)
    for who in (dealer, w.officer):
        await m13._as(db, who)
        await m13._refused(db, q, {"p": p}, "42501")
        await m13._as_owner(db)


async def test_a_manager_reads_only_the_dealers_of_its_own_area(db: AsyncSession) -> None:
    """Code review finding 1: partners.edit at org_subtree reaches its own district
    only; drop partner_visible_to_caller and the other district's manager reads it."""
    w = await m13._world(db)
    p = await _dealer(db, w, "5000")
    q = "SELECT * FROM partner_credit_position(CAST(:p AS uuid))"
    await m13._as(db, w.dm)
    assert (await db.execute(text(q), {"p": p})).one()[0] == Decimal("5000")
    await m13._as_owner(db)
    elsewhere = await m31._other_district_manager(db)
    await m13._as(db, elsewhere)
    await m13._refused(db, q, {"p": p}, "42501")
    await m13._as_owner(db)


async def test_an_amended_order_is_checked_again_and_keeps_its_number(db: AsyncSession) -> None:
    """Code review finding 2: approved to draft by amendment clears the flag through
    the same trigger as a rejection; the resubmit is checked under the new setting."""
    w = await m13._world(db)
    p = await _dealer(db, w, "100")
    await _mode(db, "warn")
    order = await m13._order(db, w, qty=10, partner=p)
    request = await m13._submit(db, w, order)
    who = {"district_manager": w.dm, "state_manager": w.sm, "regional_manager": w.rm,
           "account_manager": w.accounts, "dispatch_manager": w.dispatcher}
    for step in await m13._steps(db, request):
        await m13._decide(db, who[step.role], step.id)
    await m13._as_owner(db)
    row = (await db.execute(text("SELECT status::text, over_credit_limit, order_no FROM sales_order WHERE id = CAST(:o AS uuid)"),
                            {"o": order})).one()
    assert row[0] == "approved" and row[1] is True
    number = row[2]
    await m13._as(db, w.officer)
    await db.execute(text("SELECT order_amend(CAST(:o AS uuid), 'Farmer wants more', NULL)"), {"o": order})
    await m13._as_owner(db)
    row = (await db.execute(text("SELECT status::text, over_credit_limit FROM sales_order WHERE id = CAST(:o AS uuid)"),
                            {"o": order})).one()
    assert tuple(row) == ("draft", None), "the amend cleared the flag"
    await _mode(db, "block")
    await m13._as(db, w.officer)
    await m13._refused(db, "SELECT order_submit(CAST(:o AS uuid))", {"o": order}, "CRDLM")
    await m13._as_owner(db)
    assert (await db.execute(text("SELECT order_no FROM sales_order WHERE id = CAST(:o AS uuid)"), {"o": order})).scalar_one() == number
