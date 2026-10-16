"""Price lists by sale type (FS-061): the preview, quotations, orders and publishing.

Built on the order endpoints' `shop`: a coded state with its own farmer list at
100.00 and a dealer list, priced on 2020-06-15. Each test adds typed lists scoped to
the shop's state; the shop's teardown removes every list in its state.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, Admin, _auth, _key
from tests.api.test_order_endpoints import AS_OF, Shop
from tests.api.test_product_endpoints import _window, trader

pytestmark = pytest.mark.db

shop = endpoints.shop
__all__ = ["shop", "trader"]


@dataclass
class Typed:
    shop: Shop
    lists: dict[str, str]          # sale type -> list id


async def _typed_list(s: AsyncSession, shop: Shop, sales_type: str, rate: str,
                      tier: str = "farmer") -> str:
    list_id = str((await s.execute(text(
        "INSERT INTO price_list (name, state_territory_id, channel_tier, sales_type, status, "
        "  published_at, effective_from, effective_to) "
        "VALUES (:n, CAST(:s AS uuid), CAST(:t AS channel_tier), :st, 'published', now(), "
        "  DATE '2020-01-01', DATE '2021-01-01') RETURNING id"),
        {"n": f"{sales_type} {tier} {uuid.uuid4().hex[:6]}", "s": shop.state, "t": tier,
         "st": sales_type})).scalar_one())
    await s.execute(text("INSERT INTO price_list_item (price_list_id, product_id, rate) "
                         "VALUES (CAST(:l AS uuid), CAST(:p AS uuid), CAST(:r AS numeric))"),
                    {"l": list_id, "p": shop.product, "r": rate})
    return list_id


@pytest_asyncio.fixture
async def typed(shop: Shop, sessions: Callable[[], AsyncSession]) -> Typed:
    """A commercial list at 90.00 and a subsidised one at 80.00, both for farmers in the
    shop's state. No industrial list: industrial falls to the general 100.00."""
    s = sessions()
    lists = {"commercial": await _typed_list(s, shop, "commercial", "90.00"),
             "subsidised": await _typed_list(s, shop, "subsidised", "80.00")}
    await s.commit()
    await s.close()
    return Typed(shop, lists)


async def _preview(client: httpx.AsyncClient, h: dict[str, str], shop: Shop,
                   **over: object) -> httpx.Response:
    body: dict[str, object] = {
        "as_of": AS_OF, "place_of_supply_territory_id": shop.district,
        "seller_gstin_id": shop.seller,
        "lines": [{"product_id": shop.product, "qty": "10"}]}
    body.update(over)
    return await client.post(f"{V1}/pricing/quote-lines", headers=h, json=body)


@pytest.mark.parametrize(("sales_type", "rate"), [
    ("commercial", "90.00"), ("subsidised", "80.00"), ("industrial", "100.00"),
    ("export", "100.00"), ("sample", "100.00"), (None, "100.00")])
async def test_the_preview_prices_from_the_sale_types_own_list_first(
        client: httpx.AsyncClient, typed: Typed, sales_type: str | None, rate: str) -> None:
    """Rules 2 to 4: a typed list beats the general one; another type's list never
    applies; sale types with no list of their own, and no sale type, use general lists."""
    h = await endpoints._as(client, typed.shop, "field_officer")
    r = await _preview(client, h, typed.shop, sales_type=sales_type)
    assert r.status_code == 200, r.text
    line = r.json()["data"]["lines"][0]
    assert line["rate"] == rate
    expected_list = typed.lists.get(sales_type or "")
    if expected_list:
        assert line["price_list_id"] == expected_list
    else:
        assert line["price_list_id"] not in typed.lists.values()


async def test_an_unknown_sale_type_on_the_preview_is_a_422(
        client: httpx.AsyncClient, typed: Typed) -> None:
    h = await endpoints._as(client, typed.shop, "field_officer")
    r = await _preview(client, h, typed.shop, sales_type="wholesale")
    assert r.status_code == 422, r.text


async def test_a_dealer_prices_from_a_typed_dealer_list(
        client: httpx.AsyncClient, shop: Shop, sessions: Callable[[], AsyncSession]) -> None:
    """EC-7: the restrictive tier policy and a sale type together. Staff pricing for the
    shop's dealer get the commercial dealer list; an industrial preview does not."""
    s = sessions()
    dealer_list = await _typed_list(s, shop, "commercial", "70.00", tier="dealer")
    await s.commit()
    await s.close()
    h = await endpoints._as(client, shop, "field_officer")
    r = await _preview(client, h, shop, partner_id=shop.partner, sales_type="commercial")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["lines"][0]["price_list_id"] == dealer_list
    r = await _preview(client, h, shop, partner_id=shop.partner, sales_type="industrial")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["lines"][0]["price_list_id"] != dealer_list


