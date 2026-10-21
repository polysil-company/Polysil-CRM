"""Migration 077 (FS-069): the 40 % slab, the line choice columns and their
trigger, the header freight CHECKs and grants, and the `slabs` setting. Every test
runs in the `db` fixture's transaction and is rolled back. The service paths are
in tests/api/test_gst_choice_freight.py."""

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
from tests.db.test_migration_013 import _order, _submit, _world

VERSIONS = Path(__file__).resolve().parents[2] / "api" / "db" / "migrations" / "versions"

pytestmark = [pytest.mark.db, pytest.mark.rls]

_FREIGHT = ("freight_amount", "freight_slab", "freight_slab_chosen", "freight_cgst",
            "freight_sgst", "freight_igst", "freight_total")


async def _refused(db: AsyncSession, sql: str, params: dict[str, object], needle: str) -> None:
    async with db.begin_nested() as sp:
        with pytest.raises(DBAPIError) as err:
            await db.execute(text(sql), params)
        await sp.rollback()
    assert needle in str(err.value), err.value


async def test_the_councils_40_is_a_slab_and_41_is_not(db: AsyncSession) -> None:
    await db.execute(text("INSERT INTO gst_rate (hsn_code, rate, effective_from) "
                          "VALUES ('99887766', 40, DATE '2025-09-22')"))
    await _refused(db, "INSERT INTO gst_rate (hsn_code, rate, effective_from) "
                       "VALUES ('99887765', 41, DATE '2025-09-22')", {}, "ck_gst_rate_slab")


async def test_app_role_writes_the_freight_columns_of_an_order(db: AsyncSession) -> None:
    cols = (await db.execute(text(
        "SELECT column_name, privilege_type FROM information_schema.column_privileges "
        "WHERE table_name = 'sales_order' AND grantee = 'app_role' "
        "AND privilege_type IN ('INSERT', 'UPDATE') AND column_name LIKE 'freight_%'"))).all()
    assert {(c, p) for c, p in cols} == {(c, p) for c in _FREIGHT for p in ("INSERT", "UPDATE")}


