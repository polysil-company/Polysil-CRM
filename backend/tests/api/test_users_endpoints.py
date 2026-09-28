"""The people endpoints, the own-password change and the roles lookup, against the
real app and the real database (FS-006 section 4).

Nothing is stubbed. The forced-change gate, the idempotency contract, the error
envelope, the 404-for-out-of-scope rule and the definer-backed actions all live
outside the service functions, so the tests drive them through HTTP.

The `admin` fixture is a committed administrator (users and leads at global,
masters too) with its own coded state and district, so leads can be created and
handed over. Everything it and the tests create is removed afterwards by
`created_by`.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from api.config import get_settings
from tests.api.conftest import (
    PASSWORD,
    TEMP,
    V1,
    Admin,
    Staff,
    _auth,
    _create,
    _key,
    _login,
    _staff_body,
)

pytestmark = pytest.mark.db

SYSTEM_ID = get_settings().system_user_id
INTAKE_ID = get_settings().intake_user_id


async def _complete_forced_change(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    """Sign in with the temporary password, change it, sign in again."""
    h = await _login(client, email, TEMP)
    r = await client.post(f"{V1}/auth/password",
                          json={"current_password": TEMP, "new_password": PASSWORD},
                          headers={**h, **_key()})
    assert r.status_code == 204, r.text
    return await _login(client, email, PASSWORD)


async def _lead(client: httpx.AsyncClient, h: dict[str, str], admin: Admin) -> str:
    r = await client.post(f"{V1}/leads", json={
        "farmer_name": "Rameshbhai Patel", "mobile": "98" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": admin.territory_id, "inquiry_type": "subsidised", "mis_system": "drip",
    }, headers={**h, **_key()})
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


async def _assign(client: httpx.AsyncClient, h: dict[str, str], lead_id: str, owner: str) -> None:
    r = await client.post(f"{V1}/leads/{lead_id}/assign", json={"owner_user_id": owner},
                          headers={**h, **_key()})
    assert r.status_code == 200, r.text


# ── the list and the gate ────────────────────────────────────────────────────

async def test_the_people_list_needs_users_view(client: httpx.AsyncClient, staff: Staff,
                                                admin: Admin) -> None:
    dm = await _auth(client, staff)
    assert (await client.get(f"{V1}/users", headers=dm)).status_code == 403
    h = await _auth(client, admin.user)
    r = await client.get(f"{V1}/users", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["limit"] == 50
    ids = {u["id"] for u in body["data"]}
    assert admin.user.id in ids and SYSTEM_ID not in ids
    me = next(u for u in body["data"] if u["id"] == admin.user.id)
    assert me["open_leads"] == 0 and me["must_change_password"] is False


async def test_create_a_staff_member_and_walk_the_forced_change(
        client: httpx.AsyncClient, admin: Admin) -> None:
    h = await _auth(client, admin.user)
    body = _staff_body(admin, email=f" Staff_{uuid.uuid4().hex[:6]}@Polysil.IN ")
    key = _key()
    r = await client.post(f"{V1}/users", json=body, headers={**h, **key})
    assert r.status_code == 201, r.text
    person = r.json()["data"]
    assert person["email"] == body["email"].strip().lower()
    assert person["must_change_password"] is True and person["is_active"] is True
    assert person["role"]["code"] == "field_officer" and person["open_leads"] == 0
    assert person["org_unit"]["id"] == admin.user.org_unit_id
    assert person["created_by"]["id"] == admin.user.id
    assert person["active_sessions"] == 0 and person["locked_until"] is None

    # the same key replays; a different password under the same key is a 409
    again = await client.post(f"{V1}/users", json=body, headers={**h, **key})
    assert again.status_code == 201 and again.json()["data"]["id"] == person["id"]
    other = await client.post(f"{V1}/users", json={**body, "password": TEMP + "x"},
                              headers={**h, **key})
    assert other.status_code == 409
    # and the address is taken
    dup = await client.post(f"{V1}/users", json=_staff_body(admin, email=person["email"]),
                            headers={**h, **_key()})
    assert dup.status_code == 422 and dup.json()["error"]["fields"] == {"email": "already in use"}

    # the temporary password works once for /auth/me and /auth/password only
    temp = await _login(client, person["email"], TEMP)
    me = await client.get(f"{V1}/auth/me", headers=temp)
    assert me.status_code == 200 and me.json()["data"]["must_change_password"] is True
    gated = await client.get(f"{V1}/leads", headers=temp)
    assert gated.status_code == 403
    assert gated.json()["error"]["code"] == "password_change_required"
    wrong = await client.post(f"{V1}/auth/password",
                              json={"current_password": "not-it-at-all", "new_password": PASSWORD},
                              headers={**temp, **_key()})
    assert wrong.status_code == 422 and "current_password" in wrong.json()["error"]["fields"]
    short = await client.post(f"{V1}/auth/password",
                              json={"current_password": TEMP, "new_password": "short"},
                              headers={**temp, **_key()})
    assert short.status_code == 422
    assert short.json()["error"]["fields"] == {"new_password": "at least 12 characters"}
    done = await client.post(f"{V1}/auth/password",
                             json={"current_password": TEMP, "new_password": PASSWORD},
                             headers={**temp, **_key()})
    assert done.status_code == 204, done.text
    # every session is gone, the new password is in force, the gate is lifted
    assert (await client.get(f"{V1}/auth/me", headers=temp)).status_code == 401
    fresh = await _login(client, person["email"], PASSWORD)
    me = await client.get(f"{V1}/auth/me", headers=fresh)
    assert me.json()["data"]["must_change_password"] is False
    assert (await client.get(f"{V1}/leads", headers=fresh)).status_code == 200
    detail = await client.get(f"{V1}/users/{person['id']}", headers=h)
    assert detail.json()["data"]["password_changed_at"] is not None


async def test_create_validation_names_the_field(client: httpx.AsyncClient, admin: Admin) -> None:
    h = await _auth(client, admin.user)
    cases = [
        (_staff_body(admin, email="not-an-email"), "email"),
        (_staff_body(admin, role="dealer"), "role"),
        (_staff_body(admin, role="system"), "role"),
        (_staff_body(admin, role="no_such_role"), "role"),
        (_staff_body(admin, password="short"), "password"),
        (_staff_body(admin, org_unit_id=str(uuid.uuid4())), "org_unit_id"),
        (_staff_body(admin, territory_ids=[str(uuid.uuid4())]), "territory_ids"),
        (_staff_body(admin, partner_id=admin.dealer_id), "partner_id"),
        ({"user_type": "partner_user", "full_name": "Kiran", "mobile": "+44 7700 900123",
          "partner_id": admin.dealer_id}, "mobile"),
        ({"user_type": "partner_user", "full_name": "Kiran", "mobile": "9876501234",
          "partner_id": str(uuid.uuid4())}, "partner_id"),
        ({"user_type": "partner_user", "full_name": "Kiran", "mobile": "9876501234",
          "partner_id": admin.dealer_id, "role": "dealer"}, "role"),
        ({"user_type": "consumer", "full_name": "x", "mobile": "9876501234"}, "user_type"),
    ]
    for body, field in cases:
        r = await client.post(f"{V1}/users", json=body, headers={**h, **_key()})
        assert r.status_code == 422, (field, r.text)
        assert field in r.json()["error"]["fields"], (field, r.text)


async def test_a_partner_users_role_is_its_partners_type(client: httpx.AsyncClient,
                                                         admin: Admin) -> None:
    h = await _auth(client, admin.user)
    mobile = "98765" + f"{uuid.uuid4().int % 10**5:05d}"
    person = await _create(client, h, {
        "user_type": "partner_user", "full_name": "Kiran Dave",
        "mobile": "+91 " + mobile[:5] + " " + mobile[5:], "partner_id": admin.dealer_id})
    assert person["role"]["code"] == "dealer" and person["mobile"] == "91" + mobile
    assert person["partner"]["id"] == admin.dealer_id and person["org_unit"] is None
    assert person["open_leads"] is None and person["must_change_password"] is False
    assert person["locked_until"] is None and person["active_sessions"] == 0
    # unlock and set-password have nothing to do for an OTP account
    for path in ("unlock", "password"):
        r = await client.post(f"{V1}/users/{person['id']}/{path}",
                              json={"password": TEMP} if path == "password" else None,
                              headers={**h, **_key()})
        assert r.status_code == 422 and "user_type" in r.json()["error"]["fields"], r.text
    # the same mobile again is taken, whatever form it arrives in
    dup = await client.post(f"{V1}/users", json={
        "user_type": "partner_user", "full_name": "Again", "mobile": "0" + mobile,
        "partner_id": admin.dealer_id}, headers={**h, **_key()})
    assert dup.status_code == 422 and dup.json()["error"]["fields"] == {"mobile": "already in use"}


# ── edit ─────────────────────────────────────────────────────────────────────

async def test_patch_refuses_the_callers_own_role_and_corrects_others(
        client: httpx.AsyncClient, admin: Admin) -> None:
    h = await _auth(client, admin.user)
    for field, value in (("role", "board"), ("org_unit_id", admin.user.org_unit_id),
                         ("territory_ids", [admin.territory_id]), ("is_active", False)):
        r = await client.patch(f"{V1}/users/{admin.user.id}", json={field: value},
                               headers={**h, **_key()})
        assert r.status_code == 422 and field in r.json()["error"]["fields"], (field, r.text)
    own = await client.patch(f"{V1}/users/{admin.user.id}", json={"full_name": "API Admin II"},
                             headers={**h, **_key()})
    assert own.status_code == 200 and own.json()["data"]["full_name"] == "API Admin II"

    person = await _create(client, h, _staff_body(admin))
    r = await client.patch(f"{V1}/users/{person['id']}", json={
        "role": "district_manager", "territory_ids": [admin.territory_id],
        "full_name": "Meera J. Joshi"}, headers={**h, **_key()})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["role"]["code"] == "district_manager" and data["full_name"] == "Meera J. Joshi"
    assert [t["id"] for t in data["territories"]] == [admin.territory_id]
    empty = await client.patch(f"{V1}/users/{person['id']}", json={},
                               headers={**h, **_key()})
    assert empty.status_code == 422
    portal = await client.patch(f"{V1}/users/{person['id']}", json={"role": "dealer"},
                                headers={**h, **_key()})
    assert portal.status_code == 422 and "role" in portal.json()["error"]["fields"]


async def test_deactivating_signs_out_first_and_reactivating_needs_an_open_office(
        client: httpx.AsyncClient, admin: Admin) -> None:
    h = await _auth(client, admin.user)
    person = await _create(client, h, _staff_body(admin))
    theirs = await _complete_forced_change(client, person["email"])
    off = await client.patch(f"{V1}/users/{person['id']}", json={"is_active": False},
                             headers={**h, **_key()})
    assert off.status_code == 200 and off.json()["data"]["is_active"] is False
    assert (await client.get(f"{V1}/auth/me", headers=theirs)).status_code == 401
    r = await client.post(f"{V1}/auth/login",
                          json={"email": person["email"], "password": PASSWORD})
    assert r.status_code == 401   # inactive is invalid_credentials, never a distinct code
    on = await client.patch(f"{V1}/users/{person['id']}", json={"is_active": True},
                            headers={**h, **_key()})
    assert on.status_code == 200 and on.json()["data"]["is_active"] is True
    assert (await client.get(f"{V1}/users/{person['id']}", headers=h)
            ).json()["data"]["active_sessions"] == 0


# ── the admin actions ────────────────────────────────────────────────────────

async def test_set_password_revokes_and_forces_a_change(client: httpx.AsyncClient,
                                                        admin: Admin) -> None:
    h = await _auth(client, admin.user)
    person = await _create(client, h, _staff_body(admin))
    theirs = await _complete_forced_change(client, person["email"])
    key = _key()
    r = await client.post(f"{V1}/users/{person['id']}/password",
                          json={"password": "another-temporary-1"}, headers={**h, **key})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"id": person["id"], "must_change_password": True,
                                "sessions_revoked": 1}
    assert (await client.get(f"{V1}/auth/me", headers=theirs)).status_code == 401
    # a replay says the same; a different password under the key is a conflict
    assert (await client.post(f"{V1}/users/{person['id']}/password",
                              json={"password": "another-temporary-1"},
                              headers={**h, **key})).json()["data"]["sessions_revoked"] == 1
    assert (await client.post(f"{V1}/users/{person['id']}/password",
                              json={"password": "yet-another-temporary"},
                              headers={**h, **key})).status_code == 409
    again = await _login(client, person["email"], "another-temporary-1")
    assert (await client.get(f"{V1}/auth/me", headers=again)
            ).json()["data"]["must_change_password"] is True
    short = await client.post(f"{V1}/users/{person['id']}/password",
                              json={"password": "short"}, headers={**h, **_key()})
    assert short.status_code == 422 and "password" in short.json()["error"]["fields"]


async def test_revoke_sessions_and_unlock(client: httpx.AsyncClient, admin: Admin) -> None:
    h = await _auth(client, admin.user)
    person = await _create(client, h, _staff_body(admin))
    theirs = await _complete_forced_change(client, person["email"])
    r = await client.post(f"{V1}/users/{person['id']}/sessions/revoke", headers={**h, **_key()})
    assert r.status_code == 200 and r.json()["data"]["sessions_revoked"] == 1
    assert (await client.get(f"{V1}/auth/me", headers=theirs)).status_code == 401

    for _ in range(5):
        await client.post(f"{V1}/auth/login",
                          json={"email": person["email"], "password": "wrong-wrong-wrong"})
    locked = await client.post(f"{V1}/auth/login",
                               json={"email": person["email"], "password": PASSWORD})
    assert locked.status_code == 423
    detail = await client.get(f"{V1}/users/{person['id']}", headers=h)
    assert detail.json()["data"]["locked_until"] is not None
    r = await client.post(f"{V1}/users/{person['id']}/unlock", headers={**h, **_key()})
    assert r.status_code == 200 and r.json()["data"]["was_locked"] is True
    assert (await client.get(f"{V1}/users/{person['id']}", headers=h)
            ).json()["data"]["locked_until"] is None
    assert (await client.post(f"{V1}/auth/login",
                              json={"email": person["email"], "password": PASSWORD})
            ).status_code == 200


async def test_handover_moves_open_leads_and_can_deactivate_the_leaver(
        client: httpx.AsyncClient, admin: Admin, monkeypatch: pytest.MonkeyPatch) -> None:
    from api.services import users as users_service

    h = await _auth(client, admin.user)
    leaver = await _create(client, h, _staff_body(admin, full_name="Leaver"))
    target = await _create(client, h, _staff_body(admin, full_name="Target"))
    watcher = await _create(client, h, _staff_body(admin, full_name="Watcher",
                                                    role="regional_manager"))
    leads = [await _lead(client, h, admin) for _ in range(3)]
    for lid in leads:
        await _assign(client, h, lid, leaver["id"])
    # one of them is closed: it stays with the leaver (rule 12)
    reasons = (await client.get(f"{V1}/lookups/lost-reasons", headers=h)).json()["data"]
    reason = next(x for x in reasons if x["is_active"])["id"]
    r = await client.post(f"{V1}/leads/{leads[2]}/transition",
                          json={"to_stage": "lost", "lost_reason_id": reason},
                          headers={**h, **_key()})
    assert r.status_code == 200, r.text
    listed = await client.get(f"{V1}/users/{leaver['id']}", headers=h)
    assert listed.json()["data"]["open_leads"] == 2

    self_ = await client.post(f"{V1}/users/{leaver['id']}/handover",
                              json={"to_user_id": leaver["id"]}, headers={**h, **_key()})
    assert self_.status_code == 422 and "to_user_id" in self_.json()["error"]["fields"]
    cannot_edit = await client.post(f"{V1}/users/{leaver['id']}/handover",
                                    json={"to_user_id": watcher["id"]}, headers={**h, **_key()})
    assert cannot_edit.status_code == 422, cannot_edit.text
    assert cannot_edit.json()["error"]["fields"] == {"to_user_id": "not assignable by you"}
    # a batch of one: deactivating while a lead remains is refused, and the batch it
    # moved is rolled back with the 422; without the flag the calls drain the queue
    monkeypatch.setattr(users_service, "HANDOVER_BATCH", 1)
    too_soon = await client.post(f"{V1}/users/{leaver['id']}/handover",
                                 json={"to_user_id": target["id"], "deactivate": True},
                                 headers={**h, **_key()})
    assert too_soon.status_code == 422, too_soon.text
    assert "deactivate" in too_soon.json()["error"]["fields"]
    assert (await client.get(f"{V1}/users/{leaver['id']}", headers=h)
            ).json()["data"]["open_leads"] == 2
    key = _key()
    r = await client.post(f"{V1}/users/{leaver['id']}/handover",
                          json={"to_user_id": target["id"]}, headers={**h, **key})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"leads_moved": 1, "remaining": 1, "tasks_moved": 0,
                                  "deactivated": False}
    replay = await client.post(f"{V1}/users/{leaver['id']}/handover",
                               json={"to_user_id": target["id"]}, headers={**h, **key})
    assert replay.json() == r.json()   # the same key moves nothing more
    monkeypatch.setattr(users_service, "HANDOVER_BATCH", 500)
    r = await client.post(f"{V1}/users/{leaver['id']}/handover",
                          json={"to_user_id": target["id"]}, headers={**h, **_key()})
    assert r.json()["data"] == {"leads_moved": 1, "remaining": 0, "tasks_moved": 0,
                                  "deactivated": False}
    owned = await client.get(f"{V1}/leads", params={"owner_user_id": target["id"]}, headers=h)
    assert {x["id"] for x in owned.json()["data"]} == set(leads[:2])
    timeline = await client.get(f"{V1}/leads/{leads[0]}/timeline", headers=h)
    kinds = [e["kind"] for e in timeline.json()["data"]]
    assert kinds.count("lead.assigned") == 2   # the assign, then the handover

    done = await client.post(f"{V1}/users/{leaver['id']}/handover",
                             json={"to_user_id": target["id"], "deactivate": True},
                             headers={**h, **_key()})
    assert done.status_code == 200, done.text
    assert done.json()["data"] == {"leads_moved": 0, "remaining": 0, "tasks_moved": 0,
                                     "deactivated": True}
    assert (await client.get(f"{V1}/users/{leaver['id']}", headers=h)
            ).json()["data"]["is_active"] is False


async def test_delete_refuses_open_leads_then_soft_deletes(client: httpx.AsyncClient,
                                                           admin: Admin) -> None:
    h = await _auth(client, admin.user)
    leaver = await _create(client, h, _staff_body(admin))
    target = await _create(client, h, _staff_body(admin))
    lid = await _lead(client, h, admin)
    await _assign(client, h, lid, leaver["id"])
    r = await client.delete(f"{V1}/users/{leaver['id']}", headers={**h, **_key()})
    assert r.status_code == 422 and "open_leads" in r.json()["error"]["fields"]
    assert (await client.post(f"{V1}/users/{leaver['id']}/handover",
                              json={"to_user_id": target["id"]},
                              headers={**h, **_key()})).status_code == 200
    assert (await client.delete(f"{V1}/users/{leaver['id']}",
                                headers={**h, **_key()})).status_code == 204
    assert (await client.delete(f"{V1}/users/{leaver['id']}",
                                headers={**h, **_key()})).status_code == 204
    listed = await client.get(f"{V1}/users", params={"q": leaver["email"]}, headers=h)
    assert listed.json()["data"] == []
    detail = await client.get(f"{V1}/users/{leaver['id']}", headers=h)
    assert detail.status_code == 200 and detail.json()["data"]["deleted_at"] is not None
    me = await client.delete(f"{V1}/users/{admin.user.id}", headers={**h, **_key()})
    assert me.status_code == 422 and "id" in me.json()["error"]["fields"]


@pytest.mark.parametrize("principal", [SYSTEM_ID, INTAKE_ID], ids=["system", "intake"])
async def test_the_principals_are_never_listed_and_never_administrable(
        client: httpx.AsyncClient, admin: Admin, principal: str) -> None:
    """Rule 19, and code review F-3: the website's intake account is a principal
    too. Deleting it, or handing leads to it, would strand the public form's leads."""
    h = await _auth(client, admin.user)
    page = await client.get(f"{V1}/users", params={"limit": 100}, headers=h)
    assert principal not in {u["id"] for u in page.json()["data"]}
    assert (await client.get(f"{V1}/users/{principal}", headers=h)).status_code == 404
    for method, path, body in (
        ("PATCH", "", {"full_name": "x"}),
        ("POST", "/password", {"password": TEMP}),
        ("POST", "/sessions/revoke", None),
        ("POST", "/unlock", None),
        ("POST", "/handover", {"to_user_id": admin.user.id}),
        ("DELETE", "", None),
    ):
        r = await client.request(method, f"{V1}/users/{principal}{path}", json=body,
                                 headers={**h, **_key()})
        assert r.status_code == 422, (method, path, r.text)
        assert "id" in r.json()["error"]["fields"], (method, path, r.text)
    r = await client.post(f"{V1}/users/{admin.user.id}/handover", json={"to_user_id": principal},
                          headers={**h, **_key()})
    assert r.status_code == 422 and "to_user_id" in r.json()["error"]["fields"], r.text


