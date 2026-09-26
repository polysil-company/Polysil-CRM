"""Migration 016 (FS-012): the order messages, written by the approval definers in
the decision's own transaction, and the PDF queued on approval. The world is
migration 013's: a coded state, a district, one office, one user per seeded role.
Staff mobiles are set here, since staff sign in by email and have none by default."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13

pytestmark = [pytest.mark.db, pytest.mark.rls]


def _mobile() -> str:
    return "9197" + f"{uuid.uuid4().int % 10**8:08d}"


async def _give_mobile(db: AsyncSession, user: str) -> str:
    m = _mobile()
    await db.execute(text("UPDATE app_user SET mobile = :m WHERE id = CAST(:u AS uuid)"), {"m": m, "u": user})
    return "+" + m


async def _rows(db: AsyncSession, key: str, recipient: str | None = None) -> list[Any]:
    return list((await db.execute(text(
        "SELECT recipient, payload FROM notification_outbox WHERE template_key = :k "
        "AND (CAST(:r AS text) IS NULL OR recipient = :r) AND created_at > now() - interval '1 minute' "
        "ORDER BY created_at"), {"k": key, "r": recipient})).all())


@pytest.mark.parametrize(("value", "printed"), [
    ("123456.5", "1,23,456.50"), ("1000", "1,000.00"), ("999", "999.00"),
    ("10000000", "1,00,00,000.00"), ("0.004", "0.00"), ("-2500.555", "-2,500.56")])
async def test_money_prints_in_the_indian_grouping(db: AsyncSession, value: str, printed: str) -> None:
    assert (await db.execute(text("SELECT inr_text(CAST(:v AS numeric))"), {"v": value})).scalar_one() == printed


async def test_the_chain_alerts_each_step_and_the_outcome_reaches_buyer_and_owner(db: AsyncSession) -> None:
    w = await m13._world(db)
    dm = await _give_mobile(db, w.dm)
    accounts = await _give_mobile(db, w.accounts)
    dispatcher = await _give_mobile(db, w.dispatcher)
    officer = await _give_mobile(db, w.officer)
    order = await m13._order(db, w)
    request = await m13._submit(db, w, order)
    steps = await m13._steps(db, request)
    assert [s.role for s in steps] == ["district_manager", "account_manager", "dispatch_manager"]

    waiting = await _rows(db, "approval.waiting")
    assert [r.recipient for r in waiting] == [dm], "step 1 alerts the District Manager only"
    p = waiting[0].payload
    assert p["_template"] == "polysil_approval_waiting" and p["approver_name"] == "district_manager"
    assert p["total"] == "52,500.00" and p["order_no"].startswith("SO/"), "money as a string (EC-6)"
    assert not await _rows(db, "approval.waiting", officer), "never the requester or owner (EC-2)"

    await m13._decide(db, w.dm, steps[0].id)
    assert [r.recipient for r in await _rows(db, "approval.waiting", accounts)] == [accounts]
    await m13._decide(db, w.accounts, steps[1].id)
    assert [r.recipient for r in await _rows(db, "approval.waiting", dispatcher)] == [dispatcher]
    await m13._decide(db, w.dispatcher, steps[2].id)

    confirmed = await _rows(db, "order.confirmed")
    assert [r.recipient for r in confirmed] == ["+919800000000"]
    assert confirmed[0].payload["party_name"] == "Farmer"
    decided = await _rows(db, "order.decided", officer)
    assert [r.payload["outcome"] for r in decided] == ["approved"]
    state, conf = (await db.execute(text(
        "SELECT o.pdf_state, (SELECT e.payload->>'confirmation' FROM activity_event e WHERE e.entity_id = o.id "
        "AND e.kind = 'order.approved') FROM sales_order o WHERE o.id = CAST(:o AS uuid)"), {"o": order})).one()
    assert (state, conf) == ("pending", "queued")


async def test_a_return_tells_the_owner_and_a_resubmit_does_not_alert_twice(db: AsyncSession) -> None:
    w = await m13._world(db)
    dm = await _give_mobile(db, w.dm)
    officer = await _give_mobile(db, w.officer)
    order = await m13._order(db, w)
    request = await m13._submit(db, w, order)
    step = (await m13._steps(db, request))[0]
    await m13._decide(db, w.dm, step.id, "reject", "Rate too low")
    assert [r.payload["outcome"] for r in await _rows(db, "order.decided", officer)] == ["returned for changes"]
    assert not await _rows(db, "order.confirmed")
    await m13._submit(db, w, order)
    assert len(await _rows(db, "approval.waiting", dm)) == 1, "one alert per person per step per hour (EC-3)"


async def test_a_disabled_template_and_a_missing_mobile_write_nothing(db: AsyncSession) -> None:
    w = await m13._world(db)
    # the District Manager has a mobile, so only the switch keeps the alert back
    await _give_mobile(db, w.dm)
    await _give_mobile(db, w.accounts)
    await db.execute(text("UPDATE message_template SET enabled = false WHERE key = 'approval.waiting'"))
    order = await m13._order(db, w)
    await db.execute(text("UPDATE sales_order SET party_mobile = NULL WHERE id = CAST(:o AS uuid)"), {"o": order})
    request = await m13._submit(db, w, order)
    assert not await _rows(db, "approval.waiting"), "disabled: no row at all (rule 3)"
    who = {"district_manager": w.dm, "account_manager": w.accounts, "dispatch_manager": w.dispatcher}
    for s in await m13._steps(db, request):
        await m13._decide(db, who[s.role], s.id)
    conf = (await db.execute(text(
        "SELECT payload->>'confirmation' FROM activity_event WHERE entity_id = CAST(:o AS uuid) "
        "AND kind = 'order.approved'"), {"o": order})).scalar_one()
    assert conf == "no_mobile" and not await _rows(db, "order.confirmed")


async def test_app_role_cannot_write_the_pdf_columns_or_queue_an_order_message(db: AsyncSession) -> None:
    w = await m13._world(db)
    order = await m13._order(db, w)
    await m13._as(db, w.officer)
    await m13._refused(db, "UPDATE sales_order SET pdf_state = 'ready' WHERE id = CAST(:o AS uuid)",
                       {"o": order}, "42501")
    await m13._refused(db, "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
                           "VALUES ('whatsapp', 'order.confirmed', '+919800000000', '{}')", {}, "42501")


async def test_a_manager_who_submits_is_not_alerted_for_their_own_step(db: AsyncSession) -> None:
    """EC-2: the District Manager submits an officer's order; the step is theirs by
    role, but they may not decide it, so the other District Manager is alerted."""
    w = await m13._world(db)
    submitter = await _give_mobile(db, w.dm)
    other = await m13._user(db, "district_manager", w.office, uuid.uuid4().hex[:8])
    colleague = await _give_mobile(db, other)
    order = await m13._order(db, w)
    await m13._submit(db, w, order, by=w.dm)
    recipients = [r.recipient for r in await _rows(db, "approval.waiting")]
    assert colleague in recipients and submitter not in recipients, recipients



async def test_owner_creator_and_submitter_are_each_left_out_and_other_offices_are_not_alerted(
        db: AsyncSession) -> None:
    """Code review F-1: three different people, so each exclusion is tested alone,
    and a District Manager in another office, who must never hear of the order."""
    w = await m13._world(db)
    tag = uuid.uuid4().hex[:8]
    far_district = str((await db.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, CAST(:p AS uuid)) "
        "RETURNING id"), {"n": f"m013_district_far_{tag}", "p": w.state})).scalar_one())
    far_office = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, CAST(:t AS uuid)) "
        "RETURNING id"), {"n": f"m013_office_far_{tag}", "t": far_district})).scalar_one())
    far_dm = await _give_mobile(db, await m13._user(db, "district_manager", far_office, "f" + tag))
    creator = await m13._user(db, "district_manager", w.office, "c" + tag)
    creator_mobile = await _give_mobile(db, creator)
    dm = await _give_mobile(db, w.dm)
    owner_mobile = await _give_mobile(db, w.accounts)
    other_accounts = await _give_mobile(db, await m13._user(db, "account_manager", w.office, "a" + tag))

    order = await m13._order(db, w, owner=w.accounts)
    await db.execute(text("UPDATE sales_order SET created_by = CAST(:c AS uuid) WHERE id = CAST(:o AS uuid)"),
                     {"c": creator, "o": order})
    request = await m13._submit(db, w, order, by=w.sm)
    step1 = [r.recipient for r in await _rows(db, "approval.waiting")]
    assert dm in step1, step1
    assert creator_mobile not in step1, "the creator is left out"
    assert far_dm not in step1, "a District Manager of another office is never alerted"

    steps = await m13._steps(db, request)
    await m13._decide(db, w.dm, steps[0].id)
    step2 = [r.recipient for r in await _rows(db, "approval.waiting")]
    assert other_accounts in step2, step2
    assert owner_mobile not in step2, "the owner is left out"

# ── the order PDF render lease ───────────────────────────────────────────────

SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"


async def _approved(db: AsyncSession) -> tuple[Any, str]:
    w = await m13._world(db)
    order = await m13._order(db, w)
    request = await m13._submit(db, w, order)
    who = {"district_manager": w.dm, "account_manager": w.accounts, "dispatch_manager": w.dispatcher}
    for s in await m13._steps(db, request):
        await m13._decide(db, who[s.role], s.id)
    # the claim takes any due order; another test's committed one would be claimed
    # first when the API tests run alongside. Set them aside, in this transaction only.
    await db.execute(text(
        "UPDATE sales_order SET pdf_next_attempt_at = now() + interval '1 day' "
        "WHERE pdf_state = 'pending' AND id <> CAST(:o AS uuid)"), {"o": order})
    return w, order


async def _claim(db: AsyncSession) -> dict[str, Any] | None:
    await m13._as(db, SYSTEM_USER_ID)
    doc = (await db.execute(text("SELECT order_render_claim(interval '5 minutes')"))).scalar_one()
    await m13._as_owner(db)
    return doc


async def _pdf(db: AsyncSession, order: str) -> Any:
    return (await db.execute(text(
        "SELECT pdf_state, pdf_key, pdf_error, pdf_attempts, pdf_next_attempt_at > now() AS later "
        "FROM sales_order WHERE id = CAST(:o AS uuid)"), {"o": order})).one()


async def test_the_worker_claims_an_approved_order_and_a_stale_lease_writes_nothing(db: AsyncSession) -> None:
    _, order = await _approved(db)
    doc = await _claim(db)
    assert doc is not None and doc["order"]["id"] == order
    o = doc["order"]
    assert o["total"] == 52500 and o["payment_terms"] and o["place_of_supply"], o
    assert not {"remarks", "cancel_remark", "close_remark", "pdf_lease"} & o.keys(), "rule 9"
    assert [line["line_no"] for line in doc["lines"]] == [1]
    assert await _claim(db) is None, "a live lease is not claimed twice"

    await m13._as(db, SYSTEM_USER_ID)
    stale = (await db.execute(text("SELECT order_render_done(CAST(:o AS uuid), gen_random_uuid(), 'x')"),
                              {"o": order})).scalar_one()
    done = (await db.execute(text("SELECT order_render_done(CAST(:o AS uuid), CAST(:l AS uuid), 'orders/k.pdf')"),
                             {"o": order, "l": doc["lease_token"]})).scalar_one()
    await m13._as_owner(db)
    assert (stale, done) == (False, True)
    p = await _pdf(db, order)
    assert (p.pdf_state, p.pdf_key, p.pdf_attempts) == ("ready", "orders/k.pdf", 1)


async def test_a_failed_render_backs_off_and_the_fifth_gives_up(db: AsyncSession) -> None:
    _, order = await _approved(db)
    doc = await _claim(db)
    assert doc is not None
    await m13._as(db, SYSTEM_USER_ID)
    await db.execute(text("SELECT order_render_failed(CAST(:o AS uuid), CAST(:l AS uuid), 'boom')"),
                     {"o": order, "l": doc["lease_token"]})
    await m13._as_owner(db)
    p = await _pdf(db, order)
    assert (p.pdf_state, p.pdf_error, p.later) == ("pending", "boom", True)
    assert await _claim(db) is None, "backed off"

    await db.execute(text("UPDATE sales_order SET pdf_attempts = 5, pdf_next_attempt_at = now() - interval '1 second' "
                          "WHERE id = CAST(:o AS uuid)"), {"o": order})
    assert await _claim(db) is None
    p = await _pdf(db, order)
    assert p.pdf_state == "failed" and p.pdf_error.startswith("render abandoned after 5 attempts: boom")


async def test_a_cancelled_order_is_not_rendered(db: AsyncSession) -> None:
    w, order = await _approved(db)
    # the State Manager holds sales_orders.delete, which cancelling an approved order needs
    await m13._as(db, w.sm)
    await db.execute(text("SELECT order_cancel(CAST(:o AS uuid), 'Customer postponed')"), {"o": order})
    await m13._as_owner(db)
    assert (await _pdf(db, order)).pdf_state == "pending", "cancelled while the PDF was queued"
    assert await _claim(db) is None


async def test_only_the_system_principal_renders_orders(db: AsyncSession) -> None:
    w, order = await _approved(db)
    await m13._as(db, w.officer)
    await m13._refused(db, "SELECT order_render_claim(interval '5 minutes')", {}, "42501")
    await m13._refused(db, "SELECT order_render_done(CAST(:o AS uuid), gen_random_uuid(), 'x')",
                       {"o": order}, "42501")
    await m13._refused(db, "SELECT order_render_failed(CAST(:o AS uuid), gen_random_uuid(), 'x')",
                       {"o": order}, "42501")


async def test_orders_approved_before_the_migration_are_queued_and_nobody_is_messaged(
        db: AsyncSession) -> None:
    """Cross-vendor review: only an approval sets the PDF state, so an order approved
    before 016 would say "not approved yet" for good. The backfill queues it, leaves
    drafts and cancelled orders alone, and writes no message."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "api/db/migrations/versions/016_order_messages.py"
    spec = importlib.util.spec_from_file_location("m016_for_test", path)
    assert spec and spec.loader
    m16 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m16)

    w, approved = await _approved(db)
    w2, cancelled = await _approved(db)
    await m13._as(db, w2.sm)
    await db.execute(text("SELECT order_cancel(CAST(:o AS uuid), 'x')"), {"o": cancelled})
    await m13._as_owner(db)
    draft = await m13._order(db, w)
    await db.execute(text("UPDATE sales_order SET pdf_state = NULL, pdf_next_attempt_at = NULL "
                          "WHERE id IN (CAST(:a AS uuid), CAST(:c AS uuid))"), {"a": approved, "c": cancelled})
    before = (await db.execute(text("SELECT count(*) FROM notification_outbox"))).scalar_one()
    await db.execute(text(m16.BACKFILL))
    states = dict((await db.execute(text(
        "SELECT id::text, pdf_state FROM sales_order WHERE id IN (CAST(:a AS uuid), CAST(:c AS uuid), CAST(:d AS uuid))"),
        {"a": approved, "c": cancelled, "d": draft})).all())
    assert states == {approved: "pending", cancelled: None, draft: None}
    assert (await db.execute(text("SELECT count(*) FROM notification_outbox"))).scalar_one() == before
