"""Migration 012 (FS-005 5): the second enforcer, executed.

The triggers, the checks, the functions' guards and the lease, each run against
the live schema as the role that would run it in production. The service is the
first enforcer; these prove the database refuses what the service only promised
(ADR-039).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from api.domain import quotations as domain
from tests.db.conftest import Fixtures, make_partner_user, make_staff

pytestmark = [pytest.mark.db, pytest.mark.rls]

SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"

DEFINERS = [
    "quotation_allocate_no(text, text)", "quotation_visible(uuid)",
    "quotation_accepted_for_lead(uuid)", "quotation_open_draft(citext)",
    "quotation_next_version(uuid)",
    "lead_lock_for_quotation(uuid, boolean)", "lead_stage_from_quotation(uuid, text)",
    "quotation_public_view(text)", "quotation_public_open(text, text)",
    "quotation_render_claim(interval)", "quotation_render_done(uuid, uuid, text, text)",
    "quotation_render_failed(uuid, uuid, text)", "quotation_expire_due(date)",
    "lead_scope_to_quotations()",
    # the two 006 functions this migration replaces
    "lead_merge(uuid, uuid)", "lead_timeline(uuid, timestamptz, uuid, integer)",
]
INVOKERS = ["quotation_parent_guard()"]
PLAIN = ["refuse_sent_quotation_edit()", "refuse_sent_quotation_line_edit()"]


# ── helpers ──────────────────────────────────────────────────────────────────

async def _as(db: AsyncSession, user_id: str) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id)})
    await enter_role(db, "app_role")


async def _grant(db: AsyncSession, role_id: str, module: str, actions: list[str],
                 scope: str) -> None:
    for action in actions:
        await db.execute(text(
            "INSERT INTO role_permission (role_id, module, action, scope) "
            "VALUES (:r, :m, CAST(:a AS permission_action), CAST(:s AS permission_scope))"),
            {"r": role_id, "m": module, "a": action, "s": scope})


async def _lead(db: AsyncSession, ids: Fixtures, *, owner_user_id: str | None = None,
                stage: str = "qualified") -> str:
    return str((await db.execute(text(
        "INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id, "
        "farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id) "
        "VALUES (:no, CAST(:st AS lead_stage), 'commercial', "
        "(SELECT id FROM mis_system WHERE code='drip'), "
        "(SELECT id FROM lead_source WHERE code='employee'), 'Farmer', :mob, :terr, :ou, :oou) "
        "RETURNING id"),
        {"no": "POL-" + uuid.uuid4().hex[:12], "st": stage,
         "mob": "+9198" + f"{uuid.uuid4().int % 10**8:08d}", "terr": ids.territory_id,
         "ou": owner_user_id, "oou": ids.org_unit_id})).scalar_one())


async def _quotation(db: AsyncSession, ids: Fixtures, lead_id: str, *,
                     owner_user_id: str | None = None, status: str = "draft",
                     quote_no: str | None = None, version: int = 1,
                     valid_until: dt.date | None = None, lines: int = 0) -> str:
    """A quotation as the owner. A sent one carries what the sent-row CHECK asks;
    its lines go in while it is still a draft, then the status moves, because the
    line trigger refuses a write under a sent parent."""
    sent = status != "draft"
    if sent and lines:
        q = await _quotation(db, ids, lead_id, owner_user_id=owner_user_id)
        for _ in range(lines):
            await _line(db, q)
        await db.execute(text(
            "UPDATE quotation SET status = CAST(:status AS quotation_status), sent_at = now(), "
            "valid_until = COALESCE(:until, CURRENT_DATE + 45), share_token = :token, "
            "quote_no = :no, seller_legal_name = 'Polysil', seller_gstin_no = '24AAAAA0000A1Z5', "
            "seller_state_code = 'GJ', pdf_state = 'pending', "
            "pdf_next_attempt_at = now() - interval '1 day' WHERE id = CAST(:q AS uuid)"),
            {"status": status, "until": valid_until, "token": domain.share_token(),
             "no": quote_no or ("QT/T/" + uuid.uuid4().hex[:8]), "q": q})
        return q
    return str((await db.execute(text(
        "INSERT INTO quotation (lead_id, sales_type, owner_user_id, owner_org_unit_id, "
        "territory_id, party_name, party_mobile, seller_gstin_id, place_of_supply_territory_id, "
        "place_of_supply_state_id, intra_state, price_effective_date, status, quote_no, version, "
        "sent_at, valid_until, share_token, seller_legal_name, seller_gstin_no, "
        "seller_state_code, pdf_state) "
        "VALUES (CAST(:lead AS uuid), 'commercial', CAST(:ou AS uuid), CAST(:oou AS uuid), "
        "CAST(:terr AS uuid), 'Farmer', '+919800000000', "
        "(SELECT id FROM seller_gstin ORDER BY is_default DESC LIMIT 1), "
        "CAST(:terr AS uuid), CAST(:terr AS uuid), true, CURRENT_DATE, "
        "CAST(:status AS quotation_status), :no, :ver, "
        "CASE WHEN :sent THEN now() END, "
        "CASE WHEN :sent THEN COALESCE(:until, CURRENT_DATE + 45) END, "
        "CASE WHEN :sent THEN :token END, CASE WHEN :sent THEN 'Polysil' END, "
        "CASE WHEN :sent THEN '24AAAAA0000A1Z5' END, CASE WHEN :sent THEN 'GJ' END, "
        "CASE WHEN :sent THEN 'pending' END) RETURNING id"),
        {"lead": lead_id, "ou": owner_user_id, "oou": ids.org_unit_id,
         "terr": ids.territory_id, "status": status,
         "no": quote_no or ("QT/T/" + uuid.uuid4().hex[:8]) if sent or quote_no else None,
         "ver": version, "sent": sent, "token": domain.share_token(),
         "until": valid_until})).scalar_one())


async def _line(db: AsyncSession, quotation_id: str) -> str:
    return str((await db.execute(text(
        "INSERT INTO quotation_line (quotation_id, line_no, product_id, description, hsn_code, "
        "uom, qty, rate, price_list_id, price_list_item_id, gst_rate_id, gross, discount_pct, "
        "discount1_amt, after_discount1, discount2_pct, discount2_amt, after_discount2, "
        "discount3_pct, discount3_amt, discount, taxable, gst_slab, cgst_rate, sgst_rate, "
        "igst_rate, cgst, sgst, igst, total) "
        "SELECT CAST(:q AS uuid), 1, i.product_id, 'x', '3917', 'NOS', 1, 100, i.price_list_id, "
        "i.id, (SELECT id FROM gst_rate LIMIT 1), 100, 10, 10, 90, 0, 0, 90, 0, 0, 10, 90, 5, "
        "2.5, 2.5, 0, 2.25, 2.25, 0, 94.50 FROM price_list_item i LIMIT 1 RETURNING id"),
        {"q": quotation_id})).scalar_one())


async def _refused(db: AsyncSession, sql: str, params: dict[str, Any], sqlstate: str) -> str:
    """Runs the statement in a savepoint and returns the refusal's message."""
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