async def test_an_unknown_person_is_404_on_every_action(client: httpx.AsyncClient,
                                                        admin: Admin) -> None:
    h = await _auth(client, admin.user)
    nobody = str(uuid.uuid4())
    assert (await client.get(f"{V1}/users/{nobody}", headers=h)).status_code == 404
    for method, path, body in (
        ("PATCH", "", {"full_name": "x"}),
        ("POST", "/password", {"password": TEMP}),
        ("POST", "/sessions/revoke", None),
        ("POST", "/unlock", None),
        ("POST", "/handover", {"to_user_id": admin.user.id}),
        ("DELETE", "", None),
    ):
        r = await client.request(method, f"{V1}/users/{nobody}{path}", json=body,
                                 headers={**h, **_key()})
        assert r.status_code == 404, (method, path, r.text)


async def test_a_viewer_sees_the_list_but_not_lockout_or_sessions(
        client: httpx.AsyncClient, admin: Admin) -> None:
    """RBAC 6.4: the Board holds users.view at global and no users.edit."""
    h = await _auth(client, admin.user)
    board = await _create(client, h, _staff_body(admin, role="board"))
    theirs = await _complete_forced_change(client, board["email"])
    r = await client.get(f"{V1}/users", headers=theirs)
    assert r.status_code == 200 and admin.user.id in {u["id"] for u in r.json()["data"]}
    detail = await client.get(f"{V1}/users/{admin.user.id}", headers=theirs)
    assert detail.status_code == 200
    assert detail.json()["data"]["locked_until"] is None
    assert detail.json()["data"]["active_sessions"] is None
    assert (await client.post(f"{V1}/users/{admin.user.id}/sessions/revoke",
                              headers={**theirs, **_key()})).status_code == 403


