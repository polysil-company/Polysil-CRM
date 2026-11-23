"""092 (FS-091): the order render claim carries the approval trail for the internal
copy, and owes an internal copy to an order already ready without re-rendering its
customer copy. Each test runs in its own rolled-back transaction."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db.test_migration_016 import SYSTEM_USER_ID, _approved, _claim

pytestmark = pytest.mark.db

RETURNED = "Rate below the district floor"


async def _row(db: AsyncSession, order: str) -> Any:
    return (await db.execute(text(
        "SELECT pdf_state, pdf_key, pdf_internal_key, pdf_attempts, pdf_internal_attempts, "
        "pdf_internal_error, pdf_error, pdf_lease FROM sales_order "
        "WHERE id = CAST(:o AS uuid)"), {"o": order})).one()


async def _system(db: AsyncSession, sql: str, params: dict[str, Any]) -> Any:
    await m13._as(db, SYSTEM_USER_ID)
    out = (await db.execute(text(sql), params)).scalar_one()
    await m13._as_owner(db)
    return out


async def _done(db: AsyncSession, order: str, lease: str, key: str | None,
                internal: str | None) -> bool:
    return bool(await _system(
        db, "SELECT order_render_done(CAST(:o AS uuid), CAST(:l AS uuid), :k, :i)",
        {"o": order, "l": lease, "k": key, "i": internal}))


async def _ready_owing(db: AsyncSession, order: str) -> None:
    """An order rendered before 092: ready, a customer copy, no internal copy."""
    await db.execute(text(
        "UPDATE sales_order SET pdf_state = 'ready', pdf_key = 'orders/old.pdf', "
        "pdf_internal_key = NULL, pdf_lease = NULL, pdf_lease_until = NULL, "
        "pdf_next_attempt_at = NULL WHERE id = CAST(:o AS uuid)"), {"o": order})


async def test_the_claim_carries_every_round_with_its_remarks_outside_the_order(
        db: AsyncSession) -> None:
    w = await m13._world(db)
    order = await m13._order(db, w)
    await db.execute(text("UPDATE sales_order SET remarks = 'Deliver before sowing' "
                          "WHERE id = CAST(:o AS uuid)"), {"o": order})
    first = await m13._submit(db, w, order)
    step = (await m13._steps(db, first))[0]
    await m13._decide(db, w.dm, step.id, decision="reject", remark=RETURNED)
    # one transaction stamps both rounds alike; rounds are separate transactions live
    await db.execute(text("UPDATE approval_request SET created_at = created_at - interval '1 hour' "
                          "WHERE id = CAST(:r AS uuid)"), {"r": first})
    second = await m13._submit(db, w, order)
    who = {"district_manager": w.dm, "account_manager": w.accounts,
           "dispatch_manager": w.dispatcher}
    for s in await m13._steps(db, second):
        await m13._decide(db, who[s.role], s.id, remark=f"ok from {s.role}")
    await db.execute(text(
        "UPDATE sales_order SET pdf_next_attempt_at = now() + interval '1 day' "
        "WHERE (pdf_state = 'pending' OR (pdf_state = 'ready' AND pdf_internal_key IS NULL)) "
        "AND id <> CAST(:o AS uuid)"), {"o": order})

    doc = await _claim(db)
    assert doc is not None and doc["order"]["id"] == order and doc["mode"] == "both"
    assert not {"remarks", "amend_reason", "amended_from_total", "pdf_internal_error",
                "pdf_lease"} & doc["order"].keys(), "rule 1: nothing internal in `order`"
    internal = doc["internal"]
    assert internal["remarks"] == "Deliver before sowing"
    rounds = internal["approvals"]
    assert [(r["round"], r["status"]) for r in rounds] == [(1, "rejected"), (2, "approved")]
    assert rounds[0]["amount"] == "52500.00"
    one = rounds[0]["steps"]
    assert (one[0]["decision"], one[0]["remark"], one[0]["role"]) == \
        ("reject", RETURNED, "District Manager")
    assert one[0]["by"] and one[0]["decided_role"] is None
    assert all(s["decision"] is None for s in one[1:]), "later steps were not reached"
    assert [s["remark"] for s in rounds[1]["steps"]] == [
        "ok from district_manager", "ok from account_manager", "ok from dispatch_manager"]
    assert rounds[0]["requested_by"]


async def test_a_pending_order_is_claimed_before_one_owing_its_internal_copy(
        db: AsyncSession) -> None:
    """EC-4: fresh approvals go first."""
    _, owing = await _approved(db)
    await _ready_owing(db, owing)
    _, fresh = await _approved(db)
    # _approved set every other owing order aside, this one too
    await db.execute(text("UPDATE sales_order SET pdf_next_attempt_at = NULL "
                          "WHERE id = CAST(:o AS uuid)"), {"o": owing})
    first = await _claim(db)
    assert first is not None and (first["order"]["id"], first["mode"]) == (fresh, "both")
    second = await _claim(db)
    assert second is not None and (second["order"]["id"], second["mode"]) == (owing, "internal")
    assert await _claim(db) is None


async def test_mode_internal_leaves_the_customer_copy_alone(db: AsyncSession) -> None:
    """EC-1: pdf_state stays ready and pdf_key is kept, through the claim and the done."""
    _, order = await _approved(db)
    await _ready_owing(db, order)
    doc = await _claim(db)
    assert doc is not None and doc["mode"] == "internal" and doc["attempt"] == 1
    r = await _row(db, order)
    assert (r.pdf_state, r.pdf_key, r.pdf_attempts, r.pdf_internal_attempts) == \
        ("ready", "orders/old.pdf", 0, 1)
    assert await _claim(db) is None, "a live lease is not claimed twice"

    assert not await _done(db, order, doc["lease_token"], "orders/new.pdf", "orders/i.pdf"), \
        "a key in mode internal would republish the customer copy"
    assert await _done(db, order, doc["lease_token"], None, "orders/i.pdf")
    r = await _row(db, order)
    assert (r.pdf_state, r.pdf_key, r.pdf_internal_key, r.pdf_lease) == \
        ("ready", "orders/old.pdf", "orders/i.pdf", None)


async def test_mode_both_publishes_the_customer_copy_without_an_internal_one(
        db: AsyncSession) -> None:
    """Plan review R-4: the internal copy failed; branch 2 owes it afterwards."""
    _, order = await _approved(db)
    doc = await _claim(db)
    assert doc is not None and doc["mode"] == "both"
    assert await _done(db, order, doc["lease_token"], "orders/c.pdf", None)
    r = await _row(db, order)
    assert (r.pdf_state, r.pdf_key, r.pdf_internal_key) == ("ready", "orders/c.pdf", None)
    again = await _claim(db)
    assert again is not None and (again["order"]["id"], again["mode"]) == (order, "internal")


async def test_done_refuses_nothing_rendered_and_a_stale_lease(db: AsyncSession) -> None:
    _, order = await _approved(db)
    doc = await _claim(db)
    assert doc is not None
    await m13._as(db, SYSTEM_USER_ID)
    await m13._refused(db, "SELECT order_render_done(CAST(:o AS uuid), CAST(:l AS uuid), "
                           "NULL, NULL)", {"o": order, "l": doc["lease_token"]}, "22004")
    await m13._as_owner(db)
    assert not await _done(db, order, "00000000-0000-0000-0000-000000000000", "k", "i")


async def test_an_internal_failure_charges_only_the_internal_copy(db: AsyncSession) -> None:
    _, order = await _approved(db)
    await _ready_owing(db, order)
    doc = await _claim(db)
    assert doc is not None and doc["mode"] == "internal"
    assert await _system(db, "SELECT order_render_failed(CAST(:o AS uuid), CAST(:l AS uuid), "
                             "'font missing')", {"o": order, "l": doc["lease_token"]})
    r = await _row(db, order)
    assert (r.pdf_state, r.pdf_key, r.pdf_attempts, r.pdf_error) == \
        ("ready", "orders/old.pdf", 0, None)
    assert (r.pdf_internal_attempts, r.pdf_internal_error, r.pdf_lease) == \
        (1, "font missing", None)
    assert await _claim(db) is None, "backed off"

    await db.execute(text("UPDATE sales_order SET pdf_internal_attempts = 4, "
                          "pdf_next_attempt_at = now() - interval '1 second' "
                          "WHERE id = CAST(:o AS uuid)"), {"o": order})
    fifth = await _claim(db)
    assert fifth is not None and fifth["attempt"] == 5, "four failures leave a fifth try"
    assert await _system(db, "SELECT order_render_failed(CAST(:o AS uuid), CAST(:l AS uuid), "
                             "'font missing')", {"o": order, "l": fifth["lease_token"]})
    await db.execute(text("UPDATE sales_order SET pdf_next_attempt_at = now() - interval '1 second' "
                          "WHERE id = CAST(:o AS uuid)"), {"o": order})
    assert await _claim(db) is None, "five attempts and branch 2 gives up"
    assert (await _row(db, order)).pdf_state == "ready"


async def test_the_three_argument_done_hands_the_lease_back_uncharged(db: AsyncSession) -> None:
    """EC-3: a worker older than 092 publishes nothing."""
    _, order = await _approved(db)
    doc = await _claim(db)
    assert doc is not None
    assert (await _row(db, order)).pdf_attempts == 1
    assert not await _system(db, "SELECT order_render_done(CAST(:o AS uuid), CAST(:l AS uuid), "
                                 "'orders/old-worker.pdf')",
                             {"o": order, "l": doc["lease_token"]})
    r = await _row(db, order)
    assert (r.pdf_state, r.pdf_key, r.pdf_attempts, r.pdf_lease) == ("pending", None, 0, None)

    await _ready_owing(db, order)
    doc = await _claim(db)
    assert doc is not None and doc["mode"] == "internal"
    assert not await _system(db, "SELECT order_render_done(CAST(:o AS uuid), CAST(:l AS uuid), "
                                 "'orders/old-worker.pdf')",
                             {"o": order, "l": doc["lease_token"]})
    r = await _row(db, order)
    assert (r.pdf_state, r.pdf_key, r.pdf_internal_attempts, r.pdf_lease) == \
        ("ready", "orders/old.pdf", 0, None)


async def test_a_cancelled_order_is_not_owed_an_internal_copy(db: AsyncSession) -> None:
    """EC-5. A submitted order cannot be soft-deleted, so cancel is the case."""
    w, cancelled = await _approved(db)
    await _ready_owing(db, cancelled)
    await m13._as(db, w.sm)
    await db.execute(text("SELECT order_cancel(CAST(:o AS uuid), 'Plant shut')"),
                     {"o": cancelled})
    await m13._as_owner(db)
    assert await _claim(db) is None


async def test_the_new_columns_may_change_after_submit(db: AsyncSession) -> None:
    """The guard lets them through; without 092's swap this UPDATE is refused."""
    _, order = await _approved(db)
    await db.execute(text("UPDATE sales_order SET pdf_internal_key = 'k', "
                          "pdf_internal_attempts = 2, pdf_internal_error = 'e' "
                          "WHERE id = CAST(:o AS uuid)"), {"o": order})
    r = await _row(db, order)
    assert (r.pdf_internal_key, r.pdf_internal_attempts) == ("k", 2)


async def test_an_escalated_step_names_the_role_that_took_it(db: AsyncSession) -> None:
    """Code review F-6: `decided_role` from the SQL, not a fixture."""
    _, order = await _approved(db)
    await db.execute(text(
        "UPDATE approval_step s SET decided_role_id = (SELECT id FROM role WHERE code = 'state_manager') "
        "FROM approval_request q WHERE q.id = s.request_id AND q.entity_id = CAST(:o AS uuid) "
        "AND s.seq = 1"), {"o": order})
    doc = await _claim(db)
    assert doc is not None
    steps = doc["internal"]["approvals"][-1]["steps"]
    assert steps[0]["decided_role"] == "State Manager"
    assert all(s["decided_role"] is None for s in steps[1:]), "the step's own role is not escalation"
