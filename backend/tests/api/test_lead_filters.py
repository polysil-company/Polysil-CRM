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
