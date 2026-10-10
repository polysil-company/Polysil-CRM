"""FS-040 over the API and under RLS: campaigns, the campaign on a lead and a QR
code, and the campaign performance report."""

# ruff: noqa: E501  (request bodies and assertions)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from api.services.clock import today_ist
from tests.api import test_complaints as cmp
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import PASSWORD, V1, _key, _login

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


@dataclass
class Mkt:
    tag: str
    email: str
    user_id: str


@pytest_asyncio.fixture
async def mkt(shop: Shop, sessions: Sessions) -> AsyncIterator[Mkt]:
    """A Marketing user in the shop's office. Campaigns, and QR codes the test made,
    are removed before the shop's own teardown removes the leads."""
    tag = "cmp" + uuid.uuid4().hex[:8]
    email = f"{tag}_marketing@polysil.in"
    s = sessions()
    user_id = str((await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, :p, 'Meera Marketing', r.id, CAST(:o AS uuid) FROM role r "
        "WHERE r.code = 'marketing' RETURNING id"),
        {"e": email, "p": PasswordHasher().hash(PASSWORD), "o": shop.office})).scalar_one())
    await s.commit()
    await s.close()
    try:
        yield Mkt(tag, email, user_id)
    finally:
        c = sessions()
        camps = "(SELECT id FROM campaign WHERE name::text LIKE :t)"
        qrs = f"(SELECT id FROM lead_qr_code WHERE campaign_id IN {camps} OR label LIKE :t)"
        for stmt in (
            f"UPDATE lead SET campaign_id = NULL WHERE campaign_id IN {camps}",
            f"UPDATE lead SET qr_code_id = NULL WHERE qr_code_id IN {qrs}",
            f"DELETE FROM activity_event WHERE entity_type = 'lead_qr_code' AND entity_id IN {qrs}",
            f"DELETE FROM lead_qr_code WHERE id IN {qrs}",
            f"DELETE FROM activity_event WHERE entity_type = 'campaign' AND entity_id IN {camps}",
            f"DELETE FROM campaign WHERE id IN {camps}",
            "DELETE FROM idempotency_record WHERE user_id = CAST(:u AS uuid)",
            "DELETE FROM activity_event WHERE actor_id = CAST(:u AS uuid)",
            "DELETE FROM session WHERE user_id = CAST(:u AS uuid)",
            "DELETE FROM login_attempt WHERE identifier = CAST(:e AS citext)",
            "DELETE FROM app_user WHERE id = CAST(:u AS uuid)",
        ):
            await c.execute(text(stmt), {"t": f"{tag}%", "u": user_id, "e": email})
        await c.commit()
        await c.close()


async def _hm(client: httpx.AsyncClient, mkt: Mkt) -> dict[str, str]:
    return await _login(client, mkt.email, PASSWORD)


async def _camp(client: httpx.AsyncClient, h: dict[str, str], mkt: Mkt, name: str,
                **over: object) -> dict:
    body: dict[str, object] = {"name": f"{mkt.tag} {name}", "type": "agri_fair",
                               "start_date": today_ist().isoformat(),
                               "cost_planned": "150000.00", **over}
    r = await client.post(f"{V1}/campaigns", json=body, headers={**h, **_key()})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _lead(client: httpx.AsyncClient, h: dict[str, str], shop: Shop, **extra: object) -> dict:
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        **extra})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _patch(client: httpx.AsyncClient, h: dict[str, str], path: str,
                 body: dict) -> httpx.Response:
    return await client.patch(f"{V1}/{path}", json=body, headers={**h, **_key()})


# ── the campaign list ────────────────────────────────────────────────────────

