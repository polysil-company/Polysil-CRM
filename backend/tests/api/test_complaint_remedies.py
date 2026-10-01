"""Complaint remedies (FS-015b), end to end over ASGI: a refund through the approval
engine, a free replacement order through dispatch, or none; the complaint closes
on the remedy, and a refused or withdrawn remedy returns it to QC.

The order tests' shop, plus a price list in force today: a replacement prices at
today's list (FS-015b §5), and the shop's list ends in 2021.
"""

# ruff: noqa: E501  (embedded SQL, kept on one line so each statement reads whole)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.schemas import complaints as sch
from api.services import complaints as service
from tests.api import test_complaints as complaints_t
from tests.api import test_order_concurrency as conc
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


@pytest_asyncio.fixture
async def remedies(shop: Shop, sessions: Sessions) -> AsyncIterator[Shop]:
    """The shop with a farmer list from 2021 with no end, and its cleanup."""
    s = sessions()
    price_list = str((await s.execute(text(
        "INSERT INTO price_list (name, state_territory_id, channel_tier, status, published_at, "
        "effective_from) VALUES (:n, CAST(:s AS uuid), 'farmer', 'published', now(), DATE '2021-01-01') RETURNING id"),
        {"n": f"remedy list {uuid.uuid4().hex[:8]}", "s": shop.state})).scalar_one())
    await s.execute(text("INSERT INTO price_list_item (price_list_id, product_id, rate) VALUES (CAST(:l AS uuid), CAST(:p AS uuid), 120)"),
                    {"l": price_list, "p": shop.product})
    await s.commit()
    await s.close()
    try:
        yield shop
    finally:
        c = sessions()
        complaints = "(SELECT id FROM complaint WHERE territory_id = CAST(:d AS uuid))"
        orders = "(SELECT id FROM sales_order WHERE territory_id = CAST(:d AS uuid) AND order_type = 'replacement')"
        for stmt in (
            f"DELETE FROM complaint_remedy WHERE complaint_id IN {complaints}",
            # the shop's teardown resets complaints to draft; 027's CHECK pairs closed_at with closed
            "UPDATE complaint SET status = 'qc_approved', closed_at = NULL WHERE territory_id = CAST(:d AS uuid) AND closed_at IS NOT NULL",
            f"DELETE FROM approval_step WHERE request_id IN (SELECT id FROM approval_request WHERE doc_type = 'complaint' AND entity_id IN {complaints})",
            f"DELETE FROM approval_request WHERE doc_type = 'complaint' AND entity_id IN {complaints}",
            f"DELETE FROM notification WHERE resource_id IN {complaints}",
            # the replacement orders' lines point at this list: they go first
            f"DELETE FROM approval_step WHERE request_id IN (SELECT id FROM approval_request WHERE doc_type = 'sales_order' AND entity_id IN {orders})",
            f"DELETE FROM approval_request WHERE doc_type = 'sales_order' AND entity_id IN {orders}",
            f"DELETE FROM dispatch WHERE sales_order_id IN {orders}",
            f"DELETE FROM activity_event WHERE entity_id IN {orders}",
            f"DELETE FROM notification WHERE resource_id IN {orders}",
            f"DELETE FROM sales_order WHERE id IN {orders}",
            "DELETE FROM price_list_item WHERE price_list_id = CAST(:pl AS uuid)",
            "DELETE FROM price_list WHERE id = CAST(:pl AS uuid)",
        ):
            await c.execute(text(stmt), {"d": shop.district, "pl": price_list})
        await c.commit()
        await c.close()


# ── helpers ──────────────────────────────────────────────────────────────────

async def _as(client: httpx.AsyncClient, shop: Shop, role: str) -> dict[str, str]:
    return await complaints_t._as(client, shop, role)


