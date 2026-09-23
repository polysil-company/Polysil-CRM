"""Migration 013 (FS-011 5): the second enforcer, executed.

Every test runs the database half of FS-011 as the role that would run it, with
the seeded roles as they stand (RBAC 6.2: a test that overrides the seed's scope
passes against a broken seed). The world is built inside the rolled-back
transaction: a coded state, a district, one office, and one user on each seeded
role that the chain names, all in that office.
"""

# ruff: noqa: E501  (embedded SQL, kept on one line so each statement reads whole)

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from tests.db.conftest import Fixtures, make_partner_user

pytestmark = [pytest.mark.db, pytest.mark.rls]

GRANTED = [
    "order_visible(uuid)", "create_approval_request(text, uuid)",
    "record_decision(uuid, text, text)", "approval_queue(timestamptz, uuid, integer, boolean)",
    "order_submit(uuid)", "order_cancel(uuid, text, text)", "order_delete(uuid)",
    "order_quotations_claim(uuid, uuid[])", "dispatch_record(uuid, jsonb)",
    "dispatch_void(uuid, text)", "order_close_short(uuid, text)",
]
INTERNAL = [
    "approval_owner_level(uuid)", "approval_chain(text, numeric, uuid, integer)",
    "approval_step_stalled(uuid)", "approval_refusal(uuid)",
    "apply_approval_outcome(text, uuid, text)", "advance_approval(uuid)",
    "order_quotations_release(uuid)", "order_allocate_no(text, text)",
    "order_dispatch_status(uuid)",
]


# ── the world ────────────────────────────────────────────────────────────────

@dataclass
class World:
    state: str
    state_code: str
    district: str
    office: str
    officer: str
    dm: str
    sm: str
    rm: str
    accounts: str
    dispatcher: str
    admin: str


async def _as(db: AsyncSession, user_id: str) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id)})
    await enter_role(db, "app_role")


async def _as_owner(db: AsyncSession) -> None:
    await db.execute(text("SELECT set_config('role', 'none', true)"))


async def _user(db: AsyncSession, role_code: str, office: str, tag: str) -> str:
    return str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, 'x', :n, r.id, CAST(:o AS uuid) FROM role r WHERE r.code = :c "
        "RETURNING id"),
        {"e": f"{role_code}_{tag}@m013.in", "n": role_code, "c": role_code,
         "o": office})).scalar_one())


async def _world(db: AsyncSession) -> World:
    tag = uuid.uuid4().hex[:8]
    code = "O" + tag[:3].upper()
    state = str((await db.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": f"m013_state_{tag}", "c": code})).scalar_one())
    district = str((await db.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
        {"n": f"m013_district_{tag}", "p": state})).scalar_one())
    office = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"m013_office_{tag}", "t": district})).scalar_one())
    users = {c: await _user(db, c, office, tag) for c in (
        "field_officer", "district_manager", "state_manager", "regional_manager",
        "account_manager", "dispatch_manager", "admin_sales")}
    return World(state, code, district, office, users["field_officer"],
                 users["district_manager"], users["state_manager"], users["regional_manager"],
                 users["account_manager"], users["dispatch_manager"], users["admin_sales"])


async def _catalogue_row(db: AsyncSession) -> tuple[str, str]:
    """A price-list item and a tax rate of the test's own (ISS-096: CI's database
    has no catalogue)."""
    found = (await db.execute(text(
        "SELECT i.id AS item, g.id AS gst FROM price_list_item i "
        "JOIN price_list l ON l.id = i.price_list_id AND l.name = 'm013 lines' "
        "JOIN gst_rate g ON g.hsn_code = '3917' AND g.effective_from = DATE '1991-01-01' "
        "LIMIT 1"))).one_or_none()
    if found is not None:
        return str(found.item), str(found.gst)
    product = (await db.execute(text(
        "INSERT INTO product (description, product_category_id, quotation_category, uom_id) "
        "SELECT CAST(:d AS citext), (SELECT id FROM product_category ORDER BY sort_order LIMIT 1), "
        "'field', (SELECT id FROM uom LIMIT 1) RETURNING id"),
        {"d": "M013 PIPE " + uuid.uuid4().hex[:8]})).scalar_one()
    price_list = (await db.execute(text(
        "INSERT INTO price_list (name, channel_tier, status, published_at, effective_from, "
        "effective_to) VALUES ('m013 lines', 'farmer', 'published', now(), DATE '1991-01-01', "
        "DATE '1992-01-01') RETURNING id"))).scalar_one()
    item = (await db.execute(text(
        "INSERT INTO price_list_item (price_list_id, product_id, rate) VALUES (:l, :p, 100) "
        "RETURNING id"), {"l": price_list, "p": product})).scalar_one()
    gst = (await db.execute(text(
        "INSERT INTO gst_rate (hsn_code, rate, effective_from, effective_to) "
        "VALUES ('3917', 5, DATE '1991-01-01', DATE '1992-01-01') RETURNING id"))).scalar_one()
    return str(item), str(gst)


