"""/orders, /approvals and /dispatches, end to end over ASGI (FS-011 4, 10).

A committed world: a coded state with a district and one office, a user on each
seeded role the chain names (the seed as it stands, RBAC 6.2), and a small
catalogue of its own whose price list is scoped to that state, so nothing here
overlaps another fixture's list. The catalogue's HSN, tax rate and seller
registration run from 2019 with no end: an order prices at the 2020 list and taxes
at today, and both dates must resolve (FS-011 rule 3).
"""

# ruff: noqa: E501  (embedded SQL, kept on one line so each statement reads whole)

from __future__ import annotations

import datetime as dt
import pathlib
import random
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.services.clock import today_ist
from api.storage import LocalStorage
from tests.api.conftest import PASSWORD, V1, _key, _login
from worker.jobs.orders import render_one as render_order

pytestmark = pytest.mark.db

AS_OF = "2020-06-15"
ROLES = ("field_officer", "district_manager", "state_manager", "regional_manager",
         "account_manager", "dispatch_manager", "admin_sales", "qc_manager")


@dataclass
class Shop:
    state: str
    code: str
    district: str
    office: str
    product: str
    seller: str
    users: dict[str, str]      # role code -> email
    ids: dict[str, str]        # role code -> user id; "dealer" is the partner's user
    partner: str               # a dealer in the district, on its own dealer-tier list


