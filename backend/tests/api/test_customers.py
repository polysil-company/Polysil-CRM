# ruff: noqa: E501  (request bodies and assertions)

"""FS-041 over the API and in the database: the customer a lead gets at
qualification, who sees it, its page and timeline, editing and consent."""

from __future__ import annotations

import asyncio
import importlib.util
import uuid
from collections.abc import Callable
from pathlib import Path

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


def _mobile() -> str:
    return "96" + f"{uuid.uuid4().int % 10**8:08d}"


async def _lead(client: httpx.AsyncClient, h: dict[str, str], shop: Shop, mobile: str,
                name: str = "Rameshbhai Patel") -> dict:
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": name, "mobile": mobile, "territory_id": shop.district,
        "inquiry_type": "commercial", "mis_system": "drip", "village": "Vadod"})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _move(client: httpx.AsyncClient, h: dict[str, str], lead_id: str, *stages: str) -> dict:
    data: dict = {}
    for stage in stages:
        r = await client.post(f"{V1}/leads/{lead_id}/transition", json={"to_stage": stage},
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
    return data


async def _cleanup(sessions: Sessions, mobiles: list[str]) -> None:
    """Customers point at nothing the shop removes, but leads point at them."""
    e164 = ["+91" + m for m in mobiles]
    c = sessions()
    for stmt in ("UPDATE lead SET customer_id = NULL WHERE mobile = ANY(:m)",
                 "DELETE FROM activity_event WHERE entity_type = 'customer' AND customer_id IN (SELECT id FROM customer WHERE mobile = ANY(:m))",
                 "DELETE FROM customer WHERE mobile = ANY(:m)"):
        await c.execute(text(stmt), {"m": e164})
    await c.commit()
    await c.close()


# ── linking ──────────────────────────────────────────────────────────────────

async def test_a_lead_gets_its_customer_at_qualified(client: httpx.AsyncClient, shop: Shop,
                                                     sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    m = _mobile()
    try:
        a = await _lead(client, ho, shop, m)
        assert a["customer_id"] is None
        assert (await _move(client, ho, a["id"], "contacted"))["customer_id"] is None
        a = await _move(client, ho, a["id"], "qualified")
        cid = a["customer_id"]
        assert cid

        # a second enquiry from the same number joins it, whatever name it carries
        b = await _lead(client, ho, shop, m, name="R. Patel")
        assert b["customer_id"] is None
        b = await _move(client, ho, b["id"], "contacted", "qualified")
        assert b["customer_id"] == cid

        r = await client.get(f"{V1}/customers/{cid}", headers=ho)
        assert r.status_code == 200, r.text
        c = r.json()["data"]
        assert (c["name"], c["mobile"], c["lead_count"]) == ("Rameshbhai Patel", "+91" + m, 2)
        assert {x["id"] for x in c["leads"]} == {a["id"], b["id"]}
        assert all(x["source"] == "employee" for x in c["leads"])

        s = sessions()
        created = (await s.execute(text(
            "SELECT count(*) FROM activity_event WHERE kind = 'customer.created' "
            "AND customer_id = CAST(:c AS uuid) AND lead_id IS NULL"), {"c": cid})).scalar_one()
        payload = (await s.execute(text(
            "SELECT payload FROM activity_event WHERE kind = 'customer.created' "
            "AND customer_id = CAST(:c AS uuid)"), {"c": cid})).scalar_one()
        await s.close()
        assert created == 1 and "inquiry_no" not in payload, payload
        # the lead timeline is unchanged: customer events carry no lead_id (edge case 12)
        r = await client.get(f"{V1}/leads/{a['id']}/timeline", headers=ho)
        assert not any(e["kind"].startswith("customer.") for e in r.json()["data"]), r.text
    finally:
        await _cleanup(sessions, [m])


async def test_two_leads_qualifying_at_once_share_one_customer(shop: Shop, sessions: Sessions,
                                                                client: httpx.AsyncClient) -> None:
    """Edge case 1: the second insert waits on the unique mobile, then joins."""
    ho = await endpoints._as(client, shop, "field_officer")
    m = _mobile()
    try:
        a = await _lead(client, ho, shop, m)
        b = await _lead(client, ho, shop, m)
        s1, s2 = sessions(), sessions()
        await s1.execute(text("UPDATE lead SET stage = 'qualified' WHERE id = CAST(:i AS uuid)"), {"i": a["id"]})
        started = asyncio.Event()

        async def second() -> None:
            started.set()
            await s2.execute(text("UPDATE lead SET stage = 'qualified' WHERE id = CAST(:i AS uuid)"), {"i": b["id"]})
            await s2.commit()

        task = asyncio.create_task(second())
        await started.wait()
        await asyncio.sleep(0.5)          # let the second statement reach the unique index
        await s1.commit()
        await asyncio.wait_for(task, 30)
        await s1.close()
        await s2.close()
        s = sessions()
        ids = (await s.execute(text(
            "SELECT DISTINCT customer_id::text FROM lead WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))"),
            {"a": a["id"], "b": b["id"]})).scalars().all()
        events = (await s.execute(text(
            "SELECT count(*) FROM activity_event WHERE kind = 'customer.created' "
            "AND customer_id = CAST(:c AS uuid)"), {"c": ids[0]})).scalar_one()
        await s.close()
        assert len(ids) == 1 and ids[0] is not None and events == 1, (ids, events)
    finally:
        await _cleanup(sessions, [m])


async def test_a_customer_seen_only_elsewhere_is_joined_not_duplicated(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Edge case 2: the officer cannot see the manager's lead, so cannot see its
    customer; qualifying the officer's lead still joins it (the definer), and the
    officer's page lists only the officer's lead."""
    hdm = await endpoints._as(client, shop, "district_manager")
    ho = await endpoints._as(client, shop, "field_officer")
    m = _mobile()
    try:
        first = await _move(client, hdm, (await _lead(client, hdm, shop, m))["id"], "contacted", "qualified")
        cid = first["customer_id"]
        assert (await client.get(f"{V1}/customers/{cid}", headers=ho)).status_code == 404
        r = await client.get(f"{V1}/customers/{cid}/timeline", headers=ho)
        assert r.status_code == 404, r.text

        mine = await _move(client, ho, (await _lead(client, ho, shop, m))["id"], "contacted", "qualified")
        assert mine["customer_id"] == cid
        r = await client.get(f"{V1}/customers/{cid}", headers=ho)
        assert [x["id"] for x in r.json()["data"]["leads"]] == [mine["id"]], r.text
        assert r.json()["data"]["lead_count"] == 1
        r = await client.get(f"{V1}/customers/{cid}", headers=hdm)
        assert r.json()["data"]["lead_count"] == 2, r.text
    finally:
        await _cleanup(sessions, [m])


async def test_who_sees_the_list_and_a_dealer_reads_only(client: httpx.AsyncClient, shop: Shop,
                                                         sessions: Sessions) -> None:
    hdm = await endpoints._as(client, shop, "district_manager")
    m1, m2 = _mobile(), _mobile()
    hd, dealer_mobile = await cmp._dealer(client, shop, sessions)
    try:
        theirs = await _lead(client, hd, shop, m1, name="Dealer Farmer")
        theirs = await _move(client, hdm, theirs["id"], "contacted", "qualified")
        other = await _move(client, hdm, (await _lead(client, hdm, shop, m2, name="Staff Farmer"))["id"],
                            "contacted", "qualified")

        r = await client.get(f"{V1}/customers", params={"territory_id": shop.district}, headers=hdm)
        names = {c["name"] for c in r.json()["data"]}
        assert {"Dealer Farmer", "Staff Farmer"} <= names, r.text
        r = await client.get(f"{V1}/customers", params={"q": m2[-6:]}, headers=hdm)
        assert [c["id"] for c in r.json()["data"]] == [other["customer_id"]], r.text
        r = await client.get(f"{V1}/customers", params={"q": "ab"}, headers=hdm)
        assert r.status_code == 422, r.text

        r = await client.get(f"{V1}/customers/{theirs['customer_id']}", headers=hd)
        assert r.status_code == 200, r.text
        assert (await client.get(f"{V1}/customers/{other['customer_id']}", headers=hd)).status_code == 404
        r = await client.patch(f"{V1}/customers/{theirs['customer_id']}", json={"name": "Renamed"},
                               headers={**hd, **_key()})
        assert r.status_code == 403, r.text
    finally:
        await cmp._forget(sessions, dealer_mobile)
        await _cleanup(sessions, [m1, m2])


async def test_the_update_policy_refuses_a_dealer(shop: Shop, sessions: Sessions,
                                                   client: httpx.AsyncClient) -> None:
    """Edge case 9: dealers hold leads.edit, so the policy says staff only."""
    from tests.api.test_campaigns import _as_db
    hd, dealer_mobile = await cmp._dealer(client, shop, sessions)
    hdm = await endpoints._as(client, shop, "district_manager")
    m = _mobile()
    try:
        lead = await _lead(client, hd, shop, m)
        cid = (await _move(client, hdm, lead["id"], "contacted", "qualified"))["customer_id"]
        dealer = await _as_db(sessions, shop.ids["dealer"])
        try:
            assert (await dealer.execute(text("SELECT count(*) FROM customer WHERE id = CAST(:c AS uuid)"),
                                         {"c": cid})).scalar_one() == 1
            res = await dealer.execute(text("UPDATE customer SET name = 'x' WHERE id = CAST(:c AS uuid)"),
                                       {"c": cid})
            assert res.rowcount == 0  # type: ignore[attr-defined]
        finally:
            await dealer.rollback()
            await dealer.close()
    finally:
        await cmp._forget(sessions, dealer_mobile)
        await _cleanup(sessions, [m])


# ── the page, the timeline, editing ──────────────────────────────────────────

async def test_edit_consent_and_the_timeline(client: httpx.AsyncClient, shop: Shop,
                                             sessions: Sessions) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    m = _mobile()
    try:
        a = await _move(client, ho, (await _lead(client, ho, shop, m))["id"], "contacted", "qualified")
        cid = a["customer_id"]
        path = f"{V1}/customers/{cid}"

        async def patch(body: dict) -> httpx.Response:
            return await client.patch(path, json=body, headers={**ho, **_key()})

        r = await patch({"name": "Rameshbhai  K.  Patel", "survey_no": "112/3", "customer_type": "farmer"})
        assert r.status_code == 200 and r.json()["data"]["name"] == "Rameshbhai K. Patel", r.text
        assert (await patch({"name": None})).status_code == 422
        assert (await patch({"territory_id": shop.state})).status_code == 422, "a state is refused"
        assert (await patch({"territory_id": str(uuid.uuid4())})).status_code == 422, "an unknown one too"
        assert (await patch({"consent_given": True})).status_code == 422
        assert (await patch({"consent_channel": "whatsapp"})).status_code == 422

        first = (await patch({"consent_given": True, "consent_channel": "whatsapp"})).json()["data"]
        assert first["consent_channel"] == "whatsapp" and first["consent_given_at"]
        again = (await patch({"consent_given": True, "consent_channel": "whatsapp"})).json()["data"]
        assert again["consent_given_at"] == first["consent_given_at"], "re-sending keeps the date"
        moved = (await patch({"consent_given": True, "consent_channel": "written"})).json()["data"]
        assert moved["consent_channel"] == "written" and moved["consent_given_at"] != first["consent_given_at"]
        gone = (await patch({"consent_given": False})).json()["data"]
        assert (gone["consent_given_at"], gone["consent_channel"]) == (None, None)

        # the lead keeps its own party (rule 6)
        r = await client.get(f"{V1}/leads/{a['id']}", headers=ho)
        assert r.json()["data"]["farmer_name"] == "Rameshbhai Patel"

        s = sessions()
        updates = (await s.execute(text(
            "SELECT payload FROM activity_event WHERE kind = 'customer.updated' "
            "AND customer_id = CAST(:c AS uuid) ORDER BY occurred_at"), {"c": cid})).scalars().all()
        await s.close()
        assert len(updates) == 4, updates          # name, consent, channel, withdrawal
        assert updates[-1]["consent"]["to"] is None and updates[-1]["consent"]["from"] == "written"
        assert updates[0]["changed"]["name"] == {"from": "Rameshbhai Patel", "to": "Rameshbhai K. Patel"}

        for i in range(6):
            r = await client.post(f"{V1}/leads/{a['id']}/notes", json={"note": f"call {i}"},
                                  headers={**ho, **_key()})
            assert r.status_code in (200, 201), r.text

        # one timeline: the lead's events and the customer's own, each once, paged. The
        # notes are newest, so the later pages hold lead events only (plan review B-1)
        r = await client.get(f"{path}/timeline", params={"limit": 100}, headers=ho)
        full = r.json()["data"]
        kinds = [e["kind"] for e in full]
        assert "lead.created" in kinds and "customer.created" in kinds and kinds.count("customer.updated") == 4
        assert len({e["id"] for e in full}) == len(full)
        assert all(e["lead_id"] == a["id"] for e in full if e["kind"].startswith("lead."))
        walked, cursor = [], None
        while True:
            params: dict = {"limit": 2, **({"before": cursor} if cursor else {})}
            page = (await client.get(f"{path}/timeline", params=params, headers=ho)).json()
            walked += [e["id"] for e in page["data"]]
            cursor = page["meta"]["next_cursor"]
            if not cursor:
                break
        assert walked == [e["id"] for e in full] and len(walked) >= 14, len(walked)
        r = await client.get(f"{path}/timeline", params={"limit": 3}, headers=ho)
        assert [e["kind"] for e in r.json()["data"]] == ["lead.note_added"] * 3, r.text
    finally:
        await _cleanup(sessions, [m])


async def test_a_merge_gives_the_survivor_the_customer(client: httpx.AsyncClient, shop: Shop,
                                                       sessions: Sessions) -> None:
    """Edge case 5: a later qualification of the survivor joins, never duplicates."""
    ho = await endpoints._as(client, shop, "field_officer")
    hdm = await endpoints._as(client, shop, "district_manager")
    m1, m2 = _mobile(), _mobile()
    try:
        loser = await _move(client, ho, (await _lead(client, ho, shop, m1))["id"], "contacted", "qualified")
        survivor = await _lead(client, ho, shop, m2)
        r = await client.post(f"{V1}/leads/{loser['id']}/merge", json={"into_lead_id": survivor["id"]},
                              headers={**hdm, **_key()})
        assert r.status_code == 200 and r.json()["data"]["customer_id"] == loser["customer_id"], r.text
        after = await _move(client, ho, survivor["id"], "contacted", "qualified")
        assert after["customer_id"] == loser["customer_id"]
        s = sessions()
        assert (await s.execute(text("SELECT count(*) FROM customer WHERE mobile = :m"),
                                {"m": "+91" + m2})).scalar_one() == 0
        await s.close()
    finally:
        await _cleanup(sessions, [m1, m2])


async def test_the_backfill_takes_the_oldest_lead(shop: Shop, sessions: Sessions,
                                                  client: httpx.AsyncClient) -> None:
    """Edge cases 3 and 4: one customer per mobile from the oldest lead that got past
    contacted, lost-from-quoted included; a lead lost from contacted gets none."""
    path = Path(__file__).resolve().parents[2] / "api/db/migrations/versions/050_customer_record.py"
    spec = importlib.util.spec_from_file_location("mig050_backfill", path)
    assert spec is not None and spec.loader is not None
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    ho = await endpoints._as(client, shop, "field_officer")
    m, early = _mobile(), _mobile()
    seed = await _lead(client, ho, shop, _mobile())
    s = sessions()
    try:
        # rolled back with the test: the leads must arrive unlinked, as before 050
        await s.execute(text("ALTER TABLE lead DISABLE TRIGGER trg_lead_link_customer"))
        insert = ("INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
                  "mobile, territory_id, owner_org_unit_id, created_at, lost_from_stage, lost_reason_id) "
                  "SELECT :no, CAST(:st AS lead_stage), inquiry_type, mis_system_id, lead_source_id, :n, :m, territory_id, "
                  "owner_org_unit_id, now() - make_interval(days => :d), CAST(:lf AS lead_stage), "
                  "CASE WHEN :st = 'lost' THEN (SELECT id FROM won_lost_reason LIMIT 1) END "
                  "FROM lead WHERE id = CAST(:l AS uuid)")
        tag = uuid.uuid4().hex[:6]
        for no, st, n, mob, d, lf in ((f"BF{tag}-1", "quoted", "Newer Name", m, 1, None),
                                      (f"BF{tag}-2", "lost", "Older Name", m, 9, "quoted"),
                                      (f"BF{tag}-3", "lost", "Never Qualified", early, 5, "contacted")):
            await s.execute(text(insert), {"no": no, "st": st, "n": n, "m": "+91" + mob, "d": d, "lf": lf,
                                           "l": seed["id"]})
        # a loser merged into the qualified one follows it, whatever its own number
        loser_mobile = "+91" + _mobile()
        await s.execute(text(
            "INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
            "mobile, territory_id, owner_org_unit_id, merged_into_id) SELECT :no, 'merged', inquiry_type, "
            "mis_system_id, lead_source_id, 'Loser', :m, territory_id, owner_org_unit_id, "
            "(SELECT id FROM lead WHERE inquiry_no = CAST(:s AS citext)) FROM lead WHERE id = CAST(:l AS uuid)"),
            {"no": f"BF{tag}-4", "m": loser_mobile, "s": f"BF{tag}-1", "l": seed["id"]})
        for stmt in mig.BACKFILL[:3]:
            await s.execute(text(stmt))
        follows = (await s.execute(text(
            "SELECT l.customer_id = s.customer_id FROM lead l JOIN lead s ON s.id = l.merged_into_id "
            "WHERE l.inquiry_no = CAST(:n AS citext)"), {"n": f"BF{tag}-4"})).scalar_one()
        own = (await s.execute(text("SELECT count(*) FROM customer WHERE mobile = :m"),
                               {"m": loser_mobile})).scalar_one()
        assert follows and own == 0, (follows, own)
        names = (await s.execute(text("SELECT mobile, name FROM customer WHERE mobile = ANY(:m)"),
                                 {"m": ["+91" + m, "+91" + early]})).all()
        linked = (await s.execute(text(
            "SELECT count(*) FROM lead WHERE mobile = :m AND customer_id IS NOT NULL"), {"m": "+91" + m})).scalar_one()
        assert [(r.mobile, r.name) for r in names] == [("+91" + m, "Older Name")], names
        assert linked == 2
    finally:
        await s.rollback()
        await s.close()


async def test_a_lead_inserted_past_qualified_links_at_once(shop: Shop, sessions: Sessions,
                                                           client: httpx.AsyncClient) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    m = _mobile()
    seed = await _lead(client, ho, shop, _mobile())
    s = sessions()
    try:
        cid = (await s.execute(text(
            "INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
            "mobile, territory_id, owner_org_unit_id) SELECT :no, 'won', inquiry_type, mis_system_id, "
            "lead_source_id, 'Imported', :m, territory_id, owner_org_unit_id FROM lead WHERE id = CAST(:l AS uuid) "
            "RETURNING customer_id::text"), {"no": f"IMP{uuid.uuid4().hex[:6]}", "m": "+91" + m, "l": seed["id"]})).scalar_one()
        assert cid is not None
    finally:
        await s.rollback()
        await s.close()
