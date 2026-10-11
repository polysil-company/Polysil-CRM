"""FS-034: marketing material ordered, approved over the office, dispatched; prices
copied onto the order; and who must not get in."""

# ruff: noqa: E501  (embedded SQL)

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

from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api import test_rewards as rewards
from tests.api.conftest import V1, _key

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]

pytestmark = pytest.mark.db


@pytest_asyncio.fixture
async def made(shop: Shop, sessions: Sessions) -> AsyncIterator[list[str]]:
    """Catalogue items a test made; the shop's marketing orders go with them."""
    ids: list[str] = []
    yield ids
    c = sessions()
    orders = "(SELECT id FROM marketing_order WHERE owner_org_unit_id = CAST(:o AS uuid))"
    for stmt in (f"DELETE FROM activity_event WHERE entity_type = 'marketing_order' AND entity_id IN {orders}",
                 f"DELETE FROM marketing_order_line WHERE order_id IN {orders}",
                 "DELETE FROM marketing_order WHERE owner_org_unit_id = CAST(:o AS uuid)",
                 "DELETE FROM marketing_order_counter WHERE state_code = :c",
                 "DELETE FROM marketing_material_price WHERE material_id = ANY(CAST(:ids AS uuid[]))",
                 "DELETE FROM marketing_material WHERE id = ANY(CAST(:ids AS uuid[]))"):
        await c.execute(text(stmt), {"o": shop.office, "c": shop.code, "ids": ids})
    await c.commit()
    await c.close()


async def _item(client: httpx.AsyncClient, shop: Shop, made: list[str], price: str = "120.00",
                pct: str = "50") -> dict[str, Any]:
    h = await endpoints._as(client, shop, "admin_sales")
    r = await client.post(f"{V1}/marketing-materials", headers={**h, **_key()}, json={
        "code": f"T-{uuid.uuid4().hex[:8]}", "name": "Test cap", "price": price, "company_share_pct": pct})
    assert r.status_code == 201, r.text
    made.append(r.json()["data"]["id"])
    return dict(r.json()["data"])


async def _order(client: httpx.AsyncClient, h: dict[str, str], **body: Any) -> httpx.Response:
    return await client.post(f"{V1}/marketing-orders", headers={**h, **_key()}, json=body)


async def _act(client: httpx.AsyncClient, h: dict[str, str], oid: str, action: str, **body: Any) -> httpx.Response:
    return await client.post(f"{V1}/marketing-orders/{oid}/{action}", headers={**h, **_key()}, json=body)


