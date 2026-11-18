"""Migration 017 (FS-013): discount approval on quotations, executed as the roles
that call it. The world is migration 013's: a coded state, a district, one office,
one user per seeded role. Each test sets its own limits on that state, so the
company-wide stand-ins do not decide the result."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.quotations import effective_discount_pct
from tests.db import test_migration_012 as m12
from tests.db import test_migration_013 as m13

pytestmark = [pytest.mark.db, pytest.mark.rls]

LIMITS = {"field_officer": 5, "district_manager": 10, "state_manager": 15, "regional_manager": 20,
          "admin_sales": None}


async def _world(db: AsyncSession, limits: dict[str, int | None] = LIMITS) -> Any:
    w = await m13._world(db)
    for code, pct in limits.items():
        await db.execute(text(
            "INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount) "
            "SELECT 'quotation', r.id, CAST(:t AS uuid), :m FROM role r WHERE r.code = :c"),
            {"t": w.state, "m": pct, "c": code})
    return w


async def _quotation(db: AsyncSession, w: Any, *, owner: str | None = None,
                     pct: str = "12") -> str:
    """A draft owned by `owner`: one line, and a header of gross 1000 at `pct` % off."""
    ids = SimpleNamespace(territory_id=w.district, org_unit_id=w.office)
    lead = await m12._lead(db, ids, owner_user_id=owner or w.officer)  # type: ignore[arg-type]
    q = await m12._quotation(db, ids, lead, owner_user_id=owner or w.officer)  # type: ignore[arg-type]
    await db.execute(text("UPDATE quotation SET created_by = owner_user_id WHERE id = CAST(:q AS uuid)"),
                     {"q": q})
    await m12._line(db, q)
    await _figures(db, q, pct)
    return q


async def _figures(db: AsyncSession, q: str, pct: str) -> None:
    # the header only: the limit reads it and the hash covers it; the line's own
    # checks hold its figures to each other
    discount = Decimal("1000") * Decimal(pct) / 100
    taxable = Decimal("1000") - discount
    await db.execute(text(
        "UPDATE quotation SET gross = 1000, discount = :d, taxable = :t, total = :t "
        "WHERE id = CAST(:q AS uuid)"), {"d": discount, "t": taxable, "q": q})


async def _request(db: AsyncSession, who: str, q: str) -> str:
    await m13._as(db, who)
    request = str((await db.execute(text("SELECT quotation_request_approval(CAST(:q AS uuid), 'please')"),
                                    {"q": q})).scalar_one())
    await m13._as_owner(db)
    return request


async def _step_role(db: AsyncSession, request: str) -> list[str]:
    return [r[0] for r in (await db.execute(text(
        "SELECT r.code FROM approval_step s JOIN role r ON r.id = s.approver_role_id "
        "WHERE s.request_id = CAST(:r AS uuid) ORDER BY s.seq"), {"r": request})).all()]


async def _gate(db: AsyncSession, who: str, q: str) -> str:
    await m13._as(db, who)
    gate = str((await db.execute(text("SELECT quotation_send_gate(CAST(:q AS uuid))"), {"q": q})).scalar_one())
    await m13._as_owner(db)
    return gate


async def _step(db: AsyncSession, request: str) -> str:
    return str((await db.execute(text("SELECT id FROM approval_step WHERE request_id = CAST(:r AS uuid)"),
                                 {"r": request})).scalar_one())


# ── the chain ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("owner_role", "pct", "step"), [
    ("officer", "8", "district_manager"),      # above 5, within the District Manager's 10
    ("officer", "12", "state_manager"),        # the lowest ladder role that covers it
    ("officer", "18", "regional_manager"),
    ("officer", "35", "admin_sales"),          # the top, uncapped (EC-3)
    ("officer", "20.004", "admin_sales"),      # shows as 20.00; a 20 % limit does not cover it
    ("dm", "12", "state_manager"),             # levels at or below the owner's are skipped
    ("rm", "25", "admin_sales"),               # asked for by Admin-Sales: a Regional Manager cannot edit
])
async def test_one_step_the_lowest_ladder_role_above_the_owner_that_covers_it(
        db: AsyncSession, owner_role: str, pct: str, step: str) -> None:
    w = await _world(db)
    owner = getattr(w, owner_role)
    q = await _quotation(db, w, owner=owner, pct=pct)
    request = await _request(db, w.admin if owner_role == "rm" else owner, q)
    assert await _step_role(db, request) == [step], "one step, and never Accounts or Dispatch"
    amount = (await db.execute(text("SELECT amount FROM approval_request WHERE id = CAST(:r AS uuid)"),
                               {"r": request})).scalar_one()
    assert amount == effective_discount_pct(Decimal("1000"), Decimal("1000") * Decimal(pct) / 100)


async def test_within_the_owners_limit_there_is_nothing_to_request(db: AsyncSession) -> None:
    w = await _world(db)
    q = await _quotation(db, w, pct="5")          # exactly the officer's limit
    assert await _gate(db, w.officer, q) == "none_needed"
    await m13._as(db, w.officer)
    await m13._refused(db, "SELECT quotation_request_approval(CAST(:q AS uuid), NULL)", {"q": q}, "APRNR")


async def test_no_ladder_role_covers_it_and_nobody_is_asked(db: AsyncSession) -> None:
    w = await _world(db, {**LIMITS, "admin_sales": 30})
    q = await _quotation(db, w, pct="40")
    await m13._as(db, w.officer)
    await m13._refused(db, "SELECT quotation_request_approval(CAST(:q AS uuid), NULL)", {"q": q}, "APRNA")


# ── the gate ─────────────────────────────────────────────────────────────────

async def test_the_gate_follows_the_request_and_an_edit_voids_an_approval(db: AsyncSession) -> None:
    w = await _world(db)
    q = await _quotation(db, w, pct="12")
    assert await _gate(db, w.officer, q) == "required"
    request = await _request(db, w.officer, q)
    assert await _gate(db, w.officer, q) == "pending"
    await m13._decide(db, w.sm, await _step(db, request))
    assert await _gate(db, w.officer, q) == "approved"
    # the terms are outside the approval (EC-10)
    await db.execute(text("UPDATE quotation SET terms = 'Ex works' WHERE id = CAST(:q AS uuid)"), {"q": q})
    assert await _gate(db, w.officer, q) == "approved"
    await _figures(db, q, "13")
    assert await _gate(db, w.officer, q) == "void", "an edit after approval needs a new one"


async def test_a_return_needs_a_new_request(db: AsyncSession) -> None:
    w = await _world(db)
    q = await _quotation(db, w, pct="12")
    request = await _request(db, w.officer, q)
    await m13._decide(db, w.sm, await _step(db, request), "reject", "Too deep")
    assert await _gate(db, w.officer, q) == "returned"
    status = (await db.execute(text("SELECT status::text FROM quotation WHERE id = CAST(:q AS uuid)"),
                               {"q": q})).scalar_one()
    assert status == "draft", "the quotation's status never moves (RBAC 5.2d)"


async def test_an_edit_cancels_the_pending_request_and_the_approver_is_too_late(db: AsyncSession) -> None:
    w = await _world(db)
    q = await _quotation(db, w, pct="12")
    request = await _request(db, w.officer, q)
    await m13._as(db, w.officer)
    assert (await db.execute(text("SELECT quotation_approval_cancel(CAST(:q AS uuid))"), {"q": q})).scalar_one()
    await m13._as_owner(db)
    assert await _gate(db, w.officer, q) == "required"
    await m13._as(db, w.sm)
    await m13._refused(db, "SELECT record_decision(CAST(:s AS uuid), 'approve', 'ok')",
                       {"s": await _step(db, request)}, "APRCL")


async def test_the_decision_refuses_figures_that_moved_under_it(db: AsyncSession) -> None:
    """EC-1: even if an edit skipped the cancel, an approval is never for other figures."""
    w = await _world(db)
    q = await _quotation(db, w, pct="12")
    request = await _request(db, w.officer, q)
    await _figures(db, q, "14")
    await m13._as(db, w.sm)
    await m13._refused(db, "SELECT record_decision(CAST(:s AS uuid), 'approve', 'ok')",
                       {"s": await _step(db, request)}, "APRFC")


# ── who decides, who sees ────────────────────────────────────────────────────

async def test_only_a_manager_who_sees_the_quotation_decides_it(db: AsyncSession) -> None:
    w = await _world(db)
    q = await _quotation(db, w, pct="12")
    request = await _request(db, w.officer, q)
    step = await _step(db, request)
    tag = uuid.uuid4().hex[:8]
    far_district = str((await db.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, CAST(:p AS uuid)) RETURNING id"),
        {"n": f"m017_far_{tag}", "p": w.state})).scalar_one())
    far_office = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, CAST(:t AS uuid)) RETURNING id"),
        {"n": f"m017_far_office_{tag}", "t": far_district})).scalar_one())
    far_sm = await m13._user(db, "state_manager", far_office, "far" + tag)

    decide = "SELECT record_decision(CAST(:s AS uuid), 'approve', 'ok')"
    await m13._as(db, far_sm)
    refusal = await m13._refused(db, decide, {"s": step}, "42501")
    queued = (await db.execute(text("SELECT count(*) FROM approval_queue(NULL, NULL, 50, true) "
                                    "WHERE step_id = CAST(:s AS uuid)"), {"s": step})).scalar_one()
    seen = (await db.execute(text("SELECT count(*) FROM approval_request WHERE id = CAST(:r AS uuid)"),
                             {"r": request})).scalar_one()
    await m13._as_owner(db)
    assert "not_your_step" in refusal and (queued, seen) == (0, 0), "another office's manager is out"

    await m13._as(db, w.officer)
    assert (await db.execute(text("SELECT count(*) FROM approval_request WHERE id = CAST(:r AS uuid)"),
                             {"r": request})).scalar_one() == 1, "the owner reads its request"
    assert "self_approval" in await m13._refused(db, decide, {"s": step}, "42501")
    await m13._as(db, w.sm)
    queued = (await db.execute(text("SELECT count(*) FROM approval_queue(NULL, NULL, 50, false) "
                                    "WHERE step_id = CAST(:s AS uuid)"), {"s": step})).scalar_one()
    await m13._as_owner(db)
    assert queued == 1, "the State Manager of the office has it in the queue"


async def test_a_higher_line_manager_may_decide_a_lower_step(db: AsyncSession) -> None:
    w = await _world(db)
    q = await _quotation(db, w, pct="8")
    request = await _request(db, w.officer, q)
    assert await _step_role(db, request) == ["district_manager"]
    await m13._decide(db, w.rm, await _step(db, request))
    assert await _gate(db, w.officer, q) == "approved"


async def test_app_role_cannot_write_the_approval_or_reach_the_internal_definers(db: AsyncSession) -> None:
    w = await _world(db)
    q = await _quotation(db, w, pct="12")
    request = await _request(db, w.officer, q)
    await m13._as(db, w.officer)
    await m13._refused(db, "UPDATE approval_request SET lines_hash = 'x' WHERE id = CAST(:r AS uuid)",
                       {"r": request}, "42501")
    await m13._refused(db, "SELECT quotation_lines_hash(CAST(:q AS uuid))", {"q": q}, "42501")
    await m13._refused(db, "SELECT quotation_owner_limit(CAST(:q AS uuid))", {"q": q}, "42501")


async def test_the_decision_and_the_request_land_on_the_quotation_timeline(db: AsyncSession) -> None:
    w = await _world(db)
    q = await _quotation(db, w, pct="12")
    request = await _request(db, w.officer, q)
    await m13._decide(db, w.sm, await _step(db, request))
    kinds = [r[0] for r in (await db.execute(text(
        "SELECT kind FROM activity_event WHERE entity_type = 'quotation' AND entity_id = CAST(:q AS uuid) "
        "ORDER BY occurred_at, id"), {"q": q})).all()]
    # presence only: events written in one transaction share a timestamp (ISS-099)
    assert {"quotation.approval_requested", "approval.decided", "quotation.approval_approved"} <= set(kinds), kinds


@pytest.mark.parametrize(("gross", "discount"), [("1857.42", "269.32"), ("3.00", "1.00"),
                                                 ("200.00", "0.01"), ("0.00", "0.00")])
async def test_the_sql_percentage_agrees_with_the_domain(db: AsyncSession, gross: str, discount: str) -> None:
    got = (await db.execute(text("SELECT quotation_effective_pct(CAST(:g AS numeric), CAST(:d AS numeric))"),
                            {"g": gross, "d": discount})).scalar_one()
    assert got == effective_discount_pct(Decimal(gross), Decimal(discount))


async def test_a_manager_without_a_row_is_not_approved_by_a_lower_one(db: AsyncSession) -> None:
    """A Regional Manager with no quotation row has a limit of 0, so any discount needs
    approval; the ladder skips every level at or below theirs, even when a District
    Manager's limit would cover the figure."""
    w = await _world(db, {k: v for k, v in LIMITS.items() if k != "regional_manager"})
    await db.execute(text(
        "DELETE FROM approval_threshold WHERE doc_type = 'quotation' AND territory_id IS NULL "
        "AND role_id = (SELECT id FROM role WHERE code = 'regional_manager')"))
    q = await _quotation(db, w, owner=w.rm, pct="8")
    request = await _request(db, w.admin, q)
    assert await _step_role(db, request) == ["admin_sales"]



