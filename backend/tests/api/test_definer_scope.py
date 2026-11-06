"""The PR 11 review of 033 to 039, as executed facts: two granted definers called
directly by a caller outside the area, and a scheme edit racing a use of the scheme.

A definer bypasses RLS, so a plain EXISTS on channel_partner inside one sees every
dealer. The service guards these calls; these tests skip the service on purpose."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.clock import today_ist
from tests.api import test_order_concurrency as conc
from tests.api import test_order_endpoints as endpoints
from tests.api import test_schemes as schemes
from tests.api.conftest import PASSWORD

pytestmark = pytest.mark.db

shop = endpoints.shop
made = schemes.made
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


@pytest_asyncio.fixture
async def elsewhere(shop: Shop, sessions: Sessions) -> AsyncIterator[dict[str, str]]:
    """A second district in the shop's state, with its own office, manager and dealer."""
    tag = uuid.uuid4().hex[:8]
    c = sessions()
    district = str((await c.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, CAST(:p AS uuid)) RETURNING id"),
        {"n": f"ds_other_{tag}", "p": shop.state})).scalar_one())
    office = str((await c.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, CAST(:t AS uuid)) RETURNING id"),
        {"n": f"ds_office_{tag}", "t": district})).scalar_one())
    email = f"ds_dm_{tag}@polysil.in"
    dm = str((await c.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, :p, 'Other DM', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'district_manager' "
        "RETURNING id"), {"e": email, "p": PasswordHasher().hash(PASSWORD), "o": office})).scalar_one())
    dealer = str((await c.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, mobile, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'Far Dealer', :m, CAST(:t AS uuid), 'dealer') RETURNING id"),
        {"c": f"DSF{tag}".upper(), "m": "9193" + f"{uuid.uuid4().int % 10**8:08d}", "t": district})).scalar_one())
    await c.commit()
    await c.close()
    try:
        yield {"district": district, "office": office, "dm": dm, "dealer": dealer}
    finally:
        c = sessions()
        for stmt in ("DELETE FROM app_user WHERE id = CAST(:u AS uuid)",
                     "DELETE FROM channel_partner WHERE id = CAST(:d AS uuid)",
                     "DELETE FROM org_unit WHERE id = CAST(:o AS uuid)",
                     "DELETE FROM territory WHERE id = CAST(:t AS uuid)"):
            await c.execute(text(stmt), {"u": dm, "d": dealer, "o": office, "t": district})
        await c.commit()
        await c.close()


async def _as(sessions: Sessions, user_id: str) -> AsyncSession:
    s = sessions()
    await conc._as(s, user_id)
    return s


async def _sqlstate(s: AsyncSession, sql: str, params: dict[str, Any]) -> str:
    try:
        await s.execute(text(sql), params)
    except DBAPIError as exc:
        return str(getattr(exc.orig, "sqlstate", ""))
    return "ok"


async def test_marketing_order_create_checks_the_dealer_and_the_office_itself(
        shop: Shop, elsewhere: dict[str, str], sessions: Sessions) -> None:
    """PR 11 review finding 1: called directly, past the service."""
    c = sessions()
    material = str((await c.execute(text(
        "SELECT id FROM marketing_material WHERE is_active ORDER BY code LIMIT 1"))).scalar_one())
    await c.close()
    lines = json.dumps([{"material_id": material, "qty": 1}])
    call = "SELECT marketing_order_create(CAST(:p AS uuid), CAST(:o AS uuid), CAST(:l AS jsonb), NULL)"
    for partner, office, expected in (
            (elsewhere["dealer"], shop.office, "MKTVL"),   # a dealer outside the manager's reach
            (None, elsewhere["office"], "42501"),          # another district's office
            (None, shop.office, "ok")):                     # their own office: allowed
        s = await _as(sessions, shop.ids["district_manager"])
        try:
            got = await _sqlstate(s, call, {"p": partner, "o": office, "l": lines})
        finally:
            await s.rollback()
            await s.close()
        assert got == expected, (partner, office, got)


async def test_scheme_standing_answers_only_inside_the_callers_reach(
        client: httpx.AsyncClient, shop: Shop, made: list[str], elsewhere: dict[str, str],
        sessions: Sessions) -> None:
    """PR 11 review finding 1: scheme_standing had no permission check and an EXISTS
    that RLS cannot filter, so a direct call read any dealer's period standing."""
    today = today_ist()
    start = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    end = (today.replace(day=1) + dt.timedelta(days=40)).replace(day=1) - dt.timedelta(days=1)
    s = await schemes._scheme(client, shop, made, scheme_type="period", period="month",
                              valid_from=start.isoformat(), valid_to=end.isoformat(),
                              condition={"metric": "order_value", "min": "1"},
                              benefit={"kind": "pct", "value": "4", "entitlement_days": 60})
    call = "SELECT scheme_standing(CAST(:s AS uuid), CAST(:p AS uuid), :d) IS NOT NULL"
    answers = {}
    for who in (shop.ids["district_manager"], elsewhere["dm"]):
        c = await _as(sessions, who)
        try:
            answers[who] = (await c.execute(text(call), {"s": s["id"], "p": shop.partner, "d": today})).scalar_one()
        finally:
            await c.rollback()
            await c.close()
    assert answers[shop.ids["district_manager"]] is True, "inside the area: the standing"
    assert answers[elsewhere["dm"]] is False, "another district's manager reads nothing"


async def test_a_scheme_edit_waits_for_a_use_in_flight_and_then_sees_it(
        client: httpx.AsyncClient, shop: Shop, made: list[str], sessions: Sessions) -> None:
    """PR 11 review finding 4 (rule 16). Without the share lock the edit passes
    scheme_used() while the use is uncommitted, and the used scheme's terms change."""
    s = await schemes._scheme(client, shop, made)
    order = await schemes._order(client, shop, schemes._with_partner(shop))
    holder = sessions()
    editor = sessions()
    try:
        await holder.execute(text(
            "INSERT INTO scheme_benefit (sales_order_id, scheme_id, kind, basis, amount) "
            "VALUES (CAST(:o AS uuid), CAST(:s AS uuid), 'discount', 1, 1)"), {"o": order["id"], "s": s["id"]})
        pid = int((await editor.execute(text("SELECT pg_backend_pid()"))).scalar_one())
        edit = asyncio.create_task(_sqlstate(
            editor, "UPDATE scheme SET condition_min = coalesce(condition_min, 0) + 1 WHERE id = CAST(:s AS uuid)",
            {"s": s["id"]}))
        assert await conc._blocked(sessions, pid), "the edit did not wait for the use"
        await holder.commit()
        assert await edit == "SCHIU", "once the use commits, the edit sees it and is refused"
    finally:
        await editor.rollback()
        await editor.close()
        await holder.rollback()
        await holder.close()
