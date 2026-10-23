"""The lead list's hierarchy filters: state-wise, office-wise and partner-wise,
each selecting its whole subtree (the client's request of 24 Sep: "filter state
wise, hierarchy wise, user wise")."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1

shop = endpoints.shop
Shop = endpoints.Shop

pytestmark = pytest.mark.db


async def test_state_office_partner_and_user_filters_select_their_subtrees(
        client: httpx.AsyncClient, shop: Shop, sessions: Callable[[], AsyncSession]) -> None:
    s = sessions()
    tag = uuid.uuid4().hex[:8]
    try:
        lead = str((await s.execute(text(
            "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
            "mobile, territory_id, owner_user_id, owner_org_unit_id, created_by, assigned_partner_id) "
            "VALUES (:no, 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
            "(SELECT id FROM lead_source WHERE code = 'employee'), :name, :mob, CAST(:t AS uuid), "
            "CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:o AS uuid), CAST(:p AS uuid)) RETURNING id"),
            {"no": f"FILTER-{tag}", "name": f"Filter Farmer {tag}",
             "mob": "+9197" + f"{uuid.uuid4().int % 10**8:08d}", "t": shop.district,
             "o": shop.ids["field_officer"], "ou": shop.office, "p": shop.partner})).scalar_one())
        elsewhere = str((await s.execute(text(
            "INSERT INTO territory (level, name) VALUES ('state', :n) RETURNING id"),
            {"n": f"filter_elsewhere_{tag}"})).scalar_one())
        await s.commit()
    finally:
        await s.close()

    h = await endpoints._as(client, shop, "admin_sales")

    async def found(**params: str) -> bool:
        r = await client.get(f"{V1}/leads", headers=h, params={"q": f"Filter Farmer {tag}", **params})
        assert r.status_code == 200, r.text
        return any(x["id"] == lead for x in r.json()["data"])

    try:
        # the lead sits on a district; its state selects it
        assert await found(territory_id=shop.state), "state-wise must include the state's districts"
        assert await found(territory_id=shop.district)
        assert not await found(territory_id=elsewhere)
        assert await found(owner_org_unit_id=shop.office)
        assert await found(assigned_partner_id=shop.partner)
        assert await found(owner_user_id=shop.ids["field_officer"])
        assert not await found(owner_user_id=shop.ids["district_manager"])
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM territory WHERE id = CAST(:t AS uuid)"), {"t": elsewhere})
        await c.commit()
        await c.close()


async def test_the_counts_match_the_list_under_the_same_filter(
        client: httpx.AsyncClient, shop: Shop, sessions: Callable[[], AsyncSession]) -> None:
    """API review B2: the pipeline board's counts, by stage, by priority and
    unassigned, under the list's own scope and filters."""
    s = sessions()
    tag = uuid.uuid4().hex[:8]
    try:
        for i, (stage, priority, owner) in enumerate([("new", "hot", None),
                                                      ("new", "warm", shop.ids["field_officer"]),
                                                      ("contacted", "hot", shop.ids["field_officer"])]):
            await s.execute(text(
                "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
                "mobile, territory_id, owner_user_id, owner_org_unit_id, created_by, stage, priority) "
                "VALUES (:no, 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
                "(SELECT id FROM lead_source WHERE code = 'employee'), 'Count Farmer', :mob, "
                "CAST(:t AS uuid), CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:c AS uuid), "
                "CAST(:st AS lead_stage), CAST(:pr AS lead_priority))"),
                {"no": f"COUNT-{tag}-{i}", "mob": "+9197" + f"{uuid.uuid4().int % 10**8:08d}",
                 "t": shop.district, "o": owner, "ou": shop.office, "c": shop.ids["admin_sales"],
                 "st": stage, "pr": priority})
        await s.commit()
    finally:
        await s.close()

    h = await endpoints._as(client, shop, "admin_sales")
    r = await client.get(f"{V1}/leads/stats", headers=h, params={"territory_id": shop.state})
    assert r.status_code == 200, r.text
    got = r.json()["data"] if "data" in r.json() else r.json()
    assert got["total"] == 3 and got["unassigned"] == 1
    assert got["by_stage"]["new"] == 2 and got["by_stage"]["contacted"] == 1
    assert got["by_stage"]["won"] == 0 and set(got["by_stage"]) >= {"new", "won", "lost"}
    assert got["by_priority"] == {"hot": 2, "warm": 1, "cold": 0}
    listed = await client.get(f"{V1}/leads", headers=h,
                              params={"territory_id": shop.state, "include_total": "true"})
    assert listed.json()["meta"]["total"] == got["total"], "the board and the list agree"
    fo = await endpoints._as(client, shop, "field_officer")
    mine = (await client.get(f"{V1}/leads/stats", headers=fo,
                             params={"territory_id": shop.state})).json()
    mine = mine.get("data", mine)
    assert mine["total"] == 2 and mine["unassigned"] == 0, "a field officer counts only their own"


