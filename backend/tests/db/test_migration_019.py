"""Migration 019 (FS-015): complaints, executed as the roles that call it. Two sibling
offices in one district, a seeded user per role that matters, and a dealer under
a distributor, so every rule has its negative case."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import complaints as domain
from tests.db import test_migration_013 as m13

pytestmark = [pytest.mark.db, pytest.mark.rls]

GRANTED = ["complaint_refusal(uuid,text)", "complaint_assignees(uuid)", "complaint_submit(uuid)",
           "complaint_check(uuid,text,text,complaint_severity,uuid,text)",
           "complaint_qc(uuid,text,text,date,date,date,text)", "complaint_cancel(uuid,text)",
           "complaint_sla_policy_set(complaint_severity,uuid,integer,integer,boolean,date)"]
INTERNAL = ["complaint_visible(uuid)", "complaint_has_checker(uuid)", "complaint_notify(uuid,text,text)",
            "complaint_event(uuid,text,jsonb)", "complaint_allocate_no(text,text)",
            "complaint_sla_policy_at(uuid,complaint_severity,date)", "complaint_line_guard()",
            "complaint_raiser_guard()", "complaint_header_guard()"]


@dataclass
class World:
    state_code: str
    district: str
    a: str
    b: str
    officer: str
    dm: str
    officer_b: str
    dm_b: str
    sm: str
    rm: str
    admin: str
    md: str
    qc: str
    support: str
    dealer_user: str
    dealer: str
    product: str
    product2: str


async def _world(db: AsyncSession) -> World:
    tag = uuid.uuid4().hex[:8]
    code = "C" + tag[:2].upper()
    state = str((await db.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": f"m019_state_{tag}", "c": code})).scalar_one())
    district = str((await db.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
        {"n": f"m019_district_{tag}", "p": state})).scalar_one())
    a, b = [str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"m019_office_{x}_{tag}", "t": district})).scalar_one()) for x in "ab"]
    u = {}
    for role, office, key in (("field_officer", a, "officer"), ("district_manager", a, "dm"),
                              ("field_officer", b, "officer_b"), ("district_manager", b, "dm_b"),
                              ("state_manager", a, "sm"), ("regional_manager", a, "rm"),
                              ("admin_sales", a, "admin"), ("md_ceo", a, "md"),
                              ("qc_manager", a, "qc"), ("support", a, "support")):
        u[key] = await m13._user(db, role, office, tag + key)
    distributor = str((await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('distributor', :c, 'M019 Distributor', :t, 'distributor') RETURNING id"),
        {"c": f"M19D{tag}", "t": district})).scalar_one())
    dealer = str((await db.execute(text(
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, price_tier) "
        "VALUES (:p, 'dealer', :c, 'M019 Dealer', :t, 'dealer') RETURNING id"),
        {"p": distributor, "c": f"M19R{tag}", "t": district})).scalar_one())
    dealer_user = str((await db.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "SELECT 'partner_user', :m, 'M019 Dealer', r.id, CAST(:p AS uuid) FROM role r "
        "WHERE r.code = 'dealer' RETURNING id"),
        {"m": "9196" + f"{uuid.uuid4().int % 10**8:08d}", "p": dealer})).scalar_one())
    products = [str(r[0]) for r in (await db.execute(text(
        "SELECT id FROM product WHERE deleted_at IS NULL ORDER BY id LIMIT 2"))).all()]
    if len(products) < 2:
        for i in range(2 - len(products)):
            products.append(str((await db.execute(text(
                "INSERT INTO product (description, product_category_id, quotation_category, uom_id) "
                "SELECT CAST(:d AS citext), (SELECT id FROM product_category ORDER BY sort_order LIMIT 1), "
                "'field', (SELECT id FROM uom LIMIT 1) RETURNING id"),
                {"d": f"M019 PIPE {tag} {i}"})).scalar_one()))
    return World(code, district, a, b, u["officer"], u["dm"], u["officer_b"], u["dm_b"], u["sm"],
                 u["rm"], u["admin"], u["md"], u["qc"], u["support"], dealer_user, dealer,
                 products[0], products[1])


async def _complaint(db: AsyncSession, w: World, *, raiser: str | None = None, owner: str | None = "officer",
                     office: str | None = None, partner: str | None = None, severity: str = "medium",
                     dc: str | None = "DC-1", supply: dt.date | None = dt.date(2026, 7, 1),
                     defective: str = "5", lead: str | None = None) -> str:
    """A draft with one line, as the table owner."""
    owner_id = getattr(w, owner) if owner else None
    cid = str((await db.execute(text(
        "INSERT INTO complaint (complaint_type_id, severity, description, contact_name, contact_mobile, "
        "territory_id, state_code, partner_id, lead_id, owner_user_id, owner_org_unit_id, raised_by, dc_no, supply_date) "
        "VALUES ((SELECT id FROM complaint_type WHERE code = 'dripline'), CAST(:sev AS complaint_severity), "
        "'Laterals cracking', 'Kiritbhai Shah', '+919812345678', CAST(:t AS uuid), :sc, CAST(:p AS uuid), "
        "CAST(:l AS uuid), CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:r AS uuid), :dc, :sd) RETURNING id"),
        {"sev": severity, "t": w.district, "sc": w.state_code, "p": partner, "l": lead, "o": owner_id,
         "ou": office or w.a, "r": raiser or owner_id or w.support, "dc": dc, "sd": supply})).scalar_one())
    await db.execute(text(
        "INSERT INTO complaint_line (complaint_id, line_no, product_id, supplied_qty, defective_qty) "
        "VALUES (CAST(:c AS uuid), 1, CAST(:p AS uuid), 100, :d)"), {"c": cid, "p": w.product, "d": defective})
    return cid


async def _call(db: AsyncSession, who: str, sql: str, params: dict[str, Any]) -> Any:
    await m13._as(db, who)
    result = (await db.execute(text(sql), params)).scalar_one_or_none()
    await m13._as_owner(db)
    return result


async def _refused(db: AsyncSession, who: str, sql: str, params: dict[str, Any], state: str) -> str:
    await m13._as(db, who)
    message = await m13._refused(db, sql, params, state)
    await m13._as_owner(db)
    return message


async def _row(db: AsyncSession, cid: str) -> Any:
    return (await db.execute(text("SELECT * FROM complaint WHERE id = CAST(:c AS uuid)"), {"c": cid})).one()


SUBMIT = "SELECT complaint_submit(CAST(:c AS uuid))"
CHECK = ("SELECT complaint_check(CAST(:c AS uuid), :d, 'looked at it', CAST(:s AS complaint_severity), "
         "CAST(:o AS uuid), :n)")
QC = "SELECT complaint_qc(CAST(:c AS uuid), :v, 'tested', NULL, NULL, NULL, :n)"
CANCEL = "SELECT complaint_cancel(CAST(:c AS uuid), 'raised by mistake')"
REFUSAL = "SELECT complaint_refusal(CAST(:c AS uuid), :a)"


def _check(cid: str, decision: str = "approve", severity: str | None = None, owner: str | None = None,
           note: str | None = None) -> dict[str, Any]:
    return {"c": cid, "d": decision, "s": severity, "o": owner, "n": note}


# ── the surface ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sig", GRANTED + INTERNAL)
async def test_every_new_definer_is_pinned_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
    if sig not in ("complaint_raiser_guard()", "complaint_header_guard()"):  # invoker triggers, on purpose
        assert row[0], f"{sig} is SECURITY DEFINER"
    assert "search_path=public, pg_temp" in (row[1] or []), row[1]
    assert not row[2], f"{sig} is not PUBLIC-executable"


@pytest.mark.parametrize("sig", INTERNAL)
async def test_the_internal_functions_are_not_granted(db: AsyncSession, sig: str) -> None:
    assert not (await db.execute(text("SELECT has_function_privilege('app_role', :s, 'EXECUTE')"),
                                 {"s": sig})).scalar_one()


async def test_app_role_cannot_write_the_status_the_number_or_the_targets(db: AsyncSession) -> None:
    for column in ("status", "complaint_no", "submit_count", "responded_at", "resolved_at",
                   "response_due_at", "owner_user_id", "raised_by"):
        held = (await db.execute(text(
            "SELECT has_column_privilege('app_role', 'complaint', :c, 'UPDATE')"), {"c": column})).scalar_one()
        assert not held, column
    for table in ("complaint_counter", "complaint_decision", "complaint_decision_note"):
        held = (await db.execute(text("SELECT has_table_privilege('app_role', :t, 'INSERT')"),
                                 {"t": table})).scalar_one()
        assert not held, table


async def test_the_raiser_is_the_caller(db: AsyncSession) -> None:
    w = await _world(db)
    await m13._as(db, w.officer)
    await m13._refused(db,
        "INSERT INTO complaint (complaint_type_id, description, contact_name, contact_mobile, territory_id, "
        "state_code, owner_user_id, owner_org_unit_id, raised_by) VALUES ((SELECT id FROM complaint_type "
        "WHERE code = 'dripline'), 'x', 'x', '+919812345678', CAST(:t AS uuid), 'GJ', CAST(:o AS uuid), "
        "CAST(:ou AS uuid), CAST(:r AS uuid))",
        {"t": w.district, "o": w.officer, "ou": w.a, "r": w.dm}, "42501")
    await m13._as_owner(db)


# ── working time: the SQL twin agrees with the domain ────────────────────────

@pytest.mark.parametrize("hours", [1, 4, 8, 9, 18, 27, 45])
@pytest.mark.parametrize("start", [
    dt.datetime(2026, 10, 3, 18, 0, tzinfo=domain.IST), dt.datetime(2026, 10, 4, 11, 0, tzinfo=domain.IST),
    dt.datetime(2026, 10, 3, 18, 30, tzinfo=domain.IST), dt.datetime(2026, 10, 5, 7, 0, tzinfo=domain.IST),
    dt.datetime(2026, 10, 5, 14, 30, tzinfo=domain.IST), dt.datetime(2026, 10, 3, 23, 30, tzinfo=dt.UTC),
    dt.datetime(2026, 10, 2, 17, 0, tzinfo=domain.IST), dt.datetime(2027, 3, 31, 23, 45, tzinfo=dt.UTC),
])
async def test_sql_working_hours_equal_the_domains(db: AsyncSession, start: dt.datetime, hours: int) -> None:
    sql = (await db.execute(text("SELECT complaint_add_working_hours(:s, :h)"),
                            {"s": start, "h": hours})).scalar_one()
    # the holidays the SQL reads (048), so a seeded one never splits the twins
    holidays = frozenset((await db.execute(text("SELECT day FROM holiday"))).scalars())
    assert sql == domain.add_working_hours(start, hours, holidays)


# ── the flow ─────────────────────────────────────────────────────────────────

async def test_submit_numbers_it_sets_the_targets_and_a_return_keeps_both(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w, severity="high")
    await _call(db, w.officer, SUBMIT, {"c": cid})
    c = await _row(db, cid)
    assert c.status == "submitted" and c.submit_count == 1
    assert c.complaint_no.startswith("Poly/Comp./") and c.complaint_no.endswith(f"/{w.state_code}/01")
    assert c.response_due_at == domain.add_working_hours(c.first_submitted_at, 4)
    assert c.resolution_due_at == domain.add_working_hours(c.first_submitted_at, 18)
    await _call(db, w.dm, CHECK, _check(cid, "return"))
    c2 = await _row(db, cid)
    assert c2.status == "draft" and c2.responded_at is not None
    await _call(db, w.officer, SUBMIT, {"c": cid})
    c3 = await _row(db, cid)
    assert (c3.complaint_no, c3.first_submitted_at, c3.resolution_due_at, c3.submit_count) == (
        c.complaint_no, c.first_submitted_at, c.resolution_due_at, 2), "a resubmit restarts nothing"
    second = await _complaint(db, w)
    await _call(db, w.officer, SUBMIT, {"c": second})
    assert (await _row(db, second)).complaint_no.endswith("/02")


async def test_the_full_walk_and_its_decision_rows(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w)
    await _call(db, w.officer, SUBMIT, {"c": cid})
    await _call(db, w.dm, CHECK, _check(cid, severity="high", note="dealer is upset"))
    c = await _row(db, cid)
    assert c.status == "under_qc" and c.severity == "high"
    first = c.first_submitted_at
    assert c.resolution_due_at == domain.add_working_hours(first, 18), "recomputed from the first submit"
    await _call(db, w.qc, QC, {"c": cid, "v": "approved", "n": None})
    c = await _row(db, cid)
    assert c.status == "qc_approved" and c.resolved_at is not None
    rows = (await db.execute(text(
        "SELECT stage, decision FROM complaint_decision WHERE complaint_id = CAST(:c AS uuid) ORDER BY decided_at"),
        {"c": cid})).all()
    assert [tuple(r) for r in rows] == [("check", "approve"), ("qc", "approved")]
    kinds = [r[0] for r in (await db.execute(text(
        "SELECT kind FROM activity_event WHERE entity_id = CAST(:c AS uuid) ORDER BY occurred_at, id"),
        {"c": cid})).all()]
    assert set(kinds) == {"complaint.submitted", "complaint.approved", "complaint.qc_approved"}


async def test_who_may_check(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w)
    await _call(db, w.officer, SUBMIT, {"c": cid})
    for who, why in ((w.officer, "not_a_manager"), (w.qc, "not_a_manager"), (w.support, "not_a_manager"),
                     (w.dm_b, "not_visible"), (w.dealer_user, "not_visible")):
        assert await _call(db, who, REFUSAL, {"c": cid, "a": "check"}) == why, who
    for who in (w.dm, w.sm, w.rm, w.admin, w.md):
        assert await _call(db, who, REFUSAL, {"c": cid, "a": "check"}) is None, who
    await _refused(db, w.qc, CHECK, _check(cid), "CMPRF")


async def test_a_regional_manager_checks_with_approve_alone(db: AsyncSession) -> None:
    """Edge case B-2: the RM holds view and approve, not edit."""
    w = await _world(db)
    cid = await _complaint(db, w)
    await _call(db, w.officer, SUBMIT, {"c": cid})
    await _call(db, w.rm, CHECK, _check(cid))
    assert (await _row(db, cid)).status == "under_qc"


async def test_the_reference_level_for_owners_up_the_line(db: AsyncSession) -> None:
    """B-4 and EC-1: a manager's complaint goes above them; a top manager's to
    another top manager; a functional owner's to the District Manager."""
    w = await _world(db)
    dm_owned = await _complaint(db, w, owner="dm")
    await _call(db, w.dm, SUBMIT, {"c": dm_owned})
    assert await _call(db, w.sm, REFUSAL, {"c": dm_owned, "a": "check"}) is None
    assert await _call(db, w.dm, REFUSAL, {"c": dm_owned, "a": "check"}) == "self"
    admin_owned = await _complaint(db, w, owner="admin")
    await _call(db, w.admin, SUBMIT, {"c": admin_owned})
    assert await _call(db, w.md, REFUSAL, {"c": admin_owned, "a": "check"}) is None
    assert await _call(db, w.rm, REFUSAL, {"c": admin_owned, "a": "check"}) == "not_above"
    support_owned = await _complaint(db, w, owner="support")
    await _call(db, w.support, SUBMIT, {"c": support_owned})
    assert await _call(db, w.dm, REFUSAL, {"c": support_owned, "a": "check"}) is None


