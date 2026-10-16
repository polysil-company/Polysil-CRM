"""FS-056 and FS-063 through the API: the AP, CG, RJ and UP schemes loaded by
`scripts/load_state_masters.py` calculate to the workbooks' figures, list their
inputs, and are ready."""

# ruff: noqa: E501  (SQL and request bodies inline)

from __future__ import annotations

import datetime as dt
import re
from collections.abc import AsyncIterator
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
import psycopg
import pytest
import pytest_asyncio

from api.config import get_settings
from api.services.subsidy import clear_cache
from scripts import load_state_masters as loader
from tests.api import test_subsidy_endpoints as endpoints_t
from tests.api.conftest import V1, Admin, _auth
from tests.domain import state_masters as sm

pytestmark = [pytest.mark.db, sm.needs_state_samples]

viewer = endpoints_t.viewer
ON = dt.date(2026, 9, 15)
TABLES = ("subsidy_component_rate", "quantity_matrix_cell", "quantity_matrix", "unit_cost_cell",
          "unit_cost_matrix", "subsidy_parameter", "subsidy_category", "subsidy_system",
          "subsidy_stage_field", "subsidy_stage_def", "subsidy_scheme")


def _dsn() -> str:
    return re.sub(r"^postgresql\+\w+://", "postgresql://", str(get_settings().database_url))


@pytest_asyncio.fixture(scope="module")
async def states() -> AsyncIterator[None]:
    """Loaded once; removed after only when this module created them."""
    with psycopg.connect(_dsn()) as conn:
        before = {r[0] for r in conn.execute(
            "SELECT code FROM subsidy_scheme WHERE code IN ('AP', 'CG', 'RJ', 'UP')").fetchall()}
        loader.load(conn, effective_from=ON)
        conn.commit()
    clear_cache()
    yield
    created = sorted({"AP", "CG", "RJ", "UP"} - before)
    if created:
        with psycopg.connect(_dsn()) as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM subsidy_scheme WHERE code = ANY(%(c)s)", {"c": created}).fetchall()]
            conn.execute("DELETE FROM unit_cost_cell WHERE matrix_id IN "
                         "(SELECT id FROM unit_cost_matrix WHERE scheme_id = ANY(%(i)s))", {"i": ids})
            conn.execute("DELETE FROM quantity_matrix_cell WHERE matrix_id IN "
                         "(SELECT id FROM quantity_matrix WHERE scheme_id = ANY(%(i)s))", {"i": ids})
            for table in TABLES:
                if table in ("unit_cost_cell", "quantity_matrix_cell"):
                    continue
                col = "id" if table == "subsidy_scheme" else "scheme_id"
                conn.execute(f"DELETE FROM {table} WHERE {col} = ANY(%(i)s)", {"i": ids})
            conn.commit()
    clear_cache()


def _body(key: str) -> dict[str, Any]:
    scheme, system = key.split("/")
    inp = sm.SAMPLES[key]["example"]["input"]
    body: dict[str, Any] = {
        "scheme": scheme, "system_type": system, "as_of": ON.isoformat(),
        "crops": [{"crop": c["crop"], "area": c["area"], "lateral_spacing": c["lateral_spacing"] or "1",
                   "lines": [{k: ln[k] for k in ("description", "uom", "rate", "qty")}
                             for ln in c["lines"]]} for c in inp["crops"]],
        "head_lines": [{k: ln[k] for k in ("description", "uom", "rate", "qty")}
                       for ln in inp["head_lines"]],
        "installation_rate_per_ha": inp["installation_rate_per_ha"]}
    for name in ("nozzle", "pipe_size_mm", "spacing_label", "group_total_area", "guided_cost",
                 "fittings_amount"):
        if inp.get(name) is not None:
            body[name] = inp[name]
    if inp["sump_rate_per_ha"] not in ("0", "0.00"):
        body["sump"] = {"rate_per_ha": inp["sump_rate_per_ha"]}
    for name in ("hydrocyclone_m3", "gravel_filter_m3"):
        if inp[name] not in ("0", "0.00"):
            body[name] = inp[name]
    for name in ("head_unit_existing", "pvc_existing"):
        if inp[name]:
            body[name] = True
    return body


