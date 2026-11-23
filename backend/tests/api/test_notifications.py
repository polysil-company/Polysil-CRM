"""FS-018 over the API: each event notifies the right person and not the actor; the
bell's list, unread count and mark-read; nobody reads another's."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_complaints as cmp
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _bell(client: httpx.AsyncClient, h: dict[str, str], **params: str) -> dict:
    r = await client.get(f"{V1}/notifications", headers=h, params=params)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _about(page: dict, resource_id: str) -> list[dict]:
    return [n for n in page["data"] if (n["resource"] or {}).get("id") == resource_id]


async def _lead(client: httpx.AsyncClient, shop: Shop, h: dict[str, str]) -> dict:
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Notify Farmer", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip"})
    assert r.status_code == 201, r.text
    return dict(r.json()["data"])


async def test_an_assigned_lead_a_note_and_a_task_notify_their_person(client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    fo = await endpoints._as(client, shop, "field_officer")
    lead = await _lead(client, shop, dm)
    r = await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**dm, **_key()},
                          json={"owner_user_id": shop.ids["field_officer"]})
    assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/leads/{lead['id']}/notes", headers={**dm, **_key()}, json={"note": "Call before noon"})
    assert r.status_code in (200, 201), r.text
    r = await client.post(f"{V1}/tasks", headers={**dm, **_key()}, json={
        "title": "Visit the farm", "task_type": "visit", "due_at": "2027-01-15",
        "assigned_to": shop.ids["field_officer"], "lead_id": lead["id"]})
    assert r.status_code == 201, r.text
    task = r.json()["data"]
    mine = await _bell(client, fo)
    kinds = sorted(n["kind"] for n in _about(mine, lead["id"]))
    assert kinds == ["lead_assigned", "lead_note"], kinds
    (t,) = _about(mine, task["id"])
    assert t["kind"] == "task_assigned" and t["body"] == "Visit the farm"
    assert t["actor"]["id"] == shop.ids["district_manager"] and t["actor"]["full_name"]
    assert _about(await _bell(client, dm), lead["id"]) == [], "nobody is told of their own action"


async def test_an_order_step_notifies_its_approver_and_a_reject_does_not_move_on(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Review B-1: a reject used to notify the next step's role."""
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._submit(client, fo, (await endpoints._create(client, fo, endpoints._direct(shop)))["id"])
    dm = await endpoints._as(client, shop, "district_manager")
    (waiting,) = _about(await _bell(client, dm), order["id"])
    assert waiting["kind"] == "approval_requested" and order["order_no"] in waiting["title"]
    sm = await endpoints._as(client, shop, "state_manager")
    assert _about(await _bell(client, sm), order["id"]) == [], "the step is the district manager's"
    r = await endpoints._decide(client, dm, order["approval"]["steps"][0]["id"], "reject", "Rate too low")
    assert r.status_code == 200, r.text
    accounts = await endpoints._as(client, shop, "account_manager")
    assert _about(await _bell(client, accounts), order["id"]) == [], "a reject moves nothing on"
    (back,) = _about(await _bell(client, fo), order["id"])
    assert back["kind"] == "order_returned" and back["actor"]["id"] == shop.ids["district_manager"]


