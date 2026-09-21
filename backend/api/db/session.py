"""The engine, and nothing that opens a transaction.

Sessions are created only in api/deps.py and worker/ (CLAUDE.md 4.1 rule 2).
A CI grep fails the build on `async_session_factory(` anywhere else, because
SET LOCAL claim propagation depends on exactly one place owning the boundary.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from api.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base for every model in api/models/."""


def _make_engine(settings: Settings | None = None) -> AsyncEngine:
    """The application engine. `settings` is for tests that need a different
    timeout; the application passes nothing and gets the process settings."""
    settings = settings or get_settings()
    connect_args: dict[str, object] = {
        # Prepared statements are per-backend, and PgBouncer hands the next
        # statement a different backend. Both caches have to be off or the next
        # request on a recycled connection fails with "prepared statement
        # _asyncpg_stmt_1 does not exist".
        #
        # Both are DBAPI arguments, not engine arguments. statement_cache_size
        # is asyncpg's own; prepared_statement_cache_size is SQLAlchemy's, and
        # despite the name it is handled by the dialect's DBAPI emulation, so
        # passing it to create_async_engine raises TypeError at import.
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        # Turning the caches off is not sufficient on its own. asyncpg still
        # prepares every statement, and it names them in numeric order per
        # connection - so two application connections landing on one PgBouncer
        # server connection collide on __asyncpg_stmt_1__. A unique name per
        # prepare is the documented fix (asyncpg #837, SQLAlchemy #6467).
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }
    if settings.db_command_timeout is not None:
        # ISS-064: a lost reply is an error after this long, not a hang.
        connect_args["command_timeout"] = settings.db_command_timeout
    return create_async_engine(
        str(settings.database_url),
        # PgBouncer in transaction mode hands the next statement a different
        # backend, so a second pool on top of it is both pointless and a source of
        # stale-connection errors. NullPool leaves pooling to PgBouncer, which is
        # the layer that actually knows.
        poolclass=NullPool,
        connect_args=connect_args,
        echo=False,
    )


engine: AsyncEngine = _make_engine()

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
)


async def enter_role(session: AsyncSession, role: str | None) -> None:
    """Switch the current transaction into `role`, transaction-locally.

    `set_config('role', ..., true)` rather than `SET LOCAL ROLE`: a role name cannot
    be a bind parameter and this form takes one. `true` scopes it to the transaction,
    for the same reason the claim is: under PgBouncer's transaction pooling a plain
    SET leaks the role onto whichever request next borrows the connection.

    This is the statement that makes RLS apply at all. `appuser` owns every table
    and is exempt from every policy; `app_role` owns nothing. FS-002 5.1, 5.2 fact 1.
    """
    if role:
        await session.execute(text("SELECT set_config('role', :r, true)"), {"r": role})