@pytest_asyncio.fixture
async def shop(sessions: Callable[[], AsyncSession]) -> AsyncIterator[Shop]:
    tag = uuid.uuid4().hex[:8]
    code = "S" + tag[:3].upper()
    hsn = "9" + "".join(random.choice("0123456789") for _ in range(7))
    s = sessions()
    # 4,096 codes, and a failed teardown leaves its state behind: skip a code in use
    while (await s.execute(text("SELECT 1 FROM territory WHERE level = 'state' AND code = :c"),
                           {"c": code})).first():
        code = "S" + uuid.uuid4().hex[:3].upper()
    state = str((await s.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": f"ord_state_{tag}", "c": code})).scalar_one())
    district = str((await s.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
        {"n": f"ord_district_{tag}", "p": state})).scalar_one())
    office = str((await s.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"ord_office_{tag}", "t": district})).scalar_one())
    hasher = PasswordHasher()
    users, ids = {}, {}
    for role in ROLES:
        email = f"ord_{role}_{tag}@polysil.in"
        ids[role] = str((await s.execute(text(
            "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
            "SELECT 'staff', :e, :p, :n, r.id, CAST(:o AS uuid) FROM role r WHERE r.code = :c "
            "RETURNING id"),
            {"e": email, "p": hasher.hash(PASSWORD), "n": role.replace("_", " ").title(),
             "c": role, "o": office})).scalar_one())
        users[role] = email
    product = str((await s.execute(text(
        "INSERT INTO product (description, product_category_id, quotation_category, uom_id) "
        "SELECT CAST(:d AS citext), (SELECT id FROM product_category ORDER BY sort_order LIMIT 1), "
        "'field', (SELECT id FROM uom WHERE decimals = 0 LIMIT 1) RETURNING id"),
        {"d": f"ORDER PIPE {tag}"})).scalar_one())
    await s.execute(text("INSERT INTO product_hsn (product_id, hsn_code, effective_from) "
                         "VALUES (CAST(:p AS uuid), :h, DATE '2019-01-01')"), {"p": product, "h": hsn})
    await s.execute(text("INSERT INTO gst_rate (hsn_code, rate, effective_from) "
                         "VALUES (:h, 5, DATE '2019-01-01')"), {"h": hsn})
    seller = str((await s.execute(text(
        "INSERT INTO seller_gstin (gstin, legal_name, state_territory_id, effective_from) "
        "VALUES (:g, 'Polysil Order Test', CAST(:s AS uuid), DATE '2019-01-01') RETURNING id"),
        {"g": f"{random.randint(10, 37)}AB{random.choice('CDEFGH')}DE{random.randint(1000, 9999)}F1Z{random.randint(1, 9)}",
         "s": state})).scalar_one())
    price_list = str((await s.execute(text(
        "INSERT INTO price_list (name, state_territory_id, channel_tier, status, published_at, "
        "effective_from, effective_to) VALUES (:n, CAST(:s AS uuid), 'farmer', 'published', now(), "
        "DATE '2020-01-01', DATE '2021-01-01') RETURNING id"),
        {"n": f"order list {tag}", "s": state})).scalar_one())
    await s.execute(text("INSERT INTO price_list_item (price_list_id, product_id, rate) "
                         "VALUES (CAST(:l AS uuid), CAST(:p AS uuid), 100)"),
                    {"l": price_list, "p": product})
    partner = str((await s.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, mobile, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'Shah Irrigation', :m, CAST(:t AS uuid), 'dealer') RETURNING id"),
        {"c": f"ORD{tag}".upper(), "m": "9196" + f"{random.randint(0, 10**8 - 1):08d}",
         "t": district})).scalar_one())
    ids["dealer"] = str((await s.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "SELECT 'partner_user', :m, 'Bhavesh Shah', r.id, CAST(:p AS uuid) FROM role r "
        "WHERE r.code = 'dealer' RETURNING id"),
        {"m": "9195" + f"{random.randint(0, 10**8 - 1):08d}", "p": partner})).scalar_one())
    dealer_list = str((await s.execute(text(
        "INSERT INTO price_list (name, state_territory_id, channel_tier, status, published_at, "
        "effective_from, effective_to) VALUES (:n, CAST(:s AS uuid), 'dealer', 'published', now(), "
        "DATE '2020-01-01', DATE '2021-01-01') RETURNING id"),
        {"n": f"order dealer list {tag}", "s": state})).scalar_one())
    await s.execute(text("INSERT INTO price_list_item (price_list_id, product_id, rate) "
                         "VALUES (CAST(:l AS uuid), CAST(:p AS uuid), 90)"),
                    {"l": dealer_list, "p": product})
    await s.commit()
    try:
        yield Shop(state, code, district, office, product, seller, users, ids, partner)
    finally:
        c = sessions()
        people = list(ids.values())
        orders = "(SELECT id FROM sales_order WHERE territory_id = CAST(:d AS uuid))"
        leads = "(SELECT id FROM lead WHERE territory_id = CAST(:d AS uuid))"
        quotations = "(SELECT id FROM quotation WHERE territory_id = CAST(:d AS uuid))"
        for stmt in (
            # FS-015: complaints point at people, leads, orders and products
            "DELETE FROM complaint_decision_note WHERE decision_id IN (SELECT d.id FROM complaint_decision d JOIN complaint c ON c.id = d.complaint_id WHERE c.territory_id = CAST(:d AS uuid))",
            "DELETE FROM complaint_decision WHERE complaint_id IN (SELECT id FROM complaint WHERE territory_id = CAST(:d AS uuid))",
            "DELETE FROM complaint_attachment WHERE complaint_id IN (SELECT id FROM complaint WHERE territory_id = CAST(:d AS uuid))",
            # the line guard holds every writer to a draft parent
            "UPDATE complaint SET status = 'draft' WHERE territory_id = CAST(:d AS uuid)",
            "DELETE FROM complaint_line WHERE complaint_id IN (SELECT id FROM complaint WHERE territory_id = CAST(:d AS uuid))",
            "DELETE FROM notification_outbox WHERE template_key LIKE 'complaint.%' AND payload->>'complaint_no' IN (SELECT complaint_no::text FROM complaint WHERE territory_id = CAST(:d AS uuid))",
            "DELETE FROM activity_event WHERE entity_type = 'complaint' AND entity_id IN (SELECT id FROM complaint WHERE territory_id = CAST(:d AS uuid))",
            "DELETE FROM complaint WHERE territory_id = CAST(:d AS uuid)",
            "DELETE FROM complaint_counter WHERE state_code = :c",
            # FS-014: tasks and minutes point at people, leads and each other
            "UPDATE meeting_minutes SET task_id = NULL WHERE created_by = ANY(CAST(:people AS uuid[]))",
            "DELETE FROM task WHERE assigned_to = ANY(CAST(:people AS uuid[])) OR assigned_by = ANY(CAST(:people AS uuid[]))",
            "DELETE FROM meeting_minutes WHERE created_by = ANY(CAST(:people AS uuid[]))",
            f"DELETE FROM approval_step WHERE request_id IN (SELECT id FROM approval_request WHERE entity_id IN {orders})",
            f"DELETE FROM approval_request WHERE entity_id IN {orders}",
            # FS-013: a quotation's discount approval
            f"DELETE FROM approval_step WHERE request_id IN (SELECT id FROM approval_request WHERE entity_id IN {quotations})",
            f"DELETE FROM approval_request WHERE entity_id IN {quotations}",
            f"DELETE FROM dispatch WHERE sales_order_id IN {orders}",
            f"DELETE FROM activity_event WHERE entity_id IN {orders}",
            "DELETE FROM sales_order WHERE territory_id = CAST(:d AS uuid)",
            "ALTER TABLE quotation DISABLE TRIGGER trg_quotation_refuse_sent_edit",
            f"DELETE FROM activity_event WHERE lead_id IN {leads}",
            "UPDATE quotation SET supersedes_id = NULL, superseded_by_id = NULL WHERE territory_id = CAST(:d AS uuid)",
            "DELETE FROM notification_outbox WHERE recipient IN (SELECT party_mobile FROM quotation WHERE territory_id = CAST(:d AS uuid))",
            "DELETE FROM quotation WHERE territory_id = CAST(:d AS uuid)",
            "ALTER TABLE quotation ENABLE TRIGGER trg_quotation_refuse_sent_edit",
            f"DELETE FROM lead_duplicate_link WHERE lead_a_id IN {leads} OR lead_b_id IN {leads}",
            "DELETE FROM notification_outbox WHERE recipient IN (SELECT mobile FROM lead WHERE territory_id = CAST(:d AS uuid))",
            "DELETE FROM lead WHERE territory_id = CAST(:d AS uuid)",
            "DELETE FROM order_counter WHERE state_code = :c",
            "DELETE FROM quotation_counter WHERE state_code = :c",
            "DELETE FROM inquiry_counter WHERE state_code = :c",
            "DELETE FROM approval_threshold WHERE territory_id IN (CAST(:s AS uuid), CAST(:d AS uuid))",
            "DELETE FROM idempotency_record WHERE user_id = ANY(CAST(:people AS uuid[]))",
            "DELETE FROM activity_event WHERE actor_id = ANY(CAST(:people AS uuid[])) OR entity_id = ANY(CAST(:people AS uuid[]))",
            "DELETE FROM session WHERE user_id = ANY(CAST(:people AS uuid[]))",
            "DELETE FROM login_attempt WHERE identifier = ANY(CAST(:emails AS citext[]))",
            "DELETE FROM app_user WHERE id = ANY(CAST(:people AS uuid[]))",
            "DELETE FROM channel_partner WHERE id = CAST(:cp AS uuid)",
            "DELETE FROM price_list_item WHERE price_list_id IN (CAST(:pl AS uuid), CAST(:dl AS uuid))",
            "DELETE FROM price_list WHERE id IN (CAST(:pl AS uuid), CAST(:dl AS uuid))",
            "DELETE FROM product_hsn WHERE product_id = CAST(:p AS uuid)",
            "DELETE FROM gst_rate WHERE hsn_code = :h",
            "DELETE FROM product WHERE id = CAST(:p AS uuid)",
            "DELETE FROM seller_gstin WHERE id = CAST(:sg AS uuid)",
            "DELETE FROM org_unit WHERE id = CAST(:o AS uuid)",
            "DELETE FROM territory WHERE id = CAST(:d AS uuid)",
            "DELETE FROM territory WHERE id = CAST(:s AS uuid)",
        ):
            await c.execute(text(stmt), {"d": district, "s": state, "c": code, "people": people,
                                         "emails": list(users.values()), "pl": price_list,
                                         "p": product, "h": hsn, "sg": seller, "o": office,
                                         "cp": partner, "dl": dealer_list})
        await c.commit()


