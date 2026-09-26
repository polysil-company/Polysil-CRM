"""The public lead form and QR codes, end to end over ASGI (FS-003a).

The world is the order tests' shop: a coded state, a district, one office with a
field officer (so `lead_auto_owner()` has someone to give a public lead to) and a
dealer. The WhatsApp code is read back from the outbox as the table owner, as the
sign-in tests do; the worker does not run here.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

shop = endpoints.shop
Shop = endpoints.Shop

pytestmark = pytest.mark.db

Sessions = Callable[[], AsyncSession]


@pytest_asyncio.fixture
async def mobiles(sessions: Sessions) -> AsyncIterator[list[str]]:
    """Fresh numbers for a test, and their challenges, codes and QR codes cleared after."""
    made: list[str] = []
    yield made
    c = sessions()
    e164 = ["+91" + m[-10:] for m in made]
    await c.execute(text("DELETE FROM lead_intake_challenge WHERE mobile = ANY(:m)"), {"m": e164})
    await c.execute(text("DELETE FROM notification_outbox WHERE recipient = ANY(:m)"), {"m": e164})
    await c.commit()
    await c.close()


def _mobile(made: list[str]) -> str:
    m = "97" + f"{uuid.uuid4().int % 10**8:08d}"
    made.append(m)
    return m


async def _code(sessions: Sessions, mobile: str) -> str:
    s = sessions()
    try:
        return str((await s.execute(text(
            "SELECT payload->>'code' FROM notification_outbox WHERE template_key = 'lead.verify' "
            "AND recipient = :m AND state = 'pending' ORDER BY created_at DESC LIMIT 1"),
            {"m": "+91" + mobile[-10:]})).scalar_one())
    finally:
        await s.close()


def _body(shop: Shop, mobile: str, code: str, **over: object) -> dict[str, object]:
    body: dict[str, object] = {"mobile": mobile, "code": code, "farmer_name": "Web Farmer",
                               "territory_id": shop.district, "village": "Vadod",
                               "mis_system": "drip"}
    body.update(over)
    return body


async def _lead(sessions: Sessions, inquiry_no: str) -> dict[str, object]:
    s = sessions()
    try:
        row = (await s.execute(text(
            "SELECT l.owner_user_id::text AS owner, l.owner_org_unit_id::text AS office, "
            "l.assigned_partner_id::text AS partner, l.created_by::text AS created_by, "
            "l.qr_code_id::text AS qr, src.code AS source, "
            "(SELECT count(*) FROM notification_outbox o WHERE o.template_key = 'lead_ack' "
            "  AND o.recipient = l.mobile) AS acks "
            "FROM lead l JOIN lead_source src ON src.id = l.lead_source_id WHERE l.inquiry_no = :n"),
            {"n": inquiry_no})).one()
        return dict(row._mapping)
    finally:
        await s.close()


async def test_a_verified_farmer_becomes_a_website_lead_owned_by_the_covering_officer(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, mobiles: list[str]) -> None:
    m = _mobile(mobiles)
    r = await client.post("/public/leads/verify", json={"mobile": m})
    assert r.status_code == 202, r.text
    assert r.json()["data"] == {"sent": True, "channel": "whatsapp", "expires_in": 600,
                                "resend_after": 60}
    code = await _code(sessions, m)
    r = await client.post("/public/leads", json=_body(shop, m, code))
    assert r.status_code == 201, r.text
    got = r.json()["data"]
    assert set(got) == {"inquiry_no", "created"} and got["created"] is True
    lead = await _lead(sessions, got["inquiry_no"])
    assert lead["source"] == "website"
    assert lead["created_by"] == get_settings().intake_user_id
    assert lead["owner"] == shop.ids["field_officer"], "routed to the covering officer (EC-2)"
    assert lead["office"] == shop.office and lead["partner"] is None
    assert lead["acks"] == 1, "the acknowledgement is queued once"

    # a lost 201: the same code again answers the same number (EC-3, plan review B-4)
    r = await client.post("/public/leads", json=_body(shop, m, code))
    assert r.status_code == 200 and r.json()["data"] == {"inquiry_no": got["inquiry_no"],
                                                         "created": False}
    # a second enquiry the same day, with a fresh code: the first number (rule 4)
    await client.post("/public/leads/verify", json={"mobile": m})
    again = await client.post("/public/leads", json=_body(shop, m, await _code(sessions, m),
                                                           farmer_name="Someone Else"))
    assert again.status_code == 200 and again.json()["data"]["inquiry_no"] == got["inquiry_no"]
    assert (await _lead(sessions, got["inquiry_no"]))["acks"] == 1


async def test_wrong_codes_count_and_burn_and_a_bad_territory_leaves_the_code_usable(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, mobiles: list[str]) -> None:
    """EC-3: a wrong code's count commits; a 422 elsewhere rolls the consumption back."""
    m = _mobile(mobiles)
    await client.post("/public/leads/verify", json={"mobile": m})
    code = await _code(sessions, m)
    # a state is refused, and the right code survives it
    r = await client.post("/public/leads", json=_body(shop, m, code, territory_id=shop.state))
    assert r.status_code == 422 and "territory_id" in r.json()["error"]["fields"], r.text
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(4):
        r = await client.post("/public/leads", json=_body(shop, m, wrong))
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_code"
    ok = await client.post("/public/leads", json=_body(shop, m, code))
    assert ok.status_code == 201, "four wrong codes do not burn it"

    m2 = _mobile(mobiles)
    await client.post("/public/leads/verify", json={"mobile": m2})
    code2 = await _code(sessions, m2)
    for _ in range(5):
        await client.post("/public/leads", json=_body(shop, m2, wrong))
    r = await client.post("/public/leads", json=_body(shop, m2, code2))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_code", \
        "five wrong codes burn it, so the counts committed"