async def test_nobody_decides_their_own(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w, owner="qc")
    await _call(db, w.qc, SUBMIT, {"c": cid})
    await _call(db, w.dm, CHECK, _check(cid))
    assert await _call(db, w.qc, REFUSAL, {"c": cid, "a": "qc"}) == "self"
    await _refused(db, w.qc, QC, {"c": cid, "v": "approved", "n": None}, "CMPRF")


async def test_submit_refuses_what_is_missing_and_what_nobody_can_check(db: AsyncSession) -> None:
    w = await _world(db)
    missing = await _complaint(db, w, dc=None, supply=None)
    message = await _refused(db, w.officer, SUBMIT, {"c": missing}, "CMPMS")
    assert "dc_no" in message and "supply_date" in message
    nothing = await _complaint(db, w, defective="0")
    await _refused(db, w.officer, SUBMIT, {"c": nothing}, "CMPZD")
    lonely = await _complaint(db, w, owner="admin")
    await db.execute(text("UPDATE app_user SET is_active = false WHERE role_id IN "
                          "(SELECT id FROM role WHERE code IN ('admin_sales', 'md_ceo')) AND id <> CAST(:a AS uuid)"),
                     {"a": w.admin})
    await _refused(db, w.admin, SUBMIT, {"c": lonely}, "CMPNC")