async def _as(client: httpx.AsyncClient, shop: Shop, role: str) -> dict[str, str]:
    return await _login(client, shop.users[role], PASSWORD)


def _direct(shop: Shop, qty: str = "10", **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "order_type": "commercial",
        "party": {"name": "Rameshbhai Patel", "mobile": "9876543210", "address": "Vadod"},
        "place_of_supply_territory_id": shop.district, "seller_gstin_id": shop.seller,
        "price_effective_date": AS_OF,
        "lines": [{"product_id": shop.product, "qty": qty, "discount_pct": "10"}],
    }
    body.update(over)
    return body


async def _create(client: httpx.AsyncClient, h: dict[str, str], body: dict[str, object]) -> dict:
    r = await client.post(f"{V1}/orders", json=body, headers={**h, **_key()})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _submit(client: httpx.AsyncClient, h: dict[str, str], order_id: str) -> dict:
    r = await client.post(f"{V1}/orders/{order_id}/submit", json={}, headers={**h, **_key()})
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _decide(client: httpx.AsyncClient, h: dict[str, str], step_id: str,
                  decision: str = "approve", remark: str | None = "ok") -> httpx.Response:
    return await client.post(f"{V1}/approvals/steps/{step_id}/decision",
                             json={"decision": decision, "remark": remark},
                             headers={**h, **_key()})


