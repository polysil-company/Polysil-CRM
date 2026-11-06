# ruff: noqa: E501  (embedded SQL)

"""FS-048 in the database: the 50-member cap and the downgrade-safe shape of a
direct conversation. Runs in the rolled-back `db` transaction."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.conftest import Fixtures, make_staff

pytestmark = pytest.mark.db


async def _as(db: AsyncSession, user_id: str) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(user_id)})


async def _staff(db: AsyncSession, ids: Fixtures, n: int) -> list[str]:
    return [str(await make_staff(db, ids, email=f"g{uuid.uuid4().hex[:10]}@example.com")) for _ in range(n)]


async def test_a_group_holds_at_most_50_and_a_batch_past_it_adds_nobody(db: AsyncSession, ids: Fixtures) -> None:
    people = await _staff(db, ids, 52)
    me, first, rest = people[0], people[1:49], people[49:]      # me + 48 = 49 in
    await _as(db, me)
    gid = (await db.execute(text("SELECT group_create('Big', CAST(:u AS uuid[]))"), {"u": first})).scalar_one()
    count = text("SELECT count(*) FROM conversation_member WHERE conversation_id = :g AND left_at IS NULL")
    assert (await db.execute(count, {"g": gid})).scalar_one() == 49
    nested = await db.begin_nested()
    with pytest.raises(DBAPIError, match="at most 50"):
        await db.execute(text("SELECT group_add(:g, CAST(:u AS uuid[]))"), {"g": gid, "u": rest[:2]})
    await nested.rollback()
    assert (await db.execute(count, {"g": gid})).scalar_one() == 49, "all or nothing"
    await db.execute(text("SELECT group_add(:g, CAST(:u AS uuid[]))"), {"g": gid, "u": rest[:1]})
    assert (await db.execute(count, {"g": gid})).scalar_one() == 50
    nested = await db.begin_nested()
    with pytest.raises(DBAPIError, match="at most 50"):
        await db.execute(text("SELECT group_add(:g, CAST(:u AS uuid[]))"), {"g": gid, "u": rest[1:2]})
    await nested.rollback()


async def test_a_group_can_never_carry_a_pair_and_a_pair_never_a_name(db: AsyncSession, ids: Fixtures) -> None:
    a, b = sorted(await _staff(db, ids, 2))
    for stmt in ("INSERT INTO conversation (kind, user_a, user_b, name) VALUES ('direct', :a, :b, 'x')",
                 "INSERT INTO conversation (kind, user_a, user_b, name) VALUES ('group', :a, :b, 'x')",
                 "INSERT INTO conversation (kind, name) VALUES ('group', '   ')"):
        nested = await db.begin_nested()
        with pytest.raises(DBAPIError, match="ck_conversation_pair"):
            await db.execute(text(stmt), {"a": a, "b": b})
        await nested.rollback()
    # two groups with the same name and no pair do not collide on uq_conversation_pair
    await db.execute(text("INSERT INTO conversation (kind, name) VALUES ('group', 'Same'), ('group', 'Same')"))
