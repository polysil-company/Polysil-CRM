"""FS-016 over the API: sorting the lead list, crops and land, the territory's
level, and the names and quotations on the lead timeline.

The world is the order tests' shop: one office with a user per seeded role."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _lead(client: httpx.AsyncClient, shop: Shop, h: dict[str, str], **over: object) -> dict:
    body = {"farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
            "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
            "village": "Vadod", **over}
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json=body)
    assert r.status_code == 201, r.text
    return dict(r.json()["data"])


def _fields(r: httpx.Response) -> dict[str, str]:
    return dict(r.json()["error"].get("fields") or {})


async def _pages(client: httpx.AsyncClient, h: dict[str, str], params: dict[str, str]) -> list[dict]:
    """Every page of the list, two rows at a time."""
    out: list[dict] = []
    cursor = None
    for _ in range(50):
        p = {**params, "limit": "2", **({"cursor": cursor} if cursor else {})}
        r = await client.get(f"{V1}/leads", headers=h, params=p)
        assert r.status_code == 200, r.text
        out += r.json()["data"]
        cursor = r.json()["meta"].get("next_cursor")
        if not cursor:
            return out
    raise AssertionError("more than 50 pages")


# ── sorting (BE-001) ─────────────────────────────────────────────────────────

async def test_every_sort_pages_without_a_gap_or_a_repeat(client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-1: values 100, 100, 50 and four nulls, two to a page; nulls last both ways.
    EC-3: a name holding the old separator."""
    h = await endpoints._as(client, shop, "field_officer")
    tag = uuid.uuid4().hex[:6]
    values = ["100", "100", "50", None, None, None, None]
    names = [f"a|{tag} Patel", f"B{tag} Shah", f"c{tag} Joshi", f"D{tag} Rana", f"e{tag} Modi",
             f"F{tag} Desai", f"g{tag} Mehta"]
    made = [await _lead(client, shop, h, farmer_name=n, estimated_value=v)
            for n, v in zip(names, values, strict=True)]
    mine = {m["id"] for m in made}
    base = {"territory_id": shop.district, "q": tag}
    for sort in ("created_at", "farmer_name", "estimated_value"):
        for order in ("asc", "desc"):
            got = [x for x in await _pages(client, h, {**base, "sort": sort, "order": order})
                   if x["id"] in mine]
            ids = [x["id"] for x in got]
            assert len(ids) == len(set(ids)) == 7, (sort, order, ids)
            if sort == "farmer_name":
                keys = [x["farmer_name"].lower() for x in got]
                assert keys == sorted(keys, reverse=order == "desc"), (order, keys)
            if sort == "estimated_value":
                vals = [x["estimated_value"] for x in got]
                assert vals[3:] == [None] * 4, ("nulls last", order, vals)
                nums = [Decimal(v) for v in vals[:3]]
                assert nums == sorted(nums, reverse=order == "desc"), (order, vals)


