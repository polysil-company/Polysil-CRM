"""Migration 044 (FS-039): a new state's subsidy scheme, executed as the roles that
call it. Every test runs in the `db` fixture's transaction and is rolled back, so
linking GGRC to a made-up state here never leaves legacy mode for the rest of the
suite."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
import json
import pathlib
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13

pytestmark = [pytest.mark.db, pytest.mark.rls]

GRANTED = ["subsidy_scheme_create(text,text,uuid,text,text[])", "subsidy_scheme_update(text,text,boolean,uuid)",
           "subsidy_stage_rename(text,text,text)", "subsidy_scheme_for_lead(uuid)"]


def _module() -> object:
    path = pathlib.Path(__file__).resolve().parents[2] / "api/db/migrations/versions/044_subsidy_scheme_setup.py"
    spec = importlib.util.spec_from_file_location("m044", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass
class World:
    tag: str
    states: dict[str, str]       # letter -> territory id
    codes: dict[str, str]        # letter -> state code
    districts: dict[str, str]    # letter -> district id
    officer: str
    officer_b: str
    admin: str


async def _world(db: AsyncSession) -> World:
    tag = uuid.uuid4().hex[:6]
    states, codes, districts = {}, {}, {}
    for x in "xyz":
        codes[x] = (x + tag[:3]).upper()
        states[x] = str((await db.execute(text(
            "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
            {"n": f"m044_{x}_{tag}", "c": codes[x]})).scalar_one())
        districts[x] = str((await db.execute(text(
            "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
            {"n": f"m044_d{x}_{tag}", "p": states[x]})).scalar_one())
    office = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"m044_office_{tag}", "t": districts["x"]})).scalar_one())
    office_b = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"m044_office_b_{tag}", "t": districts["x"]})).scalar_one())
    return World(tag, states, codes, districts,
                 await m13._user(db, "field_officer", office, tag + "fo"),
                 await m13._user(db, "field_officer", office_b, tag + "fb"),
                 await m13._user(db, "admin_sales", office, tag + "ad"))


async def _lead(db: AsyncSession, district: str, owner: str) -> str:
    return str((await db.execute(text(
        "INSERT INTO lead (inquiry_no, inquiry_type, stage, mis_system_id, lead_source_id, farmer_name, mobile, "
        "territory_id, owner_user_id, owner_org_unit_id) VALUES (:no, 'subsidised', 'qualified', "
        "(SELECT id FROM mis_system WHERE code = 'drip'), (SELECT id FROM lead_source WHERE code = 'employee'), "
        "'Farmer', :mob, CAST(:t AS uuid), CAST(:u AS uuid), (SELECT org_unit_id FROM app_user WHERE id = CAST(:u AS uuid))) "
        "RETURNING id"),
        {"no": "POL-" + uuid.uuid4().hex[:12], "mob": "+9198" + f"{uuid.uuid4().int % 10**8:08d}",
         "t": district, "u": owner})).scalar_one())


_CREATE_SCHEME = "SELECT subsidy_scheme_create(:c, :n, CAST(:s AS uuid), :t, CAST(:sy AS text[]))"
_UPDATE = "SELECT subsidy_scheme_update(:c, :n, :a, CAST(:s AS uuid))"


async def _scheme(db: AsyncSession, w: World, code: str, state: str, template: str = "GGRC",
                  systems: list[str] | None = None) -> str:
    await m13._as(db, w.admin)
    sid = str((await db.execute(text(_CREATE_SCHEME), {
        "c": code, "n": f"Scheme {code}", "s": state, "t": template,
        "sy": systems or ["drip", "mini_sprinkler", "sprinkler"]})).scalar_one())
    await m13._as_owner(db)
    return sid


async def _link_ggrc(db: AsyncSession, w: World) -> None:
    """Leave legacy mode: GGRC to state x (rolled back with the test)."""
    await m13._as(db, w.admin)
    await db.execute(text(_UPDATE), {"c": "GGRC", "n": None, "a": None, "s": w.states["x"]})
    await m13._as_owner(db)


def _app_sql(regular: str = "gen_random_uuid()") -> str:
    return ("SELECT subsidy_application_create(CAST(:l AS uuid), 'small_farmer', 'Small farmer', 80, "
            f"CAST(:req AS jsonb), '{{}}'::jsonb, 100, 80, 20, 1, NULL, 'test', {regular}, gen_random_uuid(), "
            "DATE '2020-06-15', NULL, '2026-27', 'drip')")


@pytest.fixture(autouse=True)
async def _legacy_mode(db: AsyncSession) -> None:
    """Start every test in legacy mode, as CI's database is: GGRC alone, with no
    state. A seeded database has GGRC on Gujarat; the change is rolled back."""
    await db.execute(text("UPDATE subsidy_scheme SET state_territory_id = NULL WHERE code = 'GGRC'"))
    await db.execute(text("UPDATE subsidy_scheme SET is_active = false WHERE code <> 'GGRC'"))


# ── grants and shape ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("sig", GRANTED)
async def test_every_new_definer_is_pinned_granted_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE'), "
        "has_function_privilege('app_role', p.oid, 'EXECUTE') FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"),
        {"s": sig})).one()
    assert row[0] and "search_path=public, pg_temp" in (row[1] or []), row
    assert not row[2] and row[3], row


async def test_the_application_create_keeps_its_one_signature(db: AsyncSession) -> None:
    """Plan review B-2: a new parameter would have left the GGRC-only function live."""
    n = (await db.execute(text("SELECT count(*) FROM pg_proc WHERE proname = 'subsidy_application_create'"))).scalar_one()
    assert n == 1


async def test_a_lower_case_code_is_refused_by_the_table(db: AsyncSession) -> None:
    """Plan review B-1: citext's `~` ignores case, so the CHECK casts to text."""
    await m13._refused(db, "INSERT INTO subsidy_scheme (code, name) VALUES ('upmis', 'x')", {}, "23514")
    await m13._refused(db, "INSERT INTO subsidy_scheme (code, name) VALUES ('U', 'x')", {}, "23514")


