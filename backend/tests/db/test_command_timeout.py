"""ISS-064: a statement whose reply never comes is an error, not a hang.

The tunnel to the development database dropped between a request and its reply
three times in one evening; each time the suite sat in select() with no error,
and looked like a slow run for thirty minutes. asyncpg's command_timeout turns
that into a failure after a bounded wait. Proved with pg_sleep through PgBouncer:
the timeout fires, asyncpg cancels the statement, and the connection is closed
rather than reused with a query still running on it.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from api.config import get_settings
from api.db.session import _make_engine, engine

pytestmark = pytest.mark.db


def test_the_application_engine_carries_the_timeout() -> None:
    settings = get_settings()
    assert settings.db_command_timeout is not None and settings.db_command_timeout > 0
    # NullPool: every checkout dials PgBouncer with these arguments
    assert engine.dialect.create_connect_args(engine.url)[1] is not None
    assert engine.pool._creator  # the creator closes over connect_args


async def test_a_statement_that_outlives_the_timeout_fails_rather_than_hangs() -> None:
    """A one-second engine against a three-second sleep. Under PgBouncer the
    cancel request reaches the right backend because the client is still linked
    to it for the whole transaction."""
    settings = get_settings().model_copy(update={"db_command_timeout": 1.0})
    short = _make_engine(settings)
    try:
        started = asyncio.get_running_loop().time()
        with pytest.raises((asyncio.TimeoutError, TimeoutError, DBAPIError)):
            async with short.connect() as c:
                await c.execute(text("SELECT pg_sleep(3)"))
        waited = asyncio.get_running_loop().time() - started
        assert waited < 2.5, f"the timeout did not bound the wait: {waited:.1f}s"
    finally:
        await short.dispose()


async def test_a_statement_within_the_timeout_is_unaffected() -> None:
    settings = get_settings().model_copy(update={"db_command_timeout": 5.0})
    short = _make_engine(settings)
    try:
        async with short.connect() as c:
            assert (await c.execute(text("SELECT pg_sleep(0.2), 1"))).one()[1] == 1
    finally:
        await short.dispose()
