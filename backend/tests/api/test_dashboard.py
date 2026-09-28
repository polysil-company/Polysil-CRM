"""FS-017 over the API: GET /dashboard/overview against a known set of leads and
tasks in the order tests' shop, a fresh office per test."""

# ruff: noqa: E501  (SQL inline)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.tasks import IST
from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


def _at(days_ago: int, hour: int = 10, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(today_ist() - dt.timedelta(days=days_ago), dt.time(hour, minute), tzinfo=IST)


async def _leads(sessions: Sessions, shop: Shop, rows: list[tuple[dt.datetime, str, str | None]],
                 owner: str = "field_officer") -> list[str]:
    """(created_at, stage, value) leads owned by one of the shop's people."""
    s = sessions()
    ids = []
    tag = uuid.uuid4().hex[:8]
    for i, (at, stage, value) in enumerate(rows):
        ids.append(str((await s.execute(text(
            "INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
            "mobile, territory_id, owner_user_id, owner_org_unit_id, created_by, created_at, estimated_value, lost_reason_id) "
            "VALUES (:no, CAST(:st AS lead_stage), 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
            "(SELECT id FROM lead_source WHERE code = 'employee'), 'Dash Farmer', :mob, CAST(:t AS uuid), "
            "CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:o AS uuid), :at, :v, CASE WHEN :st = 'lost' THEN "
            "(SELECT id FROM won_lost_reason WHERE kind = 'lost' ORDER BY sort_order LIMIT 1) END) RETURNING id"),
            {"no": f"DASH-{tag}-{i}", "st": stage, "mob": "+9197" + f"{uuid.uuid4().int % 10**8:08d}",
             "t": shop.district, "o": shop.ids[owner], "ou": shop.office, "at": at,
             "v": Decimal(value) if value else None})).scalar_one()))
    await s.commit()
    await s.close()
    return ids


async def _overview(client: httpx.AsyncClient, h: dict[str, str], days: int = 7) -> dict:
    r = await client.get(f"{V1}/dashboard/overview", headers=h, params={"days": days})
    assert r.status_code == 200, r.text
    return dict(r.json()["data"])


async def test_the_figures_over_a_known_week(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """This week: 3 new (1 won), one of them at 00:30 IST on the first day, which a
    UTC date would put in the week before (code review F-1); the week before: 2
    new (1 won). A lead 20 days old counts in the pipeline only."""
    await _leads(sessions, shop, [
        (_at(0), "new", "1000"), (_at(2), "won", "5000"), (_at(6, 0, 30), "qualified", None),
        (_at(8), "won", "700"), (_at(13), "lost", "300"), (_at(20), "negotiation", "2500"),
    ])
    h = await endpoints._as(client, shop, "field_officer")
    o = await _overview(client, h, 7)
    assert o["period"] == {"start": (today_ist() - dt.timedelta(days=6)).isoformat(), "end": today_ist().isoformat()}
    k = o["kpis"]
    assert k["new_leads"]["value"] == "3" and k["new_leads"]["delta_percent"] == "50.0"
    assert k["new_leads"]["trend"] == ["1", "0", "0", "0", "1", "0", "1"], "the 00:30 IST lead is in its own IST day"
    assert k["conversion_rate"]["value"] == "33.3" and k["conversion_rate"]["delta_percent"] == "-33.3"
    assert k["conversion_rate"]["trend"][4] == "100.0" and k["conversion_rate"]["trend"][1] == "0.0"
    assert k["pipeline_value"] == {"value": "3500.00", "delta_percent": None, "trend": []}, "new + qualified + negotiation"
    stages = {p["stage"]: p for p in o["pipeline"]}
    assert "merged" not in stages and stages["won"] == {"stage": "won", "count": 2, "value": "5700.00"}
    assert stages["contacted"] == {"stage": "contacted", "count": 0, "value": "0.00"}
    employee = next(x for x in o["sources"] if x["source"] == "employee")
    assert employee["count"] == 3
    stats = (await client.get(f"{V1}/leads/stats", headers=h, params={
        "created_from": o["period"]["start"], "created_to": o["period"]["end"]})).json()
    stats = stats.get("data", stats)
    assert stats["total"] == 3, "the list reads the same IST dates, the last one inclusive"


async def test_overdue_and_the_next_follow_ups(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Review B-1: the card, the flags and /leads/stats count the same overdue tasks."""
    ids = await _leads(sessions, shop, [(_at(3), "new", None), (_at(3), "contacted", None)])
    fo, dm = shop.ids["field_officer"], shop.ids["district_manager"]
    s = sessions()
    for lead, due, status, who in ((ids[0], _at(2), "open", fo), (ids[1], _at(1), "open", fo),
                                   (ids[0], _at(0, 23), "open", fo), (ids[0], _at(1), "cancelled", fo),
                                   (ids[1], _at(400), "open", fo), (None, _at(1), "open", fo)):
        await s.execute(text(
            "INSERT INTO task (title, task_type, status, due_at, assigned_to, assigned_by, owner_org_unit_id, lead_id, "
            "cancel_reason) VALUES ('Call', 'followup', CAST(:st AS task_status), :due, CAST(:u AS uuid), "
            "CAST(:by AS uuid), CAST(:ou AS uuid), CAST(:l AS uuid), CASE WHEN :st = 'cancelled' THEN 'No' END)"),
            {"st": status, "due": due, "u": who, "by": dm, "ou": shop.office, "l": lead})
    await s.commit()
    await s.close()
    h = await endpoints._as(client, shop, "field_officer")
    o = await _overview(client, h)
    rows = o["follow_ups"]
    assert [r["overdue"] for r in rows] == [True, True, False], rows
    assert o["kpis"]["overdue_follow_ups"]["value"] == "2" == str(sum(r["overdue"] for r in rows))
    assert rows[0]["district"] and rows[0]["assigned_to"]["id"] == fo and rows[0]["farmer_name"] == "Dash Farmer"
    stats = (await client.get(f"{V1}/leads/stats", headers=h)).json()
    assert (stats.get("data", stats))["follow_ups_overdue"] == 2


async def test_a_role_without_leads_gets_zeros_not_403(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "dispatch_manager")
    o = await _overview(client, h, 30)
    assert o["kpis"]["new_leads"]["value"] == "0" and o["kpis"]["pipeline_value"]["value"] == "0.00"
    assert all(p["count"] == 0 for p in o["pipeline"])


async def test_a_deleted_lead_leaves_the_figures(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Review B-2: a caller who may read deleted leads still does not count them."""
    (lead,) = await _leads(sessions, shop, [(_at(1), "new", "4321")])
    h = await endpoints._as(client, shop, "admin_sales")
    before = Decimal((await _overview(client, h))["kpis"]["pipeline_value"]["value"])
    s = sessions()
    await s.execute(text("UPDATE lead SET deleted_at = now() WHERE id = CAST(:l AS uuid)"), {"l": lead})
    await s.commit()
    await s.close()
    after = Decimal((await _overview(client, h))["kpis"]["pipeline_value"]["value"])
    assert before - after == Decimal("4321.00")


@pytest.mark.parametrize("days", ["15", "0", "x"])
async def test_only_7_30_or_90_days(client: httpx.AsyncClient, shop: Shop, days: str) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    r = await client.get(f"{V1}/dashboard/overview", headers=h, params={"days": days})
    assert r.status_code == 422, r.text



# ── code review F-2 and F-3: scope and the deleter ───────────────────────────

async def _task(sessions: Sessions, shop: Shop, lead: str | None, due: dt.datetime, to: str,
                by: str = "district_manager") -> None:
    s = sessions()
    await s.execute(text(
        "INSERT INTO task (title, task_type, due_at, assigned_to, assigned_by, owner_org_unit_id, lead_id) "
        "VALUES ('Call', 'followup', :due, CAST(:u AS uuid), CAST(:by AS uuid), CAST(:ou AS uuid), CAST(:l AS uuid))"),
        {"due": due, "u": shop.ids[to], "by": shop.ids[by], "ou": shop.office, "l": lead})
    await s.commit()
    await s.close()


async def test_an_officer_does_not_count_a_colleagues_leads(client: httpx.AsyncClient, shop: Shop,
                                                            sessions: Sessions) -> None:
    """The manager's lead is out of the officer's lead scope; the officer's own task
    on it is left out too (rule 4: both task and lead)."""
    (theirs,) = await _leads(sessions, shop, [(_at(1), "new", "9000")], owner="district_manager")
    await _task(sessions, shop, theirs, _at(2), to="field_officer")
    o = await _overview(client, await endpoints._as(client, shop, "field_officer"))
    assert o["kpis"]["new_leads"]["value"] == "0" and o["kpis"]["pipeline_value"]["value"] == "0.00"
    assert o["follow_ups"] == [] and o["kpis"]["overdue_follow_ups"]["value"] == "0"
    dm = await _overview(client, await endpoints._as(client, shop, "district_manager"))
    assert dm["kpis"]["new_leads"]["value"] == "1", "the manager counts their own"


async def test_ten_follow_ups_at_most(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    (lead,) = await _leads(sessions, shop, [(_at(1), "new", None)])
    for i in range(11):
        await _task(sessions, shop, lead, _at(0, 20) + dt.timedelta(minutes=i), to="field_officer")
    o = await _overview(client, await endpoints._as(client, shop, "field_officer"))
    assert len(o["follow_ups"]) == 10
    assert [r["due_at"] for r in o["follow_ups"]] == sorted(r["due_at"] for r in o["follow_ups"])


async def test_a_dealer_sees_its_leads_and_no_task_figures(client: httpx.AsyncClient, shop: Shop,
                                                           sessions: Sessions) -> None:
    from tests.api.test_complaints import _dealer, _forget
    (lead,) = await _leads(sessions, shop, [(_at(1), "new", "1200")])
    await _task(sessions, shop, lead, _at(2), to="field_officer")
    s = sessions()
    await s.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) WHERE id = CAST(:l AS uuid)"),
                    {"p": shop.partner, "l": lead})
    await s.commit()
    await s.close()
    h, mobile = await _dealer(client, shop, sessions)
    try:
        o = await _overview(client, h)
        assert o["kpis"]["new_leads"]["value"] == "1" and o["kpis"]["pipeline_value"]["value"] == "1200.00"
        assert o["kpis"]["overdue_follow_ups"]["value"] is None, "no figure, not a false zero"
        assert o["follow_ups"] == []
    finally:
        await _forget(sessions, mobile)


async def test_a_deleted_leads_task_leaves_both_overdue_figures(client: httpx.AsyncClient, shop: Shop,
                                                                sessions: Sessions) -> None:
    """Code review F-3: for a deleter the card and /leads/stats used to disagree."""
    (lead,) = await _leads(sessions, shop, [(_at(3), "new", None)])
    await _task(sessions, shop, lead, _at(2), to="field_officer")
    h = await endpoints._as(client, shop, "admin_sales")

    async def both() -> tuple[str, int]:
        card = (await _overview(client, h))["kpis"]["overdue_follow_ups"]["value"]
        st = (await client.get(f"{V1}/leads/stats", headers=h)).json()
        return card, (st.get("data", st))["follow_ups_overdue"]

    card, listed = await both()
    assert card == str(listed)
    s = sessions()
    await s.execute(text("UPDATE lead SET deleted_at = now() WHERE id = CAST(:l AS uuid)"), {"l": lead})
    await s.commit()
    await s.close()
    card2, listed2 = await both()
    assert card2 == str(listed2) and listed2 == listed - 1
