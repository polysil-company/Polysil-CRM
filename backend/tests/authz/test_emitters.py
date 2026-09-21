"""The two emitters read one declaration and must agree with it, and with rule 8.

No database. The parity suite (step 4) is what proves the SQL and the predicate
agree with each other on real rows; these prove each one says what the
declaration says.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from api.authz.modules import SPECS
from api.authz.policy_sql import (
    drop_policies_for,
    guard_sql,
    has_bare_helper_call,
    indexes_for,
    parent_guard_ddl,
    policies_for,
)
from api.authz.predicate import (
    Caller,
    can_reparent,
    parent_lookup,
    scope_predicate,
    write_predicate,
)
from api.domain.authz import SCOPES, ScopeSpec

LEADS = ScopeSpec(module="leads", table="lead", own="owner_user_id",
                  org_subtree="owner_org_unit_id", territory="territory_id",
                  partner_subtree="assigned_partner_id",
                  parents={"assigned_partner_id": "channel_partner"})


def _sql(clause: sa.ColumnElement[bool]) -> str:
    return str(clause.compile(dialect=postgresql.dialect(),
                              compile_kwargs={"literal_binds": True}))


# ── policy SQL ───────────────────────────────────────────────────────────────

def test_every_helper_call_is_wrapped_in_a_scalar_subselect() -> None:
    """Rule 8, ISS-056. The check that would have caught RBAC.md's 13 bare calls."""
    for spec in (LEADS, *SPECS.values()):
        for stmt in policies_for(spec):
            assert not has_bare_helper_call(stmt), stmt


def test_the_bare_call_detector_detects() -> None:
    assert has_bare_helper_call("USING (app_scope('leads') = 'own')")
    assert not has_bare_helper_call("USING ((SELECT app_scope('leads')) = 'own')")


def test_one_permissive_select_branch_per_declared_scope_plus_global() -> None:
    stmts = policies_for(LEADS)
    selects = [s for s in stmts if "FOR SELECT USING" in s and "RESTRICTIVE" not in s]
    assert len(selects) == len(LEADS.declared_scopes()) + 1
    for scope in SCOPES:
        assert any(f"lead_sel_{scope} " in s for s in selects), scope
    for s in selects:
        assert "(SELECT app_scope('leads')) = '" in s


def test_a_missing_branch_emits_nothing_rather_than_matching_nothing() -> None:
    spec = SPECS["partners"]
    stmts = policies_for(spec)
    assert not any("channel_partner_sel_own " in s for s in stmts)
    assert any("channel_partner_sel_territory " in s for s in stmts)


def test_restrictive_permission_and_soft_delete() -> None:
    stmts = "\n".join(policies_for(LEADS))
    assert ("lead_res_perm ON lead AS RESTRICTIVE FOR SELECT USING (\n"
            "  (SELECT app_has_permission('leads', 'view'))") in stmts
    assert "deleted_at IS NULL OR (SELECT app_has_permission('leads', 'delete'))" in stmts


def test_the_self_column_exempts_the_callers_own_row() -> None:
    stmts = "\n".join(policies_for(SPECS["users"]))
    assert ("app_user_sel_self ON app_user FOR SELECT USING (\n"
            "  id = (SELECT app_current_user_id())") in stmts
    assert ("id = (SELECT app_current_user_id()) OR "
            "(SELECT app_has_permission('users', 'view'))") in stmts
    stmts = "\n".join(policies_for(SPECS["partners"]))
    assert ("id = (SELECT app_current_partner()) OR "
            "(SELECT app_has_permission('partners', 'view'))") in stmts


def test_writes_check_scope_action_and_parents() -> None:
    stmts = {s.split(" ON ")[0].split("CREATE POLICY ")[1]: s for s in policies_for(LEADS)
             if s.startswith("CREATE POLICY")}
    ins = stmts["lead_ins"]
    assert "WITH CHECK" in ins
    assert "EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = assigned_partner_id)" in ins
    assert "(SELECT app_has_permission('leads', 'create'))" in stmts["lead_ins_perm"]
    assert "(SELECT app_has_permission('leads', 'edit'))" in stmts["lead_upd_perm"]
    assert "(SELECT app_has_permission('leads', 'delete'))" in stmts["lead_del_perm"]
    assert "USING (" in stmts["lead_upd"] and "WITH CHECK (" in stmts["lead_upd"]


