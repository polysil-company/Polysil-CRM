"""FS-035: a QR code edited and switched off, the dormant-lead sweep and its way back,
and a lead's office following its new owner (GAP-061).

The world is the order tests' shop. The sweep runs inside a transaction that is
rolled back: it would otherwise park every idle lead on the shared dev database."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import PASSWORD, V1, _key, _login
from worker.jobs.outbox import enter_as_principal

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _lead(client: httpx.AsyncClient, shop: Shop, h: dict[str, str]) -> dict[str, Any]:
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod"})
    assert r.status_code == 201, r.text
    return dict(r.json()["data"])


async def _to(client: httpx.AsyncClient, h: dict[str, str], lead_id: str, **body: object) -> httpx.Response:
    return await client.post(f"{V1}/leads/{lead_id}/transition", json=body, headers={**h, **_key()})


async def _qualified(client: httpx.AsyncClient, shop: Shop, h: dict[str, str]) -> dict[str, Any]:
    lead = await _lead(client, shop, h)
    for stage in ("contacted", "qualified"):
        r = await _to(client, h, lead["id"], to_stage=stage)
        assert r.status_code == 200, r.text
    return lead


async def _lost_reason(client: httpx.AsyncClient, h: dict[str, str]) -> str:
    r = await client.get(f"{V1}/lookups/lost-reasons", headers=h)
    assert r.status_code == 200, r.text
    return str(next(x["id"] for x in r.json()["data"] if x["is_active"]))


async def _park(sessions: Sessions, lead_id: str, frm: str) -> None:
    """A lead the sweep parked, committed, for the tests of the way back."""
    s = sessions()
    await s.execute(text("UPDATE lead SET stage = 'dormant', dormant_from_stage = CAST(:f AS lead_stage) "
                         "WHERE id = CAST(:i AS uuid)"), {"i": lead_id, "f": frm})
    await s.commit()
    await s.close()


async def _row(sessions: Sessions, lead_id: str) -> Any:
    s = sessions()
    try:
        return (await s.execute(text(
            "SELECT stage::text AS stage, dormant_from_stage::text AS dormant_from, "
            "lost_from_stage::text AS lost_from, reopen_count, owner_org_unit_id::text AS oou "
            "FROM lead WHERE id = CAST(:i AS uuid)"), {"i": lead_id})).one()
    finally:
        await s.close()


# ── QR codes ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def qr_made(sessions: Sessions) -> AsyncIterator[list[str]]:
    made: list[str] = []
    yield made
    c = sessions()
    await c.execute(text("UPDATE lead SET qr_code_id = NULL WHERE qr_code_id = ANY(CAST(:i AS uuid[]))"), {"i": made})
    await c.execute(text("DELETE FROM activity_event WHERE entity_type = 'lead_qr_code' AND entity_id = ANY(CAST(:i AS uuid[]))"), {"i": made})
    await c.execute(text("DELETE FROM lead_qr_code WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": made})
    await c.commit()
    await c.close()


async def _qr(client: httpx.AsyncClient, h: dict[str, str], shop: Shop, made: list[str]) -> dict[str, Any]:
    r = await client.post(f"{V1}/lead-qr-codes", headers={**h, **_key()},
                          json={"label": "Shah Irrigation counter", "campaign": "Krishi Mela",
                                "partner_id": shop.partner, "territory_id": shop.district})
    assert r.status_code == 201, r.text
    made.append(r.json()["data"]["id"])
    return dict(r.json()["data"])


async def test_a_qr_code_is_renamed_and_switched_off_and_keeps_its_code(
        client: httpx.AsyncClient, shop: Shop, qr_made: list[str], sessions: Sessions) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    qr = await _qr(client, dm, shop, qr_made)
    url = f"{V1}/lead-qr-codes/{qr['id']}"

    r = await client.patch(url, headers={**dm, **_key()}, json={"label": "Shah counter, Anand", "campaign": None})
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert (got["label"], got["campaign"], got["code"], got["url"]) == ("Shah counter, Anand", None, qr["code"], qr["url"])
    assert got["partner"]["id"] == shop.partner, "a field left out is unchanged"

    r = await client.patch(url, headers={**dm, **_key()}, json={"is_active": False})
    assert r.status_code == 200 and r.json()["data"]["is_active"] is False
    assert (await client.get("/public/lead-form", params={"qr": qr["code"]})).status_code == 404, \
        "a switched-off code no longer opens its own form"
    off = (await client.get(f"{V1}/lead-qr-codes", headers=dm, params={"active": "false"})).json()["data"]
    on = (await client.get(f"{V1}/lead-qr-codes", headers=dm, params={"active": "true"})).json()["data"]
    assert qr["id"] in {x["id"] for x in off} and qr["id"] not in {x["id"] for x in on}

    for body, field in (({}, "body"), ({"label": None}, "label"), ({"is_active": None}, "is_active")):
        r = await client.patch(url, headers={**dm, **_key()}, json=body)
        assert r.status_code == 422 and field in r.json()["error"]["fields"], (body, r.text)

    s = sessions()
    kinds = (await s.execute(text("SELECT kind FROM activity_event WHERE entity_id = CAST(:i AS uuid) ORDER BY occurred_at"),
                             {"i": qr["id"]})).scalars().all()
    await s.close()
    assert kinds == ["lead_qr_code.created", "lead_qr_code.updated", "lead_qr_code.updated"]


async def test_a_qr_code_edit_refuses_a_state_and_another_districts_manager(
        client: httpx.AsyncClient, shop: Shop, qr_made: list[str], sessions: Sessions) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    qr = await _qr(client, dm, shop, qr_made)
    r = await client.patch(f"{V1}/lead-qr-codes/{qr['id']}", headers={**dm, **_key()},
                           json={"territory_id": shop.state})
    assert r.status_code == 422 and "territory_id" in r.json()["error"]["fields"], r.text

    tag = uuid.uuid4().hex[:8]
    c = sessions()
    district = str((await c.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, CAST(:p AS uuid)) RETURNING id"),
        {"n": f"sg_other_{tag}", "p": shop.state})).scalar_one())
    office = str((await c.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, CAST(:t AS uuid)) RETURNING id"),
        {"n": f"sg_other_office_{tag}", "t": district})).scalar_one())
    email = f"sg_dm_{tag}@polysil.in"
    other = str((await c.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, :p, 'Other DM', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'district_manager' "
        "RETURNING id"), {"e": email, "p": PasswordHasher().hash(PASSWORD), "o": office})).scalar_one())
    far = str((await c.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, mobile, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'Far Dealer', :m, CAST(:t AS uuid), 'dealer') RETURNING id"),
        {"c": f"SGF{tag}".upper(), "m": "9194" + f"{uuid.uuid4().int % 10**8:08d}", "t": district})).scalar_one())
    await c.commit()
    await c.close()
    try:
        # a dealer in another district is outside this manager's reach (create's F-2 check)
        r = await client.patch(f"{V1}/lead-qr-codes/{qr['id']}", headers={**dm, **_key()},
                               json={"partner_id": far})
        assert r.status_code == 422 and r.json()["error"]["fields"] == {"partner_id": "not found"}, r.text
        h = await _login(client, email, PASSWORD)
        r = await client.patch(f"{V1}/lead-qr-codes/{qr['id']}", headers={**h, **_key()}, json={"label": "Mine now"})
        assert r.status_code == 404, r.text
    finally:
        c = sessions()
        for stmt in ("DELETE FROM session WHERE user_id = CAST(:u AS uuid)",
                     "DELETE FROM login_attempt WHERE identifier = :e",
                     "DELETE FROM idempotency_record WHERE user_id = CAST(:u AS uuid)",
                     "DELETE FROM app_user WHERE id = CAST(:u AS uuid)",
                     "DELETE FROM channel_partner WHERE id = CAST(:f AS uuid)",
                     "DELETE FROM org_unit WHERE id = CAST(:o AS uuid)",
                     "DELETE FROM territory WHERE id = CAST(:t AS uuid)"):
            await c.execute(text(stmt), {"u": other, "e": email, "o": office, "t": district, "f": far})
        await c.commit()
        await c.close()


# ── the sweep ────────────────────────────────────────────────────────────────

async def _sweep(s: AsyncSession, days_ahead: int = 61) -> int:
    """Run the sweep as the worker does, `days_ahead` in the future, so every lead made
    in this test is old enough without touching its history. Back to the session's
    own role after, to read the result; the caller rolls back."""
    await enter_as_principal(s, get_settings())
    n = int((await s.execute(text(
        "SELECT lead_dormant_sweep(now() + make_interval(days => :d), 1000000)"), {"d": days_ahead})).scalar_one())
    await s.execute(text("RESET ROLE"))
    return n


async def _stages(s: AsyncSession, ids: list[str]) -> dict[str, tuple[str, str | None]]:
    rows = (await s.execute(text(
        "SELECT id::text AS id, stage::text AS stage, dormant_from_stage::text AS frm FROM lead "
        "WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": ids})).all()
    return {r.id: (r.stage, r.frm) for r in rows}


async def test_the_sweep_parks_idle_open_leads_and_never_a_won_or_lost_one(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    idle = await _qualified(client, shop, fo)
    fresh_new = await _lead(client, shop, fo)
    lost = await _lead(client, shop, fo)
    r = await _to(client, fo, lost["id"], to_stage="lost", lost_reason_id=await _lost_reason(client, fo))
    assert r.status_code == 200, r.text
    won = await _qualified(client, shop, fo)
    tasked = await _qualified(client, shop, fo)
    r = await client.post(f"{V1}/tasks", headers={**fo, **_key()}, json={
        "title": "Call the farmer", "task_type": "call", "lead_id": tasked["id"],
        "due_at": (today_ist() + dt.timedelta(days=90)).isoformat()})
    assert r.status_code == 201, r.text
    ids = [idle["id"], fresh_new["id"], lost["id"], won["id"], tasked["id"]]

    s = sessions()
    try:
        await s.execute(text("UPDATE lead SET stage = 'won' WHERE id = CAST(:i AS uuid)"), {"i": won["id"]})
        ledger_before = (await s.execute(text(
            "SELECT count(*) FROM reward_ledger WHERE lead_id = ANY(CAST(:i AS uuid[]))"), {"i": ids})).scalar_one()
        assert await _sweep(s) >= 2
        got = await _stages(s, ids)
        assert got[idle["id"]] == ("dormant", "qualified")
        assert got[fresh_new["id"]] == ("dormant", "new")
        assert got[lost["id"]] == ("lost", None), "a lost lead is never swept"
        assert got[won["id"]] == ("won", None), "a won lead is never swept"
        assert got[tasked["id"]] == ("qualified", None), "an open task keeps it open (GAP-340)"
        event = (await s.execute(text(
            "SELECT payload, actor_id::text AS actor FROM activity_event WHERE lead_id = CAST(:i AS uuid) "
            "AND kind = 'lead.stage_changed' ORDER BY occurred_at DESC LIMIT 1"), {"i": idle["id"]})).one()
        assert event.payload["to"] == "dormant" and event.payload["from"] == "qualified"
        assert (event.payload["reason"], event.payload["days"]) == ("no_activity", 60)
        assert event.actor == get_settings().system_user_id
        ledger_after = (await s.execute(text(
            "SELECT count(*) FROM reward_ledger WHERE lead_id = ANY(CAST(:i AS uuid[]))"), {"i": ids})).scalar_one()
        assert ledger_after == ledger_before, "the rewards trigger fired and wrote nothing"
        # session A's 034 trigger stamps won_at and lost_at on stage changes
        cols = set((await s.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'lead' "
            "AND column_name IN ('won_at', 'lost_at')"))).scalars().all())
        if cols == {"won_at", "lost_at"}:
            dates = (await s.execute(text(
                "SELECT won_at, lost_at FROM lead WHERE id = CAST(:i AS uuid)"), {"i": idle["id"]})).one()
            assert dates == (None, None), "a dormant lead carries no won or lost date"
        assert await _sweep(s) == 0, "a second run changes nothing"
    finally:
        await s.rollback()
        await s.close()


async def test_the_setting_is_read_and_only_a_persons_event_counts(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Rules 4 and 5, each half able to fail (code review F-1)."""
    fo = await endpoints._as(client, shop, "field_officer")
    lead = await _qualified(client, shop, fo)
    me = shop.ids["field_officer"]
    s = sessions()
    try:
        # 35 days ahead: idle under a 10-day setting, not under the default 60
        await _sweep(s, days_ahead=35)
        assert (await _stages(s, [lead["id"]]))[lead["id"]][0] == "qualified", "the default 60 is read"
        await s.execute(text("UPDATE lead_score_rule SET value = 10 WHERE key = 'dormant_after_days'"))
        # the cut is now 25 days ahead; a person's event at 30 days keeps the lead open
        event = str((await s.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload, occurred_at) "
            "VALUES ('lead', CAST(:i AS uuid), CAST(:i AS uuid), 'lead.note_added', CAST(:me AS uuid), '{}', "
            "now() + interval '30 days') RETURNING id"), {"i": lead["id"], "me": me})).scalar_one())
        await _sweep(s, days_ahead=35)
        assert (await _stages(s, [lead["id"]]))[lead["id"]][0] == "qualified", "a person's event is activity"
        # the same moment written by the System is not
        await s.execute(text("DELETE FROM activity_event WHERE id = CAST(:e AS uuid)"), {"e": event})
        await s.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload, occurred_at) "
            "VALUES ('lead', CAST(:i AS uuid), CAST(:i AS uuid), 'quotation.expired', CAST(:sys AS uuid), '{}', "
            "now() + interval '30 days')"), {"i": lead["id"], "sys": get_settings().system_user_id})
        await _sweep(s, days_ahead=35)
        assert (await _stages(s, [lead["id"]]))[lead["id"]][0] == "dormant", "a System event is not"
    finally:
        await s.rollback()
        await s.close()


