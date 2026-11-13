"""FS-055: the farmer's share on subsidised orders, the supply date from dispatch,
subsidy notifications, reopen, and the 069 live-text swaps."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api import test_subsidised_orders as subsidised
from tests.api import test_subsidy_applications as apps_t
from tests.api.conftest import V1, _key
from tests.api.test_payments import _forget_payments, _pay  # noqa: F401  (autouse fixture)
from tests.api.test_subsidy_applications import APPS, Office, _app, _as, _record

pytestmark = pytest.mark.db

shop = endpoints.shop
office = apps_t.office
fake_engine = apps_t.fake_engine
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]

OWED_IN = ("order_payment_position(uuid, date)", "partner_credit_exposure(uuid)",
           "order_payment_schedule_set(uuid, jsonb)", "payment_apply(payment, jsonb, boolean)",
           "dealer_rating(uuid)", "order_paid_at(uuid)")


async def _approved_subsidised(client: httpx.AsyncClient, shop: Shop, lead_ids: list[str] | None = None,
                               partner: bool = False, **block: object) -> dict[str, Any]:
    """`partner`: the order names the shop's dealer, as payment tests do."""
    fo = await endpoints._as(client, shop, "field_officer")
    if lead_ids is None:
        lead_ids = [(await subsidised._lead(client, shop, fo))["id"]]
    body = subsidised._body(shop, lead_ids, **block)
    if partner:
        body["partner_id"] = shop.partner
    order = await endpoints._create(client, fo, body)
    order = await endpoints._submit(client, fo, order["id"])
    approved: dict[str, Any] = await endpoints._approve_all(client, shop, order)
    return approved


async def _dispatch(client: httpx.AsyncClient, shop: Shop, order: dict[str, Any],
                    at: dt.datetime | None = None) -> dict[str, Any]:
    hd = await endpoints._as(client, shop, "dispatch_manager")
    line = order["lines"][0]
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()}, json={
        "dispatched_at": (at or dt.datetime.now(dt.UTC)).isoformat(),
        "lines": [{"order_line_id": line["id"], "qty": "1"}]})
    assert r.status_code == 201, r.text
    data: dict[str, Any] = r.json()["data"]
    return data


# ── A: payable ───────────────────────────────────────────────────────────────

async def test_a_subsidised_order_is_paid_by_the_farmers_share(client: httpx.AsyncClient, shop: Shop) -> None:
    order = await _approved_subsidised(client, shop)
    total = Decimal(order["totals"]["total"])
    share = total - Decimal("10.00")
    accounts = await endpoints._as(client, shop, "account_manager")
    got = (await client.get(f"{V1}/orders/{order['id']}", headers=accounts)).json()["data"]
    assert got["payable"] == f"{share:.2f}", "rule 4: the order detail's payable is the farmer's share"
    assert got["payments"]["payable"] == f"{share:.2f}", "rule 3: the payment position agrees"
    r = await _pay(client, accounts, {"partner_id": None, "amount": f"{share:.2f}",
                                      "allocations": [{"sales_order_id": order["id"], "amount": f"{share:.2f}"}]})
    assert r.status_code == 201, r.text
    block = (await client.get(f"{V1}/orders/{order['id']}", headers=accounts)).json()["data"]["payments"]
    assert block["status"] == "paid" and block["balance"] == "0.00", block


