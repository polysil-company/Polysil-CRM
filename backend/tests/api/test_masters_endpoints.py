"""Offices, territories and partners, against the real app and the real database
(FS-006 section 4). Reuses the committed administrator of the people tests, whose
teardown removes everything created under it.

Partners are the one scoped table here, so the partner-caller path is driven end
to end: a dealer's user signs in by OTP, sees its own subtree, edits its contact
details, and is refused on credit terms and on close.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import Admin, Staff, _auth, _key, _staff_body

pytestmark = pytest.mark.db

V1 = "/api/v1"


async def _post(client: httpx.AsyncClient, h: dict[str, str], path: str, body: dict | None,
                expect: int = 201) -> dict:
    r = await client.post(f"{V1}{path}", json=body, headers={**h, **_key()})
    assert r.status_code == expect, r.text
    return r.json()


async def _read_code(sessions: Callable[[], AsyncSession], mobile: str) -> str:
    s = sessions()
    code = (await s.execute(text(
        "SELECT payload ->> 'code' FROM notification_outbox WHERE recipient = :m "
        "ORDER BY created_at DESC LIMIT 1"), {"m": mobile})).scalar_one()
    await s.rollback()
    return str(code)


# ── offices ──────────────────────────────────────────────────────────────────

async def test_offices_are_created_moved_closed_and_reopened(
        client: httpx.AsyncClient, admin: Admin, staff: Staff) -> None:
    h = await _auth(client, admin.user)
    tag = uuid.uuid4().hex[:6]
    region = (await _post(client, h, "/org-units", {
        "name": f"Region {tag}", "role_level": 4, "parent_id": admin.user.org_unit_id}))["data"]
    assert region["parent"]["id"] == admin.user.org_unit_id and region["is_open"] is True
    assert region["active_users"] == 0 and region["territory"] is None
    district = (await _post(client, h, "/org-units", {
        "name": f"District {tag}", "role_level": 2, "parent_id": region["id"],
        "territory_id": admin.territory_id}))["data"]
    assert district["territory"]["id"] == admin.territory_id
    dup = await client.post(f"{V1}/org-units", json={
        "name": f"  district {tag} ", "role_level": 2, "parent_id": region["id"]},
        headers={**h, **_key()})
    assert dup.status_code == 422 and "name" in dup.json()["error"]["fields"]

    # the tree with counts, readable by a plain staff user; writes need masters.edit
    dm = await _auth(client, staff)
    listed = await client.get(f"{V1}/org-units", params={"parent_id": region["id"]}, headers=dm)
    assert listed.status_code == 200
    assert [o["id"] for o in listed.json()["data"]] == [district["id"]]
    assert (await client.post(f"{V1}/org-units", json={"name": "x", "role_level": 1},
                              headers={**dm, **_key()})).status_code == 403

    # a move under its own descendant is refused; a real move takes
    cycle = await client.patch(f"{V1}/org-units/{region['id']}", json={"parent_id": district["id"]},
                               headers={**h, **_key()})
    assert cycle.status_code == 422 and "parent_id" in cycle.json()["error"]["fields"], cycle.text
    moved = await client.patch(f"{V1}/org-units/{district['id']}",
                               json={"parent_id": admin.user.org_unit_id, "name": f"Moved {tag}"},
                               headers={**h, **_key()})
    assert moved.status_code == 200
    assert moved.json()["data"]["parent"]["id"] == admin.user.org_unit_id

    # an office with an active person cannot close; move them and it can
    person = (await client.post(f"{V1}/users", json=_staff_body(admin, org_unit_id=district["id"]),
                                headers={**h, **_key()})).json()["data"]
    counted = await client.get(f"{V1}/org-units/{district['id']}", headers=h)
    assert counted.json()["data"]["active_users"] == 1
    refused = await client.post(f"{V1}/org-units/{district['id']}/close", headers={**h, **_key()})
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["fields"] == {"id": "active users are anchored here"}
    assert (await client.patch(f"{V1}/users/{person['id']}",
                               json={"org_unit_id": admin.user.org_unit_id},
                               headers={**h, **_key()})).status_code == 200
    closed = await client.post(f"{V1}/org-units/{district['id']}/close", headers={**h, **_key()})
    assert closed.status_code == 200 and closed.json()["data"]["is_open"] is False
    assert closed.json()["data"]["closed_at"] is not None
    again = await client.post(f"{V1}/org-units/{district['id']}/close", headers={**h, **_key()})
    assert again.status_code == 200
    # nobody can be created into a closed office
    into = await client.post(f"{V1}/users", json=_staff_body(admin, org_unit_id=district["id"]),
                             headers={**h, **_key()})
    assert into.status_code == 422 and "org_unit_id" in into.json()["error"]["fields"]
    reopened = await client.post(f"{V1}/org-units/{district['id']}/reopen",
                                 headers={**h, **_key()})
    assert reopened.status_code == 200 and reopened.json()["data"]["is_open"] is True
    only_closed = await client.get(f"{V1}/org-units", params={"is_open": "false", "q": tag},
                                   headers=h)
    assert only_closed.json()["data"] == []


# ── territories ──────────────────────────────────────────────────────────────

async def test_territories_follow_the_level_order_and_lock_a_numbered_code(
        client: httpx.AsyncClient, admin: Admin) -> None:
    h = await _auth(client, admin.user)
    tag = uuid.uuid4().hex[:6]
    wrong = await client.post(f"{V1}/territories", json={
        "name": f"v_{tag}", "level": "village", "parent_id": admin.territory_id},
        headers={**h, **_key()})
    assert wrong.status_code == 422
    assert wrong.json()["error"]["fields"] == {"parent_id": "a village sits under a taluka"}
    taluka = (await _post(client, h, "/territories", {
        "name": f"Gondal {tag}", "level": "taluka", "parent_id": admin.territory_id,
        "code": f"g{tag[:3]}"}))["data"]
    assert taluka["code"] == f"G{tag[:3]}".upper() and taluka["code_locked"] is False
    assert taluka["parent"]["id"] == admin.territory_id
    dup = await client.post(f"{V1}/territories", json={
        "name": f"gondal {tag}", "level": "taluka", "parent_id": admin.territory_id},
        headers={**h, **_key()})
    assert dup.status_code == 422 and "name" in dup.json()["error"]["fields"]
    renamed = await client.patch(f"{V1}/territories/{taluka['id']}",
                                 json={"name": f"Gondal T {tag}", "code": None},
                                 headers={**h, **_key()})
    assert renamed.status_code == 200 and renamed.json()["data"]["code"] is None

    # the admin's state has no lead yet: its code may still change, and change back
    state_id = (await client.get(f"{V1}/territories/{admin.territory_id}", headers=h)
                ).json()["data"]["parent"]["id"]
    before = await client.get(f"{V1}/territories/{state_id}", headers=h)
    assert before.json()["data"]["code_locked"] is False
    r = await client.post(f"{V1}/leads", json={
        "farmer_name": "Rameshbhai Patel", "mobile": "98" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": admin.territory_id, "inquiry_type": "commercial", "mis_system": "drip",
    }, headers={**h, **_key()})
    assert r.status_code == 201, r.text
    after = await client.get(f"{V1}/territories/{state_id}", headers=h)
    assert after.json()["data"]["code_locked"] is True
    locked = await client.patch(f"{V1}/territories/{state_id}", json={"code": "ZZZZ"},
                                headers={**h, **_key()})
    assert locked.status_code == 422, locked.text
    assert locked.json()["error"]["fields"] == {
        "code": "cannot change: leads are numbered under it"}
    listed = await client.get(f"{V1}/territories", params={"level": "state", "q": admin.state_code},
                              headers=h)
    assert [t["code_locked"] for t in listed.json()["data"] if t["id"] == state_id] == [True]


# ── partners ─────────────────────────────────────────────────────────────────

async def test_staff_manage_partners_and_a_dealer_edits_only_its_contact_details(
        client: httpx.AsyncClient, admin: Admin, sessions: Callable[[], AsyncSession]) -> None:
    h = await _auth(client, admin.user)
    tag = uuid.uuid4().hex[:6].upper()
    wrong = await client.post(f"{V1}/partners", json={
        "parent_id": admin.dealer_id, "partner_type": "distributor", "code": f"X-{tag}",
        "name": "Wrong", "territory_id": admin.territory_id}, headers={**h, **_key()})
    assert wrong.status_code == 422 and "partner_type" in wrong.json()["error"]["fields"]
    sub = (await _post(client, h, "/partners", {
        "parent_id": admin.dealer_id, "partner_type": "sub_dealer", "code": f"SUB-{tag}",
        "name": "Patel Agro", "territory_id": admin.territory_id, "mobile": "98765 43210",
        "contact_name": f"Kishor Bhatt {tag}",
        "gstin": "24aaaaa0000a1z5", "credit_limit": "25000.00", "payment_terms_days": 15,
        "is_gst_registered": True}))["data"]
    assert sub["price_tier"] == "sub_dealer" and sub["mobile"] == "919876543210"
    assert sub["gstin"] == "24AAAAA0000A1Z5" and sub["credit_limit"] == "25000.00"
    assert sub["parent"]["id"] == admin.dealer_id and sub["users"] == 0
    # a person's name finds their firm, in the lead picker and the list (re-walk R-8)
    for path in ("/lookups/partners", "/partners"):
        found = await client.get(f"{V1}{path}", params={"q": f"kishor bhatt {tag}"}, headers=h)
        assert [p["id"] for p in found.json()["data"]] == [sub["id"]], (path, found.text)
    bad = await client.post(f"{V1}/partners", json={
        "parent_id": admin.dealer_id, "partner_type": "sub_dealer", "code": f"SUB2-{tag}",
        "name": "Bad GST", "territory_id": admin.territory_id, "gstin": "nope"},
        headers={**h, **_key()})
    assert bad.status_code == 422 and bad.json()["error"]["fields"] == {"gstin": "not a GSTIN"}
    dup = await client.post(f"{V1}/partners", json={
        "parent_id": admin.dealer_id, "partner_type": "sub_dealer", "code": f"sub-{tag}",
        "name": "Dup", "territory_id": admin.territory_id}, headers={**h, **_key()})
    assert dup.status_code == 422 and dup.json()["error"]["fields"] == {"code": "already in use"}

    # the dealer's user, created through People, signs in by OTP
    mobile = "97" + f"{uuid.uuid4().int % 10**8:08d}"
    dealer_user = (await _post(client, h, "/users", {
        "user_type": "partner_user", "full_name": "Chirag Patel", "mobile": mobile,
        "partner_id": admin.dealer_id}))["data"]
    assert (await client.get(f"{V1}/partners/{admin.dealer_id}", headers=h)
            ).json()["data"]["users"] == 1
    await client.post(f"{V1}/auth/otp/request", json={"mobile": "91" + mobile})
    code = await _read_code(sessions, "91" + mobile)
    r = await client.post(f"{V1}/auth/otp/verify", json={"mobile": "91" + mobile, "code": code})
    assert r.status_code == 200, r.text
    d = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    mine = await client.get(f"{V1}/partners", headers=d)
    assert mine.status_code == 200, mine.text
    assert {p["id"] for p in mine.json()["data"]} == {admin.dealer_id, sub["id"]}
    assert all(p["credit_limit"] is None for p in mine.json()["data"])
    assert (await client.get(f"{V1}/partners/{admin.distributor_id}", headers=d)).status_code == 404
    ok = await client.patch(f"{V1}/partners/{admin.dealer_id}", json={"contact_name": "Chirag"},
                            headers={**d, **_key()})
    assert ok.status_code == 200 and ok.json()["data"]["contact_name"] == "Chirag"
    refused = await client.patch(f"{V1}/partners/{admin.dealer_id}", json={"credit_limit": "1"},
                                 headers={**d, **_key()})
    assert refused.status_code == 422
    assert refused.json()["error"]["fields"] == {
        "credit_limit": "a partner may edit its contact details only"}
    assert (await client.post(f"{V1}/partners/{admin.dealer_id}/close",
                              headers={**d, **_key()})).status_code == 403
    grandchild = await client.post(f"{V1}/partners", json={
        "parent_id": sub["id"], "partner_type": "sub_dealer", "code": f"GC-{tag}",
        "name": "Too deep", "territory_id": admin.territory_id}, headers={**d, **_key()})
    assert grandchild.status_code == 422, grandchild.text

    # staff close the dealer: its user is signed out and inactive; reopen restores nobody
    closed = await client.post(f"{V1}/partners/{admin.dealer_id}/close", headers={**h, **_key()})
    assert closed.status_code == 200, closed.text
    assert closed.json()["data"]["is_active"] is False
    assert closed.json()["data"]["users"] == 0 and closed.json()["data"]["users_inactive"] == 1
    assert (await client.get(f"{V1}/partners", headers=d)).status_code == 401
    person = await client.get(f"{V1}/users/{dealer_user['id']}", headers=h)
    assert person.json()["data"]["is_active"] is False
    reopened = await client.post(f"{V1}/partners/{admin.dealer_id}/reopen",
                                 headers={**h, **_key()})
    assert reopened.status_code == 200 and reopened.json()["data"]["is_active"] is True
    assert reopened.json()["data"]["users_inactive"] == 1
    back = await client.patch(f"{V1}/users/{dealer_user['id']}", json={"is_active": True},
                              headers={**h, **_key()})
    assert back.status_code == 200 and back.json()["data"]["is_active"] is True
