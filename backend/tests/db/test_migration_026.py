"""Migration 026 (FS-015b): complaint remedies at the database level. The flows are
the API tests'; these hold the grants, the seeds and the engine's new arms."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.db, pytest.mark.rls]

GRANTED = ["complaint_remedy_choose(uuid,text,numeric,text,uuid,text)",
           "complaint_remedy_replacement(uuid,jsonb,jsonb,text)", "complaint_remedy_withdraw(uuid,text)",
           "complaint_remedy_order(uuid)", "order_complaint(uuid)"]
INTERNAL = ["complaint_close(uuid,text)", "complaint_refund_outcome(uuid,text)",
            "complaint_replacement_progress(uuid)"]


def _m026():  # type: ignore[no-untyped-def]
    path = next((Path(__file__).parents[2] / "api" / "db" / "migrations" / "versions").glob("026_*.py"))
    spec = importlib.util.spec_from_file_location("m026_for_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("sig", GRANTED + INTERNAL)
async def test_every_new_definer_is_pinned_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
    assert row[0], f"{sig} is SECURITY DEFINER"
    assert "search_path=public, pg_temp" in (row[1] or []), row[1]
    assert not row[2], f"{sig} is not PUBLIC-executable"


@pytest.mark.parametrize("sig", GRANTED)
async def test_the_entry_points_are_granted(db: AsyncSession, sig: str) -> None:
    assert (await db.execute(text("SELECT has_function_privilege('app_role', :s, 'EXECUTE')"), {"s": sig})).scalar_one()


@pytest.mark.parametrize("sig", INTERNAL)
async def test_the_internal_functions_are_not_granted(db: AsyncSession, sig: str) -> None:
    assert not (await db.execute(text("SELECT has_function_privilege('app_role', :s, 'EXECUTE')"), {"s": sig})).scalar_one()


async def test_app_role_writes_a_remedy_only_through_the_definers(db: AsyncSession) -> None:
    for verb in ("INSERT", "UPDATE", "DELETE"):
        assert not (await db.execute(text("SELECT has_table_privilege('app_role', 'complaint_remedy', :v)"),
                                     {"v": verb})).scalar_one(), verb
    for column in ("status", "closed_at"):
        assert not (await db.execute(text("SELECT has_column_privilege('app_role', 'complaint', :c, 'UPDATE')"),
                                     {"c": column})).scalar_one(), column


async def test_the_seeds_are_in_the_migration(db: AsyncSession) -> None:
    """ISS-102: rows only a seed script writes never reach staging (plan review B7)."""
    limits = dict((await db.execute(text(
        "SELECT r.code, t.max_amount FROM approval_threshold t JOIN role r ON r.id = t.role_id "
        "WHERE t.doc_type = 'complaint' AND t.territory_id IS NULL AND t.deleted_at IS NULL"))).all())
    assert set(limits) == {"district_manager", "state_manager", "regional_manager"}
    assert limits["regional_manager"] is None
    held = (await db.execute(text(
        "SELECT rp.scope::text FROM role_permission rp JOIN role r ON r.id = rp.role_id "
        "WHERE r.code = 'account_manager' AND rp.module = 'complaints' AND rp.action = 'view' "
        "AND rp.deleted_at IS NULL"))).scalar_one()
    assert held == "global"
    approve = (await db.execute(text(
        "SELECT count(*) FROM role_permission rp JOIN role r ON r.id = rp.role_id "
        "WHERE r.code = 'account_manager' AND rp.module = 'complaints' AND rp.action = 'approve' "
        "AND rp.deleted_at IS NULL"))).scalar_one()
    assert approve == 0, "approve would let Accounts give QC verdicts"


async def test_a_refund_chain_ends_with_accounts_and_an_order_chain_is_unchanged(db: AsyncSession) -> None:
    async def roles(doc_type: str, amount: int) -> list[str]:
        return list((await db.execute(text(
            "SELECT r.code::text FROM unnest(approval_chain(:d, :a, NULL, 0)) WITH ORDINALITY AS c(id, n) "
            "JOIN role r ON r.id = c.id ORDER BY c.n"), {"d": doc_type, "a": amount})).scalars())
    refund = await roles("complaint", 50000)
    assert refund[-1] == "account_manager" and "dispatch_manager" not in refund
    assert refund[:2] == ["district_manager", "state_manager"]
    order = await roles("sales_order", 50000)
    assert order[-2:] == ["account_manager", "dispatch_manager"], "orders keep Accounts and Dispatch"


def test_a_changed_anchor_fails_the_migration() -> None:
    m = _m026()
    with pytest.raises(RuntimeError, match="anchor not found once"):
        m._replace("CREATE FUNCTION f() ... body", "an anchor that is not there", "x")
    with pytest.raises(RuntimeError, match="anchor not found once"):
        m._replace("twice twice", "twice", "x")
    # every patch builds from the live text of the migrations before it
    assert len(m._engine_patched()) == 7 and len(m._orders_patched()) == 5 and len(m._bell_patched()) == 2


async def test_the_closed_check_pairs_the_status_and_its_time(db: AsyncSession) -> None:
    defn = (await db.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_complaint_closed'"))).scalar_one()
    assert "closed" in defn and "closed_at" in defn
