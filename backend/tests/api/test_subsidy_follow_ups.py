"""FS-009a: ageing and reports over real stage entries, and subsidy masters revised
from a date without restating what is in force today."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api import test_subsidy_applications as subsidy
from tests.api.conftest import V1, _key

shop = endpoints.shop
office = subsidy.office
fake_engine = subsidy.fake_engine
Sessions = Callable[[], AsyncSession]

pytestmark = pytest.mark.db


@pytest.mark.usefixtures("fake_engine")
async def test_ageing_and_the_reports_read_the_recorded_dates_in_scope(
        client: httpx.AsyncClient, office: subsidy.Office) -> None:
    fo = await subsidy._as(client, office, "field_officer")
    app = await subsidy._app(client, office, fo)
    sc = await subsidy._as(client, office, "state_coordinator")
    inward = today_ist() - dt.timedelta(days=20)
    r = await subsidy._record(client, sc, app["id"], "application_in_process", days_ago=20,
                              values={"app_inward": inward.isoformat()}, remark="Filed")
    assert r.status_code in (200, 201), r.text
    rows = (await client.get(f"{V1}/subsidy-reports/ageing", headers=sc,
                             params={"q": app["application_no"]})).json()["data"]
    [row] = rows
    f = row["inward_to_submission"]
    assert (f["days"], f["running"], f["since"], f["until"]) == (20, True, inward.isoformat(), None)
    assert row["today_to_supply"]["days"] is None

    stages = (await client.get(f"{V1}/subsidy-reports/stages", headers=sc)).json()["data"]
    assert any(s["code"] == "application_in_process" and s["count"] >= 1 for s in stages)
    supply = (await client.get(f"{V1}/subsidy-reports/supply", headers=sc)).json()["data"]
    assert sum(x["not_supplied"] for x in supply) >= 1
    for path in ("ageing", "stages", "supply"):
        r = await client.get(f"{V1}/subsidy-reports/{path}/export", headers=sc)
        assert r.status_code == 200 and r.content[:2] == b"PK", path

    stranger = await subsidy._as(client, office, "stranger")
    assert (await client.get(f"{V1}/subsidy-reports/ageing", headers=stranger,
                             params={"q": app["application_no"]})).json()["data"] == []


@pytest_asyncio.fixture
async def param_key(sessions: Sessions) -> AsyncIterator[str]:
    key = f"test_param_{uuid.uuid4().hex[:8]}"
    yield key
    c = sessions()
    await c.execute(text("DELETE FROM subsidy_parameter WHERE key = :k"), {"k": key})
    await c.commit()
    await c.close()


async def test_a_parameter_revision_starts_on_its_date_and_leaves_today_alone(
        client: httpx.AsyncClient, shop: endpoints.Shop, param_key: str) -> None:
    admin = await endpoints._as(client, shop, "admin_sales")
    tomorrow = today_ist() + dt.timedelta(days=1)
    later = today_ist() + dt.timedelta(days=5)

    async def revise(on: dt.date, value: str, h: dict[str, str] = admin) -> httpx.Response:
        return await client.post(f"{V1}/subsidy-masters/parameters/revisions", headers={**h, **_key()}, json={
            "effective_from": on.isoformat(), "rows": [{"key": param_key, "value": value, "unit": "rupees"}]})

    r = await revise(tomorrow, "200")
    assert r.status_code == 201 and r.json()["data"] == {"closed": 0, "inserted": 1, "effective_from": tomorrow.isoformat()}
    r = await revise(tomorrow, "250")
    assert (r.status_code == 409 and r.json()["error"]["code"] == "later_revision_exists") or \
        r.json()["error"]["code"] == "revision_on_start_date"
    r = await revise(later, "300")
    assert r.status_code == 201 and r.json()["data"]["closed"] == 1
    r = await revise(today_ist() - dt.timedelta(days=1), "1")
    assert r.status_code == 422 and r.json()["error"]["code"] == "revision_in_past"
    fo = await endpoints._as(client, shop, "field_officer")
    assert (await revise(later + dt.timedelta(days=3), "9", fo)).status_code == 403

    async def value_on(day: dt.date) -> Any:
        rows = (await client.get(f"{V1}/subsidy-masters/parameters", headers=fo,
                                 params={"on": day.isoformat()})).json()["data"]
        return next((x["value"] for x in rows if x["key"] == param_key), None)

    assert await value_on(today_ist()) is None, "nothing in force today"
    assert await value_on(tomorrow) == "200.0000"
    assert await value_on(later) == "300.0000"


@pytest.mark.usefixtures("fake_engine")
async def test_a_cleared_date_counts_as_cleared_and_a_cancelled_application_stops_counting(
        client: httpx.AsyncClient, office: subsidy.Office, sessions: Sessions) -> None:
    """Code review F-2 and F-3."""
    fo = await subsidy._as(client, office, "field_officer")
    app = await subsidy._app(client, office, fo)
    sc = await subsidy._as(client, office, "state_coordinator")
    wrong = today_ist() - dt.timedelta(days=9)
    r = await subsidy._record(client, sc, app["id"], "application_in_process", days_ago=9,
                              values={"app_inward": wrong.isoformat()}, remark="Filed")
    assert r.status_code in (200, 201), r.text
    r = await subsidy._record(client, sc, app["id"], "application_in_process", days_ago=0,
                              values={"app_inward": None}, remark="Inward date was wrong")
    assert r.status_code in (200, 201), r.text

    async def row() -> dict[str, Any]:
        rows = (await client.get(f"{V1}/subsidy-reports/ageing", headers=sc,
                                 params={"q": app["application_no"]})).json()["data"]
        return dict(rows[0])

    assert (await row())["inward_to_submission"]["days"] is None, "the cleared date is gone"
    r = await subsidy._record(client, sc, app["id"], "application_in_process", days_ago=0,
                              values={"app_inward": (today_ist() - dt.timedelta(days=4)).isoformat()},
                              remark="Right date")
    assert r.status_code in (200, 201), r.text
    r = await client.post(f"{V1}/subsidy-applications/{app['id']}/cancel", headers={**sc, **_key()},
                          json={"reason": "Farmer withdrew"})
    assert r.status_code == 200, r.text
    f = (await row())["inward_to_submission"]
    assert (f["days"], f["running"]) == (4, False), "stops on the IST day it was cancelled"
    cancelled = (await client.get(f"{V1}/subsidy-reports/supply", headers=sc,
                                  params={"status": "cancelled"})).json()["data"]
    assert sum(x["not_supplied"] for x in cancelled) >= 1, "status=cancelled is honoured"


@pytest_asyncio.fixture
async def matrix_restore(sessions: Sessions) -> AsyncIterator[list[str]]:
    """A quantity matrix in force for the test, a stand-in when the database has none
    (CI starts empty). Afterwards: every matrix the test made is removed, and the rows
    that were there get back only what changed on them (PR 11 review: the old fixture
    skipped on CI and rewrote updated_by on every row)."""
    made: list[str] = []
    c = sessions()
    before = {r.id: (r.effective_to, r.updated_by) for r in (await c.execute(text(
        "SELECT id, effective_to, updated_by FROM quantity_matrix"))).all()}
    open_now = (await c.execute(text(
        "SELECT count(*) FROM quantity_matrix WHERE is_active AND effective_from <= CURRENT_DATE "
        "AND (effective_to IS NULL OR effective_to > CURRENT_DATE)"))).scalar_one()
    if not open_now:
        stand_in = str((await c.execute(text(
            "INSERT INTO quantity_matrix (scheme_id, system_type, effective_from, source) "
            "SELECT id, 'sprinkler', DATE '2020-01-01', 'test stand-in' FROM subsidy_scheme WHERE code = 'GGRC' "
            "RETURNING id"))).scalar_one())
        await c.execute(text("INSERT INTO quantity_matrix_cell (matrix_id, component_code, area_breakpoint, qty) "
                             "VALUES (CAST(:m AS uuid), 'PIPE', 1, 10)"), {"m": stand_in})
        made.append(stand_in)
    await c.commit()
    await c.close()
    yield made
    c = sessions()
    # the test's own matrices first: reopening a closed one while they exist breaks ex_quantity_matrix
    await c.execute(text("DELETE FROM quantity_matrix_cell WHERE matrix_id IN "
                         "(SELECT id FROM quantity_matrix WHERE NOT (id = ANY(CAST(:keep AS uuid[]))))"),
                    {"keep": list(before)})
    await c.execute(text("DELETE FROM quantity_matrix WHERE NOT (id = ANY(CAST(:keep AS uuid[])))"),
                    {"keep": list(before)})
    now = {r.id: (r.effective_to, r.updated_by) for r in (await c.execute(text(
        "SELECT id, effective_to, updated_by FROM quantity_matrix"))).all()}
    for mid, (to, by) in before.items():
        if now.get(mid) != (to, by):
            await c.execute(text("UPDATE quantity_matrix SET effective_to = :t, updated_by = :b WHERE id = :m"),
                            {"t": to, "b": by, "m": mid})
    await c.commit()
    await c.close()


async def test_a_new_matrix_starts_on_its_date_and_the_old_one_stays_in_force_before_it(
        client: httpx.AsyncClient, shop: endpoints.Shop, matrix_restore: list[str], sessions: Sessions) -> None:
    """Code review F-4: the listing, and a revision that closes rather than edits."""
    admin = await endpoints._as(client, shop, "admin_sales")
    before = (await client.get(f"{V1}/subsidy-masters/quantity-matrices/matrices", headers=admin)).json()["data"]
    assert before, "the fixture puts a matrix in force"
    old = before[0]
    start = today_ist() + dt.timedelta(days=30)
    r = await client.post(f"{V1}/subsidy-masters/quantity-matrices/matrices", headers={**admin, **_key()}, json={
        "system_type": old["system_type"], "effective_from": start.isoformat(), "source": "test circular",
        "quantity_cells": [{"component_code": "TEST", "area_breakpoint": "1", "qty": "2"}]})
    assert r.status_code == 201, r.text
    c = sessions()
    mid = str((await c.execute(text(
        "SELECT id FROM quantity_matrix WHERE effective_from = :d AND source = 'test circular'"),
        {"d": start})).scalar_one())
    old_cells = (await c.execute(text("SELECT count(*) FROM quantity_matrix_cell WHERE matrix_id = CAST(:m AS uuid)"),
                                 {"m": old["id"]})).scalar_one()
    await c.close()
    today = (await client.get(f"{V1}/subsidy-masters/quantity-matrices/matrices", headers=admin)).json()["data"]
    later = (await client.get(f"{V1}/subsidy-masters/quantity-matrices/matrices", headers=admin,
                              params={"on": start.isoformat()})).json()["data"]
    assert old["id"] in {m["id"] for m in today}
    assert mid in {m["id"] for m in later} and old["id"] not in {m["id"] for m in later}
    assert old_cells == len(old["cells"]), "the old matrix's cells are untouched"
    r = await client.post(f"{V1}/subsidy-masters/quantity-matrices/matrices", headers={**admin, **_key()}, json={
        "system_type": old["system_type"], "effective_from": start.isoformat(), "source": "again",
        "quantity_cells": [{"component_code": "TEST", "area_breakpoint": "1", "qty": "3"}]})
    assert r.status_code == 409
