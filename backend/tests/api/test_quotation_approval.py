"""FS-013 over the API: a discount above the owner's limit is sent only once a
manager approves it; an edit voids the approval; the approver's inbox shows the
quotation; a dealer sees the chain without names or remarks.

The world is the order tests' shop (real roles, the stand-in limits: officer 5 %,
District Manager 10 %, State Manager 15 %)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.session import enter_role
from api.schemas import orders as osch
from api.schemas import quotations as qsch
from api.services import approvals as approval_service
from api.services import quotations as quotation_service
from tests.api import test_order_concurrency as conc
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key, _login

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _draft(client: httpx.AsyncClient, shop: Shop, h: dict[str, str], pct: str,
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
        "price_effective_date": endpoints.AS_OF,
        "lines": [{"product_id": shop.product, "qty": "20", "discount_pct": pct}]})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _send(client: httpx.AsyncClient, h: dict[str, str], qid: str) -> httpx.Response:
    return await client.post(f"{V1}/quotations/{qid}/send", json={"channel": "none"},
                             headers={**h, **_key()})


async def _ask(client: httpx.AsyncClient, h: dict[str, str], qid: str) -> httpx.Response:
    return await client.post(f"{V1}/quotations/{qid}/request-approval",
                             json={"remark": "Season order"}, headers={**h, **_key()})


async def test_a_deep_discount_is_sent_only_after_a_manager_approves_it(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    q = await _draft(client, shop, ho, "12")
    assert q["discount"] == {"effective_pct": "12.00", "owner_limit_pct": "5.00",
                             "approval_required": True, "send_gate": "required"}
    assert q["approval"] is None

    r = await _send(client, ho, q["id"])
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "discount_approval_required"

    r = await _ask(client, ho, q["id"])
    assert r.status_code == 200, r.text
    asked = r.json()["data"]
    assert asked["status"] == "draft" and asked["discount"]["send_gate"] == "pending"
    assert [s["role"] for s in asked["approval"]["steps"]] == ["state_manager"]
    r = await _send(client, ho, q["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_pending", r.text
    r = await _ask(client, ho, q["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_pending", r.text

    hs = await endpoints._as(client, shop, "state_manager")
    inbox = (await client.get(f"{V1}/approvals/pending", headers=hs)).json()["data"]
    row = next(x for x in inbox if x["document"]["id"] == q["id"])
    assert (row["doc_type"], row["document"]["number"], row["document"]["discount_pct"]) == \
        ("quotation", None, "12.00")
    r = await client.post(f"{V1}/approvals/steps/{row['step_id']}/decision",
                          json={"decision": "approve", "remark": "Season rate"},
                          headers={**hs, **_key()})
    assert r.status_code == 200, r.text
    decided = r.json()["data"]
    assert decided["id"] == q["id"] and decided["discount"]["send_gate"] == "approved"

    r = await _send(client, ho, q["id"])
    assert r.status_code == 200 and r.json()["data"]["status"] == "sent", r.text
    timeline = [e["kind"] for e in (await client.get(
        f"{V1}/quotations/{q['id']}/timeline", headers=ho)).json()["data"]]
    assert {"quotation.approval_requested", "quotation.approval_approved"} <= set(timeline)


async def test_within_the_limit_nothing_is_asked_and_the_send_goes_through(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    q = await _draft(client, shop, ho, "5")
    assert q["discount"]["send_gate"] == "none_needed"
    r = await _ask(client, ho, q["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_not_required", r.text
    assert (await _send(client, ho, q["id"])).status_code == 200


async def test_an_edit_after_approval_voids_it_and_an_edit_while_pending_cancels_it(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    hm = await endpoints._as(client, shop, "district_manager")
    q = await _draft(client, shop, ho, "8")
    asked = (await _ask(client, ho, q["id"])).json()["data"]
    step = asked["approval"]["steps"][0]
    assert step["role"] == "district_manager"
    r = await client.post(f"{V1}/approvals/steps/{step['id']}/decision",
                          json={"decision": "approve", "remark": "ok"}, headers={**hm, **_key()})
    assert r.status_code == 200, r.text

    lines = [{"product_id": shop.product, "qty": "25", "discount_pct": "8"}]
    r = await client.put(f"{V1}/quotations/{q['id']}/lines", json={"lines": lines},
                         headers={**ho, **_key()})
    assert r.status_code == 200 and r.json()["data"]["discount"]["send_gate"] == "void", r.text
    r = await _send(client, ho, q["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "discount_approval_required"

    asked = (await _ask(client, ho, q["id"])).json()["data"]
    pending_step = asked["approval"]["steps"][0]["id"]
    lines[0]["qty"] = "30"
    r = await client.put(f"{V1}/quotations/{q['id']}/lines", json={"lines": lines},
                         headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    edited = r.json()["data"]
    gate, status = edited["discount"]["send_gate"], edited["approval"]["status"]
    assert (gate, status) == ("required", "cancelled")
    r = await client.post(f"{V1}/approvals/steps/{pending_step}/decision",
                          json={"decision": "approve", "remark": "ok"}, headers={**hm, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "request_closed", r.text


async def test_the_owner_cannot_approve_and_a_return_needs_a_new_request(
        client: httpx.AsyncClient, shop: Shop) -> None:
    hm = await endpoints._as(client, shop, "district_manager")
    q = await _draft(client, shop, hm, "12")            # the District Manager's own draft
    asked = (await _ask(client, hm, q["id"])).json()["data"]
    step = asked["approval"]["steps"][0]
    assert step["role"] == "state_manager", "above the owner's own level"
    hs = await endpoints._as(client, shop, "state_manager")
    r = await client.post(f"{V1}/approvals/steps/{step['id']}/decision",
                          json={"decision": "reject", "remark": "Too deep for this crop"},
                          headers={**hs, **_key()})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["discount"]["send_gate"] == "returned"
    r = await _send(client, hm, q["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "discount_approval_required"


async def test_a_dealer_sees_the_chain_without_names_or_remarks(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    q = await _draft(client, shop, ho, "12", partner_id=shop.partner)
    step = (await _ask(client, ho, q["id"])).json()["data"]["approval"]["steps"][0]
    hs = await endpoints._as(client, shop, "state_manager")
    r = await client.post(f"{V1}/approvals/steps/{step['id']}/decision",
                          json={"decision": "approve", "remark": "Internal: dealer margin thin"},
                          headers={**hs, **_key()})
    assert r.status_code == 200, r.text
    staff_view = r.json()["data"]["approval"]["steps"][0]
    assert staff_view["by"] is not None and staff_view["remark"] == "Internal: dealer margin thin"

    s = sessions()
    try:
        await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                        {"u": shop.ids["dealer"]})
        await enter_role(s, "app_role")
        seen = await quotation_service.get_quotation(s, q["id"], get_settings(), portal=True)
    finally:
        await s.rollback()
        await s.close()
    assert seen.approval is not None and seen.approval.status == "approved"
    assert seen.approval.steps[0].by is None and seen.approval.steps[0].remark is None
    assert seen.discount is None, "a dealer does not learn the officer's discount limit"


# ── OCR review of FS-013 ─────────────────────────────────────────────────────

async def test_the_inbox_names_who_asked_not_who_drafted(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    hm = await endpoints._as(client, shop, "district_manager")
    q = await _draft(client, shop, ho, "12")
    assert (await _ask(client, hm, q["id"])).status_code == 200
    hs = await endpoints._as(client, shop, "state_manager")
    inbox = (await client.get(f"{V1}/approvals/pending", headers=hs)).json()["data"]
    row = next(x for x in inbox if x["document"]["id"] == q["id"])
    assert row["document"]["raised_by"]["id"] == shop.ids["district_manager"]


async def test_nobody_covers_it_answers_no_approver(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """EC-3 over HTTP: the frontend reads 422 no_approver, not a 500."""
    s = sessions()
    await s.execute(text(
        "INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount) "
        "SELECT 'quotation', r.id, CAST(:t AS uuid), 30 FROM role r WHERE r.code = 'admin_sales'"),
        {"t": shop.state})
    await s.commit()
    await s.close()
    ho = await endpoints._as(client, shop, "field_officer")
    q = await _draft(client, shop, ho, "40")
    r = await _ask(client, ho, q["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_approver", r.text


async def test_below_the_top_a_quotation_limit_cannot_be_none(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """A null limit for an officer would switch the gate off for them."""
    ha = await endpoints._as(client, shop, "admin_sales")
    for role, amount, ok in (("field_officer", None, False), ("district_manager", "101", False),
                             ("admin_sales", None, True)):
        r = await client.put(f"{V1}/approvals/thresholds", headers={**ha, **_key()}, json={
            "doc_type": "quotation", "role": role, "territory_id": shop.state,
            "max_amount": amount})
        assert (r.status_code == 200) is ok, (role, amount, r.text)


async def test_a_role_holding_only_quotations_approve_reaches_the_inbox(
        client: httpx.AsyncClient, staff: Any, sessions: Sessions) -> None:
    s = sessions()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) "
        "VALUES (CAST(:r AS uuid), 'quotations', 'view', 'org_subtree'), "
        "(CAST(:r AS uuid), 'quotations', 'approve', 'org_subtree')"), {"r": staff.role_id})
    await s.commit()
    await s.close()
    h = await _login(client, staff.email, staff.password)
    r = await client.get(f"{V1}/approvals/pending", headers=h)
    assert r.status_code == 200, r.text
    # and opens an approval (code review): either view permission
    r = await client.get(f"{V1}/approvals/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404, r.text


async def _gate(sessions: Sessions, shop: Shop, qid: str) -> str:
    s = sessions()
    try:
        await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                        {"u": shop.ids["field_officer"]})
        await enter_role(s, "app_role")
        return str((await s.execute(text("SELECT quotation_send_gate(CAST(:q AS uuid))"),
                                    {"q": qid})).scalar_one())
    finally:
        await s.rollback()
        await s.close()


def _edit(shop: Shop, qid: str) -> Any:
    body = qsch.LinesReplace.model_validate(
        {"lines": [{"product_id": shop.product, "qty": "30", "discount_pct": "12"}]})

    async def work(s: AsyncSession) -> Any:
        return await quotation_service.replace_lines(
            s, conc._caller(shop, "field_officer"), qid, body, get_settings())
    return work


def _approve(shop: Shop, step_id: str) -> Any:
    async def work(s: AsyncSession) -> Any:
        return await approval_service.decide(
            s, conc._caller(shop, "state_manager"), step_id,
            osch.DecisionRequest(decision="approve", remark="Season rate"))
    return work


async def test_an_edit_that_wins_the_race_leaves_the_approver_too_late(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Spec 10, concurrency: the decision waits on the edit (the lead, then the
    quotation), then finds the request cancelled. Never an approval of figures the
    approver did not see. This proves the wait and the outcome, not which row the
    wait was on."""
    ho = await endpoints._as(client, shop, "field_officer")
    q = await _draft(client, shop, ho, "12")
    step = (await _ask(client, ho, q["id"])).json()["data"]["approval"]["steps"][0]
    got, waited = await conc._race(
        sessions, (shop.ids["field_officer"], _edit(shop, q["id"])),
        (shop.ids["state_manager"], _approve(shop, step["id"])))
    assert waited, "the decision did not wait on the edit"
    assert [conc._outcome(g) for g in got] == ["ok", "request_closed"], got
    assert await _gate(sessions, shop, q["id"]) == "required"