async def test_an_approve_moves_the_notification_to_the_next_step(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._submit(client, fo, (await endpoints._create(client, fo, endpoints._direct(shop)))["id"])
    dm = await endpoints._as(client, shop, "district_manager")
    assert (await endpoints._decide(client, dm, order["approval"]["steps"][0]["id"])).status_code == 200
    accounts = await endpoints._as(client, shop, "account_manager")
    (waiting,) = _about(await _bell(client, accounts), order["id"])
    assert waiting["kind"] == "approval_requested"


async def test_a_complaint_goes_to_its_checker_then_qc_then_back(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    c = await cmp._create(client, shop, fo)
    assert (await cmp._post(client, fo, f"/{c['id']}/submit")).status_code == 200
    dm = await endpoints._as(client, shop, "district_manager")
    sm = await endpoints._as(client, shop, "state_manager")
    assert [n["kind"] for n in _about(await _bell(client, dm), c["id"])] == ["complaint_to_check"]
    assert _about(await _bell(client, sm), c["id"]) == [], "the lowest level that may check"
    r = await cmp._post(client, dm, f"/{c['id']}/check", {"decision": "approve", "remark": "Genuine"})
    assert r.status_code == 200, r.text
    qc = await endpoints._as(client, shop, "qc_manager")
    assert [n["kind"] for n in _about(await _bell(client, qc), c["id"])] == ["complaint_to_qc"]
    r = await cmp._post(client, qc, f"/{c['id']}/qc", {"verdict": "approved", "remark": "Manufacturing defect",
                                                       "sample_received_on": "2026-07-20", "tested_on": "2026-07-22"})
    assert r.status_code == 200, r.text
    assert "complaint_qc_approved" in [n["kind"] for n in _about(await _bell(client, fo), c["id"])]


async def test_the_bell_counts_pages_and_marks_read(client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    fo = await endpoints._as(client, shop, "field_officer")
    for _ in range(3):
        lead = await _lead(client, shop, dm)
        await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**dm, **_key()},
                          json={"owner_user_id": shop.ids["field_officer"]})
    first = await _bell(client, fo, limit="2")
    unread = first["meta"]["unread_count"]
    assert unread >= 3 and len(first["data"]) == 2 and first["meta"]["next_cursor"]
    second = await _bell(client, fo, limit="2", cursor=first["meta"]["next_cursor"])
    # a real second page, strictly older than the first (code review F-2)
    assert second["data"], "the cursor led somewhere"
    assert not {n["id"] for n in first["data"]} & {n["id"] for n in second["data"]}
    last = (first["data"][-1]["created_at"], first["data"][-1]["id"])
    assert all((n["created_at"], n["id"]) < last for n in second["data"])
    one = first["data"][0]["id"]
    r = await client.post(f"{V1}/notifications/read", headers={**fo, **_key()}, json={"ids": [one]})
    assert r.status_code == 200 and r.json()["data"]["unread_count"] == unread - 1, r.text
    r = await client.post(f"{V1}/notifications/read", headers={**dm, **_key()}, json={"all": True})
    assert (await _bell(client, fo))["meta"]["unread_count"] == unread - 1, "another's mark-all touches nothing of mine"
    r = await client.post(f"{V1}/notifications/read", headers={**dm, **_key()}, json={"ids": [first["data"][1]["id"]]})
    assert (await _bell(client, fo))["meta"]["unread_count"] == unread - 1, "nor do my ids in another's hands"
    r = await client.post(f"{V1}/notifications/read", headers={**fo, **_key()}, json={"all": True})
    assert r.json()["data"]["unread_count"] == 0
    assert (await _bell(client, fo, unread="true"))["data"] == []


@pytest.mark.parametrize("body", [{}, {"ids": [], "all": True}, {"ids": ["x"]}, {"all": False}])
async def test_mark_read_takes_ids_or_all(client: httpx.AsyncClient, shop: Shop, body: dict) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/notifications/read", headers={**fo, **_key()}, json=body)
    assert r.status_code == 422, r.text


async def test_a_notification_fault_never_blocks_the_write(client: httpx.AsyncClient, shop: Shop,
                                                          sessions: Sessions) -> None:
    """Review B-3: a bad payload is logged, the event row stays."""
    # The bad uuid is cast inside the order arm's WHERE clause, which PostgreSQL
    # never evaluates against an empty approval_step. A pending step makes the
    # fault certain whatever ran before (it went green or red with test order).
    h = await endpoints._as(client, shop, "field_officer")
    await endpoints._submit(client, h, (await endpoints._create(client, h, endpoints._direct(shop)))["id"])
    s = sessions()
    try:
        eid = str((await s.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload) "
            "VALUES ('sales_order', gen_random_uuid(), 'order.submitted', CAST(:a AS uuid), "
            "'{\"request\": \"not-a-uuid\"}'::jsonb) RETURNING id"), {"a": shop.ids["field_officer"]})).scalar_one())
        failed = (await s.execute(text("SELECT sqlstate FROM notification_failure WHERE event_id = CAST(:e AS uuid)"),
                                  {"e": eid})).scalars().all()
        assert failed == ["22P02"], failed
    finally:
        await s.rollback()
        await s.close()



# ── code review F-3: the trigger's own paths to a dealer and to a discount ───

async def test_a_dealer_is_told_of_a_return_but_not_by_whom(client: httpx.AsyncClient, shop: Shop,
                                                            sessions: Sessions) -> None:
    """Question 15.14 through the trigger, not only through notify_one."""
    dm = await endpoints._as(client, shop, "district_manager")
    dealer, mobile = await cmp._dealer(client, shop, sessions)
    try:
        type_id = (await client.get(f"{V1}/lookups/complaint-types", headers=dealer)).json()["data"][0]["id"]
        r = await client.post(f"{V1}/complaints", headers={**dealer, **_key()}, json=cmp._body(shop, type_id))
        assert r.status_code == 201, r.text
        c = r.json()["data"]
        assert (await cmp._post(client, dealer, f"/{c['id']}/submit")).status_code == 200
        r = await cmp._post(client, dm, f"/{c['id']}/check", {"decision": "return", "remark": "Add the challan photo"})
        assert r.status_code == 200, r.text
        (back,) = [n for n in _about(await _bell(client, dealer), c["id"]) if n["kind"] == "complaint_returned"]
        assert back["actor"] is None, back
        assert "Asha" not in back["title"] and "Patel" not in back["title"]
    finally:
        await cmp._forget(sessions, mobile)


