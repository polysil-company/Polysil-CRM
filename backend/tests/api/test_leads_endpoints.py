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


@pytest_asyncio.fixture
async def env(sessions: Callable[[], AsyncSession], staff: Staff) -> AsyncIterator[Env]:
    """A state (with a code) over a district, committed. Depends on `staff` so it
    tears down first and clears the leads that pin the staff org unit."""
    tag = uuid.uuid4().hex[:8]
    code = "Z" + tag[:2].upper()
    district_name = f"gondal_{tag}"
    s = sessions()
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