async def test_stats_count_sources_types_and_follow_ups(
        client: httpx.AsyncClient, shop: Shop, sessions: Callable[[], AsyncSession]) -> None:
    """BE-007 and BE-002: by source and by inquiry type over the same scope, and the
    open tasks on those leads due today and overdue, by the planner's IST days."""
    s = sessions()
    tag = uuid.uuid4().hex[:8]
    leads = []
    try:
        for i, (source, kind) in enumerate((("employee", "commercial"), ("employee", "subsidised"),
                                            ("website", "commercial"))):
            leads.append(str((await s.execute(text(
                "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
                "mobile, territory_id, owner_user_id, owner_org_unit_id, created_by) "
                "VALUES (:no, CAST(:k AS inquiry_type), (SELECT id FROM mis_system WHERE code = 'drip'), "
                "(SELECT id FROM lead_source WHERE code = :src), 'Stats Farmer', :mob, CAST(:t AS uuid), "
                "CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:o AS uuid)) RETURNING id"),
                {"no": f"STATS-{tag}-{i}", "k": kind, "src": source,
                 "mob": "+9197" + f"{uuid.uuid4().int % 10**8:08d}", "t": shop.district,
                 "o": shop.ids["field_officer"], "ou": shop.office})).scalar_one()))
        fo = shop.ids["field_officer"]
        # due today (late evening IST), overdue by two days, tomorrow, and a done one today
        for lead, due, status in ((leads[0], "today 23:00", "open"), (leads[1], "-2 days", "open"),
                                  (leads[2], "+1 day", "open"), (leads[2], "today 23:00", "done")):
            await s.execute(text(
                "INSERT INTO task (title, task_type, status, due_at, assigned_to, assigned_by, "
                "owner_org_unit_id, lead_id, completed_at, outcome) VALUES ('Call', 'followup', "
                "CAST(:st AS task_status), CASE :due "
                "  WHEN 'today 23:00' THEN (date_trunc('day', now() AT TIME ZONE 'Asia/Kolkata') + interval '23 hours') AT TIME ZONE 'Asia/Kolkata' "
                "  WHEN '-2 days' THEN now() - interval '2 days' ELSE now() + interval '1 day' END, "
                "CAST(:fo AS uuid), CAST(:fo AS uuid), CAST(:ou AS uuid), CAST(:l AS uuid), "
                "CASE WHEN :st = 'done' THEN now() END, CASE WHEN :st = 'done' THEN 'Spoke' END)"),
                {"st": status, "due": due, "fo": fo, "ou": shop.office, "l": lead})
        # noise the officer's counts must not include: the manager's own lead with a
        # task due today, and a personal task of the officer's with no lead
        dm = shop.ids["district_manager"]
        other = str((await s.execute(text(
            "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
            "mobile, territory_id, owner_user_id, owner_org_unit_id, created_by) "
            "VALUES (:no, 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
            "(SELECT id FROM lead_source WHERE code = 'website'), 'Other Farmer', :mob, CAST(:t AS uuid), "
            "CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:o AS uuid)) RETURNING id"),
            {"no": f"STATS-{tag}-dm", "mob": "+9197" + f"{uuid.uuid4().int % 10**8:08d}",
             "t": shop.district, "o": dm, "ou": shop.office})).scalar_one())
        today_2300 = ("(date_trunc('day', now() AT TIME ZONE 'Asia/Kolkata') + interval '23 hours') "
                      "AT TIME ZONE 'Asia/Kolkata'")
        for who, lead in ((dm, other), (fo, None)):
            await s.execute(text(
                "INSERT INTO task (title, task_type, due_at, assigned_to, assigned_by, owner_org_unit_id, "
                f"lead_id) VALUES ('Call', 'followup', {today_2300}, CAST(:u AS uuid), CAST(:u AS uuid), "
                "CAST(:ou AS uuid), CAST(:l AS uuid))"), {"u": who, "ou": shop.office, "l": lead})
        await s.commit()
    finally:
        await s.close()

    h = await endpoints._as(client, shop, "field_officer")
    got = (await client.get(f"{V1}/leads/stats", headers=h, params={"territory_id": shop.state})).json()
    got = got.get("data", got)
    assert got["total"] == 3
    assert got["by_source"]["employee"] == 2 and got["by_source"]["website"] == 1
    c = sessions()
    sources = set((await c.execute(text(
        "SELECT code FROM lead_source WHERE deleted_at IS NULL"))).scalars())
    await c.close()
    assert set(got["by_source"]) == {str(x) for x in sources}, "every source is present"
    assert all(v == 0 for k, v in got["by_source"].items() if k not in ("employee", "website")), \
        "0 when empty"
    assert got["by_inquiry_type"] == {"commercial": 2, "subsidised": 1, "industrial": 0}
    assert got["follow_ups_due_today"] == 1, "the open one today; not the done one, not tomorrow's"
    assert got["follow_ups_overdue"] == 1
    narrowed = (await client.get(f"{V1}/leads/stats", headers=h,
                                 params={"territory_id": shop.state, "stage": "won"})).json()
    narrowed = narrowed.get("data", narrowed)
    assert (narrowed["follow_ups_due_today"], narrowed["follow_ups_overdue"]) == (0, 0), \
        "the lead filters apply to the follow-ups: no lead is won"


async def test_no_tasks_scope_means_no_follow_up_figure() -> None:
    """A dealer's dashboard shows no figure rather than a false zero."""
    from api.authz.predicate import Caller
    from api.services import leads as service
    dealer = Caller(str(uuid.uuid4()), None, str(uuid.uuid4()), scopes={"leads": "partner_subtree"})
    assert await service.follow_ups(None, dealer, []) == (None, None)  # type: ignore[arg-type]
