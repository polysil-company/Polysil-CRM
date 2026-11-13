# ruff: noqa: E501  (request bodies inline)

"""FS-051 over the API: a dealer application from staff, through the applicant's
link, to an approved dealer who signs in."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import gstin
from tests.api import test_complaints as complaints_t
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
JPEG, PDF = complaints_t.JPEG, complaints_t.PDF
PAN = "ABCDE1234F"


def _gstin(state: str = "24") -> str:
    prefix = f"{state}{PAN}1Z"
    return prefix + gstin.check_character(prefix)


def _mobile10() -> str:
    return "9" + f"{uuid.uuid4().int % 10**9:09d}"


@pytest_asyncio.fixture
async def apps(shop: Shop, sessions: Sessions, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[list[str]]:
    """The applications' mobiles, cleaned up before the shop removes its people."""
    storage = complaints_t._Counting()
    monkeypatch.setattr("api.routers.dealer_applications.get_storage", lambda *a, **k: storage)
    monkeypatch.setattr("api.routers.documents.get_storage", lambda *a, **k: storage)
    mobiles: list[str] = []
    yield mobiles
    s = sessions()
    nums = ["91" + m for m in mobiles]
    for stmt in (
        "DELETE FROM activity_event WHERE entity_id IN (SELECT id FROM dealer_application WHERE mobile = ANY(:n)) "
        "OR entity_id IN (SELECT partner_id FROM dealer_application WHERE mobile = ANY(:n)) "
        "OR entity_id IN (SELECT user_id FROM dealer_application WHERE mobile = ANY(:n))",
        "DELETE FROM record_document WHERE record_type = 'dealer_application' AND record_id IN (SELECT id FROM dealer_application WHERE mobile = ANY(:n))",
        "DELETE FROM notification_outbox WHERE recipient = ANY(:n) OR recipient = ANY(:p)",
        "DELETE FROM login_attempt WHERE identifier = ANY(:n)",
        "DELETE FROM session WHERE user_id IN (SELECT id FROM app_user WHERE mobile = ANY(:n))",
        "UPDATE dealer_application SET user_id = NULL, partner_id = NULL WHERE mobile = ANY(:n)",
        "DELETE FROM app_user WHERE mobile = ANY(:n) AND user_type = 'partner_user'",
        "DELETE FROM partner_closure WHERE descendant_id IN (SELECT id FROM channel_partner WHERE mobile = ANY(:n))",
        "DELETE FROM channel_partner WHERE mobile = ANY(:n)",
        "DELETE FROM dealer_application WHERE mobile = ANY(:n)",
    ):
        try:
            async with s.begin_nested():
                await s.execute(text(stmt), {"n": nums, "p": ["+" + x for x in nums]})
        except Exception:
            pass
    await s.commit()
    await s.close()


async def _code(sessions: Sessions, mobile: str, template: str) -> str:
    s = sessions()
    try:
        return str((await s.execute(text(
            "SELECT payload ->> 'code' FROM notification_outbox WHERE recipient IN (:m, :p) AND template_key = :t "
            "ORDER BY created_at DESC LIMIT 1"), {"m": mobile, "p": "+" + mobile, "t": template})).scalar_one())
    finally:
        await s.close()


async def _start(client: httpx.AsyncClient, shop: Shop, h: dict[str, str], mobile10: str) -> tuple[dict, str]:
    r = await client.post(f"{V1}/dealer-applications", headers={**h, **_key()}, json={
        "firm_name": "Patel Agro", "contact_name": "Rameshbhai Patel", "mobile": mobile10,
        "territory_id": shop.district})
    assert r.status_code == 201, r.text
    app = r.json()["data"]
    return app, app["apply_url"].rsplit("/", 1)[1]


