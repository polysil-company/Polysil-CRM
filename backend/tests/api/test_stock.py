"""FS-023 over the API: warehouses, recorded stock, availability and committed,
dispatch decrements and void restores, the order line's stock, who may not."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_complaints as complaints_t
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


@pytest_asyncio.fixture(autouse=True)
async def _forget_stock(shop: Shop, sessions: Sessions) -> AsyncIterator[None]:
    """Before `shop` deletes its product: the movements reference it. The test
    warehouses stay: a submitted order's warehouse cannot be cleared, and the shop
    deletes the orders only after this runs. They stop naming the shop's people."""
    yield
    s = sessions()
    try:
        await s.execute(text("DELETE FROM stock_movement WHERE product_id = CAST(:p AS uuid)"), {"p": shop.product})
        # the warehouses stay, so they must stop naming the people the shop deletes
        await s.execute(text("UPDATE warehouse SET created_by = NULL WHERE created_by = ANY(CAST(:u AS uuid[]))"),
                        {"u": list(shop.ids.values())})
        await s.execute(text("UPDATE warehouse SET updated_by = NULL WHERE updated_by = ANY(CAST(:u AS uuid[]))"),
                        {"u": list(shop.ids.values())})
        await s.commit()
    finally:
        await s.close()


async def _warehouse(client: httpx.AsyncClient, shop: Shop, **over: Any) -> dict:
    admin = await endpoints._as(client, shop, "admin_sales")
    body = {"code": f"T{shop.code}{uuid.uuid4().hex[:4]}", "name": "Test depot", **over}
    r = await client.post(f"{V1}/warehouses", headers={**admin, **_key()}, json=body)
    assert r.status_code == 201, r.text
    return dict(r.json()["data"])


async def _move(client: httpx.AsyncClient, h: dict[str, str], wid: str, product: str, qty: str,
                kind: str = "receipt") -> httpx.Response:
    return await client.post(f"{V1}/stock/movements", headers={**h, **_key()}, json={
        "warehouse_id": wid, "kind": kind, "reference": "GRN 1", "lines": [{"product_id": product, "qty": qty}]})


async def _available(client: httpx.AsyncClient, h: dict[str, str], wid: str, product: str) -> tuple[str, str]:
    r = await client.get(f"{V1}/stock/availability", headers=h, params={"warehouse_id": wid, "product_ids": product})
    assert r.status_code == 200, r.text
    item = r.json()["data"]["items"][0]
    return item["on_hand"], item["available"]


async def test_receipts_adjustments_and_the_negative_rule(client: httpx.AsyncClient, shop: Shop) -> None:
    wh = await _warehouse(client, shop)
    hd = await endpoints._as(client, shop, "dispatch_manager")
    r = await _move(client, hd, wh["id"], shop.product, "100")
    assert r.status_code == 201 and r.json()["data"]["movements"][0]["on_hand_after"] == "100", r.text
    assert (await _move(client, hd, wh["id"], shop.product, "-30", "adjustment")).status_code == 201
    r = await _move(client, hd, wh["id"], shop.product, "-71", "adjustment")
    assert r.status_code == 409 and r.json()["error"]["code"] == "negative_stock", r.text
    r = await _move(client, hd, wh["id"], shop.product, "-5", "receipt")
    assert r.status_code == 422, "a receipt is positive"
    assert await _available(client, hd, wh["id"], shop.product) == ("70", "70")


async def test_an_order_commits_and_a_dispatch_moves_stock_and_a_void_puts_it_back(
        client: httpx.AsyncClient, shop: Shop) -> None:
    wh = await _warehouse(client, shop)
    hd = await endpoints._as(client, shop, "dispatch_manager")
    await _move(client, hd, wh["id"], shop.product, "50")
    fo = await endpoints._as(client, shop, "field_officer")
    draft = await endpoints._create(client, fo, endpoints._direct(shop, warehouse_id=wh["id"]))
    assert draft["warehouse"]["id"] == wh["id"]
    assert draft["lines"][0]["stock"]["available"] == "50", "a draft commits nothing"
    order = await endpoints._submit(client, fo, draft["id"])
    assert await _available(client, hd, wh["id"], shop.product) == ("50", "40"), "submitted commits its 10"
    order = await endpoints._approve_all(client, shop, order)
    line = order["lines"][0]
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()}, json={
        "dc_no": "DC-1", "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
        "lines": [{"order_line_id": line["id"], "qty": "4"}]})
    assert r.status_code == 201 and r.json()["data"]["warehouse"]["id"] == wh["id"], r.text
    dispatch = r.json()["data"]
    assert await _available(client, hd, wh["id"], shop.product) == ("46", "40"), "4 left; 6 still owed"
    r = await client.post(f"{V1}/dispatches/{dispatch['id']}/void", headers={**hd, **_key()}, json={"remark": "Wrong DC"})
    assert r.status_code == 200, r.text
    assert await _available(client, hd, wh["id"], shop.product) == ("50", "40"), "the void restores exactly"
    led = (await client.get(f"{V1}/stock/movements", headers=hd, params={"warehouse_id": wh["id"]})).json()["data"]
    kinds = [m["kind"] for m in led]
    assert kinds.count("dispatch") == 1 and kinds.count("dispatch_void") == 1
    assert next(m for m in led if m["kind"] == "dispatch")["order"] == order["order_no"]