async def test_a_decision_on_a_complaint_that_moved_on_is_status_changed(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w)
    await _call(db, w.officer, SUBMIT, {"c": cid})
    await _call(db, w.dm, CHECK, _check(cid))
    await _refused(db, w.sm, CHECK, _check(cid), "CMPSC")
    await _refused(db, w.officer, CANCEL, {"c": cid}, "CMPSC")


async def test_a_submitted_complaints_lines_are_frozen(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w)
    await _call(db, w.officer, SUBMIT, {"c": cid})
    await m13._refused(db, "DELETE FROM complaint_line WHERE complaint_id = CAST(:c AS uuid)", {"c": cid}, "CMPND")


async def test_cancel_records_its_reason(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w)
    await _call(db, w.officer, CANCEL, {"c": cid})
    assert (await _row(db, cid)).status == "cancelled"
    reason = (await db.execute(text(
        "SELECT remark FROM complaint_decision WHERE complaint_id = CAST(:c AS uuid) AND stage = 'cancel'"),
        {"c": cid})).scalar_one()
    assert reason == "raised by mistake"


# ── owners and assignees ─────────────────────────────────────────────────────

async def test_the_check_may_assign_an_owner_from_its_own_list(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w, owner=None, raiser=w.support)
    await _call(db, w.support, SUBMIT, {"c": cid})
    await m13._as(db, w.dm)
    listed = {str(r[0]) for r in (await db.execute(text(
        "SELECT id FROM complaint_assignees(CAST(:c AS uuid))"), {"c": cid})).all()}
    await m13._as_owner(db)
    assert w.officer in listed and w.officer_b not in listed, "the checker's office tree only"
    await _refused(db, w.dm, CHECK, _check(cid, owner=w.officer_b), "CMPAS")
    await _call(db, w.dm, CHECK, _check(cid, owner=w.officer))
    assert str((await _row(db, cid)).owner_user_id) == w.officer


