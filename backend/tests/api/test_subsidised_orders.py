"""FS-054: subsidised sales orders, typed in, with the subsidy entered by hand."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import orders as domain
from api.errors import ForbiddenError
from api.schemas import orders as order_sch
from api.services import orders as order_service
from tests.api import test_order_endpoints as endpoints
from tests.api import test_order_partners as partners_t
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _lead(client: httpx.AsyncClient, shop: Shop, h: dict[str, str], *, qualify: bool = True) -> dict:
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "subsidised", "mis_system": "drip",
        "village": "Vadod"})
    assert r.status_code == 201, r.text
    lead = r.json()["data"]
    if qualify:
        for stage in ("contacted", "qualified"):
            r = await client.post(f"{V1}/leads/{lead['id']}/transition", headers={**h, **_key()},
                                  json={"to_stage": stage})
            assert r.status_code == 200, r.text
    return lead


def _body(shop: Shop, leads: list[str], **subsidy: object) -> dict[str, object]:
    return endpoints._direct(shop, order_type="subsidised",
                             subsidy={"lead_ids": leads, "subsidy_amount": "10.00", **subsidy})


async def _put(client: httpx.AsyncClient, h: dict[str, str], oid: str, **block: object) -> httpx.Response:
    return await client.put(f"{V1}/orders/{oid}/subsidy", headers={**h, **_key()}, json=block)


def _code(r: httpx.Response) -> str:
    return str(r.json()["error"]["code"])


async def test_a_subsidised_order_covers_two_leads_and_follows_its_total(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    a, b = await _lead(client, shop, ho), await _lead(client, shop, ho)
    order = await endpoints._create(client, ho, _body(shop, [a["id"], b["id"]]))
    total = Decimal(order["totals"]["total"])
    s = order["subsidy"]
    assert order["order_type"] == "subsidised" and order["lead"]["id"] == a["id"], "the first lead is the order's"
    assert (s["material_amount"], s["subsidy_amount"]) == (f"{total:.2f}", "10.00"), s
    assert s["farmer_payable"] == f"{total - 10:.2f}" and s["material_is_total"] and s["farmer_payable_is_derived"]
    assert [x["id"] for x in s["leads"]] == [a["id"], b["id"]]
    assert all(x["inquiry_no"] for x in s["leads"])

    # the second lead's timeline shows the order to a reader who sees the order
    tl = (await client.get(f"{V1}/leads/{b['id']}/timeline", headers=ho)).json()["data"]
    assert any(e["kind"] == "order.subsidy_set" for e in tl), [e["kind"] for e in tl]

    # rule 3a: a lines edit moves the default material
    r = await client.put(f"{V1}/orders/{order['id']}/lines", headers={**ho, **_key()},
                         json={"lines": [{"product_id": shop.product, "qty": "20", "discount_pct": "10"}]})
    assert r.status_code == 200, r.text
    moved = r.json()["data"]
    assert Decimal(moved["totals"]["total"]) > total
    assert moved["subsidy"]["material_amount"] == moved["totals"]["total"], "null means the total now"

    # rule 5: the first lead stays; the others may change
    r = await _put(client, ho, order["id"], lead_ids=[b["id"], a["id"]], subsidy_amount="10.00")
    assert r.status_code == 422 and _code(r) == "first_lead_fixed", r.text
    r = await _put(client, ho, order["id"], lead_ids=[a["id"]], subsidy_amount="999999999.00")
    assert r.status_code == 422 and _code(r) == "subsidy_above_material", r.text
    r = await _put(client, ho, order["id"], lead_ids=[a["id"]], material_amount="5000.00",
                   subsidy_amount="4000.00", farmer_payable="1500.00")
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert got["subsidy"]["material_amount"] == "5000.00" and not got["subsidy"]["material_is_total"]
    assert got["subsidy"]["farmer_payable"] == "1500.00" and not got["subsidy"]["farmer_payable_is_derived"]
    assert [x["id"] for x in got["subsidy"]["leads"]] == [a["id"]]
    assert "farmer_payable_not_material_less_subsidy" in got["warnings"], "kept, with a warning (GAP-451)"
    r = await _put(client, ho, order["id"], lead_ids=[a["id"]], material_amount="5000.00",
                   subsidy_amount="100.00", farmer_payable="5000.01")
    assert r.status_code == 422 and _code(r) == "payable_above_material", r.text

    # rule 5a: the type is fixed
    r = await client.patch(f"{V1}/orders/{order['id']}", headers={**ho, **_key()},
                           json={"order_type": "commercial"})
    assert r.status_code == 422 and _code(r) == "order_type_fixed", r.text

    # submit and approve along the total's chain; afterwards the block is fixed
    submitted = await endpoints._submit(client, ho, order["id"])
    assert submitted["status"] == "submitted"
    r = await _put(client, ho, order["id"], lead_ids=[a["id"]], subsidy_amount="10.00")
    assert r.status_code == 409 and _code(r) == "order_not_draft", r.text
    approved = await endpoints._approve_all(client, shop, submitted)
    assert approved["status"] == "approved", approved["status"]


async def test_the_refusals(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    a = await _lead(client, shop, ho)
    fresh = await _lead(client, shop, ho, qualify=False)

    async def post(h: dict[str, str], body: dict[str, object]) -> httpx.Response:
        return await client.post(f"{V1}/orders", json=body, headers={**h, **_key()})

    ds, dealer = await partners_t._as_dealer(sessions, shop)
    try:
        with pytest.raises(ForbiddenError) as err:
            await order_service.create_order(ds, dealer, order_sch.OrderCreate.model_validate(
                _body(shop, [a["id"]])), None)  # type: ignore[arg-type]
        assert err.value.code == "type_staff_only"
    finally:
        await ds.rollback()
        await ds.close()
    r = await post(ho, endpoints._direct(shop, order_type="subsidised"))
    assert r.status_code == 422 and _code(r) == "subsidy_missing", r.text
    r = await post(ho, {**_body(shop, [a["id"]]), "lead_id": a["id"]})
    assert r.status_code == 422 and _code(r) == "lead_from_subsidy", r.text
    r = await post(ho, endpoints._direct(shop, subsidy={"lead_ids": [a["id"]], "subsidy_amount": "1.00"}))
    assert r.status_code == 422 and _code(r) == "subsidy_not_allowed", r.text
    stranger = str(uuid.uuid4())
    r = await post(ho, _body(shop, [a["id"], stranger]))
    assert r.status_code == 422 and _code(r) == "lead_not_visible", r.text
    assert r.json()["error"]["fields"] == {"subsidy.lead_ids": stranger}
    r = await post(ho, _body(shop, [a["id"], fresh["id"]]))
    assert r.status_code == 422 and _code(r) == "lead_not_open", r.text
    r = await post(ho, _body(shop, [a["id"]], material_amount="500.00", subsidy_amount="500.01"))
    assert r.status_code == 422 and _code(r) == "subsidy_above_material", r.text
    r = await post(ho, _body(shop, [a["id"]], subsidy_amount="1.005"))
    assert r.status_code == 422, "paise only"
    # EC-5: a repeat is dropped
    once = await endpoints._create(client, ho, _body(shop, [a["id"], a["id"]]))
    assert [x["id"] for x in once["subsidy"]["leads"]] == [a["id"]]
    # a commercial order has no subsidy block
    plain = await endpoints._create(client, ho, endpoints._direct(shop))
    assert plain["subsidy"] is None
    r = await _put(client, ho, plain["id"], lead_ids=[a["id"]], subsidy_amount="1.00")
    assert r.status_code == 422 and _code(r) == "order_type_not_subsidised", r.text


async def test_submit_rechecks_every_named_lead(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Rule 5b, EC-4: a second lead lost after the order was made stops the submit."""
    ho = await endpoints._as(client, shop, "field_officer")
    a, b = await _lead(client, shop, ho), await _lead(client, shop, ho)
    order = await endpoints._create(client, ho, _body(shop, [a["id"], b["id"]]))
    s = sessions()
    try:
        await s.execute(text("UPDATE lead SET stage = 'lost', lost_reason_id = (SELECT id FROM won_lost_reason WHERE kind = 'lost' LIMIT 1) WHERE id = CAST(:l AS uuid)"), {"l": b["id"]})
        await s.commit()
    finally:
        await s.close()
    r = await client.post(f"{V1}/orders/{order['id']}/submit", json={}, headers={**ho, **_key()})
    assert r.status_code == 422 and _code(r) == "lead_not_open", r.text
    assert r.json()["error"]["fields"] == {"subsidy.lead_ids": b["id"]}


