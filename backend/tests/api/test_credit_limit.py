"""FS-027 over the API: the credit check at submit under each setting, who sees the
flag, benefits applied by the same submit, the credit endpoint's readers, and two
submits for one dealer racing. The setting is company-wide, so tests restore it."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_order_concurrency as conc
from tests.api import test_order_endpoints as endpoints
from tests.api import test_schemes as schemes_t
from tests.api.conftest import V1, _key
from tests.api.test_payments import (
    _forget_payments,  # noqa: F401  (autouse: payment rows before the shop)
)
from tests.api.test_schemes import made  # noqa: F401  (fixture)
from tests.api.test_settings_amend_reopen import restore  # noqa: F401  (fixture)

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
REFUSED = "This order would take the dealer over its credit limit."


async def _owner_sql(sessions: Sessions, sql: str, params: dict[str, Any]) -> None:
    c = sessions()
    await c.execute(text(sql), params)
    await c.commit()
    await c.close()


async def _mode(sessions: Sessions, mode: str) -> None:
    await _owner_sql(sessions, "UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = 'dealer_credit_check'",
                     {"v": json.dumps(mode)})


async def _limit(sessions: Sessions, shop: Shop, limit: str | None) -> None:
    await _owner_sql(sessions, "UPDATE channel_partner SET credit_limit = CAST(:l AS numeric) WHERE id = CAST(:p AS uuid)",
                     {"l": limit, "p": shop.partner})


async def _draft(client: httpx.AsyncClient, shop: Shop) -> dict[str, Any]:
    fo = await endpoints._as(client, shop, "field_officer")
    return dict(await endpoints._create(client, fo, endpoints._direct(shop, partner_id=shop.partner)))


async def _submit(client: httpx.AsyncClient, shop: Shop, order_id: str) -> httpx.Response:
    fo = await endpoints._as(client, shop, "field_officer")
    return await client.post(f"{V1}/orders/{order_id}/submit", json={}, headers={**fo, **_key()})


async def test_block_refuses_without_figures_and_warn_flags_for_approvers_only(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:  # noqa: F811
    await _limit(sessions, shop, "1.00")
    order = await _draft(client, shop)
    await _mode(sessions, "block")
    r = await _submit(client, shop, order["id"])
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "credit_limit_exceeded" and r.json()["error"]["message"] == REFUSED
    admin = await endpoints._as(client, shop, "admin_sales")
    got = (await client.get(f"{V1}/orders/{order['id']}", headers=admin)).json()["data"]
    assert got["status"] == "draft" and got["order_no"] is None, "the refusal rolled the whole submit back"

    await _mode(sessions, "warn")
    r = await _submit(client, shop, order["id"])       # a new key, as the handover says
    assert r.status_code == 200, r.text
    got = (await client.get(f"{V1}/orders/{order['id']}", headers=admin)).json()["data"]
    assert got["over_credit_limit"] is True
    fo = await endpoints._as(client, shop, "field_officer")
    assert (await client.get(f"{V1}/orders/{order['id']}", headers=fo)).json()["data"]["over_credit_limit"] is None, \
        "a field officer may not read credit standing (GAP-244)"
    listed = (await client.get(f"{V1}/orders", headers=admin, params={"q": got["order_no"]})).json()["data"]
    assert [x["over_credit_limit"] for x in listed if x["id"] == order["id"]] == [True]
    step = got["approval"]["steps"][0]
    approver = await endpoints._as(client, shop, step["role"])
    queue = (await client.get(f"{V1}/approvals/pending", headers=approver)).json()["data"]
    assert [q["document"]["over_credit_limit"] for q in queue if q["document"]["id"] == order["id"]] == [True]

    r = await endpoints._decide(client, approver, step["id"], "reject", "Over credit")
    assert r.status_code == 200 and r.json()["data"]["status"] == "draft", r.text
    assert (await client.get(f"{V1}/orders/{order['id']}", headers=admin)).json()["data"]["over_credit_limit"] is None, \
        "back to draft clears the flag, so the resubmit is checked again"


async def test_off_and_no_limit_leave_the_order_unchecked(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:  # noqa: F811
    admin = await endpoints._as(client, shop, "admin_sales")
    await _limit(sessions, shop, "1.00")
    await _mode(sessions, "off")
    a = await _draft(client, shop)
    assert (await _submit(client, shop, a["id"])).status_code == 200
    await _mode(sessions, "block")
    await _limit(sessions, shop, None)                 # no limit: never checked (GAP-240)
    b = await _draft(client, shop)
    assert (await _submit(client, shop, b["id"])).status_code == 200
    for o in (a, b):
        assert (await client.get(f"{V1}/orders/{o['id']}", headers=admin)).json()["data"]["over_credit_limit"] is None


async def test_a_discount_applied_by_the_same_submit_counts(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None,  # noqa: F811
        made: list[str]) -> None:  # noqa: F811
    """Plan review edge 5: the check runs after the status UPDATE, so the benefit
    the schemes trigger applies is already counted."""
    order = await _draft(client, shop)
    total = Decimal(order["totals"]["total"])
    await schemes_t._scheme(client, shop, made, benefit={"kind": "pct", "value": "50"})
    await _limit(sessions, shop, str((total * Decimal("0.75")).quantize(Decimal("0.01"))))
    await _mode(sessions, "block")
    r = await _submit(client, shop, order["id"])
    assert r.status_code == 200, f"half the total is owed, under three quarters: {r.text}"
    admin = await endpoints._as(client, shop, "admin_sales")
    assert (await client.get(f"{V1}/orders/{order['id']}", headers=admin)).json()["data"]["over_credit_limit"] is False


async def test_the_credit_endpoint_is_for_accounts_and_dealer_managers(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:  # noqa: F811
    await _limit(sessions, shop, "100000.00")
    await _mode(sessions, "warn")
    order = await _draft(client, shop)
    assert (await _submit(client, shop, order["id"])).status_code == 200
    total = Decimal(order["totals"]["total"])
    accounts = await endpoints._as(client, shop, "account_manager")
    r = await client.get(f"{V1}/partners/{shop.partner}/credit", headers=accounts)
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert Decimal(got["exposure"]) >= total and got["credit_limit"] == "100000.00"
    assert Decimal(got["available"]) == Decimal(got["credit_limit"]) - Decimal(got["exposure"])
    assert got["check"] == "warn"
    admin = await endpoints._as(client, shop, "admin_sales")
    assert (await client.get(f"{V1}/partners/{shop.partner}/credit", headers=admin)).status_code == 200
    fo = await endpoints._as(client, shop, "field_officer")
    r = await client.get(f"{V1}/partners/{shop.partner}/credit", headers=fo)
    assert r.status_code == 403 and r.json()["error"]["code"] == "credit_not_permitted", r.text


@pytest.mark.concurrency
async def test_two_submits_for_one_dealer_cannot_both_fit(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:  # noqa: F811
    """Each order fits alone, the two together do not. The dealer row is locked,
    so the second submit waits and then counts the first. Raced as resubmits: a
    first submit queues on the order-number counter before it reaches the dealer,
    while a rejected order keeps its number and skips the counter, so only the
    dealer lock can serialise these two."""
    a, b = await _draft(client, shop), await _draft(client, shop)
    total = Decimal(a["totals"]["total"])
    await _mode(sessions, "off")
    for o in (a, b):
        r = await _submit(client, shop, o["id"])
        assert r.status_code == 200, r.text
        step = r.json()["data"]["approval"]["steps"][0]
        r = await endpoints._decide(client, await endpoints._as(client, shop, step["role"]), step["id"], "reject", "Again")
        assert r.status_code == 200 and r.json()["data"]["order_no"], r.text
    await _limit(sessions, shop, str(total * Decimal("1.5")))
    await _mode(sessions, "block")
    me = shop.ids["field_officer"]
    got, waited = await conc._race(sessions, (me, conc._submit(shop, a["id"])), (me, conc._submit(shop, b["id"])),
                                   on="channel_partner")
    assert waited, "the second submit did not wait on the dealer: the race was not a race"
    assert sorted(conc._outcome(g) for g in got) == ["credit_limit_exceeded", "ok"], got
