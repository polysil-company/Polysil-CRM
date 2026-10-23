"""Alembic environment.

Two things differ from the generated default:

1. The URL comes from Settings, so there is exactly one source of truth and no
   connection string in a committed file.
2. Migrations run over a *synchronous* psycopg connection. Alembic's async recipe
   works, but DDL through PgBouncer's transaction pooling is where advisory locks
   and session-scoped state get surprising, and a migration is the one place we do
   not want an extra layer of indirection between us and the server.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from api.config import get_settings
from api.db.session import Base

# Import every model module so Base.metadata is populated before autogenerate runs.
# Autogenerate is a draft regardless (CLAUDE.md 4.3), but an empty metadata makes it
# a draft that silently proposes dropping the entire schema.
import api.models  # noqa: F401  isort:skip

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    """The async DSN from Settings, rewritten for the sync driver Alembic uses."""
    url = str(get_settings().database_url)
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://").replace(
        "postgresql://", "postgresql+psycopg://"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # Postgres does transactional DDL, so a failed migration leaves nothing
            # half-applied.
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