async def _order(db: AsyncSession, w: World, *, owner: str | None = None, qty: int = 500,
                 decimals: int = 0, lead: str | None = None, partner: str | None = None) -> str:
    """A draft as the table owner: one line of `qty` at 100 with 5 % GST, so the
    total is 105 x qty."""
    owner = owner or w.officer
    gross = Decimal(qty) * 100
    tax = gross * Decimal("0.025")
    total = gross + 2 * tax
    order = str((await db.execute(text(
        "INSERT INTO sales_order (order_type, party_name, party_mobile, owner_user_id, "
        "owner_org_unit_id, territory_id, seller_gstin_id, place_of_supply_territory_id, "
        "place_of_supply_state_id, intra_state, price_effective_date, gross, taxable, cgst, "
        "sgst, total, created_by, lead_id, partner_id) "
        "VALUES ('commercial', 'Farmer', '+919800000000', CAST(:o AS uuid), CAST(:ou AS uuid), "
        "CAST(:d AS uuid), (SELECT id FROM seller_gstin ORDER BY is_default DESC LIMIT 1), "
        "CAST(:d AS uuid), CAST(:s AS uuid), true, CURRENT_DATE, :g, :g, :t, :t, :tot, "
        "CAST(:o AS uuid), CAST(:lead AS uuid), CAST(:p AS uuid)) RETURNING id"),
        {"o": owner, "ou": w.office, "d": w.district, "s": w.state, "g": gross, "t": tax,
         "tot": total, "lead": lead, "p": partner})).scalar_one())
    item, gst = await _catalogue_row(db)
    await db.execute(text(
        "INSERT INTO order_line (sales_order_id, line_no, product_id, description, hsn_code, uom, "
        "uom_decimals, qty, rate, price_list_id, price_list_item_id, gst_rate_id, gross, "
        "after_discount1, after_discount2, taxable, gst_slab, cgst_rate, sgst_rate, igst_rate, "
        "cgst, sgst, igst, total) "
        "SELECT CAST(:o AS uuid), 1, i.product_id, 'pipe', '3917', 'MTR', :dec, :q, 100, "
        "i.price_list_id, i.id, CAST(:g AS uuid), :gross, :gross, :gross, :gross, 5, 2.5, 2.5, 0, "
        ":t, :t, 0, :tot FROM price_list_item i WHERE i.id = CAST(:i AS uuid)"),
        {"o": order, "dec": decimals, "q": qty, "g": gst, "gross": gross, "t": tax,
         "tot": total, "i": item})
    return order


async def _refused(db: AsyncSession, sql: str, params: dict[str, Any], sqlstate: str) -> str:
    await db.execute(text("SAVEPOINT sp"))
    try:
        await db.execute(text(sql), params)
    except DBAPIError as exc:
        code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
        await db.execute(text("ROLLBACK TO SAVEPOINT sp"))
        assert code == sqlstate, f"expected {sqlstate}, got {code}: {exc.orig}"
        return str(exc.orig)
    await db.execute(text("ROLLBACK TO SAVEPOINT sp"))
    raise AssertionError(f"the statement was accepted: {sql[:80]}")


async def _submit(db: AsyncSession, w: World, order: str, by: str | None = None) -> str:
    await _as(db, by or w.officer)
    request = str((await db.execute(text("SELECT order_submit(CAST(:o AS uuid))"),
                                    {"o": order})).scalar_one())
    await _as_owner(db)
    return request


async def _steps(db: AsyncSession, request: str) -> list[Any]:
    return list((await db.execute(text(
        "SELECT s.id, s.seq, r.code::text AS role, s.decision::text AS decision, "
        "dr.code::text AS decided_role FROM approval_step s JOIN role r ON r.id = s.approver_role_id "
        "LEFT JOIN role dr ON dr.id = s.decided_role_id WHERE s.request_id = CAST(:r AS uuid) "
        "ORDER BY s.seq"), {"r": request})).all())


async def _decide(db: AsyncSession, who: str, step: Any, decision: str = "approve",
                  remark: str | None = "ok") -> str:
    await _as(db, who)
    out = str((await db.execute(text("SELECT record_decision(CAST(:s AS uuid), :d, :r)"),
                                {"s": str(step), "d": decision, "r": remark})).scalar_one())
    await _as_owner(db)
    return out


async def _status(db: AsyncSession, order: str) -> str:
    return str((await db.execute(text(
        "SELECT status::text FROM sales_order WHERE id = CAST(:o AS uuid)"),
        {"o": order})).scalar_one())


async def _approved(db: AsyncSession, w: World, qty: int = 500, decimals: int = 0) -> str:
    order = await _order(db, w, qty=qty, decimals=decimals)
    request = await _submit(db, w, order)
    who = {"district_manager": w.dm, "state_manager": w.sm, "regional_manager": w.rm,
           "account_manager": w.accounts, "dispatch_manager": w.dispatcher}
    for step in await _steps(db, request):
        await _decide(db, who[step.role], step.id)
    assert await _status(db, order) == "approved"
    return order


