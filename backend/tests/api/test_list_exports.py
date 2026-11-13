"""FS-081 over the API: the 24 exports registered from their lists. Every route
answers Excel and CSV; a page-number list comes back whole; no list is cut short;
handler-level refusals and hidden figures carry over."""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import exports
from tests.api import test_exports as base
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1
from tests.conftest import Dealer

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]

# every new export, with filters that keep it small on a shared database
NEW: dict[str, dict[str, Any]] = {
    "products": {"q": "zz no such product"}, "tax-rates": {"hsn_code": "00000000"},
    "price-lists": {"status": "draft"}, "customers": {"q": "zz no such customer"},
    "stock": {"short_only": "true"}, "stock/movements": {}, "warehouses": {},
    "payments": {}, "warranty-terms": {}, "org-units": {"q": "zz no such office"},
    "territories": {"level": "state"}, "dealer-applications": {"q": "zz no such firm"},
    "campaigns": {"q": "zz no such campaign"}, "schemes": {"q": "zz no such scheme"},
    "scheme-entitlements": {}, "rewards/ledger": {}, "rewards/gift-redemptions": {},
    "reward-rules": {}, "gifts": {}, "subsidy-schemes": {}, "holidays": {"year": "2026"},
    "seller-gstins": {}, "ratings": {"max_score": "1"},
}


