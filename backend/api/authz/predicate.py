"""Enforcer 1: the service-layer predicate, from the same declaration.

Stage 3 of FS-002 section 3 resolves the caller once per request into a `Caller`;
stage 4 applies `scope_predicate()` to every read and `parent_in_scope()` to every
foreign key on a write. RLS re-checks both underneath. Neither layer is written
by hand: the SQL emitter and this module read the same `ScopeSpec`.

This module imports SQLAlchemy, so it lives here and not in `domain/` (rule 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql import ColumnElement, TableClause

from api.domain.authz import ScopeSpec

# Typed as uuid on purpose. An untyped column binds a caller id as VARCHAR and
# Postgres refuses `uuid = character varying`; the parity suite found this the
# first time the predicate ran against a real table.
_ID = sa.Uuid()
org_closure = sa.table("org_closure", sa.column("ancestor_id", _ID),
                       sa.column("descendant_id", _ID))
partner_closure = sa.table("partner_closure", sa.column("ancestor_id", _ID),
                           sa.column("descendant_id", _ID))
territory_closure = sa.table("territory_closure", sa.column("ancestor_id", _ID),
                             sa.column("descendant_id", _ID))
user_territory = sa.table("user_territory", sa.column("user_id", _ID),
                          sa.column("territory_id", _ID))
org_unit = sa.table("org_unit", sa.column("id", _ID), sa.column("territory_id", _ID))


@dataclass(frozen=True)
class Caller:
    """What stage 3 resolves, once per request, from the rows get_db already reads.

    `scopes` is module -> scope from the caller's role_permission view rows. A
    module absent from it means no permission, and the predicate for it is
    `false`: the service never issues an unscoped read (rule 2).
    """

    user_id: str
    org_unit_id: str | None
    partner_id: str | None
    scopes: dict[str, str] = field(default_factory=dict)
    # modules where the caller holds `delete`, which is what lets them read a
    # soft-deleted row ({t}_res_deleted)
    deletes: frozenset[str] = frozenset()


def scope_predicate(spec: ScopeSpec, caller: Caller,
                    table: TableClause | Any) -> ColumnElement[bool]:
    """The rows this caller may reach in `spec.table`, as a clause on `table`.

    Mirrors `policy_sql.branch_predicate` branch for branch, then the restrictive
    soft-delete policy. The two are compared by the parity suite; a divergence
    here is a bug in one of them, not a feature.
    """
    return _soft_delete(spec, caller, table, _scope_clause(spec, caller, table))


def _soft_delete(spec: ScopeSpec, caller: Caller, table: TableClause | Any,
                 clause: ColumnElement[bool]) -> ColumnElement[bool]:
    """`{t}_res_deleted`: a soft-deleted row is visible only with the module's
    delete permission. The predicate had no such clause and was more permissive
    than the policy (code review F-5)."""
    if not spec.soft_delete or spec.module in caller.deletes:
        return clause
    return sa.and_(clause, table.c[spec.soft_delete].is_(None))


def _scope_clause(spec: ScopeSpec, caller: Caller,
                  table: TableClause | Any) -> ColumnElement[bool]:
    scope = caller.scopes.get(spec.module)
    if scope is None or not spec.has_branch(scope):
        return self_row(spec, caller, table)
    if scope == "global":
        return sa.true()
    column = spec.branch_column(scope)
    assert column is not None  # has_branch() above; the type checker cannot see it
    col = table.c[column]
    if scope == "own":
        return col == caller.user_id
    if scope == "org_subtree":
        # A caller whose branch anchor is missing still reads their own row,
        # as the policy's self branch does (code review F-11).
        if caller.org_unit_id is None:
            return self_row(spec, caller, table)
        subtree = sa.select(org_closure.c.descendant_id).where(
            org_closure.c.ancestor_id == caller.org_unit_id)
        if spec.org_subtree_via:
            # at, under or above the offices' territories (FS-020), as the policy
            offices = sa.select(org_unit.c.territory_id).where(org_unit.c.id.in_(subtree))
            return sa.or_(
                col.in_(sa.select(territory_closure.c.descendant_id).where(
                    territory_closure.c.ancestor_id.in_(offices))),
                col.in_(sa.select(territory_closure.c.ancestor_id).where(
                    territory_closure.c.descendant_id.in_(offices))))
        return col.in_(subtree)
    if scope == "territory":
        return col.in_(
            sa.select(territory_closure.c.descendant_id)
            .select_from(territory_closure.join(
                user_territory, user_territory.c.territory_id == territory_closure.c.ancestor_id))
            .where(user_territory.c.user_id == caller.user_id))
    if scope == "partner_subtree":
        if caller.partner_id is None:
            return self_row(spec, caller, table)
        return col.in_(sa.select(partner_closure.c.descendant_id).where(
            partner_closure.c.ancestor_id == caller.partner_id))
    raise ValueError(scope)


def self_row(spec: ScopeSpec, caller: Caller, table: TableClause | Any) -> ColumnElement[bool]:
    """The one row a caller may always read: their own. Mirrors the self clause in
    the restrictive policy. False when the spec declares none."""
    if not spec.self_column:
        return sa.false()
    ref = caller.user_id if spec.self_ref == "user" else caller.partner_id
    if ref is None:
        return sa.false()
    return table.c[spec.self_column] == ref


def write_predicate(spec: ScopeSpec, caller: Caller,
                    table: TableClause | Any) -> ColumnElement[bool]:
    """The rows this caller may write, mirroring the policy's WITH CHECK: the read
    predicate, or, for a self-keyed subtree, the row's same-table parent being in
    the subtree."""
    read = scope_predicate(spec, caller, table)
    parent = spec.self_parent()
    if (caller.scopes.get(spec.module) == "partner_subtree" and spec.partner_subtree == "id"
            and parent and caller.partner_id is not None):
        subtree = sa.select(partner_closure.c.descendant_id).where(
            partner_closure.c.ancestor_id == caller.partner_id)
        return sa.or_(read, table.c[parent].in_(subtree))
    return read


def can_reparent(spec: ScopeSpec, caller: Caller) -> bool:
    """Stage 4 on UPDATE: may this caller change a same-table parent at all?

    A subtree caller keyed on the row's own id may not. Moving its own row, or a
    descendant, moves a whole subtree out of its ancestor's reach, and the
    ancestor never sees it happen. Mirrors authz_reparent_guard() in migration
    005 (code review F-1). Callers on other branches may, and then
    parent_lookup() decides whether the new parent is one they can see.
    """
    if spec.self_parent() is None:
        return True
    return not (caller.scopes.get(spec.module) == "partner_subtree"
                and spec.partner_subtree == "id")


def parent_lookup(spec: ScopeSpec, column: str, value: Any) -> sa.Select[Any]:
    """Stage 4: the statement that decides whether `value` is a parent this caller
    may attach to. It reads the parent table under the caller's own policies, so
    the answer is the policy's answer; the service adds the field name and the 422.

    Returns a SELECT of the parent id; zero rows means refuse.
    """
    parent = spec.parents[column]
    t = sa.table(parent, sa.column("id", _ID))
    return sa.select(t.c.id).where(t.c.id == value)
