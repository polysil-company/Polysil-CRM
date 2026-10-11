"""Whoever sees a lead sees the people on it (RBAC.md 6.2, GAP-060): the list a
District Manager opens names the owner, and names a dealer who created a lead,
though no users scope of the manager's reaches a partner user."""

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


async def test_a_district_manager_sees_the_owner_and_a_dealer_creator_on_the_lead_list(
        client: httpx.AsyncClient, shop: Shop, sessions: Callable[[], AsyncSession]) -> None:
    s = sessions()
    try:
        lead = str((await s.execute(text(
            "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
            "mobile, territory_id, owner_user_id, owner_org_unit_id, created_by, assigned_partner_id) "
            "VALUES (:no, 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
            "(SELECT id FROM lead_source WHERE code = 'dealer'), 'Named Farmer', :mob, CAST(:t AS uuid), "
            "CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:c AS uuid), CAST(:p AS uuid)) RETURNING id"),
            {"no": f"PEOPLE-{uuid.uuid4().hex[:8]}", "mob": "+9197" + f"{uuid.uuid4().int % 10**8:08d}",
             "t": shop.district, "o": shop.ids["field_officer"], "ou": shop.office,
             "c": shop.ids["dealer"], "p": shop.partner})).scalar_one())
        await s.commit()
    finally:
        await s.close()

    h = await endpoints._as(client, shop, "district_manager")
    r = await client.get(f"{V1}/leads", headers=h, params={"q": "Named Farmer"})
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["data"] if x["id"] == lead)
    assert row["owner"] == {"id": shop.ids["field_officer"], "full_name": "Field Officer"}
    assert row["created_by"] == {"id": shop.ids["dealer"], "full_name": "Bhavesh Shah"}
    assert row["assigned_partner"]["name"] == "Shah Irrigation"