async def test_admin_sales_tops_the_ladder_even_without_a_row(db: AsyncSession) -> None:
    """OCR review: the owner's limit already treats Admin-Sales as uncapped with no
    row; the ladder does the same, so a deep discount is never left without an approver."""
    w = await _world(db, {k: v for k, v in LIMITS.items() if k != "admin_sales"})
    await db.execute(text(
        "DELETE FROM approval_threshold WHERE doc_type = 'quotation' "
        "AND role_id = (SELECT id FROM role WHERE code = 'admin_sales')"))
    q = await _quotation(db, w, pct="35")
    assert await _step_role(db, await _request(db, w.officer, q)) == ["admin_sales"]


@pytest.mark.parametrize(("pct", "limit"), [("5", 5), ("5.001", 5), ("0.01", 0), ("12", 10), ("9.999", 10)])
async def test_the_sql_gate_agrees_with_the_domain(db: AsyncSession, pct: str, limit: int) -> None:
    """OCR review: the domain's discount_approval_required() is the rule's statement;
    the gate the send uses is SQL. Held equal here."""
    from api.domain.quotations import discount_approval_required
    w = await _world(db, {**LIMITS, "field_officer": limit or None})
    if limit == 0:
        await db.execute(text(
            "UPDATE approval_threshold SET max_amount = NULL WHERE doc_type = 'quotation' "
            "AND territory_id = CAST(:t AS uuid) AND role_id = (SELECT id FROM role WHERE code = 'field_officer')"),
            {"t": w.state})
        await db.execute(text(
            "DELETE FROM approval_threshold WHERE doc_type = 'quotation' "
            "AND role_id = (SELECT id FROM role WHERE code = 'field_officer')"))
    q = await _quotation(db, w, pct=pct)
    await m13._as(db, w.officer)
    required = (await db.execute(text("SELECT approval_required FROM quotation_discount_limit(CAST(:q AS uuid))"),
                                 {"q": q})).scalar_one()
    await m13._as_owner(db)
    discount = Decimal("1000") * Decimal(pct) / 100
    assert required is discount_approval_required(Decimal("1000"), discount, Decimal(limit))