# ── the functions ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sig", DEFINERS)
async def test_every_definer_is_pinned_and_definer(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT prosecdef, proconfig FROM pg_proc WHERE oid = CAST(:s AS regprocedure)"),
        {"s": sig})).one()
    assert row.prosecdef is True, sig
    assert row.proconfig and any(c.startswith("search_path=") and "pg_temp" in c
                                 for c in row.proconfig), sig


@pytest.mark.parametrize("sig", INVOKERS + PLAIN)
async def test_the_three_that_are_not_definers_are_still_pinned(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT prosecdef, proconfig FROM pg_proc WHERE oid = CAST(:s AS regprocedure)"),
        {"s": sig})).one()
    assert row.prosecdef is False, sig
    assert row.proconfig and any("pg_temp" in c for c in row.proconfig), sig


@pytest.mark.parametrize("sig", DEFINERS + INVOKERS + PLAIN)
async def test_nothing_new_is_public_executable(db: AsyncSession, sig: str) -> None:
    ok = (await db.execute(text(
        "SELECT has_function_privilege('public', CAST(:s AS regprocedure), 'EXECUTE')"),
        {"s": sig})).scalar_one()
    assert ok is False, sig


async def test_the_counter_has_rls_on_and_no_grants(db: AsyncSession) -> None:
    row = (await db.execute(text(
        "SELECT relrowsecurity, has_table_privilege('app_role', 'quotation_counter', 'SELECT') "
        "FROM pg_class WHERE relname = 'quotation_counter'"))).one()
    assert row[0] is True and row[1] is False


