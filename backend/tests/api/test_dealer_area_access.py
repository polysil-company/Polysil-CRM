"""FS-020: the dealers that serve a user's area, the dealer on a document they can
see, and the lead list's area filter. ISS-109 is the shape: a field officer in a
taluka office could not price, quote or order a lead whose dealer sits at the
district.

The world extends the order fixture: a taluka under its district with an office
under the district office and a field officer in it, a state distributor, a dealer
in the taluka, and a second district with its own dealer and its own lead.
"""

# ruff: noqa: E501  (embedded SQL, kept on one line so each statement reads whole)

from __future__ import annotations

import random
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import PASSWORD, V1, _key, _login
from tests.api.test_order_endpoints import AS_OF, Shop, shop  # noqa: F401  (the fixture)
from tests.api.test_order_endpoints import _as as _shop_as

pytestmark = pytest.mark.db


@dataclass
class Area:
    taluka: str
    office: str
    officer: str          # email of the field officer in the taluka office
    distributor: str      # at the state
    taluka_dealer: str
    far_district: str
    far_dealer: str       # in the other district: outside everyone's office area
    stray_dealer: str     # in the other district, on no document


def _partner_sql() -> str:
    return ("INSERT INTO channel_partner (partner_type, code, name, mobile, territory_id, price_tier, "
            "credit_limit, payment_terms_days) VALUES (CAST(:ty AS partner_type), :c, :n, :m, "
            "CAST(:t AS uuid), CAST(:tier AS channel_tier), 50000, 30) RETURNING id")


@pytest_asyncio.fixture
async def area(shop: Shop, sessions: Callable[[], AsyncSession]) -> AsyncIterator[Area]:  # noqa: F811
    tag = uuid.uuid4().hex[:8]
    s = sessions()

    async def one(sql: str, **p: object) -> str:
        if "ty" in p:
            p["tier"] = p["ty"]
        return str((await s.execute(text(sql), p)).scalar_one())

    taluka = await one("INSERT INTO territory (level, name, parent_id) VALUES ('taluka', :n, CAST(:p AS uuid)) RETURNING id",
                       n=f"area_taluka_{tag}", p=shop.district)
    far = await one("INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, CAST(:p AS uuid)) RETURNING id",
                    n=f"area_far_{tag}", p=shop.state)
    office = await one("INSERT INTO org_unit (name, role_level, territory_id, parent_id) VALUES (:n, 1, CAST(:t AS uuid), CAST(:p AS uuid)) RETURNING id",
                       n=f"area_office_{tag}", t=taluka, p=shop.office)
    email = f"area_fo_{tag}@polysil.in"
    await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, :p, 'Taluka Officer', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'field_officer'"),
        {"e": email, "p": PasswordHasher().hash(PASSWORD), "o": office})

    def mob() -> str:
        return "9194" + f"{random.randint(0, 10**8 - 1):08d}"

    distributor = await one(_partner_sql(), ty="distributor", c=f"DIS{tag}".upper(), n=f"State Distributor {tag}", m=mob(), t=shop.state)
    taluka_dealer = await one(_partner_sql(), ty="dealer", c=f"TAL{tag}".upper(), n=f"Taluka Dealer {tag}", m=mob(), t=taluka)
    far_dealer = await one(_partner_sql(), ty="dealer", c=f"FAR{tag}".upper(), n=f"Far Dealer {tag}", m=mob(), t=far)
    stray = await one(_partner_sql(), ty="dealer", c=f"STR{tag}".upper(), n=f"Stray Dealer {tag}", m=mob(), t=far)
    await s.commit()
    try:
        yield Area(taluka, office, email, distributor, taluka_dealer, far, far_dealer, stray)
    finally:
        c = sessions()
        terr = [taluka, far]
        partners = [distributor, taluka_dealer, far_dealer, stray]
        user = "(SELECT id FROM app_user WHERE email = CAST(:e AS citext))"
        # the officer's leads anywhere, the shop's district included
        leads = ("(SELECT id FROM lead WHERE territory_id = ANY(CAST(:t AS uuid[])) "
                 f"OR owner_user_id IN {user} OR created_by IN {user})")
        quotes = f"(SELECT id FROM quotation WHERE lead_id IN {leads})"
        orders = (f"(SELECT id FROM sales_order WHERE lead_id IN {leads} "
                  "OR territory_id = ANY(CAST(:t AS uuid[])))")
        for stmt in (
            f"DELETE FROM task WHERE assigned_to IN {user} OR assigned_by IN {user}",
            f"DELETE FROM approval_step WHERE request_id IN (SELECT id FROM approval_request WHERE entity_id IN {orders})",
            f"DELETE FROM approval_request WHERE entity_id IN {orders}",
            f"DELETE FROM activity_event WHERE entity_id IN {orders}",
            f"DELETE FROM order_quotation WHERE sales_order_id IN {orders}",
            f"DELETE FROM order_line WHERE sales_order_id IN {orders}",
            f"DELETE FROM sales_order WHERE id IN {orders}",
            "ALTER TABLE quotation DISABLE TRIGGER trg_quotation_refuse_sent_edit",
            f"DELETE FROM activity_event WHERE lead_id IN {leads}",
            f"DELETE FROM approval_step WHERE request_id IN (SELECT id FROM approval_request WHERE entity_id IN {quotes})",
            f"DELETE FROM approval_request WHERE entity_id IN {quotes}",
            f"UPDATE quotation SET supersedes_id = NULL, superseded_by_id = NULL WHERE id IN {quotes}",
            f"DELETE FROM quotation WHERE id IN {quotes}",
            "ALTER TABLE quotation ENABLE TRIGGER trg_quotation_refuse_sent_edit",
            f"DELETE FROM lead_duplicate_link WHERE lead_a_id IN {leads} OR lead_b_id IN {leads}",
            f"DELETE FROM notification_outbox WHERE recipient IN (SELECT mobile FROM lead WHERE id IN {leads})",
            f"DELETE FROM lead WHERE id IN {leads}",
            # leads at the shop's district point at these dealers; the shop clears the leads
            "UPDATE lead SET assigned_partner_id = NULL WHERE assigned_partner_id = ANY(CAST(:cp AS uuid[]))",
            "UPDATE quotation SET partner_id = NULL WHERE partner_id = ANY(CAST(:cp AS uuid[]))",
            f"DELETE FROM idempotency_record WHERE user_id IN {user}",
            f"DELETE FROM activity_event WHERE actor_id IN {user}",
            f"DELETE FROM session WHERE user_id IN {user}",
            "DELETE FROM login_attempt WHERE identifier = CAST(:e AS citext)",
            "DELETE FROM app_user WHERE email = CAST(:e AS citext)",
            "DELETE FROM channel_partner WHERE id = ANY(CAST(:cp AS uuid[]))",
            "DELETE FROM org_unit WHERE id = CAST(:o AS uuid)",
            "DELETE FROM territory WHERE id = ANY(CAST(:t AS uuid[]))",
        ):
            await c.execute(text(stmt), {"t": terr, "cp": partners, "e": email, "o": office})
        await c.commit()


