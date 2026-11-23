"""Migration 014: the names of the people and partners on documents the caller can
see (RBAC.md 6.2, GAP-060), executed as the roles that call them.

The worlds come from migration 013's tests, so the seeded roles stand as they are.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_013 as m13
from tests.db.conftest import Fixtures

pytestmark = [pytest.mark.db, pytest.mark.rls]

SIGS = ["people_names(uuid[])", "partner_names(uuid[])"]


@pytest.mark.parametrize("sig", SIGS)
async def test_the_lookups_are_pinned_granted_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, has_function_privilege('app_role', CAST(:s AS regprocedure), 'EXECUTE') AS app, "
        "EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0) AS public "
        "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
    assert row.prosecdef and row.proconfig == ["search_path=public, pg_temp"]
    assert row.app and not row.public


async def _office_user(db: AsyncSession, w: m13.World, role: str) -> str:
    """Someone in an office of their own, outside the world's office subtree."""
    tag = uuid.uuid4().hex[:8]
    office = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 5, CAST(:t AS uuid)) RETURNING id"),
        {"n": f"m014_hq_{tag}", "t": w.state})).scalar_one())
    return await m13._user(db, role, office, tag)


async def _names(db: AsyncSession, who: str, ids: list[str]) -> set[str]:
    await m13._as(db, who)
    got = {str(r) for r in (await db.execute(text(
        "SELECT id FROM people_names(CAST(:ids AS uuid[]))"), {"ids": ids})).scalars()}
    await m13._as_owner(db)
    return got


async def test_a_manager_names_whoever_is_on_a_visible_order_and_no_one_else(
        db: AsyncSession) -> None:
    """An administrator at head office created the order: outside the manager's
    users scope, on a document the manager sees. A second administrator is on
    nothing the manager sees, and is not named: the lookup is not a directory."""
    w = await m13._world(db)
    creator = await _office_user(db, w, "admin_sales")
    stranger = await _office_user(db, w, "admin_sales")
    order = await m13._order(db, w)
    await db.execute(text("UPDATE sales_order SET created_by = CAST(:c AS uuid) WHERE id = CAST(:o AS uuid)"),
                     {"c": creator, "o": order})
    await m13._as(db, w.dm)
    direct = (await db.execute(text(
        "SELECT count(*) FROM app_user WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": [creator, stranger]})).scalar_one()
    await m13._as_owner(db)
    assert direct == 0, "the manager's users scope does not reach head office"
    assert await _names(db, w.dm, [creator, stranger, w.officer]) == {creator, w.officer}


async def test_a_partner_never_learns_who_approved_or_dispatched(db: AsyncSession,
                                                                 ids: Fixtures) -> None:
    """Question 15.14: the dealer sees its order and the officer who owns it, not the
    District Manager who decided its step or the dispatcher who shipped it."""
    w = await m13._world(db)
    dealer = str((await db.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "SELECT 'partner_user', :m, 'Dealer User', r.id, CAST(:p AS uuid) FROM role r WHERE r.code = 'dealer' "
        "RETURNING id"), {"m": "9196" + f"{uuid.uuid4().int % 10**8:08d}", "p": ids.dealer_id})).scalar_one())
    order = await m13._order(db, w, partner=ids.dealer_id)
    request = await m13._submit(db, w, order)
    steps = await m13._steps(db, request)
    await m13._decide(db, w.dm, steps[0].id)
    assert await _names(db, dealer, [w.officer, w.dm]) == {w.officer}
    assert await _names(db, w.sm, [w.officer, w.dm]) == {w.officer, w.dm}, \
        "staff on the order's chain see who decided"


async def test_a_partner_on_a_visible_lead_is_named_and_another_is_not(
        db: AsyncSession, ids: Fixtures) -> None:
    w = await m13._world(db)
    order = await m13._order(db, w, partner=ids.dealer_id)
    assert order
    await m13._as(db, w.officer)
    got = {str(r) for r in (await db.execute(text(
        "SELECT id FROM partner_names(CAST(:ids AS uuid[]))"),
        {"ids": [ids.dealer_id, ids.distributor_id]})).scalars()}
    await m13._as_owner(db)
    assert got == {str(ids.dealer_id)}