async def test_a_dispatch_from_another_warehouse_moves_that_warehouse(client: httpx.AsyncClient, shop: Shop) -> None:
    home, other = await _warehouse(client, shop), await _warehouse(client, shop)
    hd = await endpoints._as(client, shop, "dispatch_manager")
    order = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, await endpoints._as(client, shop, "field_officer"),
        (await endpoints._create(client, await endpoints._as(client, shop, "field_officer"),
                                 endpoints._direct(shop, warehouse_id=home["id"])))["id"]))
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()}, json={
        "dispatched_at": dt.datetime.now(dt.UTC).isoformat(), "warehouse_id": other["id"],
        "lines": [{"order_line_id": order["lines"][0]["id"], "qty": "3"}]})
    assert r.status_code == 201, r.text
    assert (await _available(client, hd, other["id"], shop.product))[0] == "-3", "a dispatch may go negative (rule 5)"
    assert (await _available(client, hd, home["id"], shop.product))[0] == "0"


async def test_the_default_warehouse_cannot_simply_go(client: httpx.AsyncClient, shop: Shop) -> None:
    admin = await endpoints._as(client, shop, "admin_sales")
    default = next(w for w in (await client.get(f"{V1}/warehouses", headers=admin)).json()["data"] if w["is_default"])
    r = await client.patch(f"{V1}/warehouses/{default['id']}", headers={**admin, **_key()}, json={"is_active": False})
    assert r.status_code == 409 and r.json()["error"]["code"] == "default_warehouse", r.text
    r = await client.patch(f"{V1}/warehouses/{default['id']}", headers={**admin, **_key()}, json={"is_default": False})
    assert r.status_code == 409 and r.json()["error"]["code"] == "default_warehouse"
    wh = await _warehouse(client, shop)
    r = await client.post(f"{V1}/warehouses", headers={**admin, **_key()}, json={"code": wh["code"].lower(), "name": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "code_taken", "codes are case-insensitive"


async def test_who_may_not(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    wh = await _warehouse(client, shop)
    fo = await endpoints._as(client, shop, "field_officer")
    assert (await client.get(f"{V1}/stock", headers=fo)).status_code == 200, "staff read"
    assert (await _move(client, fo, wh["id"], shop.product, "5")).status_code == 403, "an officer does not record"
    dealer, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        assert (await client.get(f"{V1}/stock", headers=dealer)).status_code == 403
        assert (await client.get(f"{V1}/warehouses", headers=dealer)).status_code == 403
    finally:
        await complaints_t._forget(sessions, mobile)
    r = await client.post(f"{V1}/orders", headers={**fo, **_key()},
                          json=endpoints._direct(shop, warehouse_id=str(uuid.uuid4())))
    assert r.status_code == 422, "no such warehouse"


async def test_a_dispatch_from_an_inactive_warehouse_is_409_not_500(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-1: dispatch_record's stock states reach the API."""
    wh = await _warehouse(client, shop)
    admin = await endpoints._as(client, shop, "admin_sales")
    r = await client.patch(f"{V1}/warehouses/{wh['id']}", headers={**admin, **_key()}, json={"is_active": False})
    assert r.status_code == 200, r.text
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, fo, (await endpoints._create(client, fo, endpoints._direct(shop)))["id"]))
    hd = await endpoints._as(client, shop, "dispatch_manager")
    body = {"dispatched_at": dt.datetime.now(dt.UTC).isoformat(), "warehouse_id": wh["id"],
            "lines": [{"order_line_id": order["lines"][0]["id"], "qty": "1"}]}
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()}, json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "warehouse_inactive", r.text
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()},
                          json={**body, "warehouse_id": str(uuid.uuid4())})
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_such_warehouse", r.text


async def test_a_draft_line_is_short_against_what_it_needs(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-3: a draft commits nothing, so short means below its own need."""
    wh = await _warehouse(client, shop)
    hd = await endpoints._as(client, shop, "dispatch_manager")
    await _move(client, hd, wh["id"], shop.product, "5")
    fo = await endpoints._as(client, shop, "field_officer")
    draft = await endpoints._create(client, fo, endpoints._direct(shop, warehouse_id=wh["id"]))
    assert draft["lines"][0]["stock"] == {"available": "5", "short": True}, "10 needed, 5 there"


async def test_a_dealer_cannot_choose_a_warehouse(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    wh = await _warehouse(client, shop)
    dealer, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        r = await client.post(f"{V1}/orders", headers={**dealer, **_key()},
                              json={**endpoints._direct(shop, warehouse_id=wh["id"]), "partner_id": shop.partner})
        assert r.status_code == 422 and "warehouse_id" in r.json()["error"]["fields"], r.text
    finally:
        await complaints_t._forget(sessions, mobile)
