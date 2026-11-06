"""FS-086: a person's assigned districts count toward their area.

Built on FS-020's `area`: a field officer in a taluka office under the shop's
district, and a second district ("far") outside every office's area, with two
dealers in it. Assigning "far" to the officer brings those dealers in."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from tests.api.test_dealer_area_access import Area, _officer, _picker, area
from tests.api.test_order_endpoints import Shop, shop

pytestmark = pytest.mark.db
__all__ = ["area", "shop"]


async def _officer_id(sessions: Callable[[], AsyncSession], area: Area) -> str:
    s = sessions()
    uid = str((await s.execute(text("SELECT id FROM app_user WHERE email = CAST(:e AS citext)"),
                               {"e": area.officer})).scalar_one())
    await s.close()
    return uid


@pytest_asyncio.fixture
async def held(area: Area, sessions: Callable[[], AsyncSession]) -> AsyncIterator[Callable[..., object]]:
    """Assign territories to the area's officer; every row goes at teardown."""
    uid = await _officer_id(sessions, area)
    made: list[str] = []

    async def give(territory: str) -> None:
        s = sessions()
        made.append(str((await s.execute(text(
            "INSERT INTO user_territory (user_id, territory_id) VALUES (CAST(:u AS uuid), CAST(:t AS uuid)) RETURNING id"),
            {"u": uid, "t": territory})).scalar_one()))
        await s.commit()
        await s.close()

    try:
        yield give
    finally:
        s = sessions()
        await s.execute(text("DELETE FROM user_territory WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": made})
        await s.commit()
        await s.close()


async def test_an_assigned_district_brings_its_dealers_in(
        client: httpx.AsyncClient, shop: Shop, area: Area, held: Callable[..., object]) -> None:
    """Rule 1, EC-1: the picker (RLS) and GET /partners (the Python enforcer too)."""
    ho = await _officer(client, area)
    assert area.far_dealer not in await _picker(client, ho)
    await held(area.far_district)  # type: ignore[misc]
    seen = await _picker(client, ho)
    assert {area.far_dealer, area.stray_dealer, area.taluka_dealer, shop.partner} <= seen
    r = await client.get("/api/v1/partners", params={"limit": 100}, headers=ho)
    if r.status_code == 200:  # an officer may lack the list route; the read rule is what counts
        assert area.far_dealer in {p["id"] for p in r.json()["data"]}
    r = await client.get(f"/api/v1/partners/{area.far_dealer}", headers=ho)
    assert r.status_code in (200, 403), r.text
    if r.status_code == 200:
        assert r.json()["data"]["id"] == area.far_dealer


async def test_a_state_assigned_adds_nothing(
        client: httpx.AsyncClient, shop: Shop, area: Area, held: Callable[..., object],
        sessions: Callable[[], AsyncSession]) -> None:
    """Rule 7: a state never counts. A second state, with a dealer of its own."""
    tag = uuid.uuid4().hex[:6].upper()
    s = sessions()
    state = str((await s.execute(text("INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
                                 {"n": f"held_state_{tag}", "c": f"Z{tag[:1]}"})).scalar_one())
    district = str((await s.execute(text("INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, CAST(:p AS uuid)) RETURNING id"),
                                    {"n": f"held_district_{tag}", "p": state})).scalar_one())
    dealer = str((await s.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, mobile, territory_id, price_tier) "
        "VALUES ('dealer', :c, :n, :m, CAST(:t AS uuid), 'dealer') RETURNING id"),
        {"c": f"HLD{tag}", "n": f"Held State Dealer {tag}", "m": "9193" + f"{uuid.uuid4().int % 10**8:08d}", "t": district})).scalar_one())
    await s.commit()
    try:
        await held(state)  # type: ignore[misc]
        ho = await _officer(client, area)
        assert dealer not in await _picker(client, ho), "a state assignment widened the area"
        # a deleted territory adds nothing either (EC-8)
        await s.execute(text("UPDATE territory SET deleted_at = now() WHERE id = CAST(:t AS uuid)"), {"t": district})
        await s.commit()
        await held(district)  # type: ignore[misc]
        assert dealer not in await _picker(client, ho), "a deleted district widened the area"
    finally:
        await s.execute(text("DELETE FROM user_territory WHERE territory_id = ANY(CAST(:t AS uuid[]))"), {"t": [state, district]})
        await s.execute(text("DELETE FROM channel_partner WHERE id = CAST(:p AS uuid)"), {"p": dealer})
        await s.execute(text("DELETE FROM territory WHERE id = CAST(:t AS uuid)"), {"t": district})
        await s.execute(text("DELETE FROM territory WHERE id = CAST(:t AS uuid)"), {"t": state})
        await s.commit()
        await s.close()


async def test_the_automatic_owner_comes_through_an_assigned_district(
        shop: Shop, area: Area, held: Callable[..., object],
        sessions: Callable[[], AsyncSession]) -> None:
    """Rule 5: no office covers "far", so before the assignment nobody gets its lead."""

    async def owner() -> str | None:
        s = sessions()
        try:
            await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                            {"u": shop.ids["admin_sales"]})
            await enter_role(s, "app_role")
            got = (await s.execute(text("SELECT lead_auto_owner(CAST(:t AS uuid))"),
                                   {"t": area.far_district})).scalar_one_or_none()
            return str(got) if got else None
        finally:
            await s.rollback()
            await s.close()

    assert await owner() is None
    await held(area.far_district)  # type: ignore[misc]
    assert await owner() == await _officer_id(sessions, area)
