"""FS-070: the frontend's asks BE-024 to BE-030 (BE-023 is in test_subsidy_applications).

Each filter narrows and leaving it out changes nothing; each new field is present and
right, and absent where the caller may not see it.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_complaints as complaints
from tests.api import test_order_endpoints as endpoints
from tests.api import test_schemes as schemes
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
made = schemes.made
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


# ── BE-024: categories and units ─────────────────────────────────────────────

async def test_the_category_and_unit_lookups_list_every_live_code(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    tag = uuid.uuid4().hex[:6].upper()
    s = sessions()
    await s.execute(text("INSERT INTO product_category (code, name, is_active) VALUES (:c, 'Gone', true), (:o, 'Off', false)"),
                    {"c": f"GONE{tag}", "o": f"OFF{tag}"})
    await s.execute(text("UPDATE product_category SET deleted_at = now() WHERE code = :c"), {"c": f"GONE{tag}"})
    await s.execute(text("INSERT INTO uom (code, name, decimals, deleted_at) VALUES (:u, 'Gone', 0, now())"),
                    {"u": f"GU{tag}"})
    await s.commit()
    try:
        r = await client.get(f"{V1}/lookups/product-categories", headers=h)
        assert r.status_code == 200, r.text
        rows = {x["code"]: x for x in r.json()["data"]}
        assert f"GONE{tag}" not in rows, "a soft-deleted category is listed"
        off = rows[f"OFF{tag}"]
        assert off["is_active"] is False and off["id"] and isinstance(off["sort_order"], int)
        r = await client.get(f"{V1}/lookups/uoms", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["data"] and all(0 <= u["decimals"] <= 3 for u in r.json()["data"])
        assert f"GU{tag}" not in {u["code"] for u in r.json()["data"]}, "a soft-deleted unit is listed"
    finally:
        await s.execute(text("DELETE FROM uom WHERE code = :u"), {"u": f"GU{tag}"})
        await s.execute(text("DELETE FROM product_category WHERE code IN (:c, :o)"),
                        {"c": f"GONE{tag}", "o": f"OFF{tag}"})
        await s.commit()
        await s.close()


@pytest.mark.parametrize("path", ["product-categories", "uoms"])
async def test_the_lookups_need_products_view(client: httpx.AsyncClient, shop: Shop, path: str) -> None:
    h = await endpoints._as(client, shop, "qc_manager")
    r = await client.get(f"{V1}/lookups/{path}", headers=h)
    assert r.status_code == 403, r.text


# ── BE-025: document types per record ────────────────────────────────────────

async def test_document_types_follow_the_record(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    every = {x["code"] for x in (await client.get(f"{V1}/documents/types", headers=h)).json()["data"]}
    assert len(every) == 16  # FS-071 added deposit_slip
    lead = {x["code"] for x in (await client.get(f"{V1}/documents/types", headers=h,
                                                 params={"record_type": "lead"})).json()["data"]}
    dealer = {x["code"] for x in (await client.get(f"{V1}/documents/types", headers=h,
                                                   params={"record_type": "dealer_application"})).json()["data"]}
    assert "gst_certificate" not in lead and "invoice" in lead and "other" in lead
    assert dealer == {"gst_certificate", "pan_card", "cancelled_cheque", "shop_photo", "shop_licence", "deposit_slip",
                      "other"}
    r = await client.get(f"{V1}/documents/types", headers=h, params={"record_type": "farm"})
    assert r.status_code == 422, r.text


# ── BE-026: lookup row fields ────────────────────────────────────────────────

async def test_lookup_rows_carry_sort_order_quality_and_kind(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    admin = await endpoints._as(client, shop, "admin_sales")
    fo = await endpoints._as(client, shop, "field_officer")
    code = f"t_{uuid.uuid4().hex[:8]}"
    r = await client.post(f"{V1}/lookups/lead-sources", headers={**admin, **_key()},
                          json={"code": code, "name": "Test source", "sort_order": 7, "quality": "0.555"})
    assert r.status_code == 201, r.text
    made_row = r.json()["data"]
    try:
        assert made_row["sort_order"] == 7 and Decimal(made_row["quality"]) == Decimal("0.56"), \
            "the answer is the stored row"
        mine = next(x for x in (await client.get(f"{V1}/lookups/lead-sources", headers=admin)).json()["data"]
                if x["code"] == code)
        assert Decimal(mine["quality"]) == Decimal("0.56") and mine["kind"] is None
        theirs = next(x for x in (await client.get(f"{V1}/lookups/lead-sources", headers=fo)).json()["data"]
                  if x["code"] == code)
        assert theirs["quality"] is None and theirs["sort_order"] == 7, "quality is for Masters editors"
        reasons = (await client.get(f"{V1}/lookups/lost-reasons", headers=fo)).json()["data"]
        assert reasons and all(x["kind"] == "lost" for x in reasons)
        systems = (await client.get(f"{V1}/lookups/mis-systems", headers=fo)).json()["data"]
        assert systems and all(x["sort_order"] is None for x in systems)
        r = await client.patch(f"{V1}/lookups/lead-sources/{made_row['id']}", headers={**admin, **_key()},
                               json={"sort_order": 2**31})
        assert r.status_code == 422, r.text
    finally:
        s = sessions()
        await s.execute(text("DELETE FROM lead_source WHERE code = :c"), {"c": code})
        await s.commit()
        await s.close()


# ── BE-027: scheme target names ──────────────────────────────────────────────

async def test_scheme_targets_carry_names_and_an_echo_changes_nothing(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    targets = [{"type": "territory", "id": shop.district}, {"type": "partner_type", "id": "dealer"},
               {"type": "partner", "id": shop.partner}, {"type": "product", "id": shop.product}]
    sch = await schemes._scheme(client, shop, made, targets=targets)
    names = {t["type"]: t["name"] for t in sch["targets"]}
    s = sessions()
    want = (await s.execute(text(
        "SELECT (SELECT name FROM territory WHERE id = CAST(:d AS uuid)) AS terr, "
        "(SELECT name FROM channel_partner WHERE id = CAST(:p AS uuid)) AS part, "
        "(SELECT description FROM product WHERE id = CAST(:x AS uuid)) AS prod"),
        {"d": shop.district, "p": shop.partner, "x": shop.product})).one()
    await s.close()
    assert names == {"territory": want.terr, "partner_type": "dealer", "partner": want.part, "product": want.prod}

    s = sessions()
    cat = (await s.execute(text(
        "SELECT c.id, c.name FROM product_category c JOIN product p ON p.product_category_id = c.id "
        "WHERE p.id = CAST(:x AS uuid)"), {"x": shop.product})).one()
    await s.close()
    by_cat = await schemes._scheme(client, shop, made, targets=[
        {"type": "territory", "id": shop.district}, {"type": "product_category", "id": str(cat.id)}])
    assert {t["type"]: t["name"] for t in by_cat["targets"]}["product_category"] == cat.name

    h = await endpoints._as(client, shop, "admin_sales")
    r = await client.patch(f"{V1}/schemes/{sch['id']}", json={"is_active": False}, headers={**h, **_key()})
    assert r.status_code == 200, r.text
    echoed = [dict(t, name="ગુજરાત " * 200) for t in r.json()["data"]["targets"]]
    r = await client.patch(f"{V1}/schemes/{sch['id']}", json={"targets": echoed}, headers={**h, **_key()})
    assert r.status_code == 200, r.text
    assert {t["type"]: t["name"] for t in r.json()["data"]["targets"]} == names, "names are never stored"


async def test_a_dealer_reads_target_names_but_no_partner_targets(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    sch = await schemes._scheme(client, shop, made, targets=[
        {"type": "partner_type", "id": "dealer"}, {"type": "partner", "id": shop.partner},
        {"type": "product", "id": shop.product}])
    h, mobile = await complaints._dealer(client, shop, sessions)
    try:
        r = await client.get(f"{V1}/schemes/{sch['id']}", headers=h)
        assert r.status_code == 200, r.text
        seen = {t["type"]: t["name"] for t in r.json()["data"]["targets"]}
        assert "partner" not in seen and seen["partner_type"] == "dealer" and seen["product"]
    finally:
        await complaints._forget(sessions, mobile)


# ── BE-029: orderable quotations ─────────────────────────────────────────────

async def _orderable(client: httpx.AsyncClient, h: dict[str, str], lead_id: str, **params: str) -> set[str]:
    r = await client.get(f"{V1}/quotations", headers=h,
                         params={"orderable": "true", "lead_id": lead_id, "include_total": "true", **params})
    assert r.status_code == 200, r.text
    rows = {x["id"] for x in r.json()["data"]}
    assert r.json()["meta"]["total"] == len(rows), "the total counts the same rows"
    return rows


async def test_orderable_lists_only_accepted_quotations_on_no_live_order(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await endpoints._as(client, shop, "field_officer")
    q = await endpoints._accepted_quotation(client, shop, ho)
    lead = q["lead"]["id"]
    assert await _orderable(client, ho, lead) == {q["id"]}

    order = await endpoints._create(client, ho, {"quotation_ids": [q["id"]]})
    assert await _orderable(client, ho, lead) == set(), "a draft order holds it, the caller's own too"
    r = await client.post(f"{V1}/orders/{order['id']}/cancel", json={"remark": "Wrong lead"},
                          headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    assert await _orderable(client, ho, lead) == {q["id"]}, "cancelling releases it"

async def test_orderable_leaves_out_a_quotation_not_yet_accepted(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-1: the status rule on its own, with no `status` param."""
    ho = await endpoints._as(client, shop, "field_officer")
    lead = (await client.post(f"{V1}/leads", headers={**ho, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod"})).json()["data"]
    for stage in ("contacted", "qualified"):
        r = await client.post(f"{V1}/leads/{lead['id']}/transition", json={"to_stage": stage},
                              headers={**ho, **_key()})
        assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/quotations", headers={**ho, **_key()}, json={
        "lead_id": lead["id"], "sales_type": "commercial",
        "place_of_supply_territory_id": shop.district, "seller_gstin_id": shop.seller,
        "price_effective_date": endpoints.AS_OF,
        "lines": [{"product_id": shop.product, "qty": "20", "discount_pct": "5"}]})
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    every = await client.get(f"{V1}/quotations", headers=ho, params={"lead_id": lead["id"]})
    assert {x["id"] for x in every.json()["data"]} == {q["id"]}, "without the filter nothing changes"
    assert await _orderable(client, ho, lead["id"]) == set(), "a draft is not orderable"
    r = await client.post(f"{V1}/quotations/{q['id']}/send", json={"channel": "none"},
                          headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    assert await _orderable(client, ho, lead["id"]) == set(), "a sent quotation is not orderable"


async def test_a_returned_order_holds_its_quotation_and_a_deleted_draft_frees_it(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Edge case EC-9: an approver's rejection returns the order to draft and keeps the
    hold; deleting a never-submitted draft releases it."""
    ho = await endpoints._as(client, shop, "field_officer")
    q = await endpoints._accepted_quotation(client, shop, ho)
    lead = q["lead"]["id"]
    order = await endpoints._submit(client, ho, (await endpoints._create(
        client, ho, {"quotation_ids": [q["id"]]}))["id"])
    hm = await endpoints._as(client, shop, "district_manager")
    r = await endpoints._decide(client, hm, order["approval"]["steps"][0]["id"], "reject", "Rate too low")
    assert r.status_code == 200, r.text
    assert await _orderable(client, ho, lead) == set(), "a returned order still holds it"
    r = await client.post(f"{V1}/orders/{order['id']}/cancel", json={"remark": "Start again"},
                          headers={**ho, **_key()})
    assert r.status_code == 200, r.text

    draft = await endpoints._create(client, ho, {"quotation_ids": [q["id"]]})
    assert await _orderable(client, ho, lead) == set()
    admin = await endpoints._as(client, shop, "md_ceo")
    r = await client.delete(f"{V1}/orders/{draft['id']}", headers={**admin, **_key()})
    assert r.status_code == 204, r.text
    assert await _orderable(client, ho, lead) == {q["id"]}, "deleting the draft releases it"


# ── BE-030: features on /auth/me ─────────────────────────────────────────────

async def _setting(sessions: Sessions, value: str | None, description: str) -> None:
    s = sessions()
    if value is None:
        await s.execute(text("DELETE FROM app_setting WHERE key = 'tasks_for_dealers'"))
    else:
        await s.execute(text(
            "INSERT INTO app_setting (key, kind, value, allowed, description) VALUES "
            "('tasks_for_dealers', 'choice', to_jsonb(CAST(:v AS text)), '[\"off\", \"on\"]', "
            ":d) ON CONFLICT (key) DO UPDATE SET value = to_jsonb(CAST(:v AS text))"),
            {"v": value, "d": description})
    await s.commit()
    await s.close()


async def test_me_says_whether_tasks_are_on_for_dealers(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    s = sessions()
    before, description = (await s.execute(text(
        "SELECT value #>> '{}', description FROM app_setting WHERE key = 'tasks_for_dealers'"))).one()
    await s.close()
    h = await endpoints._as(client, shop, "field_officer")
    dealer, mobile = await complaints._dealer(client, shop, sessions)
    try:
        for value, want in (("on", True), ("off", False), (None, False)):
            await _setting(sessions, value, description)
            for who in (h, dealer):
                r = await client.get(f"{V1}/auth/me", headers=who)
                assert r.status_code == 200, (value, r.text)
                assert r.json()["data"]["features"] == {"tasks_for_dealers": want}, value
    finally:
        await _setting(sessions, before, description)
        await complaints._forget(sessions, mobile)
