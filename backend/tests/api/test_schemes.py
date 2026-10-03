"""FS-031: schemes on real orders, end to end, against hand-worked figures.

Every benefit is written by migration 033's status trigger, so these tests drive
orders through the API (submit, approve, dispatch, void, cancel) and read what the
trigger stored. The negative cases are the point: a dealer never reads a scheme or
a credit meant for someone else, nobody writes a benefit by hand, and one credit is
never spent twice.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.session import enter_role
from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key
from worker.jobs.outbox import enter_as_principal

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]

pytestmark = pytest.mark.db


@pytest_asyncio.fixture
async def made(shop: Shop, sessions: Sessions) -> AsyncIterator[list[str]]:
    """The schemes a test created; removed, with everything they gave, before the
    shop's own teardown deletes the orders they point at."""
    ids: list[str] = []
    yield ids
    if not ids:
        return
    c = sessions()
    for stmt in (
        "DELETE FROM scheme_benefit WHERE scheme_id = ANY(CAST(:ids AS uuid[]))",
        "DELETE FROM reward_ledger WHERE scheme_id = ANY(CAST(:ids AS uuid[])) AND reverses_id IS NOT NULL",
        "DELETE FROM reward_ledger WHERE scheme_id = ANY(CAST(:ids AS uuid[]))",
        "DELETE FROM scheme_entitlement WHERE scheme_id = ANY(CAST(:ids AS uuid[]))",
        "DELETE FROM activity_event WHERE entity_type = 'scheme' AND entity_id = ANY(CAST(:ids AS uuid[]))",
        "DELETE FROM activity_event WHERE partner_id = CAST(:p AS uuid) AND (kind LIKE 'partner.entitlement_%' OR kind LIKE 'partner.points_%')",
        "DELETE FROM scheme_target WHERE scheme_id = ANY(CAST(:ids AS uuid[]))",
        "DELETE FROM scheme WHERE id = ANY(CAST(:ids AS uuid[]))",
    ):
        await c.execute(text(stmt), {"ids": ids, "p": shop.partner})
    await c.commit()
    await c.close()


def _paise(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def _scheme(client: httpx.AsyncClient, shop: Shop, made: list[str], **body: Any) -> dict[str, Any]:
    h = await endpoints._as(client, shop, "admin_sales")
    tag = uuid.uuid4().hex[:8]
    payload: dict[str, Any] = {
        "code": f"T-{tag}", "name": f"Test scheme {tag}", "scheme_type": "order_discount",
        "benefit": {"kind": "pct", "value": "5"}, "valid_from": "2020-01-01",
        # every test scheme is fenced to the shop's district, so no other test's order sees it
        "targets": [{"type": "territory", "id": shop.district}]}
    payload.update(body)
    r = await client.post(f"{V1}/schemes", json=payload, headers={**h, **_key()})
    assert r.status_code == 201, r.text
    made.append(r.json()["data"]["id"])
    return dict(r.json()["data"])


def _with_partner(shop: Shop, qty: str = "10") -> dict[str, object]:
    return endpoints._direct(shop, qty=qty, partner_id=shop.partner)


async def _order(client: httpx.AsyncClient, shop: Shop, body: dict[str, object]) -> dict[str, Any]:
    ho = await endpoints._as(client, shop, "field_officer")
    return dict(await endpoints._create(client, ho, body))


async def _submit(client: httpx.AsyncClient, shop: Shop, order_id: str) -> dict[str, Any]:
    ho = await endpoints._as(client, shop, "field_officer")
    return dict(await endpoints._submit(client, ho, order_id))


async def _get(client: httpx.AsyncClient, shop: Shop, order_id: str) -> dict[str, Any]:
    h = await endpoints._as(client, shop, "admin_sales")
    r = await client.get(f"{V1}/orders/{order_id}", headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json()["data"])


async def _dispatch_all(client: httpx.AsyncClient, shop: Shop, order: dict[str, Any],
                        at: dt.datetime | None = None) -> str:
    hd = await endpoints._as(client, shop, "dispatch_manager")
    line = order["lines"][0]
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()}, json={
        "dc_no": "DC-S", "dispatched_at": (at or dt.datetime.now(dt.UTC)).isoformat(),
        "lines": [{"order_line_id": line["id"], "qty": line["qty"]}]})
    assert r.status_code == 201, r.text
    return str(r.json()["data"]["id"])