# ── the surface ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sig", GRANTED + INTERNAL)
async def test_every_new_definer_is_pinned_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
    assert row[0], f"{sig} is SECURITY DEFINER"
    assert "search_path=public, pg_temp" in (row[1] or []), row[1]
    assert not row[2], f"{sig} is not PUBLIC-executable"


@pytest.mark.parametrize("sig", INTERNAL)
async def test_the_internal_functions_are_not_granted_to_app_role(db: AsyncSession,
                                                                  sig: str) -> None:
    held = (await db.execute(text("SELECT has_function_privilege('app_role', :s, 'EXECUTE')"),
                             {"s": sig})).scalar_one()
    assert not held, f"{sig} is reachable only through the granted definers"


async def test_app_role_cannot_write_the_status_by_update_or_by_insert(db: AsyncSession) -> None:
    """Delta check N-1 and cross-vendor C-2: column grants. Without them an owner
    approves their own order in one statement."""
    w = await _world(db)
    order = await _order(db, w)
    await _as(db, w.officer)
    await _refused(db, "UPDATE sales_order SET status = 'approved' WHERE id = CAST(:o AS uuid)",
                   {"o": order}, "42501")
    await _refused(db, "UPDATE sales_order SET order_no = 'SO/X' WHERE id = CAST(:o AS uuid)",
                   {"o": order}, "42501")
    await _refused(db,
        "INSERT INTO sales_order (order_type, status, party_name, owner_user_id, owner_org_unit_id, "
        "territory_id, seller_gstin_id, place_of_supply_territory_id, place_of_supply_state_id, "
        "intra_state, price_effective_date) SELECT order_type, 'approved', party_name, owner_user_id, "
        "owner_org_unit_id, territory_id, seller_gstin_id, place_of_supply_territory_id, "
        "place_of_supply_state_id, intra_state, price_effective_date FROM sales_order "
        "WHERE id = CAST(:o AS uuid)", {"o": order}, "42501")
    # a draft-editable column is fine
    await db.execute(text("UPDATE sales_order SET remarks = 'call first' WHERE id = CAST(:o AS uuid)"),
                     {"o": order})


async def test_a_new_order_is_a_fresh_draft_even_for_the_owner(db: AsyncSession) -> None:
    """The belt behind the grant: the trigger refuses a non-draft insert whoever runs it."""
    w = await _world(db)
    order = await _order(db, w)
    await _refused(db,
        "INSERT INTO sales_order (order_type, status, party_name, owner_org_unit_id, territory_id, "
        "seller_gstin_id, place_of_supply_territory_id, place_of_supply_state_id, intra_state, "
        "price_effective_date) SELECT order_type, 'approved', party_name, owner_org_unit_id, "
        "territory_id, seller_gstin_id, place_of_supply_territory_id, place_of_supply_state_id, "
        "intra_state, price_effective_date FROM sales_order WHERE id = CAST(:o AS uuid)",
        {"o": order}, "23514")


async def test_a_submitted_order_refuses_edits_and_illegal_moves(db: AsyncSession) -> None:
    w = await _world(db)
    order = await _order(db, w)
    await _submit(db, w, order)
    await _refused(db, "UPDATE sales_order SET party_name = 'Someone else' "
                       "WHERE id = CAST(:o AS uuid)", {"o": order}, "23514")
    await _refused(db, "UPDATE sales_order SET status = 'dispatched', approved_at = now() "
                       "WHERE id = CAST(:o AS uuid)", {"o": order}, "23514")
    await _refused(db, "UPDATE order_line SET qty = 1 WHERE sales_order_id = CAST(:o AS uuid)",
                   {"o": order}, "23514")


async def test_nobody_inserts_an_approval_step_directly(db: AsyncSession) -> None:
    """RBAC 5.2a: a user who could insert steps could fabricate a chain."""
    w = await _world(db)
    order = await _order(db, w)
    request = await _submit(db, w, order)
    await _as(db, w.accounts)
    await _refused(db, "INSERT INTO approval_step (request_id, seq, approver_role_id) "
                       "SELECT CAST(:r AS uuid), 9, role_id FROM app_user "
                       "WHERE id = CAST(:u AS uuid)", {"r": request, "u": w.accounts}, "42501")
    await _refused(db, "UPDATE approval_step SET decision = 'approve' "
                       "WHERE request_id = CAST(:r AS uuid)", {"r": request}, "42501")


