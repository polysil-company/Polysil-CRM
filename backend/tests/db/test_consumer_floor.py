"""The consumer floor (FS-044, migration 052): every table with RLS on carries one
restrictive policy a consumer's claim never passes, and a consumer reads nothing
but its own account and idempotency rows (plan review B-1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz import consumer_floor
from api.db.session import enter_role

pytestmark = [pytest.mark.db, pytest.mark.rls]

_RLS = ("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity ORDER BY c.relname")


async def test_every_rls_table_carries_the_floor_as_generated(db: AsyncSession) -> None:
    """A migration that turns RLS on for a new table must add the floor too."""
    tables = (await db.execute(text(_RLS))).scalars().all()
    assert len(tables) > 50
    for t in tables:
        name = consumer_floor.name(t)
        before = (await db.execute(text(
            "SELECT permissive, cmd, roles, qual, with_check FROM pg_policies "
            "WHERE tablename = :t AND policyname = :n"), {"t": t, "n": name})).all()
        assert len(before) == 1, f"{t} has no consumer floor"
        await db.execute(text("SAVEPOINT floor"))
        await db.execute(text(f"DROP POLICY {name} ON {t}"))
        await db.execute(text(consumer_floor.policy_sql(t)))
        after = (await db.execute(text(
            "SELECT permissive, cmd, roles, qual, with_check FROM pg_policies "
            "WHERE tablename = :t AND policyname = :n"), {"t": t, "n": name})).all()
        await db.execute(text("ROLLBACK TO SAVEPOINT floor"))
        assert after == before, t
        assert before[0][0] == "RESTRICTIVE"


async def test_a_consumer_reads_nothing_but_its_own_rows(db: AsyncSession) -> None:
    """Executed over every RLS table, as app_role with a consumer claim."""
    customer = (await db.execute(text(
        "INSERT INTO customer (name, mobile) VALUES ('Floor Farmer', :m) RETURNING id"),
        {"m": "+9196" + f"{uuid.uuid4().int % 10**8:08d}"})).scalar_one()
    me = (await db.execute(text(
        "SELECT id FROM app_user WHERE customer_id = :c AND user_type = 'consumer'"),
        {"c": customer})).scalar_one()
    tables = (await db.execute(text(_RLS))).scalars().all()
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(me)})
    await enter_role(db, "app_role")
    assert (await db.execute(text("SELECT app_is_consumer()"))).scalar_one() is True
    readable = []
    for t in tables:
        try:
            async with db.begin_nested():
                n = (await db.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one()
        except Exception:      # no SELECT grant at all is also a closed door
            continue
        if n:
            readable.append((t, n))
    assert readable == [("app_user", 1)], readable   # its own row only: /auth/me needs it
