# ruff: noqa: E501  (request bodies and assertions)

"""FS-044 over the API: consumer accounts, the switch, the guard, a farmer's own
record, and the users side."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_campaigns as camp
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key
from tests.api.test_customers import _cleanup, _lead, _mobile, _move

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _switch(client: httpx.AsyncClient, shop: Shop, value: str) -> None:
    ha = await endpoints._as(client, shop, "admin_sales")
    r = await client.patch(f"{V1}/settings", json={"values": {"consumer_portal": value}},
                           headers={**ha, **_key()})
    assert r.status_code == 200, r.text


async def _release(sessions: Sessions) -> None:
    """The setting row names the shop's admin, whom the shop's teardown deletes."""
    s = sessions()
    await s.execute(text("UPDATE app_setting SET updated_by = NULL WHERE key = 'consumer_portal'"))
    await s.commit()
    await s.close()


@pytest_asyncio.fixture
async def portal_on(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> AsyncIterator[None]:
    """The switch is company-wide; always put it back."""
    await _switch(client, shop, "on")
    try:
        yield
    finally:
        await _switch(client, shop, "off")
        await _release(sessions)


async def _sign_in(client: httpx.AsyncClient, sessions: Sessions, mobile10: str) -> dict[str, str]:
    m = "91" + mobile10
    await client.post(f"{V1}/auth/otp/request", json={"mobile": m})
    s = sessions()
    code = (await s.execute(text(
        "SELECT payload ->> 'code' FROM notification_outbox WHERE recipient IN (:m, :p) "
        "ORDER BY created_at DESC LIMIT 1"), {"m": m, "p": "+" + m})).scalar_one()
    await s.close()
    r = await client.post(f"{V1}/auth/otp/verify", json={"mobile": m, "code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _account(sessions: Sessions, mobile10: str) -> tuple[bool, bool] | None:
    s = sessions()
    row = (await s.execute(text(
        "SELECT is_active, deleted_at IS NOT NULL AS gone FROM app_user "
        "WHERE mobile = :m AND user_type = 'consumer' ORDER BY created_at DESC LIMIT 1"),
        {"m": "91" + mobile10})).one_or_none()
    await s.close()
    return (row.is_active, row.gone) if row else None


async def _forget(sessions: Sessions, mobiles: list[str]) -> None:
    s = sessions()
    nums = ["91" + m for m in mobiles] + ["+91" + m for m in mobiles]
    users = "(SELECT id FROM app_user WHERE mobile = ANY(:n) AND user_type = 'consumer')"
    for stmt in (f"DELETE FROM idempotency_record WHERE user_id IN {users}",
                 f"DELETE FROM session WHERE user_id IN {users}",
                 f"DELETE FROM activity_event WHERE actor_id IN {users} OR entity_id IN {users}",
                 "DELETE FROM notification_outbox WHERE recipient = ANY(:n)",
                 "DELETE FROM login_attempt WHERE identifier = ANY(:n)",
                 f"DELETE FROM otp_issue WHERE user_id IN {users}",
                 "DELETE FROM app_user WHERE mobile = ANY(:n) AND user_type = 'consumer'"):
        try:
            async with s.begin_nested():
                await s.execute(text(stmt), {"n": nums})
        except Exception:
            pass
    await s.commit()
    await s.close()


# ── accounts and the switch ──────────────────────────────────────────────────

async def test_a_customer_gets_an_inactive_account_the_switch_flips(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    m = _mobile()
    try:
        await _move(client, ho, (await _lead(client, ho, shop, m))["id"], "contacted", "qualified")
        assert await _account(sessions, m) == (False, False), "off by default: inactive"
        await _switch(client, shop, "on")
        assert await _account(sessions, m) == (True, False)
        await _switch(client, shop, "off")
        assert await _account(sessions, m) == (False, False)
    finally:
        await _switch(client, shop, "off")
        await _release(sessions)
        await _forget(sessions, [m])
        await _cleanup(sessions, [m])


async def test_a_number_already_signing_in_gets_no_account_and_a_new_user_takes_it(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """GAP-266 both ways: the dealer's number makes no consumer; a staff user created
    on a farmer's number releases the farmer's account (edge case 3)."""
    s = sessions()
    dealer_mobile = (await s.execute(text("SELECT mobile FROM app_user WHERE id = CAST(:u AS uuid)"),
                                     {"u": shop.ids["dealer"]})).scalar_one()
    await s.close()
    ho = await endpoints._as(client, shop, "field_officer")
    m = _mobile()
    try:
        await _move(client, ho, (await _lead(client, ho, shop, dealer_mobile[2:]))["id"], "contacted", "qualified")
        assert await _account(sessions, dealer_mobile[2:]) is None

        await _move(client, ho, (await _lead(client, ho, shop, m))["id"], "contacted", "qualified")
        assert await _account(sessions, m) == (False, False)
        ha = await endpoints._as(client, shop, "admin_sales")
        r = await client.get(f"{V1}/users", params={"q": m}, headers=ha)
        assert all(u["user_type"] != "consumer" for u in r.json()["data"]), "consumers left out by default"
        r = await client.post(f"{V1}/users", headers={**ha, **_key()}, json={
            "user_type": "partner_user", "full_name": "Farmer Turned Dealer", "mobile": m,
            "partner_id": shop.partner})
        assert r.status_code == 201, r.text
        assert await _account(sessions, m) == (False, True), "the consumer account is released"
        s = sessions()
        await s.execute(text("DELETE FROM app_user WHERE id = CAST(:u AS uuid)"), {"u": r.json()["data"]["id"]})
        await s.commit()
        await s.close()
    finally:
        await _forget(sessions, [m, dealer_mobile[2:]])
        await _cleanup(sessions, [m, dealer_mobile[2:]])


# ── the guard and the floor ──────────────────────────────────────────────────

async def test_a_consumer_reaches_only_auth_and_the_portal(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, portal_on: None) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    m = _mobile()
    try:
        await _move(client, ho, (await _lead(client, ho, shop, m))["id"], "contacted", "qualified")
        hc = await _sign_in(client, sessions, m)
        assert (await client.get(f"{V1}/auth/me", headers=hc)).status_code == 200
        assert (await client.get(f"{V1}/portal/me", headers=hc)).status_code == 200
        for path in ("/campaigns", "/settings", "/products", "/dashboard/overview", "/holidays",
                     "/assistant?q=lead", "/notifications", "/leads"):
            r = await client.get(f"{V1}{path}", headers=hc)
            assert r.status_code == 403 and r.json()["error"]["code"] == "consumer_not_allowed", (path, r.text)
        # staff and dealers are not consumers
        r = await client.get(f"{V1}/portal/me", headers=ho)
        assert r.status_code == 403 and r.json()["error"]["code"] == "not_a_consumer", r.text
    finally:
        await _forget(sessions, [m])
        await _cleanup(sessions, [m])


# ── the farmer's own record ──────────────────────────────────────────────────

async def test_a_farmer_sees_their_own_record_and_nothing_else(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, portal_on: None) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    lead, order = await camp._won_lead(client, shop, ho, None)  # type: ignore[arg-type]
    m = lead["mobile"][3:]
    other = _mobile()
    try:
        await _move(client, ho, (await _lead(client, ho, shop, other, name="Someone Else"))["id"], "contacted", "qualified")
        second = await _move(client, ho, (await _lead(client, ho, shop, m))["id"], "contacted", "qualified")
        hc = await _sign_in(client, sessions, m)
        me = (await client.get(f"{V1}/portal/me", headers=hc)).json()["data"]
        assert me["mobile"] == lead["mobile"]
        enq = (await client.get(f"{V1}/portal/enquiries", headers=hc)).json()["data"]
        assert {e["inquiry_no"]: e["status"] for e in enq} == {
            lead["inquiry_no"]: "won", second["inquiry_no"]: "in_progress"}, enq
        quotes = (await client.get(f"{V1}/portal/quotations", headers=hc)).json()["data"]
        assert len(quotes) == 1 and quotes[0]["status"] == "accepted" and quotes[0]["link"], quotes
        orders = (await client.get(f"{V1}/portal/orders", headers=hc)).json()["data"]
        assert [(o["order_no"], o["status"], o["total"]) for o in orders] == [
            (order["order_no"], "in_progress", order["totals"]["total"])], orders
        assert (await client.get(f"{V1}/portal/complaints", headers=hc)).json()["data"] == []
        body = str(enq) + str(quotes) + str(orders) + str(me)
        assert "Someone Else" not in body and "Field Officer" not in body, "no other farmer, no staff name"

        # consent: on, again (same date), off
        on = (await client.patch(f"{V1}/portal/me", json={"consent_given": True}, headers={**hc, **_key()})).json()["data"]
        again = (await client.patch(f"{V1}/portal/me", json={"consent_given": True}, headers={**hc, **_key()})).json()["data"]
        assert on["consent_channel"] == "portal" and again["consent_given_at"] == on["consent_given_at"]
        off = (await client.patch(f"{V1}/portal/me", json={"consent_given": False}, headers={**hc, **_key()})).json()["data"]
        assert off["consent_given_at"] is None

        # plan review B-2: a lead moved to another number leaves this farmer's portal,
        # though it keeps its customer
        r = await client.patch(f"{V1}/leads/{second['id']}", json={"mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}"},
                               headers={**ho, **_key()})
        assert r.status_code == 200 and r.json()["data"]["customer_id"] == second["customer_id"], r.text
        enq = (await client.get(f"{V1}/portal/enquiries", headers=hc)).json()["data"]
        assert [e["inquiry_no"] for e in enq] == [lead["inquiry_no"]], enq

        # switching off ends the session
        await _switch(client, shop, "off")
        assert (await client.get(f"{V1}/portal/me", headers=hc)).status_code == 401
    finally:
        await _forget(sessions, [m, other])
        await _cleanup(sessions, [m, other])


async def test_a_dealers_document_shows_no_amount(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, portal_on: None) -> None:
    """GAP-271: a quotation with a partner carries the dealer's buying price."""
    ho = await endpoints._as(client, shop, "field_officer")
    q = await endpoints._accepted_quotation(client, shop, ho, partner_id=shop.partner)
    lead = (await client.get(f"{V1}/leads/{q['lead']['id']}", headers=ho)).json()["data"]
    m = lead["mobile"][3:]
    try:
        assert lead["customer_id"], lead
        hc = await _sign_in(client, sessions, m)
        quotes = (await client.get(f"{V1}/portal/quotations", headers=hc)).json()["data"]
        assert [(x["status"], x["total"], x["link"]) for x in quotes] == [("accepted", None, None)], quotes
    finally:
        await _forget(sessions, [m])
        await _cleanup(sessions, [m])
