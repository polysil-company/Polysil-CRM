"""ISS-110: the payment and stock locks, proven with two sessions rather than by
reading. Each race holds the first writer's transaction open until PostgreSQL
reports the second one waiting, then checks that the second saw the first's work.
Remove the lock and the second reads stale figures: both writes succeed."""

# ruff: noqa: E501  (inline SQL and request bodies)

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_order_concurrency as conc
from tests.api import test_order_endpoints as endpoints
from tests.api import test_payments as payments_t
from tests.api import test_stock as stock_t
from tests.api.test_payments import _forget_payments  # noqa: F401  (autouse: payment rows first)
from tests.api.test_stock import _forget_stock  # noqa: F401  (autouse: stock rows first)

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


def _definer(sql: str, params: dict[str, Any]) -> conc.Work:
    async def work(s: AsyncSession) -> Any:
        return (await s.execute(text(sql), params)).scalar_one_or_none()
    return work


async def test_two_allocations_of_one_receipt_never_exceed_it(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """payment_allocate locks the receipt: the second allocation waits, then sees
    the first and is refused for exceeding what is left (PAYOA)."""
    fo = await endpoints._as(client, shop, "field_officer")
    orders = [await endpoints._submit(client, fo, (await endpoints._create(
        client, fo, endpoints._direct(shop, partner_id=shop.partner)))["id"]) for _ in range(2)]
    amount = min(Decimal(o["totals"]["total"]) for o in orders)
    accounts = await endpoints._as(client, shop, "account_manager")
    r = await payments_t._pay(client, accounts, {"partner_id": shop.partner, "amount": str(amount), "allocations": []})
    assert r.status_code == 201, r.text
    receipt = r.json()["data"]["id"]
    sql = "SELECT payment_allocate(CAST(:p AS uuid), CAST(:a AS jsonb))"
    me = shop.ids["account_manager"]
    first, second = ({"p": receipt, "a": json.dumps([{"sales_order_id": o["id"], "amount": str(amount)}])}
                     for o in orders)
    got, waited = await conc._race(sessions, (me, _definer(sql, first)), (me, _definer(sql, second)), on="payment")
    assert waited, "the second allocation did not wait on the receipt: the race was not a race"
    assert sorted(conc._outcome(g) for g in got) == ["PAYOA", "ok"], got
    s = sessions()
    try:
        allocated = (await s.execute(text(
            "SELECT COALESCE(sum(amount), 0) FROM payment_allocation WHERE payment_id = CAST(:p AS uuid) AND NOT voided"),
            {"p": receipt})).scalar_one()
    finally:
        await s.rollback()
        await s.close()
    assert allocated == amount, "the receipt was allocated once, never twice"


async def test_two_withdrawals_never_take_stock_below_zero(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """stock_record takes an advisory lock per warehouse and product: the second
    withdrawal waits, then reads the first's movement and is refused (STKNG)."""
    admin = await endpoints._as(client, shop, "admin_sales")
    wh = await stock_t._warehouse(client, shop)
    assert (await stock_t._move(client, admin, wh["id"], shop.product, "100")).status_code == 201
    sql = "SELECT stock_record(CAST(:w AS uuid), 'adjustment', 'count', NULL, CAST(:l AS jsonb))"
    take = {"w": wh["id"], "l": json.dumps([{"product_id": shop.product, "qty": "-60"}])}
    me = shop.ids["admin_sales"]
    got, waited = await conc._race(sessions, (me, _definer(sql, take)), (me, _definer(sql, take)))
    assert waited, "the second withdrawal did not wait: the race was not a race"
    assert sorted(conc._outcome(g) for g in got) == ["STKNG", "ok"], got
    on_hand = (await client.get(f"{endpoints.V1}/stock", headers=admin,
                                params={"warehouse_id": wh["id"], "product_id": shop.product})).json()["data"]
    assert Decimal(on_hand[0]["on_hand"]) == 40, on_hand