async def test_the_roles_lookup_lists_sixteen_and_never_system(client: httpx.AsyncClient,
                                                              staff: Staff) -> None:
    h = await _auth(client, staff)
    r = await client.get(f"{V1}/lookups/roles", headers=h)
    assert r.status_code == 200
    roles = r.json()["data"]
    codes = [x["code"] for x in roles]
    assert len(codes) == 16 and "system" not in codes
    assert not any(c.startswith("api_") for c in codes)
    assert {x["code"] for x in roles if x["is_portal"]} == {"distributor", "dealer", "sub_dealer"}
    assert next(x for x in roles if x["code"] == "field_officer")["level"] == 1


async def test_the_list_filters_and_pages(client: httpx.AsyncClient, admin: Admin) -> None:
    h = await _auth(client, admin.user)
    people = [await _create(client, h, _staff_body(admin, full_name=f"Page {i}"))
              for i in range(3)]
    first = await client.get(f"{V1}/users", headers=h,
                             params={"limit": 2, "org_unit_id": admin.user.org_unit_id})
    assert first.status_code == 200 and len(first.json()["data"]) == 2
    cursor = first.json()["meta"]["next_cursor"]
    assert cursor
    second = await client.get(f"{V1}/users", params={"limit": 2, "cursor": cursor,
                                                     "org_unit_id": admin.user.org_unit_id},
                              headers=h)
    assert second.status_code == 200
    seen = {u["id"] for u in first.json()["data"]} | {u["id"] for u in second.json()["data"]}
    assert {p["id"] for p in people} <= seen
    by_role = await client.get(f"{V1}/users", params={"role": "field_officer", "q": "Page 1"},
                               headers=h)
    assert [u["full_name"] for u in by_role.json()["data"]] == ["Page 1"]
    bad = await client.get(f"{V1}/users", params={"cursor": "not-a-cursor"}, headers=h)
    assert bad.status_code == 422


