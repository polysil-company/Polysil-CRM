"""The SQL emitter: a ScopeSpec into policies, ENABLE, and indexes.

Every helper call is wrapped in a scalar subselect, without exception. A bare
STABLE call with constant arguments is evaluated per row; the subselect is what
makes Postgres hoist it to an InitPlan (rule 8, ADR-021, ISS-056). The plan test
in the parity suite checks every call site, not that some InitPlan exists.

Permissive branches OR together and each tests the scope it serves, so exactly one
can be true for a given caller (RBAC.md 5.1). Restrictive policies AND on top:
the module permission, and soft delete. Writes get the same scope branches in
WITH CHECK, the action's own permission, and an EXISTS on every declared parent
(FS-002 5.2 fact 5).

Output is byte-stable for a given declaration. It is pasted into a migration and
reviewed by hand; the drift test compares a regeneration against pg_policies.
"""

from __future__ import annotations

from api.domain.authz import ScopeSpec

USER = "(SELECT app_current_user_id())"
ORG = "(SELECT app_current_org_unit())"
PARTNER = "(SELECT app_current_partner())"


def scope_call(module: str) -> str:
    return f"(SELECT app_scope('{module}'))"


def perm_call(module: str, action: str) -> str:
    return f"(SELECT app_has_permission('{module}', '{action}'))"


OFFICE_TERRITORIES = ("SELECT ou.territory_id FROM org_unit ou "
                      "WHERE ou.id IN (SELECT descendant_id FROM org_closure "
                      f"WHERE ancestor_id = {ORG})")


def branch_predicate(spec: ScopeSpec, scope: str, *, write: bool = False) -> str:
    """The row test for one scope branch, without the scope guard. `write` narrows
    the one branch whose read and write reach differ: org_subtree_via reads the
    rows at, under or above the caller's office territories and writes only at or
    under them (FS-020)."""
    col = spec.branch_column(scope)
    if scope == "global":
        return "true"
    assert col is not None
    if scope == "own":
        return f"{col} = {USER}"
    if scope == "org_subtree" and spec.org_subtree_via:
        under = (f"{col} IN (SELECT tc.descendant_id FROM territory_closure tc "
                 f"WHERE tc.ancestor_id IN ({OFFICE_TERRITORIES}))")
        if write:
            return under
        above = (f"{col} IN (SELECT tc.ancestor_id FROM territory_closure tc "
                 f"WHERE tc.descendant_id IN ({OFFICE_TERRITORIES}))")
        return f"({under}\n    OR {above})"
    if scope == "org_subtree":
        return f"{col} IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = {ORG})"
    if scope == "territory":
        return (f"{col} IN (SELECT tc.descendant_id FROM territory_closure tc "
                f"JOIN user_territory ut ON ut.territory_id = tc.ancestor_id "
                f"WHERE ut.user_id = {USER})")
    if scope == "partner_subtree":
        return (f"{col} IN (SELECT descendant_id FROM partner_closure "
                f"WHERE ancestor_id = {PARTNER})")
    raise ValueError(scope)


def _branches(spec: ScopeSpec, *, write: bool = False) -> list[tuple[str, str]]:
    """(scope, guarded predicate) for every branch the spec declares, plus global."""
    out = []
    for scope in (*spec.declared_scopes(), "global"):
        guard = f"{scope_call(spec.module)} = '{scope}'"
        pred = branch_predicate(spec, scope, write=write)
        out.append((scope, guard if pred == "true" else f"{guard}\n  AND {pred}"))
    return out


def _or_branches(spec: ScopeSpec, *, for_write: bool = False, write: bool = False) -> str:
    """For writes on a table whose subtree branch is keyed on its own id, the new
    row has no closure entry yet, so the branch also accepts the row's same-table
    parent being in the subtree. A dealer creates a sub-dealer under itself; a
    row cannot be attached under a parent the caller does not reach."""
    parts = []
    for scope, p in _branches(spec, write=write or for_write):
        if (for_write and scope == "partner_subtree" and spec.partner_subtree == "id"
                and spec.self_parent()):
            parent_pred = branch_predicate(spec, scope).replace(
                "id IN", f"{spec.self_parent()} IN", 1)
            guard = f"{scope_call(spec.module)} = '{scope}'"
            p = f"{guard}\n  AND (({branch_predicate(spec, scope)}) OR ({parent_pred}))"
        parts.append(f"({p})")
    return "\n  OR ".join(parts)


