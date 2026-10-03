"""FS-032: reward points earned by triggers, spent through one locked definer.

Orders move through the API; a dealer's own spending is driven through the definer
as the dealer's user, because a dealer signs in by WhatsApp code. The negatives: a
field officer never reads a dealer's points, a balance is never spent twice, and the
expiry takes only what is left of a lot.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.session import enter_role
from api.domain import rewards as domain
from tests.api import test_order_endpoints as endpoints
from tests.api import test_schemes as schemes
from tests.api.conftest import V1, _key
from worker.jobs.outbox import enter_as_principal

shop = endpoints.shop
Shop = endpoints.Shop
made = schemes.made
Sessions = Callable[[], AsyncSession]

pytestmark = pytest.mark.db


@pytest_asyncio.fixture
async def ruled(shop: Shop, sessions: Sessions) -> AsyncIterator[list[str]]:
    """Rules and gifts a test made, and every ledger row and redemption of the shop's
    partner and people, removed before the shop's teardown deletes the orders."""
    ids: list[str] = []
    yield ids
    c = sessions()
    people = list(shop.ids.values())
    for stmt in (
        "DELETE FROM scheme_benefit WHERE redemption_id IN (SELECT id FROM reward_redemption WHERE partner_id = CAST(:p AS uuid) OR user_id = ANY(CAST(:people AS uuid[])))",
        # a reversal must keep reverses_id (ck_reward_ledger_reverses), so reversals go first
        "DELETE FROM reward_ledger WHERE reverses_id IS NOT NULL AND (partner_id = CAST(:p AS uuid) OR user_id = ANY(CAST(:people AS uuid[])))",
        "UPDATE reward_ledger SET expires_id = NULL WHERE partner_id = CAST(:p AS uuid) OR user_id = ANY(CAST(:people AS uuid[]))",
        "DELETE FROM reward_ledger WHERE partner_id = CAST(:p AS uuid) OR user_id = ANY(CAST(:people AS uuid[]))",
        "DELETE FROM reward_redemption WHERE partner_id = CAST(:p AS uuid) OR user_id = ANY(CAST(:people AS uuid[]))",
        "DELETE FROM activity_event WHERE kind LIKE 'rewards.%' AND (partner_id = CAST(:p AS uuid) OR entity_id = ANY(CAST(:people AS uuid[])))",
        "DELETE FROM reward_rule WHERE id = ANY(CAST(:ids AS uuid[]))",
        "DELETE FROM gift WHERE id = ANY(CAST(:ids AS uuid[]))",
    ):
        await c.execute(text(stmt), {"p": shop.partner, "people": people, "ids": ids})
    await c.commit()
    await c.close()


async def _rule(client: httpx.AsyncClient, shop: Shop, ruled: list[str], **body: Any) -> dict[str, Any]:
    h = await endpoints._as(client, shop, "admin_sales")
    tag = uuid.uuid4().hex[:8]
    payload = {"code": f"R-{tag}", "name": f"Rule {tag}", "holder": "partner", "basis": "order_value",
               "points": 1, "per_amount": "100", "valid_from": "2020-01-01", **body}
    r = await client.post(f"{V1}/reward-rules", json=payload, headers={**h, **_key()})
    assert r.status_code == 201, r.text
    ruled.append(r.json()["data"]["id"])
    return dict(r.json()["data"])


async def _ledger(sessions: Sessions, *, partner: str | None = None, user: str | None = None) -> list[tuple[str, int]]:
    c = sessions()
    try:
        rows = (await c.execute(text(
            "SELECT kind, points FROM reward_ledger WHERE (CAST(:p AS uuid) IS NOT NULL AND partner_id = CAST(:p AS uuid)) "
            "OR (CAST(:u AS uuid) IS NOT NULL AND user_id = CAST(:u AS uuid)) ORDER BY created_at, id"),
            {"p": partner, "u": user})).all()
        return [(r.kind, r.points) for r in rows]
    finally:
        await c.close()


