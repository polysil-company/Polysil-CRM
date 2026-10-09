"""/subsidy-schemes, end to end over ASGI (FS-039).

The subsidy-application office (GGRC on the shop's state for the test), plus a
second state with its own scheme. The new scheme is filled through the FS-009a
master endpoints the admin uses, and at every step the readiness panel and a real
calculation must agree on what is missing (rule 7).
"""

# ruff: noqa: E501  (embedded SQL, kept on one line so each statement reads whole)

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.subsidy.sprinkler import required_rates
from api.schemas.subsidy import CalculateRequest
from api.services.clock import today_ist
from tests.api import test_order_concurrency as conc
from tests.api import test_subsidy_applications as subsidy
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = subsidy.shop
office = subsidy.office
fake_engine = subsidy.fake_engine
Sessions = Callable[[], AsyncSession]
SCHEMES = f"{V1}/subsidy-schemes"
MASTERS = f"{V1}/subsidy-masters"


@dataclass
class Other:
    """A second state with a district, and the code its scheme will take."""

    state: str
    district: str
    bare_state: str     # a third state that never gets a scheme
    bare_district: str
    code: str


@pytest_asyncio.fixture
async def other(office: subsidy.Office, sessions: Sessions) -> AsyncIterator[Other]:
    tag = uuid.uuid4().hex[:6].upper()
    s = sessions()
    ids = []
    for x in ("Y", "Z"):
        st = str((await s.execute(text(
            "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
            {"n": f"fs039_{x}_{tag}", "c": f"{x}{tag[:3]}"})).scalar_one())
        d = str((await s.execute(text(
            "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
            {"n": f"fs039_d{x}_{tag}", "p": st})).scalar_one())
        ids += [st, d]
    await s.commit()
    await s.close()
    code = f"UP{tag}"
    try:
        yield Other(ids[0], ids[1], ids[2], ids[3], code)
    finally:
        c = sessions()
        scheme = "(SELECT id FROM subsidy_scheme WHERE code IN (:c, :b))"
        apps = "(SELECT id FROM subsidy_application WHERE territory_id IN (CAST(:d1 AS uuid), CAST(:d2 AS uuid)))"
        for stmt in (
            f"DELETE FROM subsidy_stage_value WHERE entry_id IN (SELECT id FROM subsidy_stage_entry WHERE application_id IN {apps})",
            f"DELETE FROM subsidy_stage_entry WHERE application_id IN {apps}",
            f"DELETE FROM activity_event WHERE entity_type = 'subsidy_application' AND entity_id IN {apps}",
            "DELETE FROM subsidy_application WHERE territory_id IN (CAST(:d1 AS uuid), CAST(:d2 AS uuid))",
            "DELETE FROM subsidy_app_counter WHERE state_code IN (:y, :z)",
            f"DELETE FROM subsidy_stage_field WHERE scheme_id IN {scheme}",
            f"DELETE FROM subsidy_stage_def WHERE scheme_id IN {scheme}",
            f"DELETE FROM unit_cost_cell WHERE matrix_id IN (SELECT id FROM unit_cost_matrix WHERE scheme_id IN {scheme})",
            f"DELETE FROM unit_cost_matrix WHERE scheme_id IN {scheme}",
            f"DELETE FROM quantity_matrix_cell WHERE matrix_id IN (SELECT id FROM quantity_matrix WHERE scheme_id IN {scheme})",
            f"DELETE FROM quantity_matrix WHERE scheme_id IN {scheme}",
            f"DELETE FROM subsidy_category WHERE scheme_id IN {scheme}",
            f"DELETE FROM subsidy_parameter WHERE scheme_id IN {scheme}",
            f"DELETE FROM subsidy_component_rate WHERE scheme_id IN {scheme}",
            f"DELETE FROM crop_lateral_spacing WHERE scheme_id IN {scheme}",
            f"DELETE FROM subsidy_system WHERE scheme_id IN {scheme}",
            "DELETE FROM subsidy_scheme WHERE code IN (:c, :b)",
            "DELETE FROM lead WHERE territory_id IN (CAST(:d1 AS uuid), CAST(:d2 AS uuid))",
            "DELETE FROM territory WHERE id IN (CAST(:d1 AS uuid), CAST(:d2 AS uuid))",
            "DELETE FROM territory WHERE id IN (CAST(:s1 AS uuid), CAST(:s2 AS uuid))",
        ):
            await c.execute(text(stmt), {"c": code, "b": f"B{tag}", "d1": ids[1], "d2": ids[3],
                                         "s1": ids[0], "s2": ids[2], "y": f"Y{tag[:3]}", "z": f"Z{tag[:3]}"})
        await c.commit()
        await c.close()


async def _post(client: httpx.AsyncClient, h: dict[str, str], url: str, body: dict[str, Any],
                method: str = "POST") -> httpx.Response:
    return await client.request(method, url, headers={**h, **_key()}, json=body)


async def _detail(client: httpx.AsyncClient, h: dict[str, str], code: str) -> dict[str, Any]:
    r = await client.get(f"{SCHEMES}/{code}", headers=h)
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()["data"]
    return data


def _missing(detail: dict[str, Any], system: str) -> list[str]:
    return next(s["missing"] for s in detail["systems"] if s["system_type"] == system)


def _drip(scheme: str) -> dict[str, Any]:
    return {"scheme": scheme, "system_type": "drip", "installation_rate_per_ha": "2000",
            "crops": [{"crop": "Cotton", "area": "1.5", "lateral_spacing": "1.2",
                       "lines": [{"description": "16 mm lateral", "uom": "m", "rate": "12.50", "qty": "100"}]}],
            "head_lines": [{"description": "Screen filter", "uom": "No", "rate": "3500", "qty": "1"}]}


async def _calculate(client: httpx.AsyncClient, h: dict[str, str], scheme: str) -> httpx.Response:
    return await client.post(f"{V1}/subsidy/calculate", headers=h, json=_drip(scheme))


def _jantri(variant: str, dim: int = 2) -> dict[str, Any]:
    cells = [{"lateral_spacing": sp if dim == 2 else None, "area_breakpoint": a, "unit_cost": c}
             for sp in (["1.2", "1.5"] if dim == 2 else [None])
             for a, c in (("0.4", "120000"), ("1", "110000"), ("2", "100000"), ("5", "90000"))]
    return {"system_type": "drip", "variant": variant, "dimensionality": dim,
            "effective_from": today_ist().isoformat(), "source": "FS-039 test", "unit_cost_cells": cells}


SP_AREAS = ("1", "2", "3")
QTY_ROWS = ("pipe", "coupler", "riser", "pcn", "bend", "tee", "end_plug", "nozzle_plastic", "nozzle_brass")


def _table_1d(variant: str, dim: int = 1) -> dict[str, Any]:
    """A sprinkler unit cost table on the tabulated areas; `dim=2` is the wrong shape."""
    spacings = ["1.2"] if dim == 2 else [None]
    return {"system_type": "sprinkler", "variant": variant, "dimensionality": dim,
            "effective_from": today_ist().isoformat(), "source": "FS-039 test",
            "unit_cost_cells": [{"lateral_spacing": sp, "area_breakpoint": a, "unit_cost": "80000"}
                                for sp in spacings for a in SP_AREAS]}


def _quantities(skip: tuple[str, str] | None = None) -> dict[str, Any]:
    return {"system_type": "sprinkler", "effective_from": today_ist().isoformat(), "source": "FS-039 test",
            "quantity_cells": [{"component_code": c, "area_breakpoint": a, "qty": "10"}
                               for c in QTY_ROWS for a in SP_AREAS if (c, a) != skip]}


def _sprinkler(scheme: str) -> dict[str, Any]:
    return {"scheme": scheme, "system_type": "sprinkler", "nozzle": "plastic",
            "crops": [{"crop": "Cotton", "area": "1", "lateral_spacing": "1.2"}]}


async def _ggrc_rows(client: httpx.AsyncClient, h: dict[str, str], kind: str, system: str | None,
                     keep: tuple[str, ...]) -> list[dict[str, Any]]:
    r = await client.get(f"{MASTERS}/{kind}?scheme=GGRC", headers=h)
    assert r.status_code == 200, r.text
    rows = [row for row in r.json()["data"] if system is None or row.get("system_type") in (system, None)]
    return [{k: row[k] for k in keep if k in row} for row in rows]


# ── create, fill, agree ──────────────────────────────────────────────────────

async def test_a_new_state_is_set_up_and_readiness_and_the_engine_agree_at_every_step(
        client: httpx.AsyncClient, office: subsidy.Office, other: Other) -> None:
    admin = await subsidy._as(client, office, "admin_sales")
    r = await _post(client, admin, SCHEMES, {"code": other.code.lower(), "name": " UP Micro Irrigation ",
                                             "state_territory_id": other.state, "systems": ["drip", "sprinkler"]})
    assert r.status_code == 201, r.text
    d = r.json()["data"]
    assert d["code"] == other.code and d["name"] == "UP Micro Irrigation" and not d["ready"]
    assert [s["system_type"] for s in d["systems"]] == ["drip", "sprinkler"]
    assert d["stages"] and d["stages"][0]["seq"] == 4
    params = [f"parameters:{k}" for k in ("inspection_floor", "min_area_prorate", "max_area_scaling",
                                          "education_amount", "insurance_rate", "inspection_rate",
                                          "gst_material_half", "gst_service_half", "seven_year_area_min",
                                          "seven_year_area_max")]
    assert _missing(d, "drip") == ["unit_cost_matrix:regular", "unit_cost_matrix:seven_year", "categories",
                                   "crop_spacings", *params]
    assert _missing(d, "sprinkler") == ["unit_cost_matrix:regular", "unit_cost_matrix:seven_year", "categories",
                                        "crop_spacings", "quantity_matrix", *params]
    listed = {s["code"]: s for s in (await client.get(SCHEMES, headers=admin)).json()["data"]}
    assert not listed[other.code]["ready"] and listed[other.code]["state"]["id"] == other.state

    async def step(expect_first: str | None) -> None:
        missing = _missing(await _detail(client, admin, other.code), "drip")
        calc = await _calculate(client, admin, other.code)
        if expect_first is None:
            assert missing == [] and calc.status_code == 200, (missing, calc.text)
        else:
            assert missing[0] == expect_first and calc.status_code in (404, 422), (missing, calc.text)

    await step("unit_cost_matrix:regular")
    for variant in ("regular", "seven_year"):
        r = await _post(client, admin, f"{MASTERS}/unit-cost-matrices/matrices", {"scheme": other.code, **_jantri(variant)})
        assert r.status_code == 201, r.text
    await step("categories")
    cats = await _ggrc_rows(client, admin, "categories", "drip",
                            ("system_type", "code", "name", "pct", "variant", "per_ha_cap", "gsdma_pct", "sort_order"))
    assert cats, "GGRC's categories are seeded by 009"
    r = await _post(client, admin, f"{MASTERS}/categories/revisions",
                    {"scheme": other.code, "effective_from": today_ist().isoformat(), "rows": cats})
    assert r.status_code == 201, r.text
    await step("crop_spacings")
    r = await _post(client, admin, f"{MASTERS}/crop-spacings/revisions", {
        "scheme": other.code, "effective_from": today_ist().isoformat(),
        "rows": [{"crop": "Cotton", "standard_spacing": "1.2"}, {"crop": "Castor", "standard_spacing": "1.5"}]})
    assert r.status_code == 201, r.text
    await step("parameters:inspection_floor")
    rows = await _ggrc_rows(client, admin, "parameters", None, ("system_type", "key", "value", "unit"))
    held_back = [row for row in rows if row["key"] == "seven_year_area_max"]
    assert held_back, "GGRC's parameters are seeded by 009"
    r = await _post(client, admin, f"{MASTERS}/parameters/revisions", {
        "scheme": other.code, "effective_from": today_ist().isoformat(),
        "rows": [row for row in rows if row["key"] != "seven_year_area_max"]})
    assert r.status_code == 201, r.text
    await step("parameters:seven_year_area_max")
    assert _missing(await _detail(client, admin, other.code), "drip") == ["parameters:seven_year_area_max"]
    r = await _post(client, admin, f"{MASTERS}/parameters/revisions", {
        "scheme": other.code, "effective_from": today_ist().isoformat(), "rows": held_back})
    assert r.status_code == 201, r.text
    await step(None)
    calc = await _calculate(client, admin, other.code.lower())
    assert calc.status_code == 200 and calc.json()["data"]["scheme"] == other.code, calc.text

    # sprinkler: rates are listed only once a quantity table names the areas
    sp = _missing(await _detail(client, admin, other.code), "sprinkler")
    # only drip's categories were copied; the crop spacings are the scheme's, so filled
    assert sp == ["unit_cost_matrix:regular", "unit_cost_matrix:seven_year", "categories", "quantity_matrix"], sp

    # sprinkler to ready: once a quantity table names the areas, each rate is listed (review F-3)
    for variant in ("regular", "seven_year"):
        r = await _post(client, admin, f"{MASTERS}/unit-cost-matrices/matrices", {"scheme": other.code, **_table_1d(variant)})
        assert r.status_code == 201, r.text
    sp_cats = await _ggrc_rows(client, admin, "categories", "sprinkler",
                               ("system_type", "code", "name", "pct", "variant", "per_ha_cap", "gsdma_pct", "sort_order"))
    r = await _post(client, admin, f"{MASTERS}/categories/revisions",
                    {"scheme": other.code, "effective_from": today_ist().isoformat(), "rows": sp_cats})
    assert r.status_code == 201, r.text
    r = await _post(client, admin, f"{MASTERS}/quantity-matrices/matrices", {"scheme": other.code, **_quantities()})
    assert r.status_code == 201, r.text
    want = []
    for code, size, nozzle in required_rates(tuple(Decimal(a) for a in SP_AREAS), Decimal("2.0")):
        tail = size if size is not None else nozzle
        want.append(f"component_rate:{code}" + (f":{tail}" if tail is not None else ""))
    assert _missing(await _detail(client, admin, other.code), "sprinkler") == want
    calc = await client.post(f"{V1}/subsidy/calculate", headers=admin, json=_sprinkler(other.code))
    assert calc.status_code == 422 and "no rate for" in calc.text, calc.text
    rates = await _ggrc_rows(client, admin, "component-rates", "sprinkler",
                             ("system_type", "component_code", "description", "uom", "pipe_size_mm", "nozzle",
                              "rate", "source_cell"))
    r = await _post(client, admin, f"{MASTERS}/component-rates/revisions",
                    {"scheme": other.code, "effective_from": today_ist().isoformat(), "rows": rates})
    assert r.status_code == 201, r.text
    d = await _detail(client, admin, other.code)
    assert d["ready"] and all(s["ready"] for s in d["systems"]), d
    calc = await client.post(f"{V1}/subsidy/calculate", headers=admin, json=_sprinkler(other.code))
    assert calc.status_code == 200, calc.text

    # switch-off after a calculation has warmed the cache (review F-4); never ready when off (F-5)
    assert (await _calculate(client, admin, other.code)).status_code == 200
    r = await _post(client, admin, f"{SCHEMES}/{other.code}", {"is_active": False}, "PATCH")
    assert r.status_code == 200 and r.json()["data"]["ready"] is False, r.text
    assert all(s["ready"] for s in r.json()["data"]["systems"])
    calc = await _calculate(client, admin, other.code)
    assert calc.status_code == 422 and "scheme" in subsidy._fields(calc), calc.text


async def test_tables_with_gaps_or_the_wrong_shape_are_listed_and_refused(
        client: httpx.AsyncClient, office: subsidy.Office, other: Other) -> None:
    """Code review F-1: a ragged 2-D table and a quantity table without a full row
    were a KeyError, a 500, while the panel said nothing."""
    admin = await subsidy._as(client, office, "admin_sales")
    r = await _post(client, admin, SCHEMES, {"code": other.code, "name": "UP", "state_territory_id": other.state,
                                             "systems": ["drip", "sprinkler"]})
    assert r.status_code == 201, r.text
    ragged = _jantri("regular")
    ragged["unit_cost_cells"] = [c for c in ragged["unit_cost_cells"]
                                 if not (c["lateral_spacing"] == "1.5" and c["area_breakpoint"] == "5")]
    for body in (ragged, _jantri("seven_year"), _table_1d("regular"), _table_1d("seven_year", dim=2)):
        r = await _post(client, admin, f"{MASTERS}/unit-cost-matrices/matrices", {"scheme": other.code, **body})
        assert r.status_code == 201, r.text
    r = await _post(client, admin, f"{MASTERS}/quantity-matrices/matrices",
                    {"scheme": other.code, **_quantities(skip=("riser", "3"))})
    assert r.status_code == 201, r.text
    d = await _detail(client, admin, other.code)
    assert _missing(d, "drip")[0] == "unit_cost_matrix:regular"
    sp = _missing(d, "sprinkler")
    assert sp[0] == "unit_cost_matrix:seven_year" and "quantity_matrix:riser" in sp, sp
    calc = await _calculate(client, admin, other.code)
    assert calc.status_code == 404 and "missing cells" in calc.text, calc.text

    # the quantity gap on its own reaches the engine's refusal, on a second scheme
    bare = "B" + other.code[2:]
    r = await _post(client, admin, SCHEMES, {"code": bare, "name": "Bare", "state_territory_id": other.bare_state,
                                             "systems": ["sprinkler"]})
    assert r.status_code == 201, r.text
    for variant in ("regular", "seven_year"):
        r = await _post(client, admin, f"{MASTERS}/unit-cost-matrices/matrices", {"scheme": bare, **_table_1d(variant)})
        assert r.status_code == 201, r.text
    cats = await _ggrc_rows(client, admin, "categories", "sprinkler",
                            ("system_type", "code", "name", "pct", "variant", "per_ha_cap", "gsdma_pct", "sort_order"))
    for kind, rows in (("categories", cats), ("crop-spacings", [{"crop": "Cotton", "standard_spacing": "1.2"}])):
        r = await _post(client, admin, f"{MASTERS}/{kind}/revisions",
                        {"scheme": bare, "effective_from": today_ist().isoformat(), "rows": rows})
        assert r.status_code == 201, r.text
    r = await _post(client, admin, f"{MASTERS}/quantity-matrices/matrices", {"scheme": bare, **_quantities(skip=("riser", "3"))})
    assert r.status_code == 201, r.text
    assert "quantity_matrix:riser" in _missing(await _detail(client, admin, bare), "sprinkler")
    calc = await client.post(f"{V1}/subsidy/calculate", headers=admin, json=_sprinkler(bare))
    assert calc.status_code == 404 and "riser" in calc.text, calc.text


# ── refusals ─────────────────────────────────────────────────────────────────

async def test_create_and_update_refusals(client: httpx.AsyncClient, office: subsidy.Office, other: Other,
                                          sessions: Sessions) -> None:
    admin = await subsidy._as(client, office, "admin_sales")
    fo = await subsidy._as(client, office, "field_officer")
    body = {"code": other.code, "name": "UP", "state_territory_id": other.state}
    assert (await _post(client, fo, SCHEMES, body)).status_code == 403
    r = await _post(client, admin, SCHEMES, {**body, "code": "ggrc"})
    assert r.status_code == 409 and subsidy._code(r) == "code_taken", r.text
    r = await _post(client, admin, SCHEMES, {**body, "state_territory_id": office.shop.state})
    assert r.status_code == 409 and subsidy._code(r) == "state_has_scheme", r.text
    r = await _post(client, admin, SCHEMES, {**body, "state_territory_id": other.district})
    assert r.status_code == 422 and "state_territory_id" in subsidy._fields(r), r.text
    r = await _post(client, admin, SCHEMES, {**body, "template": "NOPE"})
    assert r.status_code == 422 and "template" in subsidy._fields(r), r.text
    r = await _post(client, admin, SCHEMES, {**body, "code": "a b"})
    assert r.status_code == 422, r.text
    # legacy mode: with GGRC unlinked, no state's scheme can be added
    s = sessions()
    await s.execute(text("UPDATE subsidy_scheme SET state_territory_id = NULL WHERE code = 'GGRC'"))
    await s.commit()
    await s.close()
    r = await _post(client, admin, SCHEMES, body)
    assert r.status_code == 409 and subsidy._code(r) == "unlinked_scheme_exists", r.text
    r = await _post(client, admin, f"{SCHEMES}/GGRC", {"state_territory_id": office.shop.state}, "PATCH")
    assert r.status_code == 200 and r.json()["data"]["state"]["id"] == office.shop.state, r.text
    r = await _post(client, admin, f"{SCHEMES}/GGRC", {"state_territory_id": other.state}, "PATCH")
    assert r.status_code == 409 and subsidy._code(r) == "state_fixed", r.text
    assert (await _post(client, admin, SCHEMES, body)).status_code == 201
    r = await _post(client, admin, f"{SCHEMES}/NOPE", {"name": "x"}, "PATCH")
    assert r.status_code == 404, r.text
    r = await _post(client, admin, f"{SCHEMES}/{other.code}", {}, "PATCH")
    assert r.status_code == 422, r.text


# ── switch-off, rename, the lead's scheme ────────────────────────────────────

async def test_switch_off_stops_calculations_and_a_stage_is_renamed(
        client: httpx.AsyncClient, office: subsidy.Office, other: Other) -> None:
    admin = await subsidy._as(client, office, "admin_sales")
    r = await _post(client, admin, SCHEMES, {"code": other.code, "name": "UP", "state_territory_id": other.state})
    assert r.status_code == 201, r.text
    r = await _post(client, admin, f"{SCHEMES}/{other.code}/stages/ggrc_query", {"name": "UP query"}, "PATCH")
    assert r.status_code == 200 and r.json()["data"] == {"seq": 8, "code": "ggrc_query", "name": "UP query",
                                                         "is_active": True}, r.text
    r = await _post(client, admin, f"{SCHEMES}/{other.code}/stages/nope", {"name": "x"}, "PATCH")
    assert r.status_code == 404, r.text
    r = await _post(client, admin, f"{SCHEMES}/{other.code}", {"is_active": False}, "PATCH")
    assert r.status_code == 200 and r.json()["data"]["is_active"] is False, r.text
    calc = await _calculate(client, admin, other.code)
    assert calc.status_code == 422 and "scheme" in subsidy._fields(calc), calc.text


async def test_an_application_takes_its_leads_scheme(
        client: httpx.AsyncClient, office: subsidy.Office, other: Other,
        fake_engine: list[CalculateRequest], sessions: Sessions) -> None:
    admin = await subsidy._as(client, office, "admin_sales")
    r = await _post(client, admin, SCHEMES, {"code": other.code, "name": "UP", "state_territory_id": other.state})
    assert r.status_code == 201, r.text
    fo = await subsidy._as(client, office, "field_officer")
    # the officer's office covers the shop's district; leads elsewhere are its own, so it sees them
    leads = {}
    for name, district in (("y", other.district), ("z", other.bare_district), ("shop", office.shop.district)):
        r = await client.post(f"{V1}/leads", headers={**fo, **_key()}, json={
            "farmer_name": "Ramesh", "mobile": "98" + f"{uuid.uuid4().int % 10**8:08d}", "territory_id": district,
            "inquiry_type": "subsidised", "mis_system": "drip", "village": "Agra"})
        assert r.status_code == 201, r.text
        leads[name] = r.json()["data"]["id"]
        for stage in ("contacted", "qualified"):
            assert (await client.post(f"{V1}/leads/{leads[name]}/transition", json={"to_stage": stage},
                                      headers={**fo, **_key()})).status_code == 200
    r = await client.get(f"{SCHEMES}/for-lead/{leads['y']}", headers=fo)
    assert r.status_code == 200 and r.json()["data"]["code"] == other.code and not r.json()["data"]["ready"], r.text
    r = await client.get(f"{SCHEMES}/for-lead/{leads['shop']}", headers=fo)
    assert r.status_code == 200 and r.json()["data"]["code"] == "GGRC", r.text
    r = await client.get(f"{SCHEMES}/for-lead/{leads['z']}", headers=fo)
    assert r.status_code == 422 and subsidy._code(r) == "no_scheme_for_state", r.text

    def body(lead: str, scheme: str | None) -> dict[str, Any]:
        calc = subsidy._calc(office)
        if scheme is not None:
            calc["scheme"] = scheme
        return {"lead_id": lead, "category_code": "small_farmer", "calculation": calc}

    r = await _post(client, fo, subsidy.APPS, body(leads["y"], None))          # the GGRC default
    assert r.status_code == 422 and "calculation.scheme" in subsidy._fields(r), r.text
    r = await _post(client, fo, subsidy.APPS, body(leads["z"], "GGRC"))
    assert r.status_code == 422 and subsidy._code(r) == "no_scheme_for_state", r.text
    r = await _post(client, fo, subsidy.APPS, body(leads["y"], other.code.lower()))
    assert r.status_code == 201, r.text
    app = r.json()["data"]
    assert app["scheme"] == other.code
    # F-6: the stage report labels a stage with GGRC's name when both schemes hold it;
    # "A UP intake" sorts first, so a plain min(name) would pick it
    r = await _post(client, fo, subsidy.APPS, body(leads["shop"], "GGRC"))
    assert r.status_code == 201, r.text
    r = await _post(client, admin, f"{SCHEMES}/{other.code}/stages/application_in_process", {"name": "A UP intake"}, "PATCH")
    assert r.status_code == 200, r.text
    rows = (await client.get(f"{V1}/subsidy-reports/stages", headers=admin)).json()["data"]
    assert next(x for x in rows if x["seq"] == 4)["name"] == "Application in process", rows
    r = await client.get(f"{subsidy.APPS}/{app['id']}/pims.xlsx", headers=fo)
    assert r.status_code == 422 and subsidy._code(r) == "pims_not_for_scheme", r.text
    listed = {s["code"]: s for s in (await client.get(SCHEMES, headers=admin)).json()["data"]}
    assert listed[other.code]["applications"] == 1


async def test_an_application_waits_on_a_switch_off_and_then_finds_no_scheme(
        client: httpx.AsyncClient, office: subsidy.Office, other: Other, sessions: Sessions) -> None:
    """Code review F-2: the switch-off holds the state and the scheme; the create
    waits on them, then resolves again and is refused. Without the locks it would
    land on a scheme that was switched off under it."""
    admin = await subsidy._as(client, office, "admin_sales")
    r = await _post(client, admin, SCHEMES, {"code": other.code, "name": "UP", "state_territory_id": other.state})
    assert r.status_code == 201, r.text
    fo = await subsidy._as(client, office, "field_officer")
    r = await client.post(f"{V1}/leads", headers={**fo, **_key()}, json={
        "farmer_name": "Ramesh", "mobile": "98" + f"{uuid.uuid4().int % 10**8:08d}", "territory_id": other.district,
        "inquiry_type": "subsidised", "mis_system": "drip", "village": "Agra"})
    assert r.status_code == 201, r.text
    lead = r.json()["data"]["id"]
    for stage in ("contacted", "qualified"):
        assert (await client.post(f"{V1}/leads/{lead}/transition", json={"to_stage": stage},
                                  headers={**fo, **_key()})).status_code == 200

    async def switch_off(s: AsyncSession) -> Any:
        return (await s.execute(text("SELECT subsidy_scheme_update(:c, NULL, false, NULL)"),
                                {"c": other.code})).scalar_one()

    async def apply(s: AsyncSession) -> Any:
        return (await s.execute(text(
            "SELECT subsidy_application_create(CAST(:l AS uuid), 'small_farmer', 'Small farmer', 80, "
            "CAST(:req AS jsonb), '{}'::jsonb, 100, 80, 20, 1, NULL, 'test', gen_random_uuid(), gen_random_uuid(), "
            "DATE '2020-06-15', NULL, '2026-27', 'drip')"),
            {"l": lead, "req": json.dumps({"scheme": other.code})})).scalar_one()

    got, waited = await conc._race(sessions, (office.shop.ids["admin_sales"], switch_off),
                                   (office.shop.ids["field_officer"], apply))
    assert waited, "the create did not wait on the switch-off: the race was not a race"
    assert "ok" in got[0] and got[1] == {"error": "SAPSN"}, got
