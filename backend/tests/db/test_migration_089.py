"""Migration 089 (FS-088): installation and fittings columns, their CHECKs and grants,
the identity with every charge, and the public view's charges. Every test runs in
the `db` fixture's transaction and is rolled back. The service paths are in
tests/api/test_fs088_charges.py."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.conftest import Fixtures
from tests.db.test_migration_012 import _as_owner, _lead, _quotation

VERSIONS = Path(__file__).resolve().parents[2] / "api" / "db" / "migrations" / "versions"

pytestmark = [pytest.mark.db, pytest.mark.rls]

KINDS = ("installation", "fittings")
SUFFIXES = ("amount", "slab", "slab_chosen", "cgst", "sgst", "igst", "total")


def _089() -> Any:
    spec = importlib.util.spec_from_file_location("m089", VERSIONS / "089_document_charges.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _refused(db: AsyncSession, sql: str, params: dict[str, object], needle: str) -> None:
    async with db.begin_nested() as sp:
        with pytest.raises(DBAPIError) as err:
            await db.execute(text(sql), params)
        await sp.rollback()
    assert needle in str(err.value), err.value


def test_the_kinds_match_the_domain() -> None:
    from api.domain.pricing.tax import CHARGE_KINDS
    from api.services.pricing import CHARGE_COLUMNS

    m = _089()
    assert ("freight", *m.KINDS) == CHARGE_KINDS
    assert set(m.ALL_COLUMNS) | {f"freight_{s}" for s in SUFFIXES} == set(CHARGE_COLUMNS)


async def test_app_role_writes_the_charge_columns_of_an_order(db: AsyncSession) -> None:
    """EC-4: sales_order is column-granted."""
    cols = (await db.execute(text(
        "SELECT column_name, privilege_type FROM information_schema.column_privileges "
        "WHERE table_name = 'sales_order' AND grantee = 'app_role' "
        "AND privilege_type IN ('INSERT', 'UPDATE') "
        "AND (column_name LIKE 'installation_%' OR column_name LIKE 'fittings_%')"))).all()
    want = {(f"{k}_{s}", p) for k in KINDS for s in SUFFIXES for p in ("INSERT", "UPDATE")}
    assert {(c, p) for c, p in cols} == want


async def test_the_header_checks_and_the_identity(db: AsyncSession) -> None:
    for table in ("quotation", "sales_order"):
        defs = dict((await db.execute(text(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = CAST(:t AS regclass) AND conname LIKE :p"),
            {"t": table, "p": f"ck_{table}_%"})).all())
        for kind in KINDS:
            for name in ("set", "figures", "type"):
                assert f"ck_{table}_{kind}_{name}" in defs, (table, kind, name)
        identity = defs[f"ck_{table}_taxable_identity"]
        assert all(f"{k}_amount" in identity for k in ("freight", *KINDS)), identity
        assert "NOT VALID" not in identity, "validated"


async def test_a_writer_that_forgets_a_charge_fails_the_identity(
        db: AsyncSession, ids: Fixtures) -> None:
    """EC-6: installation set, taxable left as the goods only."""
    await _as_owner(db)
    q = await _quotation(db, ids, await _lead(db, ids))
    await _refused(db, (
        "UPDATE quotation SET installation_amount = 100, installation_slab = 18, "
        "installation_slab_chosen = false, installation_cgst = 9, installation_sgst = 9, "
        "installation_igst = 0, installation_total = 118 WHERE id = CAST(:q AS uuid)"),
        {"q": q}, "ck_quotation_taxable_identity")
    await _refused(db, (
        "UPDATE quotation SET fittings_amount = 100, taxable = taxable + 100 "
        "WHERE id = CAST(:q AS uuid)"), {"q": q}, "ck_quotation_fittings_set")


async def test_a_charge_on_a_subsidised_quotation_is_refused(
        db: AsyncSession, ids: Fixtures) -> None:
    await _as_owner(db)
    q = await _quotation(db, ids, await _lead(db, ids))
    await db.execute(text("UPDATE quotation SET sales_type = 'subsidised' WHERE id = CAST(:q AS uuid)"),
                     {"q": q})
    await _refused(db, (
        "UPDATE quotation SET installation_amount = 100, installation_slab = 18, "
        "installation_slab_chosen = false, installation_cgst = 9, installation_sgst = 9, "
        "installation_igst = 0, installation_total = 118, taxable = taxable + 100, "
        "total = total + 118 WHERE id = CAST(:q AS uuid)"), {"q": q},
        "ck_quotation_installation_type")


async def test_the_public_view_carries_each_charge(db: AsyncSession) -> None:
    """Plan review B-1."""
    body = (await db.execute(text(
        "SELECT pg_get_functiondef('quotation_public_view(text)'::regprocedure)"))).scalar_one()
    for col in ("freight_amount", "installation_amount", "fittings_amount"):
        assert f"q.{col}" in body, col
    granted = (await db.execute(text(
        "SELECT has_function_privilege('app_anon', 'quotation_public_view(text)', 'EXECUTE')"))).scalar_one()
    assert granted, "the swap keeps the anon grant"


class _Op:
    """Collects what the downgrade runs; stops at the first catalogue read."""

    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str) -> None:
        self.sql.append(sql)

    def get_bind(self) -> Any:
        raise _StopError


class _StopError(Exception):
    pass


async def test_the_downgrade_refuses_while_a_document_carries_a_charge(
        db: AsyncSession, ids: Fixtures) -> None:
    await _as_owner(db)
    q = await _quotation(db, ids, await _lead(db, ids))
    await db.execute(text(
        "UPDATE quotation SET fittings_amount = 100, fittings_slab = 18, fittings_slab_chosen = false, "
        "fittings_cgst = 9, fittings_sgst = 9, fittings_igst = 0, fittings_total = 118, "
        "taxable = taxable + 100, total = total + 118 WHERE id = CAST(:q AS uuid)"), {"q": q})
    m = _089()
    op = _Op()
    m.op = op
    with pytest.raises(_StopError):
        m.downgrade()
    assert len(op.sql) == 1, "the guard runs before anything else"
    conn = await db.connection()
    async with db.begin_nested() as sp:
        with pytest.raises(DBAPIError) as err:
            await conn.exec_driver_sql(op.sql[0])
        await sp.rollback()
    assert "documents carry installation or fittings" in str(err.value), err.value


def test_the_downgrade_restores_077s_identity() -> None:
    """EC-9."""
    m = _089()
    assert m.IDENTITY_077 == "taxable = gross - discount + COALESCE(freight_amount, 0)"
    spec = importlib.util.spec_from_file_location("m077", VERSIONS / "077_gst_choice_and_freight.py")
    assert spec is not None and spec.loader is not None
    src = (VERSIONS / "077_gst_choice_and_freight.py").read_text(encoding="utf-8")
    assert m.IDENTITY_077 in src