async def test_marketing_keeps_campaigns(client: httpx.AsyncClient, shop: Shop, mkt: Mkt,
                                         sessions: Sessions) -> None:
    hm = await _hm(client, mkt)
    c = await _camp(client, hm, mkt, "Krishi Mela", territory_id=shop.district,
                    end_date=(today_ist() + dt.timedelta(days=2)).isoformat())
    assert (c["cost_planned"], c["cost_actual"], c["is_active"], c["lead_count"]) == (
        "150000.00", None, True, 0)
    assert c["territory"]["id"] == shop.district and c["summary"]["leads"] == 0

    # the name is unique, case ignored (rule: uq_campaign_name on citext)
    r = await client.post(f"{V1}/campaigns", headers={**hm, **_key()}, json={
        "name": f"{mkt.tag} KRISHI MELA", "type": "exhibition",
        "start_date": today_ist().isoformat()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "campaign_name_taken", r.text
    r = await client.post(f"{V1}/campaigns", headers={**hm, **_key()}, json={
        "name": f"{mkt.tag} Backwards", "type": "exhibition",
        "start_date": today_ist().isoformat(),
        "end_date": (today_ist() - dt.timedelta(days=1)).isoformat()})
    assert r.status_code == 422 and "end_date" in r.json()["error"]["fields"], r.text
    r = await client.post(f"{V1}/campaigns", headers={**hm, **_key()}, json={
        "name": f"{mkt.tag} Odd", "type": "carnival", "start_date": today_ist().isoformat()})
    assert r.status_code == 422, r.text

    other = await _camp(client, hm, mkt, "Dealer meet", type="dealer_meet")
    r = await _patch(client, hm, f"campaigns/{c['id']}",
                     {"cost_actual": "120000.50", "end_date": None, "description": "Stall 4"})
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert (got["cost_actual"], got["end_date"], got["description"]) == (
        "120000.50", None, "Stall 4")
    r = await _patch(client, hm, f"campaigns/{c['id']}", {"name": other["name"].upper()})
    assert r.status_code == 409, r.text
    r = await _patch(client, hm, f"campaigns/{c['id']}", {"name": None})
    assert r.status_code == 422, r.text
    r = await _patch(client, hm, f"campaigns/{c['id']}",
                     {"start_date": (today_ist() + dt.timedelta(days=9)).isoformat(),
                      "end_date": (today_ist() + dt.timedelta(days=8)).isoformat()})
    assert r.status_code == 422, r.text

    r = await client.get(f"{V1}/campaigns", params={"q": mkt.tag, "type": "dealer_meet"},
                         headers=hm)
    assert [x["id"] for x in r.json()["data"]] == [other["id"]], r.text
    r = await _patch(client, hm, f"campaigns/{c['id']}", {"is_active": False})
    assert r.status_code == 200 and r.json()["data"]["is_active"] is False, r.text
    r = await client.get(f"{V1}/campaigns", params={"q": mkt.tag, "active": "true"}, headers=hm)
    assert [x["id"] for x in r.json()["data"]] == [other["id"]], r.text
    r = await client.get(f"{V1}/campaigns", params={"q": mkt.tag, "active": "false"}, headers=hm)
    assert [x["id"] for x in r.json()["data"]] == [c["id"]], r.text

    s = sessions()
    kinds = (await s.execute(text(
        "SELECT kind, count(*) FROM activity_event WHERE entity_type = 'campaign' "
        "AND entity_id = CAST(:c AS uuid) GROUP BY kind"), {"c": c["id"]})).all()
    await s.close()
    assert dict(kinds) == {"campaign.created": 1, "campaign.updated": 2}, kinds


async def test_only_marketing_writes_and_cost_is_for_campaigns_view(
        client: httpx.AsyncClient, shop: Shop, mkt: Mkt, sessions: Sessions) -> None:
    hm = await _hm(client, mkt)
    c = await _camp(client, hm, mkt, "Bike campaign")
    ho = await endpoints._as(client, shop, "field_officer")
    r = await client.get(f"{V1}/campaigns", params={"q": mkt.tag}, headers=ho)
    assert r.status_code == 200, r.text
    row = r.json()["data"][0]
    assert row["id"] == c["id"] and row["cost_planned"] is None and row["cost_actual"] is None
    r = await client.get(f"{V1}/campaigns/{c['id']}", headers=ho)
    assert r.json()["data"]["summary"]["cost_per_lead"] is None, r.text

    r = await client.post(f"{V1}/campaigns", headers={**ho, **_key()}, json={
        "name": f"{mkt.tag} Mine", "type": "other", "start_date": today_ist().isoformat()})
    assert r.status_code == 403, r.text
    ha = await endpoints._as(client, shop, "admin_sales")
    assert (await _patch(client, ha, f"campaigns/{c['id']}", {"is_active": False})).status_code == 403
    r = await client.delete(f"{V1}/campaigns/{c['id']}", headers={**ha, **_key()})
    assert r.status_code == 403, r.text

    hd, mobile = await cmp._dealer(client, shop, sessions)
    try:
        r = await client.get(f"{V1}/campaigns", headers=hd)
        assert r.status_code == 403, r.text
        # a dealer reads no campaign, so cannot put one on a lead
        r = await client.post(f"{V1}/leads", headers={**hd, **_key()}, json={
            "farmer_name": "Dealer lead", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
            "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
            "campaign_id": c["id"]})
        assert r.status_code == 422 and "campaign_id" in r.json()["error"]["fields"], r.text
    finally:
        await cmp._forget(sessions, mobile)
    assert (await client.get(f"{V1}/campaigns/{uuid.uuid4()}", headers=hm)).status_code == 404
    assert (await client.get(f"{V1}/campaigns/not-a-uuid", headers=hm)).status_code == 422


async def _as_db(sessions: Sessions, user_id: str) -> AsyncSession:
    s = sessions()
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})
    await enter_role(s, "app_role")
    return s