def _parents(spec: ScopeSpec) -> str:
    """The INSERT WITH CHECK: one check per declared parent, run under the caller's
    policies. A missing parent is the FK's error; a hidden parent is this one's.

    A parent on the SAME table cannot be an inline EXISTS: a policy on t that
    selects from t is 42P17, statically (FS-002 5.2 fact 3, and executed again
    on channel_partner.parent_id). It goes through authz_visible(), an INVOKER
    function whose SELECT runs under t's SELECT policies at runtime, which do
    not reference t again, so nothing recurses.

    This is INSERT only. On UPDATE a WITH CHECK cannot see OLD, so it cannot tell
    a changed parent from an unchanged one and re-validates a parent the row's own
    editor may not see (a partner a manager assigned), locking them out of their
    row (cross-vendor B-2, executed). A change to a parent on UPDATE is guarded by
    {t}_parent_guard() (cross-table) or authz_reparent_guard() (same-table), which
    see OLD and fire only on a change.
    """
    clauses = []
    for col, parent in spec.parents.items():
        if parent == spec.table:
            clauses.append(f"({col} IS NULL OR authz_visible('{parent}', {col}))")
        elif col in spec.parent_fallback:
            clauses.append(
                f"({col} IS NULL OR EXISTS (SELECT 1 FROM {parent} p WHERE p.id = {col})"
                f" OR {spec.parent_fallback[col]}({col}))")
        else:
            clauses.append(
                f"({col} IS NULL OR EXISTS (SELECT 1 FROM {parent} p WHERE p.id = {col}))")
    return "\n  AND ".join(clauses)


def _view_gate(spec: ScopeSpec) -> str:
    """The view-permission gate, with the self exemption folded in if declared."""
    gate = perm_call(spec.module, "view")
    if spec.self_column:
        ref = USER if spec.self_ref == "user" else PARTNER
        gate = f"{spec.self_column} = {ref} OR {gate}"
    return gate


def _deleted_gate(spec: ScopeSpec) -> str | None:
    """The soft-delete gate: a deleted row is visible only with delete permission."""
    if not spec.soft_delete:
        return None
    return f"{spec.soft_delete} IS NULL OR {perm_call(spec.module, 'delete')}"


def _cross_parents(spec: ScopeSpec) -> list[tuple[str, str]]:
    """(column, parent table) for every parent on a *different* table. A same-table
    parent keeps its own guard (authz_reparent_guard), which carries a stronger
    rule; this list is what {t}_parent_guard() covers."""
    return [(col, parent) for col, parent in spec.parents.items() if parent != spec.table]


