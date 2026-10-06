"""FS-025 over the API: who may set whose target, past months, achievement."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
MONTH = today_ist().strftime("%Y-%m")  # the IST month, as the service reads it


@pytest_asyncio.fixture(autouse=True)
async def _forget_targets(shop: Shop, sessions: Callable[[], AsyncSession]) -> AsyncIterator[None]:
    """Before `shop` deletes its people: their targets reference them."""
    yield
    s = sessions()
    try:
        await s.execute(text("DELETE FROM sales_target WHERE user_id = ANY(CAST(:p AS uuid[])) "
                             "OR created_by = ANY(CAST(:p AS uuid[]))"), {"p": list(shop.ids.values())})
        await s.commit()
    finally:
        await s.close()


async def _put(client: httpx.AsyncClient, h: dict[str, str], user: str, month: str = MONTH, **targets: object) -> httpx.Response:
    return await client.put(f"{V1}/targets", headers={**h, **_key()},
                            json={"user_id": user, "month": month, "targets": targets or {"orders": 10}})


async def test_a_manager_sets_a_target_below_them_and_the_history_stays(client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    fo_id = shop.ids["field_officer"]
    r = await _put(client, dm, fo_id, orders=10, order_value="500000.00")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["targets"]["orders"] == 10
    r = await _put(client, dm, fo_id, orders=12)
    data = r.json()["data"]
    assert data["targets"] == {"order_value": "500000.00", "orders": 12, "leads_won": None, "visits": None}
    assert len(data["history"]) == 3


async def test_not_yourself_not_a_peer_not_a_past_month(client: httpx.AsyncClient, shop: Shop) -> None:
    """Review B-1: the subtree holds the caller and their peers at one office."""
    dm = await endpoints._as(client, shop, "district_manager")
    r = await _put(client, dm, shop.ids["district_manager"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_your_team"
    r = await _put(client, dm, shop.ids["state_manager"])
    assert r.status_code == 403, "a higher rank is not below me"
    last = (today_ist().replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    r = await _put(client, dm, shop.ids["field_officer"], month=last)
    assert r.status_code == 422 and r.json()["error"]["code"] == "month_closed"
    r = await _put(client, dm, shop.ids["field_officer"], orders="2.5")
    assert r.status_code == 422, "a count is whole"
    fo = await endpoints._as(client, shop, "field_officer")
    assert (await _put(client, fo, shop.ids["field_officer"])).status_code == 403, "an officer sets nothing"


async def test_achievement_lists_people_without_a_target_and_counts_orders(client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    await _put(client, dm, shop.ids["field_officer"], orders=4)
    fo = await endpoints._as(client, shop, "field_officer")
    await endpoints._submit(client, fo, (await endpoints._create(client, fo, endpoints._direct(shop)))["id"])
    data = (await client.get(f"{V1}/targets/achievement", headers=dm, params={"month": MONTH})).json()["data"]
    rows = {r["user"]["id"]: r for r in data["rows"]}
    me = rows[shop.ids["field_officer"]]["metrics"]["orders"]
    assert me == {"target": 4, "achieved": 1, "pct": "25.0"}
    assert shop.ids["district_manager"] in rows, "the caller is listed, without a target"
    assert shop.ids["state_manager"] not in rows, "review 7: a higher rank at my office is not mine to set"
    own = (await client.get(f"{V1}/targets/achievement", headers=fo, params={"month": MONTH})).json()["data"]
    assert [r["user"]["id"] for r in own["rows"]] == [shop.ids["field_officer"]]


async def test_global_sets_only_people_who_carry_targets(client: httpx.AsyncClient, shop: Shop) -> None:
    """Review 8: a target for a dealer, or for a global role, would never be seen."""
    admin = await endpoints._as(client, shop, "admin_sales")
    for who in ("dealer", "admin_sales"):
        r = await _put(client, admin, shop.ids[who])
        assert r.status_code == 422 and r.json()["error"]["code"] == "no_targets", (who, r.text)
    assert (await _put(client, admin, shop.ids["district_manager"])).status_code == 200
