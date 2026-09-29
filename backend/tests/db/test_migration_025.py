"""Migration 025 (FS-009): subsidy applications, executed as the roles that call it.
A coded state, one district, two sibling offices each with a field officer, so
every rule has its negative case."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13

pytestmark = [pytest.mark.db, pytest.mark.rls]

GRANTED = ["subsidy_application_visible(uuid)",
           "subsidy_application_create(uuid,text,text,numeric,jsonb,jsonb,numeric,numeric,numeric,numeric,numeric,text,uuid,uuid,date,text,text,text)",
           "subsidy_stage_record(uuid,text,date,jsonb,text)", "subsidy_application_cancel(uuid,text)",
           "subsidy_document_lock(uuid)"]
INTERNAL = ["subsidy_allocate_no(text,text)", "subsidy_event(uuid,text,jsonb)"]


@dataclass
class World:
    code: str
    district: str
    officer: str
    officer_b: str
    coordinator: str


async def _world(db: AsyncSession) -> World:
    tag = uuid.uuid4().hex[:8]
    code = "Q" + tag[:3].upper()
    state = str((await db.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": f"m025_state_{tag}", "c": code})).scalar_one())
    district = str((await db.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
        {"n": f"m025_district_{tag}", "p": state})).scalar_one())
    a, b = [str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"m025_office_{x}_{tag}", "t": district})).scalar_one()) for x in "ab"]
    officer = await m13._user(db, "field_officer", a, tag + "a")
    officer_b = await m13._user(db, "field_officer", b, tag + "b")
    coordinator = await m13._user(db, "state_coordinator", b, tag + "c")
    await db.execute(text("INSERT INTO user_territory (user_id, territory_id) VALUES (:u, :t)"),
                     {"u": coordinator, "t": state})
    return World(code, district, officer, officer_b, coordinator)


async def _lead(db: AsyncSession, w: World, owner: str, stage: str = "qualified") -> str:
    return str((await db.execute(text(
        "INSERT INTO lead (inquiry_no, inquiry_type, stage, mis_system_id, lead_source_id, farmer_name, mobile, "
        "territory_id, owner_user_id, owner_org_unit_id) VALUES (:no, 'subsidised', CAST(:st AS lead_stage), "
        "(SELECT id FROM mis_system WHERE code = 'drip'), (SELECT id FROM lead_source WHERE code = 'employee'), "
        "'Farmer', :mob, CAST(:t AS uuid), CAST(:u AS uuid), (SELECT org_unit_id FROM app_user WHERE id = CAST(:u AS uuid))) "
        "RETURNING id"),
        {"no": "POL-" + uuid.uuid4().hex[:12], "st": stage, "mob": "+9198" + f"{uuid.uuid4().int % 10**8:08d}",
         "t": w.district, "u": owner})).scalar_one())


_CREATE = ("SELECT subsidy_application_create(CAST(:l AS uuid), 'small_farmer', 'Small farmer', 80, "
           "CAST(:req AS jsonb), '{}'::jsonb, 100, 80, 20, 1, NULL, 'test', gen_random_uuid(), gen_random_uuid(), "
           "DATE '2020-06-15', NULL, '2026-27', 'drip')")


async def _create(db: AsyncSession, lead: str, by: str) -> str:
    await m13._as(db, by)
    app = str((await db.execute(text(_CREATE), {"l": lead, "req": json.dumps({"crops": []})})).scalar_one())
    await m13._as_owner(db)
    return app


# ── grants ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sig", GRANTED + INTERNAL)
async def test_every_new_definer_is_pinned_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
    assert row[0], f"{sig} is SECURITY DEFINER"
    assert "search_path=public, pg_temp" in (row[1] or []), row[1]
    assert not row[2], f"{sig} is not PUBLIC-executable"


@pytest.mark.parametrize("sig", INTERNAL)
async def test_the_internal_functions_are_not_granted(db: AsyncSession, sig: str) -> None:
    assert not (await db.execute(text("SELECT has_function_privilege('app_role', :s, 'EXECUTE')"),
                                 {"s": sig})).scalar_one()


async def test_app_role_writes_the_application_only_through_the_definers(db: AsyncSession) -> None:
    for table in ("subsidy_application", "subsidy_stage_entry", "subsidy_stage_value", "subsidy_app_counter",
                  "subsidy_stage_def", "subsidy_stage_field", "subsidy_document_type"):
        for verb in ("INSERT", "UPDATE", "DELETE"):
            held = (await db.execute(text("SELECT has_table_privilege('app_role', :t, :v)"),
                                     {"t": table, "v": verb})).scalar_one()
            assert not held, (table, verb)
    for column, allowed in (("deleted_at", True), ("deleted_by", True), ("storage_key", False),
                            ("application_id", False), ("uploaded_by", False)):
        held = (await db.execute(text(
            "SELECT has_column_privilege('app_role', 'subsidy_document', :c, 'UPDATE')"), {"c": column})).scalar_one()
        assert held == allowed, column


# ── the definers, as the caller ──────────────────────────────────────────────

async def test_a_state_coordinator_forwards_without_leads_edit(db: AsyncSession) -> None:
    """lead_state_code() gates on leads.create; the definer must not call it."""
    w = await _world(db)
    lead = await _lead(db, w, w.officer)
    app = await _create(db, lead, w.coordinator)
    row = (await db.execute(text(
        "SELECT a.application_no, a.owner_user_id, l.stage::text FROM subsidy_application a JOIN lead l ON l.id = a.lead_id "
        "WHERE a.id = CAST(:a AS uuid)"), {"a": app})).one()
    assert row[0] == f"SA/{w.code}/2026-27/00001" and str(row[1]) == w.officer and row[2] == "won"


async def test_an_out_of_scope_caller_meets_not_found(db: AsyncSession) -> None:
    w = await _world(db)
    lead = await _lead(db, w, w.officer)
    await m13._as(db, w.officer_b)
    await m13._refused(db, _CREATE, {"l": lead, "req": "{}"}, "SAPNF")
    await m13._as_owner(db)
    app = await _create(db, lead, w.officer)
    await m13._as(db, w.officer_b)
    await m13._refused(db, "SELECT subsidy_stage_record(CAST(:a AS uuid), 'technical_in_process', current_date, '{}', NULL)",
                       {"a": app}, "SAPAN")
    await m13._refused(db, "SELECT subsidy_application_cancel(CAST(:a AS uuid), 'x')", {"a": app}, "SAPAN")
    await m13._refused(db, "SELECT * FROM subsidy_document_lock(CAST(:a AS uuid))", {"a": app}, "SAPAN")
    seen = (await db.execute(text(
        "SELECT count(*) FROM activity_event WHERE entity_type = 'subsidy_application' AND entity_id = CAST(:a AS uuid)"),
        {"a": app})).scalar_one()
    assert seen == 0, "another office's officer sees none of its events"
    entries = (await db.execute(text(
        "SELECT count(*) FROM subsidy_stage_entry WHERE application_id = CAST(:a AS uuid)"), {"a": app})).scalar_one()
    assert entries == 0
    await m13._as(db, w.officer)
    seen = (await db.execute(text(
        "SELECT count(*) FROM activity_event WHERE entity_type = 'subsidy_application' AND entity_id = CAST(:a AS uuid)"),
        {"a": app})).scalar_one()
    assert seen == 1


async def test_a_lead_holds_one_live_application(db: AsyncSession) -> None:
    w = await _world(db)
    lead = await _lead(db, w, w.officer)
    app = await _create(db, lead, w.officer)
    await m13._as(db, w.officer)
    await m13._refused(db, _CREATE, {"l": lead, "req": "{}"}, "SAPDU")
    await db.execute(text("SELECT subsidy_application_cancel(CAST(:a AS uuid), ' Duplicate ')"), {"a": app})
    again = str((await db.execute(text(_CREATE), {"l": lead, "req": "{}"})).scalar_one())
    assert again != app
    await m13._as_owner(db)
    reason = (await db.execute(text("SELECT cancel_reason FROM subsidy_application WHERE id = CAST(:a AS uuid)"),
                               {"a": app})).scalar_one()
    assert reason == "Duplicate"


@pytest.mark.parametrize("stage,state", [("new", "SAPST"), ("contacted", "SAPST")])
async def test_a_lead_that_is_not_ready_is_refused(db: AsyncSession, stage: str, state: str) -> None:
    w = await _world(db)
    lead = await _lead(db, w, w.officer, stage=stage)
    await m13._as(db, w.officer)
    await m13._refused(db, _CREATE, {"l": lead, "req": "{}"}, state)


async def test_a_bad_value_writes_no_entry(db: AsyncSession) -> None:
    w = await _world(db)
    app = await _create(db, await _lead(db, w, w.officer), w.officer)
    await m13._as(db, w.officer)
    sql = "SELECT subsidy_stage_record(CAST(:a AS uuid), :s, current_date, CAST(:v AS jsonb), 'r')"
    for stage, values, state in (("technical_in_process", {"tech_received": "not a date"}, "SAPFV"),
                                 ("farmer_share", {"farmer_share_amt": "1.001"}, "SAPFV"),
                                 ("farmer_share", {"farmer_share_amt": "-5"}, "SAPFV"),
                                 ("farmer_share", {"farmer_share_amt": "NaN"}, "SAPFV"),
                                 ("farmer_share", {"farmer_share_amt": "10000000000000"}, "SAPFV"),
                                 ("farmer_share", {"tech_received": "2020-01-01"}, "SAPFK")):
        message = await m13._refused(db, sql, {"a": app, "s": stage, "v": json.dumps(values)}, state)
        assert next(iter(values)) in message
    count = (await db.execute(text("SELECT count(*) FROM subsidy_stage_entry WHERE application_id = CAST(:a AS uuid)"),
                              {"a": app})).scalar_one()
    assert count == 1, "only the create's entry"


# ── documents ────────────────────────────────────────────────────────────────

_DOC = ("INSERT INTO subsidy_document (application_id, document_type_id, storage_key, content_type, size_bytes, "
        "sha256, uploaded_by) VALUES (CAST(:a AS uuid), (SELECT id FROM subsidy_document_type ORDER BY sort_order LIMIT 1), "
        "'k', 'image/jpeg', 1, :h, CAST(:u AS uuid))")


async def test_a_document_is_the_callers_and_never_on_a_cancelled_application(db: AsyncSession) -> None:
    w = await _world(db)
    app = await _create(db, await _lead(db, w, w.officer), w.officer)
    await m13._as(db, w.officer)
    await m13._refused(db, _DOC, {"a": app, "h": "a" * 64, "u": w.officer_b}, "42501")
    await db.execute(text(_DOC), {"a": app, "h": "b" * 64, "u": w.officer})
    await m13._as(db, w.officer_b)
    await m13._refused(db, _DOC, {"a": app, "h": "c" * 64, "u": w.officer_b}, "42501")
    assert (await db.execute(text("SELECT count(*) FROM subsidy_document WHERE application_id = CAST(:a AS uuid)"),
                             {"a": app})).scalar_one() == 0, "out of scope: not even the officer's file shows"
    await m13._as(db, w.officer)
    await db.execute(text("SELECT subsidy_application_cancel(CAST(:a AS uuid), 'x')"), {"a": app})
    await m13._refused(db, _DOC, {"a": app, "h": "d" * 64, "u": w.officer}, "42501")
    status, files = (await db.execute(text("SELECT * FROM subsidy_document_lock(CAST(:a AS uuid))"), {"a": app})).one()
    assert (status, files) == ("cancelled", 1)


# ── code review (Fable, on the build) ────────────────────────────────────────

async def test_the_table_refuses_a_nan_amount(db: AsyncSession) -> None:
    """F-4: numeric NaN sorts above every number, so `>= 0` alone admits it."""
    w = await _world(db)
    app = await _create(db, await _lead(db, w, w.officer), w.officer)
    entry = (await db.execute(text("SELECT id FROM subsidy_stage_entry WHERE application_id = CAST(:a AS uuid)"),
                              {"a": app})).scalar_one()
    await m13._refused(db, "INSERT INTO subsidy_stage_value (entry_id, field_key, value_amount) "
                           "VALUES (CAST(:e AS uuid), 'pfms_amt', 'NaN')", {"e": str(entry)}, "23514")


async def test_a_field_key_is_unique_across_its_scheme(db: AsyncSession) -> None:
    """F-7: values and closure key on field_key across all of an application's entries."""
    await m13._refused(db, "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type) "
                           "SELECT d.scheme_id, d.id, 'pfms_amt', 'Again', 'amount' FROM subsidy_stage_def d "
                           "WHERE d.code = 'farmer_share'", {}, "23505")
    await m13._refused(db, "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type) "
                           "SELECT gen_random_uuid(), d.id, 'new_key', 'Elsewhere', 'date' FROM subsidy_stage_def d "
                           "WHERE d.code = 'farmer_share'", {}, "23503")