async def _as_db(sessions: Sessions, user_id: str) -> AsyncSession:
    s = sessions()
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})
    await enter_role(s, "app_role")
    return s


async def _spend(sessions: Sessions, shop: Shop, *, points: int = 0, order: str | None = None,
                 gift: str | None = None) -> str:
    s = await _as_db(sessions, shop.ids["dealer"])
    try:
        rid = (await s.execute(text(
            "SELECT reward_spend(:k, 'partner', CAST(:p AS uuid), :n, CAST(:o AS uuid), CAST(:g AS uuid))"),
            {"k": "order" if order else "gift", "p": shop.partner, "n": points or 1, "o": order, "g": gift})).scalar_one()
        await s.commit()
        return str(rid)
    finally:
        await s.close()


async def _give(sessions: Sessions, shop: Shop, points: int) -> None:
    """Points for the dealer by an adjustment, as the admin would."""
    s = await _as_db(sessions, shop.ids["admin_sales"])
    try:
        await s.execute(text("SELECT reward_adjust('partner', CAST(:p AS uuid), :n, 'test')"),
                        {"p": shop.partner, "n": points})
        await s.commit()
    finally:
        await s.close()


# ── the masters ──────────────────────────────────────────────────────────────

async def test_rules_refuse_wrong_shapes_and_only_admins_write_them(
        client: httpx.AsyncClient, shop: Shop, ruled: list[str]) -> None:
    h = await endpoints._as(client, shop, "admin_sales")
    for body, field in (({"basis": "order_value", "per_amount": None}, "per_amount"),
                        ({"basis": "lead_won", "holder": "partner", "per_amount": None}, "holder"),
                        ({"basis": "lead_won", "holder": "staff", "per_amount": "100"}, "per_amount")):
        r = await client.post(f"{V1}/reward-rules", headers={**h, **_key()}, json={
            "code": f"X-{uuid.uuid4().hex[:6]}", "name": "x", "holder": "partner", "points": 1,
            "valid_from": "2026-10-01", **body})
        assert r.status_code == 422 and field in r.json()["error"]["fields"], r.text
    fo = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/reward-rules", headers={**fo, **_key()}, json={
        "code": "FO-R", "name": "x", "holder": "partner", "basis": "order_value", "points": 1,
        "per_amount": "100", "valid_from": "2026-10-01"})
    assert r.status_code == 403
    r = await client.get(f"{V1}/reward-settings", headers=fo)
    assert r.status_code == 200 and Decimal(r.json()["data"]["point_value"]) > 0


# ── earning, by the triggers ─────────────────────────────────────────────────

async def test_a_delivered_order_earns_for_the_partner_and_the_staff_owner_and_a_void_takes_it_back(
        client: httpx.AsyncClient, shop: Shop, ruled: list[str], sessions: Sessions) -> None:
    await _rule(client, shop, ruled, holder="partner", points=2, per_amount="100")
    await _rule(client, shop, ruled, holder="staff", points=1, per_amount="500")
    order = await endpoints._approve_all(client, shop, await schemes._submit(
        client, shop, (await schemes._order(client, shop, schemes._with_partner(shop)))["id"]))
    sent = await schemes._dispatch_all(client, shop, order)
    taxable = Decimal((await schemes._get(client, shop, order["id"]))["totals"]["taxable"])
    partner_pts = domain.points_for(taxable, Decimal("100"), 2)
    staff_pts = domain.points_for(taxable, Decimal("500"), 1)
    assert partner_pts > 0 and staff_pts > 0
    assert await _ledger(sessions, partner=shop.partner) == [("earned", partner_pts)]
    assert await _ledger(sessions, user=shop.ids["field_officer"]) == [("earned", staff_pts)]
    await schemes._void(client, shop, sent)
    assert await _ledger(sessions, partner=shop.partner) == [("earned", partner_pts), ("reversed", -partner_pts)]
    assert await _ledger(sessions, user=shop.ids["field_officer"]) == [("earned", staff_pts), ("reversed", -staff_pts)]