# ── what a dealer sees ───────────────────────────────────────────────────────

async def test_the_internal_note_never_reaches_a_dealer(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w, partner=w.dealer)
    await _call(db, w.officer, SUBMIT, {"c": cid})
    await _call(db, w.dm, CHECK, _check(cid, note="the dealer over-watered it"))
    sql = ("SELECT count(*) FROM complaint_decision_note n JOIN complaint_decision d ON d.id = n.decision_id "
           "WHERE d.complaint_id = CAST(:c AS uuid)")
    assert await _call(db, w.dm, sql, {"c": cid}) == 1
    assert await _call(db, w.dealer_user, "SELECT count(*) FROM complaint WHERE id = CAST(:c AS uuid)", {"c": cid}) == 1
    assert await _call(db, w.dealer_user, "SELECT count(*) FROM complaint_decision WHERE complaint_id = CAST(:c AS uuid)", {"c": cid}) == 1
    assert await _call(db, w.dealer_user, sql, {"c": cid}) == 0


async def test_the_lead_timeline_hides_a_complaint_the_reader_cannot_see(db: AsyncSession) -> None:
    """EC-4: a dealer who sees the lead does not see a complaint about another dealer."""
    w = await _world(db)
    from types import SimpleNamespace

    from tests.db import test_migration_012 as m12
    lead = await m12._lead(db, SimpleNamespace(territory_id=w.district, org_unit_id=w.a),  # type: ignore[arg-type]
                           owner_user_id=w.officer)
    await db.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) WHERE id = CAST(:l AS uuid)"),
                     {"p": w.dealer, "l": lead})
    cid = await _complaint(db, w, lead=lead)           # no partner: not the dealer's
    await _call(db, w.officer, SUBMIT, {"c": cid})
    sql = ("SELECT count(*) FROM lead_timeline(CAST(:l AS uuid), NULL, NULL, 100) "
           "WHERE entity_type = 'complaint'")
    assert await _call(db, w.officer, sql, {"l": lead}) == 1
    assert await _call(db, w.dealer_user, sql, {"l": lead}) == 0


