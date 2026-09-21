"""The definer bodies migration 008 pasted are what it says they are (007's idiom),
and the two ACLs the reviews asked for.

* `auth_issue_otp_challenge` is replaced with CREATE OR REPLACE: `app_anon` still
  executes it and PUBLIC does not. A DROP would have reset the ACL to
  PUBLIC-executable (007, executed), which for a function that queues a message
  to any number at the client's cost is the worst quiet failure available.
* `outbox_lead_withdrawn` is granted to `app_role` and to nobody else; the body
  refuses anyone but the system principal (test_functions_008).
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    m = _load("008_message_delivery")
    assert m is not None
    out: dict[str, str] = {}
    for stmt in [*m.FUNCTIONS, *m.REPLACED]:
        match = _HEAD.search(stmt)
        assert match, stmt[:80]
        out[match.group(1)] = stmt
    return out


def test_the_migration_names_two_bodies() -> None:
    assert sorted(_statements()) == ["auth_issue_otp_challenge", "outbox_lead_withdrawn"]


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
        "FROM pg_proc WHERE proname IN ('auth_issue_otp_challenge', "
        "'outbox_lead_withdrawn')"))).all())
    assert rows == {"auth_issue_otp_challenge": "vd", "outbox_lead_withdrawn": "sd"}


async def test_the_otp_definer_kept_its_grant_to_the_pre_auth_role(db: AsyncSession) -> None:
    sig = "auth_issue_otp_challenge(text, inet, text, int)"
    anon, public = (await db.execute(text(
        "SELECT has_function_privilege('app_anon', :s, 'EXECUTE'), "
        "has_function_privilege('public', :s, 'EXECUTE')"), {"s": sig})).one()
    assert anon is True and public is False


async def test_the_withdrawal_definer_is_granted_to_the_application_role_only(
        db: AsyncSession) -> None:
    sig = "outbox_lead_withdrawn(citext)"
    rows = (await db.execute(text(
        "SELECT has_function_privilege('app_role', :s, 'EXECUTE'), "
        "has_function_privilege('app_anon', :s, 'EXECUTE'), "
        "has_function_privilege('public', :s, 'EXECUTE')"), {"s": sig})).one()
    assert tuple(rows) == (True, False, False)