async def test_a_won_lead_earns_its_staff_owner_whoever_wins_it(
        shop: Shop, ruled: list[str], sessions: Sessions, client: httpx.AsyncClient) -> None:
    await _rule(client, shop, ruled, holder="staff", basis="lead_won", points=5, per_amount=None)
    s = sessions()
    try:
        lead = str((await s.execute(text(
            "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, mobile, "
            "territory_id, owner_user_id, owner_org_unit_id, created_by, stage) VALUES (:no, 'commercial', "
            "(SELECT id FROM mis_system WHERE code = 'drip'), (SELECT id FROM lead_source WHERE code = 'employee'), "
            "'Reward Farmer', :m, CAST(:t AS uuid), CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:o AS uuid), 'negotiation') "
            "RETURNING id"),
            {"no": f"RW-{uuid.uuid4().hex[:8]}", "m": "+9197" + f"{uuid.uuid4().int % 10**8:08d}",
             "t": shop.district, "o": shop.ids["field_officer"], "ou": shop.office})).scalar_one())
        # the trigger fires on every writer of the stage; the table owner stands in for all three
        await s.execute(text("UPDATE lead SET stage = 'won' WHERE id = CAST(:l AS uuid)"), {"l": lead})
        await s.execute(text("UPDATE lead SET stage = 'won', updated_at = now() WHERE id = CAST(:l AS uuid)"), {"l": lead})
        await s.commit()
    finally:
        await s.close()
    assert await _ledger(sessions, user=shop.ids["field_officer"]) == [("earned", 5)], "once, however often it is written"


# ── spending ─────────────────────────────────────────────────────────────────

async def test_points_on_a_draft_come_off_the_payable_at_submit_and_come_back_on_cancel(
        client: httpx.AsyncClient, shop: Shop, ruled: list[str], sessions: Sessions) -> None:
    await _give(sessions, shop, 500)
    draft = await schemes._order(client, shop, schemes._with_partner(shop))
    total = Decimal(draft["totals"]["total"])
    cap = int(total * Decimal("0.10"))           # the stand-in limit is 10% at ₹1 a point
    with pytest.raises(DBAPIError, match=r"RWDMX|more than"):
        await _spend(sessions, shop, points=cap + 1, order=draft["id"])
    await _spend(sessions, shop, points=cap, order=draft["id"])
    assert await _ledger(sessions, partner=shop.partner) == [("adjusted", 500), ("redeemed", -cap)]
    with pytest.raises(DBAPIError, match=r"RWDEX|already"):
        await _spend(sessions, shop, points=1, order=draft["id"])

    await schemes._submit(client, shop, draft["id"])
    got = await schemes._get(client, shop, draft["id"])
    [b] = [x for x in got["benefits"] if x["kind"] == "reward_redemption"]
    assert (b["scheme"], b["amount"], b["status"]) == (None, f"{cap}.00", "applied")
    assert Decimal(got["payable"]) == total - cap

    ho = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/orders/{draft['id']}/cancel", json={"remark": "x"}, headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    rows = await _ledger(sessions, partner=shop.partner)
    assert rows[-1] == ("released", cap) and sum(p for _, p in rows) == 500


