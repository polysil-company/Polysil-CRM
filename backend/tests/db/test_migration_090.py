"""Migration 090 (FS-089): the industrial order ladder. Every test runs in the `db`
fixture's transaction and is rolled back. The order paths are in
tests/api/test_fs089_industrial_ladder.py."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.test_migration_013 import _world

pytestmark = [pytest.mark.db]

D = Decimal
TAIL = ["account_manager", "dispatch_manager"]


async def _chain(db: AsyncSession, doc: str, amount: str, territory: str, level: int) -> list[str]:
    return (await db.execute(text(
        "SELECT array_agg(r.code::text ORDER BY x.n) FROM unnest(approval_chain(:d, "
        ":a, CAST(:t AS uuid), :l)) WITH ORDINALITY x(id, n) JOIN role r ON r.id = x.id"),
        {"d": doc, "a": D(amount), "t": territory, "l": level})).scalar_one()


async def test_the_seeded_ladder(db: AsyncSession) -> None:
    rows = dict((await db.execute(text(
        "SELECT r.code::text, t.max_amount FROM approval_threshold t JOIN role r ON r.id = t.role_id "
        "WHERE t.doc_type = 'industrial_order' AND t.territory_id IS NULL AND t.deleted_at IS NULL"))).all())
    assert rows == {"state_manager": D("500000.00"), "regional_manager": D("2500000.00"),
                    "md_ceo": None}


@pytest.mark.parametrize(("amount", "level", "expected"), [
    ("400000", 1, ["state_manager"]),
    ("500000.00", 1, ["state_manager"]),                     # EC-5: the ceiling is inclusive
    ("500000.01", 1, ["state_manager", "regional_manager"]),
    ("2500000.01", 1, ["state_manager", "regional_manager", "md_ceo"]),
    ("2500000.01", 3, ["regional_manager", "md_ceo"]),       # an SM's own order skips SM
    ("300000", 3, []),                                       # EC-6: and a small one skips all
    ("9000000", 4, ["md_ceo"]),
    ("9000000", 5, []),                                      # Admin-Sales and MD: Accounts only
])
async def test_the_industrial_ladder_by_value_and_owner(
        db: AsyncSession, amount: str, level: int, expected: list[str]) -> None:
    """Rules 1 and 3: no District Manager step; the MD at the top."""
    w = await _world(db)
    assert await _chain(db, "industrial_order", amount, w.district, level) == [*expected, *TAIL]


async def test_the_sales_order_ladder_is_unchanged(db: AsyncSession) -> None:
    """Rule 6: no MD step on any other order."""
    w = await _world(db)
    chain = await _chain(db, "sales_order", "9000000", w.district, 1)
    assert chain == ["district_manager", "state_manager", "regional_manager", *TAIL]


async def test_the_doc_type_check(db: AsyncSession) -> None:
    async with db.begin_nested() as sp:
        with pytest.raises(DBAPIError) as err:
            await db.execute(text(
                "INSERT INTO approval_threshold (doc_type, role_id, max_amount) "
                "SELECT 'export_order', id, 1 FROM role WHERE code = 'state_manager'"))
        await sp.rollback()
    assert "ck_approval_threshold_doc_type" in str(err.value)


async def test_the_quotation_and_complaint_branches_are_untouched(db: AsyncSession) -> None:
    body = (await db.execute(text(
        "SELECT pg_get_functiondef('approval_chain(text, numeric, uuid, integer)'::regprocedure)"))).scalar_one()
    assert "'district_manager', 'state_manager', 'regional_manager', 'admin_sales'" in body
    assert "p_doc_type <> 'complaint' OR code = 'account_manager'" in body
    assert "IF v_levels[i] > p_owner_level THEN" in body, "scripts/mutation_check_orders.py anchors it"
