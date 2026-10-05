"""Half one of the parity suite: the permission matrix (FS-002 5.5).

22 modules x 16 roles x 5 actions = 1,760 cells, enumerated from RBAC.md section
6 by the seed generator and never from what happens to be seeded. For each cell
both layers must agree with the document: app_has_permission() is true exactly
where the matrix has a cell, app_scope() is the cell's scope, and require()
raises 403 where it is blank. the rest of the 1,760 are blank; those are the
assertions that matter (FS-002 9.3 A-1).

The matrix rows are written inside the rolled-back transaction, over whatever the
demo seed left, so the test does not depend on the seed and cannot bless it.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, scope_predicate
from api.db.session import enter_role
from api.deps import require
from api.domain.authz import ACTIONS, denied_cells, modules_in, roles_in
from api.errors import ForbiddenError
from scripts.generate_permission_seed import as_sql, load_grants
from tests.db.conftest import Fixtures

pytestmark = [pytest.mark.db, pytest.mark.rls]

GRANTS = load_grants()
ROLES = roles_in(GRANTS)
MODULES = modules_in(GRANTS)
GRANTED: dict[tuple[str, str, str], str] = {(g.role, g.module, g.action): g.scope for g in GRANTS}
DENIED = denied_cells(GRANTS)
PORTAL = {"distributor", "dealer", "sub_dealer"}


def test_the_matrix_is_sixteen_by_twenty_two_by_five() -> None:
    """ISS-031: 1,600, not 1,440; FS-021 adds `tracking`, FS-025 `targets`. The generator enumerates
    rather than hard-codes, so this is the one place the count is asserted."""
    assert len(ROLES) == 16
    assert len(MODULES) == 22
    assert len(ACTIONS) == 5
    assert len(GRANTED) + len(DENIED) == 1760
    assert "tracking" in MODULES


def test_the_board_sees_everything_except_tracking_and_stock() -> None:
    """RBAC.md 6.4's Except line (FS-021 GAP-195, FS-023 B-1). The board's other
    modules are untouched, and no portal role holds stock."""
    for m in ('tracking', 'stock'):
        assert ('board', m, 'view') in DENIED
    assert all(('board', m, 'view') in GRANTED for m in MODULES if m not in ('tracking', 'stock'))
    assert all((r, 'stock', 'view') in DENIED for r in PORTAL)
    assert "campaigns" in MODULES and "stock" in MODULES


@pytest_asyncio.fixture
async def matrix(db: AsyncSession, ids: Fixtures) -> dict[str, str]:
    """role code -> the id of a user holding that role, with the matrix rows in
    place of whatever the seed put there. Rolled back with the test."""
    for code in ROLES:
        await db.execute(text(
            "INSERT INTO role (code, name, level, is_portal) VALUES (:c, :n, 1, :p) "
            "ON CONFLICT (code) DO NOTHING"), {"c": code, "n": code, "p": code in PORTAL})
    await db.execute(text(
        "DELETE FROM role_permission WHERE role_id IN "
        "(SELECT id FROM role WHERE code = ANY(CAST(:c AS text[])))"), {"c": list(ROLES)})
    await db.execute(text(as_sql(GRANTS)))
    sub_dealer = (await db.execute(text(
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES (:p, 'sub_dealer', :c, 'x', :t, 'sub_dealer') RETURNING id"),
        {"p": ids.dealer_id, "c": ids.unique("SUB"), "t": ids.territory_id})).scalar_one()
    # 007's role-family trigger holds a portal role to its partner type's seeded
    # level, so each portal user is anchored on a partner of its own type.
    anchors = {"distributor": ids.distributor_id, "dealer": ids.dealer_id,
               "sub_dealer": str(sub_dealer)}
    users: dict[str, str] = {}
    for code in ROLES:
        tag = uuid.uuid4().hex[:8]
        if code in PORTAL:
            row = await db.execute(text(
                "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
                "SELECT 'partner_user', :m, :n, r.id, :p FROM role r WHERE r.code = :c "
                "RETURNING id"),
                {"m": "9177" + f"{uuid.uuid4().int % 10**8:08d}", "n": code, "c": code,
                                  "p": anchors[code]})
        else:
            row = await db.execute(text(
                "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
                "SELECT 'staff', :e, :n, r.id, :o FROM role r WHERE r.code = :c "
                "RETURNING id"), {"e": f"{code}_{tag}@polysil.in", "n": code, "c": code,
                                  "o": ids.org_unit_id})
        users[code] = str(row.scalar_one())
    return users


async def _claim(db: AsyncSession, user_id: str) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})


async def test_the_database_answers_every_cell_from_the_matrix(
        db: AsyncSession, matrix: dict[str, str]) -> None:
    """All 1,760, one statement per role, as app_role. A cell the document leaves
    blank must be false, and app_scope() must be the view row's scope or NULL."""
    await enter_role(db, "app_role")
    wrong: list[tuple[str, str, str, object, object]] = []
    checked = 0
    for role, user in matrix.items():
        await _claim(db, user)
        rows = (await db.execute(text(
            "SELECT m, a, app_has_permission(m, a), app_scope(m) "
            "FROM unnest(CAST(:mods AS text[])) m CROSS JOIN unnest(CAST(:acts AS text[])) a"),
            {"mods": list(MODULES), "acts": list(ACTIONS)})).all()
        for module, action, allowed, scope in rows:
            checked += 1
            expected = (role, module, action) in GRANTED
            expected_scope = GRANTED.get((role, module, "view"))
            if allowed != expected or scope != expected_scope:
                wrong.append((role, module, action, allowed, scope))
    assert checked == 1760
    assert not wrong, f"{len(wrong)} cells disagree with RBAC.md: {wrong[:10]}"


async def test_require_answers_403_exactly_where_the_cell_is_blank(
        db: AsyncSession, matrix: dict[str, str]) -> None:
    """The service gate. require() asks app_has_permission() inside the same
    transaction, so one granted and one blank cell per role is the assertion that
    it reads the same row the policies read; the full 1,760 are the test above."""
    await enter_role(db, "app_role")
    for role, user in matrix.items():
        await _claim(db, user)
        module, action = next((m, a) for r, m, a in GRANTED if r == role)
        await require(module, action)(db)
        module, action = next((m, a) for r, m, a in sorted(DENIED) if r == role)
        with pytest.raises(ForbiddenError):
            await require(module, action)(db)


def test_the_predicate_gives_a_blank_view_cell_only_the_self_row() -> None:
    """Enforcer 1, without a database. For every role with no view on a module
    that has a ScopeSpec, the service predicate is the self clause or false,
    never an unscoped read (rule 2)."""
    import sqlalchemy as sa

    for name, spec in SPECS.items():
        t = sa.table(spec.table, sa.column("id"), sa.column("deleted_at"))
        for role in ROLES:
            if (role, name, "view") in GRANTED:
                continue
            caller = Caller(user_id="u", org_unit_id=None, partner_id=None, scopes={})
            clause = str(scope_predicate(spec, caller, t))
            assert clause in (
                "false", f"{spec.table}.id = :id_1 AND {spec.table}.deleted_at IS NULL",
            ), (role, name, clause)


def test_the_system_principal_is_not_in_the_matrix() -> None:
    assert "system" not in ROLES