@pytest.mark.parametrize("key", sorted(sm.PUBLIC))
async def test_a_state_workbook_reproduces_through_the_endpoint(
        client: httpx.AsyncClient, viewer: Admin, states: None, key: str) -> None:
    h = await _auth(client, viewer.user)
    r = await client.post(f"{V1}/subsidy/calculate", json=_body(key), headers=h)
    assert r.status_code == 200, r.text
    ex = sm.SAMPLES[key]["example"]
    row = next(c for c in r.json()["data"]["crops"][0]["categories"] if c["code"] == ex["category"])
    want = {k: Decimal(v).quantize(Decimal("0.01"), ROUND_HALF_UP) for k, v in ex["expected"].items()}
    assert Decimal(row["subsidy"]) == want["subsidy"], key
    share = Decimal(row["farmer_share"])
    if ex.get("rupees"):
        share = share.quantize(Decimal(1), ROUND_HALF_UP)    # the portal prints rupees (FS-063)
    assert share == want["farmer_share"], key


async def test_the_config_lists_each_systems_inputs(
        client: httpx.AsyncClient, viewer: Admin, states: None) -> None:
    h = await _auth(client, viewer.user)
    r = await client.get(f"{V1}/subsidy/config", params={"scheme": "CG", "as_of": ON.isoformat()},
                         headers=h)
    assert r.status_code == 200, r.text
    systems = {s["system_type"]: s for s in r.json()["data"]["systems"]}
    assert set(systems) == {"drip", "sprinkler"}, "CG has no mini sprinkler"
    assert systems["drip"]["inputs"] == ["spacing_label"] and systems["drip"]["spacing_labels"]
    assert systems["sprinkler"]["inputs"] == ["pipe_size_mm"]
    assert systems["drip"]["cap_mode"] == "incl_gst" and systems["drip"]["pipeline"] == "gst_inclusive"
    r = await client.get(f"{V1}/subsidy/config", params={"scheme": "RJ", "as_of": ON.isoformat()},
                         headers=h)
    rj = {s["system_type"]: s for s in r.json()["data"]["systems"]}
    assert "pvc_existing" in rj["drip"]["inputs"]
    r = await client.get(f"{V1}/subsidy/config", params={"scheme": "AP", "as_of": ON.isoformat()},
                         headers=h)
    ap = {s["system_type"]: s for s in r.json()["data"]["systems"]}
    assert set(ap) == {"drip", "sprinkler"}
    assert ap["drip"]["inputs"] == ["guided_cost", "fittings_amount"]
    assert ap["drip"]["pipeline"] == "portal_manual" and ap["drip"]["cap_mode"] == "excl_gst"
    assert ap["sprinkler"]["inputs"] == ["pipe_size_mm"] and ap["sprinkler"]["cap_mode"] == "excl_gst"


async def test_a_missing_state_input_names_its_field(
        client: httpx.AsyncClient, viewer: Admin, states: None) -> None:
    h = await _auth(client, viewer.user)
    body = {k: v for k, v in _body("UP/sprinkler").items() if k != "pipe_size_mm"}
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 422 and "pipe_size_mm" in r.json()["error"]["fields"], r.text
    body = {k: v for k, v in _body("CG/drip").items() if k != "spacing_label"}
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 422 and "spacing_label" in r.json()["error"]["fields"], r.text
    # FS-063: the portal's figures on AP drip only
    for name in ("guided_cost", "fittings_amount"):
        body = {k: v for k, v in _body("AP/drip").items() if k != name}
        r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
        assert r.status_code == 422 and name in r.json()["error"]["fields"], r.text
        r = await client.post(f"{V1}/subsidy/calculate", json={**_body("CG/drip"), name: "100"},
                              headers=h)
        assert r.status_code == 422 and name in r.json()["error"]["fields"], r.text


