"""FS-089: an industrial order climbs State Manager, Regional Manager and MD by value;
every other order keeps today's ladder. The shop's people all sit in one district
office, so each holder sees the order."""

# ruff: noqa: F811  (the fixture is imported from the module that defines it)

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import V1, _key
from tests.api.test_order_endpoints import Shop, _approve_all, _direct, _submit, shop  # noqa: F401
from tests.api.test_order_endpoints import _as as _shop_as
from tests.api.test_order_endpoints import _create as _create_order

pytestmark = pytest.mark.db

TAIL = ["account_manager", "dispatch_manager"]


def _roles(order: dict) -> list[str]:
    return [s["role"] for s in order["approval"]["steps"]]


async def test_a_small_industrial_order_goes_to_the_state_manager(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """No District Manager step (rule 1)."""
    ho = await _shop_as(client, shop, "field_officer")
    draft = await _create_order(client, ho, _direct(shop, order_type="industrial"))
    order = await _submit(client, ho, draft["id"])
    assert _roles(order) == ["state_manager", *TAIL]
    done = await _approve_all(client, shop, order)
    assert done["status"] == "approved"


async def test_a_large_industrial_order_climbs_to_the_md_who_decides_it(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """28,35,000 with GST is above the Regional Manager's 25,00,000."""
    ho = await _shop_as(client, shop, "field_officer")
    draft = await _create_order(client, ho, _direct(shop, qty="30000", order_type="industrial"))
    order = await _submit(client, ho, draft["id"])
    assert _roles(order) == ["state_manager", "regional_manager", "md_ceo", *TAIL]
    done = await _approve_all(client, shop, order)
    md = next(s for s in done["approval"]["steps"] if s["role"] == "md_ceo")
    # decided_role names a stand-in only; the MD decided the MD's own step
    assert (md["decision"], md["decided_role"]) == ("approve", None)
    assert done["status"] == "approved"


async def test_a_commercial_order_keeps_the_district_managers_ladder(
        client: httpx.AsyncClient, shop: Shop) -> None:
    ho = await _shop_as(client, shop, "field_officer")
    draft = await _create_order(client, ho, _direct(shop, qty="30000"))
    order = await _submit(client, ho, draft["id"])
    assert _roles(order) == ["district_manager", "state_manager", "regional_manager", *TAIL]


async def test_a_draft_moved_to_industrial_takes_the_industrial_ladder(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-8, rule 5."""
    ho = await _shop_as(client, shop, "field_officer")
    draft = await _create_order(client, ho, _direct(shop))
    r = await client.patch(f"{V1}/orders/{draft['id']}", json={"order_type": "industrial"},
                           headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    order = await _submit(client, ho, draft["id"])
    assert _roles(order) == ["state_manager", *TAIL]


async def test_no_md_who_can_take_the_step_refuses_the_submit(
        client: httpx.AsyncClient, shop: Shop, sessions: Callable[[], AsyncSession]) -> None:
    """Rule 7: nobody ranks above the MD, so a stuck MD step is refused at submit."""
    ho = await _shop_as(client, shop, "field_officer")
    draft = await _create_order(client, ho, _direct(shop, qty="30000", order_type="industrial"))
    s = sessions()
    # The shop's office is a root and md_ceo a line role, so approval_step_stalled
    # looks at the shop's MD alone. Only that account is switched off (code review F-1).
    md = shop.ids["md_ceo"]
    await s.execute(text("UPDATE app_user SET is_active = false WHERE id = CAST(:u AS uuid)"),
                    {"u": md})
    await s.commit()
    try:
        r = await client.post(f"{V1}/orders/{draft['id']}/submit", json={},
                              headers={**ho, **_key()})
        assert r.status_code == 422 and r.json()["error"]["code"] == "no_approver", r.text
    finally:
        await s.execute(text("UPDATE app_user SET is_active = true WHERE id = CAST(:u AS uuid)"),
                        {"u": md})
        await s.commit()
    # the refusal rolled the submit back: still a draft, and it submits once the MD is back
    r = await client.get(f"{V1}/orders/{draft['id']}", headers=ho)
    assert r.json()["data"]["status"] == "draft", r.text
    order = await _submit(client, ho, draft["id"])
    assert "md_ceo" in [st["role"] for st in order["approval"]["steps"]]


async def test_the_thresholds_take_the_industrial_ladder_and_cap_below_the_md(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """Rule 8 and plan review B-1."""
    ha = await _shop_as(client, shop, "admin_sales")
    put = f"{V1}/approvals/thresholds"
    r = await client.put(put, headers={**ha, **_key()}, json={
        "doc_type": "industrial_order", "role": "state_manager", "territory_id": shop.state,
        "max_amount": None})
    assert r.status_code == 422 and "max_amount" in r.json()["error"]["fields"], r.text
    r = await client.put(put, headers={**ha, **_key()}, json={
        "doc_type": "industrial_order", "role": "district_manager", "max_amount": "1000"})
    assert r.status_code == 422 and "role" in r.json()["error"]["fields"], r.text
    r = await client.put(put, headers={**ha, **_key()}, json={
        "doc_type": "sales_order", "role": "md_ceo", "max_amount": "1000"})
    assert r.status_code == 422 and "role" in r.json()["error"]["fields"], r.text
    r = await client.put(put, headers={**ha, **_key()}, json={
        "doc_type": "industrial_order", "role": "state_manager", "territory_id": shop.state,
        "max_amount": "200000"})
    assert r.status_code == 200, r.text
    rows = [x for x in r.json()["data"] if x["doc_type"] == "industrial_order"]
    assert {(x["role"], (x["territory"] or {}).get("id")) for x in rows} >= {
        ("state_manager", None), ("regional_manager", None), ("md_ceo", None),
        ("state_manager", shop.state)}


async def test_an_amended_industrial_order_climbs_the_industrial_ladder_again(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-9 under the default `always`: the amendment resubmits on its type's ladder."""
    from tests.api.test_settings_amend_reopen import _amend

    ho = await _shop_as(client, shop, "field_officer")
    draft = await _create_order(client, ho, _direct(shop, order_type="industrial"))
    approved = await _approve_all(client, shop, await _submit(client, ho, draft["id"]))
    assert approved["status"] == "approved"
    r = await _amend(client, ho, draft["id"])
    assert r.status_code == 200, r.text
    again = await _submit(client, ho, draft["id"])
    assert _roles(again) == ["state_manager", *TAIL]