# ── create ───────────────────────────────────────────────────────────────────

async def test_create_copies_settings_and_stages_and_no_figure(db: AsyncSession) -> None:
    w = await _world(db)
    await _link_ggrc(db, w)
    sid = await _scheme(db, w, "up" + w.tag[:4], w.states["y"])
    code = (await db.execute(text("SELECT code::text FROM subsidy_scheme WHERE id = :i"), {"i": sid})).scalar_one()
    assert code == ("UP" + w.tag[:4]).upper()
    for table, cols in (
        ("subsidy_system", "system_type, pipeline_variant, jantri_variant, quantity_source, has_head_unit, supports_group, "
                           "crop_count_max, rounded_blocks, rounded_lines, spacing_rule, seven_year_spacing_floor, "
                           "spacing_outside_table, formula_version, is_active"),
        ("subsidy_stage_def", "seq, code, name, is_active"),
    ):
        mine = (await db.execute(text(f"SELECT {cols} FROM {table} WHERE scheme_id = :i ORDER BY 1"), {"i": sid})).all()
        ggrc = (await db.execute(text(
            f"SELECT {cols} FROM {table} WHERE scheme_id = (SELECT id FROM subsidy_scheme WHERE code = 'GGRC') "
            f"{'AND is_active' if table == 'subsidy_system' else ''} ORDER BY 1"))).all()
        assert mine == ggrc and mine, table
    fields = (await db.execute(text(
        "SELECT d.code, f.field_key, f.label, f.type::text, f.pairs_with_key, f.is_active FROM subsidy_stage_field f "
        "JOIN subsidy_stage_def d ON d.id = f.stage_def_id WHERE f.scheme_id = :i ORDER BY 1, 2"), {"i": sid})).all()
    ggrc_fields = (await db.execute(text(
        "SELECT d.code, f.field_key, f.label, f.type::text, f.pairs_with_key, f.is_active FROM subsidy_stage_field f "
        "JOIN subsidy_stage_def d ON d.id = f.stage_def_id "
        "WHERE f.scheme_id = (SELECT id FROM subsidy_scheme WHERE code = 'GGRC') ORDER BY 1, 2"))).all()
    assert fields == ggrc_fields and any(f.pairs_with_key for f in fields)
    for table in ("subsidy_category", "unit_cost_matrix", "quantity_matrix", "subsidy_component_rate",
                  "crop_lateral_spacing", "subsidy_parameter"):
        n = (await db.execute(text(f"SELECT count(*) FROM {table} WHERE scheme_id = :i"), {"i": sid})).scalar_one()
        assert n == 0, f"{table}: a figure was copied"