async def _approve_all(client: httpx.AsyncClient, shop: Shop, order: dict) -> dict:
    for step in order["approval"]["steps"]:
        h = await _as(client, shop, step["role"])
        r = await _decide(client, h, step["id"], remark="Payment seen")
        assert r.status_code == 200, r.text
        order = r.json()["data"]
    return order


# ── the life of a direct order ───────────────────────────────────────────────

async def test_a_direct_order_is_priced_numbered_approved_and_dispatched(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await _as(client, shop, "field_officer")
    draft = await _create(client, ho, _direct(shop))
    assert draft["status"] == "draft" and draft["order_no"] is None
    line = draft["lines"][0]
    assert (line["gross"], line["discount1_amt"], line["taxable"]) == ("1000.00", "100.00", "900.00")
    assert draft["totals"]["total"] == "945.00", "5 % on 900.00, taxed at today's date"

    order = await _submit(client, ho, draft["id"])
    assert order["status"] == "submitted" and order["order_no"].startswith(f"SO/{shop.code}/")
    assert [s["role"] for s in order["approval"]["steps"]] == [
        "district_manager", "account_manager", "dispatch_manager"]
    assert order["tax_date"] == today_ist().isoformat()

    order = await _approve_all(client, shop, order)
    assert order["status"] == "approved" and order["approval"]["status"] == "approved"

    hd = await _as(client, shop, "dispatch_manager")
    sent_at = dt.datetime.now(dt.UTC).isoformat()
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()},
                          json={"dc_no": "DC-1", "dispatched_at": sent_at,
                                "lines": [{"order_line_id": line["id"], "qty": "4"}]})
    assert r.status_code == 201, r.text
    listed = (await client.get(f"{V1}/orders?q={order['order_no']}&include_total=true",
                               headers=ho)).json()
    row = next(x for x in listed["data"] if x["id"] == order["id"])
    assert (row["status"], row["dispatched_pct"]) == ("partially_dispatched", 40)
    tl = (await client.get(f"{V1}/orders/{order['id']}/timeline", headers=ho)).json()["data"]
    kinds = [e["kind"] for e in tl]
    for kind in ("order.created", "order.submitted", "approval.decided", "order.approved",
                 "dispatch.recorded"):
        assert kind in kinds, kinds
    decided = [e for e in tl if e["kind"] == "approval.decided"]
    assert any(e["payload"].get("remark") == "Payment seen" for e in decided), \
        "staff see the Accounts remark on the order's own timeline"