async def test_every_new_export_answers_excel_and_csv(client: httpx.AsyncClient, shop: Shop,
                                                      sessions: Sessions) -> None:
    """EC-7: every route, not a sample, so one placed behind a /{id} route shows."""
    h = await endpoints._as(client, shop, "admin_sales")
    s = sessions()
    list_id = str((await s.execute(text("SELECT id FROM price_list ORDER BY created_at DESC LIMIT 1"))).scalar_one())
    await s.close()
    paths = {**NEW, f"price-lists/{list_id}/items": {"q": "zz none"}}
    for path, params in paths.items():
        base._rows(await client.get(f"{V1}/{path}/export", headers=h, params=params))
        base._csv(await client.get(f"{V1}/{path}/export", headers=h, params={**params, "format": "csv"}))
        r = await client.get(f"{V1}/{path}/export", headers=h, params={**params, "format": "pdf"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "format_not_available", path


async def test_a_page_number_list_comes_back_whole(client: httpx.AsyncClient, shop: Shop,
                                                   sessions: Sessions) -> None:
    """EC-1, EC-4: products page by number; the file holds every matching row. The
    test makes its own 120 products, more than two screen pages of 50, so it does
    not depend on the catalogue a database happens to hold (CI's has few)."""
    tag = f"zz export whole {uuid.uuid4().hex[:8]}"
    s = sessions()
    await s.execute(text(
        "INSERT INTO product (description, product_category_id, quotation_category, uom_id) "
        "SELECT CAST(:d || ' ' || g AS citext), (SELECT id FROM product_category ORDER BY sort_order LIMIT 1), "
        "'field', (SELECT id FROM uom WHERE decimals = 0 LIMIT 1) FROM generate_series(1, 120) g"), {"d": tag})
    await s.commit()
    await s.close()
    h = await endpoints._as(client, shop, "admin_sales")
    rows = base._rows(await client.get(f"{V1}/products/export", headers=h, params={"q": tag}))
    assert len(rows) == 120


async def test_a_capped_list_is_asked_for_more_than_the_cap(client: httpx.AsyncClient, shop: Shop,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """EC-2: the screen still gets at most 200 and 500; the export asks for 5,001, so
    a long list is refused, never cut."""
    from api.services import campaigns, dealer_applications
    seen: dict[str, int] = {}

    async def apps(*_a: Any, limit: int = 200, **_k: Any) -> list:
        seen["apps"] = limit
        return []

    async def camps(*_a: Any, limit: int = 500, **_k: Any) -> list:
        seen["camps"] = limit
        return []

    monkeypatch.setattr(dealer_applications, "list_", apps)
    monkeypatch.setattr(campaigns, "list_campaigns", camps)
    h = await endpoints._as(client, shop, "admin_sales")
    for path, key, screen in (("dealer-applications", "apps", 200), ("campaigns", "camps", 500)):
        assert (await client.get(f"{V1}/{path}", headers=h)).status_code == 200
        assert seen[key] == screen
        base._rows(await client.get(f"{V1}/{path}/export", headers=h))
        assert seen[key] == exports.MAX_ROWS + 1, path


async def test_a_dealer_is_refused_staff_lists_gated_in_the_handler(
        client: httpx.AsyncClient, dealer: Dealer, sessions: Sessions) -> None:
    """Plan review S-3: these lists have no require() gate, so parity says nothing."""
    from tests.api.test_auth_endpoints import _otp_sign_in
    h = {"Authorization": f"Bearer {await _otp_sign_in(client, dealer, sessions)}"}
    for path in ("campaigns", "dealer-applications"):
        r = await client.get(f"{V1}/{path}/export", headers=h)
        assert r.status_code == 403, (path, r.text)


async def test_campaign_cost_is_blank_without_campaigns_view(client: httpx.AsyncClient, shop: Shop,
                                                             sessions: Sessions) -> None:
    """EC-10: the export runs the list handler as the caller, so its hiding carries over."""
    name = f"Export Melo {uuid.uuid4().hex[:8]}"
    s = sessions()
    cid = (await s.execute(text(
        "INSERT INTO campaign (name, type, start_date, cost_planned, cost_actual) "
        "VALUES (:n, 'exhibition', DATE '2026-10-01', 125000.50, 98000) RETURNING id"), {"n": name})).scalar_one()
    await s.commit()
    try:
        admin = base._rows(await client.get(f"{V1}/campaigns/export", params={"q": name},
                                            headers=await endpoints._as(client, shop, "admin_sales")))
        officer = base._rows(await client.get(f"{V1}/campaigns/export", params={"q": name},
                                              headers=await endpoints._as(client, shop, "field_officer")))
        assert [r["Name"] for r in admin] == [name] == [r["Name"] for r in officer]
        assert admin[0]["Planned cost"] == 125000.5 and admin[0]["Actual cost"] == 98000
        assert officer[0]["Planned cost"] is None and officer[0]["Actual cost"] is None
    finally:
        await s.execute(text("DELETE FROM campaign WHERE id = :i"), {"i": cid})
        await s.commit()
        await s.close()


async def test_a_scoped_export_holds_exactly_the_callers_list(client: httpx.AsyncClient, shop: Shop,
                                                             sessions: Sessions) -> None:
    """Rule 1 and the scope (code review F-1): a customer is seen through a lead. The
    field officer's file holds the customer on their own lead and not the one on the
    District Manager's lead in the same district; an administrator's holds both."""
    tag = uuid.uuid4().hex[:8]
    s = sessions()
    made: list[str] = []
    try:
        for i, owner in enumerate(("field_officer", "district_manager")):
            mobile = "+9196" + f"{uuid.uuid4().int % 10**8:08d}"
            cid = str((await s.execute(text(
                "INSERT INTO customer (name, mobile, territory_id) VALUES (:n, :m, CAST(:t AS uuid)) RETURNING id"),
                {"n": f"Export Kheti {tag} {owner}", "m": mobile, "t": shop.district})).scalar_one())
            made.append(cid)
            await s.execute(text(
                "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
                "mobile, territory_id, owner_user_id, owner_org_unit_id, created_by, customer_id) "
                "VALUES (:no, 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
                "(SELECT id FROM lead_source WHERE code = 'employee'), :name, :mob, CAST(:t AS uuid), "
                "CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:o AS uuid), CAST(:c AS uuid))"),
                {"no": f"CUS-{tag}-{i}", "name": f"Export Kheti {tag} {owner}", "mob": mobile,
                 "t": shop.district, "o": shop.ids[owner], "ou": shop.office, "c": cid})
        await s.commit()
        q = {"q": f"Export Kheti {tag}"}
        officer = await endpoints._as(client, shop, "field_officer")
        listed = (await client.get(f"{V1}/customers", headers=officer, params=q)).json()["data"]
        rows = base._rows(await client.get(f"{V1}/customers/export", headers=officer, params=q))
        assert [r["Name"] for r in rows] == [c["name"] for c in listed] == [f"Export Kheti {tag} field_officer"]
        admin = await endpoints._as(client, shop, "admin_sales")
        everyone = base._rows(await client.get(f"{V1}/customers/export", headers=admin, params=q))
        assert sorted(r["Name"] for r in everyone) == [f"Export Kheti {tag} district_manager",
                                                       f"Export Kheti {tag} field_officer"]
    finally:
        # the shop's teardown removes the leads; the customers must lose them first
        await s.execute(text("UPDATE lead SET customer_id = NULL WHERE customer_id = ANY(CAST(:c AS uuid[]))"),
                        {"c": made})
        await s.execute(text("DELETE FROM customer WHERE id = ANY(CAST(:c AS uuid[]))"), {"c": made})
        await s.commit()
        await s.close()
