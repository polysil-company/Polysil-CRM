"""FS-029 over the API: the order on the lead timeline (BE-020), one conversation
(BE-021), and whose approval is next as an order-list filter (BE-022)."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_complaints as cmp
from tests.api import test_exports as ex
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _submitted(client: httpx.AsyncClient, h: dict[str, str], body: dict) -> dict:
    return await endpoints._submit(client, h, (await endpoints._create(client, h, body))["id"])


# ── BE-020: the order on the lead timeline ───────────────────────────────────

async def _order_events(client: httpx.AsyncClient, h: dict[str, str], lead_id: str) -> list[dict]:
    r = await client.get(f"{V1}/leads/{lead_id}/timeline", headers=h)
    assert r.status_code == 200, r.text
    return [e for e in r.json()["data"] if "order_id" in e["payload"]]


async def test_every_event_on_an_order_names_it(client: httpx.AsyncClient, shop: Shop) -> None:
    """Order, approval and dispatch kinds alike (review E-3); quotation events keep
    their own fields and gain no order ones."""
    ho = await endpoints._as(client, shop, "field_officer")
    q = await endpoints._accepted_quotation(client, shop, ho)
    order = await endpoints._approve_all(
        client, shop, await _submitted(client, ho, {"quotation_ids": [q["id"]]}))
    hd = await endpoints._as(client, shop, "dispatch_manager")
    line = order["lines"][0]
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()},
                          json={"dc_no": "DC-1",
                                "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
                                "lines": [{"order_line_id": line["id"], "qty": "1"}]})
    assert r.status_code == 201, r.text

    r = await client.get(f"{V1}/leads/{q['lead']['id']}/timeline", headers=ho)
    tl = r.json()["data"]
    on_order = [e for e in tl if e["kind"].startswith(("order.", "dispatch.", "approval."))]
    kinds = {e["kind"] for e in on_order}
    wanted = {"order.created", "order.submitted", "approval.decided", "dispatch.recorded"}
    assert wanted <= kinds, kinds
    for e in on_order:
        assert e["payload"]["order_id"] == order["id"], e
        assert e["payload"]["order_no"] == order["order_no"], e
    for e in (e for e in tl if e["kind"].startswith("quotation.")):
        assert "order_id" not in e["payload"] and e["payload"]["quotation_id"] == q["id"], e


async def test_a_draft_order_has_no_number_yet(client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    q = await endpoints._accepted_quotation(client, shop, ho)
    draft = await endpoints._create(client, ho, {"quotation_ids": [q["id"]]})
    events = await _order_events(client, ho, q["lead"]["id"])
    assert events and all(e["payload"]["order_id"] == draft["id"] for e in events), events
    assert all(e["payload"]["order_no"] is None for e in events), events


async def test_an_old_empty_payload_gains_the_order(client: httpx.AsyncClient, shop: Shop,
                                                    sessions: Sessions) -> None:
    """Read-time: an event written with `{}` (order.approved, order.returned...) names
    its order too."""
    ho = await endpoints._as(client, shop, "field_officer")
    q = await endpoints._accepted_quotation(client, shop, ho)
    order = await _submitted(client, ho, {"quotation_ids": [q["id"]]})
    s = sessions()
    await s.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('sales_order', CAST(:o AS uuid), CAST(:l AS uuid), 'order.returned', NULL, "
        "'{}'::jsonb)"),
        {"o": order["id"], "l": q["lead"]["id"]})
    await s.commit()
    await s.close()
    events = await _order_events(client, ho, q["lead"]["id"])
    returned = next(e for e in events if e["kind"] == "order.returned")
    assert returned["payload"] == {"order_id": order["id"], "order_no": order["order_no"]}


# ── BE-021: one conversation ─────────────────────────────────────────────────

async def test_a_conversation_reads_before_anyone_writes(client: httpx.AsyncClient,
                                                         shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    dm = await endpoints._as(client, shop, "district_manager")
    r = await client.post(f"{V1}/conversations", headers={**fo, **_key()},
                          json={"participant_id": shop.ids["district_manager"]})
    assert r.status_code in (200, 201), r.text
    cid = r.json()["data"]["id"]

    for h, other in ((fo, "district_manager"), (dm, "field_officer")):
        r = await client.get(f"{V1}/conversations/{cid}", headers=h)
        assert r.status_code == 200, r.text
        c = r.json()["data"]
        assert c["id"] == cid and c["participant"]["id"] == shop.ids[other], c
        assert c["last_message"] is None and c["unread_count"] == 0, c

    r = await client.post(f"{V1}/conversations/{cid}/messages", headers={**fo, **_key()},
                          json={"body": "Kal milte hain"})
    assert r.status_code == 201, r.text
    c = (await client.get(f"{V1}/conversations/{cid}", headers=dm)).json()["data"]
    assert c["last_message"]["body"] == "Kal milte hain" and c["unread_count"] == 1, c


async def test_a_conversation_not_yours_is_not_found(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    sm = await endpoints._as(client, shop, "state_manager")
    r = await client.post(f"{V1}/conversations", headers={**fo, **_key()},
                          json={"participant_id": shop.ids["district_manager"]})
    cid = r.json()["data"]["id"]
    assert (await client.get(f"{V1}/conversations/{cid}", headers=sm)).status_code == 404
    assert (await client.get(f"{V1}/conversations/{uuid.uuid4()}", headers=fo)).status_code == 404
    assert (await client.get(f"{V1}/conversations/not-a-uuid", headers=fo)).status_code == 422


async def test_a_dealer_reads_no_conversation(client: httpx.AsyncClient, shop: Shop,
                                              sessions: Sessions) -> None:
    dealer, mobile = await cmp._dealer(client, shop, sessions)
    try:
        r = await client.get(f"{V1}/conversations/{uuid.uuid4()}", headers=dealer)
        assert r.status_code == 403, r.text
    finally:
        await cmp._forget(sessions, mobile)


# ── BE-022: whose approval is next ───────────────────────────────────────────

async def _two_waiting(client: httpx.AsyncClient, shop: Shop) -> tuple[dict, dict]:
    """One order at the District Manager's step, one at Accounts'."""
    ho = await endpoints._as(client, shop, "field_officer")
    at_dm = await _submitted(client, ho, endpoints._direct(shop))
    at_acc = await _submitted(client, ho, endpoints._direct(shop))
    dm = await endpoints._as(client, shop, "district_manager")
    r = await endpoints._decide(client, dm, at_acc["approval"]["steps"][0]["id"])
    assert r.status_code == 200, r.text
    return at_dm, r.json()["data"]


async def test_the_accounts_queue_lists_only_orders_at_its_step(
        client: httpx.AsyncClient, shop: Shop) -> None:
    at_dm, at_acc = await _two_waiting(client, shop)
    acc = await endpoints._as(client, shop, "account_manager")
    mine = {"owner": shop.ids["field_officer"]}    # the account manager sees every shop's orders

    async def listed(**params: str) -> dict:
        r = await client.get(f"{V1}/orders", headers=acc,
                             params={**mine, "include_total": "true", **params})
        assert r.status_code == 200, r.text
        return r.json()

    page = await listed(waiting_on="account_manager")
    assert [o["id"] for o in page["data"]] == [at_acc["id"]] and page["meta"]["total"] == 1
    assert page["data"][0]["approval_waiting_on"] == "account_manager"
    assert [o["id"] for o in (await listed(waiting_on="district_manager"))["data"]] == [at_dm["id"]]
    assert (await listed(waiting_on="no_such_role"))["data"] == []
    assert (await listed(waiting_on="account_manager", status="draft"))["data"] == []

    # list total equals the stats count for the role (review E-10)
    stats = (await client.get(f"{V1}/orders/stats", headers=acc, params=mine)).json()
    assert stats["waiting_on"] == {"district_manager": 1, "account_manager": 1}, stats
    narrowed = (await client.get(f"{V1}/orders/stats", headers=acc,
                                 params={**mine, "waiting_on": "account_manager"})).json()
    assert narrowed["total"] == 1 and narrowed["waiting_on"] == {"account_manager": 1}, narrowed

    rows = ex._rows(await client.get(f"{V1}/orders/export", headers=acc,
                                     params={**mine, "waiting_on": "account_manager"}))
    assert len(rows) == 1, rows


@pytest.mark.parametrize("bad", ["Account", "1role", "a-b", "x" * 65])
async def test_a_malformed_role_is_422(client: httpx.AsyncClient, shop: Shop, bad: str) -> None:
    acc = await endpoints._as(client, shop, "account_manager")
    for path in ("/orders", "/orders/stats", "/orders/export"):
        r = await client.get(f"{V1}{path}", headers=acc, params={"waiting_on": bad})
        assert r.status_code == 422, (path, r.text)


async def test_an_officer_filters_only_within_their_own_orders(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Review E-9: the filter reads under the caller's policies, like the column. A
    District Manager's order at the Accounts step is not the officer's to see."""
    _, at_acc = await _two_waiting(client, shop)
    dm = await endpoints._as(client, shop, "district_manager")
    theirs = await _submitted(client, dm, endpoints._direct(shop))
    for step in theirs["approval"]["steps"]:
        if step["role"] == "account_manager":
            break
        h = await endpoints._as(client, shop, step["role"])
        r = await endpoints._decide(client, h, step["id"])
        assert r.status_code == 200, r.text
    ho = await endpoints._as(client, shop, "field_officer")
    r = await client.get(f"{V1}/orders", headers=ho, params={"waiting_on": "account_manager"})
    assert r.status_code == 200, r.text
    assert [o["id"] for o in r.json()["data"]] == [at_acc["id"]]
    r = await client.get(f"{V1}/orders", headers=dm, params={"waiting_on": "account_manager"})
    assert {at_acc["id"], theirs["id"]} <= {o["id"] for o in r.json()["data"]}
