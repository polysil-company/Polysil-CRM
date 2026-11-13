"""Ratings (FS-043) end to end: feedback on installation, product and service, who
may rate and see what, and the dealer rating derived from payments.

Built on the complaint remedies' `remedies` shop (orders, dispatch, complaints
walked to closed). This file's fixture removes its ratings, receipts and setting
changes before the shop's teardown deletes the documents they point at.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import json
import uuid
from collections.abc import AsyncIterator, Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from api.errors import ForbiddenError, NotFoundError
from api.schemas import ratings as sch
from api.services import orders as order_service
from api.services import ratings as service
from api.services.clock import today_ist
from tests.api import test_complaint_remedies as remedies_t
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key
from tests.api.test_order_partners import _as_dealer

pytestmark = pytest.mark.db

shop = endpoints.shop
remedies = remedies_t.remedies
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
SETTINGS = ("dealer_rating_window_days", "dealer_rating_payment_days", "dealer_rating_order_value")


@pytest_asyncio.fixture
async def rx(remedies: Shop, sessions: Sessions) -> AsyncIterator[Shop]:
    s = sessions()
    saved = dict((await s.execute(text("SELECT key::text, value::text FROM app_setting WHERE key = ANY(:k)"),
                                  {"k": list(SETTINGS)})).all())
    await s.close()
    try:
        yield remedies
    finally:
        c = sessions()
        people = list(remedies.ids.values())
        for stmt in (
            "DELETE FROM rating WHERE entered_by = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM payment_allocation WHERE created_by = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM activity_event WHERE kind LIKE 'payment.%' AND actor_id = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM payment WHERE entered_by = ANY(CAST(:p AS uuid[]))",
        ):
            await c.execute(text(stmt), {"p": people})
        for key, value in saved.items():
            await c.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = :k"),
                            {"k": key, "v": value})
        # a PATCH stamps the shop's admin on the row; the shop deletes its people next
        await c.execute(text("UPDATE app_setting SET updated_by = NULL WHERE updated_by = ANY(CAST(:p AS uuid[]))"),
                        {"p": people})
        await c.execute(text("DELETE FROM activity_event WHERE kind = 'setting.changed' AND actor_id = ANY(CAST(:p AS uuid[]))"),
                        {"p": people})
        await c.commit()
        await c.close()


def _code(r: httpx.Response) -> str:
    return str(r.json()["error"]["code"])


async def _dispatched(client: httpx.AsyncClient, shop: Shop, **over: Any) -> dict:
    """A direct order, approved and half shipped."""
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._submit(client, fo, (await endpoints._create(client, fo, endpoints._direct(shop, **over)))["id"])
    order = await endpoints._approve_all(client, shop, order)
    hd = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()},
                          json={"dc_no": "DC-R", "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
                                "lines": [{"order_line_id": order["lines"][0]["id"], "qty": "4"}]})
    assert r.status_code == 201, r.text
    return order


async def _rate(client: httpx.AsyncClient, h: dict[str, str], **body: Any) -> httpx.Response:
    return await client.post(f"{V1}/ratings", headers={**h, **_key()}, json={"score": 4, **body})


# ── feedback ─────────────────────────────────────────────────────────────────

async def test_an_installation_is_rated_once_after_it_ships(client: httpx.AsyncClient, rx: Shop) -> None:
    """Rules 2, 5, 6: nothing shipped, nothing to rate; once shipped, one rating by
    staff on the farmer's behalf, and the event on the order's timeline."""
    fo = await endpoints._as(client, rx, "field_officer")
    approved = await endpoints._approve_all(client, rx, await endpoints._submit(
        client, fo, (await endpoints._create(client, fo, endpoints._direct(rx)))["id"]))
    r = await _rate(client, fo, target="installation", sales_order_id=approved["id"])
    assert r.status_code == 422 and _code(r) == "not_rateable", r.text

    order = await _dispatched(client, rx)
    r = await _rate(client, fo, target="installation", sales_order_id=order["id"], score=2,
                    comment="  Drippers clogged in week two.  ")
    assert r.status_code == 201, r.text
    got = r.json()["data"]
    assert (got["rated_by"], got["score"], got["comment"]) == ("customer", 2, "Drippers clogged in week two.")
    assert got["order"]["status"] == "partially_dispatched" and got["entered_by"]["id"] == rx.ids["field_officer"]
    r = await _rate(client, fo, target="installation", sales_order_id=order["id"])
    assert r.status_code == 409 and _code(r) == "rating_exists", r.text

    tl = (await client.get(f"{V1}/orders/{order['id']}/timeline", headers=fo)).json()["data"]
    event = next(e for e in tl if e["kind"] == "rating.recorded")
    assert event["payload"]["score"] == 2 and "comment" not in event["payload"]

    low = (await client.get(f"{V1}/ratings", headers=fo, params={"max_score": 2, "sales_order_id": order["id"]})).json()
    assert [x["id"] for x in low["data"]] == [got["id"]]


async def test_a_product_is_rated_only_once_it_has_shipped_on_that_order(client: httpx.AsyncClient, rx: Shop) -> None:
    fo = await endpoints._as(client, rx, "field_officer")
    order = await _dispatched(client, rx)
    r = await _rate(client, fo, target="product", sales_order_id=order["id"], product_id=str(uuid.uuid4()))
    assert r.status_code == 422 and _code(r) == "product_not_shipped", r.text
    r = await _rate(client, fo, target="product", sales_order_id=order["id"], product_id=rx.product, score=5)
    assert r.status_code == 201 and r.json()["data"]["product"]["id"] == rx.product, r.text
    r = await _rate(client, fo, target="product", sales_order_id=order["id"])
    assert r.status_code == 422, "a product rating names its product"


async def test_a_service_is_rated_once_the_complaint_is_closed(client: httpx.AsyncClient, rx: Shop) -> None:
    c = await remedies_t._qc_approved(client, rx)
    fo = await endpoints._as(client, rx, "field_officer")
    r = await _rate(client, fo, target="service", complaint_id=c["id"])
    assert r.status_code == 422 and _code(r) == "not_rateable", r.text
    qc = await remedies_t._as(client, rx, "qc_manager")
    assert (await remedies_t._remedy(client, qc, c["id"], kind="none", remark="Fixed on site")).status_code == 200
    r = await _rate(client, fo, target="service", complaint_id=c["id"], score=5)
    assert r.status_code == 201 and r.json()["data"]["complaint"]["status"] == "closed", r.text


async def test_a_dealer_rates_its_own_and_reads_a_farmers_rating_as_a_score(
        client: httpx.AsyncClient, rx: Shop, sessions: Sessions) -> None:
    """Rules 5 and 14, and plan review B-2: the dealer's own rating is `dealer`; the
    farmer's comment and the staff name never reach it, nor the event's actor."""
    fo = await endpoints._as(client, rx, "field_officer")
    order = await _dispatched(client, rx, partner_id=rx.partner)
    r = await _rate(client, fo, target="installation", sales_order_id=order["id"], score=1,
                    comment="Dealer charged over the quote")
    assert r.status_code == 201, r.text

    s, dealer = await _as_dealer(sessions, rx)
    try:
        mine = await service.record(s, dealer, sch.RatingCreate(target="installation", sales_order_id=order["id"], score=4))
        assert mine.rated_by == "dealer"
        page = await service.list_ratings(s, dealer, sales_order_id=order["id"])
        theirs = next(x for x in page.data if x.rated_by == "customer")
        assert (theirs.score, theirs.comment, theirs.entered_by) == (1, None, None)
        tl = (await order_service.timeline(s, dealer, order["id"])).data
        events = [e for e in tl if e.kind == "rating.recorded"]
        assert events and all(e.actor is None for e in events)
    finally:
        await s.rollback()
        await s.close()


async def test_a_dealer_cannot_rate_a_document_that_is_not_its_own(
        client: httpx.AsyncClient, rx: Shop, sessions: Sessions) -> None:
    order = await _dispatched(client, rx)   # a direct sale: no dealer
    s, dealer = await _as_dealer(sessions, rx)
    try:
        # a direct sale is not the dealer's to see, so not to rate
        with pytest.raises(NotFoundError):
            await service.record(s, dealer, sch.RatingCreate(target="installation", sales_order_id=order["id"], score=3))
    finally:
        await s.rollback()
        await s.close()


# ── the derived dealer rating ────────────────────────────────────────────────

async def test_the_dealer_rating_is_derived_the_same_for_every_reader(
        client: httpx.AsyncClient, rx: Shop, sessions: Sessions) -> None:
    """Rules 8 to 13 and edge 2: an order paid the day it was placed scores 5 on
    payment; its value scores against the bands; Accounts, the district manager and
    the dealer itself read the same figures; a field officer gets 403."""
    order = await _dispatched(client, rx, partner_id=rx.partner)
    accounts = await endpoints._as(client, rx, "account_manager")
    total = order["totals"]["total"]
    r = await client.post(f"{V1}/payments", headers={**accounts, **_key()}, json={
        "mode": "neft", "ref_no": "UTR" + uuid.uuid4().hex[:10], "received_on": today_ist().isoformat(),
        "partner_id": rx.partner, "amount": total,
        "allocations": [{"sales_order_id": order["id"], "amount": total}]})
    assert r.status_code == 201, r.text
    s = sessions()
    try:
        await s.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = 'dealer_rating_order_value'"),
                        {"v": json.dumps([100, 500, 1000, 5000])})
        await s.commit()
    finally:
        await s.close()

    r = await client.get(f"{V1}/partners/{rx.partner}/dealer-rating", headers=accounts)
    assert r.status_code == 200, r.text
    card = r.json()["data"]
    taxable = Decimal(order["totals"]["taxable"])
    assert (card["orders"], card["paid_orders"], card["payment_days"], card["payment_score"]) == (1, 1, "0.0", 5)
    assert card["order_value"] == f"{taxable:.2f}"
    expected_value_score = 4 if taxable >= 1000 else 3
    assert card["value_score"] == expected_value_score
    assert card["rating"] == f"{(5 + expected_value_score) / 2:.1f}"

    dm = await endpoints._as(client, rx, "district_manager")
    assert (await client.get(f"{V1}/partners/{rx.partner}/dealer-rating", headers=dm)).json()["data"] == card
    fo = await endpoints._as(client, rx, "field_officer")
    r = await client.get(f"{V1}/partners/{rx.partner}/dealer-rating", headers=fo)
    assert r.status_code == 403 and _code(r) == "rating_not_permitted", r.text

    d, _dealer = await _as_dealer(sessions, rx)
    try:
        own = await service.dealer_rating(d, rx.partner)
        assert own.model_dump(mode="json") == card
    except ForbiddenError:
        pytest.fail("the dealer reads its own rating")
    finally:
        await d.rollback()
        await d.close()


async def test_bands_settings_are_listed_and_held_to_four_rising_whole_numbers(
        client: httpx.AsyncClient, rx: Shop) -> None:
    admin = await endpoints._as(client, rx, "admin_sales")
    got = {x["key"]: x for x in (await client.get(f"{V1}/settings", headers=admin)).json()["data"]}
    assert got["dealer_rating_payment_days"]["kind"] == "bands"
    assert got["dealer_rating_payment_days"]["value"] == [7, 15, 30, 60]
    for bad in ([7, 7, 30, 60], [7, 15.5, 30, 60], ["7", "15", "30", "60"], [7, 15, 30], [-1, 15, 30, 60]):
        r = await client.patch(f"{V1}/settings", headers={**admin, **_key()},
                               json={"values": {"dealer_rating_payment_days": bad}})
        assert r.status_code == 422, (bad, r.text)
    r = await client.patch(f"{V1}/settings", headers={**admin, **_key()},
                           json={"values": {"dealer_rating_payment_days": [0, 15, 30, 60]}})
    assert r.status_code == 200, r.text



# ── code review: tests that fail when the rule breaks ────────────────────────

async def _owner(sessions: Sessions, *stmts: tuple[str, dict[str, Any]]) -> None:
    """Statements as the table owner, triggers off: backdating a submitted order is
    not something any path in the system may do."""
    s = sessions()
    try:
        await s.execute(text("ALTER TABLE sales_order DISABLE TRIGGER USER"))
        for sql, params in stmts:
            await s.execute(text(sql), params)
        await s.execute(text("ALTER TABLE sales_order ENABLE TRIGGER USER"))
        await s.commit()
    finally:
        await s.close()


async def _dealer_order(client: httpx.AsyncClient, shop: Shop, qty: str) -> dict:
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._submit(client, fo, (await endpoints._create(
        client, fo, endpoints._direct(shop, qty=qty, partner_id=shop.partner)))["id"])
    return await endpoints._approve_all(client, shop, order)


async def test_the_dealer_rating_weights_days_by_value_and_leaves_out_young_unpaid_orders(
        client: httpx.AsyncClient, rx: Shop, sessions: Sessions) -> None:
    """Rules 10 to 13 with numbers that move (code review F-1, F-5). A: paid today,
    placed 10 days ago. B: unpaid, 20 days. E: unpaid, exactly the first band (7
    days), so it counts. C: unpaid, 3 days, younger than the band, so it does not.
    Payment days are the value-weighted mean of A, B and E; value counts all four."""
    a = await _dealer_order(client, rx, "10")
    b = await _dealer_order(client, rx, "2")
    c = await _dealer_order(client, rx, "1")
    e = await _dealer_order(client, rx, "3")
    accounts = await endpoints._as(client, rx, "account_manager")
    r = await client.post(f"{V1}/payments", headers={**accounts, **_key()}, json={
        "mode": "neft", "ref_no": "UTR" + uuid.uuid4().hex[:10], "received_on": today_ist().isoformat(),
        "partner_id": rx.partner, "amount": a["totals"]["total"],
        "allocations": [{"sales_order_id": a["id"], "amount": a["totals"]["total"]}]})
    assert r.status_code == 201, r.text
    back = "UPDATE sales_order SET submitted_at = now() - make_interval(days => :n) WHERE id = CAST(:o AS uuid)"
    await _owner(sessions, (back, {"n": 10, "o": a["id"]}), (back, {"n": 20, "o": b["id"]}),
                 (back, {"n": 3, "o": c["id"]}), (back, {"n": 7, "o": e["id"]}),
                 ("UPDATE app_setting SET value = '[7, 15, 30, 60]' WHERE key = 'dealer_rating_payment_days'", {}),
                 ("UPDATE app_setting SET value = '[100, 500, 1000, 5000]' WHERE key = 'dealer_rating_order_value'", {}))

    t = {k: Decimal(o["totals"]["taxable"]) for k, o in (("a", a), ("b", b), ("c", c), ("e", e))}
    weighted = (10 * t["a"] + 20 * t["b"] + 7 * t["e"]) / (t["a"] + t["b"] + t["e"])
    days = weighted.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    score = next((sc for edge, sc in ((7, 5), (15, 4), (30, 3), (60, 2)) if days <= edge), 1)
    value = sum(t.values())
    vscore = next((sc for edge, sc in ((5000, 5), (1000, 4), (500, 3), (100, 2)) if value >= edge), 1)

    card = (await client.get(f"{V1}/partners/{rx.partner}/dealer-rating", headers=accounts)).json()["data"]
    assert (card["orders"], card["paid_orders"]) == (4, 1)
    assert card["payment_days"] == f"{days}" and card["payment_score"] == score
    assert card["order_value"] == f"{value:.2f}" and card["value_score"] == vscore
    assert card["rating"] == f"{Decimal(score + vscore) / 2:.1f}"


async def test_a_dealer_reads_no_rating_on_a_document_it_cannot_see(
        client: httpx.AsyncClient, rx: Shop, sessions: Sessions) -> None:
    """Code review F-2: the read policy, negative. A customer rating on a direct sale
    is invisible to the dealer, in the list and in the summary."""
    fo = await endpoints._as(client, rx, "field_officer")
    order = await _dispatched(client, rx)
    assert (await _rate(client, fo, target="installation", sales_order_id=order["id"])).status_code == 201
    s, dealer = await _as_dealer(sessions, rx)
    try:
        assert (await service.list_ratings(s, dealer, sales_order_id=order["id"])).data == []
        assert await service.summary(s, group_by="target") == []
    finally:
        await s.rollback()
        await s.close()


async def test_a_dealer_cannot_rate_its_sub_dealers_order(
        client: httpx.AsyncClient, rx: Shop, sessions: Sessions) -> None:
    """Edge 8, code review F-3: the dealer sees a sub-dealer's order through its
    subtree, and is still refused (`not_your_order`). All in one rolled-back
    transaction: the sub-dealer never outlives the test."""
    order = await _dispatched(client, rx, partner_id=rx.partner)
    s = sessions()
    try:
        sub = (await s.execute(text(
            "INSERT INTO channel_partner (partner_type, code, name, mobile, territory_id, price_tier, parent_id) "
            "VALUES ('sub_dealer', :c, 'Sub Irrigation', :m, CAST(:t AS uuid), 'sub_dealer', CAST(:p AS uuid)) RETURNING id"),
            {"c": "SUB" + uuid.uuid4().hex[:6].upper(), "m": "9194" + f"{uuid.uuid4().int % 10**8:08d}",
             "t": rx.district, "p": rx.partner})).scalar_one()
        await s.execute(text("ALTER TABLE sales_order DISABLE TRIGGER USER"))
        await s.execute(text("UPDATE sales_order SET partner_id = CAST(:p AS uuid) WHERE id = CAST(:o AS uuid)"),
                        {"p": str(sub), "o": order["id"]})
        await s.execute(text("ALTER TABLE sales_order ENABLE TRIGGER USER"))
        await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": rx.ids["dealer"]})
        await enter_role(s, "app_role")
        assert (await s.execute(text("SELECT order_visible(CAST(:o AS uuid))"), {"o": order["id"]})).scalar_one()
        with pytest.raises(DBAPIError) as err:
            await s.execute(text("SELECT rating_record('installation', CAST(:o AS uuid), NULL, NULL, 4, NULL)"),
                            {"o": order["id"]})
        assert "RTGNY" in str(getattr(err.value.orig, "sqlstate", "")) or "not your order" in str(err.value)
    finally:
        await s.rollback()
        await s.close()


async def test_a_voided_dispatch_leaves_nothing_to_rate(client: httpx.AsyncClient, rx: Shop) -> None:
    """Edge 3, code review F-4: only a live dispatch makes an installation or a
    product rateable."""
    order = await _dispatched(client, rx)
    hd = await endpoints._as(client, rx, "dispatch_manager")
    full = (await client.get(f"{V1}/orders/{order['id']}", headers=hd)).json()["data"]
    dispatch_id = full["dispatches"][0]["id"]
    r = await client.post(f"{V1}/dispatches/{dispatch_id}/void", headers={**hd, **_key()},
                          json={"remark": "Wrong truck"})
    assert r.status_code == 200, r.text
    fo = await endpoints._as(client, rx, "field_officer")
    r = await _rate(client, fo, target="installation", sales_order_id=order["id"])
    assert r.status_code == 422 and _code(r) == "not_rateable", r.text
    r = await _rate(client, fo, target="product", sales_order_id=order["id"], product_id=rx.product)
    assert r.status_code == 422 and _code(r) == "not_rateable", r.text