async def test_create_copies_inactive_stages_so_every_pair_keeps_its_partner(db: AsyncSession) -> None:
    """Edge case 6: stage 17's dates pair with stage 16's amounts."""
    w = await _world(db)
    await _link_ggrc(db, w)
    tmpl = await _scheme(db, w, "T" + w.tag[:4], w.states["y"])
    await db.execute(text("UPDATE subsidy_stage_def SET is_active = false WHERE scheme_id = :i AND seq = 17"), {"i": tmpl})
    copy = await _scheme(db, w, "C" + w.tag[:4], w.states["z"], template="T" + w.tag[:4])
    dangling = (await db.execute(text(
        "SELECT count(*) FROM subsidy_stage_field f WHERE f.scheme_id = :i AND f.pairs_with_key IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM subsidy_stage_field g WHERE g.scheme_id = :i AND g.field_key = f.pairs_with_key)"),
        {"i": copy})).scalar_one()
    assert dangling == 0
    assert not (await db.execute(text("SELECT is_active FROM subsidy_stage_def WHERE scheme_id = :i AND seq = 17"),
                                 {"i": copy})).scalar_one()


async def test_create_refusals(db: AsyncSession) -> None:
    w = await _world(db)
    params = {"c": "R" + w.tag[:4], "n": "R", "s": w.states["y"], "t": "GGRC", "sy": ["drip"]}
    await m13._as(db, w.officer)
    await m13._refused(db, _CREATE_SCHEME, params, "42501")
    await m13._as(db, w.admin)
    await m13._refused(db, _CREATE_SCHEME, params, "SSCUL")      # GGRC has no state yet
    await m13._as_owner(db)
    await _link_ggrc(db, w)
    await m13._as(db, w.admin)
    await m13._refused(db, _CREATE_SCHEME, {**params, "s": w.districts["y"]}, "SSCST")
    await m13._refused(db, _CREATE_SCHEME, {**params, "t": "NOPE"}, "SSCTM")
    await m13._refused(db, _CREATE_SCHEME, {**params, "sy": ["drip", "orchard"]}, "SSCSY")
    await m13._refused(db, _CREATE_SCHEME, {**params, "sy": []}, "SSCSY")
    await m13._refused(db, _CREATE_SCHEME, {**params, "c": "ggrc"}, "23505")
    await m13._refused(db, _CREATE_SCHEME, {**params, "s": w.states["x"]}, "23505")   # GGRC holds x
    await db.execute(text(_CREATE_SCHEME), params)
    await m13._as_owner(db)
    await db.execute(text("UPDATE subsidy_stage_def SET is_active = false WHERE scheme_id = "
                          "(SELECT id FROM subsidy_scheme WHERE code = :c)"), {"c": params["c"]})
    await m13._as(db, w.admin)
    await m13._refused(db, _CREATE_SCHEME, {**params, "c": "S" + w.tag[:4], "s": w.states["z"], "t": params["c"]},
                       "SSCTM")
    await m13._as_owner(db)


# ── update and rename ────────────────────────────────────────────────────────

async def test_update_links_once_switches_off_and_guards_the_state(db: AsyncSession) -> None:
    w = await _world(db)
    await _link_ggrc(db, w)
    await m13._as(db, w.admin)
    await m13._refused(db, _UPDATE, {"c": "GGRC", "n": None, "a": None, "s": w.states["y"]}, "SSCSF")
    await m13._refused(db, _UPDATE, {"c": "NOPE", "n": "x", "a": None, "s": None}, "SSCNF")
    await m13._as_owner(db)
    first = "A" + w.tag[:4]
    await _scheme(db, w, first, w.states["y"])
    await m13._as(db, w.admin)
    await db.execute(text(_UPDATE), {"c": first, "n": " Renamed ", "a": False, "s": None})
    await m13._as_owner(db)
    await _scheme(db, w, "B" + w.tag[:4], w.states["y"])          # the state is free again
    await m13._as(db, w.admin)
    await m13._refused(db, _UPDATE, {"c": first, "n": None, "a": True, "s": None}, "23505")
    await m13._as_owner(db)
    assert (await db.execute(text("SELECT name FROM subsidy_scheme WHERE code = :c"), {"c": first})).scalar_one() == "Renamed"
    # an unlinked scheme cannot come back while linked ones are active
    await db.execute(text("INSERT INTO subsidy_scheme (code, name, is_active) VALUES (:c, 'old', false)"),
                     {"c": ("L" + w.tag[:4]).upper()})
    await m13._as(db, w.admin)
    await m13._refused(db, _UPDATE, {"c": "L" + w.tag[:4], "n": None, "a": True, "s": None}, "SSCUL")
    await m13._as(db, w.officer)
    await m13._refused(db, _UPDATE, {"c": first, "n": "x", "a": None, "s": None}, "42501")
    await m13._as_owner(db)


