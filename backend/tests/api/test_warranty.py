# ruff: noqa: E501  (embedded SQL and request bodies)

"""FS-046 over the API: the periods, an order's warranty, and each complaint line's."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import warranty
from api.services.clock import today_ist
from tests.api import test_complaints as complaints_t
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


@pytest_asyncio.fixture(autouse=True)
async def _terms(shop: Shop, sessions: Sessions) -> AsyncIterator[None]:
    """Afterwards, every term but the seeded default goes, and the default is open
    again (a set closes the one in force). Depends on the shop so it runs before the
    shop removes the admin who created the terms."""
    yield
    s = sessions()
    # the approvals queue order messages, which no foreign key removes with the order;
    # test_migration_016 counts the last minute's rows
    await s.execute(text("DELETE FROM notification_outbox WHERE payload->>'order_no' IN "
                         "(SELECT order_no::text FROM sales_order WHERE territory_id = CAST(:d AS uuid))"),
                    {"d": shop.district})
    await s.execute(text("DELETE FROM activity_event WHERE kind = 'warranty_term.set'"))
    await s.execute(text("DELETE FROM warranty_term WHERE NOT (product_category_id IS NULL AND effective_from = DATE '2020-01-01')"))
    await s.execute(text("UPDATE warranty_term SET effective_to = NULL WHERE product_category_id IS NULL"))
    await s.commit()
    await s.close()


async def _category(sessions: Sessions, shop: Shop) -> str:
    s = sessions()
    try:
        return str((await s.execute(text("SELECT product_category_id FROM product WHERE id = CAST(:p AS uuid)"),
                                    {"p": shop.product})).scalar_one())
    finally:
        await s.close()


async def _term(client: httpx.AsyncClient, h: dict[str, str], **body: Any) -> httpx.Response:
    return await client.post(f"{V1}/warranty-terms", json=body, headers={**h, **_key()})


async def _dispatched(client: httpx.AsyncClient, shop: Shop, qty: str = "4") -> dict[str, Any]:
    """A direct order, approved, with one dispatch of `qty` of its line."""
    ho = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, ho, (await endpoints._create(client, ho, endpoints._direct(shop)))["id"]))
    dm = await endpoints._as(client, shop, "dispatch_manager")
    line = order["lines"][0]
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**dm, **_key()}, json={
        "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
        "lines": [{"order_line_id": line["id"], "qty": qty}]})
    assert r.status_code == 201, r.text
    return {**order, "dispatch_id": r.json()["data"]["id"]}


async def _warranty(client: httpx.AsyncClient, h: dict[str, str], order_id: str) -> httpx.Response:
    return await client.get(f"{V1}/orders/{order_id}/warranty", headers=h)


# ── the periods ──────────────────────────────────────────────────────────────

async def test_setting_a_period_from_tomorrow(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    admin = await endpoints._as(client, shop, "admin_sales")
    officer = await endpoints._as(client, shop, "field_officer")
    cat = await _category(sessions, shop)
    tomorrow = today_ist() + dt.timedelta(days=1)

    r = await _term(client, admin, product_category_id=cat, months=24, effective_from=tomorrow.isoformat())
    assert r.status_code == 201, r.text
    mine = [t for t in r.json()["data"] if t["product_category"] and t["product_category"]["id"] == cat]
    assert [(t["months"], t["effective_from"], t["effective_to"]) for t in mine] == [(24, tomorrow.isoformat(), None)]

    r = await _term(client, admin, product_category_id=cat, months=18, effective_from=tomorrow.isoformat())
    assert r.status_code == 409 and r.json()["error"]["code"] == "term_exists", r.text
    r = await _term(client, admin, product_category_id=cat, months=18, effective_from=today_ist().isoformat())
    assert r.status_code == 422 and "effective_from" in r.json()["error"]["fields"], r.text
    r = await _term(client, admin, product_category_id=cat, months=121, effective_from=tomorrow.isoformat())
    assert r.status_code == 422, r.text
    r = await _term(client, admin, product_category_id="00000000-0000-4000-8000-000000000000", months=6,
                    effective_from=tomorrow.isoformat())
    assert r.status_code == 422 and "product_category_id" in r.json()["error"]["fields"], r.text
    assert (await _term(client, officer, months=6, effective_from=tomorrow.isoformat())).status_code == 403

    # the default: a set closes the one in force at that day
    later = tomorrow + dt.timedelta(days=30)
    r = await _term(client, admin, months=6, effective_from=later.isoformat())
    assert r.status_code == 201, r.text
    defaults = [(t["months"], t["effective_from"], t["effective_to"]) for t in r.json()["data"] if t["product_category"] is None]
    assert defaults == [(12, "2020-01-01", later.isoformat()), (6, later.isoformat(), None)]
    r = await client.get(f"{V1}/warranty-terms", headers=admin)
    assert r.status_code == 200 and len(r.json()["data"]) == 3


async def test_the_list_needs_masters_view(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    hd, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        assert (await client.get(f"{V1}/warranty-terms", headers=hd)).status_code == 403
    finally:
        await complaints_t._forget(sessions, mobile)


# ── an order ─────────────────────────────────────────────────────────────────

async def test_an_orders_warranty_line_by_line(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    order = await _dispatched(client, shop)
    ho = await endpoints._as(client, shop, "field_officer")
    r = await _warranty(client, ho, order["id"])
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    today = today_ist()
    end = warranty.end_date(today, 12)
    assert end is not None
    [line] = data["lines"]
    assert (line["qty_ordered"], line["qty_dispatched"], line["status"]) == ("10.000", "4.000", "active")
    [d] = line["dispatches"]
    assert (d["start"], d["start_basis"], d["end"], d["months"], d["status"], d["qty"]) == (
        today.isoformat(), "dispatched_at", end.isoformat(), 12, "active", "4.000")
    assert data["replacement_for"] is None and line["claims"] == []

    # a category with no warranty from before today (an owner insert: the API refuses a past start)
    cat = await _category(sessions, shop)
    s = sessions()
    await s.execute(text("INSERT INTO warranty_term (product_category_id, months, effective_from) VALUES (CAST(:c AS uuid), 0, DATE '2026-01-01')"), {"c": cat})
    await s.commit()
    await s.close()
    line = (await _warranty(client, ho, order["id"])).json()["data"]["lines"][0]
    assert (line["status"], line["dispatches"][0]["status"], line["dispatches"][0]["end"]) == ("none", "none", None)

    # a void undoes the dispatch: no warranty left on the line
    dm = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.post(f"{V1}/dispatches/{d['dispatch_id']}/void", json={"remark": "wrong lorry"}, headers={**dm, **_key()})
    assert r.status_code == 200, r.text
    line = (await _warranty(client, ho, order["id"])).json()["data"]["lines"][0]
    assert (line["status"], line["dispatches"], line["qty_dispatched"]) == ("not_dispatched", [], "0.000")


async def test_a_dealer_cannot_read_another_partys_order(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    order = await _dispatched(client, shop)
    hd, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        r = await _warranty(client, hd, order["id"])
        assert r.status_code == 404, r.text
        qc = await endpoints._as(client, shop, "qc_manager")
        assert (await _warranty(client, qc, order["id"])).status_code == 403   # no sales_orders.view
    finally:
        await complaints_t._forget(sessions, mobile)


# ── a complaint ──────────────────────────────────────────────────────────────

async def test_a_complaint_line_shows_the_same_warranty_to_its_owner_and_to_qc(
        client: httpx.AsyncClient, shop: Shop) -> None:
    order = await _dispatched(client, shop)
    ho = await endpoints._as(client, shop, "field_officer")
    dm = await endpoints._as(client, shop, "district_manager")
    qc = await endpoints._as(client, shop, "qc_manager")
    c = await complaints_t._create(client, shop, ho, sales_order_id=order["id"])
    today = today_ist()
    expect = {"status": "in_warranty", "start": today.isoformat(),
              "end": warranty.end_date(today, 12).isoformat(),  # type: ignore[union-attr]
              "months": 12, "basis": "dispatch"}
    assert (await complaints_t._post(client, ho, f"/{c['id']}/submit")).status_code == 200
    r = await complaints_t._post(client, dm, f"/{c['id']}/check", {"decision": "approve", "remark": "Genuine"})
    assert r.status_code == 200, r.text
    owner = (await client.get(f"{V1}/complaints/{c['id']}", headers=ho)).json()["data"]["lines"][0]["warranty"]
    checker = (await client.get(f"{V1}/complaints/{c['id']}", headers=qc)).json()["data"]["lines"][0]["warranty"]
    assert owner == checker == expect, (owner, checker)

    # the order's tab lists it as a claim on the product
    [claim] = (await _warranty(client, ho, order["id"])).json()["data"]["lines"][0]["claims"]
    assert (claim["complaint_id"], claim["raised_on"], claim["warranty_status"], claim["defective_qty"]) == (
        c["id"], today.isoformat(), "in_warranty", "340.000")


async def test_without_an_order_the_supply_date_starts_it(client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    c = await complaints_t._create(client, shop, ho, supply_date="2024-02-29")
    w = (await client.get(f"{V1}/complaints/{c['id']}", headers=ho)).json()["data"]["lines"][0]["warranty"]
    # a draft is compared with today: 29 Feb 2024 + 12 months ended 28 Feb 2025
    assert w == {"status": "expired", "start": "2024-02-29", "end": "2025-02-28", "months": 12, "basis": "supply_date"}
    c = await complaints_t._create(client, shop, ho, supply_date=None, dc_no=None)
    w = (await client.get(f"{V1}/complaints/{c['id']}", headers=ho)).json()["data"]["lines"][0]["warranty"]
    assert w == {"status": "unknown", "start": None, "end": None, "months": None, "basis": None}


# ── code review ──────────────────────────────────────────────────────────────

async def test_two_admins_setting_the_default_at_once_both_succeed(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """F-1: the advisory lock serialises two sets. Without it the second overlaps
    the first and the exclusion constraint makes it a 500."""
    admin = await endpoints._as(client, shop, "admin_sales")
    d1 = today_ist() + dt.timedelta(days=10)
    d2 = today_ist() + dt.timedelta(days=20)
    r1, r2 = await asyncio.gather(_term(client, admin, months=18, effective_from=d1.isoformat()),
                                  _term(client, admin, months=24, effective_from=d2.isoformat()))
    assert (r1.status_code, r2.status_code) == (201, 201), (r1.text, r2.text)
    rows = (await client.get(f"{V1}/warranty-terms", headers=admin)).json()["data"]
    assert [(t["months"], t["effective_from"], t["effective_to"]) for t in rows if t["product_category"] is None] == [
        (12, "2020-01-01", d1.isoformat()), (18, d1.isoformat(), d2.isoformat()), (24, d2.isoformat(), None)]


async def test_the_complaint_warranty_function_answers_only_who_sees_the_complaint(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """F-2: the definer's own gate, without the endpoint's 404 in front of it."""
    ho = await endpoints._as(client, shop, "field_officer")
    c = await complaints_t._create(client, shop, ho)
    s = sessions()
    try:
        counts = {}
        for who in ("field_officer", "dealer"):
            await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": shop.ids[who]})
            await s.execute(text("SELECT set_config('role', 'app_role', true)"))
            counts[who] = (await s.execute(text("SELECT count(*) FROM complaint_warranty(CAST(:c AS uuid))"),
                                           {"c": c["id"]})).scalar_one()
            await s.rollback()
        assert counts == {"field_officer": 1, "dealer": 0}, counts
    finally:
        await s.close()


async def test_a_dc_date_starts_it_and_an_old_one_has_expired(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """F-4: the DC date arm, and expired on the order tab."""
    ho = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, ho, (await endpoints._create(client, ho, endpoints._direct(shop)))["id"]))
    dm = await endpoints._as(client, shop, "dispatch_manager")
    old = today_ist() - dt.timedelta(days=400)
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**dm, **_key()}, json={
        "dispatched_at": dt.datetime.now(dt.UTC).isoformat(), "dc_no": "DC-W1", "dc_date": old.isoformat(),
        "lines": [{"order_line_id": order["lines"][0]["id"], "qty": "2"}]})
    assert r.status_code == 201, r.text
    line = (await _warranty(client, ho, order["id"])).json()["data"]["lines"][0]
    d = line["dispatches"][0]
    assert (d["start"], d["start_basis"], d["end"], d["status"], line["status"]) == (
        old.isoformat(), "dc_date", warranty.end_date(old, 12).isoformat(), "expired", "expired")  # type: ignore[union-attr]


async def test_a_line_without_its_own_dispatch_is_not_dispatched(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """F-3: the same product on two lines, only the first shipped."""
    ho = await endpoints._as(client, shop, "field_officer")
    body = endpoints._direct(shop)
    body["lines"] = [{"product_id": shop.product, "qty": "5", "discount_pct": "10"},
                     {"product_id": shop.product, "qty": "3", "discount_pct": "10"}]
    order = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, ho, (await endpoints._create(client, ho, body))["id"]))
    dm = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**dm, **_key()}, json={
        "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
        "lines": [{"order_line_id": order["lines"][0]["id"], "qty": "5"}]})
    assert r.status_code == 201, r.text
    c = await complaints_t._create(client, shop, ho, sales_order_id=order["id"])
    assert (await complaints_t._post(client, ho, f"/{c['id']}/submit")).status_code == 200
    lines = (await _warranty(client, ho, order["id"])).json()["data"]["lines"]
    assert [(ln["status"], len(ln["dispatches"])) for ln in lines] == [("active", 1), ("not_dispatched", 0)]
    # the claim is on the product: both lines list it, against the product's anchor
    assert [[x["warranty_status"] for x in ln["claims"]] for ln in lines] == [["in_warranty"], ["in_warranty"]]
