# ruff: noqa: E501  (embedded SQL)

"""Warranty (FS-046, migration 053) in the database: the SQL end date is the
authoritative twin of api/domain/warranty.end_date, and the term table's shape."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import warranty

pytestmark = [pytest.mark.db]


async def test_sql_end_date_equals_the_python_twin_2020_to_2040(db: AsyncSession) -> None:
    """Every start day, a spread of lengths: one statement, compared row by row (edge EC-2)."""
    rows = (await db.execute(text(
        "SELECT d::date AS start, m, warranty_end(d::date, m) AS e "
        "FROM generate_series(DATE '2020-01-01', DATE '2040-12-31', interval '1 day') d, "
        "unnest(ARRAY[0, 1, 2, 6, 11, 12, 13, 24, 36, 120]) m"))).all()
    assert len(rows) > 70_000
    bad = [(r.start, r.m, r.e, warranty.end_date(r.start, r.m)) for r in rows
           if r.e != warranty.end_date(r.start, r.m)]
    assert not bad, bad[:5]


async def test_named_end_dates(db: AsyncSession) -> None:
    cases = [(dt.date(2026, 1, 31), 1, dt.date(2026, 2, 28)),
             (dt.date(2024, 2, 29), 12, dt.date(2025, 2, 28)),
             (dt.date(2027, 3, 1), 12, dt.date(2028, 2, 29)),
             (dt.date(2026, 1, 1), 1, dt.date(2026, 1, 31))]
    for start, months, end in cases:
        got = (await db.execute(text("SELECT warranty_end(:s, :m)"), {"s": start, "m": months})).scalar_one()
        assert got == end, (start, months)
    assert (await db.execute(text("SELECT warranty_end(DATE '2026-01-01', 0)"))).scalar_one() is None


async def test_the_default_term_and_the_constraints(db: AsyncSession) -> None:
    default = (await db.execute(text(
        "SELECT months, effective_from FROM warranty_term WHERE product_category_id IS NULL "
        "AND effective_from = DATE '2020-01-01'"))).one()
    assert default.months == 12
    # a start before any term: no months, so the status is unknown (edge EC-5)
    product = (await db.execute(text("SELECT id FROM product LIMIT 1"))).scalar_one()
    assert (await db.execute(text("SELECT warranty_months(:p, DATE '2016-01-01')"),
                             {"p": product})).scalar_one() is None
    assert (await db.execute(text("SELECT warranty_months(:p, DATE '2026-10-01')"),
                             {"p": product})).scalar_one() is not None
    cons = {r[0] for r in (await db.execute(text(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'warranty_term'::regclass"))).all()}
    assert {"ck_warranty_term_dates", "ex_warranty_term_default", "ex_warranty_term_category"} <= cons
    await db.execute(text("SAVEPOINT w"))
    with pytest.raises(Exception, match="ex_warranty_term_default"):
        await db.execute(text("INSERT INTO warranty_term (months, effective_from) VALUES (6, DATE '2030-01-01')"))
    await db.execute(text("ROLLBACK TO SAVEPOINT w"))