async def test_the_policies_refuse_everyone_but_marketing(shop: Shop, mkt: Mkt,
                                                          sessions: Sessions) -> None:
    """The RLS floor under the route checks, negatives first."""
    officer = await _as_db(sessions, shop.ids["field_officer"])
    try:
        with pytest.raises(DBAPIError):
            async with officer.begin_nested():
                await officer.execute(text(
                    "INSERT INTO campaign (name, type, start_date) "
                    "VALUES (:n, 'other', CURRENT_DATE)"), {"n": f"{mkt.tag} sneaky"})
    finally:
        await officer.rollback()
        await officer.close()

    m = await _as_db(sessions, mkt.user_id)
    try:
        cid = (await m.execute(text(
            "INSERT INTO campaign (name, type, start_date) VALUES (:n, 'other', CURRENT_DATE) "
            "RETURNING id::text"), {"n": f"{mkt.tag} policy"})).scalar_one()
        await m.commit()
    finally:
        await m.close()

    officer = await _as_db(sessions, shop.ids["field_officer"])
    try:
        assert (await officer.execute(text("SELECT count(*) FROM campaign WHERE id = CAST(:c AS uuid)"),
                                      {"c": cid})).scalar_one() == 1
        upd = await officer.execute(text(
            "UPDATE campaign SET is_active = false WHERE id = CAST(:c AS uuid)"), {"c": cid})
        dele = await officer.execute(text("DELETE FROM campaign WHERE id = CAST(:c AS uuid)"),
                                     {"c": cid})
        assert (upd.rowcount, dele.rowcount) == (0, 0)  # type: ignore[attr-defined]
    finally:
        await officer.rollback()
        await officer.close()

    dealer = await _as_db(sessions, shop.ids["dealer"])
    try:
        assert (await dealer.execute(text("SELECT count(*) FROM campaign"))).scalar_one() == 0
    finally:
        await dealer.rollback()
        await dealer.close()


# ── the campaign on a lead ───────────────────────────────────────────────────