async def test_the_sweep_skips_a_lead_a_person_is_changing(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Plan review B-2: executed with two sessions, not reasoned about."""
    fo = await endpoints._as(client, shop, "field_officer")
    lead = await _qualified(client, shop, fo)
    other = await _qualified(client, shop, fo)
    holder, sweeper = sessions(), sessions()
    try:
        await holder.execute(text("SELECT 1 FROM lead WHERE id = CAST(:i AS uuid) FOR UPDATE"), {"i": lead["id"]})
        await asyncio.wait_for(_sweep(sweeper), timeout=60)
        got = await _stages(sweeper, [lead["id"], other["id"]])
        assert got[lead["id"]] == ("qualified", None), "skipped, not waited on and not overwritten"
        assert got[other["id"]] == ("dormant", "qualified")
    finally:
        await sweeper.rollback()
        await holder.rollback()
        await sweeper.close()
        await holder.close()


async def test_the_sweep_refuses_anyone_but_the_system(sessions: Sessions) -> None:
    from sqlalchemy.exc import DBAPIError
    s = sessions()
    try:
        with pytest.raises(DBAPIError) as err:
            await s.execute(text("SELECT lead_dormant_sweep(now(), 10)"))
        assert getattr(err.value.orig, "sqlstate", None) == "42501"
    finally:
        await s.rollback()
        await s.close()


# ── the way back ─────────────────────────────────────────────────────────────

async def test_reopen_returns_a_dormant_lead_where_it_was_without_counting_a_reopen(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    lead = await _qualified(client, shop, fo)
    await _park(sessions, lead["id"], "qualified")
    got = (await client.get(f"{V1}/leads/{lead['id']}", headers=fo)).json()["data"]
    assert (got["stage"], got["dormant_from_stage"]) == ("dormant", "qualified")
    r = await _to(client, fo, lead["id"], to_stage="contacted")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_transition"
    r = await client.post(f"{V1}/leads/{lead['id']}/reopen", headers={**fo, **_key()}, json={"note": "Called back"})
    assert r.status_code == 200, r.text
    assert (r.json()["data"]["stage"], r.json()["data"]["dormant_from_stage"]) == ("qualified", None)
    row = await _row(sessions, lead["id"])
    assert (row.stage, row.dormant_from, row.reopen_count) == ("qualified", None, 0)
    r = await client.post(f"{V1}/leads/{lead['id']}/reopen", headers={**fo, **_key()}, json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "stage_terminal"


async def test_a_dormant_lead_lost_remembers_the_real_stage_and_reopens_there(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    lead = await _qualified(client, shop, fo)
    await _park(sessions, lead["id"], "qualified")
    r = await _to(client, fo, lead["id"], to_stage="lost", lost_reason_id=await _lost_reason(client, fo))
    assert r.status_code == 200, r.text
    row = await _row(sessions, lead["id"])
    assert (row.stage, row.dormant_from, row.lost_from) == ("lost", None, "qualified"), "review N-3"
    r = await client.post(f"{V1}/leads/{lead['id']}/reopen", headers={**fo, **_key()}, json={})
    assert r.status_code == 200 and r.json()["data"]["stage"] == "qualified"
    assert (await _row(sessions, lead["id"])).reopen_count == 1


async def test_merging_a_dormant_loser_clears_its_from_stage(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Plan review B-1: without the clear trigger the CHECK fails with a 500."""
    dm = await endpoints._as(client, shop, "district_manager")
    survivor = await _lead(client, shop, dm)
    loser = await _lead(client, shop, dm)
    await _park(sessions, loser["id"], "new")
    r = await client.post(f"{V1}/leads/{loser['id']}/merge", json={"into_lead_id": survivor["id"]},
                          headers={**dm, **_key()})
    assert r.status_code == 200, r.text
    row = await _row(sessions, loser["id"])
    assert (row.stage, row.dormant_from) == ("merged", None)


async def test_the_dormant_setting_is_admin_editable_and_positive(client: httpx.AsyncClient, shop: Shop) -> None:
    admin = await endpoints._as(client, shop, "admin_sales")
    items = (await client.get(f"{V1}/lookups/scoring", headers=admin)).json()["data"]
    assert {"key": "dormant_after_days", "value": "60.00"} in items
    r = await client.patch(f"{V1}/lookups/scoring", headers={**admin, **_key()},
                           json={"values": {"dormant_after_days": "0"}})
    assert r.status_code == 422 and "dormant_after_days" in r.json()["error"]["fields"], r.text


# ── the office follows the owner (GAP-061) ───────────────────────────────────

@pytest_asyncio.fixture
async def taluka(shop: Shop, sessions: Sessions) -> AsyncIterator[dict[str, str]]:
    """A taluka office under the shop's district office, with its own officer and
    manager. Removed before the shop's teardown deletes the leads."""
    tag = uuid.uuid4().hex[:8]
    c = sessions()
    terr = str((await c.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('taluka', :n, CAST(:p AS uuid)) RETURNING id"),
        {"n": f"sg_taluka_{tag}", "p": shop.district})).scalar_one())
    office = str((await c.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id, parent_id) VALUES (:n, 1, CAST(:t AS uuid), CAST(:p AS uuid)) RETURNING id"),
        {"n": f"sg_taluka_office_{tag}", "t": terr, "p": shop.office})).scalar_one())
    hq = str((await c.execute(text(
        "INSERT INTO org_unit (name, role_level, parent_id) VALUES (:n, 1, CAST(:p AS uuid)) RETURNING id"),
        {"n": f"sg_desk_{tag}", "p": shop.office})).scalar_one())
    people: dict[str, str] = {}
    for key, role, unit in (("officer", "field_officer", office), ("manager", "district_manager", office),
                            ("desk", "field_officer", hq)):
        email = f"sg_{key}_{tag}@polysil.in"
        people[key] = str((await c.execute(text(
            "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
            "SELECT 'staff', :e, :p, :n, r.id, CAST(:o AS uuid) FROM role r WHERE r.code = :r RETURNING id"),
            {"e": email, "p": PasswordHasher().hash(PASSWORD), "n": f"SG {key}", "r": role, "o": unit})).scalar_one())
        people[f"{key}_email"] = email
    await c.commit()
    await c.close()
    try:
        yield {"territory": terr, "office": office, "hq": hq, **people}
    finally:
        c = sessions()
        ids = [people["officer"], people["manager"], people["desk"]]
        for stmt in (
            "UPDATE lead SET owner_user_id = NULL WHERE owner_user_id = ANY(CAST(:u AS uuid[]))",
            "UPDATE lead SET owner_org_unit_id = CAST(:home AS uuid) WHERE owner_org_unit_id IN (CAST(:o AS uuid), CAST(:hq AS uuid))",
            "UPDATE quotation SET owner_org_unit_id = CAST(:home AS uuid) WHERE owner_org_unit_id IN (CAST(:o AS uuid), CAST(:hq AS uuid))",
            "DELETE FROM session WHERE user_id = ANY(CAST(:u AS uuid[]))",
            "DELETE FROM login_attempt WHERE identifier = ANY(CAST(:e AS citext[]))",
            "DELETE FROM idempotency_record WHERE user_id = ANY(CAST(:u AS uuid[]))",
            "DELETE FROM activity_event WHERE actor_id = ANY(CAST(:u AS uuid[]))",
            "DELETE FROM app_user WHERE id = ANY(CAST(:u AS uuid[]))",
            "DELETE FROM org_unit WHERE id IN (CAST(:o AS uuid), CAST(:hq AS uuid))",
            "DELETE FROM territory WHERE id = CAST(:t AS uuid)",
        ):
            await c.execute(text(stmt), {"u": ids, "e": [people["officer_email"], people["manager_email"], people["desk_email"]],
                                         "home": shop.office, "o": office, "hq": hq, "t": terr})
        await c.commit()
        await c.close()