async def test_the_catalogue_is_seeded_and_only_editors_write_it(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    items = (await client.get(f"{V1}/marketing-materials", headers=fo, params={"active": "true"})).json()["data"]
    codes = {i["code"] for i in items}
    assert {"MM-CAP", "MM-UMBRELLA", "MM-DIARY-B"} <= codes and len([c for c in codes if c.startswith("MM-")]) >= 17
    assert all(i["is_provisional"] for i in items if i["code"].startswith("MM-")), "stand-in prices"
    r = await client.post(f"{V1}/marketing-materials", headers={**fo, **_key()},
                          json={"code": "FO-X", "name": "x", "price": "1"})
    assert r.status_code == 403, "create is for ordering; the catalogue needs edit"


async def test_an_order_is_shared_half_and_half_approved_over_the_office_and_dispatched(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    cap = await _item(client, shop, made, price="120.00")
    odd = await _item(client, shop, made, price="0.01")
    fo = await endpoints._as(client, shop, "field_officer")
    r = await _order(client, fo, partner_id=shop.partner, remark="Anand meet",
                     lines=[{"material_id": cap["id"], "qty": 20}, {"material_id": odd["id"], "qty": 1}])
    assert r.status_code == 201, r.text
    o = r.json()["data"]
    assert o["order_no"].startswith(f"MM/{shop.code}/") and o["status"] == "submitted"
    assert [(x["value"], x["company_share"], x["dealer_share"]) for x in o["lines"]] == [
        ("2400.00", "1200.00", "1200.00"), ("0.01", "0.01", "0.00")], "half-up on the company's half"
    assert o["totals"] == {"value": "2400.01", "company_share": "1200.01", "dealer_share": "1200.00"}
    assert o["can"]["cancel"] and not o["can"]["approve"]
    r = await _act(client, fo, o["id"], "approve")
    assert r.status_code == 403

    dm = await endpoints._as(client, shop, "district_manager")
    queue = (await client.get(f"{V1}/marketing-orders", headers=dm, params={"awaiting": "me"})).json()["data"]
    assert o["id"] in {x["id"] for x in queue}
    assert (await client.get(f"{V1}/marketing-orders/{o['id']}", headers=dm)).json()["data"]["can"]["approve"]
    r = await _act(client, dm, o["id"], "approve", remark="ok")
    assert r.status_code == 200 and r.json()["data"]["status"] == "approved"
    r = await _act(client, dm, o["id"], "reject", remark="late")
    assert r.status_code == 409 and r.json()["error"]["code"] == "status_changed"

    admin = await endpoints._as(client, shop, "admin_sales")
    future = (today_ist() + dt.timedelta(days=3)).isoformat()
    r = await client.post(f"{V1}/marketing-orders/{o['id']}/dispatch", headers={**admin, **_key()},
                          json={"dispatched_on": future, "reference": "DTDC 1"})
    assert r.status_code == 422
    r = await client.post(f"{V1}/marketing-orders/{o['id']}/dispatch", headers={**admin, **_key()},
                          json={"dispatched_on": today_ist().isoformat(), "reference": "DTDC 123"})
    assert r.status_code == 200 and r.json()["data"]["dispatch"]["reference"] == "DTDC 123"

    # today's price is on an order now: it cannot be replaced until tomorrow
    r = await client.patch(f"{V1}/marketing-materials/{cap['id']}", headers={**admin, **_key()}, json={"price": "150"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "price_changed_today"


async def test_a_new_items_price_can_be_corrected_the_same_day_and_a_later_price_never_restates_an_order(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    """Code review F-1: a typo on the day an item is added is fixable while no order uses it."""
    admin = await endpoints._as(client, shop, "admin_sales")
    cap = await _item(client, shop, made, price="1200.00")
    r = await client.patch(f"{V1}/marketing-materials/{cap['id']}", headers={**admin, **_key()}, json={"price": "120"})
    assert r.status_code == 200 and r.json()["data"]["price"] == "120.00", r.text
    fo = await endpoints._as(client, shop, "field_officer")
    o = (await _order(client, fo, partner_id=shop.partner, lines=[{"material_id": cap["id"], "qty": 2}])).json()["data"]
    assert o["lines"][0]["price"] == "120.00"
    # make today's row yesterday's, as it will be tomorrow, then change the price
    c = sessions()
    await c.execute(text("ALTER TABLE marketing_material_price DISABLE TRIGGER trg_marketing_material_price_refuse"))
    await c.execute(text("UPDATE marketing_material_price SET effective_from = effective_from - 1 "
                         "WHERE material_id = CAST(:m AS uuid)"), {"m": cap["id"]})
    await c.execute(text("ALTER TABLE marketing_material_price ENABLE TRIGGER trg_marketing_material_price_refuse"))
    await c.commit()
    await c.close()
    r = await client.patch(f"{V1}/marketing-materials/{cap['id']}", headers={**admin, **_key()}, json={"price": "150"})
    assert r.status_code == 200 and r.json()["data"]["price"] == "150.00", r.text
    again = (await client.get(f"{V1}/marketing-orders/{o['id']}", headers=fo)).json()["data"]
    assert again["lines"][0]["price"] == "120.00" and again["totals"]["value"] == "240.00"


async def test_a_staff_order_goes_to_the_requesters_office_and_another_districts_manager_cannot_approve(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    """Code review F-5 and F-6: rule 6 routes a staff order by the requester; the approver
    needs the office in their subtree."""
    from argon2 import PasswordHasher

    from tests.api.conftest import PASSWORD, _login
    tag = uuid.uuid4().hex[:8]
    c = sessions()
    district = str((await c.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, CAST(:p AS uuid)) RETURNING id"),
        {"n": f"mm_other_{tag}", "p": shop.state})).scalar_one())
    office = str((await c.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, CAST(:t AS uuid)) RETURNING id"),
        {"n": f"mm_other_office_{tag}", "t": district})).scalar_one())
    email = f"mm_dm_{tag}@polysil.in"
    other_dm = str((await c.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, :p, 'Other DM', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'district_manager' "
        "RETURNING id"), {"e": email, "p": PasswordHasher().hash(PASSWORD), "o": office})).scalar_one())
    await c.commit()
    await c.close()
    try:
        cap = await _item(client, shop, made)
        fo = await endpoints._as(client, shop, "field_officer")
        o = (await _order(client, fo, partner_id=shop.partner, lines=[{"material_id": cap["id"], "qty": 1}])).json()["data"]
        assert o["office"]["id"] == shop.office
        h = await _login(client, email, PASSWORD)
        r = await _act(client, h, o["id"], "approve")
        assert r.status_code == 403 and r.json()["error"]["code"] == "not_your_approval"
    finally:
        c = sessions()
        for stmt in ("DELETE FROM session WHERE user_id = CAST(:u AS uuid)",
                     "DELETE FROM login_attempt WHERE identifier = :e",
                     "DELETE FROM activity_event WHERE actor_id = CAST(:u AS uuid)",
                     "DELETE FROM idempotency_record WHERE user_id = CAST(:u AS uuid)",
                     "DELETE FROM app_user WHERE id = CAST(:u AS uuid)",
                     "DELETE FROM org_unit WHERE id = CAST(:o AS uuid)",
                     "DELETE FROM territory WHERE id = CAST(:t AS uuid)"):
            await c.execute(text(stmt), {"u": other_dm, "e": email, "o": office, "t": district})
        await c.commit()
        await c.close()