# ── the chain ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("owner_level", "amount", "expected"), [
    (0, 50_000, ["district_manager"]),
    (0, 100_000, ["district_manager"]),
    (0, 100_000.01, ["district_manager", "state_manager"]),
    (0, 900_000, ["district_manager", "state_manager", "regional_manager"]),
    (2, 50_000, []),
    (2, 300_000, ["state_manager"]),
    (3, 900_000, ["regional_manager"]),
    (5, 900_000, []),
])
async def test_the_chain_by_band_and_owner_level(db: AsyncSession, owner_level: int,
                                                 amount: float, expected: list[str]) -> None:
    """FS-011 2.3 over the seeded stand-ins (1,00,000 and 5,00,000), band edges
    included; Accounts and Dispatch always close it; no level-5 line role ever
    appears (delta check R-3)."""
    w = await _world(db)
    chain = (await db.execute(text(
        "SELECT array_agg(r.code::text ORDER BY x.n) FROM unnest(approval_chain('sales_order', "
        ":a, CAST(:t AS uuid), :l)) WITH ORDINALITY x(id, n) JOIN role r ON r.id = x.id"),
        {"a": Decimal(str(amount)), "t": w.district, "l": owner_level})).scalar_one()
    assert chain == [*expected, "account_manager", "dispatch_manager"], chain


async def test_a_territory_row_overrides_the_global_one(db: AsyncSession) -> None:
    """Edge case 4: the nearest row up the territory tree wins; a row on the state
    reaches an order on a district."""
    w = await _world(db)
    await db.execute(text(
        "INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount) "
        "SELECT 'sales_order', id, CAST(:s AS uuid), 20000 FROM role WHERE code = 'district_manager'"),
        {"s": w.state})
    chain = (await db.execute(text(
        "SELECT array_agg(r.code::text ORDER BY x.n) FROM unnest(approval_chain('sales_order', "
        "50000, CAST(:t AS uuid), 0)) WITH ORDINALITY x(id, n) JOIN role r ON r.id = x.id"),
        {"t": w.district})).scalar_one()
    assert chain[:2] == ["district_manager", "state_manager"], chain


# ── deciding ─────────────────────────────────────────────────────────────────

async def test_submit_numbers_the_order_and_builds_the_chain_from_the_owner(
        db: AsyncSession) -> None:
    """Edge case 1: the District Manager submits the officer's order, and the chain
    still starts at the District Manager, because the level is the owner's; the
    District Manager is the requester and cannot decide it."""
    w = await _world(db)
    order = await _order(db, w)  # 52,500
    request = await _submit(db, w, order, by=w.dm)
    row = (await db.execute(text(
        "SELECT order_no, status::text, tax_date IS NOT NULL, seller_legal_name IS NOT NULL "
        "FROM sales_order WHERE id = CAST(:o AS uuid)"), {"o": order})).one()
    assert row[0].startswith(f"SO/{w.state_code}/") and row[1] == "submitted" and row[2] and row[3]
    steps = await _steps(db, request)
    assert [s.role for s in steps] == ["district_manager", "account_manager", "dispatch_manager"]
    await _as(db, w.dm)
    message = await _refused(db, "SELECT record_decision(CAST(:s AS uuid), 'approve', 'x')",
                             {"s": str(steps[0].id)}, "42501")
    assert "self_approval" in message


async def test_accounts_and_dispatch_never_decide_a_line_step(db: AsyncSession) -> None:
    """Plan review B-1: both hold approve at global scope and are level 5; the
    escalation is by line role, so they are refused."""
    w = await _world(db)
    request = await _submit(db, w, await _order(db, w))
    first = (await _steps(db, request))[0]
    for who in (w.accounts, w.dispatcher):
        await _as(db, who)
        message = await _refused(db, "SELECT record_decision(CAST(:s AS uuid), 'approve', 'x')",
                                 {"s": str(first.id)}, "42501")
        assert "not_your_step" in message
        await _as_owner(db)


async def test_a_higher_line_manager_decides_a_lower_step_and_is_recorded(
        db: AsyncSession) -> None:
    """Rule 7: the State Manager takes the District step; the step keeps its role
    and records who and as what."""
    w = await _world(db)
    request = await _submit(db, w, await _order(db, w))
    first = (await _steps(db, request))[0]
    await _decide(db, w.sm, first.id)
    decided = (await _steps(db, request))[0]
    assert (decided.role, decided.decision, decided.decided_role) == (
        "district_manager", "approve", "state_manager")


async def test_steps_decide_in_order_and_accounts_must_say_why(db: AsyncSession) -> None:
    """APPR-11 and FS-011 rule 11; the chain approves only when every step has."""
    w = await _world(db)
    order = await _order(db, w)
    request = await _submit(db, w, order)
    dm, acc, dsp = await _steps(db, request)
    await _as(db, w.accounts)
    await _refused(db, "SELECT record_decision(CAST(:s AS uuid), 'approve', 'paid')",
                   {"s": str(acc.id)}, "APREU")
    await _as_owner(db)
    assert await _decide(db, w.dm, dm.id, remark=None) == "pending"
    await _as(db, w.accounts)
    await _refused(db, "SELECT record_decision(CAST(:s AS uuid), 'approve', '   ')",
                   {"s": str(acc.id)}, "APRRM")
    await _as_owner(db)
    assert await _decide(db, w.accounts, acc.id, remark="Payment seen") == "pending"
    assert await _status(db, order) == "submitted"
    await _as(db, w.accounts)
    await _refused(db, "SELECT record_decision(CAST(:s AS uuid), 'approve', 'again')",
                   {"s": str(acc.id)}, "APRSD")
    await _as_owner(db)
    assert await _decide(db, w.dispatcher, dsp.id, remark=None) == "approved"
    assert await _status(db, order) == "approved"