async def test_a_qr_code_credits_its_dealer_and_counts_its_leads(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, mobiles: list[str]) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/lead-qr-codes", headers={**ho, **_key()},
                          json={"label": "Shah Irrigation counter", "campaign": "Krishi Mela",
                                "partner_id": shop.partner, "territory_id": shop.district})
    assert r.status_code == 201, r.text
    qr = r.json()["data"]
    try:
        assert len(qr["code"]) == 6 and qr["url"].endswith(f"/enquiry?qr={qr['code']}")
        form = await client.get("/public/lead-form", params={"qr": qr["code"].lower()})
        assert form.status_code == 200, form.text
        data = form.json()["data"]
        assert data["qr"]["label"] == "Shah Irrigation counter"
        assert data["qr"]["territory_id"] == shop.district
        assert any(s["id"] == shop.state for s in data["states"])
        kids = await client.get("/public/territories", params={"parent_id": shop.state})
        assert [t["id"] for t in kids.json()["data"]] == [shop.district]

        m = _mobile(mobiles)
        await client.post("/public/leads/verify", json={"mobile": m})
        r = await client.post("/public/leads",
                              json=_body(shop, m, await _code(sessions, m), qr=qr["code"]))
        assert r.status_code == 201, r.text
        lead = await _lead(sessions, r.json()["data"]["inquiry_no"])
        assert (lead["source"], lead["partner"], lead["qr"]) == ("qr_code", shop.partner, qr["id"])
        listed = (await client.get(f"{V1}/lead-qr-codes", headers=ho)).json()["data"]
        assert next(x for x in listed if x["id"] == qr["id"])["lead_count"] == 1

        # the dealer closes: the poster still captures, as a website lead (rule 11)
        s = sessions()
        await s.execute(text("UPDATE channel_partner SET is_active = false WHERE id = CAST(:p AS uuid)"),
                        {"p": shop.partner})
        await s.commit()
        await s.close()
        assert (await client.get("/public/lead-form", params={"qr": qr["code"]})).status_code == 404
        m2 = _mobile(mobiles)
        await client.post("/public/leads/verify", json={"mobile": m2})
        r = await client.post("/public/leads",
                              json=_body(shop, m2, await _code(sessions, m2), qr=qr["code"]))
        lead = await _lead(sessions, r.json()["data"]["inquiry_no"])
        assert (lead["source"], lead["partner"]) == ("website", None)
    finally:
        c = sessions()
        await c.execute(text("UPDATE channel_partner SET is_active = true WHERE id = CAST(:p AS uuid)"),
                        {"p": shop.partner})
        await c.execute(text("UPDATE lead SET qr_code_id = NULL WHERE qr_code_id = CAST(:q AS uuid)"),
                        {"q": qr["id"]})
        await c.execute(text("DELETE FROM activity_event WHERE entity_id = CAST(:q AS uuid)"), {"q": qr["id"]})
        await c.execute(text("DELETE FROM lead_qr_code WHERE id = CAST(:q AS uuid)"), {"q": qr["id"]})
        await c.commit()
        await c.close()


