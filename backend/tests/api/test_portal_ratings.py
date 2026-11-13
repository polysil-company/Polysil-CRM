# ruff: noqa: E501  (request bodies and assertions)

"""FS-060 over the API: a farmer rates installation and service from the portal,
only on his own documents, once, and staff see where the rating came from."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from tests.api import test_campaigns as camp
from tests.api import test_complaints as complaints_t
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key
from tests.api.test_customers import _cleanup
from tests.api.test_portal import _forget, _sign_in, portal_on  # noqa: F401  (fixture)

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _dispatch(client: httpx.AsyncClient, shop: Shop, order: dict[str, Any]) -> None:
    hd = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()},
                          json={"dc_no": "DC-P", "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
                                "lines": [{"order_line_id": order["lines"][0]["id"], "qty": "1"}]})
    assert r.status_code == 201, r.text


async def _rate(client: httpx.AsyncClient, h: dict[str, str], **body: Any) -> httpx.Response:
    return await client.post(f"{V1}/portal/ratings", headers={**h, **_key()}, json={"score": 4, **body})


async def _owner(sessions: Sessions, sql: str, params: dict[str, Any]) -> Any:
    s = sessions()
    out = (await s.execute(text(sql), params)).all()
    await s.commit()
    await s.close()
    return out


async def _tidy(sessions: Sessions, orders: list[str], complaints: list[str], mobiles: list[str]) -> None:
    s = sessions()
    for stmt in ("DELETE FROM activity_event WHERE kind = 'rating.recorded' AND entity_id = ANY(CAST(:d AS uuid[]))",
                 "DELETE FROM rating WHERE sales_order_id = ANY(CAST(:o AS uuid[])) OR complaint_id = ANY(CAST(:c AS uuid[]))",
                 # the shop's teardown puts complaints back to draft, which a closed_at refuses
                 "UPDATE complaint SET closed_at = NULL, status = 'draft' WHERE id = ANY(CAST(:c AS uuid[]))"):
        await s.execute(text(stmt), {"d": orders + complaints, "o": orders, "c": complaints})
    await s.commit()
    await s.close()
    await _forget(sessions, mobiles)
    await _cleanup(sessions, mobiles)


async def test_a_farmer_rates_his_installation_once_and_staff_see_it_came_from_the_portal(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, portal_on: None) -> None:  # noqa: F811
    ho = await endpoints._as(client, shop, "field_officer")
    lead, order = await camp._won_lead(client, shop, ho, None)  # type: ignore[arg-type]
    m = lead["mobile"][3:]
    try:
        hc = await _sign_in(client, sessions, m)
        # nothing shipped yet
        r = await _rate(client, hc, target="installation", order_no=order["order_no"])
        assert r.status_code == 422 and r.json()["error"]["code"] == "not_rateable", r.text
        await _dispatch(client, shop, order)

        # spaces and case do not matter (EC-12)
        r = await _rate(client, hc, target="installation", order_no=f"  {order['order_no'].lower()} ",
                        score=5, comment="Good fitting work.")
        assert r.status_code == 201, r.text
        got = r.json()["data"]
        assert (got["order_no"], got["score"], got["comment"], got["entered_via"]) == (
            order["order_no"], 5, "Good fitting work.", "portal"), got
        assert got["created_at"].endswith("+05:30"), got

        # an officer's product rating on the same order is not his (review F-2, EC-2)
        r = await client.post(f"{V1}/ratings", headers={**ho, **_key()}, json={
            "target": "product", "sales_order_id": order["id"], "product_id": shop.product, "score": 1})
        assert r.status_code == 201, r.text
        assert (await client.get(f"{V1}/portal/ratings", headers=hc)).json()["data"] == [got]
        r = await _rate(client, hc, target="installation", order_no=order["order_no"])
        assert r.status_code == 409 and r.json()["error"]["code"] == "rating_exists", r.text

        # staff: a customer rating from the portal, with no person to open (EC-4)
        rows = (await client.get(f"{V1}/ratings", params={"sales_order_id": order["id"], "target": "installation"}, headers=ho)).json()["data"]
        assert [(x["rated_by"], x["entered_via"], x["entered_by"], x["comment"]) for x in rows] == [
            ("customer", "portal", None, "Good fitting work.")], rows

        # the timeline event names the farmer and never carries the comment (R-1)
        (payload,) = [r.payload for r in await _owner(
            sessions, "SELECT payload FROM activity_event WHERE kind = 'rating.recorded' AND entity_id = CAST(:o AS uuid) AND payload ->> 'target' = 'installation'",
            {"o": order["id"]})]
        assert payload["via"] == "portal" and payload["actor_name"] and "comment" not in payload, payload
    finally:
        await _tidy(sessions, [order["id"]], [], [m])


async def test_a_farmer_cannot_reach_another_farmers_order_or_a_product(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, portal_on: None) -> None:  # noqa: F811
    """EC-1 and EC-12: another farmer's real number is 404; the staff route is closed
    to a consumer by the portal guard (FS-044); calling rating_record() directly with
    ids outside his portal is RTGNF, and a product is RTGTG."""
    ho = await endpoints._as(client, shop, "field_officer")
    mine_lead, mine = await camp._won_lead(client, shop, ho, None)  # type: ignore[arg-type]
    other_lead, other = await camp._won_lead(client, shop, ho, None)  # type: ignore[arg-type]
    m, o = mine_lead["mobile"][3:], other_lead["mobile"][3:]
    try:
        await _dispatch(client, shop, mine)
        await _dispatch(client, shop, other)
        hc = await _sign_in(client, sessions, m)
        r = await _rate(client, hc, target="installation", order_no=other["order_no"])
        assert r.status_code == 404, r.text
        r = await _rate(client, hc, target="installation", order_no=mine["order_no"], complaint_no="X")
        assert r.status_code == 422, r.text
        r = await client.post(f"{V1}/ratings", headers={**hc, **_key()},
                              json={"target": "installation", "sales_order_id": mine["id"], "score": 4})
        assert r.status_code == 403 and r.json()["error"]["code"] == "consumer_not_allowed", r.text

        (me,) = [r.id for r in await _owner(
            sessions, "SELECT id FROM app_user WHERE mobile = :m AND user_type = 'consumer'", {"m": "91" + m})]
        for args, code in (((other["id"], None), "RTGNF"), ((mine["id"], shop.product), "RTGTG")):
            s = sessions()
            try:
                await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(me)})
                await enter_role(s, "app_role")
                target = "product" if args[1] else "installation"
                with pytest.raises(DBAPIError) as exc:
                    await s.execute(text(
                        "SELECT rating_record(:t, CAST(:o AS uuid), NULL, CAST(:p AS uuid), 4, NULL)"),
                        {"t": target, "o": args[0], "p": args[1]})
                assert getattr(exc.value.orig, "sqlstate", None) == code
            finally:
                await s.rollback()
                await s.close()
        assert await _owner(sessions, "SELECT id FROM rating WHERE sales_order_id IN (CAST(:a AS uuid), CAST(:b AS uuid))",
                            {"a": mine["id"], "b": other["id"]}) == []
    finally:
        await _tidy(sessions, [mine["id"], other["id"]], [], [m, o])


async def test_a_rating_staff_recorded_for_him_shows_without_its_note_and_blocks_his_own(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, portal_on: None) -> None:  # noqa: F811
    """Rule 2 and EC-2: one customer rating per order, whoever enters it first; an
    officer's comment is not the farmer's words."""
    ho = await endpoints._as(client, shop, "field_officer")
    lead, order = await camp._won_lead(client, shop, ho, None)  # type: ignore[arg-type]
    m = lead["mobile"][3:]
    try:
        await _dispatch(client, shop, order)
        r = await client.post(f"{V1}/ratings", headers={**ho, **_key()}, json={
            "target": "installation", "sales_order_id": order["id"], "score": 2,
            "comment": "Farmer unhappy with the lateral spacing."})
        assert r.status_code == 201 and r.json()["data"]["entered_via"] == "staff", r.text
        hc = await _sign_in(client, sessions, m)
        rows = (await client.get(f"{V1}/portal/ratings", headers=hc)).json()["data"]
        assert [(x["order_no"], x["score"], x["comment"], x["entered_via"]) for x in rows] == [
            (order["order_no"], 2, None, "staff")], rows
        r = await _rate(client, hc, target="installation", order_no=order["order_no"])
        assert r.status_code == 409 and r.json()["error"]["code"] == "rating_exists", r.text
    finally:
        await _tidy(sessions, [order["id"]], [], [m])


async def test_a_farmer_rates_a_service_once_his_complaint_is_closed(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, portal_on: None) -> None:  # noqa: F811
    ho = await endpoints._as(client, shop, "field_officer")
    lead, order = await camp._won_lead(client, shop, ho, None)  # type: ignore[arg-type]
    m = lead["mobile"][3:]
    c = await complaints_t._create(client, shop, ho, lead_id=lead["id"])
    try:
        r = await complaints_t._post(client, ho, f"/{c['id']}/submit")
        assert r.status_code == 200, r.text
        complaint_no = r.json()["data"]["complaint_no"]
        hc = await _sign_in(client, sessions, m)
        r = await _rate(client, hc, target="service", complaint_no=complaint_no)
        assert r.status_code == 422 and r.json()["error"]["code"] == "not_rateable", r.text
        # walked to closed elsewhere (FS-015b); here only its status matters
        await _owner(sessions, "UPDATE complaint SET status = 'closed', closed_at = now() WHERE id = CAST(:c AS uuid) RETURNING id", {"c": c["id"]})
        r = await _rate(client, hc, target="service", complaint_no=complaint_no, score=3)
        assert r.status_code == 201, r.text
        assert (r.json()["data"]["complaint_no"], r.json()["data"]["order_no"]) == (complaint_no, None)
    finally:
        await _tidy(sessions, [order["id"]], [c["id"]], [m])
