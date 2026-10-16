# ruff: noqa: E501  (request bodies inline)

"""FS-052 over the API: land in hectares, the order filters by territory and office,
and the dashboard's area by system and target series (client sheet items 1, 2, 16,
19, 20)."""

from __future__ import annotations

import io
import uuid
from collections.abc import Callable

import httpx
import openpyxl
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _lead(client: httpx.AsyncClient, shop: Shop, h: dict[str, str], **land: str) -> httpx.Response:
    return await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod", **land})


async def test_land_is_hectares_and_acres_still_work(client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    r = await _lead(client, shop, ho, land_hectares="1.82")
    assert r.status_code == 201, r.text
    lead = r.json()["data"]
    assert (lead["land_hectares"], lead["land_acres"]) == ("1.82", "4.50"), lead
    assert lead["state_name"], "the state above the territory"
    r = await _lead(client, shop, ho, land_acres="4.50")
    assert r.status_code == 201 and r.json()["data"]["land_hectares"] == "1.82", r.text
    r = await _lead(client, shop, ho, land_acres="4.50", land_hectares="1.82")
    assert r.status_code == 422 and "land_acres" in r.json()["error"]["fields"], "not both"
    r = await _lead(client, shop, ho, land_acres="0.01")
    assert r.status_code == 422, "under a hundredth of a hectare (plan review B-1)"
    r = await client.patch(f"{V1}/leads/{lead['id']}", headers={**ho, **_key()},
                           json={"land_hectares": None, "land_acres": None})
    assert r.status_code == 200 and r.json()["data"]["land_hectares"] is None, "a clear sends both null"

    # item 20: the export names the state and the hectares
    r = await client.get(f"{V1}/leads/export", headers=ho, params={"q": lead["inquiry_no"]})
    assert r.status_code == 200, r.text
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    header = [c.value for c in next(ws.iter_rows(max_row=1))]
    assert "State" in header and "Land (ha)" in header, header


async def test_orders_filter_by_territory_and_office(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._create(client, ho, endpoints._direct(shop))
    admin = await endpoints._as(client, shop, "admin_sales")
    s = sessions()
    try:
        state = str((await s.execute(text(
            "SELECT t.id FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id "
            "WHERE tc.descendant_id = CAST(:d AS uuid) AND t.level = 'state'"), {"d": shop.district})).scalar_one())
        elsewhere = str((await s.execute(text(
            "SELECT id FROM territory WHERE level = 'state' AND id <> CAST(:s AS uuid) LIMIT 1"), {"s": state})).scalar_one())
        office = str((await s.execute(text("SELECT owner_org_unit_id FROM sales_order WHERE id = CAST(:o AS uuid)"),
                                      {"o": order["id"]})).scalar_one())
    finally:
        await s.close()

    async def _ids(**params: str) -> set[str]:
        r = await client.get(f"{V1}/orders", headers=admin, params={"limit": 100, **params})
        assert r.status_code == 200, r.text
        return {o["id"] for o in r.json()["data"]}

    assert order["id"] in await _ids(territory_id=state), "a state selects its districts"
    assert order["id"] in await _ids(territory_id=f"{elsewhere},{shop.district}")
    assert order["id"] not in await _ids(territory_id=elsewhere)
    assert order["id"] in await _ids(owner_org_unit_id=office)
    stats = await client.get(f"{V1}/orders/stats", headers=admin, params={"territory_id": elsewhere})
    assert stats.status_code == 200, stats.text
    r = await client.get(f"{V1}/orders", headers=admin, params={"territory_id": "not-an-id"})
    assert r.status_code == 422, r.text


async def test_the_dashboard_has_area_by_system_and_six_months_of_targets(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    assert (await _lead(client, shop, ho, land_hectares="2.00")).status_code == 201
    assert (await _lead(client, shop, ho, land_hectares="3.50")).status_code == 201
    dm = await endpoints._as(client, shop, "district_manager")
    r = await client.get(f"{V1}/dashboard/overview", headers=dm)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    drip = next(a for a in body["area_by_system"] if a["system"] == "drip")
    assert drip["leads"] >= 2 and float(drip["hectares"]) >= 5.5, drip
    months = body["targets_by_month"]
    assert months is not None and len(months) == 6, months
    assert months == sorted(months, key=lambda m: m["month"]), "oldest first"
    assert all(m["target"] is not None for m in months)
    hd = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.get(f"{V1}/dashboard/overview", headers=hd)
    assert r.status_code == 200, "never a 403, whatever the role"