async def _officer(client: httpx.AsyncClient, area: Area) -> dict[str, str]:
    return await _login(client, area.officer, PASSWORD)


async def _lead(client: httpx.AsyncClient, h: dict[str, str], territory: str) -> dict:
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": territory, "inquiry_type": "commercial", "mis_system": "drip"})
    assert r.status_code == 201, r.text
    lead = r.json()["data"]
    for stage in ("contacted", "qualified"):
        r = await client.post(f"{V1}/leads/{lead['id']}/transition", json={"to_stage": stage},
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
    return lead


async def _assign(client: httpx.AsyncClient, h: dict[str, str], lead_id: str, partner: str) -> None:
    r = await client.post(f"{V1}/leads/{lead_id}/assign", json={"assigned_partner_id": partner},
                          headers={**h, **_key()})
    assert r.status_code == 200, r.text


def _quote_body(shop: Shop, lead_id: str) -> dict[str, object]:  # noqa: F811
    return {"lead_id": lead_id, "sales_type": "commercial",
            "place_of_supply_territory_id": shop.district, "seller_gstin_id": shop.seller,
            "price_effective_date": AS_OF,
            "lines": [{"product_id": shop.product, "qty": "20", "discount_pct": "2"}]}


async def _picker(client: httpx.AsyncClient, h: dict[str, str]) -> set[str]:
    r = await client.get(f"{V1}/lookups/partners", params={"limit": 100}, headers=h)
    assert r.status_code == 200, r.text
    return {p["id"] for p in r.json()["data"]}


# ── the area rule ────────────────────────────────────────────────────────────

async def test_an_officer_sees_the_dealers_serving_his_area_and_no_others(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    """Above (district dealer, state distributor), at (taluka dealer); never the
    other district's (ISS-109, executed before the fix: none of the three)."""
    seen = await _picker(client, await _officer(client, area))
    assert {shop.partner, area.distributor, area.taluka_dealer} <= seen
    assert area.far_dealer not in seen and area.stray_dealer not in seen


async def test_a_district_manager_sees_the_dealers_under_the_district(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    """Before FS-020 the district office saw only a dealer at the district itself."""
    seen = await _picker(client, await _shop_as(client, shop, "district_manager"))
    assert {shop.partner, area.distributor, area.taluka_dealer} <= seen
    assert area.far_dealer not in seen


async def test_a_district_manager_edits_inside_the_district_but_not_the_state_distributor(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    """Reads reach up; writes do not (FS-020 rule 5)."""
    h = await _shop_as(client, shop, "district_manager")
    ok = await client.patch(f"{V1}/partners/{area.taluka_dealer}", json={"contact_name": "Mehul"},
                            headers={**h, **_key()})
    assert ok.status_code == 200, ok.text
    up = await client.patch(f"{V1}/partners/{area.distributor}", json={"contact_name": "Mehul"},
                            headers={**h, **_key()})
    assert up.status_code in (403, 404), up.text


async def test_credit_terms_are_only_for_those_who_may_edit_dealers(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    officer = await client.get(f"{V1}/partners/{area.taluka_dealer}",
                               headers=await _officer(client, area))
    assert officer.status_code == 200, officer.text
    row = officer.json()["data"]
    assert row["name"].startswith("Taluka Dealer")
    assert row["credit_limit"] is None and row["payment_terms_days"] is None
    manager = await client.get(f"{V1}/partners/{area.taluka_dealer}",
                               headers=await _shop_as(client, shop, "district_manager"))
    assert manager.json()["data"]["credit_limit"] == "50000.00"
    assert manager.json()["data"]["payment_terms_days"] == 30


# ── quoting and ordering a dealer lead (ISS-109) ────────────────────────────

async def test_an_officer_quotes_and_orders_a_lead_whose_dealer_sits_at_the_district(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    """The demo's path: a manager sets the district dealer, the taluka officer
    drafts, sends, and places the order, at the dealer's rate (90, not 100)."""
    ho = await _officer(client, area)
    lead = await _lead(client, ho, area.taluka)
    await _assign(client, await _shop_as(client, shop, "district_manager"), lead["id"], shop.partner)
    r = await client.post(f"{V1}/pricing/quote-lines", headers=ho, json={
        "place_of_supply_territory_id": shop.district, "partner_id": shop.partner, "as_of": AS_OF,
        "seller_gstin_id": shop.seller,
        "lines": [{"product_id": shop.product, "qty": "1"}]})
    assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/quotations", json=_quote_body(shop, lead["id"]), headers={**ho, **_key()})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    assert q["partner"]["id"] == shop.partner and q["partner"]["name"] == "Shah Irrigation"
    assert q["lines"][0]["rate"] == "90.00"
    for path, body in (("send", {"channel": "none"}), ("transition", {"to": "accepted"})):
        r = await client.post(f"{V1}/quotations/{q['id']}/{path}", json=body, headers={**ho, **_key()})
        assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/orders", json={"quotation_ids": [q["id"]]}, headers={**ho, **_key()})
    assert r.status_code == 201, r.text
    assert r.json()["data"]["partner"]["id"] == shop.partner


async def test_a_dealer_from_outside_the_area_prices_through_the_lead(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    """The safety net (FS-020 rule 1): an admin assigns the other district's dealer.
    The officer cannot read that dealer, yet prices, drafts and revises with it.
    A dealer on none of his documents stays refused."""
    ho = await _officer(client, area)
    lead = await _lead(client, ho, area.taluka)
    admin = await _shop_as(client, shop, "admin_sales")
    await _assign(client, admin, lead["id"], area.far_dealer)
    assert area.far_dealer not in await _picker(client, ho)
    # the stray dealer is on a document too, one the officer cannot see: the
    # visibility test inside the definer is what refuses it (code review F-3)
    theirs = await _lead(client, admin, area.far_district)
    await _assign(client, admin, theirs["id"], area.stray_dealer)

    def preview(partner: str) -> dict[str, object]:
        return {"place_of_supply_territory_id": shop.district, "partner_id": partner, "as_of": AS_OF,
                "seller_gstin_id": shop.seller,
                "lines": [{"product_id": shop.product, "qty": "1"}]}

    r = await client.post(f"{V1}/pricing/quote-lines", headers=ho, json=preview(area.far_dealer))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["lines"][0]["rate"] == "90.00"
    r = await client.post(f"{V1}/pricing/quote-lines", headers=ho, json=preview(area.stray_dealer))
    assert r.status_code == 422 and "partner_id" in r.json()["error"]["fields"], r.text

    r = await client.post(f"{V1}/quotations", json=_quote_body(shop, lead["id"]), headers={**ho, **_key()})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    assert q["partner"]["id"] == area.far_dealer and q["partner"]["name"].startswith("Far Dealer")
    # a draft edit cannot swap in a dealer the officer reaches through nothing
    r = await client.patch(f"{V1}/quotations/{q['id']}", json={"partner_id": area.stray_dealer,
                                                                "expected_status": "draft"},
                           headers={**ho, **_key()})
    assert r.status_code in (403, 422), r.text


async def test_a_dealer_caller_still_prices_only_as_itself(
        client: httpx.AsyncClient, shop: Shop, area: Area,  # noqa: F811
        sessions: Callable[[], AsyncSession]) -> None:
    from tests.api.test_complaints import _dealer
    h, _ = await _dealer(client, shop, sessions)
    r = await client.post(f"{V1}/pricing/quote-lines", headers=h, json={
        "place_of_supply_territory_id": shop.district, "partner_id": area.far_dealer, "as_of": AS_OF,
        "seller_gstin_id": shop.seller,
        "lines": [{"product_id": shop.product, "qty": "1"}]})
    assert r.status_code == 422 and "partner_id" in r.json()["error"]["fields"], r.text


# ── the area filter ──────────────────────────────────────────────────────────

async def test_the_areas_hold_the_callers_leads_with_counts_that_match_the_list(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    ho = await _officer(client, area)
    await _lead(client, ho, area.taluka)
    await _lead(client, ho, area.taluka)
    await _lead(client, ho, shop.district)      # at the district: no taluka counts it
    hm = await _shop_as(client, shop, "admin_sales")
    await _lead(client, hm, area.far_district)  # another district: not the officer's

    async def areas(h: dict[str, str], **params: str) -> dict[str, int]:
        r = await client.get(f"{V1}/leads/areas", params=params, headers=h)
        assert r.status_code == 200, r.text
        return {a["id"]: a["lead_count"] for a in r.json()["data"]}

    assert await areas(ho, level="state") == {shop.state: 3}
    assert await areas(ho, level="district") == {shop.district: 3}
    assert await areas(ho, level="taluka") == {area.taluka: 2}
    assert await areas(ho, level="taluka", parent_id=area.far_district) == {}

    admin = await areas(hm, level="district", parent_id=shop.state)
    assert admin == {shop.district: 3, area.far_district: 1}

    # the list, filtered to an area, holds exactly the area's count
    r = await client.get(f"{V1}/leads", params={"territory_id": area.taluka, "limit": 100,
                                                "include_total": "true"}, headers=ho)
    assert r.json()["meta"]["total"] == 2, r.text
    # the officer's exact counts above are the negative: the other district's lead
    # (in another office's reach) is in none of them


async def test_the_list_takes_several_areas_and_refuses_bad_lists(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    hm = await _shop_as(client, shop, "admin_sales")
    near = await _lead(client, hm, area.taluka)
    far = await _lead(client, hm, area.far_district)
    params = {"territory_id": f" {area.taluka},,{area.far_district},{area.taluka} ", "limit": 100}
    r = await client.get(f"{V1}/leads", params=params, headers=hm)
    assert r.status_code == 200, r.text
    ids = {x["id"] for x in r.json()["data"]}
    assert {near["id"], far["id"]} <= ids
    stats = await client.get(f"{V1}/leads/stats", params={"territory_id": params["territory_id"]},
                             headers=hm)
    assert stats.status_code == 200, stats.text
    assert stats.json()["total"] == len(ids), stats.text

    many = ",".join(str(uuid.uuid4()) for _ in range(21))
    r = await client.get(f"{V1}/leads", params={"territory_id": many}, headers=hm)
    assert r.status_code == 422 and "territory_id" in r.json()["error"]["fields"], r.text
    r = await client.get(f"{V1}/leads", params={"territory_id": f"{area.taluka},nope"}, headers=hm)
    assert r.status_code == 422 and "territory_id" in r.json()["error"]["fields"], r.text
    # forms uuid.UUID() accepts and the database refuses: a 500 before (code review F-2)
    for odd in (f"{{{area.taluka}}}", f"urn:uuid:{area.taluka}", area.taluka.replace("-", "")):
        for path in ("/leads", "/leads/stats"):
            r = await client.get(f"{V1}{path}", params={"territory_id": odd}, headers=hm)
            assert r.status_code == 422 and "territory_id" in r.json()["error"]["fields"], (odd, r.text)
    r = await client.get(f"{V1}/leads/areas", params={"level": "village"}, headers=hm)
    assert r.status_code == 422 and "level" in r.json()["error"]["fields"], r.text


# ── code review F-1 and F-5 ──────────────────────────────────────────────────

async def test_a_task_links_a_dealer_the_officer_now_sees(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    """task_link_visible_as() pastes the partners guard too; 028 first missed it
    (code review F-1). A manager links the officer's task to the taluka dealer, and
    the officer links his own to the district dealer."""
    from api.services.clock import today_ist
    ho = await _officer(client, area)
    me = (await client.get(f"{V1}/auth/me", headers=ho)).json()["data"]["id"]
    body = {"title": "Visit the dealer", "task_type": "visit", "due_at": today_ist().isoformat()}
    hm = await _shop_as(client, shop, "district_manager")
    r = await client.post(f"{V1}/tasks", headers={**hm, **_key()},
                          json={**body, "assigned_to": me, "partner_id": area.taluka_dealer})
    assert r.status_code == 201, r.text
    r = await client.post(f"{V1}/tasks", headers={**ho, **_key()},
                          json={**body, "partner_id": shop.partner})
    assert r.status_code == 201, r.text
    r = await client.post(f"{V1}/tasks", headers={**ho, **_key()},
                          json={**body, "partner_id": area.stray_dealer})
    assert r.status_code == 422, r.text


async def _accepted(client: httpx.AsyncClient, shop: Shop, h: dict[str, str], lead_id: str) -> str:  # noqa: F811
    r = await client.post(f"{V1}/quotations", json=_quote_body(shop, lead_id), headers={**h, **_key()})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    for path, body in (("send", {"channel": "none"}), ("transition", {"to": "accepted"})):
        r = await client.post(f"{V1}/quotations/{q['id']}/{path}", json=body, headers={**h, **_key()})
        assert r.status_code == 200, r.text
    return str(q["id"])


async def test_a_consolidated_order_needs_a_dealer_the_caller_can_read(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    """The dealer is the buyer of record and its details print on the order. Known
    only through the leads, it is a 422, not a 500 (code review F-5)."""
    ho = await _officer(client, area)
    admin = await _shop_as(client, shop, "admin_sales")
    ids = []
    for _ in range(2):
        lead = await _lead(client, ho, area.taluka)
        await _assign(client, admin, lead["id"], area.far_dealer)
        ids.append(await _accepted(client, shop, ho, lead["id"]))
    r = await client.post(f"{V1}/orders", json={"quotation_ids": ids}, headers={**ho, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "partner_not_readable", r.text


async def test_a_draft_takes_the_leads_dealer_later_through_the_guard(
        client: httpx.AsyncClient, shop: Shop, area: Area) -> None:  # noqa: F811
    """EC-4: drafted as a direct sale, then given the lead's far dealer. The UPDATE
    passes the parent guard only through the document arm."""
    ho = await _officer(client, area)
    lead = await _lead(client, ho, area.taluka)
    await _assign(client, await _shop_as(client, shop, "admin_sales"), lead["id"], area.far_dealer)
    r = await client.post(f"{V1}/quotations", json={**_quote_body(shop, lead["id"]), "partner_id": None},
                          headers={**ho, **_key()})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    assert q["partner"] is None
    r = await client.patch(f"{V1}/quotations/{q['id']}", json={"partner_id": area.far_dealer,
                                                                "expected_status": "draft"},
                           headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["partner"]["id"] == area.far_dealer
    assert r.json()["data"]["lines"][0]["rate"] == "90.00"