async def test_a_cursor_belongs_to_its_sort(client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-4: a cursor made for one sort is refused for another; the old form still
    works for the default order and only for it."""
    h = await endpoints._as(client, shop, "field_officer")
    for _ in range(3):
        await _lead(client, shop, h)
    r = await client.get(f"{V1}/leads", headers=h,
                         params={"limit": "1", "sort": "farmer_name", "order": "asc"})
    cursor = r.json()["meta"]["next_cursor"]
    r = await client.get(f"{V1}/leads", headers=h,
                         params={"limit": "1", "sort": "farmer_name", "order": "desc", "cursor": cursor})
    assert r.status_code == 422 and "cursor" in _fields(r), r.text
    r = await client.get(f"{V1}/leads", headers=h, params={"limit": "1"})
    legacy = r.json()["meta"]["next_cursor"]
    assert "|" in base64.urlsafe_b64decode(legacy).decode(), "the default keeps the old form"
    assert (await client.get(f"{V1}/leads", headers=h,
                             params={"limit": "1", "cursor": legacy})).status_code == 200
    r = await client.get(f"{V1}/leads", headers=h,
                         params={"limit": "1", "sort": "farmer_name", "cursor": legacy})
    assert r.status_code == 422 and "cursor" in _fields(r), r.text


async def test_a_value_cursor_is_exact_and_refuses_nan(client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-3: the value round-trips as a Decimal; a tampered NaN is a 422, not a 500."""
    h = await endpoints._as(client, shop, "field_officer")
    tag = uuid.uuid4().hex[:6]
    for v in ("1234567.89", "1234567.88", "1234567.90"):
        await _lead(client, shop, h, farmer_name=f"V{tag}", estimated_value=v)
    p = {"q": tag, "sort": "estimated_value", "order": "desc", "limit": "1"}
    first = (await client.get(f"{V1}/leads", headers=h, params=p)).json()
    c = json.loads(base64.urlsafe_b64decode(first["meta"]["next_cursor"]))
    assert c["v"] == "1234567.90"
    second = (await client.get(f"{V1}/leads", headers=h, params={**p, "cursor": first["meta"]["next_cursor"]})).json()
    assert second["data"][0]["estimated_value"] == "1234567.89"
    for tampered in ({**c, "v": "NaN"}, {**c, "id": 123}, {**c, "id": []}):
        bad = base64.urlsafe_b64encode(json.dumps(tampered).encode()).decode()
        r = await client.get(f"{V1}/leads", headers=h, params={**p, "cursor": bad})
        assert r.status_code == 422 and "cursor" in _fields(r), (tampered, r.text)


async def test_an_unknown_sort_is_a_422(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    for params in ({"sort": "mobile"}, {"order": "sideways"}):
        assert (await client.get(f"{V1}/leads", headers=h, params=params)).status_code == 422


# ── crops and land (BE-003) ──────────────────────────────────────────────────

async def test_crops_and_land_on_create_patch_and_clear(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    lead = await _lead(client, shop, h, crops=["Cotton", "groundnut"], land_acres="4.50")
    assert [c["code"] for c in lead["crops"]] == ["cotton", "groundnut"], "the list's own code, in order"
    assert lead["crops"][0] == {"code": "cotton", "name": "Cotton", "is_active": True}
    assert lead["land_acres"] == "4.50"
    url = f"{V1}/leads/{lead['id']}"
    r = await client.patch(url, headers={**h, **_key()}, json={"crops": ["wheat"], "land_acres": "2"})
    assert r.status_code == 200, r.text
    assert [c["code"] for c in r.json()["data"]["crops"]] == ["wheat"]
    assert r.json()["data"]["land_acres"] == "2.00"
    tl = (await client.get(f"{url}/timeline", headers=h)).json()["data"]
    changed = next(e for e in tl if e["kind"] == "lead.updated")["payload"]["changed"]
    assert changed == {"crops": ["wheat"], "land_acres": "2"}, "strings in the payload (EC-5)"
    r = await client.patch(url, headers={**h, **_key()}, json={"crops": [], "land_acres": None})
    assert r.status_code == 200 and r.json()["data"]["crops"] == [] and r.json()["data"]["land_acres"] is None


@pytest.mark.parametrize("body", [
    {"crops": ["cotton", "COTTON"]}, {"crops": [""]}, {"crops": ["not_a_crop"]},
    {"crops": ["cotton"] + [f"c{i}" for i in range(10)]},
    {"land_acres": "4.505"}, {"land_acres": "100000"}, {"land_acres": "0"},
])
async def test_bad_crops_and_land_are_refused(client: httpx.AsyncClient, shop: Shop, body: dict) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    lead = await _lead(client, shop, h)
    r = await client.patch(f"{V1}/leads/{lead['id']}", headers={**h, **_key()}, json=body)
    assert r.status_code == 422, r.text
    assert set(_fields(r)) & {"crops", "land_acres"}, r.text


async def test_crops_null_says_send_an_empty_list(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    lead = await _lead(client, shop, h, crops=["cotton"])
    r = await client.patch(f"{V1}/leads/{lead['id']}", headers={**h, **_key()}, json={"crops": None})
    assert r.status_code == 422 and "crops" in _fields(r), r.text


async def test_a_switched_off_crop_stays_and_is_not_added(client: httpx.AsyncClient, shop: Shop,
                                                          sessions: Sessions) -> None:
    """EC-9: a form re-sending the whole record keeps working."""
    admin = await endpoints._as(client, shop, "admin_sales")
    code = f"t{uuid.uuid4().hex[:8]}"
    r = await client.post(f"{V1}/lookups/crops", headers={**admin, **_key()},
                          json={"code": code, "name": "Test Crop"})
    assert r.status_code == 201, r.text
    crop_id = r.json()["data"]["id"]
    try:
        h = await endpoints._as(client, shop, "field_officer")
        has = await _lead(client, shop, h, crops=["cotton", code])
        lacks = await _lead(client, shop, h)
        r = await client.patch(f"{V1}/lookups/crops/{crop_id}", headers={**admin, **_key()},
                               json={"is_active": False})
        assert r.status_code == 200, r.text
        r = await client.patch(f"{V1}/leads/{has['id']}", headers={**h, **_key()},
                               json={"crops": ["cotton", code], "farmer_name": "Kiritbhai M Shah"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["crops"][1] == {"code": code, "name": "Test Crop", "is_active": False}
        r = await client.patch(f"{V1}/leads/{lacks['id']}", headers={**h, **_key()}, json={"crops": [code]})
        assert r.status_code == 422 and "crops" in _fields(r), r.text
        listed = (await client.get(f"{V1}/lookups/crops", headers=h)).json()["data"]
        assert any(c["code"] == code and c["is_active"] is False for c in listed)
    finally:
        s = sessions()
        await s.execute(text("UPDATE lead SET crops = '{}' WHERE CAST(:c AS citext) = ANY(crops)"), {"c": code})
        await s.execute(text("DELETE FROM crop WHERE code = :c"), {"c": code})
        await s.commit()
        await s.close()


async def test_only_masters_edit_adds_a_crop_and_everyone_reads_the_list(
        client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/lookups/crops", headers={**h, **_key()}, json={"code": "zzz", "name": "Z"})
    assert r.status_code == 403, r.text
    listed = (await client.get(f"{V1}/lookups/crops", headers=h)).json()["data"]
    codes = {c["code"] for c in listed}
    assert {"cotton", "redgram_pigeonpea", "wheat"} <= codes and "select_crop_here" not in codes


# ── the territory's level (BE-005) ───────────────────────────────────────────

async def test_a_state_is_refused_and_a_village_is_not(client: httpx.AsyncClient, shop: Shop,
                                                       sessions: Sessions) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "A", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}", "territory_id": shop.state,
        "inquiry_type": "commercial", "mis_system": "drip"})
    assert r.status_code == 422 and "territory_id" in _fields(r), r.text
    s = sessions()
    village = str((await s.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('village', :n, CAST(:p AS uuid)) RETURNING id"),
        {"n": f"Vadod {uuid.uuid4().hex[:6]}", "p": shop.district})).scalar_one())
    await s.commit()
    try:
        lead = await _lead(client, shop, h, territory_id=village)
        url = f"{V1}/leads/{lead['id']}"
        r = await client.patch(url, headers={**h, **_key()}, json={"territory_id": village, "farmer_name": "B"})
        assert r.status_code == 200, "re-sending the same territory is never refused"
        r = await client.patch(url, headers={**h, **_key()}, json={"territory_id": shop.state})
        assert r.status_code == 422 and "territory_id" in _fields(r), r.text
        r = await client.post(f"{V1}/lead-qr-codes", headers={**h, **_key()},
                              json={"label": "Mela", "territory_id": shop.state})
        assert r.status_code in (403, 422), r.text
        dm = await endpoints._as(client, shop, "district_manager")
        r = await client.post(f"{V1}/lead-qr-codes", headers={**dm, **_key()},
                              json={"label": "Mela", "territory_id": shop.state})
        assert r.status_code == 422 and "territory_id" in _fields(r), r.text
    finally:
        await s.execute(text("DELETE FROM lead WHERE territory_id = CAST(:v AS uuid)"), {"v": village})
        await s.execute(text("DELETE FROM territory WHERE id = CAST(:v AS uuid)"), {"v": village})
        await s.commit()
        await s.close()


async def test_the_levels_filter(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    r = await client.get(f"{V1}/lookups/territories", headers=h, params={"levels": "district,taluka", "limit": "100"})
    assert r.status_code == 200 and {t["level"] for t in r.json()["data"]} <= {"district", "taluka"}
    for params in ({"levels": "hamlet"}, {"levels": "district", "level": "state"}):
        r = await client.get(f"{V1}/lookups/territories", headers=h, params=params)
        assert r.status_code == 422 and "levels" in _fields(r), r.text


# ── the timeline (BE-006, BE-017) ────────────────────────────────────────────

async def test_an_assignment_names_the_owner_and_the_partner(client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    lead = await _lead(client, shop, dm)
    url = f"{V1}/leads/{lead['id']}"
    r = await client.post(f"{url}/assign", headers={**dm, **_key()},
                          json={"owner_user_id": shop.ids["field_officer"], "assigned_partner_id": shop.partner})
    assert r.status_code == 200, r.text
    r = await client.post(f"{url}/assign", headers={**dm, **_key()}, json={"assigned_partner_id": None})
    assert r.status_code == 200, r.text
    tl = (await client.get(f"{url}/timeline", headers=dm)).json()["data"]
    assigned = [e["payload"] for e in tl if e["kind"] == "lead.assigned"]
    cleared, first = assigned[0], assigned[1]
    assert first["owner_name"] and first["partner_name"] == "Shah Irrigation", first
    assert cleared["partner_name"] is None and "owner_name" not in cleared, cleared


async def test_a_handover_names_the_previous_owner(client: httpx.AsyncClient, shop: Shop,
                                                   sessions: Sessions) -> None:
    """The handover's event shape (users.py), read through the API."""
    dm = await endpoints._as(client, shop, "district_manager")
    lead = await _lead(client, shop, dm)
    s = sessions()
    await s.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('lead', CAST(:l AS uuid), CAST(:l AS uuid), 'lead.assigned', CAST(:a AS uuid), CAST(:p AS jsonb))"),
        {"l": lead["id"], "a": shop.ids["district_manager"],
         "p": json.dumps({"owner_user_id": shop.ids["field_officer"],
                          "previous_owner_user_id": shop.ids["district_manager"], "handover": True})})
    await s.commit()
    await s.close()
    tl = (await client.get(f"{V1}/leads/{lead['id']}/timeline", headers=dm)).json()["data"]
    handover = next(e["payload"] for e in tl if e["payload"].get("handover"))
    assert handover["previous_owner_name"] and handover["owner_name"], handover


async def test_a_quotation_event_names_its_quotation(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    q = await endpoints._accepted_quotation(client, shop, h)
    tl = (await client.get(f"{V1}/leads/{q['lead']['id']}/timeline", headers=h)).json()["data"]
    quote_events = [e for e in tl if e["kind"].startswith("quotation.")]
    assert quote_events, [e["kind"] for e in tl]
    for e in quote_events:
        p = e["payload"]
        assert p["quotation_id"] == q["id"] and p["quote_no"] == q["quote_no"] and p["version"] == 1, e


async def test_a_discount_request_names_who_asked(client: httpx.AsyncClient, shop: Shop) -> None:
    """The frontend walk (29 Sep): an event a definer writes carries no name, and the
    history read "Polysil asked"; 022 names the actor for staff."""
    from tests.api import test_quotation_approval as qa
    h = await endpoints._as(client, shop, "field_officer")
    q = await qa._draft(client, shop, h, "8")
    r = await qa._ask(client, h, q["id"])
    assert r.status_code == 200, r.text
    tl = (await client.get(f"{V1}/leads/{q['lead']['id']}/timeline", headers=h)).json()["data"]
    asked = next(e for e in tl if e["kind"] == "quotation.approval_requested")
    assert asked["actor"]["full_name"] and asked["actor"]["id"] == shop.ids["field_officer"], asked


async def test_the_quotation_list_says_awaiting_approval(client: httpx.AsyncClient, shop: Shop) -> None:
    """The frontend walk: the list showed a waiting draft as a plain "Draft"."""
    from tests.api import test_quotation_approval as qa
    h = await endpoints._as(client, shop, "field_officer")
    q = await qa._draft(client, shop, h, "8")
    listed = (await client.get(f"{V1}/quotations", headers=h, params={"lead_id": q["lead"]["id"]})).json()["data"]
    assert [x["awaiting_approval"] for x in listed if x["id"] == q["id"]] == [False]
    assert (await qa._ask(client, h, q["id"])).status_code == 200
    listed = (await client.get(f"{V1}/quotations", headers=h, params={"lead_id": q["lead"]["id"]})).json()["data"]
    assert [x["awaiting_approval"] for x in listed if x["id"] == q["id"]] == [True]
