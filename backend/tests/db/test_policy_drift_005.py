"""The live policies match a regeneration, every policy column is indexed, and
every helper call site is hoisted to an InitPlan (FS-002 10: generator, plan).

Drift: for each table, snapshot pg_policies, drop and re-create the policies from
the current declaration inside a savepoint, snapshot again, roll back, compare.
The deparsed text is what Postgres stores, so two identical statements give
identical text and any edit to a ScopeSpec without a migration is a red suite.

Plan: EXPLAIN as app_role. A helper call the planner hoisted appears as $n in the
Filter line and the call itself in an InitPlan block. A bare call appears in the
Filter line, per row. The assertion is on every Filter line, not on the presence
of some InitPlan (ISS-056).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz import consumer_floor
from api.authz.modules import SPECS
from api.authz.policy_sql import drop_policies_for, has_bare_helper_call, indexes_for, policies_for
from api.db.session import enter_role
from tests.db import migration_grants
from tests.db.conftest import Fixtures, make_staff

pytestmark = [pytest.mark.db, pytest.mark.rls]

_MIG = Path(__file__).resolve().parents[2] / "api/db/migrations/versions/005_authorization.py"
_spec = importlib.util.spec_from_file_location("mig005_drift", _MIG)
mig005 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mig005)

_NAME = re.compile(r"CREATE POLICY (\w+) ON (\w+)")
_HELPER = re.compile(r"app_(?:scope|has_permission|current_\w+|is_system)\(")


async def _snapshot(db: AsyncSession, table: str) -> list[tuple]:
    """The table's own policies. The consumer floor (052) sits on every RLS table and
    is checked on its own, by tests/db/test_consumer_floor.py."""
    return [tuple(r) for r in (await db.execute(text(
        "SELECT policyname, permissive, cmd, roles, qual, with_check "
        "FROM pg_policies WHERE tablename = :t AND policyname <> :floor ORDER BY policyname"),
        {"t": table, "floor": consumer_floor.name(table)})).all()]


async def _regenerated(db: AsyncSession, table: str, drops: list[str],
                       creates: list[str]) -> list[tuple]:
    await db.execute(text("SAVEPOINT regen"))
    for stmt in drops:
        await db.execute(text(stmt))
    for stmt in creates:
        await db.execute(text(stmt))
    after = await _snapshot(db, table)
    await db.execute(text("ROLLBACK TO SAVEPOINT regen"))
    return after


@pytest.mark.parametrize("module", sorted(SPECS))
async def test_the_generated_policies_have_not_drifted(db: AsyncSession, module: str) -> None:
    spec = SPECS[module]
    before = await _snapshot(db, spec.table)
    assert before, f"{spec.table} has no policies"
    generated = [s for s in policies_for(spec) if s.startswith("CREATE POLICY")]
    assert {m.group(1) for s in generated for m in [_NAME.match(s)] if m} == {r[0] for r in before}
    after = await _regenerated(db, spec.table, drop_policies_for(spec), generated)
    assert after == before, "\n".join(str(r) for r in after if r not in before)


async def test_the_activity_event_literals_match_their_generator(db: AsyncSession) -> None:
    """Code review F-6: api/authz/activity.py was read by nothing. The migration
    keeps the literals, like the generated policies; this holds them equal."""
    from api.authz import activity

    # The union, last-declaration-wins by name: 006's activity_event_sel (with the
    # lead arm) supersedes 005's, and equals what the module emits now.
    stmt = next(s for t, s in migration_grants.hand_policies()
                if s.startswith("CREATE POLICY activity_event_sel"))
    assert stmt == activity.policy_sql()
    before = (await db.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'ck_activity_event_reference'"))).scalar_one()
    await db.execute(text("SAVEPOINT ck"))
    await db.execute(text("ALTER TABLE activity_event DROP CONSTRAINT ck_activity_event_reference"))
    await db.execute(text("ALTER TABLE activity_event ADD CONSTRAINT ck_activity_event_reference "
                          f"CHECK ({activity.check_sql()})"))
    after = (await db.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'ck_activity_event_reference'"))).scalar_one()
    await db.execute(text("ROLLBACK TO SAVEPOINT ck"))
    assert after == before


def _hand_by_table() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for table, stmt in migration_grants.hand_policies():
        out.setdefault(table, []).append(stmt)
    return out


@pytest.mark.parametrize("table", sorted(_hand_by_table()))
async def test_the_hand_written_policies_have_not_drifted(db: AsyncSession, table: str) -> None:
    creates = _hand_by_table()[table]
    names = [m.group(1) for s in creates for m in [_NAME.match(s)] if m]
    before = await _snapshot(db, table)
    assert {r[0] for r in before} == set(names), (set(names) ^ {r[0] for r in before})
    drops = [f"DROP POLICY {n} ON {table}" for n in names]
    after = await _regenerated(db, table, drops, creates)
    assert after == before


async def test_no_table_carries_a_policy_the_migration_does_not_declare(db: AsyncSession) -> None:
    live = {(r[0], r[1]) for r in (await db.execute(text(
        "SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'public'"))).all()}
    declared = {(t, m.group(1)) for t, s in migration_grants.hand_policies()
                for m in [_NAME.match(s)] if m}
    for spec in SPECS.values():
        declared |= {(spec.table, m.group(1)) for s in policies_for(spec)
                     for m in [_NAME.match(s)] if m}
    rls = (await db.execute(text(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity"))).scalars().all()
    declared |= {(t, consumer_floor.name(t)) for t in rls}
    assert live == declared, live ^ declared


@pytest.mark.parametrize("module", sorted(SPECS))
async def test_every_policy_column_is_indexed(db: AsyncSession, module: str) -> None:
    """Rule 9. The generator names the index; the migration must have created it."""
    for stmt in indexes_for(SPECS[module]):
        name = stmt.split(" ")[5]
        found = (await db.execute(text(
            "SELECT count(*) FROM pg_indexes WHERE indexname = :n"), {"n": name})).scalar_one()
        assert found == 1, name


async def test_no_live_policy_has_a_bare_helper_call(db: AsyncSession) -> None:
    """ISS-056, against what Postgres stores rather than what the source says."""
    rows = (await db.execute(text(
        "SELECT policyname, qual, with_check FROM pg_policies WHERE schemaname = 'public'"
    ))).all()
    assert rows
    for name, qual, check in rows:
        for expr in (qual, check):
            if expr:
                assert not has_bare_helper_call(expr), (name, expr)


@pytest.mark.parametrize("statement", [
    "SELECT * FROM app_user",
    "UPDATE app_user SET full_name = full_name",
    "SELECT * FROM channel_partner",
    "UPDATE channel_partner SET name = name",
    "SELECT * FROM session",
    "SELECT * FROM activity_event",
    "SELECT * FROM idempotency_record",
])
async def test_every_helper_call_site_is_an_initplan(
        db: AsyncSession, ids: Fixtures, statement: str) -> None:
    """Per call site. A Filter line naming a helper is a per-row call."""
    for module in ("users", "partners"):
        await db.execute(text(
            "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
            "(:r, :m, 'view', 'org_subtree'), (:r, :m, 'edit', 'org_subtree')"),
            {"r": ids.staff_role_id, "m": module})
    me = await make_staff(db, ids, email=ids.unique("plan") + "@polysil.in")
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(me)})
    await enter_role(db, "app_role")
    plan = [r[0] for r in (await db.execute(text(f"EXPLAIN (COSTS OFF) {statement}"))).all()]
    joined = "\n".join(plan)
    assert "InitPlan" in joined, joined
    for line in plan:
        if "Filter" in line or "Cond" in line:
            assert not _HELPER.search(line), f"per-row helper call in: {line}\n{joined}"
