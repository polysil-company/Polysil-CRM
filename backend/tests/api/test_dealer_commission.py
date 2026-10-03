"""FS-033: stage 18, recorded by the co-ordinator, approved and paid by Accounts,
against a hand-worked figure; and the people who must not get in the way."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api import test_subsidy_applications as subsidy
from tests.api.conftest import V1, _key

shop = endpoints.shop
office = subsidy.office
fake_engine = subsidy.fake_engine
Sessions = Callable[[], AsyncSession]

pytestmark = pytest.mark.db


@pytest_asyncio.fixture
async def closed(client: httpx.AsyncClient, office: subsidy.Office, fake_engine: Any,
                 sessions: Sessions) -> AsyncIterator[dict[str, Any]]:
    """An application with full FP received and the shop's dealer on it, its stored
    calculation set to round figures."""
    fo = await subsidy._as(client, office, "field_officer")
    app = await subsidy._app(client, office, fo)
    s = sessions()
    await s.execute(text(
        "UPDATE subsidy_application SET calculation = jsonb_set(jsonb_set(jsonb_set(calculation, "
        "'{total,blocks,cost_excl_gst}', '\"254300.00\"'), '{total,blocks,installation}', '\"4500.00\"'), "
        "'{total,blocks,a_plus_b}', '\"231000.00\"') WHERE id = CAST(:a AS uuid)"), {"a": app["id"]})
    await s.commit()
    await s.close()
    yield app
    c = sessions()
    for stmt in ("DELETE FROM activity_event WHERE kind LIKE 'subsidy.commission_%' AND entity_id = CAST(:a AS uuid)",
                 "DELETE FROM dealer_commission WHERE application_id = CAST(:a AS uuid)",
                 "DELETE FROM commission_rate WHERE partner_id = CAST(:p AS uuid)"):
        await c.execute(text(stmt), {"a": app["id"], "p": office.shop.partner})
    await c.commit()
    await c.close()


async def _close(sessions: Sessions, app_id: str, partner: str | None) -> None:
    s = sessions()
    await s.execute(text(
        "UPDATE subsidy_application SET status = 'full_fp_received', full_fp_received_on = :d, "
        "partner_id = CAST(:p AS uuid) WHERE id = CAST(:a AS uuid)"),
        {"d": today_ist(), "p": partner, "a": app_id})
    await s.commit()
    await s.close()


def _url(app_id: str, tail: str = "") -> str:
    return f"{V1}/subsidy-applications/{app_id}/commission{tail}"


async def test_stage_18_is_recorded_approved_and_paid_to_the_paisa(
        client: httpx.AsyncClient, office: subsidy.Office, closed: dict[str, Any], sessions: Sessions) -> None:
    sc = await subsidy._as(client, office, "state_coordinator")
    r = await client.get(_url(closed["id"], "/preview"), headers=sc)
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_closed"
    await _close(sessions, closed["id"], None)
    r = await client.get(_url(closed["id"], "/preview"), headers=sc)
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_partner"
    await _close(sessions, closed["id"], office.shop.partner)
    pv = (await client.get(_url(closed["id"], "/preview"), headers=sc)).json()["data"]
    assert (pv["cost_excl_gst"], pv["installation"], pv["a_plus_b"]) == ("254300.00", "4500.00", "231000.00")
    assert (pv["commission_pct"], pv["tod_pct"]) == ("5", "2"), "the stand-in dealer rate"

    r = await client.post(_url(closed["id"]), headers={**sc, **_key()},
                          json={"gi_fitting": "12000", "pvc_hdpe_fitting": "8400"})
    assert r.status_code == 201, r.text
    c = r.json()["data"]
    # 254300 - 12000 - 8400 - 4500 = 229400; 5% = 11470.00; 2% = 4588.00
    assert (c["commission_base"], c["commission_amount"], c["tod_amount"], c["total"], c["status"]) == (
        "229400.00", "11470.00", "4588.00", "16058.00", "calculated")
    r = await client.post(_url(closed["id"]), headers={**sc, **_key()},
                          json={"gi_fitting": "300000"})
    assert r.status_code == 422, "fittings above the cost"

    acc = await subsidy._as(client, office, "account_manager")
    r = await client.post(f"{V1}/dealer-commissions/{c['id']}/pay", headers={**acc, **_key()},
                          json={"paid_on": today_ist().isoformat(), "payment_reference": "UTR1"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "status_changed"
    r = await client.post(f"{V1}/dealer-commissions/{c['id']}/approve", headers={**acc, **_key()}, json={})
    assert r.status_code == 200 and r.json()["data"]["status"] == "approved", r.text
    r = await client.post(_url(closed["id"]), headers={**sc, **_key()}, json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "commission_exists"

    sm = await subsidy._as(client, office, "state_manager")
    r = await client.post(f"{V1}/dealer-commissions/{c['id']}/pay", headers={**sm, **_key()},
                          json={"paid_on": today_ist().isoformat(), "payment_reference": "UTR1"})
    assert r.status_code == 403, "payments edit at org scope is not Accounts"
    future = (today_ist() + dt.timedelta(days=2)).isoformat()
    r = await client.post(f"{V1}/dealer-commissions/{c['id']}/pay", headers={**acc, **_key()},
                          json={"paid_on": future, "payment_reference": "UTR1"})
    assert r.status_code == 422
    r = await client.post(f"{V1}/dealer-commissions/{c['id']}/pay", headers={**acc, **_key()},
                          json={"paid_on": today_ist().isoformat(), "payment_reference": "NEFT UTR 99"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "paid"

    tl = (await client.get(f"{V1}/subsidy-applications/{closed['id']}/timeline", headers=sc))
    if tl.status_code == 200:
        kinds = {e["kind"] for e in tl.json()["data"]}
        assert {"subsidy.commission_recorded", "subsidy.commission_approved", "subsidy.commission_paid"} <= kinds

    r = await client.get(f"{V1}/dealer-commissions/export", headers=acc, params={"status": "paid"})
    assert r.status_code == 200 and r.content[:2] == b"PK"


async def test_nobody_approves_their_own_and_a_return_needs_a_remark(
        client: httpx.AsyncClient, office: subsidy.Office, closed: dict[str, Any], sessions: Sessions) -> None:
    await _close(sessions, closed["id"], office.shop.partner)
    admin = await subsidy._as(client, office, "admin_sales")
    r = await client.post(_url(closed["id"]), headers={**admin, **_key()}, json={})
    assert r.status_code == 201, r.text
    cid = r.json()["data"]["id"]
    assert r.json()["data"]["installation"] == "4500.00", "taken from the calculation"
    r = await client.post(f"{V1}/dealer-commissions/{cid}/approve", headers={**admin, **_key()}, json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "own_decision"
    acc = await subsidy._as(client, office, "account_manager")
    r = await client.post(f"{V1}/dealer-commissions/{cid}/return", headers={**acc, **_key()}, json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "remark_required"
    r = await client.post(f"{V1}/dealer-commissions/{cid}/return", headers={**acc, **_key()},
                          json={"remark": "GI is 11,200 per the bill"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "returned"
    sc = await subsidy._as(client, office, "state_coordinator")
    r = await client.post(_url(closed["id"]), headers={**sc, **_key()}, json={"gi_fitting": "11200"})
    assert r.status_code == 201 and r.json()["data"]["status"] == "calculated"
    assert r.json()["data"]["decision_remark"] is None, "recording again clears the old decision"
    r = await client.post(f"{V1}/dealer-commissions/{cid}/approve", headers={**admin, **_key()}, json={})
    assert r.status_code == 403, "the first recorder still may not approve"


async def test_a_rate_for_one_partner_outranks_the_type_rate_and_strangers_see_nothing(
        client: httpx.AsyncClient, office: subsidy.Office, closed: dict[str, Any], sessions: Sessions) -> None:
    await _close(sessions, closed["id"], office.shop.partner)
    admin = await subsidy._as(client, office, "admin_sales")
    r = await client.post(f"{V1}/commission-rates", headers={**admin, **_key()}, json={
        "partner_id": office.shop.partner, "commission_pct": "7.5", "tod_pct": "0",
        "effective_from": "2026-01-01"})
    assert r.status_code == 201, r.text
    sc = await subsidy._as(client, office, "state_coordinator")
    pv = (await client.get(_url(closed["id"], "/preview"), headers=sc)).json()["data"]
    assert (pv["commission_pct"], pv["tod_pct"]) == ("7.5", "0")
    r = await client.post(_url(closed["id"]), headers={**sc, **_key()}, json={})
    assert r.status_code == 201
    stranger = await subsidy._as(client, office, "stranger")
    assert (await client.get(_url(closed["id"]), headers=stranger)).status_code == 404
    listed = (await client.get(f"{V1}/dealer-commissions", headers=stranger)).json()["data"]
    assert all(x["application"]["id"] != closed["id"] for x in listed)
    cid = r.json()["data"]["id"]
    fo = await subsidy._as(client, office, "field_officer")
    r = await client.post(f"{V1}/dealer-commissions/{cid}/approve", headers={**fo, **_key()}, json={})
    assert r.status_code == 403
    # code review F-6: a dealer reads no commission, its own included (GAP-330)
    from tests.api.test_rewards import _as_db
    s = await _as_db(sessions, office.shop.ids["dealer"])
    try:
        n = (await s.execute(text("SELECT count(*) FROM dealer_commission WHERE id = CAST(:i AS uuid)"),
                             {"i": cid})).scalar_one()
        assert n == 0
    finally:
        await s.rollback()
        await s.close()
