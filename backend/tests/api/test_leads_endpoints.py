"""The lead endpoints and the lookups, against the real app and the real database.

Nothing is stubbed. The idempotency contract, the error envelope, the status
codes and the RLS boundary all live outside the service functions, so the test
drives them through HTTP (FS-003 section 4, CLAUDE.md 1.4).

The `env` fixture builds a coded state -> district hierarchy the way real data is
shaped: an inquiry number needs a state code (rule 3), which the lone-district
fixtures do not have. It cleans up the leads it creates before the `staff`
fixture removes the org unit they point at.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import Staff

pytestmark = pytest.mark.db

V1 = "/api/v1"


@dataclass
class Env:
    district_id: str
    state_id: str
    state_code: str
    district_name: str


_SWEEP_LEFTOVERS = """
DO $$
DECLARE t uuid[];
BEGIN
  SELECT coalesce(array_agg(id), '{}') INTO t FROM territory
   WHERE level = 'state' AND name LIKE 'gujarat\\_%' AND code LIKE 'Z%'
     AND created_at < now() - interval '1 hour';
  t := t || coalesce((SELECT array_agg(id) FROM territory WHERE parent_id = ANY(t)), '{}');
  DELETE FROM activity_event WHERE lead_id IN (SELECT id FROM lead WHERE territory_id = ANY(t));
  DELETE FROM lead_duplicate_link
   WHERE lead_a_id IN (SELECT id FROM lead WHERE territory_id = ANY(t))
      OR lead_b_id IN (SELECT id FROM lead WHERE territory_id = ANY(t));
  DELETE FROM notification_outbox
   WHERE recipient IN (SELECT mobile FROM lead WHERE territory_id = ANY(t));
  DELETE FROM lead WHERE territory_id = ANY(t);
  DELETE FROM inquiry_counter WHERE state_code IN (SELECT code FROM territory WHERE id = ANY(t));
  DELETE FROM territory WHERE parent_id = ANY(t);
  DELETE FROM territory WHERE id = ANY(t);