# ── quotations and orders ────────────────────────────────────────────────────

async def test_a_commercial_quotation_and_its_order_use_the_commercial_list(
        client: httpx.AsyncClient, typed: Typed) -> None:
    ho = await endpoints._as(client, typed.shop, "field_officer")
    q = await endpoints._accepted_quotation(client, typed.shop, ho)
    assert q["lines"][0]["rate"] == "90.00"
    order = await endpoints._create(client, ho, {"order_type": "commercial",
                                                  "quotation_ids": [q["id"]]})
    assert order["lines"][0]["rate"] == "90.00"
    assert order["totals"]["total"] == q["totals"]["total"]


async def test_an_industrial_order_is_not_made_from_a_commercial_quotation(
        client: httpx.AsyncClient, typed: Typed) -> None:
    """EC-3, GAP-474: the two now price from different lists."""
    ho = await endpoints._as(client, typed.shop, "field_officer")
    q = await endpoints._accepted_quotation(client, typed.shop, ho)
    r = await client.post(f"{V1}/orders", json={"order_type": "industrial",
                                                 "quotation_ids": [q["id"]]},
                          headers={**ho, **_key()})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "type_mismatch"


@pytest.mark.parametrize(("order_type", "rate"), [("commercial", "90.00"),
                                                  ("industrial", "100.00")])
async def test_a_direct_order_prices_from_its_types_list(
        client: httpx.AsyncClient, typed: Typed, order_type: str, rate: str) -> None:
    ho = await endpoints._as(client, typed.shop, "field_officer")
    order = await endpoints._create(client, ho, endpoints._direct(typed.shop,
                                                                  order_type=order_type))
    assert order["lines"][0]["rate"] == rate


