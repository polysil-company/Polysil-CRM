"""FS-084 (BE-043): the order picker adds the distributors above the partners under
a field officer's area, and the officer can price and quote with one.

Built on FS-020's `area`: a field officer in a taluka office under the shop's
district, and a second district ("far") outside every office's area."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import random
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import V1, _key
from tests.api.test_dealer_area_access import Area, _lead, _officer, _quote_body, area
from tests.api.test_order_endpoints import AS_OF, Shop, shop

pytestmark = pytest.mark.db
__all__ = ["area", "shop"]


@dataclass
class World:
    tag: str
    supplier: str       # in the far district, above a dealer in the officer's taluka
    via_sub: str        # in the far district, above a far dealer above a taluka sub-dealer
    lone: str           # in the far district, above a far dealer only
    state_only: str     # above a dealer registered for the whole state (rule 7)
    dead_link: str      # above a switched-off taluka dealer (GAP-569)
    mine: list[str]     # every partner made here, children first


@pytest_asyncio.fixture
async def world(shop: Shop, area: Area, sessions: Callable[[], AsyncSession]) -> AsyncIterator[World]:
    tag = uuid.uuid4().hex[:6].upper()
    s = sessions()
    made: list[str] = []

    async def partner(ty: str, name: str, territory: str, parent: str | None = None,
                      active: bool = True) -> str:
        pid = str((await s.execute(text(
            "INSERT INTO channel_partner (parent_id, partner_type, code, name, mobile, territory_id, price_tier, is_active) "
            "VALUES (CAST(:p AS uuid), CAST(:ty AS partner_type), :c, :n, :m, CAST(:t AS uuid), CAST(:tier AS channel_tier), :a) RETURNING id"),
            {"p": parent, "ty": ty, "c": f"{name[:3]}{tag}{len(made)}", "n": f"{name} {tag}",
             "m": "9195" + f"{random.randint(0, 10**8 - 1):08d}", "t": territory,
             "tier": ty, "a": active})).scalar_one())
        made.insert(0, pid)
        return pid

    supplier = await partner("distributor", "Aasha Supplier", area.far_district)
    await partner("dealer", "Taluka Retailer", area.taluka, supplier)
    via_sub = await partner("distributor", "Bharat Supplier", area.far_district)
    middle = await partner("dealer", "Far Middle Dealer", area.far_district, via_sub)
    await partner("sub_dealer", "Taluka Sub Dealer", area.taluka, middle)
    lone = await partner("distributor", "Lone Distributor", area.far_district)
    await partner("dealer", "Lone Far Dealer", area.far_district, lone)
    state_only = await partner("distributor", "State Only Distributor", area.far_district)
    await partner("dealer", "State Wide Dealer", shop.state, state_only)
    dead_link = await partner("distributor", "Dead Link Distributor", area.far_district)
    await partner("dealer", "Closed Taluka Dealer", area.taluka, dead_link, active=False)
    # the shop prices farmers and dealers only; a supplier prices at its own tier
    price_list = str((await s.execute(text(
        "INSERT INTO price_list (name, state_territory_id, channel_tier, status, published_at, "
        "effective_from, effective_to) VALUES (:n, CAST(:s AS uuid), 'distributor', 'published', now(), "
        "DATE '2020-01-01', DATE '2021-01-01') RETURNING id"), {"n": f"distributor list {tag}", "s": shop.state})).scalar_one())
    await s.execute(text("INSERT INTO price_list_item (price_list_id, product_id, rate) "
                         "VALUES (CAST(:l AS uuid), CAST(:p AS uuid), 80)"), {"l": price_list, "p": shop.product})
    await s.commit()
    await s.close()
    try:
        yield World(tag, supplier, via_sub, lone, state_only, dead_link, made)
    finally:
        c = sessions()
        # the quotations priced from the distributor list hold its rows
        quotes = ("(SELECT id FROM quotation WHERE price_list_id = CAST(:pl AS uuid) "
                  "OR partner_id = ANY(CAST(:cp AS uuid[])))")
        for stmt in (
            "ALTER TABLE quotation DISABLE TRIGGER trg_quotation_refuse_sent_edit",
            f"DELETE FROM approval_step WHERE request_id IN (SELECT id FROM approval_request WHERE entity_id IN {quotes})",
            f"DELETE FROM approval_request WHERE entity_id IN {quotes}",
            f"DELETE FROM activity_event WHERE entity_id IN {quotes}",
            f"DELETE FROM quotation_line WHERE quotation_id IN {quotes}",
            f"UPDATE quotation SET supersedes_id = NULL, superseded_by_id = NULL WHERE id IN {quotes}",
            f"DELETE FROM quotation WHERE id IN {quotes}",
            "ALTER TABLE quotation ENABLE TRIGGER trg_quotation_refuse_sent_edit",
            "UPDATE lead SET assigned_partner_id = NULL WHERE assigned_partner_id = ANY(CAST(:cp AS uuid[]))",
            "DELETE FROM price_list_item WHERE price_list_id = CAST(:pl AS uuid)",
            "DELETE FROM price_list WHERE id = CAST(:pl AS uuid)",
        ):
            await c.execute(text(stmt), {"cp": made, "pl": price_list})
        for pid in made:  # children first
            await c.execute(text("DELETE FROM channel_partner WHERE id = CAST(:p AS uuid)"), {"p": pid})
        await c.commit()
        await c.close()


async def _pick(client: httpx.AsyncClient, h: dict[str, str], **params: object) -> list[dict]:
    r = await client.get(f"{V1}/lookups/partners", params={"limit": 100, **params}, headers=h)
    assert r.status_code == 200, r.text
    return list(r.json()["data"])


async def test_the_order_picker_adds_the_distributors_that_supply_the_area(
        client: httpx.AsyncClient, shop: Shop, area: Area, world: World) -> None:
    """Rules 1, 2, 3 and 7, EC-11 (depth 2)."""
    ho = await _officer(client, area)
    rows = await _pick(client, ho, q=world.tag, **{"for": "order"})
    by_id = {r["id"]: r for r in rows}
    assert by_id[world.supplier]["supplies_your_area"] is True
    assert by_id[world.via_sub]["supplies_your_area"] is True, "a sub-dealer reaches it at depth 2"
    for absent in (world.lone, world.state_only, world.dead_link):
        assert absent not in by_id
    # the area rows are there too, unflagged; only distributors are added
    assert all(not r["supplies_your_area"] for r in rows if r["partner_type"] != "distributor")
    plain = {r["id"] for r in await _pick(client, ho, q=world.tag)}
    assert world.supplier not in plain and world.via_sub not in plain, "lead assignment is unchanged"


async def test_the_merge_orders_and_cuts_both_kinds_of_row_together(
        client: httpx.AsyncClient, area: Area, world: World) -> None:
    """EC-9, plan review C-3: "Aasha Supplier" sorts first, ahead of every area row."""
    ho = await _officer(client, area)
    full = await _pick(client, ho, q=world.tag, **{"for": "order"})
    assert full[0]["id"] == world.supplier
    one = await _pick(client, ho, q=world.tag, limit=1, **{"for": "order"})
    assert [r["id"] for r in one] == [world.supplier]


async def test_a_dealer_login_cannot_use_the_order_picker(
        client: httpx.AsyncClient, shop: Shop, area: Area, world: World,
        sessions: Callable[[], AsyncSession]) -> None:
    """Rule 4."""
    from tests.api.test_complaints import _dealer, _forget
    h, mobile = await _dealer(client, shop, sessions)
    try:
        r = await client.get(f"{V1}/lookups/partners", params={"for": "order"}, headers=h)
        assert r.status_code == 403, r.text
    finally:
        await _forget(sessions, mobile)


async def test_an_officer_prices_and_quotes_through_a_supplier(
        client: httpx.AsyncClient, shop: Shop, area: Area, world: World) -> None:
    """EC-1: the INSERT check and the parent guard take partner_orderable. A
    distributor that supplies nobody in the area stays refused."""
    ho = await _officer(client, area)

    def preview(partner: str) -> dict[str, object]:
        return {"place_of_supply_territory_id": shop.district, "partner_id": partner, "as_of": AS_OF,
                "seller_gstin_id": shop.seller, "lines": [{"product_id": shop.product, "qty": "1"}]}

    r = await client.post(f"{V1}/pricing/quote-lines", headers=ho, json=preview(world.supplier))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["lines"][0]["rate"] == "80.00", "priced at the distributor's tier"
    r = await client.post(f"{V1}/pricing/quote-lines", headers=ho, json=preview(world.lone))
    assert r.status_code == 422 and "partner_id" in r.json()["error"]["fields"], r.text

    lead = await _lead(client, ho, area.taluka)
    r = await client.post(f"{V1}/quotations", json={**_quote_body(shop, lead["id"]), "partner_id": world.supplier},
                          headers={**ho, **_key()})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    assert q["partner"]["id"] == world.supplier and q["partner"]["name"] == f"Aasha Supplier {world.tag}"

    r = await client.patch(f"{V1}/quotations/{q['id']}", json={"partner_id": world.via_sub, "expected_status": "draft"},
                           headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    r = await client.patch(f"{V1}/quotations/{q['id']}", json={"partner_id": world.lone, "expected_status": "draft"},
                           headers={**ho, **_key()})
    assert r.status_code in (403, 422), r.text