async def test_a_stage_is_renamed_and_nothing_else_moves(db: AsyncSession) -> None:
    w = await _world(db)
    await _link_ggrc(db, w)
    code = "N" + w.tag[:4]
    await _scheme(db, w, code, w.states["y"])
    await m13._as(db, w.admin)
    await db.execute(text("SELECT subsidy_stage_rename(:s, 'ggrc_query', 'UP query')"), {"s": code})
    await m13._refused(db, "SELECT subsidy_stage_rename(:s, 'nope', 'x')", {"s": code}, "SSCNF")
    await m13._as(db, w.officer)
    await m13._refused(db, "SELECT subsidy_stage_rename(:s, 'ggrc_query', 'x')", {"s": code}, "42501")
    await m13._as_owner(db)
    rows = (await db.execute(text(
        "SELECT s.code::text, d.name, d.seq FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id "
        "WHERE d.code = 'ggrc_query' AND s.code IN ('GGRC', :s) ORDER BY 1"), {"s": code})).all()
    assert [(r[1], r[2]) for r in rows] == [("GGRC query", 8), ("UP query", 8)]


# ── which scheme a lead takes ────────────────────────────────────────────────

async def _for(db: AsyncSession, lead: str, who: str) -> str | None:
    await m13._as(db, who)
    sid = (await db.execute(text("SELECT subsidy_scheme_for_lead(CAST(:l AS uuid))"), {"l": lead})).scalar_one()
    await m13._as_owner(db)
    return str(sid) if sid else None


async def test_a_lead_takes_its_states_scheme_and_legacy_mode_only_while_nothing_is_linked(db: AsyncSession) -> None:
    w = await _world(db)
    ggrc = str((await db.execute(text("SELECT id FROM subsidy_scheme WHERE code = 'GGRC'"))).scalar_one())
    lx = await _lead(db, w.districts["x"], w.officer)
    ly = await _lead(db, w.districts["y"], w.officer)
    lz = await _lead(db, w.districts["z"], w.officer)
    assert await _for(db, ly, w.officer) == ggrc, "legacy mode: the one scheme"
    await _link_ggrc(db, w)
    up = await _scheme(db, w, "U" + w.tag[:4], w.states["y"])
    assert await _for(db, lx, w.officer) == ggrc
    assert await _for(db, ly, w.officer) == up
    assert await _for(db, lz, w.officer) is None, "linked mode: an unmapped state has none"
    await m13._as(db, w.admin)
    await db.execute(text(_UPDATE), {"c": "U" + w.tag[:4], "n": None, "a": False, "s": None})
    await m13._as_owner(db)
    assert await _for(db, ly, w.officer) is None, "a switched-off scheme is not taken"
    await m13._as(db, w.officer_b)
    await m13._refused(db, "SELECT subsidy_scheme_for_lead(CAST(:l AS uuid))", {"l": lx}, "SAPNF")
    await m13._as_owner(db)


# ── the application create ───────────────────────────────────────────────────