async def test_changing_a_drafts_sale_type_reprices_it(
        client: httpx.AsyncClient, typed: Typed) -> None:
    """Rule 7."""
    shop = typed.shop
    ho = await endpoints._as(client, shop, "field_officer")
    lead = (await client.post(f"{V1}/leads", headers={**ho, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod"})).json()["data"]
    for stage in ("contacted", "qualified"):
        r = await client.post(f"{V1}/leads/{lead['id']}/transition", json={"to_stage": stage},
                              headers={**ho, **_key()})
        assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/quotations", headers={**ho, **_key()}, json={
        "lead_id": lead["id"], "sales_type": "commercial",
        "place_of_supply_territory_id": shop.district, "seller_gstin_id": shop.seller,
        "price_effective_date": AS_OF,
        "lines": [{"product_id": shop.product, "qty": "20"}]})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    assert q["lines"][0]["rate"] == "90.00"
    r = await client.patch(f"{V1}/quotations/{q['id']}", headers={**ho, **_key()},
                           json={"sales_type": "industrial"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["lines"][0]["rate"] == "100.00"


# ── the lists themselves ─────────────────────────────────────────────────────

async def test_a_list_is_created_with_a_sale_type_and_filtered_by_it(
        client: httpx.AsyncClient, trader: Admin) -> None:
    h = await _auth(client, trader.user)
    name = f"subsidy {uuid.uuid4().hex[:6]}"
    r = await client.post(f"{V1}/price-lists", headers={**h, **_key()},
                          json={"name": name, "sales_type": "subsidised", **_window()})
    assert r.status_code == 201, r.text
    created = r.json()["data"]
    assert created["sales_type"] == "subsidised" and created["status"] == "draft"

    def ids(resp: httpx.Response) -> set[str]:
        assert resp.status_code == 200, resp.text
        return {pl["id"] for pl in resp.json()["data"]}

    lists = f"{V1}/price-lists?status=draft&limit=100"
    assert created["id"] in ids(await client.get(f"{lists}&sales_type=subsidised", headers=h))
    assert created["id"] not in ids(await client.get(f"{lists}&sales_type=general", headers=h))
    assert created["id"] not in ids(await client.get(f"{lists}&sales_type=commercial",
                                                     headers=h))
    bad = await client.post(f"{V1}/price-lists", headers={**h, **_key()},
                            json={"name": name, "sales_type": "export", **_window()})
    assert bad.status_code == 422, bad.text


async def test_publishing_a_typed_list_never_closes_a_general_one(
        client: httpx.AsyncClient, trader: Admin) -> None:
    """EC-1: before the fix, a commercial list superseded the general list of the same
    state and tier, and every other sale type lost its prices from that day."""
    h = await _auth(client, trader.user)
    # a list superseded in the past would restate priced documents, so these start in
    # a future year of this run's own
    year = str(2200 + uuid.uuid4().int % 700)

    async def make(name: str, start: str, sales_type: str | None) -> dict:
        r = await client.post(f"{V1}/price-lists", headers={**h, **_key()}, json={
            "name": f"{name} {uuid.uuid4().hex[:6]}", "channel_tier": "distributor",
            "sales_type": sales_type, "effective_from": start})
        assert r.status_code == 201, r.text
        r = await client.post(f"{V1}/price-lists/{r.json()['data']['id']}/publish",
                              headers={**h, **_key()}, json={"allow_unpriced": True})
        assert r.status_code == 200, r.text
        return r.json()["data"]

    general = await make("general", f"{year}-01-01", None)
    commercial = await make("commercial", f"{year}-03-01", "commercial")
    assert commercial["closed_predecessor_id"] is None
    still = await client.get(f"{V1}/price-lists/{general['price_list']['id']}", headers=h)
    assert still.json()["data"]["effective_to"] is None, "the general list stays open"

    # a later commercial list still supersedes the earlier commercial one
    later = await make("commercial 2", f"{year}-05-01", "commercial")
    assert later["closed_predecessor_id"] == commercial["price_list"]["id"]
    # the admin fixture's teardown removes the lists this test published


async def test_the_database_keeps_typed_lists_apart_and_fixed(
        typed: Typed, sessions: Callable[[], AsyncSession]) -> None:
    """EC-2: the two exclusions refuse a second published list with the same state,
    tier and sale type over the same dates, and accept a different sale type. The
    011 trigger refuses changing a published list's sale type."""
    shop = typed.shop
    s = sessions()
    with pytest.raises(DBAPIError) as overlap:
        await _typed_list(s, shop, "commercial", "95.00")
        await s.flush()
    assert "ex_price_list_tiered" in str(overlap.value)   # the farmer tier is set
    await s.rollback()

    with pytest.raises(DBAPIError) as fixed:
        await s.execute(text("UPDATE price_list SET sales_type = 'industrial' "
                             "WHERE id = CAST(:l AS uuid)"), {"l": typed.lists["commercial"]})
    assert "scope and start date are fixed" in str(fixed.value)
    await s.rollback()

    with pytest.raises(DBAPIError) as bad:
        await s.execute(text("INSERT INTO price_list (name, sales_type, effective_from) "
                             "VALUES ('export list', 'export', DATE '2020-01-01')"))
    assert "ck_price_list_sales_type" in str(bad.value)
    await s.rollback()

    industrial = await _typed_list(s, shop, "industrial", "95.00")
    assert industrial
    await s.commit()
    await s.close()


async def test_extending_a_general_list_may_reach_over_a_typed_one(
        client: httpx.AsyncClient, trader: Admin) -> None:
    """Plan review C-1 and ISS-208: moving a closed list's end later checks only lists of
    its own sale type, and no longer fails with a 500."""
    h = await _auth(client, trader.user)
    year = 2200 + uuid.uuid4().int % 700

    async def make(start: str, end: str | None, sales_type: str | None) -> str:
        body: dict[str, object] = {"name": f"reach {uuid.uuid4().hex[:6]}",
                                   "channel_tier": "sub_dealer", "sales_type": sales_type,
                                   "effective_from": start}
        if end:
            body["effective_to"] = end
        r = await client.post(f"{V1}/price-lists", headers={**h, **_key()}, json=body)
        assert r.status_code == 201, r.text
        list_id = str(r.json()["data"]["id"])
        r = await client.post(f"{V1}/price-lists/{list_id}/publish", headers={**h, **_key()},
                              json={"allow_unpriced": True})
        assert r.status_code == 200, r.text
        return list_id

    general = await make(f"{year}-01-01", f"{year}-03-01", None)
    await make(f"{year}-03-01", None, "commercial")
    r = await client.patch(f"{V1}/price-lists/{general}", headers={**h, **_key()},
                           json={"effective_to": f"{year}-06-01"})
    assert r.status_code == 200, r.text

    await make(f"{year}-06-01", None, None)
    r = await client.patch(f"{V1}/price-lists/{general}", headers={**h, **_key()},
                           json={"effective_to": f"{year}-09-01"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "price_list_overlaps"


async def test_every_document_type_maps_to_a_list_type_or_to_general(
        sessions: Callable[[], AsyncSession]) -> None:
    """EC-6: every value either enum holds, today and after any later migration."""
    from api.domain.pricing.types import PRICE_LIST_SALES_TYPES, price_sales_type

    s = sessions()
    values = (await s.execute(text(
        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname IN ('quotation_sales_type', 'order_type')"))).scalars().all()
    await s.close()
    assert {"commercial", "industrial", "subsidised", "export", "replacement"} <= set(values)
    for value in values:
        mapped = price_sales_type(value)
        assert mapped == (value if value in PRICE_LIST_SALES_TYPES else None), value
