"""The grants app_anon holds, checked against the live schema.

Migration 003's grant block is guarded on the role existing. On a database migrated
before the role was created, it skipped every grant and said so only in a NOTICE
nobody reads. 003b re-issues them, with the same guard.

This test is what makes the guard safe: when DB_ANON_ROLE is set, a missing grant
is a red suite rather than a 42501 on the first real sign-in.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.conftest import _anon_role
from tests.db.test_migration_003_identity import PRE_AUTH

pytestmark = pytest.mark.db


async def test_anon_holds_execute_on_all_eight(db: AsyncSession) -> None:
    role = _anon_role()
    rows = (
        await db.execute(
            text(
                """
                SELECT p.proname, has_function_privilege(:role, p.oid, 'EXECUTE')
                  FROM pg_proc p
                  JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public' AND p.proname = ANY(:names)
                """
            ),
            {"role": role, "names": list(PRE_AUTH)},
        )
    ).all()
    granted = {name for name, ok in rows if ok}
    missing = set(PRE_AUTH) - granted
    assert not missing, (
        f"{role} cannot execute {sorted(missing)}. The guarded grant block skipped them; "
        f"run `alembic upgrade head` (003b) after creating the role."
    )
    assert len(rows) == len(PRE_AUTH), "a pre-auth function is missing from the schema"


async def test_anon_holds_schema_usage(db: AsyncSession) -> None:
    role = _anon_role()
    ok = (
        await db.execute(
            text("SELECT has_schema_privilege(:role, 'public', 'USAGE')"), {"role": role}
        )
    ).scalar_one()
    assert ok, f"{role} has no USAGE on schema public; every function call fails first"


async def test_anon_holds_no_table_privilege_at_all(db: AsyncSession) -> None:
    """The containment half. app_user holds every password hash, and app_anon must not
    be able to read it directly, only through the eight definer functions."""
    role = _anon_role()
    rows = (
        await db.execute(
            text(
                """
                SELECT c.relname, priv
                  FROM pg_class c
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) AS priv
                 WHERE n.nspname = 'public' AND c.relkind = 'r'
                   AND has_table_privilege(:role, c.oid, priv)
                """
            ),
            {"role": role},
        )
    ).all()
    assert not rows, f"{role} holds table privileges it must not: {rows}"
