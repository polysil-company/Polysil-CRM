"""FS-007's two definer changes, and the outbox's negative policies (section 10).

The supersede is the definer's half of rule 1a: a second code retires the first's
pending row, after the cap and the lookup so a capped or unknown request burns
nothing, and with SKIP LOCKED so a row the worker holds is left alone and the
request does not wait. The worker's half (a claimed row that finds a newer code)
is in tests/worker.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.session import enter_role
from tests.conftest import Dealer
from tests.db.conftest import Fixtures, make_partner_user, make_staff

pytestmark = pytest.mark.db

ISSUE = text("SELECT auth_issue_otp_challenge(:m, NULL, :c, :cap)")


def _mobile() -> str:
    return "9198" + f"{uuid.uuid4().int % 10**8:08d}"


async def _as(db: AsyncSession, user_id: str) -> None:
    """What get_db does: the claim, then app_role, transaction-local."""
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id)})
    await enter_role(db, "app_role")


async def _rows(db: AsyncSession, mobile: str) -> list[tuple[str, str | None, str, str]]:
    got = (await db.execute(text(
        "SELECT state::text, error, payload::text, channel::text FROM notification_outbox "
        "WHERE recipient = :m AND template_key = 'auth.otp' ORDER BY created_at"),
        {"m": mobile})).all()
    return [tuple(r) for r in got]  # type: ignore[misc]


# ── rule 1a, the definer's half ──────────────────────────────────────────────

async def test_a_second_code_retires_the_first_and_goes_out_on_whatsapp(
        db: AsyncSession, ids: Fixtures) -> None:
    mobile = _mobile()
    await make_partner_user(db, ids, mobile=mobile)
    assert (await db.execute(ISSUE, {"m": mobile, "c": "111111", "cap": 10})).scalar_one() is True
    assert (await db.execute(ISSUE, {"m": mobile, "c": "222222", "cap": 10})).scalar_one() is True
    rows = await _rows(db, mobile)
    assert [(r[0], r[1]) for r in rows] == [("dead", "superseded"), ("pending", None)], rows
    assert rows[0][2] == "{}", "the retired row still carried its code"
    assert '"222222"' in rows[1][2] and rows[1][3] == "whatsapp"


async def test_a_capped_request_burns_nothing(db: AsyncSession, ids: Fixtures) -> None:
    """Plan review B-4: placed before the cap check, the supersede would let anyone
    who knows a number burn each code as it is issued, with the 202 unchanged."""
    mobile = _mobile()
    await make_partner_user(db, ids, mobile=mobile)
    assert (await db.execute(ISSUE, {"m": mobile, "c": "111111", "cap": 10})).scalar_one() is True
    assert (await db.execute(ISSUE, {"m": mobile, "c": "222222", "cap": 1})).scalar_one() is False
    rows = await _rows(db, mobile)
    assert [(r[0], r[1]) for r in rows] == [("pending", None)], rows
    assert '"111111"' in rows[0][2]


async def test_an_unknown_number_burns_nothing_either(db: AsyncSession) -> None:
    mobile = _mobile()
    await db.execute(text(
        "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
        "VALUES ('whatsapp', 'auth.otp', :m, '{\"code\": \"333333\"}')"), {"m": mobile})
    assert (await db.execute(ISSUE, {"m": mobile, "c": "444444", "cap": 10})).scalar_one() is False
    rows = await _rows(db, mobile)
    assert [(r[0], r[1]) for r in rows] == [("pending", None)], rows


async def test_a_row_the_worker_holds_is_left_alone_and_the_request_does_not_wait(
        sessions: Callable[[], AsyncSession], dealer: Dealer) -> None:
    """Plan review B-3, executed: a plain UPDATE waited behind the worker's row lock
    for the length of a send while holding the number's advisory lock, a wait that
    exists only for registered numbers. SKIP LOCKED returns at once and leaves the
    in-flight row to the worker's own check."""
    a, b = sessions(), sessions()
    t0 = (await a.execute(text("SELECT now()"))).scalar_one()   # the database's clock
    try:
        assert (await a.execute(ISSUE, {"m": dealer.mobile, "c": "555555",
                                        "cap": 1000})).scalar_one()
        await a.commit()
        held = (await a.execute(text(
            "SELECT id FROM notification_outbox WHERE recipient = :m AND template_key = 'auth.otp' "
            "AND state = 'pending' AND created_at >= :t FOR UPDATE"),
            {"m": dealer.mobile, "t": t0})).scalars().all()
        assert len(held) == 1
        started = time.monotonic()
        # without SKIP LOCKED this call would block on the held row; the timeout
        # turns that regression into a failure rather than a stalled run
        await b.execute(text("SET LOCAL lock_timeout = '3s'"))
        assert (await b.execute(ISSUE, {"m": dealer.mobile, "c": "666666",
                                        "cap": 1000})).scalar_one()
        await b.commit()
        assert time.monotonic() - started < 3.0, "the request waited behind the worker's lock"
        await a.rollback()
        rows = (await b.execute(text(
            "SELECT state::text, error FROM notification_outbox WHERE recipient = :m "
            "AND template_key = 'auth.otp' AND created_at >= :t ORDER BY created_at"),
            {"m": dealer.mobile, "t": t0})).all()
        await b.rollback()
        assert [tuple(r) for r in rows] == [("pending", None), ("pending", None)], rows
    finally:
        c = sessions()
        await c.execute(text(
            "DELETE FROM notification_outbox WHERE recipient = :m AND created_at >= :t"),
            {"m": dealer.mobile, "t": t0})
        await c.execute(text(
            "DELETE FROM login_attempt WHERE identifier = :m AND kind = 'otp_issue' "
            "AND attempted_at >= :t"), {"m": dealer.mobile, "t": t0})
        await c.commit()