async def test_the_line_columns_and_their_checks(db: AsyncSession) -> None:
    for table in ("quotation_line", "order_line"):
        cols = dict((await db.execute(text(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name = :t AND column_name IN ('hsn_slab', 'gst_slab_chosen')"),
            {"t": table})).all())
        assert cols == {"hsn_slab": "NO", "gst_slab_chosen": "NO"}, table
        checks = (await db.execute(text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = :c"), {"c": f"ck_{table}_gst_chosen"})).scalar_one()
        assert "gst_slab_chosen" in checks and "hsn_slab" in checks
        trg = (await db.execute(text(
            "SELECT tgenabled FROM pg_trigger WHERE tgname = :n"),
            {"n": f"trg_{table}_a_hsn_slab"})).scalar_one()
        assert trg == "O", "enabled"
    # the backfill left the freeze triggers on
    for trg in ("trg_quotation_line_refuse_sent_edit", "trg_order_line_refuse_edit",
                "trg_quotation_line_audit", "trg_order_line_audit"):
        assert (await db.execute(text("SELECT tgenabled FROM pg_trigger WHERE tgname = :n"),
                                 {"n": trg})).scalar_one() == "O", trg


async def test_the_fill_function_takes_the_slab_and_refuses_a_bare_choice(db: AsyncSession) -> None:
    """The trigger's function, called on a stand-in row: what a writer that predates
    the choice gets, and what a chosen line without its HSN slab gets."""
    await db.execute(text(
        "CREATE TEMP TABLE t077 (gst_slab numeric(6,3), hsn_slab numeric(6,3), "
        "gst_slab_chosen boolean NOT NULL DEFAULT false) ON COMMIT DROP"))
    await db.execute(text("CREATE TRIGGER t077_fill BEFORE INSERT ON t077 FOR EACH ROW "
                          "EXECUTE FUNCTION line_hsn_slab_fill()"))
    got = (await db.execute(text(
        "INSERT INTO t077 (gst_slab) VALUES (5) RETURNING hsn_slab"))).scalar_one()
    assert got == 5
    kept = (await db.execute(text(
        "INSERT INTO t077 (gst_slab, hsn_slab, gst_slab_chosen) VALUES (18, 5, true) "
        "RETURNING hsn_slab"))).scalar_one()
    assert kept == 5
    await _refused(db, "INSERT INTO t077 (gst_slab, gst_slab_chosen) VALUES (18, true)", {},
                   "a chosen GST slab needs hsn_slab")


async def test_the_header_checks(db: AsyncSession) -> None:
    for table in ("quotation", "sales_order"):
        defs = dict((await db.execute(text(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = CAST(:t AS regclass) AND conname LIKE :p"),
            {"t": table, "p": f"ck_{table}_%"})).all())
        for name in ("freight_set", "freight_figures", "freight_type", "taxable_identity"):
            assert f"ck_{table}_{name}" in defs, (table, name)
        identity = defs[f"ck_{table}_taxable_identity"]
        assert "freight_amount" in identity and "NOT VALID" not in identity, "validated"


async def test_the_slabs_setting_holds_only_slabs_once_each(db: AsyncSession) -> None:
    value = (await db.execute(text(
        "SELECT value::text, kind FROM app_setting WHERE key = 'gst_slab_choices'"))).one()
    assert value == ('["0", "5", "18", "40"]', "slabs")
    upd = "UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = 'gst_slab_choices'"
    await db.execute(text(upd), {"v": '["0", "5", "12", "18", "28", "40"]'})
    for bad, needle in (('["7"]', "is not a GST slab"), ('["18", "18.0"]', "listed twice"),
                        ('[]', "a list of GST slabs"), ('[18]', "is not a GST slab"),
                        ('["abc"]', "is not a GST slab")):
        await _refused(db, upd, {"v": bad}, needle)


# ── plan review B-1: the backfill on frozen lines ────────────────────────────

class _Op:
    """Stands in for alembic's `op`, collecting what a migration would run."""

    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str) -> None:
        self.sql.append(sql)


def _077() -> Any:
    spec = importlib.util.spec_from_file_location("m077", VERSIONS / "077_gst_choice_and_freight.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _run(db: AsyncSession, step: str) -> None:
    m = _077()
    op = _Op()
    m.op = op
    getattr(m, step)()
    conn = await db.connection()
    for sql in op.sql:
        await conn.exec_driver_sql(sql)


async def test_the_migration_runs_over_a_sent_quotation_and_a_submitted_order(
        db: AsyncSession, ids: Fixtures) -> None:
    """CI's empty database cannot show this: the freeze triggers refuse any UPDATE
    of a sent quotation's or a submitted order's line, the owner's included, so a
    plain backfill fails on staging and production. 077 disables them around it."""
    await _as_owner(db)
    lead = await _lead(db, ids)
    sent = await _quotation(db, ids, lead, status="sent", lines=1)
    w = await _world(db)
    order = await _order(db, w)
    await _submit(db, w, order)
    await _as_owner(db)
    assert (await db.execute(text("SELECT status::text FROM sales_order WHERE id = CAST(:o AS uuid)"),
                             {"o": order})).scalar_one() == "submitted"

    await _run(db, "downgrade")
    await _run(db, "upgrade")

    for table, key, ref in (("quotation_line", "quotation_id", sent),
                            ("order_line", "sales_order_id", order)):
        rows = (await db.execute(text(
            f"SELECT gst_slab, hsn_slab, gst_slab_chosen FROM {table} WHERE {key} = CAST(:r AS uuid)"),
            {"r": ref})).all()
        assert rows and all(r.hsn_slab == r.gst_slab and r.gst_slab_chosen is False for r in rows), table
    # the freeze is back on: the same UPDATE now refuses
    await _refused(db, "UPDATE quotation_line SET hsn_slab = hsn_slab WHERE quotation_id = CAST(:q AS uuid)",
                   {"q": sent}, "the lines of a sent quotation")


async def test_the_downgrade_refuses_while_a_document_carries_freight(
        db: AsyncSession, ids: Fixtures) -> None:
    """Code review F-5: dropping the columns would leave taxable and total holding
    freight nothing explains, and the identity CHECK would fail the next upgrade."""
    await _as_owner(db)
    q = await _quotation(db, ids, await _lead(db, ids))
    await db.execute(text(
        "UPDATE quotation SET freight_amount = 100, freight_slab = 18, freight_slab_chosen = false, "
        "freight_cgst = 9, freight_sgst = 9, freight_igst = 0, freight_total = 118, "
        "taxable = taxable + 100, total = total + 118 WHERE id = CAST(:q AS uuid)"), {"q": q})
    async with db.begin_nested() as sp:
        with pytest.raises(DBAPIError) as err:
            await _run(db, "downgrade")
        await sp.rollback()
    assert "documents carry freight" in str(err.value), err.value