async def test_office_use_is_all_company_the_requester_never_approves_and_a_reject_needs_a_remark(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    cap = await _item(client, shop, made)
    dm = await endpoints._as(client, shop, "district_manager")
    r = await _order(client, dm, lines=[{"material_id": cap["id"], "qty": 3}])
    assert r.status_code == 201, r.text
    o = r.json()["data"]
    assert o["partner"] is None and o["totals"]["dealer_share"] == "0.00" and o["lines"][0]["company_share_pct"] == "100.00"
    r = await _act(client, dm, o["id"], "approve")
    assert r.status_code == 403 and r.json()["error"]["code"] == "own_order"
    sm = await endpoints._as(client, shop, "state_manager")
    r = await _act(client, sm, o["id"], "reject")
    assert r.status_code == 422 and r.json()["error"]["code"] == "remark_required"
    r = await _act(client, sm, o["id"], "reject", remark="Budget used this quarter")
    assert r.status_code == 200 and r.json()["data"]["status"] == "rejected"


async def test_an_inactive_item_cannot_be_ordered_and_a_requester_cancels_their_own(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    cap = await _item(client, shop, made)
    admin = await endpoints._as(client, shop, "admin_sales")
    fo = await endpoints._as(client, shop, "field_officer")
    o = (await _order(client, fo, partner_id=shop.partner, lines=[{"material_id": cap["id"], "qty": 1}])).json()["data"]
    r = await _act(client, fo, o["id"], "cancel")
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled"
    await client.patch(f"{V1}/marketing-materials/{cap['id']}", headers={**admin, **_key()}, json={"is_active": False})
    r = await _order(client, fo, partner_id=shop.partner, lines=[{"material_id": cap["id"], "qty": 1}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "material_inactive"
    r = await _order(client, fo, partner_id=shop.partner,
                     lines=[{"material_id": cap["id"], "qty": 1}, {"material_id": cap["id"], "qty": 2}])
    assert r.status_code == 422


async def test_a_dealer_reads_only_its_own_orders_and_nobody_writes_a_line_by_hand(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    cap = await _item(client, shop, made)
    fo = await endpoints._as(client, shop, "field_officer")
    dm = await endpoints._as(client, shop, "district_manager")
    mine = (await _order(client, fo, partner_id=shop.partner, lines=[{"material_id": cap["id"], "qty": 1}])).json()["data"]
    office = (await _order(client, dm, lines=[{"material_id": cap["id"], "qty": 1}])).json()["data"]
    s = await rewards._as_db(sessions, shop.ids["dealer"])
    try:
        seen = {str(x) for x in (await s.execute(text(
            "SELECT id FROM marketing_order WHERE id = ANY(CAST(:i AS uuid[]))"),
            {"i": [mine["id"], office["id"]]})).scalars()}
        assert seen == {mine["id"]}
        from sqlalchemy.exc import DBAPIError
        with pytest.raises(DBAPIError):
            await s.execute(text("UPDATE marketing_order SET value = 0 WHERE id = CAST(:i AS uuid)"), {"i": mine["id"]})
    finally:
        await s.rollback()
        await s.close()
    r = await client.get(f"{V1}/marketing-orders/export", headers=dm, params={"status": "submitted"})
    assert r.status_code == 200 and r.content[:2] == b"PK"
