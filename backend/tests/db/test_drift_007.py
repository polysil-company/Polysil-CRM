"""The definer bodies migration 007 pasted are what it says they are (ISS-071's
idiom, extended). Three things are held here:

* the visibility guard inside `authz_user_in_scope()` is the generator's text for
  the users module, so the five guarded functions cannot drift from the policies;
* every body 007 creates or replaces is what the live database holds, whitespace
  aside, so a hotfix applied by hand to the database shows up as drift;
* the two pickers that share a candidate's row are VOLATILE: a STABLE body with
  `FOR SHARE` creates cleanly and fails only when called (0A000, executed).
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.policy_sql import guard_sql
from tests.db.migration_grants import _load

pytestmark = pytest.mark.db

_HEAD = re.compile(r"CREATE (?:OR REPLACE )?FUNCTION (\w+)\(")


def _norm(s: str) -> str:
    return " ".join(s.split())


def _body(stmt: str) -> str:
    """The text between the dollar quotes, whichever tag delimits them: the
    migration writes $fn$, pg_get_functiondef() renders $function$."""
    tag = "$fn$" if "$fn$" in stmt else "$function$"
    first = stmt.index(tag) + len(tag)
    last = stmt.rindex(tag)
    return _norm(stmt[first:last])


def _statements() -> dict[str, str]:
    m = _load("007_administration")
    assert m is not None
    out: dict[str, str] = {}
    for stmt in [*m.FUNCTIONS, *m.REPLACED, *m.TRIGGER_FUNCTIONS, m.AUTH_CREATE_SESSION_007]:
        match = _HEAD.search(stmt)
        assert match, stmt[:80]
        out[match.group(1)] = stmt
    return out


def test_the_users_guard_inside_authz_user_in_scope_is_the_generators() -> None:
    stmts = _statements()
    assert _norm(guard_sql(SPECS["users"])) in _norm(stmts["authz_user_in_scope"])


def test_the_partners_guard_inside_the_partner_counts_is_the_generators() -> None:
    stmts = _statements()
    assert _norm(guard_sql(SPECS["partners"])) in _norm(stmts["channel_partner_user_counts"])


def test_the_migration_names_twenty_two_bodies() -> None:
    """Thirteen new, five replaced, five trigger functions, and the session minter."""
    assert len(_statements()) == 24


@pytest.mark.parametrize("name", sorted(_statements()))
async def test_the_live_body_is_the_migration_text(db: AsyncSession, name: str) -> None:
    stmt = _statements()[name]
    live = (await db.execute(text(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = :n"), {"n": name})).scalars().all()
    assert len(live) == 1, f"{name}: {len(live)} rows in pg_proc"
    assert _body(live[0]) == _body(stmt)


async def test_volatility_and_definer_flags(db: AsyncSession) -> None:
    rows = dict((await db.execute(text(
        "SELECT proname, CAST(provolatile AS text) || CASE WHEN prosecdef THEN 'd' ELSE 'i' END "
        "FROM pg_proc WHERE proname IN ('authz_user_assignable', 'lead_auto_owner', "
        "'staff_directory', 'app_user_role_family_check', 'app_user_admin_floor', "
        "'org_unit_close_guard', 'territory_code_guard', 'channel_partner_guarded_columns', "
        "'auth_locked_until', 'authz_user_in_scope', 'lead_state_code', "
        "'role_permission_admin_floor')"))).all())
    assert rows == {
        "authz_user_assignable": "vd", "lead_auto_owner": "vd", "staff_directory": "sd",
        "app_user_role_family_check": "vd", "app_user_admin_floor": "vd",
        "org_unit_close_guard": "vd", "territory_code_guard": "vd",
        "channel_partner_guarded_columns": "vd",
        "auth_locked_until": "sd", "authz_user_in_scope": "sd",
        "lead_state_code": "vd", "role_permission_admin_floor": "vd",
    }


async def test_the_two_private_helpers_are_granted_to_nobody(db: AsyncSession) -> None:
    """auth_locked_until is a lockout oracle and authz_user_in_scope a visibility
    oracle; both are reached only inside the definers that own them."""
    rows = (await db.execute(text(
        "SELECT p.proname, r.rolname FROM pg_proc p CROSS JOIN pg_roles r "
        "WHERE p.proname IN ('auth_locked_until', 'authz_user_in_scope') "
        "AND r.rolname IN ('app_role', 'app_anon', 'public') "
        "AND has_function_privilege(r.rolname, p.oid, 'EXECUTE')"))).all()
    assert rows == []