async def test_the_farmer_total_follows_the_block(client: httpx.AsyncClient, shop: Shop,
                                                  sessions: Sessions) -> None:
    """Rule 1: typed farmer payable; material less subsidy; total less subsidy; an ordinary order."""
    typed = await _approved_subsidised(client, shop, material_amount="900.00", subsidy_amount="600.00",
                                       farmer_payable="200.00")
    derived = await _approved_subsidised(client, shop, material_amount="900.00", subsidy_amount="600.00")
    above = await _approved_subsidised(client, shop, material_amount="900.00", subsidy_amount="1.00",
                                       farmer_payable="899.00")
    blank = await _approved_subsidised(client, shop)
    fo = await endpoints._as(client, shop, "field_officer")
    plain = await endpoints._create(client, fo, endpoints._direct(shop))
    s = sessions()
    try:
        async def owed(o: dict[str, Any]) -> Decimal:
            return Decimal((await s.execute(text("SELECT order_owed(CAST(:o AS uuid))"), {"o": o["id"]})).scalar_one())
        assert await owed(typed) == Decimal("200.00")
        assert await owed(derived) == Decimal("300.00")
        assert await owed(above) == min(Decimal("899.00"), Decimal(above["totals"]["total"])), \
            "never above the order total (EC-6)"
        assert await owed(blank) == Decimal(blank["totals"]["total"]) - 10
        assert await owed(plain) == Decimal(plain["totals"]["total"])
    finally:
        await s.close()


async def test_the_069_swaps_hold_in_the_live_functions(sessions: Sessions) -> None:
    """064's lesson: each definer now reads order_owed and no inline owed expression."""
    s = sessions()
    try:
        for sig in OWED_IN:
            body = str((await s.execute(text(f"SELECT pg_get_functiondef('{sig}'::regprocedure)"))).scalar_one())
            assert "order_owed(" in body and "scheme_benefit b" not in body, sig
        outcome = str((await s.execute(text(
            "SELECT pg_get_functiondef('order_notify_outcome(uuid, text)'::regprocedure)"))).scalar_one())
        assert "inr_text(order_farmer_total(o.id))" in outcome, "rule 6"
        portal = str((await s.execute(text("SELECT pg_get_functiondef('portal_orders()'::regprocedure)"))).scalar_one())
        assert "THEN order_farmer_total(o.id) END" in portal, "rule 7"
        step = str((await s.execute(text(
            "SELECT pg_get_functiondef('order_notify_step(uuid)'::regprocedure)"))).scalar_one())
        assert "inr_text(o.total)" in step, "rule 8: the approver still sees the full total"
        public = (await s.execute(text(
            "SELECT has_function_privilege('app_role', 'order_owed(uuid)', 'EXECUTE')"))).scalar_one()
        assert public is False, "only definers call order_owed"
    finally:
        await s.close()


# ── C, D, E: applications ────────────────────────────────────────────────────

async def _kinds(sessions: Sessions, user_id: str, app_id: str) -> list[str]:
    s = sessions()
    try:
        return [r[0] for r in (await s.execute(text(
            "SELECT kind FROM notification WHERE recipient_id = CAST(:u AS uuid) "
            "AND resource_id = CAST(:a AS uuid) ORDER BY created_at, kind"),
            {"u": user_id, "a": app_id})).all()]
    finally:
        await s.close()


async def _supply(sessions: Sessions, app_id: str) -> str | None:
    s = sessions()
    try:
        got = (await s.execute(text("SELECT subsidy_value_date(CAST(:a AS uuid), 'supply')"),
                               {"a": app_id})).scalar_one()
        return got.isoformat() if got else None
    finally:
        await s.close()


async def test_the_supply_date_comes_from_the_dispatch(client: httpx.AsyncClient, office: Office,
                                                       fake_engine: Any, sessions: Sessions) -> None:
    shop = office.shop
    fo = await _as(client, office, "field_officer")
    app = await _app(client, office, fo)
    assert app["dispatched_on"] is None
    other = await _app(client, office, fo)
    # the application's lead is the second lead of the order: rule 9 reads the lead list too
    order = await _approved_subsidised(client, shop, [other["lead"]["id"], app["lead"]["id"]])
    yesterday = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    await _dispatch(client, shop, order, at=yesterday)
    await _dispatch(client, shop, order)
    first = (yesterday + dt.timedelta(hours=5, minutes=30)).date().isoformat()
    got = (await client.get(f"{APPS}/{app['id']}", headers=fo)).json()["data"]
    assert got["dispatched_on"] == first, "the earliest live dispatch, as an IST date"

    r = await _record(client, fo, app["id"], "farmer_share", values={"farmer_share_amt": "100.00"})
    assert r.status_code == 201, r.text
    assert await _supply(sessions, app["id"]) == first, "rule 10: filled when not sent"
    r = await _record(client, fo, app["id"], "farmer_share", remark="typed", values={"supply": None})
    assert r.status_code == 201, r.text
    assert await _supply(sessions, app["id"]) is None, "a sent null is kept"