async def test_an_approval_that_wins_the_race_is_voided_by_the_edit(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    q = await _draft(client, shop, ho, "12")
    step = (await _ask(client, ho, q["id"])).json()["data"]["approval"]["steps"][0]
    got, waited = await conc._race(
        sessions, (shop.ids["state_manager"], _approve(shop, step["id"])),
        (shop.ids["field_officer"], _edit(shop, q["id"])))
    assert waited, "the edit did not wait on the decision"
    assert [conc._outcome(g) for g in got] == ["ok", "ok"], got
    assert await _gate(sessions, shop, q["id"]) == "void", "approved, then the figures moved"


async def test_over_http_a_dealer_sees_neither_names_remarks_nor_the_limit(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """OCR review: the router derives `portal` from the caller; this goes through it."""
    ho = await endpoints._as(client, shop, "field_officer")
    q = await _draft(client, shop, ho, "12", partner_id=shop.partner)
    step = (await _ask(client, ho, q["id"])).json()["data"]["approval"]["steps"][0]
    hs = await endpoints._as(client, shop, "state_manager")
    assert (await client.post(f"{V1}/approvals/steps/{step['id']}/decision",
                              json={"decision": "approve", "remark": "Internal: margin thin"},
                              headers={**hs, **_key()})).status_code == 200
    s = sessions()
    mobile = str((await s.execute(text("SELECT mobile FROM app_user WHERE id = CAST(:u AS uuid)"),
                                  {"u": shop.ids["dealer"]})).scalar_one())
    # the dealer's lead too, so its timeline is the dealer's to read
    await s.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) "
                         "WHERE id = CAST(:l AS uuid)"), {"p": shop.partner, "l": q["lead"]["id"]})
    await s.commit()
    await s.close()
    e164 = mobile if mobile.startswith("+") else "+" + mobile
    try:
        # the sign-in path keys the outbox on the stored form (tests/api/test_auth_endpoints.py)
        await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
        c = sessions()
        code = (await c.execute(text(
            "SELECT payload ->> 'code' FROM notification_outbox WHERE recipient = :m "
            "ORDER BY created_at DESC LIMIT 1"), {"m": mobile})).scalar_one()
        await c.close()
        r = await client.post(f"{V1}/auth/otp/verify", json={"mobile": mobile, "code": code})
        assert r.status_code == 200, r.text
        hd = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
        seen = (await client.get(f"{V1}/quotations/{q['id']}", headers=hd)).json()["data"]
        assert seen["approval"]["status"] == "approved"
        assert seen["approval"]["steps"][0]["by"] is None
        assert seen["approval"]["steps"][0]["remark"] is None
        assert seen["discount"] is None
        # cross-vendor review: neither timeline carries the request's remark, the
        # officer's limit, or who decided (P1, P2)
        for path in (f"/quotations/{q['id']}/timeline", f"/leads/{q['lead']['id']}/timeline"):
            r = await client.get(f"{V1}{path}", headers=hd)
            assert r.status_code == 200, (path, r.text)
            events = r.json()["data"]
            mine = [e for e in events if e["kind"].startswith(("quotation.approval", "approval."))]
            assert mine, path
            for e in mine:
                leaked = {"remark", "owner_limit_pct"} & set(e["payload"])
                assert not leaked, (path, e)
                if e["kind"] in ("approval.decided", "quotation.approval_approved"):
                    assert e["actor"] is None, (path, e)
                    # FS-015 code review F-1: the name rode in the payload too
                    assert "actor_name" not in e["payload"], (path, e)
    finally:
        c = sessions()
        for stmt in ("DELETE FROM notification_outbox WHERE recipient IN (:m, :raw)",
                     "DELETE FROM login_attempt WHERE identifier IN (:m, :raw)"):
            await c.execute(text(stmt), {"m": e164, "raw": mobile})
        await c.commit()
        await c.close()


