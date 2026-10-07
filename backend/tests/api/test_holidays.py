"""FS-028 over the API: /holidays and its codes, and the escalation fields on a
complaint, which a dealer never gets. The sweep itself is tested at the database."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import complaints as domain
from tests.api import test_complaints as complaints_t
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


def _future_weekday(days: int) -> dt.date:
    d = domain.ist_today(dt.datetime.now(dt.UTC)) + dt.timedelta(days=days)
    return d + dt.timedelta(days=1) if d.isoweekday() == 7 else d


async def test_holidays_are_listed_for_anyone_and_kept_by_masters_editors(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    day = _future_weekday(200)
    admin = await endpoints._as(client, shop, "admin_sales")
    fo = await endpoints._as(client, shop, "field_officer")
    try:
        r = await client.post(f"{V1}/holidays", headers={**fo, **_key()}, json={"day": day.isoformat(), "name": "Diwali"})
        assert r.status_code == 403, r.text
        r = await client.post(f"{V1}/holidays", headers={**admin, **_key()}, json={"day": day.isoformat(), "name": "Diwali"})
        assert r.status_code == 201 and r.json()["data"] == {"day": day.isoformat(), "name": "Diwali"}, r.text
        r = await client.post(f"{V1}/holidays", headers={**admin, **_key()}, json={"day": day.isoformat(), "name": "Again"})
        assert r.status_code == 409 and complaints_t._code(r) == "holiday_exists", r.text
        today = domain.ist_today(dt.datetime.now(dt.UTC))
        r = await client.post(f"{V1}/holidays", headers={**admin, **_key()}, json={"day": today.isoformat(), "name": "Closure"})
        assert r.status_code == 422 and complaints_t._code(r) == "holiday_in_past", r.text
        sunday = day + dt.timedelta(days=7 - day.isoweekday())
        r = await client.post(f"{V1}/holidays", headers={**admin, **_key()}, json={"day": sunday.isoformat(), "name": "Sunday"})
        assert r.status_code == 422 and complaints_t._code(r) == "holiday_sunday", r.text
        listed = (await client.get(f"{V1}/holidays", headers=fo, params={"year": day.year})).json()["data"]
        assert {"day": day.isoformat(), "name": "Diwali"} in listed
        r = await client.delete(f"{V1}/holidays/{day.isoformat()}", headers={**admin, **_key()})
        assert r.status_code == 204, r.text
        r = await client.delete(f"{V1}/holidays/{day.isoformat()}", headers={**admin, **_key()})
        assert r.status_code == 404, r.text
    finally:
        s = sessions()
        await s.execute(text("DELETE FROM activity_event WHERE kind IN ('holiday.added', 'holiday.removed') AND payload ->> 'day' = :d"),
                        {"d": day.isoformat()})
        await s.execute(text("DELETE FROM holiday WHERE day = :d"), {"d": day})
        await s.commit()
        await s.close()


async def test_the_escalation_fields_are_for_staff_only(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    dealer, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        c = await complaints_t._create(client, shop, dealer)
        s = sessions()
        await s.execute(text("UPDATE complaint SET response_escalated_at = now() WHERE id = CAST(:c AS uuid)"), {"c": c["id"]})
        await s.commit()
        await s.close()
        admin = await endpoints._as(client, shop, "admin_sales")
        staff = (await client.get(f"{V1}/complaints/{c['id']}", headers=admin)).json()["data"]
        assert staff["response_escalated_at"] is not None and staff["resolution_escalated_at"] is None
        seen = (await client.get(f"{V1}/complaints/{c['id']}", headers=dealer)).json()["data"]
        assert seen["response_escalated_at"] is None, "a dealer never gets the escalation fields"
    finally:
        await complaints_t._forget(sessions, mobile)