# ── a scoped administrator: enforcer 1 with a scope that excludes something ───

async def test_a_scoped_administrator_reaches_its_own_subtree_only(
        client: httpx.AsyncClient, admin: Admin, scoped_admin: Staff) -> None:
    """Code review F-2. Every other people test runs as a global admin, which never
    exercises the service predicate. Here the users scope is org_subtree: the
    people in the parent office are invisible, every action on them is 404 (not
    403), and a create into the parent office is refused by field."""
    h = await _auth(client, admin.user)
    outside = await _create(client, h, _staff_body(admin, full_name="Outside"))
    s = await _auth(client, scoped_admin)
    inside = await _create(client, s, _staff_body(admin, full_name="Inside",
                                                  org_unit_id=scoped_admin.org_unit_id))
    listed = await client.get(f"{V1}/users", params={"limit": 100}, headers=s)
    assert listed.status_code == 200, listed.text
    ids = {u["id"] for u in listed.json()["data"]}
    assert {scoped_admin.id, inside["id"]} <= ids
    assert outside["id"] not in ids and admin.user.id not in ids

    assert (await client.get(f"{V1}/users/{outside['id']}", headers=s)).status_code == 404
    assert (await client.get(f"{V1}/users/{inside['id']}", headers=s)).status_code == 200
    for method, path, body in (
        ("PATCH", "", {"full_name": "x"}),
        ("POST", "/password", {"password": TEMP}),
        ("POST", "/sessions/revoke", None),
        ("POST", "/unlock", None),
        ("POST", "/handover", {"to_user_id": inside["id"]}),
    ):
        r = await client.request(method, f"{V1}/users/{outside['id']}{path}", json=body,
                                 headers={**s, **_key()})
        assert r.status_code == 404, (method, path, r.text)
    # the same actions on a person inside the subtree work
    r = await client.post(f"{V1}/users/{inside['id']}/sessions/revoke", headers={**s, **_key()})
    assert r.status_code == 200, r.text

    # a create or a move into the parent office is outside the caller's scope
    r = await client.post(f"{V1}/users", json=_staff_body(admin), headers={**s, **_key()})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["fields"] == {"org_unit_id": "outside your scope"}
    r = await client.patch(f"{V1}/users/{inside['id']}",
                           json={"org_unit_id": admin.user.org_unit_id}, headers={**s, **_key()})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["fields"] == {"org_unit_id": "outside your scope"}