async def test_assigning_across_offices_moves_the_lead_to_the_owners_office(
        client: httpx.AsyncClient, shop: Shop, taluka: dict[str, str], sessions: Sessions) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    lead = await _lead(client, shop, dm)
    assert lead["owner_org_unit"]["id"] == shop.office
    r = await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**dm, **_key()},
                          json={"owner_user_id": taluka["officer"]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["owner_org_unit"]["id"] == taluka["office"]
    # the taluka's own manager now sees it in their list; the assigner still does
    tm = await _login(client, taluka["manager_email"], PASSWORD)
    for h in (tm, dm):
        listed = (await client.get(f"{V1}/leads", headers=h, params={"q": lead["inquiry_no"]})).json()["data"]
        assert [x["id"] for x in listed] == [lead["id"]]
    s = sessions()
    kinds = (await s.execute(text(
        "SELECT payload->>'owner_org_unit_id' FROM activity_event WHERE lead_id = CAST(:i AS uuid) AND kind = 'lead.assigned'"),
        {"i": lead["id"]})).scalars().all()
    await s.close()
    assert kinds == [taluka["office"]]


async def test_an_owner_with_no_sales_office_or_none_routes_by_territory(
        client: httpx.AsyncClient, shop: Shop, taluka: dict[str, str], sessions: Sessions) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    lead = await _lead(client, shop, dm)
    r = await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**dm, **_key()},
                          json={"owner_user_id": taluka["officer"]})
    assert r.json()["data"]["owner_org_unit"]["id"] == taluka["office"]
    # a desk with no territory: the office covering the lead's district
    r = await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**dm, **_key()},
                          json={"owner_user_id": taluka["desk"]})
    assert r.status_code == 200 and r.json()["data"]["owner_org_unit"]["id"] == shop.office
    # cleared: routed by territory as well
    await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**dm, **_key()},
                      json={"owner_user_id": taluka["officer"]})
    r = await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**dm, **_key()},
                          json={"owner_user_id": None})
    assert r.status_code == 200 and r.json()["data"]["owner_org_unit"]["id"] == shop.office
    # a partner-only assignment leaves the office alone
    await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**dm, **_key()},
                      json={"owner_user_id": taluka["officer"]})
    r = await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**dm, **_key()},
                          json={"assigned_partner_id": shop.partner})
    assert r.status_code == 200 and r.json()["data"]["owner_org_unit"]["id"] == taluka["office"]


async def test_a_taluka_manager_reassigning_keeps_the_office_inside_their_scope(
        client: httpx.AsyncClient, shop: Shop, taluka: dict[str, str]) -> None:
    """Rule 13: routing by territory would take the lead to the district office,
    outside the taluka manager's subtree; the office stays."""
    dm = await endpoints._as(client, shop, "district_manager")
    lead = await _lead(client, shop, dm)
    await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**dm, **_key()},
                      json={"owner_user_id": taluka["officer"]})
    tm = await _login(client, taluka["manager_email"], PASSWORD)
    r = await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**tm, **_key()},
                          json={"owner_user_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["owner_org_unit"]["id"] == taluka["office"]


async def test_an_own_scoped_officer_cannot_clear_the_owner(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-5: clearing it would hide the row from them, a 500 from the policy."""
    fo = await endpoints._as(client, shop, "field_officer")
    lead = await _lead(client, shop, fo)
    r = await client.post(f"{V1}/leads/{lead['id']}/assign", headers={**fo, **_key()},
                          json={"owner_user_id": None})
    assert r.status_code == 422 and "owner_user_id" in r.json()["error"]["fields"], r.text
