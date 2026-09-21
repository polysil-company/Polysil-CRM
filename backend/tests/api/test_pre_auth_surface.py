"""What the four pre-auth operations are allowed to say to the database.

FS-001 §10 asks for this by name, and the code review found it missing: *"for each
of the four endpoints that cannot present an access token, assert the service
issues only `SELECT auth_*(…)`, no bare table access."*

**It is invisible without a test.** `db_anon_role` is unset on the development box
(GAP-021), so `get_db_anon` switches to no role and the pre-auth path runs with
the application role's full table grants. A bare `SELECT * FROM app_user WHERE
mobile = :m` dropped into `verify_otp` would work perfectly here, pass every other
test in this suite, and raise `42501` for the first time in staging - which is
exactly how a missing `GRANT` reached a fourth review round twice.

So the assertion is on the statements themselves rather than on their results.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import auth as service
from tests.api.conftest import Dealer, Staff

pytestmark = pytest.mark.db

# Two conditions, both cheap to reason about. Trying to parse SQL with one regex
# was the first attempt and it rejected `SELECT auth_record_attempt(...)` while
# accepting things it should not - a matcher that is itself hard to get right is
# not a good guard.
_TABLES = (
    "app_user", "session", "login_attempt", "role", "role_permission",
    "user_territory", "notification_outbox", "activity_event",
    "idempotency_record", "territory", "org_unit", "audit_log",
    "org_closure", "territory_closure",
)
_IDENTIFIER = re.compile("[A-Za-z_][A-Za-z0-9_]*")


class RecordingSession:
    """Passes everything through to a real session and keeps the SQL.

    A mock would prove nothing here - the statements have to actually run, or the
    test asserts the shape of SQL that was never valid.
    """

    def __init__(self, inner: AsyncSession) -> None:
        self._inner = inner
        self.statements: list[str] = []

    async def execute(self, statement: Any, params: Any = None, **kw: Any) -> Any:
        self.statements.append(str(statement))
        return await self._inner.execute(statement, params, **kw)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


def _offenders(statements: list[str]) -> list[str]:
    """A statement is fine only if it calls a definer function and names no table.

    Identifiers are tokenised rather than matched as substrings, because substring
    matching is wrong in both directions: `auth_create_session` and `session_id`
    both contain "session" and neither refers to the table, while a bare
    `SELECT id FROM app_user` has to be caught.
    """
    bad = []
    for statement in statements:
        names = {token.lower() for token in _IDENTIFIER.findall(statement)}
        calls_definer = any(name.startswith("auth_") for name in names)
        touches_table = bool(names & set(_TABLES))
        if not calls_definer or touches_table:
            bad.append(statement)
    return bad



async def test_login_reaches_the_database_only_through_definer_functions(
        sessions: Callable[[], AsyncSession], staff: Staff) -> None:
    rec = RecordingSession(sessions())
    await service.login(rec, email=staff.email, password=staff.password,
                        user_agent="ua", ip="10.0.0.1")
    await rec.rollback()
    assert rec.statements, "the recorder saw nothing, so this asserts nothing"
    assert _offenders(rec.statements) == []


async def test_a_rejected_login_also_uses_only_definer_functions(
        sessions: Callable[[], AsyncSession], staff: Staff) -> None:
    """The rejection path writes a `login_attempt` row, so it is a path that talks
    to the database and has to obey the same rule."""
    rec = RecordingSession(sessions())
    await service.login(rec, email=staff.email, password="wrong",
                        user_agent="ua", ip="10.0.0.1")
    await rec.rollback()
    assert _offenders(rec.statements) == []


async def test_otp_request_and_verify_use_only_definer_functions(
        sessions: Callable[[], AsyncSession], dealer: Dealer) -> None:
    rec = RecordingSession(sessions())
    await service.request_otp(rec, mobile=dealer.mobile, ip="10.0.0.1")
    await rec.commit()

    code = await _queued_code(sessions(), dealer.mobile)
    rec2 = RecordingSession(sessions())
    await service.verify_otp(rec2, mobile=dealer.mobile, code=code,
                             user_agent="ua", ip="10.0.0.1")
    await rec2.rollback()

    assert _offenders(rec.statements + rec2.statements) == []


async def test_a_rejected_otp_verify_uses_only_definer_functions(
        sessions: Callable[[], AsyncSession], dealer: Dealer) -> None:
    rec = RecordingSession(sessions())
    await service.verify_otp(rec, mobile=dealer.mobile, code="000000",
                             user_agent="ua", ip="10.0.0.1")
    await rec.rollback()
    assert _offenders(rec.statements) == []


async def test_refresh_uses_only_definer_functions(
        sessions: Callable[[], AsyncSession], staff: Staff) -> None:
    setup = sessions()
    bundle = await service.login(setup, email=staff.email, password=staff.password,
                                 user_agent="ua", ip="10.0.0.1")
    await setup.commit()
    assert isinstance(bundle, service.Bundle)

    rec = RecordingSession(sessions())
    await service.refresh(rec, refresh_token=bundle.refresh_token,
                          user_agent="ua", ip="10.0.0.1")
    await rec.rollback()
    assert _offenders(rec.statements) == []


async def test_the_reuse_path_uses_only_definer_functions(
        sessions: Callable[[], AsyncSession], staff: Staff) -> None:
    """The classification query and the family revocation are both on this path,
    and the revocation is the one that must not become a bare UPDATE."""
    from api.config import get_settings
    from api.domain.auth import hash_refresh_token, refresh_replay_key
    from api.integrations import cache

    setup = sessions()
    bundle = await service.login(setup, email=staff.email, password=staff.password,
                                 user_agent="ua", ip="10.0.0.1")
    await setup.commit()
    assert isinstance(bundle, service.Bundle)

    rotate = sessions()
    await service.refresh(rotate, refresh_token=bundle.refresh_token,
                          user_agent="ua", ip="10.0.0.1")
    await rotate.commit()

    secret = get_settings().jwt_secret.get_secret_value()
    await cache.get_redis().delete(
        refresh_replay_key(secret, hash_refresh_token(bundle.refresh_token)))

    rec = RecordingSession(sessions())
    outcome = await service.refresh(rec, refresh_token=bundle.refresh_token,
                                    user_agent="ua", ip="10.0.0.1")
    await rec.rollback()
    assert isinstance(outcome, service.Failure)
    assert _offenders(rec.statements) == []


async def test_logout_uses_only_definer_functions(
        sessions: Callable[[], AsyncSession], staff: Staff) -> None:
    setup = sessions()
    bundle = await service.login(setup, email=staff.email, password=staff.password,
                                 user_agent="ua", ip="10.0.0.1")
    await setup.commit()
    assert isinstance(bundle, service.Bundle)

    rec = RecordingSession(sessions())
    await service.logout(rec, session_id=None, refresh_token=bundle.refresh_token)
    await rec.rollback()
    assert _offenders(rec.statements) == []


async def test_the_matcher_would_catch_a_bare_table_read() -> None:
    """The test above is only worth having if this is true.

    Without it, a matcher that accidentally matched everything would make all six
    of those tests pass while asserting nothing.
    """
    assert _offenders(["SELECT * FROM auth_lookup_by_mobile(:m)"]) == []
    assert _offenders(["SELECT auth_record_attempt(:a, :b, :c, :d)"]) == []
    for bare in (
        "SELECT id FROM app_user WHERE mobile = :m",
        "UPDATE session SET used_at = now() WHERE refresh_token_hash = :h",
        "  select password_hash from app_user",
        "INSERT INTO login_attempt (identifier) VALUES (:i)",
    ):
        assert _offenders([bare]) == [bare], bare


async def _queued_code(session: AsyncSession, mobile: str) -> str:
    got = await session.execute(
        text("SELECT payload ->> 'code' FROM notification_outbox WHERE recipient = :m "
             "ORDER BY created_at DESC LIMIT 1"), {"m": mobile})
    code = got.scalar_one()
    await session.rollback()
    return str(code)


async def test_me_is_not_on_the_pre_auth_surface(
        sessions: Callable[[], AsyncSession], staff: Staff) -> None:
    """The exception that proves the rule is scoped correctly.

    `/auth/me` runs on `get_db` with a claim set, so it reads its own tables
    directly - and must, since no definer function returns a permission list. A
    rule applied to it would be the wrong rule.
    """
    rec = RecordingSession(sessions())
    await service.me(rec, user_id=staff.id)
    await rec.rollback()
    assert _offenders(rec.statements), "me() went through definer functions, unexpectedly"


async def test_an_unknown_number_still_only_uses_definer_functions(
        sessions: Callable[[], AsyncSession]) -> None:
    rec = RecordingSession(sessions())
    await service.request_otp(rec, mobile="9195" + f"{uuid.uuid4().int % 10**8:08d}",
                              ip="10.0.0.1")
    await rec.rollback()
    assert _offenders(rec.statements) == []