# ── the immutability trigger, column by column ───────────────────────────────

ALLOWED_AFTER_SEND = {
    "viewed_at": "now()", "open_count": "3", "decision_remark": "'ok'",
    "pdf_state": "'ready'", "pdf_key": "'k'", "pdf_error": "'e'", "external_id": "'erp-1'",
    "synced_at": "now()",
}
REFUSED_AFTER_SEND = {
    "party_name": "'Someone Else'", "party_mobile": "'+919811111111'", "terms": "'x'",
    "total": "1", "gross": "1", "price_effective_date": "CURRENT_DATE - 1",
    "seller_legal_name": "'Other Co'", "quote_no": "'QT/X/0'", "share_token": "'t'",
    "valid_until": "CURRENT_DATE + 90", "sent_at": "now() - interval '1 day'",
    # the scope columns and the parents: a real other value, so the refusal is the
    # immutability trigger's and not a FK's or the parent guard's
    "partner_id": "CAST(:dealer AS uuid)",
    "owner_user_id": "CAST(:other_user AS uuid)",
    "owner_org_unit_id": "CAST(:other_org AS uuid)",
    "territory_id": "CAST(:other_terr AS uuid)",
    "lead_id": "CAST(:other_lead AS uuid)",
}


@pytest.mark.parametrize("column", sorted(REFUSED_AFTER_SEND))
async def test_a_sent_quotation_refuses_the_edit(db: AsyncSession, ids: Fixtures,
                                                 column: str) -> None:
    lead = await _lead(db, ids)
    q = await _quotation(db, ids, lead, status="sent")
    other_user = await make_staff(db, ids, email=f"o{uuid.uuid4().hex[:6]}@x.in")
    other_org = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 1, :t) RETURNING id"),
        {"n": ids.unique("other-org"), "t": ids.territory_id})).scalar_one())
    other_terr = str((await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": ids.unique("other-terr")})).scalar_one())
    other_lead = await _lead(db, ids)
    msg = await _refused(
        db, f"UPDATE quotation SET {column} = {REFUSED_AFTER_SEND[column]} "
            f"WHERE id = CAST(:q AS uuid)",
        {"q": q, "dealer": ids.dealer_id, "other_user": other_user, "other_org": other_org,
         "other_terr": other_terr, "other_lead": other_lead}, "23514")
    assert "cannot change" in msg


@pytest.mark.parametrize("column", sorted(ALLOWED_AFTER_SEND))
async def test_a_sent_quotation_still_moves_its_lifecycle_columns(db: AsyncSession, ids: Fixtures,
                                                                  column: str) -> None:
    lead = await _lead(db, ids)
    q = await _quotation(db, ids, lead, status="sent")
    await db.execute(text(f"UPDATE quotation SET {column} = {ALLOWED_AFTER_SEND[column]} "
                          f"WHERE id = CAST(:q AS uuid)"), {"q": q})


async def test_the_status_may_only_move_along_the_table(db: AsyncSession, ids: Fixtures) -> None:
    lead = await _lead(db, ids)
    q = await _quotation(db, ids, lead, status="sent")
    await _refused(db, "UPDATE quotation SET status = 'draft' WHERE id = CAST(:q AS uuid)",
                   {"q": q}, "23514")
    await db.execute(text("UPDATE quotation SET status = 'viewed' WHERE id = CAST(:q AS uuid)"),
                     {"q": q})
    await db.execute(text("UPDATE quotation SET status = 'accepted', accepted_at = now() "
                          "WHERE id = CAST(:q AS uuid)"), {"q": q})
    await _refused(db, "UPDATE quotation SET status = 'rejected' WHERE id = CAST(:q AS uuid)",
                   {"q": q}, "23514")
    # and an accepted row is never superseded
    other = await _quotation(db, ids, lead, status="sent")
    await _refused(db, "UPDATE quotation SET superseded_by_id = CAST(:o AS uuid) "
                       "WHERE id = CAST(:q AS uuid)", {"q": q, "o": other}, "23514")


async def test_the_lines_of_a_sent_quotation_cannot_change(db: AsyncSession, ids: Fixtures) -> None:
    lead = await _lead(db, ids)
    q = await _quotation(db, ids, lead)
    line = await _line(db, q)
    await db.execute(text("UPDATE quotation SET status = 'sent', sent_at = now(), "
                          "valid_until = CURRENT_DATE + 45, share_token = :t, quote_no = :no, "
                          "seller_legal_name = 'P', seller_gstin_no = '24AAAAA0000A1Z5', "
                          "seller_state_code = 'GJ', pdf_state = 'pending' "
                          "WHERE id = CAST(:q AS uuid)"),
                     {"q": q, "t": domain.share_token(),
                      "no": "QT/T/" + uuid.uuid4().hex[:6]})
    await _refused(db, "UPDATE quotation_line SET rate = 1 WHERE id = CAST(:l AS uuid)",
                   {"l": line}, "23514")
    await _refused(db, "DELETE FROM quotation_line WHERE id = CAST(:l AS uuid)", {"l": line},
                   "23514")


# ── the scope columns follow the lead, and only that way ─────────────────────

async def test_scope_moves_only_through_the_lead(db: AsyncSession, ids: Fixtures) -> None:
    """A direct statement runs at trigger depth 1 and is refused; the lead's own
    trigger runs the propagation at depth 2 and is admitted."""
    a = await make_staff(db, ids, email=f"a{uuid.uuid4().hex[:6]}@x.in")
    b = await make_staff(db, ids, email=f"b{uuid.uuid4().hex[:6]}@x.in")
    lead = await _lead(db, ids, owner_user_id=a)
    q = await _quotation(db, ids, lead, owner_user_id=a, status="sent")
    await _refused(db, "UPDATE quotation SET owner_user_id = CAST(:b AS uuid) "
                       "WHERE id = CAST(:q AS uuid)", {"b": b, "q": q}, "23514")
    await db.execute(text("UPDATE lead SET owner_user_id = CAST(:b AS uuid) "
                          "WHERE id = CAST(:l AS uuid)"), {"b": b, "l": lead})
    owner = (await db.execute(text(
        "SELECT owner_user_id FROM quotation WHERE id = CAST(:q AS uuid)"), {"q": q})).scalar_one()
    assert str(owner) == str(b)


async def test_a_survivor_reassignment_reaches_the_merged_losers_quotations(
        db: AsyncSession, ids: Fixtures) -> None:
    """Cross-vendor B-4: A into B into C, then C reassigned; A's quotation follows."""
    a_owner = await make_staff(db, ids, email=f"a{uuid.uuid4().hex[:6]}@x.in")
    new_owner = await make_staff(db, ids, email=f"n{uuid.uuid4().hex[:6]}@x.in")
    survivor = await _lead(db, ids, owner_user_id=a_owner)
    loser_a = await _lead(db, ids, owner_user_id=a_owner)
    loser_b = await _lead(db, ids, owner_user_id=a_owner)
    qa = await _quotation(db, ids, loser_a, owner_user_id=a_owner, status="sent")
    qb = await _quotation(db, ids, loser_b, owner_user_id=a_owner)
    # the flat group lead_merge() leaves behind
    for loser in (loser_a, loser_b):
        await db.execute(text("UPDATE lead SET stage = 'merged', merged_into_id = CAST(:s AS uuid) "
                              "WHERE id = CAST(:l AS uuid)"), {"s": survivor, "l": loser})
    await db.execute(text("UPDATE lead SET owner_user_id = CAST(:n AS uuid) "
                          "WHERE id = CAST(:s AS uuid)"), {"n": new_owner, "s": survivor})
    owners = {str(r[0]) for r in (await db.execute(text(
        "SELECT owner_user_id FROM quotation WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))"),
        {"a": qa, "b": qb})).all()}
    assert owners == {str(new_owner)}


# ── the checks ───────────────────────────────────────────────────────────────

async def test_a_lowercase_gstin_is_refused_by_the_database(db: AsyncSession,
                                                            ids: Fixtures) -> None:
    lead = await _lead(db, ids)
    q = await _quotation(db, ids, lead)
    await _refused(db, "UPDATE quotation SET party_gstin = '24aaacp1234a1z5' "
                       "WHERE id = CAST(:q AS uuid)", {"q": q}, "23514")
    await db.execute(text("UPDATE quotation SET party_gstin = '24AAACP1234A1Z5' "
                          "WHERE id = CAST(:q AS uuid)"), {"q": q})


async def test_the_cascade_identities_are_checked(db: AsyncSession, ids: Fixtures) -> None:
    lead = await _lead(db, ids)
    q = await _quotation(db, ids, lead)
    line = await _line(db, q)
    await _refused(db, "UPDATE quotation_line SET discount1_amt = 11 WHERE id = CAST(:l AS uuid)",
                   {"l": line}, "23514")
    await _refused(db, "UPDATE quotation_line SET total = 1 WHERE id = CAST(:l AS uuid)",
                   {"l": line}, "23514")


async def test_one_open_revision_per_number(db: AsyncSession, ids: Fixtures) -> None:
    lead = await _lead(db, ids)
    no = "QT/T/" + uuid.uuid4().hex[:6]
    await _quotation(db, ids, lead, status="sent", quote_no=no, version=1)
    await _quotation(db, ids, lead, status="draft", quote_no=no, version=2)
    await db.execute(text("SAVEPOINT sp"))
    with pytest.raises(DBAPIError, match="uq_quotation_open_draft"):
        await _quotation(db, ids, lead, status="draft", quote_no=no, version=3)
    await db.execute(text("ROLLBACK TO SAVEPOINT sp"))


# ── the guards, as the roles that would call them ────────────────────────────

async def test_the_system_functions_refuse_a_person(db: AsyncSession, ids: Fixtures) -> None:
    staff = await make_staff(db, ids, email=f"s{uuid.uuid4().hex[:6]}@x.in")
    await _grant(db, ids.staff_role_id, "quotations", ["view", "edit"], "global")
    await _as(db, staff)
    for sql in ("SELECT quotation_expire_due(CURRENT_DATE)",
                "SELECT quotation_render_claim(interval '5 minutes')",
                "SELECT quotation_render_done(gen_random_uuid(), gen_random_uuid(), 'k', 'l')",
                "SELECT quotation_render_failed(gen_random_uuid(), gen_random_uuid(), 'e')"):
        await _refused(db, sql, {}, "42501")


async def test_the_lead_cannot_be_moved_by_someone_holding_only_leads_edit(
        db: AsyncSession, ids: Fixtures) -> None:
    """Cross-vendor B-2: marketing and every portal role hold leads.edit without
    quotations.edit. Called directly, past the routes."""
    lead = await _lead(db, ids, stage="quoted")
    q = await _quotation(db, ids, lead, status="sent")
    await _grant(db, ids.portal_role_id, "leads", ["view", "edit"], "global")
    dealer = await make_partner_user(db, ids, mobile="9198" + f"{uuid.uuid4().int % 10**8:08d}")
    await _as(db, dealer)
    await _refused(db, "SELECT lead_stage_from_quotation(CAST(:q AS uuid), 'quoted')", {"q": q},
                   "42501")
    await _refused(db, "SELECT lead_stage_from_quotation(CAST(:q AS uuid), 'won')", {"q": q},
                   "42501")


async def test_the_lead_moves_only_for_a_quotation_in_the_justifying_state(
        db: AsyncSession, ids: Fixtures) -> None:
    staff = await make_staff(db, ids, email=f"s{uuid.uuid4().hex[:6]}@x.in")
    await _grant(db, ids.staff_role_id, "quotations", ["view", "create", "edit"], "global")
    await _grant(db, ids.staff_role_id, "leads", ["view", "edit"], "global")
    lead = await _lead(db, ids, owner_user_id=staff, stage="qualified")
    q = await _quotation(db, ids, lead, owner_user_id=staff, status="sent")
    await _as(db, staff)
    # sent justifies quoted; accepted would justify won, and the row is sent
    await _refused(db, "SELECT lead_stage_from_quotation(CAST(:q AS uuid), 'won')", {"q": q},
                   "QLBND")
    before = (await db.execute(text("SELECT lead_stage_from_quotation(CAST(:q AS uuid), 'quoted')"),
                               {"q": q})).scalar_one()
    assert before == "qualified"
    stage = (await db.execute(text("SELECT stage::text FROM lead WHERE id = CAST(:l AS uuid)"),
                              {"l": lead})).scalar_one()
    assert stage == "quoted"
    ev = (await db.execute(text(
        "SELECT payload FROM activity_event WHERE lead_id = CAST(:l AS uuid) "
        "AND kind = 'lead.stage_changed'"), {"l": lead})).scalar_one()
    assert ev["via"] == "quotation" and ev["to"] == "quoted"


async def test_lock_for_quotation_refuses_a_closed_lead_only_when_asked(
        db: AsyncSession, ids: Fixtures) -> None:
    staff = await make_staff(db, ids, email=f"s{uuid.uuid4().hex[:6]}@x.in")
    await _grant(db, ids.staff_role_id, "leads", ["view", "edit"], "global")
    lost = await _lead(db, ids, owner_user_id=staff)
    await db.execute(text("UPDATE lead SET stage = 'lost', lost_from_stage = 'qualified', "
                          "lost_reason_id = (SELECT id FROM won_lost_reason WHERE kind = 'lost' "
                          "LIMIT 1) WHERE id = CAST(:l AS uuid)"), {"l": lost})
    await _as(db, staff)
    await _refused(db, "SELECT lead_lock_for_quotation(CAST(:l AS uuid), true)", {"l": lost},
                   "QLNOP")
    stage = (await db.execute(text("SELECT lead_lock_for_quotation(CAST(:l AS uuid), false)"),
                              {"l": lost})).scalar_one()
    assert stage == "lost", "editing or deleting a draft still locks the lead"


# ── the lease ────────────────────────────────────────────────────────────────

async def _as_system(db: AsyncSession) -> None:
    await _as(db, SYSTEM_USER_ID)


async def _as_owner(db: AsyncSession) -> None:
    """Back to the table owner, who sees every row: the system principal holds no
    quotation permission, so a direct read under its claim returns nothing."""
    await db.execute(text("SELECT set_config('role', 'none', true)"))


async def _claim_mine(db: AsyncSession, q: str, *, expect: bool = True) -> Any:
    """Claim until this test's row comes up: other tests' committed rows may be
    pending too, and the claim takes the earliest. Each foreign claim is left
    leased for its five minutes, which changes nothing they assert."""
    for _ in range(20):
        doc = (await db.execute(text("SELECT quotation_render_claim(interval '5 minutes')"))
               ).scalar_one()
        if doc is None or str(doc["quotation"]["id"]) == q:
            if expect:
                assert doc is not None and str(doc["quotation"]["id"]) == q
            return doc
        # a foreign row: hand its lease back so the next tick sees it as it was
        await db.execute(text(
            "SELECT quotation_render_failed(CAST(:id AS uuid), CAST(:t AS uuid), 'test skip')"),
            {"id": str(doc["quotation"]["id"]), "t": str(doc["lease_token"])})
    raise AssertionError("the row was never claimed")


async def test_the_claim_charges_once_and_the_lease_is_conditional(
        db: AsyncSession, ids: Fixtures) -> None:
    lead = await _lead(db, ids)
    q = await _quotation(db, ids, lead, status="sent", lines=1)
    await _as_system(db)
    doc = await _claim_mine(db, q)
    assert doc["attempt"] == 1 and doc["quotation"]["share_token"] and len(doc["lines"]) == 1
    assert "pdf_lease_token" not in doc["quotation"]
    await _as_owner(db)
    row = (await db.execute(text("SELECT pdf_state, pdf_attempts, pdf_lease_until FROM quotation "
                                 "WHERE id = CAST(:q AS uuid)"), {"q": q})).one()
    assert row.pdf_state == "rendering" and row.pdf_attempts == 1 and row.pdf_lease_until
    # this row is not claimable again while the lease holds
    await _as_system(db)
    assert await _claim_mine(db, q, expect=False) is None
    # a stale token writes nothing
    stale = (await db.execute(text(
        "SELECT quotation_render_done(CAST(:q AS uuid), gen_random_uuid(), 'k', 'l')"),
        {"q": q})).scalar_one()
    assert stale is False
    # the right one closes it and queues the message
    ok = (await db.execute(text(
        "SELECT quotation_render_done(CAST(:q AS uuid), CAST(:t AS uuid), 'k', 'http://x/q/t')"),
        {"q": q, "t": doc["lease_token"]})).scalar_one()
    assert ok is True
    await _as_owner(db)
    row = (await db.execute(text("SELECT pdf_state, pdf_key, pdf_attempts FROM quotation "
                                 "WHERE id = CAST(:q AS uuid)"), {"q": q})).one()
    assert (row.pdf_state, row.pdf_key, row.pdf_attempts) == ("ready", "k", 1)


async def test_a_failure_backs_off_without_charging_again_and_gives_up_at_five(
        db: AsyncSession, ids: Fixtures) -> None:
    lead = await _lead(db, ids)
    q = await _quotation(db, ids, lead, status="sent", lines=1)
    await _as_system(db)
    doc = await _claim_mine(db, q)
    ok = (await db.execute(text(
        "SELECT quotation_render_failed(CAST(:q AS uuid), CAST(:t AS uuid), 'boom')"),
        {"q": q, "t": doc["lease_token"]})).scalar_one()
    assert ok is True
    await _as_owner(db)
    row = (await db.execute(text(
        "SELECT pdf_state, pdf_attempts, pdf_error, "
        "pdf_next_attempt_at > now() + interval '20 seconds' AS backed_off "
        "FROM quotation WHERE id = CAST(:q AS uuid)"), {"q": q})).one()
    assert (row.pdf_state, row.pdf_attempts, row.pdf_error, row.backed_off) == (
        "pending", 1, "boom", True)
    # an expired lease is reclaimed with the charge already recorded
    await db.execute(text("UPDATE quotation SET pdf_state = 'rendering', "
                          "pdf_lease_until = now() - interval '1 second', "
                          "pdf_lease_token = gen_random_uuid() WHERE id = CAST(:q AS uuid)"),
                     {"q": q})
    await _as_system(db)
    doc = await _claim_mine(db, q)
    assert doc["attempt"] == 2
    # five attempts: the claim marks it failed and returns nothing
    await _as_owner(db)
    await db.execute(text("UPDATE quotation SET pdf_state = 'pending', pdf_attempts = 5, "
                          "pdf_next_attempt_at = now() - interval '1 day' "
                          "WHERE id = CAST(:q AS uuid)"), {"q": q})
    await _as_system(db)
    assert await _claim_mine(db, q, expect=False) is None
    await _as_owner(db)
    row = (await db.execute(text(
        "SELECT pdf_state, pdf_error FROM quotation WHERE id = CAST(:q AS uuid)"), {"q": q})).one()
    assert row.pdf_state == "failed" and "abandoned after 5" in row.pdf_error


# ── the nightly expiry ───────────────────────────────────────────────────────

async def test_expiry_takes_the_date_it_is_given_and_skips_superseded_rows(
        db: AsyncSession, ids: Fixtures) -> None:
    lead = await _lead(db, ids)
    yesterday = dt.date.today() - dt.timedelta(days=1)
    due = await _quotation(db, ids, lead, status="sent", valid_until=yesterday)
    fresh = await _quotation(db, ids, lead, status="sent")
    superseded = await _quotation(db, ids, lead, status="sent", valid_until=yesterday)
    newer = await _quotation(db, ids, lead, status="sent")
    await db.execute(text("UPDATE quotation SET superseded_by_id = CAST(:n AS uuid) "
                          "WHERE id = CAST(:s AS uuid)"), {"n": newer, "s": superseded})
    await _as_system(db)
    count = (await db.execute(text("SELECT quotation_expire_due(:today)"),
                              {"today": dt.date.today()})).scalar_one()
    assert count >= 1
    await _as_owner(db)
    states = {str(r[0]): r[1] for r in (await db.execute(text(
        "SELECT id, status::text FROM quotation WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid), "
        "CAST(:c AS uuid))"), {"a": due, "b": fresh, "c": superseded})).all()}
    assert states[due] == "expired" and states[fresh] == "sent" and states[superseded] == "sent"
    # the same date again finds nothing of this test's
    await _as_system(db)
    again = (await db.execute(text("SELECT quotation_expire_due(:today)"),
                              {"today": dt.date.today()})).scalar_one()
    await _as_owner(db)
    still = (await db.execute(
        text("SELECT status::text FROM quotation WHERE id = CAST(:f AS uuid)"),
        {"f": fresh})).scalar_one()
    assert still == "sent" and again >= 0


# ── the timeline's own filter ────────────────────────────────────────────────

async def test_the_timeline_hides_a_direct_sale_from_the_dealer_on_its_own_lead(
        db: AsyncSession, ids: Fixtures) -> None:
    """Rule 17, edge case 10 (code review F-2): lead_timeline() is a definer, so
    the event policy does not apply inside it, and its own quotation_visible()
    filter is the whole of the rule. The dealer sees the lead assigned to it and
    the quotation routed through it, and neither the direct sale on that lead nor
    that sale's events. Deleting the filter clause turns the last assertion red."""
    await _grant(db, ids.portal_role_id, "leads", ["view"], "partner_subtree")
    await _grant(db, ids.portal_role_id, "quotations", ["view"], "partner_subtree")
    dealer = await make_partner_user(db, ids, mobile="9198" + f"{uuid.uuid4().int % 10**8:08d}")
    actor = await make_staff(db, ids, email=f"tl{uuid.uuid4().hex[:6]}@x.in")
    lead = await _lead(db, ids, stage="quoted")
    await db.execute(text("UPDATE lead SET assigned_partner_id = CAST(:d AS uuid) "
                          "WHERE id = CAST(:l AS uuid)"), {"d": ids.dealer_id, "l": lead})
    direct = await _quotation(db, ids, lead, status="sent", lines=1)
    routed = await _quotation(db, ids, lead)
    await db.execute(text("UPDATE quotation SET partner_id = CAST(:d AS uuid) "
                          "WHERE id = CAST(:q AS uuid)"), {"d": ids.dealer_id, "q": routed})
    await _line(db, routed)
    await db.execute(text(
        "UPDATE quotation SET status = 'sent', sent_at = now(), valid_until = CURRENT_DATE + 45, "
        "share_token = :token, quote_no = :no, seller_legal_name = 'Polysil', "
        "seller_gstin_no = '24AAAAA0000A1Z5', seller_state_code = 'GJ', pdf_state = 'pending' "
        "WHERE id = CAST(:q AS uuid)"),
        {"token": domain.share_token(), "no": "QT/T/" + uuid.uuid4().hex[:8], "q": routed})
    for q in (direct, routed):
        await db.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
            "VALUES ('quotation', CAST(:q AS uuid), CAST(:l AS uuid), 'quotation.sent', "
            "CAST(:a AS uuid), '{}')"), {"q": q, "l": lead, "a": str(actor)})
    await _as(db, dealer)
    assert (await db.execute(text("SELECT lead_visible(CAST(:l AS uuid))"),
                             {"l": lead})).scalar_one(), "the dealer sees its own lead"
    visible = {q: (await db.execute(text("SELECT quotation_visible(CAST(:q AS uuid))"),
                                    {"q": q})).scalar_one() for q in (direct, routed)}
    assert visible == {direct: False, routed: True}, visible
    seen = {str(r.entity_id) for r in (await db.execute(text(
        "SELECT entity_id FROM lead_timeline(CAST(:l AS uuid), NULL, NULL, 50) "
        "WHERE entity_type = 'quotation'"), {"l": lead})).all()}
    assert seen == {routed}, "the direct sale's events are not on the dealer's timeline"



async def test_a_line_cannot_be_moved_out_of_a_sent_quotation(
        db: AsyncSession, ids: Fixtures) -> None:
    """Cross-vendor A-2: the trigger checked only the destination, so an editor
    could re-parent a sent quotation's line into a draft and empty the document."""
    staff = await make_staff(db, ids, email=f"mv{uuid.uuid4().hex[:6]}@x.in")
    await _grant(db, ids.staff_role_id, "quotations", ["view", "edit"], "global")
    await _grant(db, ids.staff_role_id, "leads", ["view", "edit"], "global")
    lead = await _lead(db, ids, owner_user_id=staff, stage="quoted")
    sent = await _quotation(db, ids, lead, owner_user_id=staff, status="sent", lines=1)
    draft = await _quotation(db, ids, lead, owner_user_id=staff)
    line = (await db.execute(text("SELECT id FROM quotation_line WHERE quotation_id = "
                                  "CAST(:q AS uuid)"), {"q": sent})).scalar_one()
    await _as(db, staff)
    await _refused(db, "UPDATE quotation_line SET quotation_id = CAST(:d AS uuid) "
                       "WHERE id = CAST(:l AS uuid)", {"d": draft, "l": str(line)}, "23514")