def test_a_same_table_parent_goes_through_authz_visible_not_inline_exists() -> None:
    """Executed on channel_partner: the inline form is 42P17 before any row is read."""
    stmts = "\n".join(policies_for(SPECS["partners"]))
    assert "authz_visible('channel_partner', parent_id)" in stmts
    assert "EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = parent_id)" not in stmts
    assert "EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id)" in stmts


def test_a_self_keyed_subtree_admits_a_new_row_through_its_parent() -> None:
    """On INSERT the new row is not in the closure yet; the WITH CHECK also accepts
    parent_id in the subtree. The SELECT branch is unchanged."""
    stmts = {s.split(" ON ")[0].split("CREATE POLICY ")[1]: s
             for s in policies_for(SPECS["partners"]) if s.startswith("CREATE POLICY")}
    assert "parent_id IN (SELECT descendant_id FROM partner_closure" in stmts["channel_partner_ins"]
    assert "parent_id IN" not in stmts["channel_partner_sel_partner_subtree"]


def test_org_via_territory_resolves_through_org_unit() -> None:
    stmts = "\n".join(policies_for(SPECS["partners"]))
    assert ("territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN "
            "(SELECT descendant_id FROM org_closure WHERE ancestor_id = "
            "(SELECT app_current_org_unit())))") in stmts


def test_every_referenced_column_gets_an_index_and_soft_delete_is_partial() -> None:
    idx = indexes_for(LEADS)
    assert len(idx) == len(LEADS.indexed_columns())
    assert any("ix_lead_deleted_at_live ON lead (deleted_at) WHERE deleted_at IS NULL" in i
               for i in idx)


def test_output_is_byte_stable() -> None:
    assert policies_for(LEADS) == policies_for(LEADS)
    assert indexes_for(LEADS) == indexes_for(LEADS)


def test_drop_covers_every_created_policy() -> None:
    created = {s.split(" ON ")[0].split("CREATE POLICY ")[1] for s in policies_for(LEADS)
               if s.startswith("CREATE POLICY")}
    dropped = {s.split(" ON ")[0].split("DROP POLICY IF EXISTS ")[1]
               for s in drop_policies_for(LEADS)}
    assert created == dropped


# ── the predicate ────────────────────────────────────────────────────────────

# Every clause carries deleted_at: the predicate ANDs the soft-delete rule on
# (code review F-5) and a clause without the column is a KeyError, on purpose.
lead = sa.table("lead", sa.column("owner_user_id"), sa.column("owner_org_unit_id"),
                sa.column("territory_id"), sa.column("assigned_partner_id"),
                sa.column("deleted_at"))
DEL = "lead.deleted_at IS NULL"
U = "11111111-1111-1111-1111-111111111111"
ORG = "22222222-2222-2222-2222-222222222222"
P = "33333333-3333-3333-3333-333333333333"


def _caller(scope: str | None) -> Caller:
    return Caller(user_id=U, org_unit_id=ORG, partner_id=P,
                  scopes={} if scope is None else {"leads": scope})


def test_no_permission_means_no_rows_not_all_rows() -> None:
    """Rule 2. A module the caller holds no permission for is false, never true."""
    assert _sql(scope_predicate(LEADS, _caller(None), lead)) == "false"


def test_no_permission_still_reaches_the_callers_own_row() -> None:
    """The self exemption, mirrored. A user with no users permission reads their own
    profile; a partner user with no partners permission reads their own partner."""
    au = sa.table("app_user", sa.column("id"), sa.column("deleted_at"))
    s = _sql(scope_predicate(SPECS["users"], Caller(U, ORG, P), au))
    assert s == f"app_user.id = '{U}' AND app_user.deleted_at IS NULL"
    cp = sa.table("channel_partner", sa.column("id"), sa.column("territory_id"),
                  sa.column("deleted_at"))
    s = _sql(scope_predicate(SPECS["partners"], Caller(U, None, P), cp))
    assert s == f"channel_partner.id = '{P}' AND channel_partner.deleted_at IS NULL"
    assert _sql(scope_predicate(SPECS["partners"], Caller(U, None, None), cp)) == "false"