async def test_accounts_is_refused_a_managers_step_and_the_raiser_their_own(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await _as(client, shop, "field_officer")
    order = await _submit(client, ho, (await _create(client, ho, _direct(shop)))["id"])
    first = order["approval"]["steps"][0]
    ha = await _as(client, shop, "account_manager")
    r = await _decide(client, ha, first["id"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_your_step", r.text
    # the manager submits their own order: their level is dropped, and Accounts'
    # step is theirs to wait on
    hm = await _as(client, shop, "district_manager")
    own = await _submit(client, hm, (await _create(client, hm, _direct(shop)))["id"])
    assert [s["role"] for s in own["approval"]["steps"]] == ["account_manager", "dispatch_manager"]


async def test_a_rejection_returns_to_draft_with_its_reason_and_keeps_the_number(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await _as(client, shop, "field_officer")
    order = await _submit(client, ho, (await _create(client, ho, _direct(shop)))["id"])
    hm = await _as(client, shop, "district_manager")
    r = await _decide(client, hm, order["approval"]["steps"][0]["id"], "reject", None)
    assert r.status_code == 422 and r.json()["error"]["code"] == "remark_required"
    r = await _decide(client, hm, order["approval"]["steps"][0]["id"], "reject", "Rate too low")
    back = r.json()["data"]
    assert back["status"] == "draft" and back["last_rejection"]["remark"] == "Rate too low"
    again = await _submit(client, ho, order["id"])
    assert again["order_no"] == order["order_no"] and again["last_rejection"] is None

    # F-1: each event once, though the order now has two requests
    tl = (await client.get(f"{V1}/orders/{order['id']}/timeline", headers=ho)).json()["data"]
    assert len({e["id"] for e in tl}) == len(tl), [e["kind"] for e in tl]
    decided = [e for e in tl if e["kind"] == "approval.decided"]
    assert len(decided) == 1 and decided[0]["payload"]["remark"] == "Rate too low"
    # F-4: the first request is read as itself, not as the latest
    first = order["approval"]["request_id"]
    assert again["approval"]["request_id"] != first
    r = await client.get(f"{V1}/approvals/{first}", headers=hm)
    assert r.status_code == 200, r.text
    old = r.json()["data"]
    assert old["request_id"] == first and old["status"] == "rejected"
    assert old["steps"][0]["decision"] == "reject"
    # F-3: a cancel against a status the screen no longer shows
    r = await client.post(f"{V1}/orders/{order['id']}/cancel",
                          json={"remark": "Party withdrew", "expected_status": "draft"},
                          headers={**ho, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "status_changed", r.text


async def test_a_higher_manager_covers_the_district_step(client: httpx.AsyncClient,
                                                          shop: Shop) -> None:
    ho = await _as(client, shop, "field_officer")
    order = await _submit(client, ho, (await _create(client, ho, _direct(shop)))["id"])
    hs = await _as(client, shop, "state_manager")
    queued = (await client.get(f"{V1}/approvals/pending?include_below=true",
                               headers=hs)).json()["data"]
    assert any(q["step_id"] == order["approval"]["steps"][0]["id"] for q in queued)
    r = await _decide(client, hs, order["approval"]["steps"][0]["id"])
    step = r.json()["data"]["approval"]["steps"][0]
    assert (step["role"], step["decided_role"], step["decision"]) == (
        "district_manager", "state_manager", "approve")


# ── from quotations ──────────────────────────────────────────────────────────

async def _accepted_quotation(client: httpx.AsyncClient, shop: Shop, h: dict[str, str],
                              partner_id: str | None = None) -> dict:
    lead = (await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod"})).json()["data"]
    for stage in ("contacted", "qualified"):
        r = await client.post(f"{V1}/leads/{lead['id']}/transition", json={"to_stage": stage},
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/quotations", headers={**h, **_key()}, json={
        "lead_id": lead["id"], "sales_type": "commercial", "partner_id": partner_id,
        "place_of_supply_territory_id": shop.district, "seller_gstin_id": shop.seller,
        "price_effective_date": AS_OF,
        "lines": [{"product_id": shop.product, "qty": "20", "discount_pct": "5"}]})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    for path, body in (("send", {"channel": "none"}), ("transition", {"to": "accepted"})):
        r = await client.post(f"{V1}/quotations/{q['id']}/{path}", json=body,
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_an_order_from_an_accepted_quotation_takes_its_lines_and_holds_it(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Rules 2 and 4: the lines import, the party and lead come with them, and the
    quotation is on one live order at a time; cancelling releases it."""
    ho = await _as(client, shop, "field_officer")
    q = await _accepted_quotation(client, shop, ho)
    order = await _create(client, ho, {"quotation_ids": [q["id"]]})
    assert order["lead"]["id"] == q["lead"]["id"] and order["party"]["name"] == "Kiritbhai Shah"
    assert [x["quote_no"] for x in order["quotations"]] == [q["quote_no"]]
    assert order["lines"][0]["qty"] == "20.000"
    assert order["totals"]["taxable"] == q["totals"]["taxable"]

    r = await client.post(f"{V1}/orders", json={"quotation_ids": [q["id"]]},
                          headers={**ho, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "quotation_on_order", r.text
    r = await client.post(f"{V1}/orders", headers={**ho, **_key()},
                          json={"quotation_ids": [q["id"]], "price_effective_date": "2020-07-01"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "quotations_disagree", r.text

    r = await client.post(f"{V1}/orders/{order['id']}/cancel", json={"remark": "Wrong lead"},
                          headers={**ho, **_key()})
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled", r.text
    again = await _create(client, ho, {"quotation_ids": [q["id"]]})
    assert again["id"] != order["id"]


async def test_the_order_list_finds_the_orders_a_quotation_is_on(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """BE-019: every order the quotation was on, the cancelled one included; `status`
    narrows it to the live one. Another quotation's order is not among them."""
    ho = await _as(client, shop, "field_officer")
    q = await _accepted_quotation(client, shop, ho)
    other = await _accepted_quotation(client, shop, ho)
    first = await _create(client, ho, {"quotation_ids": [q["id"]]})
    elsewhere = await _create(client, ho, {"quotation_ids": [other["id"]]})
    r = await client.post(f"{V1}/orders/{first['id']}/cancel", json={"remark": "Wrong lead"},
                          headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    live = await _create(client, ho, {"quotation_ids": [q["id"]]})

    async def ids(**params: str) -> set[str]:
        r = await client.get(f"{V1}/orders", headers=ho, params={"quotation_id": q["id"], **params})
        assert r.status_code == 200, r.text
        return {o["id"] for o in r.json()["data"]}
    assert await ids() == {first["id"], live["id"]}
    assert elsewhere["id"] not in await ids()
    assert await ids(status="draft") == {live["id"]}
    r = await client.get(f"{V1}/orders", headers=ho, params={"quotation_id": str(uuid.uuid4())})
    assert r.status_code == 200 and r.json()["data"] == []
    r = await client.get(f"{V1}/orders", headers=ho, params={"quotation_id": "not-a-uuid"})
    assert r.status_code == 422, r.text


# ── dispatch, void, close ────────────────────────────────────────────────────

async def test_dispatch_refuses_what_cannot_ship_and_closes_the_balance_short(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await _as(client, shop, "field_officer")
    order = await _approve_all(client, shop, await _submit(
        client, ho, (await _create(client, ho, _direct(shop)))["id"]))
    line = order["lines"][0]["id"]
    hd = await _as(client, shop, "dispatch_manager")
    now = dt.datetime.now(dt.UTC)
    url = f"{V1}/orders/{order['id']}/dispatches"
    cases = [
        ({"dispatched_at": now.isoformat(), "lines": []}, "no_lines"),
        ({"dispatched_at": now.isoformat(), "lines": [{"order_line_id": line, "qty": "1"},
                                                     {"order_line_id": line, "qty": "1"}]},
         "duplicate_line"),
        ({"dispatched_at": now.isoformat(), "lines": [{"order_line_id": line, "qty": "11"}]},
         "over_open_quantity"),
        ({"dispatched_at": now.isoformat(), "lines": [{"order_line_id": line, "qty": "1.5"}]},
         "unit_precision"),
    ]
    for body, code in cases:
        r = await client.post(url, json=body, headers={**hd, **_key()})
        assert r.status_code == 422 and r.json()["error"]["code"] == code, (code, r.text)
    future = (now + dt.timedelta(days=3)).isoformat()
    r = await client.post(url, headers={**hd, **_key()},
                          json={"dispatched_at": future, "lines": [{"order_line_id": line, "qty": "1"}]})
    assert r.status_code == 422, r.text

    r = await client.post(url, headers={**hd, **_key()}, json={
        "dispatched_at": now.isoformat(), "invoice_no": "INV-1", "invoice_date": "2026-01-01",
        "dc_date": "2026-01-05", "lines": [{"order_line_id": line, "qty": "3"}]})
    assert r.status_code == 201, r.text
    assert any(w.startswith("invoice_before_dc") for w in r.json()["data"]["warnings"])
    first = r.json()["data"]["id"]
    r = await client.post(f"{V1}/dispatches/{first}/void", json={"remark": "Wrong DC"},
                          headers={**hd, **_key()})
    assert r.status_code == 200 and r.json()["data"]["status"] == "approved", r.text
    r = await client.post(f"{V1}/orders/{order['id']}/close-short", json={"remark": "Stopped"},
                          headers={**hd, **_key()})
    closed = r.json()["data"]
    assert closed["status"] == "closed_short" and closed["lines"][0]["qty_short"] == "10.000"
    r = await client.post(f"{V1}/dispatches/{first}/void", json={"remark": "again"},
                          headers={**hd, **_key()})
    assert r.status_code == 409, r.text


# ── the rest of the contract ─────────────────────────────────────────────────

async def test_cancel_and_delete_follow_the_state_table(client: httpx.AsyncClient,
                                                        shop: Shop) -> None:
    ho = await _as(client, shop, "field_officer")
    order = await _approve_all(client, shop, await _submit(
        client, ho, (await _create(client, ho, _direct(shop)))["id"]))
    r = await client.post(f"{V1}/orders/{order['id']}/cancel", json={"remark": "x"},
                          headers={**ho, **_key()})
    assert r.status_code == 403, r.text
    hs = await _as(client, shop, "state_manager")
    r = await client.post(f"{V1}/orders/{order['id']}/cancel",
                          json={"remark": "Plant shut", "expected_status": "approved"},
                          headers={**hs, **_key()})
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled", r.text
    rejected = await _submit(client, ho, (await _create(client, ho, _direct(shop)))["id"])
    hm = await _as(client, shop, "district_manager")
    await _decide(client, hm, rejected["approval"]["steps"][0]["id"], "reject", "No")
    r = await client.request("DELETE", f"{V1}/orders/{rejected['id']}", headers={**hs, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "order_was_submitted", r.text


async def test_a_zero_total_and_an_unbuilt_type_are_refused(client: httpx.AsyncClient,
                                                            shop: Shop) -> None:
    ho = await _as(client, shop, "field_officer")
    r = await client.post(f"{V1}/orders", json=_direct(shop, order_type="export"),
                          headers={**ho, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "order_type_unsupported"
    free = _direct(shop)
    free["lines"] = [{"product_id": shop.product, "qty": "1", "discount_pct": "100"}]
    order = await _create(client, ho, free)
    r = await client.post(f"{V1}/orders/{order['id']}/submit", json={}, headers={**ho, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "zero_total", r.text
    assert (await client.get(f"{V1}/orders?owner=kiran", headers=ho)).status_code == 422


async def test_thresholds_must_rise_with_the_level(client: httpx.AsyncClient, shop: Shop) -> None:
    ha = await _as(client, shop, "admin_sales")
    listed = (await client.get(f"{V1}/approvals/thresholds", headers=ha)).json()["data"]
    assert {t["role"] for t in listed} >= {"district_manager", "state_manager"}
    r = await client.put(f"{V1}/approvals/thresholds", headers={**ha, **_key()}, json={
        "role": "district_manager", "territory_id": shop.state, "max_amount": "900000"})
    assert r.status_code == 200, r.text
    r = await client.put(f"{V1}/approvals/thresholds", headers={**ha, **_key()}, json={
        "role": "state_manager", "territory_id": shop.state, "max_amount": "50000"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "thresholds_not_increasing"


async def test_the_order_list_takes_several_statuses(client: httpx.AsyncClient, shop: Shop) -> None:
    """API review: "open orders" in one call."""
    ho = await _as(client, shop, "field_officer")
    draft = await _create(client, ho, _direct(shop))
    submitted = await _submit(client, ho, (await _create(client, ho, _direct(shop)))["id"])

    async def ids(status: str) -> set[str]:
        r = await client.get(f"{V1}/orders", headers=ho, params={"status": status, "limit": 100})
        assert r.status_code == 200, r.text
        return {x["id"] for x in r.json()["data"]} & {draft["id"], submitted["id"]}

    assert await ids("draft,submitted") == {draft["id"], submitted["id"]}
    assert await ids("draft") == {draft["id"]}
    assert await ids("approved,cancelled") == set()


async def test_the_order_counts_and_the_inbox_badge(client: httpx.AsyncClient, shop: Shop) -> None:
    """API review B2: the board's counts under the list's scope, the submitted
    orders by whose step is next, and the approver's badge."""
    ho = await _as(client, shop, "field_officer")
    await _create(client, ho, _direct(shop))
    await _submit(client, ho, (await _create(client, ho, _direct(shop)))["id"])
    r = await client.get(f"{V1}/orders/stats", headers=ho)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["total"] == 2 and got["by_status"]["draft"] == 1 and got["by_status"]["submitted"] == 1
    assert got["by_status"]["cancelled"] == 0
    assert got["waiting_on"] == {"district_manager": 1}
    hm = await _as(client, shop, "district_manager")
    q = (await client.get(f"{V1}/approvals/pending", headers=hm,
                          params={"include_total": "true", "limit": 1})).json()
    # the manager's area is this shop's one office, so the badge is exact
    assert q["meta"]["total"] == 1 and q["meta"]["total_capped"] is False
    assert len(q["data"]) == 1


# ── the order PDF (FS-012) ───────────────────────────────────────────────────

async def test_the_order_pdf_follows_approval_and_is_withdrawn_on_cancel(
        client: httpx.AsyncClient, shop: Shop, tmp_path: pathlib.Path) -> None:
    ho = await _as(client, shop, "field_officer")
    draft = await _create(client, ho, _direct(shop, remarks="Internal: rate agreed below list"))
    assert draft["pdf_state"] == "none"
    r = await client.get(f"{V1}/orders/{draft['id']}/pdf", headers=ho)
    assert r.status_code == 404, "no PDF before approval"

    order = await _approve_all(client, shop, await _submit(client, ho, draft["id"]))
    assert order["pdf_state"] == "pending"
    r = await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho)
    assert r.status_code == 409 and r.json()["error"]["code"] == "pdf_pending"

    settings = get_settings().model_copy(update={"pdf_renderer": "html"})
    storage = LocalStorage(root=tmp_path, secret=b"test", public_base="")
    for _ in range(5):          # another pending order may be claimed first
        if await render_order(settings, storage) is None:
            break
    got = (await client.get(f"{V1}/orders/{order['id']}", headers=ho)).json()["data"]
    assert got["pdf_state"] == "ready", got["pdf_state"]
    link = (await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho)).json()["data"]
    assert link["filename"] == order["order_no"].replace("/", "-") + ".pdf"
    assert "/public/files/" in link["url"]
    files = list(tmp_path.rglob(f"orders/{order['id']}/*.pdf"))
    assert len(files) == 1
    body = files[0].read_bytes()
    assert order["order_no"].encode() in body and b"Rameshbhai Patel" in body
    # rule 9: the order's own remark is internal (code review F-6: the approvers'
    # remarks never reach the claim, so only this one can leak)
    assert b"rate agreed below list" not in body

    hs = await _as(client, shop, "state_manager")
    r = await client.post(f"{V1}/orders/{order['id']}/cancel",
                          json={"remark": "Plant shut", "expected_status": "approved"},
                          headers={**hs, **_key()})
    assert r.status_code == 200, r.text
    r = await client.get(f"{V1}/orders/{order['id']}/pdf", headers=ho)
    assert r.status_code == 409 and r.json()["error"]["code"] == "order_cancelled"
