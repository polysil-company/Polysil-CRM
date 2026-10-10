"""FS-026 over the API: one order counted under each sale setting, as it moves
from approved to paid to dispatched. The setting is company-wide, so the test
restores it (the settings tests' `restore` fixture)."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import datetime as dt
import json
import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api import test_payments as payments_t
from tests.api.conftest import V1, _key
from tests.api.test_payments import (
    _forget_payments,  # noqa: F401  (autouse: payment rows before the shop)
)
from tests.api.test_settings_amend_reopen import restore  # noqa: F401  (fixture)

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _counts(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> dict[str, int]:
    """The dealer's order count under each mode."""
    admin = await endpoints._as(client, shop, "admin_sales")
    out = {}
    for mode in ("submission", "approval", "dispatch", "payment"):
        c = sessions()
        await c.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = 'sale_counted_at'"),
                        {"v": json.dumps(mode)})
        await c.commit()
        await c.close()
        data = (await client.get(f"{V1}/reports/dealer-performance", headers=admin,
                                 params={"territory_id": shop.district})).json()["data"]
        assert data["filters"]["sale_counted_at"] == mode
        row = next((x for x in data["rows"] if x["partner"]["id"] == shop.partner), None)
        out[mode] = row["orders"] if row else 0
    return out


async def test_one_order_counts_by_the_setting(client: httpx.AsyncClient, shop: Shop, sessions: Sessions,
                                               restore: None) -> None:  # noqa: F811
    order = await payments_t._approved(client, shop, partner_id=shop.partner)
    assert await _counts(client, shop, sessions) == {"submission": 1, "approval": 1, "dispatch": 0, "payment": 0}

    accounts = await endpoints._as(client, shop, "account_manager")
    total = order["totals"]["total"]
    r = await payments_t._pay(client, accounts, {"partner_id": shop.partner, "amount": total,
                                                 "allocations": [{"sales_order_id": order["id"], "amount": total}]})
    assert r.status_code == 201, r.text
    assert (await _counts(client, shop, sessions))["payment"] == 1, "paid in full today"

    hd = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()},
                          json={"dc_no": "DC-1", "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
                                "lines": [{"order_line_id": order["lines"][0]["id"], "qty": "10"}]})
    assert r.status_code == 201, r.text
    assert await _counts(client, shop, sessions) == {"submission": 1, "approval": 1, "dispatch": 1, "payment": 1}
    got = (await client.get(f"{V1}/orders/{order['id']}", headers=hd)).json()["data"]
    assert got["status"] == "dispatched" and got["fully_dispatched_at"] is not None


async def test_the_targets_achievement_says_which_setting_it_used(client: httpx.AsyncClient, shop: Shop) -> None:
    admin = await endpoints._as(client, shop, "admin_sales")
    month = today_ist().strftime("%Y-%m")
    r = await client.get(f"{V1}/targets/achievement", headers=admin, params={"month": month})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["filters"]["sale_counted_at"] == "approval", "the default"


async def test_a_rejected_draft_and_an_unshipped_short_order_never_count(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:  # noqa: F811
    """Plan review B-2 and B-3, in the reports and the lead 360."""
    fo = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/leads", headers={**fo, **_key()}, json={
        "farmer_name": "Short Order", "mobile": "96" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip"})
    assert r.status_code in (200, 201), r.text
    lead = r.json()["data"]["id"]
    for stage in ("contacted", "qualified"):           # an order needs an open lead
        r = await client.post(f"{V1}/leads/{lead}/transition", json={"to_stage": stage}, headers={**fo, **_key()})
        assert r.status_code == 200, r.text
    body = endpoints._direct(shop, partner_id=shop.partner, lead_id=lead)

    rejected = await endpoints._submit(client, fo, (await endpoints._create(client, fo, body))["id"])
    step = rejected["approval"]["steps"][0]
    r = await endpoints._decide(client, await endpoints._as(client, shop, step["role"]), step["id"], "reject", "Rate too low")
    assert r.status_code == 200 and r.json()["data"]["status"] == "draft", r.text

    short = await endpoints._approve_all(client, shop, await endpoints._submit(
        client, fo, (await endpoints._create(client, fo, body))["id"]))
    hd = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.post(f"{V1}/orders/{short['id']}/close-short", json={"remark": "Stopped"}, headers={**hd, **_key()})
    assert r.status_code == 200 and r.json()["data"]["status"] == "closed_short", r.text

    assert await _counts(client, shop, sessions) == {"submission": 0, "approval": 0, "dispatch": 0, "payment": 0}
    for mode in ("submission", "approval"):
        c = sessions()
        await c.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = 'sale_counted_at'"),
                        {"v": json.dumps(mode)})
        await c.commit()
        await c.close()
        r = await client.get(f"{V1}/leads/{lead}/360", headers=fo)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["summary"]["orders"] == 0, mode