def policies_for(spec: ScopeSpec) -> list[str]:
    t, m = spec.table, spec.module
    out: list[str] = [f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY"]

    for scope, pred in _branches(spec):
        out.append(f"CREATE POLICY {t}_sel_{scope} ON {t} FOR SELECT USING (\n  {pred}\n)")

    # The self exemption has to be a PERMISSIVE branch as well as the restrictive
    # clause below. Every scope branch is guarded on app_scope(), which is NULL for
    # a caller with no permission on the module, so without this a user with no
    # users permission could not read their own row. Executed: 0 rows.
    if spec.self_column:
        ref = USER if spec.self_ref == "user" else PARTNER
        out.append(f"CREATE POLICY {t}_sel_self ON {t} FOR SELECT USING (\n"
                   f"  {spec.self_column} = {ref}\n)")

    out.append(f"CREATE POLICY {t}_res_perm ON {t} AS RESTRICTIVE FOR SELECT USING (\n"
               f"  {_view_gate(spec)}\n)")
    deleted_gate = _deleted_gate(spec)
    if deleted_gate:
        out.append(f"CREATE POLICY {t}_res_deleted ON {t} AS RESTRICTIVE FOR SELECT USING (\n"
                   f"  {deleted_gate}\n)")

    # Writes reach less than reads on org_subtree_via (FS-020); for every other
    # spec the two are the same text, so their policies do not change.
    write_scope_or = _or_branches(spec, write=True)
    write_or = _or_branches(spec, for_write=True)
    parents = _parents(spec)
    check = write_or if not parents else f"({write_or})\n  AND {parents}"
    # UPDATE re-validates no parent (cross-vendor B-2, see _parents): a parent
    # change is caught by the guard trigger, which sees OLD and fires on a change.
    upd_check = write_or

    out.append(f"CREATE POLICY {t}_ins ON {t} FOR INSERT WITH CHECK (\n  {check}\n)")
    out.append(f"CREATE POLICY {t}_ins_perm ON {t} AS RESTRICTIVE FOR INSERT WITH CHECK (\n"
               f"  {perm_call(m, 'create')}\n)")
    out.append(f"CREATE POLICY {t}_upd ON {t} FOR UPDATE USING (\n  {write_scope_or}\n) "
               f"WITH CHECK (\n  {upd_check}\n)")
    out.append(f"CREATE POLICY {t}_upd_perm ON {t} AS RESTRICTIVE FOR UPDATE USING (\n"
               f"  {perm_call(m, 'edit')}\n)")
    out.append(f"CREATE POLICY {t}_del ON {t} FOR DELETE USING (\n  {write_scope_or}\n)")
    out.append(f"CREATE POLICY {t}_del_perm ON {t} AS RESTRICTIVE FOR DELETE USING (\n"
               f"  {perm_call(m, 'delete')}\n)")
    return out


def indexes_for(spec: ScopeSpec) -> list[str]:
    """Rule 9. Partial on the soft-delete column, since the policy reads it only
    for null-ness."""
    out = []
    for col in spec.indexed_columns():
        if col == spec.soft_delete:
            out.append(f"CREATE INDEX IF NOT EXISTS ix_{spec.table}_{col}_live "
                       f"ON {spec.table} ({col}) WHERE {col} IS NULL")
        else:
            out.append(f"CREATE INDEX IF NOT EXISTS ix_{spec.table}_{col} ON {spec.table} ({col})")
    return out


def drop_policies_for(spec: ScopeSpec) -> list[str]:
    t = spec.table
    names = [f"{t}_sel_{s}" for s, _ in _branches(spec)]
    if spec.self_column:
        names.append(f"{t}_sel_self")
    names += [f"{t}_res_perm", f"{t}_res_deleted", f"{t}_ins", f"{t}_ins_perm",
              f"{t}_upd", f"{t}_upd_perm", f"{t}_del", f"{t}_del_perm"]
    return [f"DROP POLICY IF EXISTS {n} ON {t}" for n in names]


def guard_sql(spec: ScopeSpec) -> str:
    """The boolean a SECURITY DEFINER function evaluates over the claim to answer
    'may the caller SELECT this row', built from the same pieces as the SELECT
    policies: any permissive branch true, AND every restrictive gate.

    A definer function cannot borrow RLS for this. SET role is refused inside a
    definer frame, and a plain invoker function nested in a definer one runs as the
    owner and sees every row (ISS-066, both executed). So the function evaluates the
    generated rule directly, as the owner, over the claim. It is pasted into
    migration 006 inside lead_visible(); the drift test compares the stored body to
    a regeneration, so the guard and the policies cannot drift apart.
    """
    permissive = _or_branches(spec)
    if spec.self_column:
        ref = USER if spec.self_ref == "user" else PARTNER
        permissive = f"{permissive}\n  OR ({spec.self_column} = {ref})"
    clause = f"({permissive})\n  AND ({_view_gate(spec)})"
    deleted_gate = _deleted_gate(spec)
    if deleted_gate:
        clause += f"\n  AND ({deleted_gate})"
    return clause


def parent_guard_ddl(spec: ScopeSpec) -> list[str]:
    """The function and trigger that check a cross-table parent on UPDATE, only when
    it changes to a non-null value, under the caller's policies via authz_visible().
    The INSERT WITH CHECK does the same at insert; this is the UPDATE half a policy
    cannot express because it cannot see OLD (cross-vendor B-2).

    Same-table parents are not here: they keep authz_reparent_guard(), which carries
    the stronger rule that a subtree caller may not move a row at all. INVOKER, so
    authz_visible() runs as the caller; a trigger function's EXECUTE is not checked
    when it fires, so it needs no grant.
    """
    cross = _cross_parents(spec)
    if not cross:
        return []
    t = spec.table
    checks = "\n".join(
        f"            IF NEW.{col} IS DISTINCT FROM OLD.{col} AND NEW.{col} IS NOT NULL\n"
        f"               AND NOT authz_visible('{parent}', NEW.{col})"
        + (f" AND NOT {spec.parent_fallback[col]}(NEW.{col})"
           if col in spec.parent_fallback else "")
        + " THEN\n"
        f"                RAISE EXCEPTION '{col} % is not in your scope', NEW.{col}\n"
        f"                    USING ERRCODE = '42501';\n"
        f"            END IF;"
        for col, parent in cross
    )
    cols = ", ".join(col for col, _ in cross)
    return [
        f"CREATE FUNCTION {t}_parent_guard() RETURNS trigger\n"
        f"        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$\n"
        f"        BEGIN\n{checks}\n            RETURN NEW;\n        END $fn$",
        f"CREATE TRIGGER trg_{t}_parent_guard\n"
        f"            BEFORE UPDATE OF {cols} ON {t}\n"
        f"            FOR EACH ROW EXECUTE FUNCTION {t}_parent_guard()",
    ]


def drop_parent_guard_ddl(spec: ScopeSpec) -> list[str]:
    """The reverse of parent_guard_ddl, for a downgrade or a re-apply."""
    if not _cross_parents(spec):
        return []
    t = spec.table
    return [f"DROP TRIGGER IF EXISTS trg_{t}_parent_guard ON {t}",
            f"DROP FUNCTION IF EXISTS {t}_parent_guard()"]


def has_bare_helper_call(sql: str) -> bool:
    """True if any app_* helper appears outside a scalar subselect. The check the
    plan test runs against the text before it runs EXPLAIN against the plan."""
    import re

    for match in re.finditer(r"app_(?:scope|has_permission|current_\w+)\(", sql):
        before = sql[max(0, match.start() - 8):match.start()]
        if not before.rstrip().endswith("SELECT"):
            return True
    return False
