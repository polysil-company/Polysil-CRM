"""Migration 035 (FS-025): targets, executed as the roles that touch them."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db import test_migration_018 as m18

pytestmark = [pytest.mark.db, pytest.mark.rls]

_INSERT = ("INSERT INTO sales_target (user_id, org_unit_id, month, metric, value, created_by) "
           "VALUES (CAST(:u AS uuid), CAST(:o AS uuid), date_trunc('month', now())::date, 'orders', 5, CAST(:me AS uuid))")


async def test_the_insert_check_refuses_self_peer_and_another_office(db: AsyncSession) -> None:
    """Review B-1, in the policy as well as the service."""
    w = await m18._world(db)
    await m13._as(db, w.dm)
    await db.execute(text(_INSERT), {"u": w.officer, "o": w.a, "me": w.dm})
    await m13._refused(db, _INSERT, {"u": w.dm, "o": w.a, "me": w.dm}, "42501")
    await m13._refused(db, _INSERT, {"u": w.officer_b, "o": w.b, "me": w.dm}, "42501")
    await m13._as_owner(db)
    await m13._as(db, w.officer)
    await m13._refused(db, _INSERT, {"u": w.officer, "o": w.a, "me": w.officer}, "42501")
    await m13._as_owner(db)


async def test_reads_follow_scope(db: AsyncSession) -> None:
    w = await m18._world(db)
    for u, o in ((w.officer, w.a), (w.officer_b, w.b)):
        await db.execute(text(_INSERT), {"u": u, "o": o, "me": w.admin})
    q = "SELECT count(*) FROM sales_target WHERE user_id = ANY(CAST(:u AS uuid[]))"
    p = {"u": [w.officer, w.officer_b]}
    for who, want in ((w.officer, 1), (w.dm, 1), (w.dm_b, 1), (w.admin, 2), (w.dealer, 0)):
        await m13._as(db, who)
        assert (await db.execute(text(q), p)).scalar_one() == want, who
        await m13._as_owner(db)


async def test_a_transfer_takes_this_month_along(db: AsyncSession) -> None:
    """Review B-2: the person's current targets follow them to the new office."""
    w = await m18._world(db)
    await db.execute(text(_INSERT), {"u": w.officer, "o": w.a, "me": w.admin})
    await db.execute(text("UPDATE app_user SET org_unit_id = CAST(:b AS uuid) WHERE id = CAST(:u AS uuid)"),
                     {"b": w.b, "u": w.officer})
    office = (await db.execute(text("SELECT org_unit_id::text FROM sales_target WHERE user_id = CAST(:u AS uuid)"),
                               {"u": w.officer})).scalar_one()
    assert office == w.b
