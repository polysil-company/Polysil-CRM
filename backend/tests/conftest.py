"""Shared fixtures.

Postgres is never mocked. RLS is the security boundary and it only exists inside
the server, so a test that mocks the database proves nothing about the property
it claims to test (CLAUDE.md 1.4).

Everything connects through PgBouncer on 127.0.0.1:6432. The pooled-connection
test (RLS-13) is the reason: a plain SET instead of set_config(..., true) passes
every other test in this suite and fails only that one, and it can only fail
against a real transaction-mode pooler.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("ENVIRONMENT", "local")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """A session with no claim set.

    Deliberately unauthenticated: a test that wants an identity says so by using
    an `as_user` fixture, so no test acquires a claim by accident and then proves
    a policy that was never evaluated.
    """
    from api.db.session import async_session_factory

    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def sessions():
    """A factory for independent sessions, each on its own connection.

    The `db` fixture above is one session that rolls back, which is right for
    almost everything and useless for the three mechanisms in migration 003 that
    only exist under concurrency - an advisory lock and two row locks. Two
    statements in one transaction never contend, so a test written that way passes
    whether or not the lock is there.

    CLAUDE.md 4.1 rule 2 puts session creation in deps.py and worker/ only; this
    file is the third place, and the scaffold's own grep names it.
    """
    from api.db.session import async_session_factory

    opened = []

    def factory() -> AsyncSession:
        s = async_session_factory()
        opened.append(s)
        return s

    try:
        yield factory
    finally:
        for s in opened:
            await s.close()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """The real app over ASGI, with a cookie jar.

    Not a stub. The refresh cookie's flags, the error envelope, the status codes
    and the dependency's transaction boundary are all part of what is being
    tested, and every one of them lives outside the service functions.
    """
    from api.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def _redis_per_event_loop() -> AsyncIterator[None]:
    """Rebuild the Redis client for each test.

    `get_redis()` is `lru_cache`d, and an asyncio Redis client binds to the loop
    that first used it. pytest-asyncio gives each test its own loop, so the second
    test to touch Redis inherits a client pointing at a closed one and fails with
    "Event loop is closed" - which looks like a bug in the code under test and is
    not one.

    Closing happens here, inside the test's own loop, before the cache is cleared.
    """
    yield
    from api.integrations.cache import get_redis

    try:
        await get_redis().aclose()
    finally:
        get_redis.cache_clear()

# ── users, committed and cleaned up ──────────────────────────────────────────
#
# These live here rather than in tests/api/ because the claim-leak tests in
# tests/db/ need them too, and a conftest is only visible to its own directory
# downward. A test that needs a real signed-in user is not an API-layer concern.

PASSWORD = "correct horse battery staple"
_hasher = PasswordHasher()


@dataclass
class Staff:
    id: str
    email: str
    password: str
    org_unit_id: str
    role_id: str


@dataclass
class Dealer:
    id: str
    mobile: str


async def _cleanup(session: AsyncSession, *, user_ids: list[str],
                   identifiers: list[str], role_id: str, org_id: str | None,
                   territory_id: str, partner_ids: Sequence[str] = ()) -> None:
    for uid in user_ids:
        await session.execute(text("DELETE FROM activity_event WHERE entity_id = CAST(:i AS uuid)"),
                              {"i": uid})
        await session.execute(text("DELETE FROM app_user WHERE id = CAST(:i AS uuid)"), {"i": uid})
    for ident in identifiers:
        await session.execute(
            text("DELETE FROM login_attempt WHERE identifier = CAST(:i AS citext)"), {"i": ident})
        await session.execute(text("DELETE FROM notification_outbox WHERE recipient = :i"),
                              {"i": ident})
    await session.execute(text("DELETE FROM role_permission WHERE role_id = CAST(:r AS uuid)"),
                          {"r": role_id})
    await session.execute(text("DELETE FROM role WHERE id = CAST(:r AS uuid)"), {"r": role_id})
    if org_id:
        await session.execute(text("DELETE FROM org_unit WHERE id = CAST(:o AS uuid)"),
                              {"o": org_id})
    # After the users that point at them, before the territory they point at.
    # Deepest node first: parent_id is ON DELETE RESTRICT.
    for pid in partner_ids:
        await session.execute(text("DELETE FROM channel_partner WHERE id = CAST(:p AS uuid)"),
                              {"p": pid})
    await session.execute(text("DELETE FROM territory WHERE id = CAST(:t AS uuid)"),
                          {"t": territory_id})
    await session.commit()


@pytest_asyncio.fixture
async def staff(sessions: Callable[[], AsyncSession]) -> AsyncIterator[Staff]:
    tag = uuid.uuid4().hex[:10]
    email = f"staff_{tag}@polysil.in"
    s = sessions()
    territory = (await s.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"api_{tag}"})).scalar_one()
    org = (await s.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) "
        "VALUES (:n, 2, :t) RETURNING id"), {"n": f"api_{tag}", "t": territory})).scalar_one()
    role = (await s.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'District Manager', 2) RETURNING id"),
        {"c": f"api_dm_{tag}"})).scalar_one()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'org_subtree'), (:r, 'leads', 'create', 'org_subtree'), "
        "(:r, 'leads', 'edit', 'org_subtree')"),
        {"r": role})
    user = (await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, :p, 'Asha Patel', :r, :o) RETURNING id"),
        {"e": email, "p": _hasher.hash(PASSWORD), "r": role, "o": org})).scalar_one()
    await s.commit()

    try:
        yield Staff(str(user), email, PASSWORD, str(org), str(role))
    finally:
        await _cleanup(sessions(), user_ids=[str(user)], identifiers=[email],
                       role_id=str(role), org_id=str(org), territory_id=str(territory))


@pytest_asyncio.fixture
async def dealer(sessions: Callable[[], AsyncSession]) -> AsyncIterator[Dealer]:
    tag = uuid.uuid4().hex[:10]
    # Digits only. A hex tag puts letters in a phone number and every OTP call
    # then fails schema validation with a 422 that looks like a routing problem.
    mobile = "9198" + f"{uuid.uuid4().int % 10**8:08d}"
    s = sessions()
    territory = (await s.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"apid_{tag}"})).scalar_one()
    role = (await s.execute(text(
        "INSERT INTO role (code, name, level, is_portal) "
        "VALUES (:c, 'Dealer', 2, true) RETURNING id"), {"c": f"api_dl_{tag}"})).scalar_one()
    partner = (await s.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'API Dealer', :t, 'dealer') RETURNING id"),
        {"c": f"API-{tag}", "t": territory})).scalar_one()
    user = (await s.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "VALUES ('partner_user', :m, 'Bhavesh Shah', :r, :p) RETURNING id"),
        {"m": mobile, "r": role, "p": partner})).scalar_one()
    await s.commit()

    try:
        yield Dealer(str(user), mobile)
    finally:
        await _cleanup(sessions(), user_ids=[str(user)], identifiers=[mobile],
                       role_id=str(role), org_id=None, territory_id=str(territory),
                       partner_ids=[str(partner)])