async def test_a_rejection_returns_the_order_to_draft_and_a_resubmit_keeps_the_number(
        db: AsyncSession) -> None:
    w = await _world(db)
    order = await _order(db, w)
    request = await _submit(db, w, order)
    number = (await db.execute(text("SELECT order_no FROM sales_order WHERE id = CAST(:o AS uuid)"),
                               {"o": order})).scalar_one()
    dm = (await _steps(db, request))[0]
    await _as(db, w.dm)
    await _refused(db, "SELECT record_decision(CAST(:s AS uuid), 'reject', NULL)",
                   {"s": str(dm.id)}, "APRRM")
    await _as_owner(db)
    assert await _decide(db, w.dm, dm.id, "reject", "Wrong rate") == "rejected"
    assert await _status(db, order) == "draft"
    again = await _submit(db, w, order)
    assert again != request
    kept = (await db.execute(text("SELECT order_no FROM sales_order WHERE id = CAST(:o AS uuid)"),
                             {"o": order})).scalar_one()
    assert kept == number
    events = [r[0] for r in (await db.execute(text(
        "SELECT payload FROM activity_event WHERE entity_id = CAST(:o AS uuid) "
        "AND kind = 'approval.decided'"), {"o": order})).all()]
    for payload in events:
        payload = payload if isinstance(payload, dict) else json.loads(payload)
        assert set(payload) == {"seq", "role", "decision"}, "no remark and no name (B-5)"


async def test_a_step_with_no_one_of_its_role_in_reach_is_stalled(db: AsyncSession) -> None:
    """Plan review B-6: stalled means no active user of the step's role sits in an
    office at or above the order's. Deactivating the only District Manager stalls
    the step; a higher manager still sees it in the queue."""
    w = await _world(db)
    request = await _submit(db, w, await _order(db, w))
    first = (await _steps(db, request))[0]
    stalled = "SELECT approval_step_stalled(CAST(:s AS uuid))"
    assert not (await db.execute(text(stalled), {"s": str(first.id)})).scalar_one()
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = CAST(:u AS uuid)"),
                     {"u": w.dm})
    assert (await db.execute(text(stalled), {"s": str(first.id)})).scalar_one()
    await _as(db, w.sm)
    queued = [str(r.step_id) for r in (await db.execute(text(
        "SELECT * FROM approval_queue(NULL, NULL, 50, false)"))).all()]
    assert str(first.id) in queued


async def test_the_queue_holds_my_steps_and_never_my_own_orders(db: AsyncSession) -> None:
    w = await _world(db)
    mine = await _submit(db, w, await _order(db, w))
    own = await _order(db, w, owner=w.dm)
    await _submit(db, w, own, by=w.dm)
    await _as(db, w.dm)
    queued = {str(r.step_id) for r in (await db.execute(text(
        "SELECT * FROM approval_queue(NULL, NULL, 50, false)"))).all()}
    assert str((await _steps(db, mine))[0].id) in queued
    await _as_owner(db)
    # the District Manager's own order has no District step, and its Accounts step
    # is neither theirs nor below them
    own_request = (await db.execute(text(
        "SELECT id FROM approval_request WHERE entity_id = CAST(:o AS uuid)"), {"o": own})).scalar_one()
    assert not ({str(s.id) for s in await _steps(db, str(own_request))} & queued)


# ── cancel ───────────────────────────────────────────────────────────────────

async def test_cancel_follows_the_state_table(db: AsyncSession) -> None:
    w = await _world(db)
    order = await _order(db, w)
    request = await _submit(db, w, order)
    await _as(db, w.officer)
    await _refused(db, "SELECT order_cancel(CAST(:o AS uuid), '  ')", {"o": order}, "APRRM")
    await db.execute(text("SELECT order_cancel(CAST(:o AS uuid), 'Customer postponed')"),
                     {"o": order})
    await _as_owner(db)
    assert await _status(db, order) == "cancelled"
    closed = (await db.execute(text("SELECT status::text FROM approval_request "
                                    "WHERE id = CAST(:r AS uuid)"), {"r": request})).scalar_one()
    assert closed == "cancelled"
    approved = await _approved(db, w)
    await _as(db, w.officer)
    await _refused(db, "SELECT order_cancel(CAST(:o AS uuid), 'x')", {"o": approved}, "42501")
    await _as(db, w.sm)
    await db.execute(text("SELECT order_cancel(CAST(:o AS uuid), 'Plant shut')"), {"o": approved})
    await _as_owner(db)
    assert await _status(db, approved) == "cancelled"


# ── dispatch ─────────────────────────────────────────────────────────────────

def _payload(line: str, qty: str) -> str:
    return json.dumps({"dc_no": "DC-1", "dispatched_at": "2026-01-15T10:00:00+05:30",
                       "lines": [{"order_line_id": line, "qty": qty}]})


