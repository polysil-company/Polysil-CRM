# ruff: noqa: E501  (embedded SQL)

"""FS-047: the hourly ceiling on sign-in codes to customers, inside the definer.

Every test runs in the rolled-back `db` transaction, so the setting, the
customers and the ledger rows it writes never outlive it (plan review R-4).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.conftest import Fixtures, make_partner_user

pytestmark = pytest.mark.db

ISSUE = text("SELECT auth_issue_otp_challenge(:m, NULL, :c, 10)")


def _mobile() -> str:
    return "9197" + f"{uuid.uuid4().int % 10**8:08d}"


async def _clean_hour(db: AsyncSession, cap: str) -> None:
    """An empty hour of customer codes and the cap under test."""
    await db.execute(text(
        "DELETE FROM login_attempt la USING app_user c WHERE c.mobile = la.identifier "
        "AND c.user_type = 'consumer' AND la.kind = 'otp_issue' "
        "AND la.attempted_at > now() - interval '2 hours'"))
    await db.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) "
                          "WHERE key = 'portal_otp_hourly_cap'"), {"v": cap})


async def _consumer(db: AsyncSession) -> str:
    mobile = _mobile()
    cid = (await db.execute(text(
        "INSERT INTO customer (name, mobile) VALUES ('Kiritbhai Shah', :m) RETURNING id"),
        {"m": "+" + mobile})).scalar_one()
    await db.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, customer_id, is_active) "
        "VALUES ('consumer', :m, 'Kiritbhai Shah', :c, true) "
        "ON CONFLICT (mobile) WHERE deleted_at IS NULL DO NOTHING"), {"m": mobile, "c": cid})
    # the insert trigger follows the portal switch (off here); the switch on is what
    # this stands in for
    await db.execute(text("UPDATE app_user SET is_active = true WHERE mobile = :m"), {"m": mobile})
    return mobile


async def _issue(db: AsyncSession, mobile: str) -> bool:
    return bool((await db.execute(ISSUE, {"m": mobile, "c": "482913"})).scalar_one())


async def test_the_setting_is_seeded(db: AsyncSession) -> None:
    row = (await db.execute(text(
        "SELECT kind, value::text, min, max FROM app_setting WHERE key = 'portal_otp_hourly_cap'"))).one()
    assert (row.kind, row.value, row.min, row.max) == ("int", "100", 0, 10000), row


async def test_the_ceiling_refuses_customers_and_never_dealers(db: AsyncSession, ids: Fixtures) -> None:
    await _clean_hour(db, "2")
    customers = [await _consumer(db) for _ in range(3)]
    assert [await _issue(db, m) for m in customers] == [True, True, False]
    dealer = _mobile()
    await make_partner_user(db, ids, mobile=dealer)
    assert await _issue(db, dealer) is True, "dealers are not counted or refused"
    assert await _issue(db, customers[0]) is False, "a customer already served is refused too"


async def test_zero_sends_no_customer_a_code(db: AsyncSession, ids: Fixtures) -> None:
    await _clean_hour(db, "0")
    assert await _issue(db, await _consumer(db)) is False
    dealer = _mobile()
    await make_partner_user(db, ids, mobile=dealer)
    assert await _issue(db, dealer) is True


async def test_an_hour_old_code_no_longer_counts(db: AsyncSession) -> None:
    await _clean_hour(db, "1")
    first, second = await _consumer(db), await _consumer(db)
    assert await _issue(db, first) is True
    assert await _issue(db, second) is False
    await db.execute(text("UPDATE login_attempt SET attempted_at = now() - interval '61 minutes' "
                          "WHERE identifier = :m AND kind = 'otp_issue'"), {"m": first})
    assert await _issue(db, second) is True


async def test_unknown_and_capped_numbers_cost_nothing(db: AsyncSession) -> None:
    await _clean_hour(db, "1")
    assert await _issue(db, _mobile()) is False                  # unknown number
    capped = await _consumer(db)
    await db.execute(text(
        "INSERT INTO login_attempt (identifier, succeeded, kind) "
        "SELECT :m, true, 'otp_issue' FROM generate_series(1, 10)"), {"m": capped})
    await db.execute(text("UPDATE login_attempt SET attempted_at = now() - interval '2 hours' "
                          "WHERE identifier = :m"), {"m": capped})   # at its daily cap, outside the hour
    assert await _issue(db, capped) is False                     # its own daily cap
    assert await _issue(db, await _consumer(db)) is True, "neither request used the one code"


async def test_a_stored_decimal_reads_as_a_whole_number(db: AsyncSession) -> None:
    """Plan review R-1: the check accepts 1.0; a plain ::int cast would raise."""
    await _clean_hour(db, "1.0")
    assert await _issue(db, await _consumer(db)) is True
    assert await _issue(db, await _consumer(db)) is False


async def test_at_the_ceiling_no_request_waits_on_the_lock(
        db: AsyncSession, sessions) -> None:  # type: ignore[no-untyped-def]
    """Edge E-1: another transaction holds the ceiling's lock. A request at the
    ceiling is refused without waiting; one under it waits, which proves the lock."""
    await _clean_hour(db, "1")
    first = await _consumer(db)
    holder = sessions()
    await holder.execute(text("SELECT pg_advisory_xact_lock(7, 0)"))
    try:
        await db.execute(text("SET LOCAL lock_timeout = '1s'"))
        nested = await db.begin_nested()
        with pytest.raises(DBAPIError, match="lock timeout"):
            await _issue(db, first)                              # under: waits on the holder
        await nested.rollback()
        await db.execute(text(
            "INSERT INTO login_attempt (identifier, succeeded, kind) VALUES (:m, true, 'otp_issue')"),
            {"m": first})                                        # now at the ceiling
        assert await _issue(db, await _consumer(db)) is False    # refused, no wait
    finally:
        await holder.rollback()
        await holder.close()


async def test_the_definer_runs_for_the_pre_auth_role(db: AsyncSession) -> None:
    await _clean_hour(db, "5")
    mobile = await _consumer(db)
    await db.execute(text("SET LOCAL ROLE app_anon"))
    assert await _issue(db, mobile) is True