async def test_a_temporary_password_is_hashed_as_typed(client: httpx.AsyncClient,
                                                       admin: Admin) -> None:
    """Cross-vendor P2-5: model-wide whitespace stripping trimmed the password
    before hashing while sign-in kept the spaces, so the password the admin
    passed on never worked."""
    h = await _auth(client, admin.user)
    spaced = " " + TEMP + " "
    person = await _create(client, h, _staff_body(admin, password=spaced))
    r = await client.post(f"{V1}/auth/login", json={"email": person["email"], "password": spaced})
    assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/auth/login", json={"email": person["email"], "password": TEMP})
    assert r.status_code == 401


async def test_a_role_that_needs_a_territory_is_refused_on_a_person_without_one(
        client: httpx.AsyncClient, admin: Admin) -> None:
    """Cross-vendor P2-6: a role change without territory_ids is checked against
    the set the person already holds, not only against a replacement."""
    h = await _auth(client, admin.user)
    person = await _create(client, h, _staff_body(admin))   # a field officer, no territories
    r = await client.patch(f"{V1}/users/{person['id']}", json={"role": "state_coordinator"},
                           headers={**h, **_key()})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["fields"] == {
        "territory_ids": "this role needs at least one territory"}
    r = await client.patch(f"{V1}/users/{person['id']}",
                           json={"role": "state_coordinator",
                                 "territory_ids": [admin.territory_id]},
                           headers={**h, **_key()})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"]["code"] == "state_coordinator"