async def _line(db: AsyncSession, order: str) -> str:
    return str((await db.execute(text(
        "SELECT id FROM order_line WHERE sales_order_id = CAST(:o AS uuid)"),
        {"o": order})).scalar_one())


async def test_dispatch_counts_open_quantity_and_derives_the_status(db: AsyncSession) -> None:
    w = await _world(db)
    order = await _approved(db, w, qty=10)
    line = await _line(db, order)
    record = "SELECT dispatch_record(CAST(:o AS uuid), CAST(:p AS jsonb))"
    await _as(db, w.dispatcher)
    await _refused(db, record, {"o": order, "p": _payload(line, "11")}, "DSPOV")
    await _refused(db, record, {"o": order, "p": _payload(line, "2.5")}, "DSPPR")
    # one payload naming the line twice is summed (edge case 9)
    twice = json.dumps({"dispatched_at": "2026-01-15T10:00:00+05:30", "lines": [
        {"order_line_id": line, "qty": "6"}, {"order_line_id": line, "qty": "6"}]})
    await _refused(db, record, {"o": order, "p": twice}, "DSPOV")
    first = str((await db.execute(text(record), {"o": order, "p": _payload(line, "4")})).scalar_one())
    await _as_owner(db)
    assert await _status(db, order) == "partially_dispatched"
    await _as(db, w.dispatcher)
    await db.execute(text(record), {"o": order, "p": _payload(line, "6")})
    await _as_owner(db)
    assert await _status(db, order) == "dispatched"
    await _as(db, w.dispatcher)
    await db.execute(text("SELECT dispatch_void(CAST(:d AS uuid), 'Wrong DC')"), {"d": first})
    await _refused(db, "SELECT dispatch_void(CAST(:d AS uuid), 'again')", {"d": first}, "DSPVD")
    await _as_owner(db)
    assert await _status(db, order) == "partially_dispatched"
    numbers = [r[0] for r in (await db.execute(text(
        "SELECT dispatch_no FROM dispatch WHERE sales_order_id = CAST(:o AS uuid) "
        "ORDER BY created_at, dispatch_no"), {"o": order})).all()]
    assert [n.rsplit("/", 1)[1] for n in numbers] == ["1", "2"]


async def test_close_short_writes_the_lines_and_a_direct_write_cannot(db: AsyncSession) -> None:
    """Plan review B-3: qty_short is admitted only at trigger depth 2, from the
    close-short trigger. The owner's direct UPDATE runs at depth 1 and is refused."""
    w = await _world(db)
    order = await _approved(db, w, qty=10)
    line = await _line(db, order)
    await _refused(db, "UPDATE order_line SET qty_short = 10 WHERE id = CAST(:l AS uuid)",
                   {"l": line}, "23514")
    await _as(db, w.dispatcher)
    await db.execute(text("SELECT dispatch_record(CAST(:o AS uuid), CAST(:p AS jsonb))"),
                     {"o": order, "p": _payload(line, "3")})
    await db.execute(text("SELECT order_close_short(CAST(:o AS uuid), 'Discontinued')"),
                     {"o": order})
    await _as_owner(db)
    assert await _status(db, order) == "closed_short"
    short = (await db.execute(text("SELECT qty_short FROM order_line WHERE id = CAST(:l AS uuid)"),
                              {"l": line})).scalar_one()
    assert short == Decimal("7.000")
    first = (await db.execute(text("SELECT id FROM dispatch WHERE sales_order_id = CAST(:o AS uuid)"),
                              {"o": order})).scalar_one()
    await _as(db, w.dispatcher)
    await _refused(db, "SELECT dispatch_void(CAST(:d AS uuid), 'x')", {"d": str(first)}, "ORDCL")


async def test_an_approved_order_that_will_never_ship_closes_short(db: AsyncSession) -> None:
    """Edge case 10."""
    w = await _world(db)
    order = await _approved(db, w, qty=10)
    await _as(db, w.dispatcher)
    await db.execute(text("SELECT order_close_short(CAST(:o AS uuid), 'Plant stopped the item')"),
                     {"o": order})
    await _as_owner(db)
    short = (await db.execute(text("SELECT qty_short FROM order_line "
                                   "WHERE sales_order_id = CAST(:o AS uuid)"), {"o": order})).scalar_one()
    assert short == Decimal("10.000")


# ── the lead timeline ────────────────────────────────────────────────────────

