"""FS-002 step 1: every application transaction runs as app_role.

The claim decides *who*; the role decides *whether RLS applies at all*. appuser owns
every table and is exempt from every policy, so a transaction that forgets the
switch makes every policy decorative (FS-002 5.2 fact 1). These tests assert the
switch through the real dependency, assert it does not leak across the pool, and
assert the grants are exactly the ones the spec lists.

Mutation-checked: change the `true` in `enter_role` to `false` and the leak test
fails; delete the `enter_role` call from `get_db` and the whoami test fails.

**After running the `false` mutation, restart PgBouncer** (`docker restart
polysil-pgbouncer-1`). A session-level role stays on every backend the mutated
requests touched, transaction pooling never resets it, and every later session
that lands there runs as app_role: the owner-run fixtures then fail with RLS
violations and permission errors that look like nothing to do with this file.
That happened during development and cost a full suite run to diagnose (ISS-057). It is
also exactly what the production leak would look like.
"""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, InternalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import Settings
from api.db.session import enter_role
from api.deps import DbSession, assert_runtime_role
from tests.conftest import Staff
from tests.db import migration_grants
from tests.db.test_claim_leak_through_deps import _token
from tests.db.test_migrations_001_002 import _closure_agrees

pytestmark = [pytest.mark.db, pytest.mark.rls]

ROUNDS = 12
REFUSED = (IntegrityError, InternalError, ProgrammingError, DBAPIError)

_MIG = Path(__file__).resolve().parents[2] / "api/db/migrations/versions/005_authorization.py"
_spec = importlib.util.spec_from_file_location("mig005", _MIG)
mig005 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mig005)


def _probe_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(db: DbSession) -> dict[str, str]:
        return {"role": (await db.execute(text("SELECT current_user"))).scalar_one()}

    return app


@pytest_asyncio.fixture
async def probe() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_probe_app()), base_url="http://probe"
    ) as c:
        yield c


# ── the switch itself ────────────────────────────────────────────────────────

async def test_enter_role_is_transaction_local(sessions: Callable[[], AsyncSession]) -> None:
    s = sessions()
    await enter_role(s, "app_role")
    assert (await s.execute(text("SELECT current_user"))).scalar_one() == "app_role"
    await s.rollback()
    assert (await s.execute(text("SELECT current_user"))).scalar_one() == "appuser"
    await s.rollback()


async def test_get_db_runs_as_app_role(probe: httpx.AsyncClient, staff: Staff,
                                       sessions: Callable[[], AsyncSession]) -> None:
    """The positive half. Delete the enter_role call from get_db and this fails."""
    token = await _token(staff, sessions)
    r = await probe.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["role"] == "app_role"


async def test_the_role_never_leaks_into_the_next_transaction(
        probe: httpx.AsyncClient, staff: Staff, sessions: Callable[[], AsyncSession]) -> None:
    """A request as app_role, then a plain transaction on the pool. If the role
    outlived its transaction, some backend is still app_role and the plain
    transaction reads it back. Under set_config(..., true) it never does.

    Mutation-checked: the `true` in enter_role becoming `false` makes this fail.
    """
    token = await _token(staff, sessions)
    leaked = 0
    for _ in range(ROUNDS):
        r = await probe.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert r.json()["role"] == "app_role"
        plain = sessions()
        seen = (await plain.execute(text("SELECT current_user"))).scalar_one()
        await plain.rollback()
        if seen != "appuser":
            leaked += 1
    assert leaked == 0, f"the role outlived its transaction {leaked} times out of {ROUNDS}"


# ── the grants ───────────────────────────────────────────────────────────────

async def test_grants_are_exactly_the_spec_table(db: AsyncSession) -> None:
    """FS-002 5.1. Both directions: every listed verb is held, and no verb is held
    on a table the list does not name. DELETE on no tree table (ISS-053)."""
    rows = (await db.execute(text(
        "SELECT c.relname, "
        "  has_table_privilege('app_role', c.oid, 'SELECT'), "
        "  has_table_privilege('app_role', c.oid, 'INSERT'), "
        "  has_table_privilege('app_role', c.oid, 'UPDATE'), "
        "  has_table_privilege('app_role', c.oid, 'DELETE') "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'alembic_version'"
    ))).all()
    verbs = ("SELECT", "INSERT", "UPDATE", "DELETE")
    actual = {r[0]: {v for v, held in zip(verbs, r[1:], strict=True) if held} for r in rows}
    # Unioned across migrations: 006 adds UPDATE to idempotency_record, which 005
    # created, so verb sets merge rather than one migration's dict winning.
    expected = migration_grants.grants()
    for table in set(actual) | set(expected):
        assert actual.get(table, set()) == expected.get(table, set()), table
    for tree in ("org_unit", "territory", "channel_partner"):
        assert "DELETE" not in actual[tree]
    # and nothing beyond the four verbs, on any table (code review, non-blocking)
    extra = (await db.execute(text(
        "SELECT c.relname, v FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, "
        "unnest(ARRAY['TRUNCATE', 'REFERENCES', 'TRIGGER']) v "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' "
        "AND has_table_privilege('app_role', c.oid, v)"))).all()
    assert extra == [], extra