async def _qc_approved(client: httpx.AsyncClient, shop: Shop, **over: Any) -> dict[str, Any]:
    """A complaint walked to `qc_approved`: raised by the officer, checked by the
    District Manager, passed by QC."""
    officer = await _as(client, shop, "field_officer")
    dm = await _as(client, shop, "district_manager")
    qc = await _as(client, shop, "qc_manager")
    c = await complaints_t._create(client, shop, officer, **over)
    assert (await complaints_t._post(client, officer, f"/{c['id']}/submit")).status_code == 200
    r = await complaints_t._post(client, dm, f"/{c['id']}/check", {"decision": "approve", "remark": "Genuine"})
    assert r.status_code == 200, r.text
    r = await complaints_t._post(client, qc, f"/{c['id']}/qc", {"verdict": "approved", "remark": "Manufacturing defect"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "qc_approved", r.text
    return dict(r.json()["data"])


async def _remedy(client: httpx.AsyncClient, h: dict[str, str], cid: str, **body: Any) -> httpx.Response:
    return await complaints_t._post(client, h, f"/{cid}/remedy", body)


def _refund(amount: str = "12500.00", **over: Any) -> dict[str, Any]:
    return {"kind": "refund", "amount": amount, "payee_name": "Kiritbhai Shah",
            "remark": "Refund of the failed laterals", **over}


async def _decide(client: httpx.AsyncClient, h: dict[str, str], step_id: str, decision: str = "approve",
                  remark: str | None = "Seen") -> httpx.Response:
    return await client.post(f"{V1}/approvals/steps/{step_id}/decision", headers={**h, **_key()},
                             json={"decision": decision, "remark": remark})


async def _get(client: httpx.AsyncClient, h: dict[str, str], cid: str) -> dict[str, Any]:
    r = await client.get(f"{V1}/complaints/{cid}", headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json()["data"])


def _code(r: httpx.Response) -> str:
    return str(r.json()["error"]["code"])


# ── refund (rules 4, 5, 7) ───────────────────────────────────────────────────

async def test_a_refund_goes_through_its_managers_and_accounts_and_closes_the_complaint(
        client: httpx.AsyncClient, remedies: Shop) -> None:
    shop = remedies
    qc = await _as(client, shop, "qc_manager")
    dm = await _as(client, shop, "district_manager")
    am = await _as(client, shop, "account_manager")
    c = await _qc_approved(client, shop)
    assert c["can"]["remedy"] and c["remedy"] is None
    r = await _remedy(client, qc, c["id"], **_refund())
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["status"] == "remedy_pending" and c["can"]["withdraw"] and not c["can"]["remedy"]
    refund = c["remedy"]["refund"]
    assert c["remedy"]["kind"] == "refund" and c["remedy"]["status"] == "pending"
    assert refund["amount"] == "12500.00" and refund["payee_name"] == "Kiritbhai Shah"
    steps = refund["approval"]["steps"]
    assert [s["role"] for s in steps] == ["district_manager", "account_manager"], "under 25,000: District, then Accounts"

    inbox = (await client.get(f"{V1}/approvals/pending", headers=dm)).json()["data"]
    row = next(x for x in inbox if x["document"]["id"] == c["id"])
    assert row["doc_type"] == "complaint" and row["document"]["total"] == "12500.00"
    assert row["document"]["number"] == c["complaint_no"]

    r = await _decide(client, dm, steps[0]["id"])
    assert r.status_code == 200, r.text
    assert r.json()["data"]["doc_type"] == "complaint" and r.json()["data"]["status"] == "remedy_pending"
    r = await _decide(client, am, steps[1]["id"], remark=None)
    assert r.status_code == 422, "the payment reference is required"
    r = await _decide(client, am, steps[1]["id"], remark="UTR 4471 0092")
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["status"] == "closed" and c["closed_at"] is not None
    assert c["remedy"]["status"] == "completed" and c["remedy"]["refund"]["payment_reference"] == "UTR 4471 0092"
    assert c["sla"]["resolved_at"] is not None, "resolution still ends at the QC verdict (D8)"


async def test_the_managers_stack_by_amount(client: httpx.AsyncClient, remedies: Shop) -> None:
    shop = remedies
    qc = await _as(client, shop, "qc_manager")
    expected = {"25000.00": ["district_manager", "account_manager"],
                "50000.00": ["district_manager", "state_manager", "account_manager"],
                "250000.00": ["district_manager", "state_manager", "regional_manager", "account_manager"]}
    for amount, roles in expected.items():
        c = await _qc_approved(client, shop)
        r = await _remedy(client, qc, c["id"], **_refund(amount))
        assert r.status_code == 200, r.text
        assert [s["role"] for s in r.json()["data"]["remedy"]["refund"]["approval"]["steps"]] == roles, amount


async def test_a_rejected_refund_returns_the_complaint_to_qc_and_a_new_choice_is_its_own(
        client: httpx.AsyncClient, remedies: Shop) -> None:
    shop = remedies
    qc = await _as(client, shop, "qc_manager")
    dm = await _as(client, shop, "district_manager")
    c = await _qc_approved(client, shop)
    first = (await _remedy(client, qc, c["id"], **_refund())).json()["data"]
    step = first["remedy"]["refund"]["approval"]["steps"][0]["id"]
    r = await _decide(client, dm, step, "reject", "Too much for a partial failure")
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["status"] == "qc_approved" and c["remedy"]["status"] == "rejected"
    assert (await _get(client, qc, c["id"]))["can"]["remedy"], "QC may choose again"
    second = (await _remedy(client, qc, c["id"], **_refund("6000.00"))).json()["data"]
    assert second["remedy"]["id"] != first["remedy"]["id"]
    approval = second["remedy"]["refund"]["approval"]
    assert approval["request_id"] != first["remedy"]["refund"]["approval"]["request_id"]
    assert all(s["decision"] is None for s in approval["steps"]), "the new request's own steps"


async def test_withdrawing_a_refund_closes_its_request(client: httpx.AsyncClient, remedies: Shop) -> None:
    shop = remedies
    qc = await _as(client, shop, "qc_manager")
    dm = await _as(client, shop, "district_manager")
    c = await _qc_approved(client, shop)
    c = (await _remedy(client, qc, c["id"], **_refund())).json()["data"]
    step = c["remedy"]["refund"]["approval"]["steps"][0]["id"]
    r = await complaints_t._post(client, qc, f"/{c['id']}/remedy/withdraw", {"remark": "Replacing instead"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "qc_approved" and r.json()["data"]["remedy"]["status"] == "withdrawn"
    r = await _decide(client, dm, step)
    assert r.status_code == 409 and _code(r) == "request_closed", r.text
    r = await complaints_t._post(client, qc, f"/{c['id']}/remedy/withdraw", {"remark": "again"})
    assert r.status_code == 409 and _code(r) == "status_changed", r.text


# ── replacement (rule 6) ─────────────────────────────────────────────────────

async def _dispatch(client: httpx.AsyncClient, h: dict[str, str], order: dict[str, Any], qty: str | None = None) -> httpx.Response:
    line = order["lines"][0]
    return await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**h, **_key()}, json={
        "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
        "lines": [{"order_line_id": line["id"], "qty": qty or line["qty"]}]})


async def _replacement(client: httpx.AsyncClient, shop: Shop) -> tuple[dict[str, Any], dict[str, Any]]:
    qc = await _as(client, shop, "qc_manager")
    dispatch = await _as(client, shop, "dispatch_manager")
    c = await _qc_approved(client, shop)
    r = await _remedy(client, qc, c["id"], kind="replacement", remark="Replace the failed laterals")
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    link = c["remedy"]["replacement"]["order"]
    r = await client.get(f"{V1}/orders/{link['id']}", headers=dispatch)
    assert r.status_code == 200, r.text
    return c, r.json()["data"]


async def test_a_replacement_is_a_free_order_that_closes_the_complaint_when_shipped(
        client: httpx.AsyncClient, remedies: Shop, sessions: Sessions) -> None:
    shop = remedies
    dispatch = await _as(client, shop, "dispatch_manager")
    c, order = await _replacement(client, shop)
    assert c["status"] == "remedy_pending" and c["remedy"]["kind"] == "replacement"
    assert order["order_type"] == "replacement" and order["status"] == "submitted"
    assert order["totals"]["total"] == "0.00" and order["lines"][0]["qty"] == "340.000"
    assert order["complaint"] == {"id": c["id"], "complaint_no": c["complaint_no"]}
    steps = order["approval"]["steps"]
    assert [s["role"] for s in steps] == ["dispatch_manager"], "Dispatch alone (D3)"
    r = await _decide(client, dispatch, steps[0]["id"])
    assert r.status_code == 200 and r.json()["data"]["status"] == "approved", r.text
    s = sessions()
    try:
        queued = (await s.execute(text(
            "SELECT count(*) FROM notification_outbox WHERE template_key = 'order.confirmed' "
            "AND payload ->> 'order_no' = :n"), {"n": order["order_no"]})).scalar_one()
    finally:
        await s.close()
    assert queued == 0, "no 'order confirmed, 0.00' to the farmer (D9)"
    r = await _dispatch(client, dispatch, order, "140")
    assert r.status_code == 201, r.text
    assert (await _get(client, await _as(client, shop, "qc_manager"), c["id"]))["status"] == "remedy_pending", "partly shipped"
    r = await _dispatch(client, dispatch, order, "200")
    assert r.status_code == 201, r.text
    c = await _get(client, await _as(client, shop, "qc_manager"), c["id"])
    assert c["status"] == "closed" and c["remedy"]["status"] == "completed"
    assert c["remedy"]["replacement"]["order"]["status"] == "dispatched"


async def test_a_rejected_replacement_is_cancelled_and_returns_the_complaint(
        client: httpx.AsyncClient, remedies: Shop) -> None:
    shop = remedies
    dispatch = await _as(client, shop, "dispatch_manager")
    c, order = await _replacement(client, shop)
    r = await _decide(client, dispatch, order["approval"]["steps"][0]["id"], "reject", "Out of stock")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "cancelled", "cancelled, never an editable draft (B4)"
    c = await _get(client, await _as(client, shop, "qc_manager"), c["id"])
    assert c["status"] == "qc_approved" and c["remedy"]["status"] == "cancelled"


async def test_a_replacement_is_withdrawn_until_it_ships(client: httpx.AsyncClient, remedies: Shop) -> None:
    shop = remedies
    qc = await _as(client, shop, "qc_manager")
    dispatch = await _as(client, shop, "dispatch_manager")
    c, order = await _replacement(client, shop)
    await _decide(client, dispatch, order["approval"]["steps"][0]["id"])
    order = (await client.get(f"{V1}/orders/{order['id']}", headers=dispatch)).json()["data"]
    assert (await _dispatch(client, dispatch, order, "10")).status_code == 201
    r = await complaints_t._post(client, qc, f"/{c['id']}/remedy/withdraw", {"remark": "Refund instead"})
    assert r.status_code == 409 and _code(r) == "status_changed", "something shipped"

    c2, order2 = await _replacement(client, shop)
    r = await complaints_t._post(client, qc, f"/{c2['id']}/remedy/withdraw", {"remark": "Refund instead"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "qc_approved", r.text
    o = (await client.get(f"{V1}/orders/{order2['id']}", headers=dispatch)).json()["data"]
    assert o["status"] == "cancelled"


async def test_a_replacement_cancelled_or_closed_short_empty_reopens_the_choice(
        client: httpx.AsyncClient, remedies: Shop) -> None:
    shop = remedies
    dispatch = await _as(client, shop, "dispatch_manager")
    sm = await _as(client, shop, "state_manager")
    c, order = await _replacement(client, shop)
    await _decide(client, dispatch, order["approval"]["steps"][0]["id"])
    r = await client.post(f"{V1}/orders/{order['id']}/close-short", headers={**dispatch, **_key()},
                          json={"remark": "Product discontinued"})
    assert r.status_code == 200, r.text
    assert (await _get(client, await _as(client, shop, "qc_manager"), c["id"]))["status"] == "qc_approved"

    c2, order2 = await _replacement(client, shop)
    r = await client.post(f"{V1}/orders/{order2['id']}/cancel", headers={**sm, **_key()}, json={"remark": "Duplicate"})
    assert r.status_code == 200, r.text
    assert (await _get(client, await _as(client, shop, "qc_manager"), c2["id"]))["status"] == "qc_approved"


async def test_an_unpriced_product_refuses_the_replacement_and_writes_nothing(
        client: httpx.AsyncClient, remedies: Shop, sessions: Sessions) -> None:
    shop = remedies
    qc = await _as(client, shop, "qc_manager")
    s = sessions()
    other = str((await s.execute(text(
        "INSERT INTO product (description, product_category_id, quotation_category, uom_id) "
        "SELECT CAST(:d AS citext), (SELECT id FROM product_category ORDER BY sort_order LIMIT 1), 'field', "
        "(SELECT id FROM uom WHERE decimals = 0 LIMIT 1) RETURNING id"), {"d": f"UNPRICED {uuid.uuid4().hex[:8]}"})).scalar_one())
    await s.commit()
    await s.close()
    try:
        c = await _qc_approved(client, shop, lines=[{"product_id": other, "supplied_qty": "10", "defective_qty": "2"}])
        r = await _remedy(client, qc, c["id"], kind="replacement", remark="Replace")
        assert r.status_code == 422 and _code(r) == "replacement_unpriced", r.text
        assert (await _get(client, qc, c["id"]))["status"] == "qc_approved"
    finally:
        s = sessions()
        # the line guard holds lines to a draft parent, as the shop's teardown knows
        await s.execute(text("UPDATE complaint SET status = 'draft' WHERE id IN "
                             "(SELECT complaint_id FROM complaint_line WHERE product_id = CAST(:p AS uuid))"), {"p": other})
        await s.execute(text("DELETE FROM complaint_line WHERE product_id = CAST(:p AS uuid)"), {"p": other})
        await s.execute(text("DELETE FROM product WHERE id = CAST(:p AS uuid)"), {"p": other})
        await s.commit()
        await s.close()


# ── no action, refusals, who sees what ───────────────────────────────────────

async def test_no_action_closes_at_once(client: httpx.AsyncClient, remedies: Shop) -> None:
    qc = await _as(client, remedies, "qc_manager")
    c = await _qc_approved(client, remedies)
    r = await _remedy(client, qc, c["id"], kind="none", remark="Installation fault, fixed on site")
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["status"] == "closed" and c["remedy"]["kind"] == "none" and c["remedy"]["status"] == "completed"
    r = await _remedy(client, qc, c["id"], kind="none", remark="again")
    assert r.status_code == 409 and _code(r) == "status_changed", r.text


async def test_only_qc_chooses_and_the_body_must_fit_the_kind(client: httpx.AsyncClient, remedies: Shop) -> None:
    shop = remedies
    qc = await _as(client, shop, "qc_manager")
    c = await _qc_approved(client, shop)
    for role in ("field_officer", "district_manager", "account_manager"):
        r = await _remedy(client, await _as(client, shop, role), c["id"], kind="none", remark="x")
        assert r.status_code == 403, (role, r.text)
    for body, field in (({"kind": "refund", "remark": "x"}, "amount"),
                        ({"kind": "refund", "amount": "100", "remark": "x"}, "payee_name"),
                        ({"kind": "none", "amount": "100", "remark": "x"}, "kind"),
                        ({"kind": "refund", "amount": "0", "payee_name": "A", "remark": "x"}, "amount"),
                        ({"kind": "refund", "amount": "1.005", "payee_name": "A", "remark": "x"}, "amount"),
                        ({"kind": "refund", "amount": "100", "payee_name": "A", "remark": "x",
                          "paid_through_partner_id": str(uuid.uuid4())}, "paid_through_partner_id")):
        r = await _remedy(client, qc, c["id"], **body)
        assert r.status_code == 422 and field in str(r.json()["error"].get("fields")), (body, r.text)
    submitted = await complaints_t._create(client, shop, await _as(client, shop, "field_officer"))
    r = await _remedy(client, qc, submitted["id"], kind="none", remark="x")
    assert r.status_code == 409 and _code(r) == "status_changed", "not qc_approved"


async def test_accounts_sees_a_complaint_and_decides_nothing_on_it(client: httpx.AsyncClient, remedies: Shop) -> None:
    am = await _as(client, remedies, "account_manager")
    c = await _qc_approved(client, remedies)
    got = await _get(client, am, c["id"])
    assert not any(got["can"][k] for k in ("check", "qc", "remedy", "withdraw", "edit", "submit"))


async def test_a_dealer_sees_the_remedy_without_its_people_or_payee(
        client: httpx.AsyncClient, remedies: Shop, sessions: Sessions) -> None:
    shop = remedies
    qc = await _as(client, shop, "qc_manager")
    dealer, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        dealer_c = await complaints_t._create(client, shop, dealer)
        dm = await _as(client, shop, "district_manager")
        r = await complaints_t._post(client, dealer, f"/{dealer_c['id']}/submit")
        assert r.status_code == 200, r.text
        await complaints_t._post(client, dm, f"/{dealer_c['id']}/check", {"decision": "approve", "remark": "Genuine"})
        await complaints_t._post(client, qc, f"/{dealer_c['id']}/qc", {"verdict": "approved", "remark": "Defect"})
        r = await _remedy(client, qc, dealer_c["id"], **_refund(paid_through_partner_id=shop.partner))
        assert r.status_code == 200, r.text
        seen = await _get(client, dealer, dealer_c["id"])
        remedy = seen["remedy"]
        assert remedy["kind"] == "refund" and remedy["refund"]["amount"] == "12500.00"
        assert remedy["refund"]["payee_name"] is None and remedy["refund"]["paid_through"] is None
        assert remedy["refund"]["approval"] is None and remedy["chosen_by"] is None and remedy["remark"] is None
        timeline = (await client.get(f"{V1}/complaints/{dealer_c['id']}/timeline", headers=dealer)).json()["data"]
        event = next(e for e in timeline if e["kind"] == "complaint.refund_requested")
        assert event["actor"] is None and "chosen_by" not in event["payload"]
    finally:
        await complaints_t._forget(sessions, mobile)


async def test_a_replacement_order_is_never_created_through_post_orders(client: httpx.AsyncClient, remedies: Shop) -> None:
    officer = await _as(client, remedies, "field_officer")
    body = {**endpoints._direct(remedies), "order_type": "replacement"}
    r = await client.post(f"{V1}/orders", json=body, headers={**officer, **_key()})
    assert r.status_code == 422 and _code(r) == "order_type_unsupported", r.text


async def test_refund_limits_are_admin_rows(client: httpx.AsyncClient, remedies: Shop) -> None:
    admin = await _as(client, remedies, "admin_sales")
    rows = (await client.get(f"{V1}/approvals/thresholds", headers=admin)).json()["data"]
    refund = {r["role"]: r["max_amount"] for r in rows if r["doc_type"] == "complaint" and r["territory"] is None}
    assert refund == {"district_manager": "25000.00", "state_manager": "100000.00", "regional_manager": None}


# ── concurrency (spec §10) ───────────────────────────────────────────────────

def _caller(shop: Shop, role: str) -> Caller:
    return Caller(shop.ids[role], shop.office, None, scopes={"complaints": "global", "sales_orders": "global"})


async def test_two_remedy_choices_at_once_leave_one(client: httpx.AsyncClient, remedies: Shop, sessions: Sessions) -> None:
    c = await _qc_approved(client, remedies)
    body = sch.RemedyIn(kind="none", remark="Settled on site")

    async def work(s: AsyncSession) -> Any:
        return await service.choose_remedy(s, _caller(remedies, "qc_manager"), c["id"], body)
    me = remedies.ids["qc_manager"]
    got, waited = await conc._race(sessions, (me, work), (me, work), on="complaint")
    assert waited, "the second choice did not queue on the complaint"
    assert sorted(conc._outcome(g) for g in got) == ["ok", "status_changed"], got


async def test_a_withdraw_racing_the_last_approval_loses_cleanly(client: httpx.AsyncClient, remedies: Shop,
                                                                 sessions: Sessions) -> None:
    from api.schemas import orders as order_sch
    from api.services import approvals as approval_service

    shop = remedies
    qc = await _as(client, shop, "qc_manager")
    c = await _qc_approved(client, shop)
    c = (await _remedy(client, qc, c["id"], **_refund())).json()["data"]
    steps = c["remedy"]["refund"]["approval"]["steps"]
    await _decide(client, await _as(client, shop, "district_manager"), steps[0]["id"])

    async def approve(s: AsyncSession) -> Any:
        return await approval_service.decide(s, _caller(shop, "account_manager"), steps[1]["id"],
                                             order_sch.DecisionRequest(decision="approve", remark="UTR 1"))

    async def withdraw(s: AsyncSession) -> Any:
        return await service.withdraw_remedy(s, _caller(shop, "qc_manager"), c["id"], sch.WithdrawIn(remark="Stop"))
    got, waited = await conc._race(sessions, (shop.ids["account_manager"], approve),
                                   (shop.ids["qc_manager"], withdraw), on="complaint")
    assert waited, "the withdraw did not queue on the complaint"
    assert [conc._outcome(g) for g in got] == ["ok", "status_changed"], got
    assert (await _get(client, qc, c["id"]))["status"] == "closed"


async def test_a_withdraw_racing_a_dispatch_queues_on_the_order_not_a_deadlock(
        client: httpx.AsyncClient, remedies: Shop, sessions: Sessions) -> None:
    """Delta B-8: every path touching an order and a complaint takes the order first."""
    from api.schemas import orders as order_sch
    from api.services import orders as order_service

    shop = remedies
    dispatch = await _as(client, shop, "dispatch_manager")
    c, order = await _replacement(client, shop)
    await _decide(client, dispatch, order["approval"]["steps"][0]["id"])
    order = (await client.get(f"{V1}/orders/{order['id']}", headers=dispatch)).json()["data"]
    body = order_sch.DispatchCreate.model_validate({
        "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
        "lines": [{"order_line_id": order["lines"][0]["id"], "qty": order["lines"][0]["qty"]}]})

    async def ship(s: AsyncSession) -> Any:
        return await order_service.record_dispatch(s, _caller(shop, "dispatch_manager"), order["id"], body)

    async def withdraw(s: AsyncSession) -> Any:
        return await service.withdraw_remedy(s, _caller(shop, "qc_manager"), c["id"], sch.WithdrawIn(remark="Stop"))
    got, waited = await conc._race(sessions, (shop.ids["dispatch_manager"], ship),
                                   (shop.ids["qc_manager"], withdraw), on="sales_order")
    assert waited, "the withdraw did not queue on the order"
    assert [conc._outcome(g) for g in got] == ["ok", "status_changed"], got
    assert (await _get(client, await _as(client, shop, "qc_manager"), c["id"]))["status"] == "closed"