def test_each_branch_mirrors_the_policy() -> None:
    assert _sql(scope_predicate(LEADS, _caller("global"), lead)) == DEL
    assert f"lead.owner_user_id = '{U}'" in _sql(scope_predicate(LEADS, _caller("own"), lead))
    org = _sql(scope_predicate(LEADS, _caller("org_subtree"), lead))
    assert "lead.owner_org_unit_id IN (SELECT org_closure.descendant_id" in org
    assert f"org_closure.ancestor_id = '{ORG}'" in org
    terr = _sql(scope_predicate(LEADS, _caller("territory"), lead))
    assert "territory_closure JOIN user_territory" in terr
    assert f"user_territory.user_id = '{U}'" in terr
    part = _sql(scope_predicate(LEADS, _caller("partner_subtree"), lead))
    assert f"partner_closure.ancestor_id = '{P}'" in part


def test_a_scope_the_table_has_no_branch_for_is_false() -> None:
    """A partner user holding partner_subtree on users reads through partner_id;
    on a table with no partner column the same scope yields nothing."""
    no_partner = ScopeSpec(module="leads", table="lead", own="owner_user_id")
    assert _sql(scope_predicate(no_partner, _caller("partner_subtree"), lead)) == "false"


def test_a_caller_with_no_anchor_for_the_branch_gets_only_the_self_row() -> None:
    """Code review F-11: the policy's self branch still admits the caller's own
    row, so the predicate does too. A spec with no self column gets false."""
    orphan = Caller(user_id=U, org_unit_id=None, partner_id=None, scopes={"leads": "org_subtree"})
    assert _sql(scope_predicate(LEADS, orphan, lead)) == "false"
    au = sa.table("app_user", sa.column("id"), sa.column("org_unit_id"), sa.column("deleted_at"))
    staff = Caller(user_id=U, org_unit_id=None, partner_id=None, scopes={"users": "org_subtree"})
    s = _sql(scope_predicate(SPECS["users"], staff, au))
    assert f"app_user.id = '{U}'" in s and "org_closure" not in s


def test_the_predicate_hides_soft_deleted_rows_unless_the_caller_holds_delete() -> None:
    """Code review F-5: {t}_res_deleted had no mirror in the predicate."""
    au = sa.table("app_user", sa.column("id"), sa.column("org_unit_id"), sa.column("deleted_at"))
    viewer = Caller(user_id=U, org_unit_id=ORG, partner_id=None, scopes={"users": "global"})
    assert _sql(scope_predicate(SPECS["users"], viewer, au)) == "app_user.deleted_at IS NULL"
    deleter = Caller(user_id=U, org_unit_id=ORG, partner_id=None, scopes={"users": "global"},
                     deletes=frozenset({"users"}))
    assert _sql(scope_predicate(SPECS["users"], deleter, au)) == "true"


def test_a_subtree_caller_keyed_on_the_row_id_cannot_reparent() -> None:
    """Code review F-1, the service half. The policy half is authz_reparent_guard()."""
    dealer = Caller(user_id=U, org_unit_id=None, partner_id=P,
                    scopes={"partners": "partner_subtree"})
    manager = Caller(user_id=U, org_unit_id=ORG, partner_id=None,
                     scopes={"partners": "org_subtree"})
    assert can_reparent(SPECS["partners"], dealer) is False
    assert can_reparent(SPECS["partners"], manager) is True
    assert can_reparent(LEADS, dealer) is True