async def test_ap_splits_the_gst_and_the_three_parts_make_the_total(
        client: httpx.AsyncClient, viewer: Admin, states: None) -> None:
    """FS-063 rule 3: subsidy + farmer share + the state's GST = the total incl GST."""
    h = await _auth(client, viewer.user)
    for key in ("AP/sprinkler", "AP/drip"):
        r = await client.post(f"{V1}/subsidy/calculate", json=_body(key), headers=h)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        blocks = data["total"]["blocks"]
        state = Decimal(blocks["gst_paid_by_state"])
        assert state > 0, key
        for row in data["crops"][0]["categories"]:
            assert (Decimal(row["subsidy"]) + Decimal(row["farmer_share"]) + state
                    == Decimal(blocks["total_incl_gst"])), (key, row)
    drip = (await client.post(f"{V1}/subsidy/calculate", json=_body("AP/drip"), headers=h)).json()["data"]
    assert drip["masters"]["regular_matrix_id"] is None
    cg = (await client.post(f"{V1}/subsidy/calculate", json=_body("CG/drip"), headers=h)).json()["data"]
    assert cg["total"]["blocks"]["gst_paid_by_state"] == "0.00"


async def test_the_loaded_schemes_are_ready(
        client: httpx.AsyncClient, viewer: Admin, states: None) -> None:
    h = await _auth(client, viewer.user)
    for code in ("AP", "CG", "RJ", "UP"):
        r = await client.get(f"{V1}/subsidy-schemes/{code}", headers=h)
        assert r.status_code == 200, r.text
        for system in r.json()["data"]["systems"]:
            assert system["missing"] == [], (code, system)


async def test_the_loader_revises_with_a_later_date(states: None) -> None:
    """Code review F-1: a later date ends the tables in force and adds new ones;
    the same date again writes nothing. Rolled back."""
    later = ON + dt.timedelta(days=30)
    with psycopg.connect(_dsn()) as conn:
        try:
            first = loader.load(conn, effective_from=later, states=("UP",))
            assert first.written and not first.skipped
            again = loader.load(conn, effective_from=later, states=("UP",))
            assert again.skipped and not again.written
            ranges = conn.execute(
                "SELECT m.effective_from, m.effective_to FROM unit_cost_matrix m "
                "JOIN subsidy_scheme s ON s.id = m.scheme_id WHERE s.code = 'UP' "
                "AND m.system_type = 'drip' AND m.variant = 'regular' ORDER BY 1").fetchall()
            assert ranges[-2:] == [(ON, later), (later, None)], ranges
            # FS-063: a system with no table re-runs and revises the same way
            ap = loader.load(conn, effective_from=later, states=("AP",))
            assert len(ap.written) == 2 and not ap.skipped, ap.written
            assert loader.load(conn, effective_from=later, states=("AP",)).written == []
        finally:
            conn.rollback()


def test_a_six_place_parameter_passes_the_revision_schema() -> None:
    """Code review F-4: UP's 0.00169 insurance rate, which four places refused."""
    from api.schemas.subsidy_follow_ups import ParameterRow
    row = ParameterRow(system_type="drip", key="insurance_rate", value=Decimal("0.00169"),
                       unit="ratio")
    assert row.value == Decimal("0.00169")


async def test_ap_drip_takes_no_unit_cost_table(
        client: httpx.AsyncClient, viewer: Admin, states: None, sessions: Any) -> None:
    """FS-063 plan review S-4: a table for a system that reads none is refused, not stored."""
    from sqlalchemy import text

    from tests.api.conftest import _key
    s = sessions()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) "
        "VALUES (CAST(:r AS uuid), 'masters', 'edit', 'global') ON CONFLICT DO NOTHING"),
        {"r": viewer.user.role_id})
    await s.commit()
    await s.close()
    h = await _auth(client, viewer.user)
    body = {"scheme": "AP", "system_type": "drip", "variant": "regular", "dimensionality": 1,
            "effective_from": (dt.date.today() + dt.timedelta(days=1)).isoformat(),
            "source": "FS-063 test",
            "unit_cost_cells": [{"lateral_spacing": None, "area_breakpoint": "1", "unit_cost": "1000"}]}
    r = await client.post(f"{V1}/subsidy-masters/unit-cost-matrices/matrices",
                          headers={**h, **_key()}, json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "system_has_no_table", r.text