async def test_people_names_a_decider_to_staff_only(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w, partner=w.dealer)
    await _call(db, w.officer, SUBMIT, {"c": cid})
    await _call(db, w.sm, CHECK, _check(cid))
    sql = "SELECT count(*) FROM people_names(CAST(:ids AS uuid[])) WHERE id = CAST(:u AS uuid)"
    assert await _call(db, w.officer, sql, {"ids": [w.sm], "u": w.sm}) == 1
    assert await _call(db, w.dealer_user, sql, {"ids": [w.sm], "u": w.sm}) == 0


# ── the targets ──────────────────────────────────────────────────────────────

async def test_the_targets_never_overlap_and_a_new_one_closes_the_old(db: AsyncSession) -> None:
    w = await _world(db)
    await m13._refused(db,
        "INSERT INTO complaint_sla_policy (severity, response_hours, resolution_hours, effective_from) "
        "VALUES ('high', 2, 9, DATE '2026-08-01')", {}, "23P01")
    await _call(db, w.admin,
                "SELECT complaint_sla_policy_set('high', NULL, 2, 9, true, DATE '2099-11-01')", {})
    rows = (await db.execute(text(
        "SELECT response_hours, effective_from, effective_to FROM complaint_sla_policy "
        "WHERE severity = 'high' AND complaint_type_id IS NULL ORDER BY effective_from"))).all()
    assert [tuple(r) for r in rows][-2:] == [(4, dt.date(2026, 4, 1), dt.date(2099, 11, 1)),
                                             (2, dt.date(2099, 11, 1), None)]
    await _refused(db, w.officer,
                   "SELECT complaint_sla_policy_set('high', NULL, 2, 9, true, DATE '2099-12-01')", {}, "42501")