async def test_the_definer_refuses_what_the_service_refuses(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """The second enforcer: a changed first lead and a commercial order, called directly."""
    ho = await endpoints._as(client, shop, "field_officer")
    a, b = await _lead(client, shop, ho), await _lead(client, shop, ho)
    order = await endpoints._create(client, ho, _body(shop, [a["id"]]))
    plain = await endpoints._create(client, ho, endpoints._direct(shop))
    fo = shop.ids["field_officer"]
    for oid, leads, state in ((order["id"], [b["id"], a["id"]], "OSBFL"),
                              (plain["id"], [a["id"]], "OSBTY"),
                              (order["id"], [a["id"], a["id"]], "OSBLD")):
        s = sessions()
        try:
            await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": fo})
            await s.execute(text("SELECT set_config('role', 'app_role', true)"))
            with pytest.raises(Exception) as err:
                await s.execute(text("SELECT order_subsidy_set(CAST(:o AS uuid), NULL, 1, NULL, CAST(:l AS uuid[]))"),
                                {"o": oid, "l": leads})
            assert getattr(getattr(err.value, "orig", None), "sqlstate", None) == state, err.value
        finally:
            await s.rollback()
            await s.close()


async def test_the_dealer_gate_on_submit_names_subsidised(sessions: Sessions) -> None:
    s = sessions()
    try:
        body = (await s.execute(text("SELECT pg_get_functiondef('order_submit(uuid)'::regprocedure)"))).scalar_one()
        assert "IN ('export', 'sample', 'subsidised') AND app_current_partner() IS NOT NULL" in body
    finally:
        await s.close()


def test_the_definer_stages_are_the_orderable_stages() -> None:
    path = Path(__file__).resolve().parents[2] / "api/db/migrations/versions/067_subsidised_orders.py"
    spec = importlib.util.spec_from_file_location("mig_067_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(mod.ORDERABLE) == set(domain.LEAD_STAGES_ORDERABLE)


async def test_lines_dropping_below_the_subsidy_warn_then_stop_the_submit(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-2, EC-2: material left to the total; the lines fall under the subsidy."""
    ho = await endpoints._as(client, shop, "field_officer")
    a = await _lead(client, shop, ho)
    probe = await endpoints._create(client, ho, endpoints._direct(shop))
    total = Decimal(probe["totals"]["total"])
    order = await endpoints._create(client, ho, _body(shop, [a["id"]], subsidy_amount=f"{total - 1:.2f}"))
    assert order["warnings"].count("subsidy_above_material") == 0
    r = await client.put(f"{V1}/orders/{order['id']}/lines", headers={**ho, **_key()},
                         json={"lines": [{"product_id": shop.product, "qty": "1", "discount_pct": "10"}]})
    assert r.status_code == 200, r.text
    assert "subsidy_above_material" in r.json()["data"]["warnings"], r.json()["data"]["warnings"]
    r = await client.post(f"{V1}/orders/{order['id']}/submit", json={}, headers={**ho, **_key()})
    assert r.status_code == 422 and _code(r) == "subsidy_above_material", r.text


async def test_the_subsidy_rows_are_hidden_and_never_written_directly(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Code review F-3: a dealer sees no staff order's subsidy; nobody inserts past the definer."""
    ho = await endpoints._as(client, shop, "field_officer")
    a = await _lead(client, shop, ho)
    order = await endpoints._create(client, ho, _body(shop, [a["id"]]))

    async def _as(s: AsyncSession, who: str) -> None:
        await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": shop.ids[who]})
        await s.execute(text("SELECT set_config('role', 'app_role', true)"))

    for who, expect in (("field_officer", 1), ("dealer", 0)):
        s = sessions()
        try:
            await _as(s, who)
            for table in ("order_subsidy", "order_subsidy_lead"):
                n = (await s.execute(text(f"SELECT count(*) FROM {table} WHERE sales_order_id = CAST(:o AS uuid)"),
                                     {"o": order["id"]})).scalar_one()
                assert n == expect, (who, table, n)
        finally:
            await s.rollback()
            await s.close()
    s = sessions()
    try:
        await _as(s, "field_officer")
        with pytest.raises(Exception) as err:
            await s.execute(text("INSERT INTO order_subsidy (sales_order_id, subsidy_amount, updated_by) "
                                 "VALUES (CAST(:o AS uuid), 1, CAST(:u AS uuid))"),
                            {"o": order["id"], "u": shop.ids["field_officer"]})
        assert getattr(getattr(err.value, "orig", None), "sqlstate", None) == "42501", err.value
    finally:
        await s.rollback()
        await s.close()