async def test_a_voided_dispatch_gives_no_dispatch_date(client: httpx.AsyncClient, office: Office,
                                                        fake_engine: Any, sessions: Sessions) -> None:
    """Rule 9. A dispatched order cannot be cancelled (013), so a voided dispatch
    is the one way a supply is taken back."""
    fo = await _as(client, office, "field_officer")
    app = await _app(client, office, fo)
    order = await _approved_subsidised(client, office.shop, [app["lead"]["id"]])
    await _dispatch(client, office.shop, order)
    s = sessions()
    try:
        await s.execute(text("UPDATE dispatch SET voided_at = now(), voided_by = dispatched_by, void_remark = 'test' "
                             "WHERE sales_order_id = CAST(:o AS uuid)"), {"o": order["id"]})
        await s.commit()
    finally:
        await s.close()
    got = (await client.get(f"{APPS}/{app['id']}", headers=fo)).json()["data"]
    assert got["dispatched_on"] is None, "a voided dispatch is not a supply"


async def test_the_owner_hears_of_returns_queries_closure_and_reopen(
        client: httpx.AsyncClient, office: Office, fake_engine: Any, sessions: Sessions) -> None:
    shop = office.shop
    fo = await _as(client, office, "field_officer")
    sc = await _as(client, office, "state_coordinator")
    app = await _app(client, office, fo)
    me = shop.ids["field_officer"]
    today = today_ist().isoformat()

    r = await _record(client, sc, app["id"], "submitted_wo_pending", values={"submission": today})
    assert r.status_code == 201, r.text
    assert await _kinds(sessions, me, app["id"]) == [], "an ordinary entry tells nobody"
    r = await _record(client, sc, app["id"], "application_in_process", remark="back",
                      values={"return_to_field": today, "app_query": today})
    assert r.status_code == 201, r.text
    assert await _kinds(sessions, me, app["id"]) == ["subsidy_returned"], "rule 14: one, returned first"
    r = await _record(client, sc, app["id"], "ggrc_query", values={"query_1": today})
    assert await _kinds(sessions, me, app["id"]) == ["subsidy_returned", "subsidy_query"]
    r = await _record(client, fo, app["id"], "ggrc_query", remark="mine", values={"query_2": today})
    assert len(await _kinds(sessions, me, app["id"])) == 2, "the actor is never told"

    # close it
    r = await _record(client, sc, app["id"], "fp_cleared_pay_pending", values={"pfms_amt": "500.00"})
    r = await _record(client, sc, app["id"], "payment_received", values={"pfms_received": today})
    assert r.json()["data"]["status"] == "full_fp_received", r.text
    assert (await _kinds(sessions, me, app["id"]))[-1] == "subsidy_closed"

    # E: reopen
    url = f"{APPS}/{app['id']}/reopen"
    r = await client.post(url, headers={**fo, **_key()}, json={"reason": "wrong date"})
    assert r.status_code == 403, "subsidy.approve only"
    admin = await _as(client, office, "admin_sales")
    r = await client.post(url, headers={**admin, **_key()}, json={"reason": "  "})
    assert r.status_code == 422, r.text
    r = await client.post(url, headers={**admin, **_key()}, json={"reason": "wrong date"})
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert got["status"] == "open" and got["full_fp_received_on"] is None
    assert (await _kinds(sessions, me, app["id"]))[-1] == "subsidy_reopened"
    r = await client.post(url, headers={**admin, **_key()}, json={"reason": "again"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "application_not_closed", r.text

    # EC-3: an entry that touches no paid amount or its date leaves it open
    r = await _record(client, sc, app["id"], "application_in_process", remark="survey fix",
                      values={"doc_check": today})
    assert r.status_code == 201 and r.json()["data"]["status"] == "open", r.text
    # the correcting entry is taken; with the date cleared it stays open
    r = await _record(client, sc, app["id"], "payment_received", remark="fix", values={"pfms_received": None})
    assert r.status_code == 201 and r.json()["data"]["status"] == "open", r.text
    r = await _record(client, sc, app["id"], "payment_received", remark="paid", values={"pfms_received": today})
    assert r.json()["data"]["status"] == "full_fp_received", "and closes again on its date"


async def test_a_cancelled_application_is_not_reopened(client: httpx.AsyncClient, office: Office,
                                                       fake_engine: Any) -> None:
    fo = await _as(client, office, "field_officer")
    app = await _app(client, office, fo)
    r = await client.post(f"{APPS}/{app['id']}/cancel", headers={**fo, **_key()}, json={"reason": "duplicate"})
    assert r.status_code == 200, r.text
    admin = await _as(client, office, "admin_sales")
    r = await client.post(f"{APPS}/{app['id']}/reopen", headers={**admin, **_key()}, json={"reason": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "application_not_closed", r.text


async def test_a_settled_commission_keeps_the_file_closed(client: httpx.AsyncClient, office: Office,
                                                          fake_engine: Any, sessions: Sessions) -> None:
    """EC-2: a commission approved or paid on these figures blocks a reopen."""
    fo = await _as(client, office, "field_officer")
    app = await _app(client, office, fo)
    today = today_ist().isoformat()
    await _record(client, fo, app["id"], "fp_cleared_pay_pending", values={"pfms_amt": "500.00"})
    r = await _record(client, fo, app["id"], "payment_received", values={"pfms_received": today})
    assert r.json()["data"]["status"] == "full_fp_received", r.text
    s = sessions()
    me = office.shop.ids["field_officer"]
    await s.execute(text(
        "INSERT INTO dealer_commission (application_id, partner_id, rate_id, status, cost_excl_gst, gi_fitting, "
        "pvc_hdpe_fitting, installation, commission_base, commission_pct, commission_amount, tod_base, tod_pct, "
        "tod_amount, total, first_recorded_by, recorded_by) "
        "SELECT CAST(:a AS uuid), CAST(:p AS uuid), r.id, 'approved', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "
        "CAST(:u AS uuid), CAST(:u AS uuid) FROM commission_rate r LIMIT 1"),
        {"a": app["id"], "p": office.shop.partner, "u": me})
    await s.commit()
    try:
        admin = await _as(client, office, "admin_sales")
        r = await client.post(f"{APPS}/{app['id']}/reopen", headers={**admin, **_key()}, json={"reason": "x"})
        assert r.status_code == 409 and r.json()["error"]["code"] == "commission_settled", r.text
    finally:
        await s.execute(text("DELETE FROM dealer_commission WHERE application_id = CAST(:a AS uuid)"),
                        {"a": app["id"]})
        await s.commit()
        await s.close()


async def test_the_detail_the_position_and_the_ledger_agree(client: httpx.AsyncClient, shop: Shop,
                                                            sessions: Sessions) -> None:
    """Plan review S-3 and B-1: one farmer total in Python, in SQL and in the dealer ledger."""
    accounts = await endpoints._as(client, shop, "account_manager")
    variants = [{}, {"material_amount": "900.00", "subsidy_amount": "600.00"},
                {"material_amount": "900.00", "subsidy_amount": "600.00", "farmer_payable": "200.00"}]
    for block in variants:
        order = await _approved_subsidised(client, shop, **block)
        got = (await client.get(f"{V1}/orders/{order['id']}", headers=accounts)).json()["data"]
        assert got["payable"] == got["payments"]["payable"], block
    dealer = await _approved_subsidised(client, shop, partner=True, material_amount="900.00",
                                        subsidy_amount="600.00", farmer_payable="200.00")
    ledger = (await client.get(f"{V1}/partners/{shop.partner}/ledger", headers=accounts)).json()["data"]
    row = next(x for x in ledger["rows"] if x["kind"] == "order" and x["ref"] == dealer["order_no"])
    assert row["debit"] == "200.00", "the ledger debits the farmer's share"