async def test_a_target_cannot_start_in_the_past(db: AsyncSession) -> None:
    """020 (PR 25 review): a past start closed the target in force early, and a
    resubmit then restated the targets of complaints already submitted."""
    w = await _world(db)
    before = (await db.execute(text(
        "SELECT id, effective_to FROM complaint_sla_policy ORDER BY id"))).all()
    yesterday = domain.ist_today(dt.datetime.now(dt.UTC)) - dt.timedelta(days=1)
    await _refused(db, w.admin,
                   "SELECT complaint_sla_policy_set('high', NULL, 5, 20, true, :d)", {"d": yesterday}, "CMPPD")
    after = (await db.execute(text(
        "SELECT id, effective_to FROM complaint_sla_policy ORDER BY id"))).all()
    assert after == before, "the refused call changed nothing"


async def test_working_hours_are_strict_and_refuse_negative_hours(db: AsyncSession) -> None:
    """020: a NULL looped until the statement timeout; -3 hours went before opening time."""
    for args in ({"s": None, "h": 5}, {"s": dt.datetime.now(dt.UTC), "h": None}):
        assert (await db.execute(text("SELECT complaint_add_working_hours(:s, :h)"), args)).scalar_one() is None
    assert (await db.execute(text("SELECT complaint_due(NULL, 4, true)"))).scalar_one() is None
    await m13._refused(db, "SELECT complaint_add_working_hours(now(), -3)", {}, "22023")