# ── rule 10a: the withdrawal definer ─────────────────────────────────────────

async def _lead(db: AsyncSession, ids: Fixtures, owner: str) -> tuple[str, str]:
    no = "F8-" + uuid.uuid4().hex[:10]
    lead_id = str((await db.execute(text(
        "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, "
        "farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id) VALUES "
        "(:no, 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
        "(SELECT id FROM lead_source WHERE code = 'employee'), 'F', :m, :t, :u, :ou) "
        "RETURNING id"),
        {"no": no, "m": "+" + _mobile(), "t": ids.territory_id, "u": owner,
         "ou": ids.org_unit_id})).scalar_one())
    return lead_id, no


async def test_lead_withdrawn_answers_for_the_system_principal_only(
        db: AsyncSession, ids: Fixtures) -> None:
    owner = await make_staff(db, ids, email=ids.unique("own") + "@polysil.in")
    live_id, live_no = await _lead(db, ids, owner)
    gone_id, gone_no = await _lead(db, ids, owner)
    merged_id, merged_no = await _lead(db, ids, owner)
    await db.execute(text("UPDATE lead SET deleted_at = now() WHERE id = :i"), {"i": gone_id})
    await db.execute(text("UPDATE lead SET merged_into_id = :o, stage = 'merged' WHERE id = :i"),
                     {"o": live_id, "i": merged_id})

    await _as(db, get_settings().system_user_id)
    answers = [(await db.execute(text("SELECT outbox_lead_withdrawn(:n)"), {"n": n})).scalar_one()
               for n in (live_no, gone_no, merged_no, "POL/XX/2099-00/00000")]
    assert answers == [False, True, True, True]

    # the same role, another claim: refused, so the grant to app_role is not an
    # "is this enquiry withdrawn" oracle
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(owner)})
    with pytest.raises(DBAPIError) as exc:
        async with db.begin_nested():
            await db.execute(text("SELECT outbox_lead_withdrawn(:n)"), {"n": live_no})
    assert getattr(exc.value.orig, "sqlstate", "") == "42501"


# ── the outbox under RLS, the negative cases ─────────────────────────────────

async def test_the_outbox_is_invisible_to_an_authenticated_non_system_principal(
        db: AsyncSession, ids: Fixtures) -> None:
    row_id = str((await db.execute(text(
        "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
        "VALUES ('whatsapp', 'lead_ack', :m, '{}') RETURNING id"),
        {"m": "+" + _mobile()})).scalar_one())
    staff = await make_staff(db, ids, email=ids.unique("rls") + "@polysil.in")

    await _as(db, staff)
    seen = (await db.execute(text(
        "SELECT count(*) FROM notification_outbox WHERE id = CAST(:i AS uuid)"),
        {"i": row_id})).scalar_one()
    updated = (await db.execute(text(
        "UPDATE notification_outbox SET error = 'x' WHERE id = CAST(:i AS uuid)"),
        {"i": row_id})).rowcount
    deleted = (await db.execute(text(
        "DELETE FROM notification_outbox WHERE id = CAST(:i AS uuid)"), {"i": row_id})).rowcount
    assert (seen, updated, deleted) == (0, 0, 0)

    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": get_settings().system_user_id})
    deleted = (await db.execute(text(
        "DELETE FROM notification_outbox WHERE id = CAST(:i AS uuid)"), {"i": row_id})).rowcount
    assert deleted == 1


# ── code review F-4: the worker's supersede lookup has an index that fits ────

async def test_the_workers_supersede_lookup_uses_its_own_index(db: AsyncSession) -> None:
    """Executed in review: the worker's check has no state clause, so the partial
    index on pending rows cannot serve it, and the planner fell back to the
    purge's index with a filter over every row created after the claimed one. The
    claimed row is a retry, older than most, so the lookup asks for a month of rows."""
    await db.execute(text("SET LOCAL enable_seqscan = off"))
    plan = (await db.execute(text(
        "EXPLAIN SELECT EXISTS (SELECT 1 FROM notification_outbox o "
        "WHERE o.template_key = 'auth.otp' "
        "AND o.recipient = :r AND o.created_at > now() - interval '30 days' "
        "AND o.id <> gen_random_uuid())"),
        {"r": "919999999999"})).scalars().all()
    assert any("ix_notification_outbox_otp_recipient" in line for line in plan), plan
