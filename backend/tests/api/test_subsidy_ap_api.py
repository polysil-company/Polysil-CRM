"""FS-063 through the API with no withheld fixtures: AP drip takes the portal's
figures and needs no company pricing, so this runs on CI (code review F-1).
The workbook checks live in `test_subsidy_states_api.py`."""

# ruff: noqa: E501  (request bodies and SQL inline)

from __future__ import annotations

import datetime as dt
import re
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any

import httpx
import psycopg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.services.subsidy import clear_cache
from scripts import load_state_masters as loader
from tests.api import test_subsidy_endpoints as endpoints_t
from tests.api.conftest import V1, Admin, _auth, _key

pytestmark = pytest.mark.db

viewer = endpoints_t.viewer
ON = dt.date(2026, 9, 15)
CALC = f"{V1}/subsidy/calculate"


def _dsn() -> str:
    return re.sub(r"^postgresql\+\w+://", "postgresql://", str(get_settings().database_url))


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def ap() -> AsyncIterator[None]:
    with psycopg.connect(_dsn()) as conn:
        existed = conn.execute("SELECT 1 FROM subsidy_scheme WHERE code = 'AP'").fetchone()
        loader.load(conn, effective_from=ON, states=("AP",))
        conn.commit()
    clear_cache()
    yield
    if existed is None:
        with psycopg.connect(_dsn()) as conn:
            sid = conn.execute("SELECT id FROM subsidy_scheme WHERE code = 'AP'").fetchone()[0]
            conn.execute("DELETE FROM unit_cost_cell WHERE matrix_id IN "
                         "(SELECT id FROM unit_cost_matrix WHERE scheme_id = %(s)s)", {"s": sid})
            conn.execute("DELETE FROM quantity_matrix_cell WHERE matrix_id IN "
                         "(SELECT id FROM quantity_matrix WHERE scheme_id = %(s)s)", {"s": sid})
            for table in (*loader.TABLES[::-1], "subsidy_system", "subsidy_stage_field",
                                                 "subsidy_stage_def"):
                conn.execute(f"DELETE FROM {table} WHERE scheme_id = %(s)s", {"s": sid})
            conn.execute("DELETE FROM subsidy_scheme WHERE id = %(s)s", {"s": sid})
            conn.commit()
    clear_cache()


def _drip(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "scheme": "AP", "system_type": "drip", "as_of": ON.isoformat(),
        "crops": [{"area": "1.02", "lateral_spacing": "5", "lines": [
            {"description": "Plain lateral 16 mm", "uom": "m", "rate": "8.43", "qty": "2310"}]}],
        "head_lines": [{"description": "Screen filter", "uom": "No.", "rate": "2337.76", "qty": "1"}],
        "guided_cost": "20000", "fittings_amount": "1000"}
    body.update(over)
    return {k: v for k, v in body.items() if v is not None}


async def test_ap_drip_calculates_from_the_portals_figures(
        client: httpx.AsyncClient, viewer: Admin, ap: None) -> None:
    h = await _auth(client, viewer.user)
    r = await client.post(CALC, json=_drip(), headers=h)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    blocks = data["total"]["blocks"]
    cost = Decimal("2337.76") + Decimal("8.43") * 2310 + 1000
    assert Decimal(blocks["cost_excl_gst"]) == cost and blocks["fittings"] == "1000.00"
    row = data["crops"][0]["categories"][0]
    assert row["subsidy"] == "18000.00", "90 % of the guided cost, the lower, to the rupee"
    state = Decimal(blocks["gst_paid_by_state"])
    assert state > 0
    assert Decimal(row["subsidy"]) + Decimal(row["farmer_share"]) + state \
        == Decimal(blocks["total_incl_gst"])
    assert data["masters"]["regular_matrix_id"] is None
    assert data["crops"][0]["jantri"]["regular"] == "20000.0000", "the guided cost (S-5)"


async def test_the_portal_fields_are_required_on_ap_drip_only(
        client: httpx.AsyncClient, viewer: Admin, ap: None) -> None:
    h = await _auth(client, viewer.user)
    for name in ("guided_cost", "fittings_amount"):
        r = await client.post(CALC, json=_drip(**{name: None}), headers=h)
        assert r.status_code == 422 and name in r.json()["error"]["fields"], r.text
    r = await client.post(CALC, json={**_drip(), "system_type": "sprinkler",
                                      "crops": [{"area": "1", "lateral_spacing": "1"}],
                                      "head_lines": [], "pipe_size_mm": 63}, headers=h)
    assert r.status_code in (404, 422), r.text
    if r.status_code == 422:
        assert "guided_cost" in r.json()["error"]["fields"], r.text
    r = await client.post(CALC, json=_drip(head_lines=[], crops=[{"area": "1", "lateral_spacing": "5"}]),
                          headers=h)
    assert r.status_code == 422, "no material (EC-8)"


async def test_ap_drip_is_ready_and_refuses_a_table(
        client: httpx.AsyncClient, viewer: Admin, ap: None,
        sessions: Callable[[], AsyncSession]) -> None:
    s = sessions()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) "
        "VALUES (CAST(:r AS uuid), 'masters', 'edit', 'global') ON CONFLICT DO NOTHING"),
        {"r": viewer.user.role_id})
    await s.commit()
    await s.close()
    h = await _auth(client, viewer.user)
    r = await client.get(f"{V1}/subsidy-schemes/AP", headers=h)
    assert r.status_code == 200, r.text
    drip = next(x for x in r.json()["data"]["systems"] if x["system_type"] == "drip")
    assert drip["missing"] == [], drip
    body = {"scheme": "AP", "system_type": "drip", "variant": "regular", "dimensionality": 1,
            "effective_from": (dt.date.today() + dt.timedelta(days=1)).isoformat(),
            "source": "FS-063 test",
            "unit_cost_cells": [{"lateral_spacing": None, "area_breakpoint": "1", "unit_cost": "1000"}]}
    r = await client.post(f"{V1}/subsidy-masters/unit-cost-matrices/matrices",
                          headers={**h, **_key()}, json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "system_has_no_table", r.text


async def test_the_loader_reruns_and_refuses_an_earlier_date(ap: None) -> None:
    """Rule 16 and code review F-3. Rolled back."""
    with psycopg.connect(_dsn()) as conn:
        try:
            again = loader.load(conn, effective_from=ON, states=("AP",))
            assert again.written == [] and len(again.skipped) >= 1, again.skipped
            later = ON + dt.timedelta(days=30)
            # an admin revision closes the open row and opens the next one
            conn.execute("UPDATE subsidy_parameter SET effective_to = %(d)s WHERE system_type = 'drip' "
                         "AND key = 'farmer_gst_fraction' AND effective_to IS NULL AND scheme_id = "
                         "(SELECT id FROM subsidy_scheme WHERE code = 'AP')", {"d": later})
            conn.execute("INSERT INTO subsidy_parameter (scheme_id, system_type, key, value, unit, "
                         "effective_from) SELECT id, 'drip', 'farmer_gst_fraction', 0.5, 'ratio', %(d)s "
                         "FROM subsidy_scheme WHERE code = 'AP'", {"d": later})
            with pytest.raises(SystemExit, match="subsidy_parameter"):
                loader.load(conn, effective_from=ON + dt.timedelta(days=10), states=("AP",))
        finally:
            conn.rollback()
