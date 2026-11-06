"""087 (FS-084): the distributor definers are pinned and private, the pasted area
predicates are the generator's, and the quotation and order parent guards stored
in the database are the generator's text (plan review C-2, C-4, C-5)."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.policy_sql import branch_predicate, parent_guard_ddl
from tests.db.migration_grants import _load

pytestmark = [pytest.mark.db]

SIGNATURES = ("order_area_partner_ids()", "partner_supplies_caller_area(uuid)",
              "order_suppliers(text, integer)", "supplier_partner_tier(uuid)",
              "partner_orderable(uuid)")


def _norm(s: str) -> str:
    return " ".join(s.split())


async def test_the_functions_are_pinned_definers_not_callable_by_public(db: AsyncSession) -> None:
    for sig in SIGNATURES:
        row = (await db.execute(text(
            "SELECT p.prosecdef, p.proconfig, "
            "has_function_privilege('public', CAST(:s AS regprocedure), 'EXECUTE') AS pub, "
            "has_function_privilege('app_role', CAST(:s AS regprocedure), 'EXECUTE') AS app "
            "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
        assert row.prosecdef, sig
        assert "search_path=public, pg_temp" in (row.proconfig or []), sig
        assert row.pub is False, sig
        assert row.app is True, sig


def test_the_pasted_area_predicates_are_the_generators() -> None:
    m = _load("087_order_distributors")
    assert m is not None
    spec = SPECS["partners"]
    assert branch_predicate(spec, "org_subtree", write=True) == m.UNDER_OFFICES
    assert branch_predicate(spec, "territory") == m.UNDER_TERRITORIES


async def test_the_stored_parent_guards_are_the_generators(db: AsyncSession) -> None:
    """No test compared these before (plan review C-5). pg_get_functiondef adds its
    own header, so the generator's body is looked for inside it."""
    for module in ("quotations", "sales_orders"):
        spec = SPECS[module]
        made = parent_guard_ddl(spec)[0]
        body = made[made.index("BEGIN"):made.index("END $fn$")]
        stored = (await db.execute(text("SELECT pg_get_functiondef(CAST(:f AS regprocedure))"),
                                   {"f": f"{spec.table}_parent_guard()"})).scalar_one()
        assert _norm(body) in _norm(stored), module
        assert "partner_orderable(NEW.partner_id)" in stored


async def test_the_insert_policies_take_partner_orderable(db: AsyncSession) -> None:
    for table in ("quotation", "sales_order"):
        check = (await db.execute(text(
            "SELECT with_check FROM pg_policies WHERE tablename = :t AND policyname = :p"),
            {"t": table, "p": f"{table}_ins"})).scalar_one()
        assert "partner_orderable(partner_id)" in check and "partner_on_visible_document" not in check