async def test_the_decision_lock_relies_on_lead_and_quotation_not_forcing_rls(db: AsyncSession) -> None:
    """record_decision() locks the lead and the quotation as the definer's owner, for an
    approver who holds no leads.edit. Under FORCE ROW LEVEL SECURITY the owner's
    FOR UPDATE would lock only what the caller sees, and the lock order would go
    without an error. This fails first if either table is ever forced."""
    forced = dict((await db.execute(text(
        "SELECT relname, relforcerowsecurity FROM pg_class WHERE relname IN ('lead', 'quotation')"))).all())
    assert forced == {"lead": False, "quotation": False}


async def test_only_an_editor_who_sees_the_quotation_may_cancel_its_request(db: AsyncSession) -> None:
    """quotation_approval_cancel() writes approval_request as a definer; its guards are
    the only thing between app_role and every pending request."""
    w = await _world(db)
    q = await _quotation(db, w, pct="12")
    await _request(db, w.officer, q)
    tag = uuid.uuid4().hex[:8]
    far_district = str((await db.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, CAST(:p AS uuid)) RETURNING id"),
        {"n": f"m017_far2_{tag}", "p": w.state})).scalar_one())
    far_office = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, CAST(:t AS uuid)) RETURNING id"),
        {"n": f"m017_far2_office_{tag}", "t": far_district})).scalar_one())
    far_sm = await m13._user(db, "state_manager", far_office, "fc" + tag)
    cancel = "SELECT quotation_approval_cancel(CAST(:q AS uuid))"
    for who in (far_sm, w.rm):            # cannot see it; sees it but holds no quotations.edit
        await m13._as(db, who)
        await m13._refused(db, cancel, {"q": q}, "42501")
    await m13._as_owner(db)
    assert await _gate(db, w.officer, q) == "pending", "nothing was cancelled"


async def test_a_decision_on_a_deleted_or_sent_draft_is_refused(db: AsyncSession) -> None:
    """Code review: even if the request were left pending, a quotation that is no
    longer a live draft is never approved."""
    w = await _world(db)
    for change in ("UPDATE quotation SET deleted_at = now() WHERE id = CAST(:q AS uuid)",
                   "UPDATE quotation SET status = 'sent', sent_at = now(), valid_until = CURRENT_DATE + 45, "
                   "share_token = md5(random()::text), quote_no = 'QT/T/' || substr(md5(random()::text), 1, 8), "
                   "seller_legal_name = 'Polysil', seller_gstin_no = '24AAAAA0000A1Z5', "
                   "seller_state_code = 'GJ', pdf_state = 'pending' WHERE id = CAST(:q AS uuid)"):
        q = await _quotation(db, w, pct="12")
        request = await _request(db, w.officer, q)
        await db.execute(text(change), {"q": q})
        await m13._as(db, w.sm)
        await m13._refused(db, "SELECT record_decision(CAST(:s AS uuid), 'approve', 'ok')",
                           {"s": await _step(db, request)}, "APRCL")
        await m13._as_owner(db)