async def test_a_discount_request_reaches_its_approver_and_the_answer_comes_back(
        client: httpx.AsyncClient, shop: Shop) -> None:
    from tests.api import test_quotation_approval as qa
    fo = await endpoints._as(client, shop, "field_officer")
    q = await qa._draft(client, shop, fo, "8")
    assert (await qa._ask(client, fo, q["id"])).status_code == 200
    dm = await endpoints._as(client, shop, "district_manager")
    (waiting,) = _about(await _bell(client, dm), q["id"])
    assert waiting["kind"] == "approval_requested" and waiting["resource"]["type"] == "quotation"
    pending = (await client.get(f"{V1}/approvals/pending", headers=dm)).json()["data"]
    step = next(p for p in pending if p["document"]["id"] == q["id"])
    r = await endpoints._decide(client, dm, step["step_id"], "reject", "Too deep")
    assert r.status_code == 200, r.text
    kinds = [n["kind"] for n in _about(await _bell(client, fo), q["id"])]
    assert "discount_returned" in kinds, kinds


# ── ISS-108: a decided step clears its bell, and says what was decided ──────

def _unread(page: dict, resource_id: str) -> list[dict]:
    return [n for n in _about(page, resource_id) if n["read_at"] is None]


async def test_an_approve_clears_the_deciders_bell_and_the_next_step_stays_unread(
        client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._submit(client, fo, (await endpoints._create(client, fo, endpoints._direct(shop)))["id"])
    dm = await endpoints._as(client, shop, "district_manager")
    assert len(_unread(await _bell(client, dm), order["id"])) == 1
    assert (await endpoints._decide(client, dm, order["approval"]["steps"][0]["id"])).status_code == 200
    (done,) = _about(await _bell(client, dm), order["id"])
    assert done["read_at"] is not None, "the decided step no longer waits"
    accounts = await endpoints._as(client, shop, "account_manager")
    (waiting,) = _about(await _bell(client, accounts), order["id"])
    assert waiting["read_at"] is None, "settling ran before the next step was told"


async def test_a_rejected_order_clears_the_bell_and_reads_not_approved(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._submit(client, fo, (await endpoints._create(client, fo, endpoints._direct(shop)))["id"])
    dm = await endpoints._as(client, shop, "district_manager")
    r = await endpoints._decide(client, dm, order["approval"]["steps"][0]["id"], "reject", "Rate too low")
    assert r.status_code == 200, r.text
    assert _unread(await _bell(client, dm), order["id"]) == []
    (back,) = _about(await _bell(client, fo), order["id"])
    assert back["kind"] == "order_returned", "the kind code is unchanged for the frontend"
    assert back["title"].endswith(" was not approved"), back["title"]


async def test_a_cancelled_order_clears_its_approvers_bell(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    order = await endpoints._submit(client, fo, (await endpoints._create(client, fo, endpoints._direct(shop)))["id"])
    dm = await endpoints._as(client, shop, "district_manager")
    assert len(_unread(await _bell(client, dm), order["id"])) == 1
    r = await client.post(f"{V1}/orders/{order['id']}/cancel", json={"remark": "Wrong lead"}, headers={**fo, **_key()})
    assert r.status_code == 200, r.text
    assert _unread(await _bell(client, dm), order["id"]) == [], "nobody is waited on after a cancel"


async def test_a_discount_names_its_percent_and_an_edit_clears_the_request(
        client: httpx.AsyncClient, shop: Shop) -> None:
    from tests.api import test_quotation_approval as qa
    fo = await endpoints._as(client, shop, "field_officer")
    dm = await endpoints._as(client, shop, "district_manager")
    q = await qa._draft(client, shop, fo, "8")
    assert (await qa._ask(client, fo, q["id"])).status_code == 200
    (waiting,) = _about(await _bell(client, dm), q["id"])
    assert waiting["title"].startswith("Discount of 8% on "), waiting["title"]
    lines = [{"product_id": shop.product, "qty": "25", "discount_pct": "8"}]
    r = await client.put(f"{V1}/quotations/{q['id']}/lines", json={"lines": lines}, headers={**fo, **_key()})
    assert r.status_code == 200 and r.json()["data"]["approval"]["status"] == "cancelled", r.text
    assert _unread(await _bell(client, dm), q["id"]) == [], "an edit cancelled the request"


async def test_a_rejected_discount_reads_not_approved_with_its_percent(client: httpx.AsyncClient, shop: Shop) -> None:
    from tests.api import test_quotation_approval as qa
    fo = await endpoints._as(client, shop, "field_officer")
    q = await qa._draft(client, shop, fo, "12.5")
    step = (await qa._ask(client, fo, q["id"])).json()["data"]["approval"]["steps"][0]
    decider = await endpoints._as(client, shop, step["role"])
    r = await endpoints._decide(client, decider, step["id"], "reject", "Too deep")
    assert r.status_code == 200, r.text
    assert _unread(await _bell(client, decider), q["id"]) == []
    (back,) = [n for n in _about(await _bell(client, fo), q["id"]) if n["kind"] == "discount_returned"]
    assert back["title"].startswith("Discount of 12.5% on ") and back["title"].endswith(" was not approved"), back["title"]
