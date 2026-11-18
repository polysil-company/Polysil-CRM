"""Migration 027 (FS-015b): `closed` and `closed_at` go together, both ways."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db import test_migration_019 as m19

pytestmark = [pytest.mark.db]


async def test_closed_and_its_time_go_together_both_ways(db: AsyncSession) -> None:
    """PR 38 review: the earlier test matched the constraint's text, and a one-way
    CHECK would have passed it."""
    w = await m19._world(db)
    cid = await m19._complaint(db, w)
    sql = ("UPDATE complaint SET status = CAST(:s AS complaint_status), closed_at = {at} "
           "WHERE id = CAST(:c AS uuid)")
    await m13._refused(db, sql.format(at="NULL"), {"s": "closed", "c": cid}, "23514")
    await m13._refused(db, sql.format(at="now()"), {"s": "qc_approved", "c": cid}, "23514")
    await db.execute(text(sql.format(at="now()")), {"s": "closed", "c": cid})
    assert (await db.execute(text("SELECT status::text FROM complaint WHERE id = CAST(:c AS uuid)"),
                             {"c": cid})).scalar_one() == "closed"