async def test_the_duplicate_complaint_indexes_are_gone(db: AsyncSession) -> None:
    names = set((await db.execute(text(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'complaint'"))).scalars())
    assert not names & {"ix_complaint_lead", "ix_complaint_order"}, names
    assert {"ix_complaint_lead_id", "ix_complaint_sales_order_id"} <= names, "the generated ones stay"

async def test_no_target_row_means_no_target(db: AsyncSession) -> None:
    w = await _world(db)
    await db.execute(text("DELETE FROM complaint_sla_policy WHERE severity = 'low'"))
    cid = await _complaint(db, w, severity="low")
    await _call(db, w.officer, SUBMIT, {"c": cid})
    c = await _row(db, cid)
    assert c.response_due_at is None and c.resolution_due_at is None and c.status == "submitted"


async def test_messages_stay_off_until_their_template_is_on(db: AsyncSession) -> None:
    w = await _world(db)
    cid = await _complaint(db, w)
    await _call(db, w.officer, SUBMIT, {"c": cid})
    sql = "SELECT count(*) FROM notification_outbox WHERE template_key LIKE 'complaint.%' AND payload->>'complaint_no' = :n"
    number = (await _row(db, cid)).complaint_no
    assert (await db.execute(text(sql), {"n": number})).scalar_one() == 0
    await db.execute(text("UPDATE message_template SET enabled = true WHERE key = 'complaint.updated'"))
    await _call(db, w.dm, CHECK, _check(cid))
    row = (await db.execute(text(
        "SELECT recipient, payload FROM notification_outbox WHERE template_key = 'complaint.updated' "
        "AND payload->>'complaint_no' = :n"), {"n": number})).one()
    assert row.recipient == "+919812345678"
    assert row.payload["status"] == "passed to our quality team"



# ── cross-vendor review (astra) ──────────────────────────────────────────────

async def test_a_submitted_complaints_header_is_frozen_for_app_role(db: AsyncSession) -> None:
    """Astra P2, reproduced: the column grants let an editor rewrite a complaint
    under QC. The definers (the table owner) still write it."""
    w = await _world(db)
    cid = await _complaint(db, w)
    await _call(db, w.officer, SUBMIT, {"c": cid})
    await _call(db, w.dm, CHECK, _check(cid))
    await _refused(db, w.officer, "UPDATE complaint SET description = 'rewritten' WHERE id = CAST(:c AS uuid)",
                   {"c": cid}, "CMPND")
    await _call(db, w.qc, QC, {"c": cid, "v": "approved", "n": None})
    assert (await _row(db, cid)).status == "qc_approved", "the definer is not held to it"


async def test_a_resubmit_recomputes_the_targets_from_the_first_submit(db: AsyncSession) -> None:
    """Astra P2, reproduced: severity raised on a returned draft kept the old targets."""
    w = await _world(db)
    cid = await _complaint(db, w, severity="medium")
    await _call(db, w.officer, SUBMIT, {"c": cid})
    first = (await _row(db, cid)).first_submitted_at
    await _call(db, w.dm, CHECK, _check(cid, "return"))
    await m13._as(db, w.officer)
    await db.execute(text("UPDATE complaint SET severity = 'high' WHERE id = CAST(:c AS uuid)"), {"c": cid})
    await m13._as_owner(db)
    await _call(db, w.officer, SUBMIT, {"c": cid})
    c = await _row(db, cid)
    assert c.first_submitted_at == first
    assert c.response_due_at == domain.add_working_hours(first, 4)
    assert c.resolution_due_at == domain.add_working_hours(first, 18)