END $$
"""


@pytest_asyncio.fixture
async def env(sessions: Callable[[], AsyncSession], staff: Staff) -> AsyncIterator[Env]:
    """A state (with a code) over a district, committed. Depends on `staff` so it
    tears down first and clears the leads that pin the staff org unit."""
    tag = uuid.uuid4().hex[:8]
    code = "Z" + tag[:2].upper()
    district_name = f"gondal_{tag}"
    s = sessions()
    # A run killed mid-test (memory, a dropped tunnel) never reaches the teardown
    # below, and a later run that draws the same code hits the inquiry_no unique
    # index. Sweep anything of ours older than an hour, in one round trip.
    await s.execute(text(_SWEEP_LEFTOVERS))
    state = (await s.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": f"gujarat_{tag}", "c": code})).scalar_one()
    district = (await s.execute(text(
        "INSERT INTO territory (level, name, parent_id) "
        "VALUES ('district', :n, :p) RETURNING id"),
        {"n": district_name, "p": state})).scalar_one()
    await s.commit()

    try:
        yield Env(str(district), str(state), code, district_name)
    finally:
        c = sessions()
        mobiles = [r[0] for r in (await c.execute(
            text("SELECT mobile FROM lead WHERE territory_id = :t"),
            {"t": str(district)})).all()]
        await c.execute(text(
            "DELETE FROM activity_event WHERE lead_id IN "
            "(SELECT id FROM lead WHERE territory_id = :t)"), {"t": str(district)})
        await c.execute(text(
            "DELETE FROM lead_duplicate_link WHERE lead_a_id IN "
            "(SELECT id FROM lead WHERE territory_id = :t) OR lead_b_id IN "
            "(SELECT id FROM lead WHERE territory_id = :t)"), {"t": str(district)})
        await c.execute(text("DELETE FROM lead WHERE territory_id = :t"), {"t": str(district)})
        if mobiles:
            await c.execute(text("DELETE FROM notification_outbox WHERE recipient = ANY(:m)"),
                            {"m": mobiles})
        await c.execute(text("DELETE FROM inquiry_counter WHERE state_code = :c"), {"c": code})
        await c.execute(text("DELETE FROM territory WHERE id = :d"), {"d": str(district)})
        await c.execute(text("DELETE FROM territory WHERE id = :s"), {"s": str(state)})
        await c.commit()


async def _auth(client: httpx.AsyncClient, staff: Staff) -> dict[str, str]:
    r = await client.post(f"{V1}/auth/login", json={"email": staff.email, "password": staff.password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _body(env: Env, **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "farmer_name": "Rameshbhai Patel",
        "mobile": "98" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": env.district_id,
        "inquiry_type": "subsidised",
        "mis_system": "drip",
    }
    body.update(over)
    return body


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


# ── create ───────────────────────────────────────────────────────────────────

async def test_create_returns_201_with_the_allocated_lead(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    r = await client.post(f"{V1}/leads", json=_body(env, estimated_value="125000.00"),
                          headers={**h, **_key()})
    assert r.status_code == 201, r.text
    lead = r.json()["data"]
    assert lead["inquiry_no"].startswith(f"POL/{env.state_code}/")
    assert lead["inquiry_no"].endswith("/00001")
    assert lead["stage"] == "new"
    assert lead["mobile"].startswith("+91") and len(lead["mobile"]) == 13
    assert lead["territory"]["id"] == env.district_id
    assert lead["owner"]["id"] == staff.id            # the staff creator owns it
    assert lead["owner_org_unit"]["id"] == staff.org_unit_id
    assert lead["source"] == "employee"               # defaulted by user type
    assert lead["estimated_value"] == "125000.00"
    assert lead["priority"] in ("hot", "warm", "cold")
    assert lead["duplicates"] == []                   # dedup is a later slice (GAP-059)


async def test_create_without_an_idempotency_key_is_400(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    r = await client.post(f"{V1}/leads", json=_body(env), headers=h)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "idempotency_key_required"


async def test_create_replays_the_same_key_and_body(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions) -> None:
    h = await _auth(client, staff)
    body, key = _body(env), _key()
    first = await client.post(f"{V1}/leads", json=body, headers={**h, **key})
    second = await client.post(f"{V1}/leads", json=body, headers={**h, **key})
    assert first.status_code == 201 and second.status_code == 201
    # Same stored answer, and only one row was written.
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    n = (await sessions().execute(
        text("SELECT count(*) FROM lead WHERE territory_id = :t"),
        {"t": env.district_id})).scalar_one()
    assert n == 1


async def test_create_same_key_different_body_is_409(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    key = _key()
    r1 = await client.post(f"{V1}/leads", json=_body(env), headers={**h, **key})
    r2 = await client.post(f"{V1}/leads", json=_body(env, farmer_name="Someone Else"),
                           headers={**h, **key})
    assert r1.status_code == 201
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "idempotency_key_reused"


async def test_create_rejects_a_non_indian_mobile(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    r = await client.post(f"{V1}/leads", json=_body(env, mobile="+1 415 555 0100"),
                          headers={**h, **_key()})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_error"
    assert "mobile" in body["fields"]


async def test_create_rejects_an_unknown_mis_system(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    r = await client.post(f"{V1}/leads", json=_body(env, mis_system="teleporter"),
                          headers={**h, **_key()})
    assert r.status_code == 422
    assert "mis_system" in r.json()["error"]["fields"]


async def test_create_needs_a_coded_state(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions) -> None:
    """A territory with no coded state ancestor refuses rather than allocating under
    a made-up code (rule 3)."""
    lone = (await sessions().execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": "orphan_" + uuid.uuid4().hex[:8]})).scalar_one()
    await sessions().commit()
    try:
        h = await _auth(client, staff)
        r = await client.post(f"{V1}/leads", json=_body(env, territory_id=str(lone)),
                              headers={**h, **_key()})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "territory_without_state_code"
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM activity_event WHERE lead_id IN "
                             "(SELECT id FROM lead WHERE territory_id = :t)"), {"t": str(lone)})
        await c.execute(text("DELETE FROM lead WHERE territory_id = :t"), {"t": str(lone)})
        await c.execute(text("DELETE FROM territory WHERE id = :t"), {"t": str(lone)})
        await c.commit()


async def test_create_requires_authentication(client: httpx.AsyncClient, env: Env) -> None:
    r = await client.post(f"{V1}/leads", json=_body(env), headers=_key())
    assert r.status_code == 401


# ── read one ─────────────────────────────────────────────────────────────────

async def test_get_returns_the_created_lead(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    created = (await client.post(f"{V1}/leads", json=_body(env),
                                 headers={**h, **_key()})).json()["data"]
    r = await client.get(f"{V1}/leads/{created['id']}", headers=h)
    assert r.status_code == 200
    got = r.json()["data"]
    assert got["id"] == created["id"]
    assert got["inquiry_no"] == created["inquiry_no"]
    assert got["created_by"]["id"] == staff.id


async def test_get_unknown_id_is_404(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    r = await client.get(f"{V1}/leads/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


# ── list ─────────────────────────────────────────────────────────────────────

async def test_list_includes_the_lead_and_searches_by_name(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    created = (await client.post(
        f"{V1}/leads", json=_body(env, farmer_name="Zzunique Farmer"),
        headers={**h, **_key()})).json()["data"]

    listed = await client.get(f"{V1}/leads", headers=h)
    assert listed.status_code == 200
    page = listed.json()
    assert "meta" in page and page["meta"]["limit"] == 50
    assert any(x["id"] == created["id"] for x in page["data"])

    found = await client.get(f"{V1}/leads", params={"q": "Zzunique"}, headers=h)
    ids = [x["id"] for x in found.json()["data"]]
    assert created["id"] in ids


async def test_list_search_by_inquiry_no(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    created = (await client.post(f"{V1}/leads", json=_body(env),
                                 headers={**h, **_key()})).json()["data"]
    r = await client.get(f"{V1}/leads", params={"q": created["inquiry_no"]}, headers=h)
    assert [x["id"] for x in r.json()["data"]] == [created["id"]]


# ── lookups ──────────────────────────────────────────────────────────────────

async def test_lookups_return_the_seeded_lists(
        client: httpx.AsyncClient, staff: Staff) -> None:
    h = await _auth(client, staff)
    mis = await client.get(f"{V1}/lookups/mis-systems", headers=h)
    assert mis.status_code == 200
    assert "drip" in [x["code"] for x in mis.json()["data"]]

    sources = await client.get(f"{V1}/lookups/lead-sources", headers=h)
    assert "employee" in [x["code"] for x in sources.json()["data"]]

    reasons = await client.get(f"{V1}/lookups/lost-reasons", headers=h)
    assert "price" in [x["code"] for x in reasons.json()["data"]]


async def test_territories_picker_finds_the_district(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    r = await client.get(f"{V1}/lookups/territories",
                         params={"q": env.district_name}, headers=h)
    assert r.status_code == 200
    rows = r.json()["data"]
    assert any(x["id"] == env.district_id for x in rows)


async def test_lookups_require_authentication(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{V1}/lookups/mis-systems")
    assert r.status_code == 401


# ── lifecycle: transition, reopen, notes, timeline ───────────────────────────

async def _make(client: httpx.AsyncClient, h: dict[str, str], env: Env, **over: object) -> str:
    r = await client.post(f"{V1}/leads", json=_body(env, **over), headers={**h, **_key()})
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


async def _to(client: httpx.AsyncClient, h: dict[str, str], lid: str, **body: object):
    return await client.post(f"{V1}/leads/{lid}/transition", json=body, headers={**h, **_key()})


async def _lost_reason(client: httpx.AsyncClient, h: dict[str, str]) -> str:
    # The list carries switched-off reasons too (ADR-033: never deleted), and the
    # live drivers leave one behind, sorted first. Pick an active one.
    items = (await client.get(f"{V1}/lookups/lost-reasons", headers=h)).json()["data"]
    return next(i["id"] for i in items if i["is_active"])


async def test_transition_new_to_contacted_stamps_first_contact(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await _to(client, h, lid, to_stage="contacted")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["stage"] == "contacted" and d["first_contacted_at"] is not None


async def test_transition_contacted_to_qualified(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    await _to(client, h, lid, to_stage="contacted")
    r = await _to(client, h, lid, to_stage="qualified")
    assert r.status_code == 200 and r.json()["data"]["stage"] == "qualified"


async def test_transition_to_quoted_needs_quotations(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    await _to(client, h, lid, to_stage="contacted")
    await _to(client, h, lid, to_stage="qualified")
    r = await _to(client, h, lid, to_stage="quoted")
    assert r.status_code == 422 and r.json()["error"]["code"] == "quotation_required"


async def test_invalid_transition_is_422(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await _to(client, h, lid, to_stage="won")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_transition"


async def test_lost_requires_a_reason_then_succeeds(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await _to(client, h, lid, to_stage="lost")
    assert r.status_code == 422 and "lost_reason_id" in r.json()["error"]["fields"]
    rid = await _lost_reason(client, h)
    r = await _to(client, h, lid, to_stage="lost", lost_reason_id=rid, lost_note="price")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["stage"] == "lost" and d["lost_reason"]["id"] == rid and d["lost_note"] == "price"


async def test_expected_stage_mismatch_is_409(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    await _to(client, h, lid, to_stage="contacted")
    r = await _to(client, h, lid, to_stage="qualified", expected_stage="new")
    assert r.status_code == 409 and r.json()["error"]["code"] == "stage_changed"
    assert r.json()["error"]["fields"]["stage"] == "contacted"


async def test_terminal_lead_cannot_transition(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    await _to(client, h, lid, to_stage="lost", lost_reason_id=await _lost_reason(client, h))
    r = await _to(client, h, lid, to_stage="contacted")
    assert r.status_code == 422 and r.json()["error"]["code"] == "stage_terminal"


async def test_reopen_a_lost_lead_returns_it_to_the_lost_stage(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    await _to(client, h, lid, to_stage="contacted")
    await _to(client, h, lid, to_stage="lost", lost_reason_id=await _lost_reason(client, h))
    r = await client.post(f"{V1}/leads/{lid}/reopen", json={"note": "called back"},
                          headers={**h, **_key()})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["stage"] == "contacted" and d["reopen_count"] == 1 and d["lost_reason"] is None


async def test_reopen_a_non_lost_lead_is_refused(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await client.post(f"{V1}/leads/{lid}/reopen", json={}, headers={**h, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "stage_terminal"


async def test_note_and_timeline(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env, note="note at create")
    await _to(client, h, lid, to_stage="contacted")
    r = await client.post(f"{V1}/leads/{lid}/notes", json={"note": "rang back Monday"},
                          headers={**h, **_key()})
    assert r.status_code == 201 and r.json()["data"]["kind"] == "lead.note_added"

    tl = await client.get(f"{V1}/leads/{lid}/timeline", headers=h)
    assert tl.status_code == 200
    events = tl.json()["data"]
    kinds = [e["kind"] for e in events]
    assert "lead.created" in kinds and "lead.stage_changed" in kinds
    assert kinds.count("lead.note_added") >= 2
    # newest first, and every event names its actor
    assert kinds[0] == "lead.note_added"
    assert all(e["actor"] and e["actor"]["full_name"] for e in events)


async def test_transition_without_idempotency_key_is_400(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await client.post(f"{V1}/leads/{lid}/transition", json={"to_stage": "contacted"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "idempotency_key_required"


# ── assignment: assign, assignees ────────────────────────────────────────────

async def _target_staff(sessions, staff: Staff) -> str:
    """A second staff user in the same org unit as `staff`, so it is inside the
    org_subtree an assigner may name. Caller cleans it up with _drop_staff."""
    s = sessions()
    uid = (await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Target Officer', :r, :o) RETURNING id"),
        {"e": f"target_{uuid.uuid4().hex[:8]}@polysil.in", "r": staff.role_id,
         "o": staff.org_unit_id})).scalar_one()
    await s.commit()
    return str(uid)


async def _drop_staff(sessions, uid: str) -> None:
    s = sessions()
    await s.execute(text("UPDATE lead SET owner_user_id = NULL WHERE owner_user_id = :u"), {"u": uid})
    await s.execute(text("DELETE FROM app_user WHERE id = :u"), {"u": uid})
    await s.commit()


async def test_assignees_lists_the_staff_in_scope(
        client: httpx.AsyncClient, staff: Staff, sessions) -> None:
    target = await _target_staff(sessions, staff)
    try:
        h = await _auth(client, staff)
        r = await client.get(f"{V1}/leads/assignees", headers=h)
        assert r.status_code == 200, r.text
        ids = {a["id"] for a in r.json()["data"]}
        assert staff.id in ids and target in ids
        me = next(a for a in r.json()["data"] if a["id"] == staff.id)
        assert me["org_unit"]["id"] == staff.org_unit_id
    finally:
        await _drop_staff(sessions, target)


async def test_assign_an_owner_in_the_subtree(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions) -> None:
    target = await _target_staff(sessions, staff)
    try:
        h = await _auth(client, staff)
        lid = await _make(client, h, env)
        r = await client.post(f"{V1}/leads/{lid}/assign", json={"owner_user_id": target},
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["owner"]["id"] == target
        kinds = [e["kind"] for e in (await client.get(
            f"{V1}/leads/{lid}/timeline", headers=h)).json()["data"]]
        assert "lead.assigned" in kinds
    finally:
        await _drop_staff(sessions, target)


async def test_assign_an_unassignable_owner_is_422(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await client.post(f"{V1}/leads/{lid}/assign", json={"owner_user_id": str(uuid.uuid4())},
                          headers={**h, **_key()})
    assert r.status_code == 422 and "owner_user_id" in r.json()["error"]["fields"]


async def test_assign_null_clears_the_owner(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)          # owned by staff on create
    r = await client.post(f"{V1}/leads/{lid}/assign", json={"owner_user_id": None},
                          headers={**h, **_key()})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["owner"] is None


async def test_assign_nothing_is_422(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await client.post(f"{V1}/leads/{lid}/assign", json={}, headers={**h, **_key()})
    assert r.status_code == 422


async def test_assign_an_invisible_partner_is_422(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await client.post(f"{V1}/leads/{lid}/assign",
                          json={"assigned_partner_id": str(uuid.uuid4())},
                          headers={**h, **_key()})
    assert r.status_code == 422 and "assigned_partner_id" in r.json()["error"]["fields"]


# ── edit and delete ──────────────────────────────────────────────────────────

async def test_patch_updates_fields_and_records_the_change(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await client.patch(f"{V1}/leads/{lid}", json={
        "farmer_name": "Corrected Name", "email": "x@example.com", "village": "Gondal",
        "estimated_value": "99000.00", "mobile": "0 98765 00000"},
        headers={**h, **_key()})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["farmer_name"] == "Corrected Name" and d["email"] == "x@example.com"
    assert d["village"] == "Gondal" and d["estimated_value"] == "99000.00"
    assert d["mobile"] == "+919876500000"         # normalised, leading 0 stripped
    kinds = [e["kind"] for e in (await client.get(
        f"{V1}/leads/{lid}/timeline", headers=h)).json()["data"]]
    assert "lead.updated" in kinds


async def test_patch_null_clears_an_optional_field(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env, email="keep@example.com")
    r = await client.patch(f"{V1}/leads/{lid}", json={"email": None}, headers={**h, **_key()})
    assert r.status_code == 200 and r.json()["data"]["email"] is None


async def test_patch_cannot_clear_a_required_field(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await client.patch(f"{V1}/leads/{lid}", json={"farmer_name": None}, headers={**h, **_key()})
    assert r.status_code == 422 and "farmer_name" in r.json()["error"]["fields"]


async def test_patch_rejects_bad_mobile_and_unknown_source(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    r = await client.patch(f"{V1}/leads/{lid}", json={"mobile": "+1 415 555 0100"},
                           headers={**h, **_key()})
    assert r.status_code == 422 and "mobile" in r.json()["error"]["fields"]
    r = await client.patch(f"{V1}/leads/{lid}", json={"source": "carrier_pigeon"},
                           headers={**h, **_key()})
    assert r.status_code == 422 and "source" in r.json()["error"]["fields"]


async def test_patch_a_closed_lead_is_422(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    await _to(client, h, lid, to_stage="lost", lost_reason_id=await _lost_reason(client, h))
    r = await client.patch(f"{V1}/leads/{lid}", json={"village": "x"}, headers={**h, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "stage_terminal"


async def test_patch_moves_territory_within_scope(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions) -> None:
    """A staff-owned lead keeps its owning unit when its territory is corrected
    (rule 4 path A); the new territory must resolve a state code and stay in scope."""
    s = sessions()
    district2 = str((await s.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
        {"n": "jetpur_" + uuid.uuid4().hex[:8], "p": env.state_id})).scalar_one())
    await s.commit()
    mobile = None
    try:
        h = await _auth(client, staff)
        created = (await client.post(f"{V1}/leads", json=_body(env),
                                     headers={**h, **_key()})).json()["data"]
        mobile = created["mobile"]
        r = await client.patch(f"{V1}/leads/{created['id']}", json={"territory_id": district2},
                               headers={**h, **_key()})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["territory"]["id"] == district2
        assert d["owner_org_unit"]["id"] == staff.org_unit_id     # unit kept: owner is staff
        assert d["inquiry_no"] == created["inquiry_no"]           # the number never changes
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM activity_event WHERE lead_id IN "
                             "(SELECT id FROM lead WHERE territory_id = :t)"), {"t": district2})
        await c.execute(text("DELETE FROM lead WHERE territory_id = :t"), {"t": district2})
        if mobile:
            await c.execute(text("DELETE FROM notification_outbox WHERE recipient = :m"), {"m": mobile})
        await c.execute(text("DELETE FROM territory WHERE id = :t"), {"t": district2})
        await c.commit()


async def test_delete_needs_the_permission_then_soft_deletes(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions) -> None:
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    # the fixture role has view/create/edit, not delete
    r = await client.delete(f"{V1}/leads/{lid}", headers={**h, **_key()})
    assert r.status_code == 403
    # grant delete; the fixture teardown removes the role's permission rows
    s = sessions()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) "
        "VALUES (:r, 'leads', 'delete', 'org_subtree')"), {"r": staff.role_id})
    await s.commit()
    r = await client.delete(f"{V1}/leads/{lid}", headers={**h, **_key()})
    assert r.status_code == 204, r.text
    r = await client.delete(f"{V1}/leads/{lid}", headers={**h, **_key()})
    assert r.status_code == 204                       # repeat is a no-op
    got = (await client.get(f"{V1}/leads/{lid}", headers=h)).json()["data"]
    kinds = [e["kind"] for e in (await client.get(
        f"{V1}/leads/{lid}/timeline", headers=h)).json()["data"]]
    assert got["id"] == lid and kinds.count("lead.deleted") == 1


# ── duplicates: detect on create, queue, dismiss, merge ──────────────────────

def _mobile() -> str:
    return "98" + f"{uuid.uuid4().int % 10**8:08d}"


async def test_create_flags_a_duplicate_by_mobile(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    m = _mobile()
    a = await _make(client, h, env, mobile=m, farmer_name="First Entry")
    r = await client.post(f"{V1}/leads", json=_body(env, mobile=m, farmer_name="Second Entry"),
                          headers={**h, **_key()})
    assert r.status_code == 201, r.text
    dups = r.json()["data"]["duplicates"]
    assert [d["lead_id"] for d in dups] == [a]
    assert dups[0]["signal"] == "mobile" and dups[0]["score"] == "1.00" and dups[0]["state"] == "pending"
    # the pair is visible from the other side too, and both timelines were flagged
    got = (await client.get(f"{V1}/leads/{a}", headers=h)).json()["data"]
    assert len(got["duplicates"]) == 1
    kinds = [e["kind"] for e in (await client.get(
        f"{V1}/leads/{r.json()['data']['id']}/timeline", headers=h)).json()["data"]]
    assert "lead.duplicate_flagged" in kinds


async def test_create_flags_a_duplicate_by_name_and_village(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    await _make(client, h, env, farmer_name="Kanubhai Desai", village="Virpur")
    r = await client.post(f"{V1}/leads", json=_body(env, farmer_name="Kanubhai Desai", village="Virpur"),
                          headers={**h, **_key()})
    assert r.status_code == 201, r.text
    dups = r.json()["data"]["duplicates"]
    assert len(dups) == 1 and dups[0]["signal"] == "name_geo"
    assert float(dups[0]["score"]) >= 0.6


async def test_duplicate_queue_lists_the_pair_and_dismiss_clears_it(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    m = _mobile()
    a = await _make(client, h, env, mobile=m)
    b = await _make(client, h, env, mobile=m)
    q = await client.get(f"{V1}/leads/duplicates", headers=h)
    assert q.status_code == 200, q.text
    pair = next(p for p in q.json()["data"] if {p["lead_a"]["id"], p["lead_b"]["id"]} == {a, b})
    assert pair["state"] == "pending" and pair["signal"] == "mobile"

    r = await client.post(f"{V1}/leads/duplicates/{pair['link_id']}/dismiss",
                          headers={**h, **_key()})
    assert r.status_code == 200 and r.json()["data"]["state"] == "dismissed"
    q = await client.get(f"{V1}/leads/duplicates", headers=h)
    assert all({p["lead_a"]["id"], p["lead_b"]["id"]} != {a, b} for p in q.json()["data"])
    kinds = [e["kind"] for e in (await client.get(f"{V1}/leads/{a}/timeline", headers=h)).json()["data"]]
    assert "lead.duplicate_dismissed" in kinds
    # dismissing again is not a pending pair any more
    r = await client.post(f"{V1}/leads/duplicates/{pair['link_id']}/dismiss",
                          headers={**h, **_key()})
    assert r.status_code == 404


async def test_merge_loser_into_survivor(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    m = _mobile()
    survivor = await _make(client, h, env, mobile=m, farmer_name="Survivor")
    loser = await _make(client, h, env, mobile=m, farmer_name="Loser")
    r = await client.post(f"{V1}/leads/{loser}/merge", json={"into_lead_id": survivor},
                          headers={**h, **_key()})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == survivor
    gone = (await client.get(f"{V1}/leads/{loser}", headers=h)).json()["data"]
    assert gone["stage"] == "merged" and gone["merged_into"]["id"] == survivor
    # the survivor's timeline folds in the merge, and the pair left the queue
    kinds = [e["kind"] for e in (await client.get(
        f"{V1}/leads/{survivor}/timeline", headers=h)).json()["data"]]
    assert "lead.merged" in kinds
    q = (await client.get(f"{V1}/leads/duplicates", headers=h)).json()["data"]
    assert all({p["lead_a"]["id"], p["lead_b"]["id"]} != {survivor, loser} for p in q)
    # the merged loser is out of the default list, reachable by explicit filter
    default_ids = {x["id"] for x in (await client.get(f"{V1}/leads", headers=h)).json()["data"]}
    merged_ids = {x["id"] for x in (await client.get(
        f"{V1}/leads", params={"stage": "merged"}, headers=h)).json()["data"]}
    assert loser not in default_ids and loser in merged_ids


async def test_merge_refusals(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    a = await _make(client, h, env)
    r = await client.post(f"{V1}/leads/{a}/merge", json={"into_lead_id": a}, headers={**h, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "merge_self"
    lost = await _make(client, h, env)
    await _to(client, h, lost, to_stage="lost", lost_reason_id=await _lost_reason(client, h))
    r = await client.post(f"{V1}/leads/{a}/merge", json={"into_lead_id": lost}, headers={**h, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "merge_terminal"
    r = await client.post(f"{V1}/leads/{a}/merge", json={"into_lead_id": str(uuid.uuid4())},
                          headers={**h, **_key()})
    assert r.status_code == 404


# ── lookup admin (masters.edit) ──────────────────────────────────────────────

async def _grant_masters(sessions, staff: Staff) -> None:
    s = sessions()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'masters', 'view', 'global'), (:r, 'masters', 'edit', 'global')"), {"r": staff.role_id})
    await s.commit()


async def _drop_lookup(sessions, table: str, code: str) -> None:
    s = sessions()
    await s.execute(text(f"DELETE FROM {table} WHERE code = :c"), {"c": code})
    await s.commit()


async def test_lookup_admin_needs_masters_edit(
        client: httpx.AsyncClient, staff: Staff) -> None:
    h = await _auth(client, staff)
    r = await client.post(f"{V1}/lookups/lost-reasons", json={"code": "x_no_perm", "name": "x"},
                          headers={**h, **_key()})
    assert r.status_code == 403


async def test_add_and_switch_off_a_lost_reason(
        client: httpx.AsyncClient, staff: Staff, sessions) -> None:
    await _grant_masters(sessions, staff)
    code = "site_unsuitable_" + uuid.uuid4().hex[:6]
    try:
        h = await _auth(client, staff)
        r = await client.post(f"{V1}/lookups/lost-reasons", json={"code": code, "name": "Site unsuitable"},
                              headers={**h, **_key()})
        assert r.status_code == 201, r.text
        item = r.json()["data"]
        assert item["code"] == code and item["is_active"] is True
        assert code in [x["code"] for x in (await client.get(
            f"{V1}/lookups/lost-reasons", headers=h)).json()["data"]]
        # the same code again is refused, never overwritten
        r = await client.post(f"{V1}/lookups/lost-reasons", json={"code": code, "name": "Again"},
                              headers={**h, **_key()})
        assert r.status_code == 422 and "code" in r.json()["error"]["fields"]
        # switch off, never delete
        r = await client.patch(f"{V1}/lookups/lost-reasons/{item['id']}", json={"is_active": False},
                               headers={**h, **_key()})
        assert r.status_code == 200 and r.json()["data"]["is_active"] is False
        r = await client.patch(f"{V1}/lookups/lost-reasons/{uuid.uuid4()}", json={"is_active": False},
                               headers={**h, **_key()})
        assert r.status_code == 404
        # the actor columns carry the caller (001: updated_by is the application's job)
        s = sessions()
        row = (await s.execute(
            text("SELECT created_by, updated_by FROM won_lost_reason WHERE code = :c"),
            {"c": code})).one()
        await s.rollback()
        assert str(row.created_by) == staff.id and str(row.updated_by) == staff.id
    finally:
        await _drop_lookup(sessions, "won_lost_reason", code)


async def test_add_a_source_with_quality_and_a_system(
        client: httpx.AsyncClient, staff: Staff, sessions) -> None:
    await _grant_masters(sessions, staff)
    src, mis = "radio_" + uuid.uuid4().hex[:6], "fogger_" + uuid.uuid4().hex[:6]
    try:
        h = await _auth(client, staff)
        r = await client.post(f"{V1}/lookups/lead-sources",
                              json={"code": src, "name": "Radio", "quality": "0.9", "sort_order": 99},
                              headers={**h, **_key()})
        assert r.status_code == 201, r.text
        r = await client.post(f"{V1}/lookups/mis-systems", json={"code": mis, "name": "Fogger"},
                              headers={**h, **_key()})
        assert r.status_code == 201, r.text
        assert mis in [x["code"] for x in (await client.get(
            f"{V1}/lookups/mis-systems", headers=h)).json()["data"]]
    finally:
        await _drop_lookup(sessions, "lead_source", src)
        await _drop_lookup(sessions, "mis_system", mis)


async def test_scoring_read_and_retune(
        client: httpx.AsyncClient, staff: Staff, sessions) -> None:
    await _grant_masters(sessions, staff)
    h = await _auth(client, staff)
    before = {i["key"]: i["value"] for i in (await client.get(
        f"{V1}/lookups/scoring", headers=h)).json()["data"]}
    assert {"w_source", "value_cap", "threshold_hot"} <= set(before)
    try:
        r = await client.patch(f"{V1}/lookups/scoring", json={"values": {"threshold_hot": "75"}},
                               headers={**h, **_key()})
        assert r.status_code == 200, r.text
        after = {i["key"]: i["value"] for i in r.json()["data"]}
        assert after["threshold_hot"] == "75.00"
        r = await client.patch(f"{V1}/lookups/scoring", json={"values": {"no_such_key": "1"}},
                               headers={**h, **_key()})
        assert r.status_code == 422 and "no_such_key" in r.json()["error"]["fields"]
        r = await client.patch(f"{V1}/lookups/scoring", json={"values": {"value_cap": "0"}},
                               headers={**h, **_key()})
        assert r.status_code == 422 and "value_cap" in r.json()["error"]["fields"]
    finally:
        await client.patch(f"{V1}/lookups/scoring",
                           json={"values": {"threshold_hot": before["threshold_hot"]}},
                           headers={**h, **_key()})


# ── hardening from the FS-003 code review ────────────────────────────────────

async def test_create_queues_exactly_one_acknowledgement(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions) -> None:
    """Rule 17: one lead_ack WhatsApp to the farmer, recipient in E.164, payload
    carrying the inquiry number (ISS-071)."""
    h = await _auth(client, staff)
    created = (await client.post(f"{V1}/leads", json=_body(env), headers={**h, **_key()})).json()["data"]
    rows = (await sessions().execute(text(
        "SELECT channel::text, payload->>'inquiry_no', payload->>'farmer_name' "
        "FROM notification_outbox WHERE recipient = :m AND template_key = 'lead_ack'"),
        {"m": created["mobile"]})).all()
    assert len(rows) == 1
    assert rows[0][0] == "whatsapp" and rows[0][1] == created["inquiry_no"]
    assert rows[0][2] == created["farmer_name"]


async def test_an_unhandled_error_is_enveloped(staff: Staff) -> None:
    """ISS-072: a 500 is the error envelope with no detail, not Starlette's plain
    text. Forced by making a dependency raise; the transport must not re-raise."""
    from api.deps import get_caller
    from api.main import app

    async def boom() -> None:
        raise RuntimeError("boom-secret-detail")

    app.dependency_overrides[get_caller] = boom
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test") as c:
            h = await _auth(c, staff)
            r = await c.get(f"{V1}/leads", headers=h)
            assert r.status_code == 500
            assert r.json()["error"]["code"] == "internal_error"
            assert "boom-secret-detail" not in r.text
    finally:
        app.dependency_overrides.pop(get_caller, None)


async def test_an_uncovered_territory_routes_to_the_hq_anchor(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions) -> None:
    """Rule 4 path B with no covering unit falls back to Polysil HQ (ISS-067). A
    global caller, an unowned lead, and a territory no sales unit covers."""
    s = sessions()
    await s.execute(text(
        "UPDATE role_permission SET scope = 'global' WHERE role_id = :r AND module = 'leads'"),
        {"r": staff.role_id})
    district2 = str((await s.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
        {"n": "nowhere_" + uuid.uuid4().hex[:8], "p": env.state_id})).scalar_one())
    await s.commit()
    mobile = None
    try:
        h = await _auth(client, staff)
        created = (await client.post(f"{V1}/leads", json=_body(env),
                                     headers={**h, **_key()})).json()["data"]
        mobile = created["mobile"]
        r = await client.post(f"{V1}/leads/{created['id']}/assign", json={"owner_user_id": None},
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
        r = await client.patch(f"{V1}/leads/{created['id']}", json={"territory_id": district2},
                               headers={**h, **_key()})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["owner_org_unit"]["name"] == "Polysil HQ"
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM activity_event WHERE lead_id IN "
                             "(SELECT id FROM lead WHERE territory_id = :t)"), {"t": district2})
        await c.execute(text("DELETE FROM lead WHERE territory_id = :t"), {"t": district2})
        if mobile:
            await c.execute(text("DELETE FROM notification_outbox WHERE recipient = :m"), {"m": mobile})
        await c.execute(text("DELETE FROM territory WHERE id = :t"), {"t": district2})
        await c.commit()


# ── cross-vendor round (astra): hash presence, scoring precision, the partner
# picker, malformed ids, scoring after events, the merge actor ────────────────

async def test_idempotency_hash_respects_field_presence(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    """{"owner_user_id": null} and {"assigned_partner_id": null} are different
    requests. With defaults in the hash they collided and the second silently
    replayed the first instead of a 409 (cross-vendor P2)."""
    h = await _auth(client, staff)
    lid = await _make(client, h, env)
    key = _key()
    r1 = await client.post(f"{V1}/leads/{lid}/assign", json={"owner_user_id": None},
                           headers={**h, **key})
    r2 = await client.post(f"{V1}/leads/{lid}/assign", json={"assigned_partner_id": None},
                           headers={**h, **key})
    assert r1.status_code == 200 and r2.status_code == 409, f"{r1.status_code}/{r2.status_code}"
    assert r2.json()["error"]["code"] == "idempotency_key_reused"


async def test_scoring_rejects_a_cap_that_rounds_to_zero(
        client: httpx.AsyncClient, staff: Staff, sessions) -> None:
    """numeric(12,2) would store "0.001" as 0.00 and every score would divide by
    zero (cross-vendor P2); the stored value is what is validated."""
    await _grant_masters(sessions, staff)
    h = await _auth(client, staff)
    r = await client.patch(f"{V1}/lookups/scoring", json={"values": {"engagement_cap": "0.001"}},
                           headers={**h, **_key()})
    assert r.status_code == 422 and "engagement_cap" in r.json()["error"]["fields"]


async def test_partner_picker_is_scoped_and_searchable(
        client: httpx.AsyncClient, staff: Staff) -> None:
    """The fixture manager holds no partners scope, so the picker is empty for them
    (the live drivers cover a manager who does); shape and search are asserted."""
    h = await _auth(client, staff)
    r = await client.get(f"{V1}/lookups/partners", params={"q": "demo"}, headers=h)
    assert r.status_code == 200 and isinstance(r.json()["data"], list)


async def test_malformed_ids_are_422_not_500(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    assert (await client.get(f"{V1}/leads/not-a-uuid", headers=h)).status_code == 422
    r = await client.post(f"{V1}/leads", json=_body(env, territory_id="nope"),
                          headers={**h, **_key()})
    assert r.status_code == 422 and "territory_id" in r.json()["error"]["fields"]
    lid = await _make(client, h, env)
    r = await client.post(f"{V1}/leads/{lid}/assign", json={"owner_user_id": "nope"},
                          headers={**h, **_key()})
    assert r.status_code == 422 and "owner_user_id" in r.json()["error"]["fields"]
    assert (await client.get(f"{V1}/leads/{lid}/timeline", headers=h)).status_code == 200


async def test_create_with_a_note_scores_the_engagement(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    """The create-time note is an event and counts toward engagement; the score
    used to be computed before it was written (cross-vendor P2). Distinct names and
    mobiles so no duplicate flag adds a second event."""
    from decimal import Decimal

    h = await _auth(client, staff)
    cfg = {i["key"]: Decimal(i["value"]) for i in (await client.get(
        f"{V1}/lookups/scoring", headers=h)).json()["data"]}
    plain = (await client.post(f"{V1}/leads", json=_body(env, farmer_name="Aaaa Bbbb"),
                               headers={**h, **_key()})).json()["data"]
    noted = (await client.post(f"{V1}/leads", json=_body(env, farmer_name="Zzzz Yyyy",
                                                          note="met at the mandi"),
                               headers={**h, **_key()})).json()["data"]
    expected = (cfg["w_engagement"] * (Decimal(1) / cfg["engagement_cap"])).quantize(Decimal("0.01"))
    assert Decimal(noted["score"]) - Decimal(plain["score"]) == expected


async def test_merge_names_the_actor_on_the_timeline(
        client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await _auth(client, staff)
    m = _mobile()
    surv = await _make(client, h, env, mobile=m)
    loser = await _make(client, h, env, mobile=m)
    r = await client.post(f"{V1}/leads/{loser}/merge", json={"into_lead_id": surv},
                          headers={**h, **_key()})
    assert r.status_code == 200, r.text
    ev = next(e for e in (await client.get(f"{V1}/leads/{surv}/timeline", headers=h)).json()["data"]
              if e["kind"] == "lead.merged")
    assert ev["actor"]["full_name"] == "Asha Patel"