# ── Fable code review of FS-013 ──────────────────────────────────────────────

async def test_a_header_edit_or_a_delete_while_pending_cancels_the_request(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    hs = await endpoints._as(client, shop, "state_manager")
    q = await _draft(client, shop, ho, "12")
    assert (await _ask(client, ho, q["id"])).status_code == 200
    r = await client.patch(f"{V1}/quotations/{q['id']}", json={"terms": "Ex works Rajkot"},
                           headers={**ho, **_key()})
    assert r.status_code == 200 and r.json()["data"]["approval"]["status"] == "cancelled", r.text

    step = (await _ask(client, ho, q["id"])).json()["data"]["approval"]["steps"][0]
    # officers hold no quotations.delete (RBAC 6.1); a State Manager deletes
    r = await client.request("DELETE", f"{V1}/quotations/{q['id']}", json={},
                             headers={**hs, **_key()})
    assert r.status_code == 204, r.text
    r = await client.post(f"{V1}/approvals/steps/{step['id']}/decision",
                          json={"decision": "approve", "remark": "ok"}, headers={**hs, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "request_closed", r.text
    inbox = (await client.get(f"{V1}/approvals/pending", headers=hs)).json()["data"]
    assert all(x["document"]["id"] != q["id"] for x in inbox), "gone from the inbox"


async def test_whoever_asks_cannot_approve_even_when_the_step_is_theirs(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """The District Manager asks on an officer's 8 % draft; the step is the District
    Manager's own role, and the requester rule still refuses them."""
    ho = await endpoints._as(client, shop, "field_officer")
    hm = await endpoints._as(client, shop, "district_manager")
    q = await _draft(client, shop, ho, "8")
    step = (await _ask(client, hm, q["id"])).json()["data"]["approval"]["steps"][0]
    assert step["role"] == "district_manager"
    r = await client.post(f"{V1}/approvals/steps/{step['id']}/decision",
                          json={"decision": "approve", "remark": "ok"}, headers={**hm, **_key()})
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval", r.text


async def test_a_limit_raised_while_pending_lets_the_send_through_and_closes_the_request(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    q = await _draft(client, shop, ho, "12")
    asked = (await _ask(client, ho, q["id"])).json()["data"]
    s = sessions()
    await s.execute(text(
        "INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount) "
        "SELECT 'quotation', r.id, CAST(:t AS uuid), 20 FROM role r "
        "WHERE r.code = 'field_officer'"),
        {"t": shop.state})
    await s.commit()
    await s.close()
    r = await _send(client, ho, q["id"])
    assert r.status_code == 200, r.text
    assert r.json()["data"]["approval"]["status"] == "cancelled", "not left in the inbox"
    hs = await endpoints._as(client, shop, "state_manager")
    r = await client.post(f"{V1}/approvals/steps/{asked['approval']['steps'][0]['id']}/decision",
                          json={"decision": "reject", "remark": "late"}, headers={**hs, **_key()})
    assert r.status_code == 409, r.text


async def test_a_zero_quotation_limit_is_allowed_and_a_zero_order_limit_is_not(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ha = await endpoints._as(client, shop, "admin_sales")
    for doc_type, role, ok in (("quotation", "field_officer", True),
                               ("sales_order", "district_manager", False)):
        r = await client.put(f"{V1}/approvals/thresholds", headers={**ha, **_key()}, json={
            "doc_type": doc_type, "role": role, "territory_id": shop.state, "max_amount": "0"})
        assert (r.status_code == 200) is ok, (doc_type, r.text)



async def test_staff_see_who_asked_who_decided_and_why(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Cross-vendor review P2: the officer's own draft, approved by a manager their
    users scope cannot see, still names the manager; an Admin-Sales requester is
    named in a District Manager's inbox; the remark is on the approval and on the
    staff timeline."""
    ho = await endpoints._as(client, shop, "field_officer")
    ha = await endpoints._as(client, shop, "admin_sales")
    hm = await endpoints._as(client, shop, "district_manager")
    q = await _draft(client, shop, ho, "8")
    asked = (await client.post(f"{V1}/quotations/{q['id']}/request-approval",
                               json={"remark": "Farmer buys for three plots"},
                               headers={**ha, **_key()})).json()["data"]
    assert asked["approval"]["request_remark"] == "Farmer buys for three plots"
    inbox = (await client.get(f"{V1}/approvals/pending", headers=hm)).json()["data"]
    row = next(x for x in inbox if x["document"]["id"] == q["id"])
    assert row["document"]["raised_by"] is not None
    assert row["document"]["raised_by"]["id"] == shop.ids["admin_sales"]
    r = await client.post(f"{V1}/approvals/steps/{row['step_id']}/decision",
                          json={"decision": "approve", "remark": "ok"}, headers={**hm, **_key()})
    assert r.status_code == 200, r.text
    seen = (await client.get(f"{V1}/quotations/{q['id']}", headers=ho)).json()["data"]
    assert seen["approval"]["steps"][0]["by"]["id"] == shop.ids["district_manager"]
    events = (await client.get(f"{V1}/quotations/{q['id']}/timeline", headers=ho)).json()["data"]
    asked_event = next(e for e in events if e["kind"] == "quotation.approval_requested")
    assert asked_event["payload"]["remark"] == "Farmer buys for three plots"