async def test_the_lead_timeline_hides_a_direct_sale_order_from_the_leads_dealer(
        db: AsyncSession, ids: Fixtures) -> None:
    """Rule 17's order half: lead_timeline() is a definer, and its own
    order_visible() filter is the whole of the rule."""
    w = await _world(db)
    await db.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'partner_subtree'), (:r, 'sales_orders', 'view', 'partner_subtree')"),
        {"r": ids.portal_role_id})
    dealer = await make_partner_user(db, ids, mobile="9198" + f"{uuid.uuid4().int % 10**8:08d}")
    lead = str((await db.execute(text(
        "INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id, "
        "farmer_name, mobile, territory_id, owner_org_unit_id, assigned_partner_id) "
        "VALUES (:no, 'qualified', 'commercial', (SELECT id FROM mis_system WHERE code='drip'), "
        "(SELECT id FROM lead_source WHERE code='employee'), 'Farmer', :m, CAST(:t AS uuid), "
        "CAST(:ou AS uuid), CAST(:p AS uuid)) RETURNING id"),
        {"no": "POL-" + uuid.uuid4().hex[:10], "m": "+9198" + f"{uuid.uuid4().int % 10**8:08d}",
         "t": w.district, "ou": w.office, "p": ids.dealer_id})).scalar_one())
    direct = await _order(db, w, lead=lead)
    routed = await _order(db, w, lead=lead, partner=ids.dealer_id)
    for o in (direct, routed):
        await db.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
            "VALUES ('sales_order', CAST(:o AS uuid), CAST(:l AS uuid), 'order.created', "
            "CAST(:a AS uuid), '{}')"), {"o": o, "l": lead, "a": w.officer})
    await _as(db, dealer)
    assert (await db.execute(text("SELECT lead_visible(CAST(:l AS uuid))"), {"l": lead})).scalar_one()
    seen = {str(r[0]) for r in (await db.execute(text(
        "SELECT entity_id FROM lead_timeline(CAST(:l AS uuid), NULL, NULL, 50) "
        "WHERE entity_type = 'sales_order'"), {"l": lead})).all()}
    assert seen == {routed}, "the direct sale's events are not on the dealer's timeline"


async def test_the_stall_rule_rests_on_the_line_roles_org_subtree_view(db: AsyncSession) -> None:
    """approval_step_stalled() looks for an approver in the offices above the
    order's, which is right only while every line role views orders org_subtree
    (plan review B-6). This fails the day the seed changes that."""
    rows = (await db.execute(text(
        "SELECT r.code::text, rp.scope::text FROM role_permission rp JOIN role r ON r.id = rp.role_id "
        "WHERE rp.module = 'sales_orders' AND rp.action = 'view' "
        "AND r.code IN ('district_manager', 'state_manager', 'regional_manager')"))).all()
    assert dict(rows) == {
        "district_manager": "org_subtree", "state_manager": "org_subtree",
        "regional_manager": "org_subtree"}


# ── the test plan's RLS row (spec 10) ────────────────────────────────────────

async def test_accounts_reads_and_decides_but_cannot_create_or_edit_an_order(db: AsyncSession) -> None:
    """RLS-8, with Accounts' seeded permissions as they stand (view and approve)."""
    w = await _world(db)
    order = await _order(db, w)
    await _as(db, w.accounts)
    assert (await db.execute(text("SELECT count(*) FROM sales_order WHERE id = CAST(:o AS uuid)"),
                             {"o": order})).scalar_one() == 1
    await _refused(db,
        "INSERT INTO sales_order (order_type, party_name, owner_org_unit_id, territory_id, "
        "seller_gstin_id, place_of_supply_territory_id, place_of_supply_state_id, intra_state, "
        "price_effective_date) SELECT order_type, party_name, owner_org_unit_id, territory_id, "
        "seller_gstin_id, place_of_supply_territory_id, place_of_supply_state_id, intra_state, "
        "price_effective_date FROM sales_order WHERE id = CAST(:o AS uuid)", {"o": order}, "42501")
    changed = (await db.execute(text(
        "UPDATE sales_order SET remarks = 'Accounts note' WHERE id = CAST(:o AS uuid) RETURNING id"),
        {"o": order})).all()
    assert changed == [], "Accounts edited a draft"


async def test_a_district_manager_elsewhere_can_neither_decide_nor_see_the_step(db: AsyncSession) -> None:
    w = await _world(db)
    order = await _order(db, w)
    step = (await _steps(db, await _submit(db, w, order)))[0]
    assert step.role == "district_manager"
    tag = uuid.uuid4().hex[:8]
    elsewhere = str((await db.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, CAST(:p AS uuid)) RETURNING id"),
        {"n": f"m013_far_{tag}", "p": w.state})).scalar_one())
    office = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, CAST(:t AS uuid)) RETURNING id"),
        {"n": f"m013_far_office_{tag}", "t": elsewhere})).scalar_one())
    stranger = await _user(db, "district_manager", office, tag)
    await _as(db, stranger)
    queued = (await db.execute(text(
        "SELECT step_id FROM approval_queue(NULL, NULL, 100, true)"))).scalars().all()
    assert str(step.id) not in {str(s) for s in queued}
    reason = await _refused(db, "SELECT record_decision(CAST(:s AS uuid), 'approve', 'ok')",
                            {"s": str(step.id)}, "42501")
    assert "not_your_step" in reason
    await _as_owner(db)
    assert (await _steps(db, str((await db.execute(text(
        "SELECT id FROM approval_request WHERE entity_id = CAST(:o AS uuid)"),
        {"o": order})).scalar_one())))[0].decision is None


