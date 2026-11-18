"""081: the forecast's indexes exist with the predicates the queries match, and the
migration round-trips. Each test runs in the `db` fixture's transaction and is
rolled back."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.test_migration_012 import _as_owner

VERSIONS = Path(__file__).resolve().parents[2] / "api" / "db" / "migrations" / "versions"
NAMES = ("ix_quotation_live_value", "ix_quotation_accepted_at", "ix_quotation_rejected_at",
         "ix_activity_event_stage_changed")

pytestmark = [pytest.mark.db]


class _Op:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str) -> None:
        self.sql.append(sql)


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("m081", VERSIONS / "081_forecast_indexes.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _run(db: AsyncSession, step: str) -> None:
    m = _module()
    op = _Op()
    m.op = op
    getattr(m, step)()
    conn = await db.connection()
    for sql in op.sql:
        await conn.exec_driver_sql(sql)


async def _defs(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE indexname = ANY(:n)"),
        {"n": list(NAMES)})).all()
    return {r.indexname: r.indexdef for r in rows}


async def test_the_indexes_carry_the_predicates_the_queries_match(db: AsyncSession) -> None:
    defs = await _defs(db)
    assert set(defs) == set(NAMES)
    live = defs["ix_quotation_live_value"]
    assert "lead_id, sent_at DESC NULLS LAST, id DESC" in live
    assert "superseded_by_id IS NULL" in live and "deleted_at IS NULL" in live
    assert "'sent'" in live and "'viewed'" in live and "'negotiation'" in live
    assert "kind = 'lead.stage_changed'" in defs["ix_activity_event_stage_changed"]


async def test_the_migration_round_trips(db: AsyncSession) -> None:
    await _as_owner(db)
    await _run(db, "downgrade")
    assert await _defs(db) == {}
    await _run(db, "upgrade")
    assert set(await _defs(db)) == set(NAMES)