def test_the_update_check_revalidates_no_parent_same_or_cross_table() -> None:
    """Cross-vendor B-2: a WITH CHECK cannot see OLD, so re-validating any parent on
    UPDATE re-checks an unchanged one the row's editor may not see. The INSERT check
    keeps every parent; the UPDATE check keeps none; the guard trigger owns changes."""
    stmts = {s.split(" ON ")[0].split("CREATE POLICY ")[1]: s
             for s in policies_for(SPECS["partners"]) if s.startswith("CREATE POLICY")}
    ins = stmts["channel_partner_ins"]
    assert "authz_visible('channel_partner', parent_id)" in ins
    assert "EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id)" in ins
    assert "authz_visible" not in stmts["channel_partner_upd"]
    assert "EXISTS (SELECT 1 FROM territory" not in stmts["channel_partner_upd"]


def test_the_parent_guard_covers_cross_table_parents_only() -> None:
    """channel_partner has a same-table parent (parent_id, kept by authz_reparent_guard)
    and a cross-table one (territory_id). The generated guard covers only the cross
    one; a spec with no cross-table parent emits no guard."""
    ddl = "\n".join(parent_guard_ddl(SPECS["partners"]))
    assert "CREATE FUNCTION channel_partner_parent_guard()" in ddl
    assert "SECURITY INVOKER" in ddl
    assert "authz_visible('territory', NEW.territory_id)" in ddl
    assert "NEW.parent_id" not in ddl                      # same-table, not here
    assert "BEFORE UPDATE OF territory_id ON channel_partner" in ddl
    # LEADS has three cross-table parents and no same-table one
    leads_ddl = "\n".join(parent_guard_ddl(LEADS))
    assert "authz_visible('channel_partner', NEW.assigned_partner_id)" in leads_ddl
    # a spec with no parents at all emits nothing
    assert parent_guard_ddl(ScopeSpec(module="leads", table="lead", own="owner_user_id")) == []


def test_the_guard_is_the_select_rule_as_one_expression() -> None:
    """lead_visible() evaluates this; it must be the SELECT policies combined, and
    carry no bare helper call (rule 8)."""
    guard = guard_sql(LEADS)
    assert "(SELECT app_scope('leads')) = 'own'" in guard
    assert "(SELECT app_scope('leads')) = 'global'" in guard
    assert "(SELECT app_has_permission('leads', 'view'))" in guard
    assert "deleted_at IS NULL OR (SELECT app_has_permission('leads', 'delete'))" in guard
    assert not has_bare_helper_call(f"USING ({guard})")
    # the users guard folds in the self exemption
    users_guard = guard_sql(SPECS["users"])
    assert "id = (SELECT app_current_user_id())" in users_guard


def test_org_via_territory_in_the_predicate() -> None:
    cp = sa.table("channel_partner", sa.column("territory_id"), sa.column("id"),
                  sa.column("deleted_at"))
    c = Caller(user_id=U, org_unit_id=ORG, partner_id=None, scopes={"partners": "org_subtree"})
    s = _sql(scope_predicate(SPECS["partners"], c, cp))
    assert "channel_partner.territory_id IN (SELECT org_unit.territory_id" in s
    assert "org_unit.id IN (SELECT org_closure.descendant_id" in s


def test_write_predicate_accepts_the_parent_for_a_self_keyed_subtree() -> None:
    cp = sa.table("channel_partner", sa.column("id"), sa.column("parent_id"),
                  sa.column("territory_id"), sa.column("deleted_at"))
    c = Caller(user_id=U, org_unit_id=None, partner_id=P, scopes={"partners": "partner_subtree"})
    s = _sql(write_predicate(SPECS["partners"], c, cp))
    assert "channel_partner.id IN (SELECT partner_closure.descendant_id" in s
    assert "channel_partner.parent_id IN (SELECT partner_closure.descendant_id" in s
    # reads do not get the parent clause
    assert "parent_id" not in _sql(scope_predicate(SPECS["partners"], c, cp))


def test_the_parent_lookup_reads_the_parent_table_under_policy() -> None:
    s = _sql(parent_lookup(LEADS, "assigned_partner_id", P))
    assert s.startswith("SELECT channel_partner.id")
    assert f"channel_partner.id = '{P}'" in s
