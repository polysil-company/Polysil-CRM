"""Migration 051 (FS-043): the `bands` setting kind at the table, and the rating
table's grants, RLS and shape. Rolled back with the `db` fixture's transaction.
Who may rate and the derived rating are exercised in tests/api/test_ratings.py."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.db, pytest.mark.rls]


async def _refused(db: AsyncSession, sql: str, params: dict[str, object], needle: str) -> None:
    async with db.begin_nested() as sp:
        with pytest.raises(DBAPIError) as err:
            await db.execute(text(sql), params)
        await sp.rollback()
    assert needle in str(err.value), err.value


@pytest.mark.parametrize("bad", [[7, 7, 30, 60], [7, 15.5, 30, 60], ["7", "15", "30", "60"],
                                 [7, 15, 30], [-1, 15, 30, 60], {"a": 1}])
async def test_a_bands_setting_is_four_rising_whole_numbers_at_the_table(db: AsyncSession, bad: object) -> None:
    """The trigger, not only the API: a string list passes Pydantic's str branch."""
    await _refused(db, "UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = 'dealer_rating_payment_days'",
                   {"v": json.dumps(bad)}, "four whole numbers, rising")


async def test_a_good_bands_value_is_kept(db: AsyncSession) -> None:
    await db.execute(text("UPDATE app_setting SET value = '[0, 15, 30, 60]' WHERE key = 'dealer_rating_payment_days'"))
    got = (await db.execute(text("SELECT value FROM app_setting WHERE key = 'dealer_rating_payment_days'"))).scalar_one()
    assert got == [0, 15, 30, 60]


async def test_app_role_reads_ratings_and_writes_them_only_through_the_definer(db: AsyncSession) -> None:
    grants = (await db.execute(text(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE table_name = 'rating' AND grantee = 'app_role'"))).scalars().all()
    assert grants == ["SELECT"]
    assert (await db.execute(text("SELECT relrowsecurity FROM pg_class WHERE relname = 'rating'"))).scalar_one()
    for fn in ("rating_record(text, uuid, uuid, uuid, integer, text)", "dealer_rating(uuid)"):
        assert (await db.execute(text("SELECT has_function_privilege('app_role', :f, 'EXECUTE')"),
                                 {"f": fn})).scalar_one(), fn
        assert not (await db.execute(text("SELECT has_function_privilege('public', :f, 'EXECUTE')"),
                                     {"f": fn})).scalar_one(), fn


async def test_a_rating_names_exactly_the_columns_of_its_target(db: AsyncSession) -> None:
    ins = ("INSERT INTO rating (target, sales_order_id, complaint_id, product_id, rated_by, score, entered_by) "
           "VALUES (:t, CAST(:o AS uuid), CAST(:c AS uuid), CAST(:p AS uuid), 'customer', 3, "
           "(SELECT id FROM app_user LIMIT 1))")
    some = "00000000-0000-0000-0000-000000000001"
    await _refused(db, ins, {"t": "installation", "o": None, "c": some, "p": None}, "ck_rating_target")
    await _refused(db, ins, {"t": "service", "o": some, "c": None, "p": None}, "ck_rating_target")
    await _refused(db, ins, {"t": "product", "o": some, "c": None, "p": None}, "ck_rating_target")