SEEDED_ROLES = ["field_officer", "district_manager", "state_manager", "regional_manager",
                "admin_sales", "md_ceo", "account_manager", "dispatch_manager", "qc_manager",
                "board", "support", "marketing", "state_coordinator", "system",
                "sub_dealer", "dealer", "distributor"]


async def test_every_seeded_role_that_orders_sees_quotations_at_the_same_scope(db: AsyncSession) -> None:
    """Rule 13's assumption: an order from quotations takes their scope, so whoever
    may create an order must see quotations at the same scope kind, or the order
    would land outside the creator's reach (or inside someone else's)."""
    rows = (await db.execute(text(
        "SELECT r.code::text AS role, o.scope::text AS orders, q.scope::text AS quotations "
        "FROM role_permission o JOIN role r ON r.id = o.role_id "
        "LEFT JOIN role_permission q ON q.role_id = o.role_id AND q.module = 'quotations' AND q.action = 'view' "
        "WHERE o.module = 'sales_orders' AND o.action = 'create' AND r.code = ANY(:seeded)"),
        {"seeded": SEEDED_ROLES})).all()
    assert len(rows) >= 5, rows
    assert [r for r in rows if r.orders != r.quotations] == []


async def test_the_list_and_the_open_steps_read_through_their_indexes(db: AsyncSession) -> None:
    """Spec 10's EXPLAIN row, under app_role so the policy's predicates are in the plan."""
    w = await _world(db)
    await db.execute(text("SET LOCAL enable_seqscan = off"))
    await _as(db, w.admin)
    plan = (await db.execute(text(
        "EXPLAIN SELECT id FROM sales_order WHERE deleted_at IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT 51"))).scalars().all()
    assert any("ix_sales_order_list" in line for line in plan), plan
    await _as_owner(db)
    plan = (await db.execute(text(
        "EXPLAIN SELECT s.id FROM approval_step s JOIN approval_request q ON q.id = s.request_id "
        "AND q.status = 'pending' WHERE s.decision IS NULL"))).scalars().all()
    assert any("ix_approval_step_open" in line or "ix_approval_step_role_open" in line
               or "ix_approval_request_pending" in line for line in plan), plan


# ── code review findings (FS-011 9.4) ────────────────────────────────────────

async def test_a_null_ceiling_below_the_top_ends_the_chain_there(db: AsyncSession) -> None:
    """F-5: null is "no ceiling", so a District Manager with none approves any amount
    and the chain does not walk on to the State Manager."""
    w = await _world(db)
    await db.execute(text(
        "INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount) "
        "SELECT 'sales_order', id, CAST(:s AS uuid), NULL FROM role WHERE code = 'district_manager'"),
        {"s": w.state})
    chain = (await db.execute(text(
        "SELECT array_agg(r.code::text ORDER BY x.n) FROM unnest(approval_chain('sales_order', "
        "900000, CAST(:t AS uuid), 0)) WITH ORDINALITY x(id, n) JOIN role r ON r.id = x.id"),
        {"t": w.district})).scalar_one()
    assert chain == ["district_manager", "account_manager", "dispatch_manager"], chain


async def test_cancel_checks_the_expected_status_under_its_own_lock(db: AsyncSession) -> None:
    """F-3: the screen's status is compared after the definer locks the row, so a
    decision that landed first is reported, not overridden."""
    w = await _world(db)
    order = await _order(db, w)
    await _submit(db, w, order)
    await _as(db, w.officer)
    reason = await _refused(db, "SELECT order_cancel(CAST(:o AS uuid), 'x', 'draft')",
                            {"o": order}, "ORDSC")
    assert "submitted" in reason
    await db.execute(text("SELECT order_cancel(CAST(:o AS uuid), 'Party withdrew', 'submitted')"),
                     {"o": order})
    await _as_owner(db)
    assert await _status(db, order) == "cancelled"


async def test_a_soft_deleted_draft_cannot_be_submitted_cancelled_deleted_or_claimed(
        db: AsyncSession) -> None:
    """F-7: order_visible() admits a deleted row for a holder of delete; the writing
    definers refuse it themselves."""
    w = await _world(db)
    order = await _order(db, w)
    await _as(db, w.admin)
    await db.execute(text("SELECT order_delete(CAST(:o AS uuid))"), {"o": order})
    await _refused(db, "SELECT order_delete(CAST(:o AS uuid))", {"o": order}, "ORDNF")
    await _refused(db, "SELECT order_submit(CAST(:o AS uuid))", {"o": order}, "ORDNF")
    await _refused(db, "SELECT order_cancel(CAST(:o AS uuid), 'x')", {"o": order}, "ORDNF")
    await _refused(db, "SELECT order_quotations_claim(CAST(:o AS uuid), ARRAY[]::uuid[])",
                   {"o": order}, "ORDNS")
    await _as_owner(db)
    events = (await db.execute(text(
        "SELECT count(*) FROM activity_event WHERE entity_id = CAST(:o AS uuid) "
        "AND kind = 'order.deleted'"), {"o": order})).scalar_one()
    assert events == 1
