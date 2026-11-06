"""FS-037: tasks for dealers, behind the `tasks_for_dealers` setting.

The world is the order tests' shop, whose dealer has one user. The setting is
company-wide: `restore` puts it back."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.clock import today_ist
from tests.api import test_complaints as complaints_t
from tests.api import test_order_concurrency as conc
from tests.api import test_order_endpoints as endpoints
from tests.api import test_settings_amend_reopen as settings_t
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
restore = settings_t.restore
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _task(client: httpx.AsyncClient, h: dict[str, str], assignee: str, **body: Any) -> httpx.Response:
    payload = {"title": "Visit the farmer", "task_type": "visit", "assigned_to": assignee,
               "due_at": (today_ist() + dt.timedelta(days=2)).isoformat(), **body}
    return await client.post(f"{V1}/tasks", json=payload, headers={**h, **_key()})


async def test_off_by_default_a_dealer_is_not_assignable(client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    r = await _task(client, dm, shop.ids["dealer"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_assignable", r.text
    r = await client.get(f"{V1}/tasks/assignees", headers=dm, params={"include_partners": "true"})
    assert all(x["kind"] == "staff" for x in r.json()["data"])


async def test_a_manager_assigns_a_dealer_who_completes_it_and_does_nothing_else(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:
    await settings_t._set(sessions, "tasks_for_dealers", "on")
    dm = await endpoints._as(client, shop, "district_manager")
    picker = (await client.get(f"{V1}/tasks/assignees", headers=dm, params={"include_partners": "true"})).json()["data"]
    dealers = [x for x in picker if x["kind"] == "partner"]
    assert shop.ids["dealer"] in {x["id"] for x in dealers}
    assert next(x for x in dealers if x["id"] == shop.ids["dealer"])["partner"]["id"] == shop.partner
    r = await _task(client, dm, shop.ids["dealer"])
    assert r.status_code == 201, r.text
    task = r.json()["data"]

    dealer, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        mine = (await client.get(f"{V1}/tasks", headers=dealer, params={"assigned_to": "me"})).json()["data"]
        assert task["id"] in {t["id"] for t in mine}
        for verb, path, body in (("patch", f"/tasks/{task['id']}", {"title": "Mine"}),
                                 ("post", f"/tasks/{task['id']}/cancel", {"reason": "No"})):
            r = await getattr(client, verb)(f"{V1}{path}", headers={**dealer, **_key()}, json=body)
            assert r.status_code == 403, (path, r.text)
        r = await _task(client, dealer, shop.ids["dealer"])
        assert r.status_code == 403, "a dealer creates no tasks"
        r = await client.post(f"{V1}/tasks/{task['id']}/complete", headers={**dealer, **_key()},
                              json={"outcome": "Met the farmer"})
        assert r.status_code == 200 and r.json()["data"]["status"] == "done", r.text
    finally:
        await complaints_t._forget(sessions, mobile)


async def test_an_officer_cannot_assign_a_dealer_and_the_link_must_be_visible(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:
    await settings_t._set(sessions, "tasks_for_dealers", "on")
    fo = await endpoints._as(client, shop, "field_officer")
    r = await _task(client, fo, shop.ids["dealer"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_assignable", "own scope assigns only themselves"
    # a lead the dealer is not on: the dealer could not open it
    dm = await endpoints._as(client, shop, "district_manager")
    lead = (await client.post(f"{V1}/leads", headers={**dm, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{dt.datetime.now().microsecond:06d}11",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip"})).json()["data"]
    r = await _task(client, dm, shop.ids["dealer"], lead_id=lead["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "link_not_visible_to_assignee", r.text


async def test_the_database_stops_a_dealer_changing_more_than_completion(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:
    await settings_t._set(sessions, "tasks_for_dealers", "on")
    dm = await endpoints._as(client, shop, "district_manager")
    task = (await _task(client, dm, shop.ids["dealer"])).json()["data"]
    s = sessions()
    try:
        await conc._as(s, shop.ids["dealer"])
        with pytest.raises(DBAPIError) as err:
            await s.execute(text("UPDATE task SET title = 'mine' WHERE id = CAST(:t AS uuid)"), {"t": task["id"]})
        assert getattr(err.value.orig, "sqlstate", None) == "42501"
    finally:
        await s.rollback()
        await s.close()


async def test_a_dealer_user_with_open_tasks_is_not_deactivated(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, restore: None) -> None:
    await settings_t._set(sessions, "tasks_for_dealers", "on")
    dm = await endpoints._as(client, shop, "district_manager")
    assert (await _task(client, dm, shop.ids["dealer"])).status_code == 201
    admin = await endpoints._as(client, shop, "admin_sales")
    r = await client.patch(f"{V1}/users/{shop.ids['dealer']}", headers={**admin, **_key()}, json={"is_active": False})
    assert r.status_code == 422 and "is_active" in r.json()["error"]["fields"], r.text
