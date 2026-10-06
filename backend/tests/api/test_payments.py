"""FS-022 over the API: receipts, allocation, void, instalments, the order's
payments block, the inbox's payment status and the dealer ledger."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
# the IST day, as the service books orders: the UTC date is a day behind between
# 18:30 and 24:00 UTC, and CI once ran there (PR 70)
TODAY = today_ist().isoformat()


@pytest_asyncio.fixture(autouse=True)
async def _forget_payments(shop: Shop, sessions: Sessions) -> AsyncIterator[None]:
    """Torn down before `shop`, which deletes its orders: the payment rows reference them."""
    yield
    s = sessions()
    try:
        people = list(shop.ids.values())
        for stmt in (
            "DELETE FROM payment_allocation WHERE created_by = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM payment_schedule WHERE created_by = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM activity_event WHERE kind LIKE 'payment.%' AND actor_id = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM payment WHERE entered_by = ANY(CAST(:p AS uuid[]))",
        ):
            await s.execute(text(stmt), {"p": people})
        await s.commit()
    finally:
        await s.close()


async def _approved(client: httpx.AsyncClient, shop: Shop, **over: Any) -> dict:
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._submit(client, fo, (await endpoints._create(client, fo, endpoints._direct(shop, **over)))["id"])
    return await endpoints._approve_all(client, shop, order)


async def _pay(client: httpx.AsyncClient, h: dict[str, str], body: dict[str, Any]) -> httpx.Response:
    base = {"mode": "neft", "ref_no": "UTR" + uuid.uuid4().hex[:10], "received_on": TODAY}
    return await client.post(f"{V1}/payments", headers={**h, **_key()}, json={**base, **body})


async def test_a_receipt_pays_an_order_and_the_order_shows_it(client: httpx.AsyncClient, shop: Shop) -> None:
    order = await _approved(client, shop)
    total = Decimal(order["totals"]["total"])
    accounts = await endpoints._as(client, shop, "account_manager")
    part = (total / 2).quantize(Decimal("0.01"))
    r = await _pay(client, accounts, {"partner_id": None, "amount": str(part),
                                      "allocations": [{"sales_order_id": order["id"], "amount": str(part)}]})
    assert r.status_code == 201, r.text
    pay = r.json()["data"]
    assert pay["allocated"] == f"{part:.2f}" and pay["unallocated"] == "0.00"
    assert pay["allocations"][0]["order_balance"] == f"{total - part:.2f}"
    block = (await client.get(f"{V1}/orders/{order['id']}", headers=accounts)).json()["data"]["payments"]
    assert block["status"] == "part_paid" and block["received"] == f"{part:.2f}" and len(block["receipts"]) == 1
    fo = await endpoints._as(client, shop, "field_officer")
    assert (await client.get(f"{V1}/orders/{order['id']}", headers=fo)).json()["data"]["payments"] is None, \
        "a field officer holds no payments.view"
    timeline = (await client.get(f"{V1}/orders/{order['id']}/timeline", headers=fo)).json()["data"]
    paid = [e for e in timeline if e["kind"] == "payment.allocated"]
    assert paid and all("amount" not in (e.get("payload") or {}) for e in paid), "no amount in any event (B-2)"


async def test_the_refusals(client: httpx.AsyncClient, shop: Shop) -> None:
    order = await _approved(client, shop)
    accounts = await endpoints._as(client, shop, "account_manager")
    one = [{"sales_order_id": order["id"], "amount": "10.00"}]
    r = await _pay(client, accounts, {"mode": "cheque", "ref_no": None, "amount": "10.00", "allocations": one})
    assert r.status_code == 422 and r.json()["error"]["code"] == "ref_required", r.text
    r = await _pay(client, accounts, {"amount": "10.00", "allocations": [{"sales_order_id": order["id"], "amount": "10.01"}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "over_allocated", r.text
    r = await _pay(client, accounts, {"amount": "10.00", "allocations": []})
    assert r.status_code == 422 and r.json()["error"]["code"] == "must_allocate", "no dealer: allocate in full"
    r = await _pay(client, accounts, {"partner_id": shop.partner, "amount": "10.00", "allocations": one})
    assert r.status_code == 422 and r.json()["error"]["code"] == "partner_mismatch", r.text
    r = await _pay(client, accounts, {"amount": "10.005", "allocations": one})
    assert r.status_code == 422, "a third decimal is refused, not rounded"
    fo = await endpoints._as(client, shop, "field_officer")
    draft = await endpoints._create(client, fo, endpoints._direct(shop))
    r = await _pay(client, accounts, {"amount": "10.00", "allocations": [{"sales_order_id": draft["id"], "amount": "10.00"}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "order_not_payable", r.text
    ref = "UTR" + uuid.uuid4().hex[:10]
    assert (await _pay(client, accounts, {"ref_no": ref, "amount": "10.00", "allocations": one})).status_code == 201
    r = await _pay(client, accounts, {"ref_no": ref, "amount": "10.00", "allocations": one})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_reference", r.text
    dm = await endpoints._as(client, shop, "district_manager")
    assert (await _pay(client, dm, {"amount": "1.00", "allocations": one})).status_code == 403


async def test_a_void_stops_counting_and_happens_once(client: httpx.AsyncClient, shop: Shop) -> None:
    order = await _approved(client, shop)
    accounts = await endpoints._as(client, shop, "account_manager")
    pay = (await _pay(client, accounts, {"amount": "100.00", "allocations": [{"sales_order_id": order["id"], "amount": "100.00"}]})).json()["data"]
    r = await client.post(f"{V1}/payments/{pay['id']}/void", headers={**accounts, **_key()}, json={"reason": "Wrong amount"})
    assert r.status_code == 200 and r.json()["data"]["voided"]["reason"] == "Wrong amount", r.text
    block = (await client.get(f"{V1}/orders/{order['id']}", headers=accounts)).json()["data"]["payments"]
    assert block["received"] == "0.00" and block["status"] == "unpaid"
    r = await client.post(f"{V1}/payments/{pay['id']}/void", headers={**accounts, **_key()}, json={"reason": "again"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_void"


async def test_instalments_cover_and_go_overdue(client: httpx.AsyncClient, shop: Shop) -> None:
    order = await _approved(client, shop)
    total = Decimal(order["totals"]["total"])
    accounts = await endpoints._as(client, shop, "account_manager")
    past = (today_ist() - dt.timedelta(days=5)).isoformat()
    later = (today_ist() + dt.timedelta(days=30)).isoformat()
    first = (total / 4).quantize(Decimal("0.01"))
    r = await client.put(f"{V1}/orders/{order['id']}/payment-schedule", headers={**accounts, **_key()},
                         json={"instalments": [{"due_on": past, "amount": str(first), "note": "Advance"},
                                               {"due_on": later, "amount": str(total - first)}]})
    assert r.status_code == 200, r.text
    block = r.json()["data"]
    assert block["overdue"] is True and block["overdue_amount"] == f"{first:.2f}"
    assert [i["covered"] for i in block["schedule"]] == [False, False]
    await _pay(client, accounts, {"amount": str(first), "allocations": [{"sales_order_id": order["id"], "amount": str(first)}]})
    block = (await client.get(f"{V1}/orders/{order['id']}", headers=accounts)).json()["data"]["payments"]
    assert block["overdue"] is False and [i["covered"] for i in block["schedule"]] == [True, False]
    r = await client.put(f"{V1}/orders/{order['id']}/payment-schedule", headers={**accounts, **_key()},
                         json={"instalments": [{"due_on": later, "amount": str(total + 1)}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "schedule_over_payable", r.text


async def test_a_retried_receipt_counts_once(client: httpx.AsyncClient, shop: Shop) -> None:
    order = await _approved(client, shop)
    accounts = await endpoints._as(client, shop, "account_manager")
    key = _key()
    body = {"mode": "cash", "received_on": TODAY, "amount": "50.00",
            "allocations": [{"sales_order_id": order["id"], "amount": "50.00"}]}
    for _ in range(2):
        r = await client.post(f"{V1}/payments", headers={**accounts, **key}, json=body)
        assert r.status_code == 201, r.text
    block = (await client.get(f"{V1}/orders/{order['id']}", headers=accounts)).json()["data"]["payments"]
    assert block["received"] == "50.00"


async def test_the_accounts_step_shows_the_payment_status(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._submit(client, fo, (await endpoints._create(client, fo, endpoints._direct(shop)))["id"])
    for step in order["approval"]["steps"]:
        if step["role"] == "account_manager":
            break
        h = await endpoints._as(client, shop, step["role"])
        assert (await endpoints._decide(client, h, step["id"])).status_code == 200
    accounts = await endpoints._as(client, shop, "account_manager")
    pending = (await client.get(f"{V1}/approvals/pending", headers=accounts)).json()["data"]
    row = next(p for p in pending if p["document"]["id"] == order["id"])
    assert row["document"]["payment_status"] == "unpaid"


async def test_a_dealer_ledger_runs_a_balance(client: httpx.AsyncClient, shop: Shop) -> None:
    order = await _approved(client, shop, partner_id=shop.partner)
    total = Decimal(order["totals"]["total"])
    accounts = await endpoints._as(client, shop, "account_manager")
    extra = Decimal("500.00")
    r = await _pay(client, accounts, {"partner_id": shop.partner, "amount": str(total + extra),
                                      "allocations": [{"sales_order_id": order["id"], "amount": str(total)}]})
    assert r.status_code == 201 and r.json()["data"]["unallocated"] == f"{extra:.2f}", r.text
    led = (await client.get(f"{V1}/partners/{shop.partner}/ledger", headers=accounts)).json()["data"]
    mine = [x for x in led["rows"] if x["ref"] == order["order_no"] or x["kind"] == "receipt"]
    assert mine[0]["kind"] == "order"
    assert Decimal(led["closing_balance"]) <= -extra, "the dealer is in credit by at least the advance"
    assert Decimal(led["unallocated"]) >= extra
    tomorrow = (today_ist() + dt.timedelta(days=1)).isoformat()
    later = (await client.get(f"{V1}/partners/{shop.partner}/ledger", headers=accounts, params={"from": tomorrow})).json()["data"]
    assert later["rows"] == [] and later["opening_balance"] == led["closing_balance"]


async def test_an_advance_is_allocated_later_and_a_void_blocks_more(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-5: the allocations endpoint and what is left of a receipt."""
    order = await _approved(client, shop, partner_id=shop.partner)
    accounts = await endpoints._as(client, shop, "account_manager")
    pay = (await _pay(client, accounts, {"partner_id": shop.partner, "amount": "100.00"})).json()["data"]
    assert pay["unallocated"] == "100.00"
    url = f"{V1}/payments/{pay['id']}/allocations"
    r = await client.post(url, headers={**accounts, **_key()},
                          json={"allocations": [{"sales_order_id": order["id"], "amount": "60.00"}]})
    assert r.status_code == 200 and r.json()["data"]["unallocated"] == "40.00", r.text
    r = await client.post(url, headers={**accounts, **_key()},
                          json={"allocations": [{"sales_order_id": order["id"], "amount": "40.01"}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "over_allocated", "60 is already spent"
    await client.post(f"{V1}/payments/{pay['id']}/void", headers={**accounts, **_key()}, json={"reason": "x"})
    r = await client.post(url, headers={**accounts, **_key()},
                          json={"allocations": [{"sales_order_id": order["id"], "amount": "1.00"}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_void"


async def test_a_paid_orders_dealer_does_not_change(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-2: pay a submitted order, reject it to draft, change its dealer: 409."""
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._submit(client, fo, (await endpoints._create(client, fo, endpoints._direct(shop)))["id"])
    accounts = await endpoints._as(client, shop, "account_manager")
    r = await _pay(client, accounts, {"amount": "10.00", "allocations": [{"sales_order_id": order["id"], "amount": "10.00"}]})
    assert r.status_code == 201, r.text
    step = order["approval"]["steps"][0]
    h = await endpoints._as(client, shop, step["role"])
    assert (await endpoints._decide(client, h, step["id"], "reject", "Fix it")).status_code == 200
    r = await client.patch(f"{V1}/orders/{order['id']}", headers={**fo, **_key()}, json={"partner_id": shop.partner})
    assert r.status_code == 409 and r.json()["error"]["code"] == "order_has_payments", r.text
    r = await client.patch(f"{V1}/orders/{order['id']}", headers={**fo, **_key()}, json={"remarks": "still fine"})
    assert r.status_code == 200, r.text


async def test_who_reads_what(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-4, F-5: the ledger is for global scope; Dispatch sees no payment status."""
    order = await _approved(client, shop, partner_id=shop.partner)
    accounts = await endpoints._as(client, shop, "account_manager")
    await _pay(client, accounts, {"partner_id": shop.partner, "amount": "10.00", "remark": "internal",
                                  "allocations": [{"sales_order_id": order["id"], "amount": "10.00"}]})
    dm = await endpoints._as(client, shop, "district_manager")
    r = await client.get(f"{V1}/partners/{shop.partner}/ledger", headers=dm)
    assert r.status_code == 403 and r.json()["error"]["code"] == "ledger_scope"
    receipts = (await client.get(f"{V1}/payments", headers=dm, params={"sales_order_id": order["id"]})).json()["data"]
    assert receipts and receipts[0]["remark"] == "internal", "staff read the remark"


async def test_a_dealer_reads_its_receipts_without_remarks(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Question 15.14: Accounts' notes are internal."""
    from tests.api import test_complaints as complaints_t
    order = await _approved(client, shop, partner_id=shop.partner)
    accounts = await endpoints._as(client, shop, "account_manager")
    pay = (await _pay(client, accounts, {"partner_id": shop.partner, "amount": "10.00", "remark": "internal",
                                         "allocations": [{"sales_order_id": order["id"], "amount": "10.00"}]})).json()["data"]
    dealer, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        r = await client.get(f"{V1}/payments/{pay['id']}", headers=dealer)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["remark"] is None and r.json()["data"]["entered_by"] is None
        led = await client.get(f"{V1}/partners/{shop.partner}/ledger", headers=dealer)
        assert led.status_code == 200, "a dealer reads its own ledger"
    finally:
        await complaints_t._forget(sessions, mobile)