async def test_a_gift_holds_points_and_a_reject_returns_them_and_a_fulfil_keeps_them(
        client: httpx.AsyncClient, shop: Shop, ruled: list[str], sessions: Sessions) -> None:
    ha = await endpoints._as(client, shop, "admin_sales")
    r = await client.post(f"{V1}/gifts", json={"name": "Umbrella", "points_cost": 120}, headers={**ha, **_key()})
    assert r.status_code == 201, r.text
    gift = r.json()["data"]["id"]
    ruled.append(gift)
    with pytest.raises(DBAPIError, match=r"RWDIN|not enough"):
        await _spend(sessions, shop, gift=gift)
    await _give(sessions, shop, 300)
    first = await _spend(sessions, shop, gift=gift)
    second = await _spend(sessions, shop, gift=gift)
    r = await client.post(f"{V1}/rewards/gift-redemptions/{first}/reject", json={"remark": None},
                          headers={**ha, **_key()})
    assert r.status_code == 422 and r.json()["error"]["code"] == "remark_required"
    r = await client.post(f"{V1}/rewards/gift-redemptions/{first}/reject", json={"remark": "Out of stock"},
                          headers={**ha, **_key()})
    assert r.status_code == 200 and r.json()["data"]["status"] == "rejected"
    r = await client.post(f"{V1}/rewards/gift-redemptions/{second}/fulfil", json={}, headers={**ha, **_key()})
    assert r.status_code == 200 and r.json()["data"]["status"] == "fulfilled"
    r = await client.post(f"{V1}/rewards/gift-redemptions/{second}/reject", json={"remark": "late"},
                          headers={**ha, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "redemption_closed"
    assert sum(p for _, p in await _ledger(sessions, partner=shop.partner)) == 300 - 120


async def test_two_spends_at_once_never_take_the_balance_below_zero(
        shop: Shop, ruled: list[str], sessions: Sessions, client: httpx.AsyncClient) -> None:
    ha = await endpoints._as(client, shop, "admin_sales")
    gift = (await client.post(f"{V1}/gifts", json={"name": "Cap", "points_cost": 100},
                              headers={**ha, **_key()})).json()["data"]["id"]
    ruled.append(gift)
    await _give(sessions, shop, 150)
    outcomes = await asyncio.gather(_spend(sessions, shop, gift=gift), _spend(sessions, shop, gift=gift),
                                    return_exceptions=True)
    assert sum(isinstance(o, str) for o in outcomes) == 1, outcomes
    assert sum(p for _, p in await _ledger(sessions, partner=shop.partner)) == 50


# ── RLS, the negatives ───────────────────────────────────────────────────────

async def test_a_field_officer_reads_their_own_points_never_a_dealers(
        client: httpx.AsyncClient, shop: Shop, ruled: list[str], sessions: Sessions) -> None:
    await _give(sessions, shop, 70)
    fo = await endpoints._as(client, shop, "field_officer")
    r = await client.get(f"{V1}/rewards/balance", headers=fo, params={"partner_id": shop.partner})
    assert r.status_code == 200 and r.json()["data"]["balance"] == 0, "the rows are invisible to V:own"
    dm = await endpoints._as(client, shop, "district_manager")
    r = await client.get(f"{V1}/rewards/balance", headers=dm, params={"partner_id": shop.partner})
    assert r.status_code == 200 and r.json()["data"]["balance"] == 70
    s = await _as_db(sessions, shop.ids["field_officer"])
    try:
        with pytest.raises(DBAPIError):
            await s.execute(text("INSERT INTO reward_ledger (holder_type, user_id, points, kind, reason) "
                                 "VALUES ('user', CAST(:u AS uuid), 1000, 'adjusted', 'mine')"),
                            {"u": shop.ids["field_officer"]})
    finally:
        await s.rollback()
        await s.close()
    s = await _as_db(sessions, shop.ids["field_officer"])
    try:
        with pytest.raises(DBAPIError, match=r"42501|not your points|not permitted"):
            await s.execute(text("SELECT reward_spend('gift', 'partner', CAST(:p AS uuid), 1, NULL, NULL)"),
                            {"p": shop.partner})
    finally:
        await s.rollback()
        await s.close()


# ── expiry ───────────────────────────────────────────────────────────────────

async def test_expiry_takes_only_what_is_left_of_each_due_lot(
        shop: Shop, ruled: list[str], sessions: Sessions) -> None:
    s = sessions()
    try:
        for pts, days in ((100, -10), (50, -5), (40, 30)):
            await s.execute(text(
                "INSERT INTO reward_ledger (holder_type, partner_id, points, kind, reason, expires_at) "
                "VALUES ('partner', CAST(:p AS uuid), :n, 'earned', 'lot', now() + make_interval(days => :d))"),
                {"p": shop.partner, "n": pts, "d": days})
        await s.execute(text("INSERT INTO reward_ledger (holder_type, partner_id, points, kind, reason) "
                             "VALUES ('partner', CAST(:p AS uuid), -120, 'redeemed', 'spent')"), {"p": shop.partner})
        await s.commit()
        await enter_as_principal(s, get_settings())
        await s.execute(text("SELECT reward_points_expire()"))
        await s.execute(text("SELECT reward_points_expire()"))
        await s.commit()
    finally:
        await s.close()
    expected = domain.expiry([domain.Lot(100, True), domain.Lot(50, True), domain.Lot(40, False)], 120, 0)
    assert expected == [0, 30, 0]
    expired = [p for k, p in await _ledger(sessions, partner=shop.partner) if k == "expired"]
    assert expired == [-30], "the second run expires nothing more"


# ── code review findings, each with its test ─────────────────────────────────

async def _hold_on_draft(client: httpx.AsyncClient, shop: Shop, sessions: Sessions, qty: str = "10") -> tuple[dict[str, Any], int]:
    await _give(sessions, shop, 1000)
    draft = await schemes._order(client, shop, schemes._with_partner(shop, qty=qty))
    cap = int(Decimal(draft["totals"]["total"]) * Decimal("0.10"))
    await _spend(sessions, shop, points=cap, order=draft["id"])
    return draft, cap


async def test_cutting_the_lines_after_the_hold_still_keeps_points_within_the_limit(
        client: httpx.AsyncClient, shop: Shop, ruled: list[str], sessions: Sessions) -> None:
    """F-1: the limit is checked again at submit, on the order as it is then."""
    draft, _cap = await _hold_on_draft(client, shop, sessions, qty="10")
    ho = await endpoints._as(client, shop, "field_officer")
    r = await client.put(f"{V1}/orders/{draft['id']}/lines", headers={**ho, **_key()},
                         json={"lines": [{"product_id": shop.product, "qty": "2", "discount_pct": "10"}]})
    assert r.status_code == 200, r.text
    await schemes._submit(client, shop, draft["id"])
    got = await schemes._get(client, shop, draft["id"])
    total = Decimal(got["totals"]["total"])
    [b] = [x for x in got["benefits"] if x["kind"] == "reward_redemption"]
    used = int(total * Decimal("0.10"))
    assert Decimal(b["amount"]) == used, "whole points under the limit; a point is never spent for less (GAP-316)"
    assert sum(p for _, p in await _ledger(sessions, partner=shop.partner)) == 1000 - used, "the rest came back"


async def test_a_draft_moved_to_no_dealer_spends_none_of_the_dealers_points(
        client: httpx.AsyncClient, shop: Shop, ruled: list[str], sessions: Sessions) -> None:
    """F-1: the hold belongs to the dealer; a draft that is no longer its order gets nothing."""
    draft, _cap = await _hold_on_draft(client, shop, sessions)
    ho = await endpoints._as(client, shop, "field_officer")
    r = await client.patch(f"{V1}/orders/{draft['id']}", headers={**ho, **_key()}, json={"partner_id": None})
    assert r.status_code == 200, r.text
    await schemes._submit(client, shop, draft["id"])
    got = await schemes._get(client, shop, draft["id"])
    assert [b for b in got["benefits"] if b["kind"] == "reward_redemption"] == []
    assert sum(p for _, p in await _ledger(sessions, partner=shop.partner)) == 1000


async def test_returned_to_draft_and_resubmitted_the_points_apply_once(
        client: httpx.AsyncClient, shop: Shop, ruled: list[str], sessions: Sessions) -> None:
    draft, cap = await _hold_on_draft(client, shop, sessions)
    order = await schemes._submit(client, shop, draft["id"])
    step = order["approval"]["steps"][0]
    r = await endpoints._decide(client, await endpoints._as(client, shop, step["role"]), step["id"],
                                decision="reject", remark="Fix the address")
    assert r.status_code == 200, r.text
    got = await schemes._get(client, shop, draft["id"])
    assert [b["status"] for b in got["benefits"] if b["kind"] == "reward_redemption"] == ["reversed"]
    assert sum(p for _, p in await _ledger(sessions, partner=shop.partner)) == 1000 - cap, "still held"
    await schemes._submit(client, shop, draft["id"])
    got = await schemes._get(client, shop, draft["id"])
    assert sorted(b["status"] for b in got["benefits"] if b["kind"] == "reward_redemption") == ["applied", "reversed"]
    assert sum(p for _, p in await _ledger(sessions, partner=shop.partner)) == 1000 - cap


async def test_when_schemes_already_cover_the_order_every_point_comes_back(
        client: httpx.AsyncClient, shop: Shop, ruled: list[str], sessions: Sessions,
        made: list[str]) -> None:
    """The v_used = 0 path: nothing left to pay."""
    await schemes._scheme(client, shop, made, benefit={"kind": "flat", "value": "100000000"})
    draft, _cap = await _hold_on_draft(client, shop, sessions)
    await schemes._submit(client, shop, draft["id"])
    got = await schemes._get(client, shop, draft["id"])
    assert got["payable"] == "0.00"
    assert [b for b in got["benefits"] if b["kind"] == "reward_redemption"] == []
    assert sum(p for _, p in await _ledger(sessions, partner=shop.partner)) == 1000


async def test_a_reversal_after_the_points_expired_takes_nothing_twice(
        client: httpx.AsyncClient, shop: Shop, ruled: list[str], sessions: Sessions) -> None:
    """F-2, reproduced by the review: expired -5, earned 5, reversed -5 made the balance -5."""
    await _rule(client, shop, ruled, holder="staff", basis="lead_won", points=5, per_amount=None, expiry_days=1)
    s = sessions()
    try:
        lead = str((await s.execute(text(
            "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, mobile, "
            "territory_id, owner_user_id, owner_org_unit_id, created_by, stage) VALUES (:no, 'commercial', "
            "(SELECT id FROM mis_system WHERE code = 'drip'), (SELECT id FROM lead_source WHERE code = 'employee'), "
            "'Expiry Farmer', :m, CAST(:t AS uuid), CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:o AS uuid), 'negotiation') "
            "RETURNING id"),
            {"no": f"RX-{uuid.uuid4().hex[:8]}", "m": "+9197" + f"{uuid.uuid4().int % 10**8:08d}",
             "t": shop.district, "o": shop.ids["field_officer"], "ou": shop.office})).scalar_one())
        await s.execute(text("UPDATE lead SET stage = 'won' WHERE id = CAST(:l AS uuid)"), {"l": lead})
        await s.execute(text("UPDATE reward_ledger SET expires_at = now() - interval '1 hour' "
                             "WHERE lead_id = CAST(:l AS uuid)"), {"l": lead})
        await s.commit()
        await enter_as_principal(s, get_settings())
        await s.execute(text("SELECT reward_points_expire()"))
        await s.commit()
    finally:
        await s.close()
    s = sessions()
    try:
        await s.execute(text("UPDATE lead SET stage = 'negotiation' WHERE id = CAST(:l AS uuid)"), {"l": lead})
        await s.commit()
    finally:
        await s.close()
    rows = await _ledger(sessions, user=shop.ids["field_officer"])
    assert ("earned", 5) in rows and ("expired", -5) in rows
    assert sum(p for _, p in rows) == 0, rows