async def test_a_lead_names_its_campaign(client: httpx.AsyncClient, shop: Shop, mkt: Mkt,
                                         sessions: Sessions) -> None:
    hm = await _hm(client, mkt)
    c = await _camp(client, hm, mkt, "Farmer meeting", type="farmer_meeting")
    spare = await _camp(client, hm, mkt, "Spare")
    ho = await endpoints._as(client, shop, "field_officer")
    a = await _lead(client, ho, shop, campaign_id=c["id"])
    assert (a["campaign_id"], a["campaign_name"]) == (c["id"], c["name"])
    b = await _lead(client, ho, shop)
    assert b["campaign_id"] is None and b["campaign_name"] is None

    base = {"territory_id": shop.district}
    r = await client.get(f"{V1}/leads", params={**base, "campaign_id": c["id"]}, headers=ho)
    assert [x["id"] for x in r.json()["data"]] == [a["id"]], r.text
    r = await client.get(f"{V1}/leads", params={**base, "campaign_id": "none"}, headers=ho)
    ids = {x["id"] for x in r.json()["data"]}
    assert b["id"] in ids and a["id"] not in ids
    r = await client.get(f"{V1}/leads/stats", params={**base, "campaign_id": c["id"]}, headers=ho)
    assert r.json()["total"] == 1, r.text
    r = await client.get(f"{V1}/leads", params={"campaign_id": "nope"}, headers=ho)
    assert r.status_code == 422, r.text
    r = await client.get(f"{V1}/leads/export", params={**base, "campaign_id": c["id"]}, headers=ho)
    assert r.status_code == 200, r.text

    # switched off: no new lead takes it, the lead that has it may re-send it
    assert (await _patch(client, hm, f"campaigns/{c['id']}", {"is_active": False})).status_code == 200
    r = await client.post(f"{V1}/leads", headers={**ho, **_key()}, json={
        "farmer_name": "Late", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "campaign_id": c["id"]})
    assert r.status_code == 422 and "campaign_id" in r.json()["error"]["fields"], r.text
    r = await _patch(client, ho, f"leads/{a['id']}", {"campaign_id": c["id"], "village": "Vadod"})
    assert r.status_code == 200 and r.json()["data"]["campaign_id"] == c["id"], r.text
    r = await _patch(client, ho, f"leads/{b['id']}", {"campaign_id": c["id"]})
    assert r.status_code == 422, r.text
    r = await _patch(client, ho, f"leads/{b['id']}", {"campaign_id": spare["id"]})
    assert r.status_code == 200 and r.json()["data"]["campaign_name"] == spare["name"], r.text
    r = await _patch(client, ho, f"leads/{b['id']}", {"campaign_id": None})
    assert r.status_code == 200 and r.json()["data"]["campaign_id"] is None, r.text

    s = sessions()
    changed = (await s.execute(text(
        "SELECT payload -> 'changed' ->> 'campaign_id' FROM activity_event "
        "WHERE lead_id = CAST(:l AS uuid) AND kind = 'lead.updated' ORDER BY occurred_at"),
        {"l": b["id"]})).scalars().all()
    await s.close()
    assert changed == [spare["id"], None], changed

    # a campaign on a lead cannot be deleted, even by someone who cannot see the lead
    r = await client.delete(f"{V1}/campaigns/{c['id']}", headers={**hm, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "campaign_in_use", r.text
    unused = await _camp(client, hm, mkt, "Typo")
    r = await client.delete(f"{V1}/campaigns/{unused['id']}", headers={**hm, **_key()})
    assert r.status_code == 204, r.text
    assert (await client.get(f"{V1}/campaigns/{unused['id']}", headers=hm)).status_code == 404


# ── QR codes ─────────────────────────────────────────────────────────────────

async def test_a_qr_lead_takes_the_codes_campaign(client: httpx.AsyncClient, shop: Shop,
                                                  mkt: Mkt, sessions: Sessions) -> None:
    hm = await _hm(client, mkt)
    c = await _camp(client, hm, mkt, "Canopy")
    other = await _camp(client, hm, mkt, "Banner")
    off = await _camp(client, hm, mkt, "Old")
    await _patch(client, hm, f"campaigns/{off['id']}", {"is_active": False})
    ho = await endpoints._as(client, shop, "field_officer")

    r = await client.post(f"{V1}/lead-qr-codes", headers={**ho, **_key()},
                          json={"label": f"{mkt.tag} counter", "campaign_id": off["id"]})
    assert r.status_code == 422, r.text
    r = await client.post(f"{V1}/lead-qr-codes", headers={**ho, **_key()}, json={
        "label": f"{mkt.tag} counter", "campaign": "free text", "campaign_id": c["id"]})
    assert r.status_code == 201, r.text
    qr = r.json()["data"]
    assert (qr["campaign_id"], qr["campaign_name"], qr["campaign"]) == (c["id"], c["name"],
                                                                        "free text")
    r = await client.get(f"{V1}/public/lead-form", params={"qr": qr["code"]})
    assert r.json()["data"]["qr"]["campaign"] == c["name"], r.text

    seed = await _lead(client, ho, shop)
    s = sessions()
    insert = ("INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, "
              "farmer_name, mobile, territory_id, owner_org_unit_id, qr_code_id, campaign_id) "
              "SELECT :no, inquiry_type, mis_system_id, lead_source_id, farmer_name, mobile, "
              "territory_id, owner_org_unit_id, CAST(:q AS uuid), CAST(:c AS uuid) FROM lead "
              "WHERE id = CAST(:l AS uuid) RETURNING campaign_id::text")
    took = (await s.execute(text(insert), {"no": f"{mkt.tag}-1", "q": qr["id"], "c": None,
                                           "l": seed["id"]})).scalar_one()
    kept = (await s.execute(text(insert), {"no": f"{mkt.tag}-2", "q": qr["id"],
                                           "c": other["id"], "l": seed["id"]})).scalar_one()
    await s.commit()
    await s.close()
    assert (took, kept) == (c["id"], other["id"])

    # re-pointing the code moves new leads only; the free-text label shows once unlinked
    r = await _patch(client, ho, f"lead-qr-codes/{qr['id']}", {"campaign_id": None})
    assert r.status_code == 200 and r.json()["data"]["campaign_id"] is None, r.text
    r = await client.get(f"{V1}/public/lead-form", params={"qr": qr["code"]})
    assert r.json()["data"]["qr"]["campaign"] == "free text", r.text
    r = await _patch(client, ho, f"lead-qr-codes/{qr['id']}", {"campaign_id": off["id"]})
    assert r.status_code == 422, r.text
    s = sessions()
    still = (await s.execute(text(
        "SELECT campaign_id::text FROM lead WHERE inquiry_no = CAST(:n AS citext)"),
        {"n": f"{mkt.tag}-1"})).scalar_one()
    await s.close()
    assert still == c["id"]


# ── the report ───────────────────────────────────────────────────────────────

async def _won_lead(client: httpx.AsyncClient, shop: Shop, h: dict[str, str],
                    campaign_id: str) -> tuple[dict, dict]:
    lead = await _lead(client, h, shop, campaign_id=campaign_id, village="Vadod")
    for stage in ("contacted", "qualified"):
        r = await client.post(f"{V1}/leads/{lead['id']}/transition", json={"to_stage": stage},
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/quotations", headers={**h, **_key()}, json={
        "lead_id": lead["id"], "sales_type": "commercial",
        "place_of_supply_territory_id": shop.district, "seller_gstin_id": shop.seller,
        "price_effective_date": endpoints.AS_OF,
        "lines": [{"product_id": shop.product, "qty": "20", "discount_pct": "5"}]})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    for path, body in (("send", {"channel": "none"}), ("transition", {"to": "accepted"})):
        r = await client.post(f"{V1}/quotations/{q['id']}/{path}", json=body,
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
    draft = await endpoints._create(client, h, {"quotation_ids": [q["id"]]})
    order = await endpoints._approve_all(client, shop, await endpoints._submit(client, h, draft["id"]))
    return lead, order


async def test_the_campaign_report_counts_leads_sales_and_cost(
        client: httpx.AsyncClient, shop: Shop, mkt: Mkt) -> None:
    hm = await _hm(client, mkt)
    c = await _camp(client, hm, mkt, "Mela", cost_planned="90000.00", territory_id=shop.district)
    idle = await _camp(client, hm, mkt, "Idle", territory_id=shop.district,
                       start_date=(today_ist() - dt.timedelta(days=3)).isoformat(),
                       end_date=today_ist().isoformat())
    ho = await endpoints._as(client, shop, "field_officer")
    _, order = await _won_lead(client, shop, ho, c["id"])
    await _lead(client, ho, shop, campaign_id=c["id"])
    await _lead(client, ho, shop, campaign_id=c["id"])

    params = {"territory_id": shop.district}
    r = await client.get(f"{V1}/reports/campaign-performance", params=params, headers=hm)
    assert r.status_code == 200, r.text
    rows = {x["campaign"]["id"]: x for x in r.json()["data"]["rows"]}
    row = rows[c["id"]]
    assert (row["leads"], row["qualified"], row["won"], row["lost"], row["open"]) == (3, 1, 1, 0, 2), row
    assert row["conversion_pct"] == "33.3", row
    assert (row["cost"], row["cost_per_lead"], row["cost_per_won"]) == ("90000.00", "30000.00", "90000.00"), row
    assert r.json()["data"]["totals"] == {"leads": 3, "won": 1, "sales_value": None, "cost": "240000.00"}
    assert row["sales_count"] is None and row["sales_value"] is None, "Marketing has no sales_orders"
    zero = rows[idle["id"]]
    assert (zero["leads"], zero["cost_per_lead"], zero["cost"]) == (0, None, "150000.00"), zero

    # actual cost wins once entered
    await _patch(client, hm, f"campaigns/{c['id']}", {"cost_actual": "60000.00"})
    r = await client.get(f"{V1}/reports/campaign-performance", params=params, headers=hm)
    row = {x["campaign"]["id"]: x for x in r.json()["data"]["rows"]}[c["id"]]
    assert (row["cost"], row["cost_per_lead"]) == ("60000.00", "20000.00"), row

    # Admin Sales sees sales and cost (RBAC 6.1); a district manager sees sales, not cost
    ha = await endpoints._as(client, shop, "admin_sales")
    r = await client.get(f"{V1}/reports/campaign-performance", params=params, headers=ha)
    row = {x["campaign"]["id"]: x for x in r.json()["data"]["rows"]}[c["id"]]
    assert (row["sales_count"], row["sales_value"]) == (1, order["totals"]["total"]), row
    assert row["cost"] == "60000.00", row
    hdm = await endpoints._as(client, shop, "district_manager")
    r = await client.get(f"{V1}/reports/campaign-performance", params=params, headers=hdm)
    row = {x["campaign"]["id"]: x for x in r.json()["data"]["rows"]}[c["id"]]
    assert row["sales_value"] == order["totals"]["total"], row
    assert row["cost"] is None and row["cost_per_lead"] is None and row["cost_planned"] is None
    r = await client.get(f"{V1}/campaigns/{c['id']}", headers=ha)
    assert r.json()["data"]["summary"]["sales_value"] == order["totals"]["total"], r.text

    # the window picks the leads: a window before today has none of them
    old = {**params, "from": "2020-01-01", "to": "2020-01-31"}
    r = await client.get(f"{V1}/reports/campaign-performance", params=old, headers=hm)
    assert c["id"] not in {x["campaign"]["id"] for x in r.json()["data"]["rows"]}, r.text

    r = await client.get(f"{V1}/reports/campaign-performance",
                         params={**params, "format": "xlsx"}, headers=hm)
    assert r.status_code == 200 and r.content[:2] == b"PK", r.text[:200]


# ── edge cases (FS-040 §8) ───────────────────────────────────────────────────

async def test_cost_never_rides_the_event(client: httpx.AsyncClient, shop: Shop, mkt: Mkt,
                                          sessions: Sessions) -> None:
    """E-3: every staff user reads campaign events, so a cost change names the field only."""
    hm = await _hm(client, mkt)
    c = await _camp(client, hm, mkt, "Secret spend", cost_planned="123456.00")
    r = await _patch(client, hm, f"campaigns/{c['id']}", {"cost_actual": "98765.00", "description": "x"})
    assert r.status_code == 200, r.text
    s = sessions()
    payloads = (await s.execute(text(
        "SELECT payload::text FROM activity_event WHERE entity_type = 'campaign' "
        "AND entity_id = CAST(:c AS uuid)"), {"c": c["id"]})).scalars().all()
    await s.close()
    assert payloads and not any("123456" in p or "98765" in p for p in payloads), payloads
    assert any('"cost_actual": null' in p for p in payloads), payloads


async def test_a_campaign_with_no_end_is_one_day(client: httpx.AsyncClient, shop: Shop,
                                                 mkt: Mkt) -> None:
    """E-4: no end date does not mean forever; it is not in a later window."""
    hm = await _hm(client, mkt)
    c = await _camp(client, hm, mkt, "One day", territory_id=shop.district,
                    start_date=(today_ist() - dt.timedelta(days=10)).isoformat())
    params = {"territory_id": shop.district,
              "from": (today_ist() - dt.timedelta(days=5)).isoformat(), "to": today_ist().isoformat()}
    r = await client.get(f"{V1}/reports/campaign-performance", params=params, headers=hm)
    assert c["id"] not in {x["campaign"]["id"] for x in r.json()["data"]["rows"]}, r.text
    r = await client.get(f"{V1}/reports/campaign-performance",
                         params={**params, "from": (today_ist() - dt.timedelta(days=10)).isoformat()},
                         headers=hm)
    assert c["id"] in {x["campaign"]["id"] for x in r.json()["data"]["rows"]}, r.text


async def test_a_dealer_neither_reads_nor_clears_the_campaign(
        client: httpx.AsyncClient, shop: Shop, mkt: Mkt, sessions: Sessions) -> None:
    """E-7 and E-8."""
    hm = await _hm(client, mkt)
    c = await _camp(client, hm, mkt, "Dealer counter")
    hd, mobile = await cmp._dealer(client, shop, sessions)
    try:
        lead = await _lead(client, hd, shop)
        hdm = await endpoints._as(client, shop, "district_manager")
        r = await _patch(client, hdm, f"leads/{lead['id']}", {"campaign_id": c["id"]})
        assert r.status_code == 200 and r.json()["data"]["campaign_id"] == c["id"], r.text
        r = await client.get(f"{V1}/leads/{lead['id']}", headers=hd)
        assert r.status_code == 200, r.text
        assert (r.json()["data"]["campaign_id"], r.json()["data"]["campaign_name"]) == (None, None)
        r = await _patch(client, hd, f"leads/{lead['id']}", {"campaign_id": None})
        assert r.status_code == 422 and "campaign_id" in r.json()["error"]["fields"], r.text
        r = await client.get(f"{V1}/leads/{lead['id']}", headers=hdm)
        assert r.json()["data"]["campaign_id"] == c["id"], r.text
    finally:
        await cmp._forget(sessions, mobile)


async def test_a_merge_keeps_the_losers_campaign(client: httpx.AsyncClient, shop: Shop,
                                                 mkt: Mkt) -> None:
    """E-10: a QR lead merged into a hand-entered one keeps its attribution; a survivor
    with its own campaign keeps that."""
    hm = await _hm(client, mkt)
    a = await _camp(client, hm, mkt, "Mela A")
    b = await _camp(client, hm, mkt, "Mela B")
    ho = await endpoints._as(client, shop, "field_officer")
    hdm = await endpoints._as(client, shop, "district_manager")
    loser = await _lead(client, ho, shop, campaign_id=a["id"])
    survivor = await _lead(client, ho, shop)
    r = await client.post(f"{V1}/leads/{loser['id']}/merge", json={"into_lead_id": survivor["id"]},
                          headers={**hdm, **_key()})
    assert r.status_code == 200 and r.json()["data"]["campaign_id"] == a["id"], r.text
    r = await client.get(f"{V1}/leads/{survivor['id']}/timeline", headers=hdm)
    took = [e["payload"]["changed"] for e in r.json()["data"] if e["kind"] == "lead.updated"]
    assert {"campaign_id": a["id"], "campaign_name": a["name"]}.items() <= took[0].items(), took

    loser = await _lead(client, ho, shop, campaign_id=a["id"])
    survivor = await _lead(client, ho, shop, campaign_id=b["id"])
    r = await client.post(f"{V1}/leads/{loser['id']}/merge", json={"into_lead_id": survivor["id"]},
                          headers={**hdm, **_key()})
    assert r.status_code == 200 and r.json()["data"]["campaign_id"] == b["id"], r.text