async def test_from_staff_through_the_link_to_a_dealer_who_signs_in(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, apps: list[str]) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    m10 = _mobile10()
    apps.append(m10)
    app, token = await _start(client, shop, ho, m10)
    assert app["status"] == "draft" and "pan_card" in app["missing"]
    pub = f"{V1}/public/dealer-apply/{token}"

    # the link alone shows no PAN or bank (plan review B-3)
    view = (await client.get(pub)).json()["data"]
    assert view["firm_name"] == "Patel Agro" and "pan" not in view and view["session"] is False
    assert (await client.patch(pub, json={"pan": PAN})).status_code == 403, "no session"

    assert (await client.post(f"{pub}/verify")).status_code == 202
    code = await _code(sessions, "91" + m10, "dealer.verify")
    assert (await client.post(f"{pub}/verify/check", json={"code": "000000" if code != "000000" else "111111"})).status_code == 422
    r = await client.post(f"{pub}/verify/check", json={"code": code})
    assert r.status_code == 200, r.text
    hs = {"X-Apply-Session": r.json()["data"]["session"]}

    r = await client.patch(pub, headers=hs, json={"gstin": _gstin(), "pan": "ZZZZZ9999Z"})
    assert r.status_code == 422 and "pan" in r.json()["error"]["fields"], "the PAN inside the GSTIN"
    r = await client.patch(pub, headers=hs, json={"gstin": "24ABCDE1234F1Z0" if _gstin()[-1] != "0" else "24ABCDE1234F1Z1"})
    assert r.status_code == 422 and "gstin" in r.json()["error"]["fields"], "a wrong check character"
    r = await client.patch(pub, headers=hs, json={
        "firm_type": "proprietorship", "gstin": _gstin().lower(), "pan": PAN, "address": "Main Road, Rajkot",
        "pincode": "360001", "bank_account_name": "Patel Agro", "bank_account_no": "123456789012",
        "bank_ifsc": "sbin0001234"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["pan"] == PAN and r.json()["data"]["bank_ifsc"] == "SBIN0001234"
    lookup = (await client.get(f"{pub}/gstin/{_gstin()}", headers=hs)).json()["data"]
    assert lookup["valid"] and lookup["pan"] == PAN and lookup["lookup"] == "unavailable"

    r = await client.post(f"{pub}/submit", headers=hs)
    assert r.status_code == 422 and {"gst_certificate", "pan_card", "cancelled_cheque"} <= set(r.json()["error"]["fields"]), r.text
    for doc_type, data in (("gst_certificate", PDF), ("pan_card", JPEG), ("cancelled_cheque", PDF + b"x")):
        r = await client.post(f"{pub}/documents", headers=hs, files={"file": ("f", data, "application/pdf")},
                              data={"doc_type": doc_type})
        assert r.status_code == 201, r.text
    assert (await client.post(f"{pub}/submit", headers=hs)).status_code == 200
    assert (await client.post(f"{pub}/submit", headers=hs)).status_code == 200, "a replay"
    assert (await client.patch(pub, headers=hs, json={"notes": "late"})).status_code == 409, "closed to the applicant"

    # staff: the creator and a field officer cannot decide; a State Manager approves
    got = (await client.get(f"{V1}/dealer-applications/{app['id']}", headers=ho)).json()["data"]
    assert got["status"] == "submitted" and got["missing"] == [] and not got["can"]["decide"]
    r = await client.post(f"{V1}/dealer-applications/{app['id']}/decision", headers={**ho, **_key()},
                          json={"decision": "approve"})
    assert r.status_code == 403, r.text
    sm = await endpoints._as(client, shop, "state_manager")
    r = await client.post(f"{V1}/dealer-applications/{app['id']}/decision", headers={**sm, **_key()},
                          json={"decision": "approve"})
    assert r.status_code == 200, r.text
    done = r.json()["data"]
    assert done["status"] == "approved" and done["partner_id"] and done["user_id"]
    r = await client.post(f"{V1}/dealer-applications/{app['id']}/decision", headers={**sm, **_key()},
                          json={"decision": "reject", "remark": "late"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_decided"

    # the new dealer signs in with a code
    await client.post(f"{V1}/auth/otp/request", json={"mobile": "91" + m10})
    code = await _code(sessions, "91" + m10, "auth.otp")
    r = await client.post(f"{V1}/auth/otp/verify", json={"mobile": "91" + m10, "code": code})
    assert r.status_code == 200, r.text
    dealer = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    assert (await client.get(f"{V1}/dealer-applications", headers=dealer)).status_code == 403, "staff only"


async def test_renewing_the_link_kills_the_old_one_and_a_staff_mobile_is_refused(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, apps: list[str]) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    m10 = _mobile10()
    apps.append(m10)
    app, token = await _start(client, shop, ho, m10)
    r = await client.post(f"{V1}/dealer-applications/{app['id']}/link", headers={**ho, **_key()})
    assert r.status_code == 200 and r.json()["data"]["apply_url"], r.text
    assert (await client.get(f"{V1}/public/dealer-apply/{token}")).status_code == 404, "the old link is dead"
    new = r.json()["data"]["apply_url"].rsplit("/", 1)[1]
    assert (await client.get(f"{V1}/public/dealer-apply/{new}")).status_code == 200

    r = await client.post(f"{V1}/dealer-applications", headers={**ho, **_key()}, json={
        "firm_name": "Dup", "contact_name": "Dup", "mobile": m10, "territory_id": shop.district})
    assert r.status_code == 409 and r.json()["error"]["code"] == "application_open"
    s = sessions()
    staff_mobile = str((await s.execute(text("SELECT mobile FROM app_user WHERE id = CAST(:u AS uuid)"),
                                        {"u": shop.ids["district_manager"]})).scalar_one() or "")
    await s.close()
    if staff_mobile:
        r = await client.post(f"{V1}/dealer-applications", headers={**ho, **_key()}, json={
            "firm_name": "Staff", "contact_name": "Staff", "mobile": staff_mobile, "territory_id": shop.district})
        assert r.status_code == 409 and r.json()["error"]["code"] == "mobile_in_use", r.text

    r = await client.post(f"{V1}/dealer-applications/{app['id']}/withdraw", headers={**ho, **_key()},
                          json={"remark": "Not interested"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "withdrawn"
    assert (await client.get(f"{V1}/public/dealer-apply/{new}")).status_code == 404


async def _verified(client: httpx.AsyncClient, sessions: Sessions, token: str, m10: str) -> dict[str, str]:
    pub = f"{V1}/public/dealer-apply/{token}"
    assert (await client.post(f"{pub}/verify")).status_code == 202
    code = await _code(sessions, "91" + m10, "dealer.verify")
    r = await client.post(f"{pub}/verify/check", json={"code": code})
    assert r.status_code == 200, r.text
    return {"X-Apply-Session": r.json()["data"]["session"]}


async def _complete(client: httpx.AsyncClient, token: str, hs: dict[str, str]) -> None:
    pub = f"{V1}/public/dealer-apply/{token}"
    r = await client.patch(pub, headers=hs, json={
        "firm_type": "partnership", "gst_registered": False, "pan": PAN, "address": "Station Road",
        "pincode": "360002", "bank_account_name": "Patel Agro", "bank_account_no": "998877665544",
        "bank_ifsc": "HDFC0001234"})
    assert r.status_code == 200, r.text
    for doc_type, data in (("pan_card", JPEG), ("cancelled_cheque", PDF)):
        r = await client.post(f"{pub}/documents", headers=hs, files={"file": ("f", data, "image/jpeg")},
                              data={"doc_type": doc_type})
        assert r.status_code == 201, r.text
    assert (await client.post(f"{pub}/submit", headers=hs)).status_code == 200


async def test_five_wrong_codes_burn_it_and_the_right_one_then_fails(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, apps: list[str]) -> None:
    """Code review, critical: the attempt count must commit with a 422."""
    ho = await endpoints._as(client, shop, "field_officer")
    m10 = _mobile10()
    apps.append(m10)
    _, token = await _start(client, shop, ho, m10)
    pub = f"{V1}/public/dealer-apply/{token}"
    assert (await client.post(f"{pub}/verify")).status_code == 202
    code = await _code(sessions, "91" + m10, "dealer.verify")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        r = await client.post(f"{pub}/verify/check", json={"code": wrong})
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_code", r.text
    r = await client.post(f"{pub}/verify/check", json={"code": code})
    assert r.status_code == 422, "burned after five"


async def test_return_resubmit_reject_renewal_and_a_released_portal_account(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, apps: list[str]) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    sm = await endpoints._as(client, shop, "state_manager")
    m10 = _mobile10()
    apps.append(m10)
    app, token = await _start(client, shop, ho, m10)
    hs = await _verified(client, sessions, token, m10)
    await _complete(client, token, hs)

    # returned: the remark needs the session (spec B-3)
    r = await client.post(f"{V1}/dealer-applications/{app['id']}/decision", headers={**sm, **_key()},
                          json={"decision": "return", "remark": "Fix the address"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "returned", r.text
    pub = f"{V1}/public/dealer-apply/{token}"
    assert "remark" not in (await client.get(pub)).json()["data"], "the link alone shows no remark"
    # a renewal kills the old link and the session
    r = await client.post(f"{V1}/dealer-applications/{app['id']}/link", headers={**ho, **_key()})
    token = r.json()["data"]["apply_url"].rsplit("/", 1)[1]
    pub = f"{V1}/public/dealer-apply/{token}"
    assert (await client.patch(pub, headers=hs, json={"address": "x"})).status_code == 403, "a stale session"
    hs = await _verified(client, sessions, token, m10)
    assert (await client.get(pub, headers=hs)).json()["data"]["remark"] == "Fix the address"
    assert (await client.patch(pub, headers=hs, json={"address": "Station Road, Rajkot"})).status_code == 200
    assert (await client.post(f"{pub}/submit", headers=hs)).status_code == 200
    assert (await client.patch(pub, headers=hs, json={"notes": "x"})).status_code in (403, 409)

    # a customer's portal account on the mobile is released on approval
    s = sessions()
    cid = (await s.execute(text("INSERT INTO customer (name, mobile) VALUES ('Ramesh', :m) RETURNING id"),
                           {"m": "+91" + m10})).scalar_one()
    # the customer's insert makes its portal account (052); switch it on
    await s.execute(text("INSERT INTO app_user (user_type, mobile, full_name, customer_id, is_active) "
                         "VALUES ('consumer', :m, 'Ramesh', :c, true) "
                         "ON CONFLICT (mobile) WHERE deleted_at IS NULL DO UPDATE SET is_active = true"),
                    {"m": "91" + m10, "c": cid})
    parent = str((await s.execute(text(
        "SELECT id FROM channel_partner WHERE partner_type = 'distributor' AND is_active AND deleted_at IS NULL LIMIT 1"))).scalar_one())
    await s.commit()
    await s.close()
    try:
        r = await client.post(f"{V1}/dealer-applications/{app['id']}/decision", headers={**sm, **_key()},
                              json={"decision": "approve", "parent_id": parent})
        assert r.status_code == 200, r.text
        s = sessions()
        row = (await s.execute(text(
            "SELECT p.code::text AS code, p.parent_id, (SELECT count(*) FROM app_user u WHERE u.mobile = :m "
            "AND u.user_type = 'consumer' AND u.deleted_at IS NULL) AS consumers "
            "FROM channel_partner p WHERE p.id = CAST(:p AS uuid)"),
            {"m": "91" + m10, "p": r.json()["data"]["partner_id"]})).one()
        await s.close()
        assert row.consumers == 0, "the portal account was released"
        assert str(row.parent_id) == parent and row.code.startswith("DLR-"), row
    finally:
        s = sessions()
        await s.execute(text("DELETE FROM app_user WHERE mobile = :m AND user_type = 'consumer'"), {"m": "91" + m10})
        await s.execute(text("DELETE FROM customer WHERE id = CAST(:c AS uuid)"), {"c": str(cid)})
        await s.commit()
        await s.close()

    # a second application, rejected
    m2 = _mobile10()
    apps.append(m2)
    app2, token2 = await _start(client, shop, ho, m2)
    await _complete(client, token2, await _verified(client, sessions, token2, m2))
    r = await client.post(f"{V1}/dealer-applications/{app2['id']}/decision", headers={**sm, **_key()},
                          json={"decision": "reject"})
    assert r.status_code == 422, "a reject needs a remark"
    r = await client.post(f"{V1}/dealer-applications/{app2['id']}/decision", headers={**sm, **_key()},
                          json={"decision": "reject", "remark": "Not in our area"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "rejected"
    assert (await client.get(f"{V1}/public/dealer-apply/{token2}")).status_code == 404



async def test_a_won_dealership_lead_starts_the_application(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, apps: list[str]) -> None:
    """FS-053 (GAP-294): won without a quotation, and the application starts from the lead."""
    ho = await endpoints._as(client, shop, "field_officer")
    m10 = _mobile10()
    apps.append(m10)

    async def _lead(kind: str) -> str:
        r = await client.post(f"{V1}/leads", headers={**ho, **_key()}, json={
            "farmer_name": "Bhavesh Traders", "mobile": m10, "territory_id": shop.district,
            "inquiry_type": kind, "mis_system": "drip", "village": "Vadod"})
        assert r.status_code == 201, r.text
        lid = r.json()["data"]["id"]
        for stage in ("contacted", "qualified"):
            r = await client.post(f"{V1}/leads/{lid}/transition", headers={**ho, **_key()}, json={"to_stage": stage})
            assert r.status_code == 200, r.text
        return str(lid)

    commercial = await _lead("commercial")
    r = await client.post(f"{V1}/leads/{commercial}/transition", headers={**ho, **_key()}, json={"to_stage": "won"})
    assert r.status_code == 422, "a commercial lead still needs its quotation"

    dealer_lead = await _lead("dealership")
    r = await client.post(f"{V1}/leads/{dealer_lead}/transition", headers={**ho, **_key()}, json={"to_stage": "won"})
    assert r.status_code == 200, r.text
    won = r.json()["data"]
    started = won["dealer_application"]
    assert won["stage"] == "won" and started["id"] and started["apply_url"] and started["not_started"] is None, won
    app = (await client.get(f"{V1}/dealer-applications/{started['id']}", headers=ho)).json()["data"]
    assert app["lead_id"] == dealer_lead and app["firm_name"] == "Bhavesh Traders" and app["status"] == "draft"

    second = await _lead("dealership")
    r = await client.post(f"{V1}/leads/{second}/transition", headers={**ho, **_key()}, json={"to_stage": "won"})
    assert r.status_code == 200 and r.json()["data"]["dealer_application"]["not_started"] == "application_open", r.text