async def test_a_number_is_limited_to_three_codes_in_fifteen_minutes(
        client: httpx.AsyncClient, mobiles: list[str]) -> None:
    m = _mobile(mobiles)
    for _ in range(3):
        assert (await client.post("/public/leads/verify", json={"mobile": m})).status_code == 202
    r = await client.post("/public/leads/verify", json={"mobile": m})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


async def test_an_unknown_qr_code_and_a_bad_mobile_are_refused(client: httpx.AsyncClient) -> None:
    assert (await client.get("/public/lead-form", params={"qr": "ZZZZZZ"})).status_code == 404
    r = await client.post("/public/leads/verify", json={"mobile": "12345"})
    assert r.status_code == 422


async def test_a_qr_code_cannot_credit_a_dealer_outside_the_creators_reach(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Code review F-2: the insert policy checks the owning office only, and the
    foreign key sees every dealer; the service reads the dealer as the caller."""
    tag = uuid.uuid4().hex[:6]
    s = sessions()
    far_state = str((await s.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": f"api_far_{tag}", "c": "F" + tag[:3].upper()})).scalar_one())
    far = str((await s.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, mobile, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'Far Dealer', :m, CAST(:t AS uuid), 'dealer') RETURNING id"),
        {"c": f"FAR{tag}".upper(), "m": "9195" + f"{uuid.uuid4().int % 10**8:08d}",
         "t": far_state})).scalar_one())
    await s.commit()
    try:
        ho = await endpoints._as(client, shop, "field_officer")
        r = await client.post(f"{V1}/lead-qr-codes", headers={**ho, **_key()},
                              json={"label": "Not ours", "partner_id": far})
        assert r.status_code == 422 and r.json()["error"]["fields"] == {"partner_id": "not found"}, r.text
        c = sessions()
        try:
            made = (await c.execute(text("SELECT count(*) FROM lead_qr_code WHERE partner_id = CAST(:p AS uuid)"),
                                    {"p": far})).scalar_one()
        finally:
            await c.close()
        assert made == 0
    finally:
        await s.execute(text("DELETE FROM channel_partner WHERE id = CAST(:p AS uuid)"), {"p": far})
        await s.execute(text("DELETE FROM territory WHERE id = CAST(:t AS uuid)"), {"t": far_state})
        await s.commit()
        await s.close()


async def test_creating_a_qr_code_writes_its_event_visible_as_the_code_is(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Cross-vendor review: a QR code's creation is a state change (CLAUDE.md 4.1
    rule 7). Its event is read through the code's own visibility, so the dealer,
    who cannot see a code that is not theirs, cannot read the event either."""
    from api.db.session import enter_role

    ho = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/lead-qr-codes", headers={**ho, **_key()},
                          json={"label": "Fair stall"})
    assert r.status_code == 201, r.text
    qr = r.json()["data"]
    try:
        async def seen_by(user: str) -> list[str]:
            s = sessions()
            try:
                await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user})
                await enter_role(s, "app_role")
                return [k for (k,) in (await s.execute(text(
                    "SELECT kind FROM activity_event WHERE entity_id = CAST(:q AS uuid)"),
                    {"q": qr["id"]})).all()]
            finally:
                await s.rollback()
                await s.close()

        assert await seen_by(shop.ids["field_officer"]) == ["lead_qr_code.created"]
        assert await seen_by(shop.ids["dealer"]) == [], "the dealer cannot see this code or its event"
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM activity_event WHERE entity_id = CAST(:q AS uuid)"), {"q": qr["id"]})
        await c.execute(text("DELETE FROM lead_qr_code WHERE id = CAST(:q AS uuid)"), {"q": qr["id"]})
        await c.commit()
        await c.close()