async def _void(client: httpx.AsyncClient, shop: Shop, dispatch_id: str) -> None:
    hd = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.post(f"{V1}/dispatches/{dispatch_id}/void", json={"remark": "Wrong DC"},
                          headers={**hd, **_key()})
    assert r.status_code == 200, r.text


async def _entitlements(client: httpx.AsyncClient, shop: Shop, scheme_id: str) -> list[dict[str, Any]]:
    h = await endpoints._as(client, shop, "admin_sales")
    r = await client.get(f"{V1}/scheme-entitlements", headers=h, params={"partner_id": shop.partner})
    assert r.status_code == 200, r.text
    return [e for e in r.json()["data"] if e["scheme"]["id"] == scheme_id]


# ── the master ───────────────────────────────────────────────────────────────

async def test_the_master_refuses_wrong_combinations_and_who_may_write(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    h = await endpoints._as(client, shop, "admin_sales")
    base = {"code": f"BAD-{uuid.uuid4().hex[:6]}", "name": "x", "valid_from": "2026-10-01"}
    cases = [
        ({"scheme_type": "order_points", "benefit": {"kind": "pct", "value": "5"}}, "benefit.kind"),
        ({"scheme_type": "order_discount", "benefit": {"kind": "pct", "value": "120"}}, "benefit.value"),
        ({"scheme_type": "period", "period": "month", "benefit": {"kind": "flat", "value": "100"}}, "valid_to"),
        ({"scheme_type": "order_discount", "period": "month", "benefit": {"kind": "flat", "value": "1"}}, "period"),
        ({"scheme_type": "order_discount", "benefit": {"kind": "flat", "value": "1"},
          "targets": [{"type": "partner_type", "id": "farmer"}]}, "targets[0].id"),
        ({"scheme_type": "order_discount", "benefit": {"kind": "flat", "value": "1"},
          "targets": [{"type": "territory", "id": str(uuid.uuid4())}]}, "targets[0].id"),
    ]
    for body, field in cases:
        r = await client.post(f"{V1}/schemes", json={**base, **body}, headers={**h, **_key()})
        assert r.status_code == 422, (field, r.text)
        assert field in (r.json()["error"].get("fields") or {}), (field, r.text)

    s = await _scheme(client, shop, made)
    r = await client.post(f"{V1}/schemes", headers={**h, **_key()}, json={
        "code": s["code"], "name": "again", "scheme_type": "order_discount",
        "benefit": {"kind": "flat", "value": "1"}, "valid_from": "2026-10-01"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "code_taken"

    fo = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/schemes", headers={**fo, **_key()}, json={
        "code": "FO-1", "name": "x", "scheme_type": "order_discount",
        "benefit": {"kind": "flat", "value": "1"}, "valid_from": "2026-10-01"})
    assert r.status_code == 403
    assert (await client.get(f"{V1}/schemes/{s['id']}", headers=fo)).status_code == 200, \
        "every staff role reads schemes (RBAC 6.1)"

    r = await client.patch(f"{V1}/schemes/{s['id']}", json={"name": "Renamed", "stackable": True},
                           headers={**h, **_key()})
    assert r.status_code == 200 and r.json()["data"]["name"] == "Renamed"
    assert r.json()["data"]["used"] is False


# ── type 1 ───────────────────────────────────────────────────────────────────

async def test_an_order_discount_is_previewed_applied_at_submit_and_reversed_on_return(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    first = await _scheme(client, shop, made, priority=10, benefit={"kind": "pct", "value": "5"})
    # lower priority and stackable, but the first is not stackable: the chain ends (rule 6)
    await _scheme(client, shop, made, priority=20, stackable=True, benefit={"kind": "flat", "value": "100"})
    draft = await _order(client, shop, endpoints._direct(shop))
    taxable, total = Decimal(draft["totals"]["taxable"]), Decimal(draft["totals"]["total"])
    expected = _paise(taxable * 5 / 100)

    h = await endpoints._as(client, shop, "field_officer")
    pv = (await client.get(f"{V1}/orders/{draft['id']}/schemes", headers=h)).json()["data"]
    assert [(d["scheme"]["id"], d["amount"]) for d in pv["discounts"]] == [(first["id"], str(expected))]
    assert pv["payable"] == str(total - expected)

    order = await _submit(client, shop, draft["id"])
    got = await _get(client, shop, order["id"])
    assert [(b["kind"], b["scheme"]["id"], b["amount"], b["status"]) for b in got["benefits"]] == [
        ("discount", first["id"], str(expected), "applied")], "the preview is what submit stores"
    assert got["payable"] == str(total - expected)
    assert got["totals"]["total"] == str(total), "the invoice never changes (ADR-050)"
    r = await client.get(f"{V1}/orders/{order['id']}/schemes", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "order_not_draft"

    # returned by the first approver: the benefit goes; resubmit applies it afresh
    step = order["approval"]["steps"][0]
    r = await endpoints._decide(client, await endpoints._as(client, shop, step["role"]), step["id"],
                                decision="reject", remark="Fix the address")
    assert r.status_code == 200, r.text
    got = await _get(client, shop, order["id"])
    assert got["status"] == "draft"
    assert [b["status"] for b in got["benefits"]] == ["reversed"]
    assert got["payable"] == str(total)
    await _submit(client, shop, order["id"])
    got = await _get(client, shop, order["id"])
    assert sorted(b["status"] for b in got["benefits"]) == ["applied", "reversed"]

    r = await client.post(f"{V1}/orders/{order['id']}/cancel", json={"remark": "x"},
                          headers={**h, **_key()})
    assert r.status_code == 200, r.text
    got = await _get(client, shop, order["id"])
    assert all(b["status"] == "reversed" for b in got["benefits"]) and got["payable"] == str(total)

    # it has been used: only its end date and active flag may change now
    ha = await endpoints._as(client, shop, "admin_sales")
    r = await client.patch(f"{V1}/schemes/{first['id']}", json={"name": "No"}, headers={**ha, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "scheme_in_use"
    r = await client.patch(f"{V1}/schemes/{first['id']}", json={"is_active": False}, headers={**ha, **_key()})
    assert r.status_code == 200 and r.json()["data"]["is_active"] is False


async def test_stackable_discounts_combine_and_a_later_non_stackable_one_is_skipped(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    a = await _scheme(client, shop, made, priority=10, stackable=True, benefit={"kind": "pct", "value": "2"})
    b = await _scheme(client, shop, made, priority=20, stackable=True, benefit={"kind": "flat", "value": "50"})
    await _scheme(client, shop, made, priority=30, benefit={"kind": "pct", "value": "10"})
    # out of range: the condition's minimum is far above this order
    await _scheme(client, shop, made, priority=5, stackable=True, benefit={"kind": "flat", "value": "999"},
                  condition={"metric": "order_value", "min": "100000000"})
    order = await _submit(client, shop, (await _order(client, shop, endpoints._direct(shop)))["id"])
    got = await _get(client, shop, order["id"])
    taxable = Decimal(got["totals"]["taxable"])
    assert [(x["scheme"]["id"], x["amount"]) for x in got["benefits"]] == [
        (a["id"], str(_paise(taxable * 2 / 100))), (b["id"], "50.00")]


# ── types 2 and 3, the trigger's delivery arm ────────────────────────────────

async def test_a_next_order_credit_is_earned_on_delivery_used_once_and_reversed_by_a_void(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    s = await _scheme(client, shop, made, scheme_type="next_order",
                      benefit={"kind": "flat", "value": "200", "entitlement_days": 30},
                      targets=[{"type": "territory", "id": shop.district},
                               {"type": "partner_type", "id": "dealer"}])
    first = await endpoints._approve_all(client, shop, await _submit(
        client, shop, (await _order(client, shop, _with_partner(shop)))["id"]))
    assert await _entitlements(client, shop, s["id"]) == [], "nothing before delivery"
    sent = await _dispatch_all(client, shop, first)
    [ent] = await _entitlements(client, shop, s["id"])
    assert (ent["status"], ent["kind"], ent["value"], ent["source_order"]["id"]) == (
        "available", "flat", "200", first["id"])

    # the next order uses it at submit; cancelling that order gives it back
    second = await _submit(client, shop, (await _order(client, shop, _with_partner(shop)))["id"])
    got = await _get(client, shop, second["id"])
    used = [b for b in got["benefits"] if b["kind"] == "entitlement_used"]
    assert [(b["amount"], b["status"]) for b in used] == [("200.00", "applied")]
    assert Decimal(got["payable"]) == Decimal(got["totals"]["total"]) - 200
    [ent] = await _entitlements(client, shop, s["id"])
    assert ent["status"] == "consumed" and ent["consumed_order"]["id"] == second["id"]
    h = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/orders/{second['id']}/cancel", json={"remark": "x"}, headers={**h, **_key()})
    assert r.status_code == 200, r.text
    [ent] = await _entitlements(client, shop, s["id"])
    assert ent["status"] == "available" and ent["consumed_order"] is None

    # a void takes the first order out of delivered: the unused credit is reversed;
    # dispatching again earns a fresh one (plan review B1)
    await _void(client, shop, sent)
    [ent] = await _entitlements(client, shop, s["id"])
    assert ent["status"] == "reversed"
    first = await _get(client, shop, first["id"])
    await _dispatch_all(client, shop, first)
    ents = await _entitlements(client, shop, s["id"])
    assert sorted(e["status"] for e in ents) == ["available", "reversed"]


async def test_points_are_earned_on_delivery_and_reversed_by_a_void(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    s = await _scheme(client, shop, made, scheme_type="order_points",
                      benefit={"kind": "points", "value": "150"})
    order = await endpoints._approve_all(client, shop, await _submit(
        client, shop, (await _order(client, shop, _with_partner(shop)))["id"]))
    sent = await _dispatch_all(client, shop, order)

    async def ledger() -> list[tuple[str, int]]:
        c = sessions()
        try:
            rows = (await c.execute(text(
                "SELECT kind, points FROM reward_ledger WHERE scheme_id = CAST(:s AS uuid) "
                "ORDER BY created_at, points DESC"), {"s": s["id"]})).all()
            return [(r.kind, r.points) for r in rows]
        finally:
            await c.close()

    assert await ledger() == [("earned", 150)]
    await _void(client, shop, sent)
    assert await ledger() == [("earned", 150), ("reversed", -150)]


async def test_an_order_without_a_partner_earns_nothing_and_a_partner_order_counts_only_targets(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    s = await _scheme(client, shop, made, scheme_type="next_order",
                      benefit={"kind": "pct", "value": "3", "entitlement_days": 10},
                      targets=[{"type": "territory", "id": shop.district},
                               {"type": "partner_type", "id": "distributor"}])
    order = await endpoints._approve_all(client, shop, await _submit(
        client, shop, (await _order(client, shop, _with_partner(shop)))["id"]))
    await _dispatch_all(client, shop, order)
    assert await _entitlements(client, shop, s["id"]) == [], "the dealer is not a distributor"
    direct = await endpoints._approve_all(client, shop, await _submit(
        client, shop, (await _order(client, shop, endpoints._direct(shop)))["id"]))
    await _dispatch_all(client, shop, direct)
    assert await _entitlements(client, shop, s["id"]) == []


# ── one credit, two orders at once ───────────────────────────────────────────

async def test_two_orders_submitted_at_once_spend_one_credit_once(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    """The guarded UPDATE (status = 'available', then the row count) is what makes this
    hold; the FOR UPDATE orders the work. This test proves the outcome, not the lock
    (code review F-4)."""
    s = await _scheme(client, shop, made, scheme_type="next_order",
                      benefit={"kind": "flat", "value": "200", "entitlement_days": 30})
    first = await endpoints._approve_all(client, shop, await _submit(
        client, shop, (await _order(client, shop, _with_partner(shop)))["id"]))
    await _dispatch_all(client, shop, first)
    a = await _order(client, shop, _with_partner(shop))
    b = await _order(client, shop, _with_partner(shop))
    ho = await endpoints._as(client, shop, "field_officer")
    ra, rb = await asyncio.gather(
        client.post(f"{V1}/orders/{a['id']}/submit", json={}, headers={**ho, **_key()}),
        client.post(f"{V1}/orders/{b['id']}/submit", json={}, headers={**ho, **_key()}))
    assert ra.status_code == 200 and rb.status_code == 200, (ra.text, rb.text)
    used = []
    for o in (a, b):
        got = await _get(client, shop, o["id"])
        used += [x for x in got["benefits"] if x["kind"] == "entitlement_used" and x["status"] == "applied"]
    assert len(used) == 1, used
    [ent] = await _entitlements(client, shop, s["id"])
    assert ent["status"] == "consumed"


# ── type 4 ───────────────────────────────────────────────────────────────────

async def test_a_period_scheme_credits_last_months_delivered_total_once(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    today = today_ist()
    last_month_start = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    end = (today.replace(day=1) + dt.timedelta(days=40)).replace(day=1) - dt.timedelta(days=1)
    s = await _scheme(client, shop, made, scheme_type="period", period="month",
                      valid_from=last_month_start.isoformat(), valid_to=end.isoformat(),
                      condition={"metric": "order_value", "min": "1"},
                      benefit={"kind": "pct", "value": "4", "entitlement_days": 60})
    order = await endpoints._approve_all(client, shop, await _submit(
        client, shop, (await _order(client, shop, _with_partner(shop)))["id"]))
    when = dt.datetime.combine(last_month_start + dt.timedelta(days=14), dt.time(6, 0), dt.UTC)
    await _dispatch_all(client, shop, order, at=when)
    taxable = Decimal((await _get(client, shop, order["id"]))["totals"]["taxable"])

    async def evaluate() -> int:
        c = sessions()
        try:
            await enter_as_principal(c, get_settings())
            n = int((await c.execute(text("SELECT scheme_period_evaluate(:d)"), {"d": today})).scalar_one())
            await c.commit()
            return n
        finally:
            await c.close()

    assert await evaluate() >= 1
    [ent] = await _entitlements(client, shop, s["id"])
    assert ent["period_start"] == last_month_start.isoformat()
    assert (ent["kind"], Decimal(ent["value"])) == ("flat", _paise(taxable * 4 / 100))
    await evaluate()
    assert len(await _entitlements(client, shop, s["id"])) == 1, "the nightly run is idempotent"

    ha = await endpoints._as(client, shop, "admin_sales")
    r = await client.get(f"{V1}/schemes/{s['id']}/standing", headers=ha, params={"partner_id": shop.partner})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["period_start"] == today.replace(day=1).isoformat()
    first = await _scheme(client, shop, made)
    r = await client.get(f"{V1}/schemes/{first['id']}/standing", headers=ha, params={"partner_id": shop.partner})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_a_period_scheme"


async def test_only_the_worker_runs_the_period_evaluation(
        shop: Shop, sessions: Sessions) -> None:
    c = sessions()
    try:
        await c.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                        {"u": shop.ids["admin_sales"]})
        await enter_role(c, "app_role")
        with pytest.raises(DBAPIError):
            await c.execute(text("SELECT scheme_period_evaluate(CURRENT_DATE)"))
    finally:
        await c.rollback()
        await c.close()


# ── RLS: the negatives ───────────────────────────────────────────────────────

async def _as_db(sessions: Sessions, user_id: str) -> AsyncSession:
    s = sessions()
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})
    await enter_role(s, "app_role")
    return s


async def test_a_dealer_reads_only_the_schemes_aimed_at_it_and_never_their_partner_targets(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    mine = await _scheme(client, shop, made, targets=[{"type": "partner_type", "id": "dealer"},
                                                      {"type": "partner", "id": shop.partner}])
    other_state = await _scheme(client, shop, made, targets=[{"type": "partner_type", "id": "distributor"}])
    inactive = await _scheme(client, shop, made, targets=[{"type": "partner_type", "id": "dealer"}])
    ha = await endpoints._as(client, shop, "admin_sales")
    r = await client.patch(f"{V1}/schemes/{inactive['id']}", json={"is_active": False}, headers={**ha, **_key()})
    assert r.status_code == 200
    s = await _as_db(sessions, shop.ids["dealer"])
    try:
        seen = {str(x) for x in (await s.execute(text(
            "SELECT id FROM scheme WHERE id = ANY(CAST(:i AS uuid[]))"),
            {"i": [mine["id"], other_state["id"], inactive["id"]]})).scalars()}
        assert seen == {mine["id"]}
        types = set((await s.execute(text(
            "SELECT target_type::text FROM scheme_target WHERE scheme_id = CAST(:i AS uuid)"),
            {"i": mine["id"]})).scalars())
        assert types == {"partner_type"}, "partner targets stay hidden from partner users"
    finally:
        await s.rollback()
        await s.close()


async def test_nobody_writes_a_benefit_or_a_credit_by_hand(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    sch = await _scheme(client, shop, made)
    order = await _order(client, shop, endpoints._direct(shop))
    for role in ("field_officer", "admin_sales"):
        s = await _as_db(sessions, shop.ids[role])
        try:
            with pytest.raises(DBAPIError):
                await s.execute(text(
                    "INSERT INTO scheme_benefit (sales_order_id, scheme_id, kind, basis, amount) "
                    "VALUES (CAST(:o AS uuid), CAST(:s AS uuid), 'discount', 1, 1)"),
                    {"o": order["id"], "s": sch["id"]})
        finally:
            await s.rollback()
            await s.close()
        s = await _as_db(sessions, shop.ids[role])
        try:
            with pytest.raises(DBAPIError):
                await s.execute(text(
                    "INSERT INTO scheme_entitlement (scheme_id, partner_id, period_start, period_end, kind, value, basis, expires_at) "
                    "VALUES (CAST(:s AS uuid), CAST(:p AS uuid), CURRENT_DATE, CURRENT_DATE, 'flat', 1, 1, now())"),
                    {"s": sch["id"], "p": shop.partner})
        finally:
            await s.rollback()
            await s.close()


async def test_a_used_scheme_refuses_an_edit_even_from_the_table_owner(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    sch = await _scheme(client, shop, made)
    await _submit(client, shop, (await _order(client, shop, endpoints._direct(shop)))["id"])
    c = sessions()
    try:
        with pytest.raises(DBAPIError, match=r"SCHIU|has been used"):
            await c.execute(text("UPDATE scheme SET benefit_value = 50 WHERE id = CAST(:s AS uuid)"),
                            {"s": sch["id"]})
    finally:
        await c.rollback()
        await c.close()


async def test_an_order_closed_short_earns_on_what_was_sent(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    """Code review F-4: closed_short is a delivery; the basis is the dispatched part."""
    s = await _scheme(client, shop, made, scheme_type="next_order",
                      benefit={"kind": "pct", "value": "10", "entitlement_days": 30})
    order = await endpoints._approve_all(client, shop, await _submit(
        client, shop, (await _order(client, shop, _with_partner(shop, qty="10")))["id"]))
    line = order["lines"][0]
    hd = await endpoints._as(client, shop, "dispatch_manager")
    r = await client.post(f"{V1}/orders/{order['id']}/dispatches", headers={**hd, **_key()}, json={
        "dc_no": "DC-P", "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
        "lines": [{"order_line_id": line["id"], "qty": "4"}]})
    assert r.status_code == 201, r.text
    assert await _entitlements(client, shop, s["id"]) == [], "partly sent is not delivered"
    r = await client.post(f"{V1}/orders/{order['id']}/close-short", json={"remark": "Rest not needed"},
                          headers={**hd, **_key()})
    assert r.status_code == 200, r.text
    [ent] = await _entitlements(client, shop, s["id"])
    expected = _paise(Decimal(line["taxable"]) * 4 / 10)
    c = sessions()
    try:
        basis = (await c.execute(text("SELECT basis FROM scheme_entitlement WHERE id = CAST(:i AS uuid)"),
                                 {"i": ent["id"]})).scalar_one()
    finally:
        await c.close()
    assert Decimal(basis) == expected


async def test_cancelling_an_approved_order_reverses_its_discount(
        client: httpx.AsyncClient, shop: Shop, made: list[str]) -> None:
    """Code review F-4: approved -> cancelled takes the reversal arm."""
    await _scheme(client, shop, made, benefit={"kind": "flat", "value": "25"})
    order = await endpoints._approve_all(client, shop, await _submit(
        client, shop, (await _order(client, shop, endpoints._direct(shop)))["id"]))
    admin = await endpoints._as(client, shop, "admin_sales")
    r = await client.post(f"{V1}/orders/{order['id']}/cancel", json={"remark": "Customer withdrew"},
                          headers={**admin, **_key()})
    assert r.status_code == 200, r.text
    got = await _get(client, shop, order["id"])
    assert [b["status"] for b in got["benefits"]] == ["reversed"]
    assert got["payable"] == got["totals"]["total"]