async def test_app_role_can_execute_the_six_helpers(db: AsyncSession) -> None:
    for fn in mig005.HELPERS:
        ok = (await db.execute(text(
            "SELECT has_function_privilege('app_role', :f, 'EXECUTE')"), {"f": fn})).scalar_one()
        assert ok, fn


async def test_app_role_has_schema_usage(db: AsyncSession) -> None:
    ok = (await db.execute(text(
        "SELECT has_schema_privilege('app_role', 'public', 'USAGE')"))).scalar_one()
    assert ok


# ── tree writes under the role ───────────────────────────────────────────────

async def test_tree_writes_work_as_app_role_through_definer_triggers(
        db: AsyncSession, staff: Staff) -> None:
    """The cross-vendor finding. With the closures granted SELECT only, an invoker
    trigger inserting into them fails with 42501. As definer it does not.

    Since 005 the tree tables carry policies: INSERT needs masters.edit, so the
    caller is a staff user granted it here, as the owner, before the switch. The
    channel_partner tree is exercised in test_policies_005.
    """
    tag = uuid.uuid4().hex[:8]
    await db.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'masters', 'view', 'global'), (:r, 'masters', 'edit', 'global')"),
        {"r": staff.role_id})
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": staff.id})
    await enter_role(db, "app_role")
    parent = (await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('state', :n) RETURNING id"),
        {"n": f"rs_{tag}"})).scalar_one()
    child = (await db.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
        {"n": f"rs_{tag}_d", "p": parent})).scalar_one()
    depth = (await db.execute(text(
        "SELECT depth FROM territory_closure WHERE ancestor_id = :a AND descendant_id = :d"),
        {"a": parent, "d": child})).scalar_one()
    assert depth == 1
    org = (await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"rs_{tag}", "t": child})).scalar_one()
    self_row = (await db.execute(text(
        "SELECT count(*) FROM org_closure WHERE ancestor_id = :o AND descendant_id = :o"),
        {"o": org})).scalar_one()
    assert self_row == 1
    await _closure_agrees(db, "territory", "territory_closure")
    # The role_permission insert holds a share lock on the staff role row. The
    # staff fixture tears down before db does, and its DELETE FROM role waited
    # on this transaction forever (executed: 50 minutes). Release it here.
    await db.rollback()


async def test_app_role_cannot_write_a_closure_directly(db: AsyncSession) -> None:
    await enter_role(db, "app_role")
    with pytest.raises(REFUSED, match="permission denied"):
        async with db.begin_nested():
            await db.execute(text(
                "INSERT INTO org_closure (ancestor_id, descendant_id, depth) "
                "VALUES (gen_random_uuid(), gen_random_uuid(), 0)"))


async def test_the_two_tree_functions_are_definer_with_a_fixed_path(db: AsyncSession) -> None:
    rows = (await db.execute(text(
        "SELECT proname, prosecdef, proconfig FROM pg_proc "
        "WHERE proname IN ('closure_maintain', 'channel_partner_type_order', 'audit_row')"
    ))).all()
    assert len(rows) == 3
    for name, secdef, config in rows:
        assert secdef, f"{name} is not SECURITY DEFINER"
        # `public, pg_temp`, not `public`: the bare form still searches pg_temp
        # first (ISS-063, cross-vendor round on FS-002). 005 rewrote 004a's.
        assert config and "search_path=public, pg_temp" in config, (
            f"{name} has no fixed search_path, or pg_temp is not explicit: {config}")


# ── the guards ───────────────────────────────────────────────────────────────

async def test_the_migration_raises_without_the_role(db: AsyncSession) -> None:
    """Rule 14, ISS-052. The real role cannot be dropped, so the guard runs against
    a name that does not exist."""
    with pytest.raises(REFUSED, match="does not exist"):
        async with db.begin_nested():
            await db.execute(text(mig005.require_role_sql("no_such_role_probe")))


async def test_startup_refuses_outside_local_without_the_role() -> None:
    base = {"database_url": "postgresql+asyncpg://u:p@127.0.0.1:6432/appdb",
            "jwt_secret": "x" * 32, "public_web_url": "https://crm.polysil.in"}
    with pytest.raises(RuntimeError, match="does not exist"):
        await assert_runtime_role(Settings(_env_file=None, environment="staging",
                                           db_app_role="no_such_role_probe", **base))
    with pytest.raises(RuntimeError, match="unset"):
        await assert_runtime_role(Settings(_env_file=None, environment="staging",
                                           db_app_role=None, **base))


async def test_startup_only_warns_in_local() -> None:
    base = {"database_url": "postgresql+asyncpg://u:p@127.0.0.1:6432/appdb",
            "jwt_secret": "x" * 32}
    await assert_runtime_role(Settings(_env_file=None, environment="local",
                                       db_app_role="no_such_role_probe", **base))


async def test_startup_passes_with_the_real_role() -> None:
    await assert_runtime_role()