async def test_the_application_takes_the_leads_scheme_and_refuses_another(db: AsyncSession) -> None:
    w = await _world(db)
    await _link_ggrc(db, w)
    code = "V" + w.tag[:4]
    up = await _scheme(db, w, code, w.states["y"])
    lead = await _lead(db, w.districts["y"], w.officer)
    await m13._as(db, w.officer)
    await m13._refused(db, _app_sql(), {"l": lead, "req": json.dumps({"scheme": "GGRC"})}, "SAPSX")
    await m13._refused(db, _app_sql(), {"l": lead, "req": json.dumps({})}, "SAPSX")   # the default is GGRC
    app = str((await db.execute(text(_app_sql()), {"l": lead, "req": json.dumps({"scheme": code.lower()})})).scalar_one())
    await m13._as_owner(db)
    row = (await db.execute(text(
        "SELECT a.scheme_id, d.seq, d.scheme_id FROM subsidy_application a JOIN subsidy_stage_def d ON d.id = a.current_stage_id "
        "WHERE a.id = :a"), {"a": app})).one()
    assert (str(row[0]), row[1], str(row[2])) == (up, 4, up)


async def test_a_matrix_of_another_scheme_is_refused(db: AsyncSession) -> None:
    w = await _world(db)
    await _link_ggrc(db, w)
    code = "W" + w.tag[:4]
    await _scheme(db, w, code, w.states["y"])
    ggrc_matrix = str((await db.execute(text(
        "INSERT INTO unit_cost_matrix (scheme_id, system_type, variant, dimensionality, effective_from, effective_to, source) "
        "SELECT id, 'drip', 'regular', 2, DATE '2001-01-01', DATE '2001-02-01', 'm044' FROM subsidy_scheme WHERE code = 'GGRC' RETURNING id"))).scalar_one())
    lead = await _lead(db, w.districts["y"], w.officer)
    await m13._as(db, w.officer)
    await m13._refused(db, _app_sql("CAST(:m AS uuid)"), {"l": lead, "m": ggrc_matrix,
                                                          "req": json.dumps({"scheme": code})}, "SAPSX")
    await m13._as_owner(db)


async def test_no_scheme_and_the_first_active_stage(db: AsyncSession) -> None:
    w = await _world(db)
    await _link_ggrc(db, w)
    code = "F" + w.tag[:4]
    sid = await _scheme(db, w, code, w.states["y"])
    await db.execute(text("UPDATE subsidy_stage_def SET is_active = false WHERE scheme_id = :i AND seq = 4"), {"i": sid})
    lead_z = await _lead(db, w.districts["z"], w.officer)
    lead_y = await _lead(db, w.districts["y"], w.officer)
    await m13._as(db, w.officer)
    await m13._refused(db, _app_sql(), {"l": lead_z, "req": json.dumps({"scheme": "GGRC"})}, "SAPSN")
    app = str((await db.execute(text(_app_sql()), {"l": lead_y, "req": json.dumps({"scheme": code})})).scalar_one())
    await m13._as_owner(db)
    seq = (await db.execute(text(
        "SELECT d.seq FROM subsidy_application a JOIN subsidy_stage_def d ON d.id = a.current_stage_id WHERE a.id = :a"),
        {"a": app})).scalar_one()
    assert seq == 5
    await db.execute(text("UPDATE subsidy_stage_def SET is_active = false WHERE scheme_id = :i"), {"i": sid})
    lead_y2 = await _lead(db, w.districts["y"], w.officer)
    await m13._as(db, w.officer)
    await m13._refused(db, _app_sql(), {"l": lead_y2, "req": json.dumps({"scheme": code})}, "SAPNG")
    await m13._as_owner(db)


# ── the GGRC backfill ────────────────────────────────────────────────────────

async def test_the_backfill_links_ggrc_to_the_live_gj_state_only_when_there_is_one(db: AsyncSession) -> None:
    # a seeded database has Gujarat already; hidden for this test, rolled back
    await db.execute(text("UPDATE territory SET deleted_at = now() WHERE level = 'state' AND code = 'GJ'"))
    backfill = _module().BACKFILL  # type: ignore[attr-defined]
    await db.execute(text(backfill))
    assert (await db.execute(text("SELECT state_territory_id FROM subsidy_scheme WHERE code = 'GGRC'"))).scalar_one() is None
    gj = str((await db.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', 'm044 Gujarat', 'GJ') RETURNING id"))).scalar_one())
    # two live GJ states cannot exist: uq_territory_level_code (007) is unique on live rows
    await db.execute(text(backfill))
    assert str((await db.execute(text("SELECT state_territory_id FROM subsidy_scheme WHERE code = 'GGRC'"))).scalar_one()) == gj
