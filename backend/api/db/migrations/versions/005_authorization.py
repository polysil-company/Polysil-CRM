"""005 authorization: the grants, and the policies over them

FS-002. Built in steps, and amended in place between them: this revision has run
nowhere but the author's database until FS-002 ships, which is the one condition
under which ISS-046 allows it. The moment it runs anywhere else, corrections are
forward-only.

Steps 1 and 3 are here; step 2 (the generator) is code, not schema. Step 1: the
grants to app_role, and the two trigger functions that have to be SECURITY
DEFINER for tree writes to work under it. Step 3: every policy, the system
principal, the deactivation cascade, the permission-invariant trigger, and the
self-elevation guard.

The policies on app_user and channel_partner are GENERATED, pasted verbatim from
`python scripts/generate_policies.py`. Do not edit them here; edit
api/authz/modules.py and regenerate. The drift test compares a regeneration
against the live pg_policies. The policies on the other fourteen tables are
hand-written below, each with the reason it is not a ScopeSpec.

Two things here that reading would not give you, both executed on 16.14:

  1. closure_maintain() ran with the caller's rights. With the closures granted
     SELECT only, a permitted node insert failed with 42501 inside the trigger.
     Found by the cross-vendor round on FS-002 rev 3 after three Claude rounds
     missed it. Both tree trigger functions are SECURITY DEFINER now; 004a fixed
     their search_path, which a definer without one must not lack.

  2. The migration RAISES if app_role is missing rather than noticing. 003 and
     004 guard their grants with a NOTICE, and 003's grants were skipped for
     two days without anyone knowing (ISS-052). A policy migration on a cluster
     without the role is one where every policy is bypassed.

Revision ID: 005_authorization
Revises: 004a_search_path
Created: during development
"""
# ruff: noqa: E501  (generated SQL is pasted verbatim; its line length is not ours to wrap)
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_authorization"
down_revision: str | None = "004a_search_path"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_role"

# FS-002 5.1, the grant table. SELECT here means "read under policy"; nothing
# bypasses RLS. No DELETE on any tree table (ISS-053): a set delete removes a
# subtree under RESTRICT and NO ACTION alike, so hard delete is an ops action.
GRANTS: dict[str, str] = {
    "app_user": "SELECT, INSERT, UPDATE",
    "user_territory": "SELECT, INSERT, UPDATE",
    "role": "SELECT, INSERT, UPDATE, DELETE",
    "role_permission": "SELECT, INSERT, UPDATE, DELETE",
    "org_unit": "SELECT, INSERT, UPDATE",
    "territory": "SELECT, INSERT, UPDATE",
    "channel_partner": "SELECT, INSERT, UPDATE",
    "org_closure": "SELECT",
    "territory_closure": "SELECT",
    "partner_closure": "SELECT",
    "session": "SELECT, INSERT, UPDATE, DELETE",
    "login_attempt": "SELECT, DELETE",
    "idempotency_record": "SELECT, INSERT, DELETE",
    "activity_event": "SELECT, INSERT",
    # login_attempt and audit_log are written by definer functions as the owner;
    # an INSERT grant here was unreachable (42501, no INSERT policy) and misleading
    # (code review F-9).
    "audit_log": "SELECT",
    "notification_outbox": "SELECT, INSERT, UPDATE",
}

# 003 revoked these from PUBLIC. Without EXECUTE, require() and every policy that
# calls one fail with 42501 - everywhere at once, and only where app_role exists.
HELPERS = (
    "app_current_user_id()",
    "app_current_org_unit()",
    "app_current_partner()",
    "app_current_role()",
    "app_has_permission(text, text)",
    "app_scope(text)",
)

# Trigger functions that write a table the caller cannot, or read one under a
# policy that could hide the row they need. audit_row() is already definer (001).
DEFINER_TRIGGERS = ("closure_maintain()", "channel_partner_type_order()")

SYSTEM_ROLE = "system"
# uuid5(NAMESPACE_DNS, "polysil.system") and "polysil.system.org". Settings.system_user_id
# carries the first; the worker sets it as its claim.
SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"
SYSTEM_ORG_ID = "a1c3b0dd-6f0c-5f0e-8c1c-1b4f2f6a9e51"

# Wrapped, every one. A bare call is evaluated per row (rule 8, ISS-056).
AUTHED = "(SELECT app_current_user_id()) IS NOT NULL"
USER = "(SELECT app_current_user_id())"
SYSTEM = "(SELECT app_is_system())"


def perm(module: str, action: str) -> str:
    return f"(SELECT app_has_permission('{module}', '{action}'))"


# Generated. See the module docstring.
GENERATED_POLICIES = """
-- users over app_user, generated from api/authz/modules.py
CREATE INDEX IF NOT EXISTS ix_app_user_id ON app_user (id);
CREATE INDEX IF NOT EXISTS ix_app_user_org_unit_id ON app_user (org_unit_id);
CREATE INDEX IF NOT EXISTS ix_app_user_partner_id ON app_user (partner_id);
CREATE INDEX IF NOT EXISTS ix_app_user_deleted_at_live ON app_user (deleted_at) WHERE deleted_at IS NULL;
ALTER TABLE app_user ENABLE ROW LEVEL SECURITY;
CREATE POLICY app_user_sel_own ON app_user FOR SELECT USING (
  (SELECT app_scope('users')) = 'own'
  AND id = (SELECT app_current_user_id())
);
CREATE POLICY app_user_sel_org_subtree ON app_user FOR SELECT USING (
  (SELECT app_scope('users')) = 'org_subtree'
  AND org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))
);
CREATE POLICY app_user_sel_partner_subtree ON app_user FOR SELECT USING (
  (SELECT app_scope('users')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))
);
CREATE POLICY app_user_sel_global ON app_user FOR SELECT USING (
  (SELECT app_scope('users')) = 'global'
);
CREATE POLICY app_user_sel_self ON app_user FOR SELECT USING (
  id = (SELECT app_current_user_id())
);
CREATE POLICY app_user_res_perm ON app_user AS RESTRICTIVE FOR SELECT USING (
  id = (SELECT app_current_user_id()) OR (SELECT app_has_permission('users', 'view'))
);
CREATE POLICY app_user_res_deleted ON app_user AS RESTRICTIVE FOR SELECT USING (
  deleted_at IS NULL OR (SELECT app_has_permission('users', 'delete'))
);
CREATE POLICY app_user_ins ON app_user FOR INSERT WITH CHECK (
  (((SELECT app_scope('users')) = 'own'
  AND id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('users')) = 'org_subtree'
  AND org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('users')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('users')) = 'global'))
  AND (org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = org_unit_id))
  AND (partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id))
);
CREATE POLICY app_user_ins_perm ON app_user AS RESTRICTIVE FOR INSERT WITH CHECK (
  (SELECT app_has_permission('users', 'create'))
);
CREATE POLICY app_user_upd ON app_user FOR UPDATE USING (
  ((SELECT app_scope('users')) = 'own'
  AND id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('users')) = 'org_subtree'
  AND org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('users')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('users')) = 'global')
) WITH CHECK (
  (((SELECT app_scope('users')) = 'own'
  AND id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('users')) = 'org_subtree'
  AND org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('users')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('users')) = 'global'))
  AND (org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = org_unit_id))
  AND (partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id))
);
CREATE POLICY app_user_upd_perm ON app_user AS RESTRICTIVE FOR UPDATE USING (
  (SELECT app_has_permission('users', 'edit'))
);
CREATE POLICY app_user_del ON app_user FOR DELETE USING (
  ((SELECT app_scope('users')) = 'own'
  AND id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('users')) = 'org_subtree'
  AND org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('users')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('users')) = 'global')
);
CREATE POLICY app_user_del_perm ON app_user AS RESTRICTIVE FOR DELETE USING (
  (SELECT app_has_permission('users', 'delete'))
);

-- partners over channel_partner, generated from api/authz/modules.py
CREATE INDEX IF NOT EXISTS ix_channel_partner_territory_id ON channel_partner (territory_id);
CREATE INDEX IF NOT EXISTS ix_channel_partner_id ON channel_partner (id);
CREATE INDEX IF NOT EXISTS ix_channel_partner_deleted_at_live ON channel_partner (deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_channel_partner_parent_id ON channel_partner (parent_id);
ALTER TABLE channel_partner ENABLE ROW LEVEL SECURITY;
CREATE POLICY channel_partner_sel_org_subtree ON channel_partner FOR SELECT USING (
  (SELECT app_scope('partners')) = 'org_subtree'
  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
);
CREATE POLICY channel_partner_sel_territory ON channel_partner FOR SELECT USING (
  (SELECT app_scope('partners')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id()))
);
CREATE POLICY channel_partner_sel_partner_subtree ON channel_partner FOR SELECT USING (
  (SELECT app_scope('partners')) = 'partner_subtree'
  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))
);
CREATE POLICY channel_partner_sel_global ON channel_partner FOR SELECT USING (
  (SELECT app_scope('partners')) = 'global'
);
CREATE POLICY channel_partner_sel_self ON channel_partner FOR SELECT USING (
  id = (SELECT app_current_partner())
);
CREATE POLICY channel_partner_res_perm ON channel_partner AS RESTRICTIVE FOR SELECT USING (
  id = (SELECT app_current_partner()) OR (SELECT app_has_permission('partners', 'view'))
);
CREATE POLICY channel_partner_res_deleted ON channel_partner AS RESTRICTIVE FOR SELECT USING (
  deleted_at IS NULL OR (SELECT app_has_permission('partners', 'delete'))
);
CREATE POLICY channel_partner_ins ON channel_partner FOR INSERT WITH CHECK (
  (((SELECT app_scope('partners')) = 'org_subtree'
  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))
  OR ((SELECT app_scope('partners')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('partners')) = 'partner_subtree'
  AND ((id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))) OR (parent_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))))
  OR ((SELECT app_scope('partners')) = 'global'))
  AND (parent_id IS NULL OR authz_visible('channel_partner', parent_id))
  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))
);
CREATE POLICY channel_partner_ins_perm ON channel_partner AS RESTRICTIVE FOR INSERT WITH CHECK (
  (SELECT app_has_permission('partners', 'create'))
);
CREATE POLICY channel_partner_upd ON channel_partner FOR UPDATE USING (
  ((SELECT app_scope('partners')) = 'org_subtree'
  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))
  OR ((SELECT app_scope('partners')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('partners')) = 'partner_subtree'
  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('partners')) = 'global')
) WITH CHECK (
  (((SELECT app_scope('partners')) = 'org_subtree'
  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))
  OR ((SELECT app_scope('partners')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('partners')) = 'partner_subtree'
  AND ((id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))) OR (parent_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))))
  OR ((SELECT app_scope('partners')) = 'global'))
  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))
);
CREATE POLICY channel_partner_upd_perm ON channel_partner AS RESTRICTIVE FOR UPDATE USING (
  (SELECT app_has_permission('partners', 'edit'))
);
CREATE POLICY channel_partner_del ON channel_partner FOR DELETE USING (
  ((SELECT app_scope('partners')) = 'org_subtree'
  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))
  OR ((SELECT app_scope('partners')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('partners')) = 'partner_subtree'
  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('partners')) = 'global')
);
CREATE POLICY channel_partner_del_perm ON channel_partner AS RESTRICTIVE FOR DELETE USING (
  (SELECT app_has_permission('partners', 'delete'))
);
"""

# Hand-written, with the reason each is not a ScopeSpec (FS-002 5.3, 5.4).
HAND_POLICIES: list[tuple[str, str]] = [
    # catalog and structure: any authenticated caller reads the whole table. Hiding
    # them hides nothing, and the helpers read role_permission.
    ("role", f"CREATE POLICY role_sel ON role FOR SELECT USING ({AUTHED})"),
    ("role", f"CREATE POLICY role_ins ON role FOR INSERT WITH CHECK ({perm('masters', 'edit')})"),
    ("role", f"CREATE POLICY role_upd ON role FOR UPDATE USING ({perm('masters', 'edit')})"),
    ("role", f"CREATE POLICY role_del ON role FOR DELETE USING ({perm('masters', 'edit')})"),
    ("role_permission", f"CREATE POLICY role_permission_sel ON role_permission FOR SELECT USING ({AUTHED})"),
    ("role_permission", f"CREATE POLICY role_permission_ins ON role_permission FOR INSERT WITH CHECK ({perm('masters', 'edit')})"),
    ("role_permission", f"CREATE POLICY role_permission_upd ON role_permission FOR UPDATE USING ({perm('masters', 'edit')})"),
    ("role_permission", f"CREATE POLICY role_permission_del ON role_permission FOR DELETE USING ({perm('masters', 'edit')})"),
    ("org_unit", f"CREATE POLICY org_unit_sel ON org_unit FOR SELECT USING ({AUTHED})"),
    ("org_unit", f"CREATE POLICY org_unit_ins ON org_unit FOR INSERT WITH CHECK ({perm('masters', 'edit')})"),
    ("org_unit", f"CREATE POLICY org_unit_upd ON org_unit FOR UPDATE USING ({perm('masters', 'edit')})"),
    ("territory", f"CREATE POLICY territory_sel ON territory FOR SELECT USING ({AUTHED})"),
    ("territory", f"CREATE POLICY territory_ins ON territory FOR INSERT WITH CHECK ({perm('masters', 'edit')})"),
    ("territory", f"CREATE POLICY territory_upd ON territory FOR UPDATE USING ({perm('masters', 'edit')})"),
    # closures: readable by anyone authenticated, written by the definer trigger only.
    ("org_closure", f"CREATE POLICY org_closure_sel ON org_closure FOR SELECT USING ({AUTHED})"),
    ("territory_closure", f"CREATE POLICY territory_closure_sel ON territory_closure FOR SELECT USING ({AUTHED})"),
    ("partner_closure", f"CREATE POLICY partner_closure_sel ON partner_closure FOR SELECT USING ({AUTHED})"),
    # user_territory: self, or users.view. Written under users.edit.
    ("user_territory", f"CREATE POLICY user_territory_sel ON user_territory FOR SELECT USING (user_id = {USER} OR {perm('users', 'view')})"),
    ("user_territory", f"CREATE POLICY user_territory_ins ON user_territory FOR INSERT WITH CHECK ({perm('users', 'edit')})"),
    ("user_territory", f"CREATE POLICY user_territory_upd ON user_territory FOR UPDATE USING ({perm('users', 'edit')})"),
    # session: self only, always, plus the principal so the purge's DELETE can see
    # the rows it deletes (cross-vendor A-3, executed). No scope branch: a manager
    # has no business reading a subordinate's session rows.
    ("session", f"CREATE POLICY session_sel ON session FOR SELECT USING (user_id = {USER} OR {SYSTEM})"),
    ("session", f"CREATE POLICY session_ins ON session FOR INSERT WITH CHECK (user_id = {USER})"),
    # Self only. A users.edit branch here without one on session_sel affected zero
    # rows (code review F-4, the A-3 shape again), and a SELECT branch would show a
    # manager every subordinate's token hashes. Forced revocation is definer-only:
    # auth_revoke_sessions().
    ("session", f"CREATE POLICY session_upd ON session FOR UPDATE USING (user_id = {USER})"),
    ("session", f"CREATE POLICY session_del ON session FOR DELETE USING ({SYSTEM})"),
    # login_attempt: the lockout ledger. Global users.view or the principal; no INSERT
    # policy at all, because the definer functions write it as the owner.
    ("login_attempt", f"CREATE POLICY login_attempt_sel ON login_attempt FOR SELECT USING (({perm('users', 'view')} AND (SELECT app_scope('users')) = 'global') OR {SYSTEM})"),
    ("login_attempt", f"CREATE POLICY login_attempt_del ON login_attempt FOR DELETE USING ({SYSTEM})"),
    # idempotency_record: replaying another user's stored response is the whole risk.
    ("idempotency_record", f"CREATE POLICY idempotency_record_sel ON idempotency_record FOR SELECT USING (user_id = {USER} OR {SYSTEM})"),
    ("idempotency_record", f"CREATE POLICY idempotency_record_ins ON idempotency_record FOR INSERT WITH CHECK (user_id = {USER})"),
    ("idempotency_record", f"CREATE POLICY idempotency_record_del ON idempotency_record FOR DELETE USING ({SYSTEM})"),
    # activity_event: reading an event is reading its entity (FS-002 5.7). The
    # EXISTS runs under the entity table's own policies. Unmapped types fall to the
    # principal only until the migration that creates their table maps them.
    ("activity_event", "CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (\n  " + "CASE entity_type\n    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)\n    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)\n    ELSE (SELECT app_is_system())\n  END" + "\n)"),
    ("activity_event", f"CREATE POLICY activity_event_ins ON activity_event FOR INSERT WITH CHECK (actor_id = {USER} OR {SYSTEM})"),
    # audit_log: global users.view only. Written by the definer trigger.
    ("audit_log", f"CREATE POLICY audit_log_sel ON audit_log FOR SELECT USING ({perm('users', 'view')} AND (SELECT app_scope('users')) = 'global')"),
    # notification_outbox: rule 6 writes it inside the request as the user; only the
    # principal reads or updates. It holds phone numbers and rendered bodies.
    ("notification_outbox", f"CREATE POLICY notification_outbox_sel ON notification_outbox FOR SELECT USING ({SYSTEM})"),
    ("notification_outbox", f"CREATE POLICY notification_outbox_ins ON notification_outbox FOR INSERT WITH CHECK ({AUTHED} OR {SYSTEM})"),
    ("notification_outbox", f"CREATE POLICY notification_outbox_upd ON notification_outbox FOR UPDATE USING ({SYSTEM})"),
]
HAND_TABLES = sorted({t for t, _ in HAND_POLICIES})
GENERATED_TABLES = ("app_user", "channel_partner")


def require_role_sql(role: str) -> str:
    """The guard, as a statement. Exposed so a test can run it against a role that
    does not exist and assert it raises, since the real role cannot be dropped."""
    return f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                RAISE EXCEPTION 'role {role} does not exist. Every policy in this '
                    'migration is bypassed without it. CREATE ROLE {role} NOLOGIN; '
                    'GRANT {role} TO <the application login>; then upgrade again. '
                    'FS-002 5.1, GAP-028.';
            END IF;
        END $$
    """


def upgrade() -> None:
    op.execute(require_role_sql(APP_ROLE))

    for fn in DEFINER_TRIGGERS:
        op.execute(f"ALTER FUNCTION {fn} SECURITY DEFINER")

    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT EXECUTE ON FUNCTION {', '.join(HELPERS)} TO {APP_ROLE}")

    # The inverse: app_role holds nothing on a table this list does not name, and
    # DELETE on no tree table. A future migration that grants more must say so
    # here, or this raises.
    tables_sql = ", ".join(f"'{t}'" for t in GRANTS)
    op.execute(
        f"""
        DO $$
        DECLARE v_extra text; v_tree text;
        BEGIN
            SELECT string_agg(c.relname, ', ') INTO v_extra
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind = 'r'
               AND c.relname NOT IN ({tables_sql}) AND c.relname <> 'alembic_version'
               AND (has_table_privilege('{APP_ROLE}', c.oid, 'SELECT')
                 OR has_table_privilege('{APP_ROLE}', c.oid, 'INSERT')
                 OR has_table_privilege('{APP_ROLE}', c.oid, 'UPDATE')
                 OR has_table_privilege('{APP_ROLE}', c.oid, 'DELETE'));
            IF v_extra IS NOT NULL THEN
                RAISE EXCEPTION '{APP_ROLE} holds privileges on tables 005 does not list: %',
                    v_extra;
            END IF;
            SELECT string_agg(t, ', ') INTO v_tree
              FROM unnest(ARRAY['org_unit', 'territory', 'channel_partner']) AS t
             WHERE has_table_privilege('{APP_ROLE}', t, 'DELETE');
            IF v_tree IS NOT NULL THEN
                RAISE EXCEPTION '{APP_ROLE} may hard-delete a tree node: %. ISS-053', v_tree;
            END IF;
        END $$
        """
    )

    _step3()


def _step3() -> None:
    """Policies, the principal, the cascade, the invariant trigger, the guard."""
    # The seventh helper. The principal's branches test the role, not a fixed id,
    # so the id can change and the policies do not.
    op.execute(
        f"""
        CREATE FUNCTION app_is_system() RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS
        $$SELECT EXISTS (SELECT 1 FROM app_user u JOIN role r ON r.id = u.role_id
                          WHERE u.id = (SELECT app_current_user_id())
                            AND r.code = '{SYSTEM_ROLE}')$$
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION app_is_system() TO {APP_ROLE}")

    # The principal: a system role with no matrix rows (its access is explicit
    # branches, asserted separately), and a staff row anchored at a System org unit
    # that this migration creates. A new user_type cannot be inserted in the same
    # transaction as the enum value (55P04); a staff row needs neither.
    op.execute(
        f"""
        INSERT INTO role (code, name, level, is_functional, is_portal)
        VALUES ('{SYSTEM_ROLE}', 'System', 5, true, false)
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO org_unit (id, name, role_level)
        VALUES ('{SYSTEM_ORG_ID}', 'System', 5)
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO app_user (id, user_type, email, full_name, role_id, org_unit_id, is_active)
        SELECT '{SYSTEM_USER_ID}', 'staff', 'system@polysil.internal', 'System',
               r.id, '{SYSTEM_ORG_ID}', true
          FROM role r WHERE r.code = '{SYSTEM_ROLE}'
        ON CONFLICT (id) DO UPDATE
           SET is_active = true, deleted_at = NULL, role_id = EXCLUDED.role_id
        """
    )

    # A same-table parent check. A policy on t cannot select from t inline (42P17,
    # FS-002 5.2 fact 3), so the generated WITH CHECK on channel_partner.parent_id
    # calls this INVOKER function instead. Its SELECT runs under the caller's
    # SELECT policies on the parent table at execution time, which is the check
    # wanted: a hidden parent is not a valid parent. plpgsql, so the body is not
    # inlined back into the policy where it would recurse again.
    op.execute(
        """
        CREATE FUNCTION authz_visible(p_table text, p_id uuid) RETURNS boolean
        LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = public AS $fn$
        DECLARE found_it boolean;
        BEGIN
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE id = $1)', p_table)
                INTO found_it USING p_id;
            RETURN found_it;
        END $fn$
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION authz_visible(text, uuid) TO {APP_ROLE}")

    # ENABLE and the policies for a table in one migration (rule 8): enabled with
    # none denies everything. channel_partner was enabled by 004 on purpose.
    for stmt in GENERATED_POLICIES.strip().split(";\n"):
        stmt = stmt.strip().rstrip(";")
        if stmt:
            op.execute(stmt)
    for table in HAND_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)

    # activity_event: the mapped entity types carry their reference. NOT VALID and
    # validated at once; every existing row is app_user, which maps to nothing.
    op.execute(
        """
        ALTER TABLE activity_event
            ADD CONSTRAINT ck_activity_event_reference CHECK ((entity_type <> 'lead' OR lead_id IS NOT NULL) AND (entity_type <> 'channel_partner' OR partner_id IS NOT NULL) AND (entity_type <> 'customer' OR customer_id IS NOT NULL)) NOT VALID
        """
    )
    op.execute("ALTER TABLE activity_event VALIDATE CONSTRAINT ck_activity_event_reference")

    # The deactivation cascade, as a trigger: no permitted UPDATE of the flags can
    # skip it (cross-vendor A-4). Directly anchored users only (GAP-042).
    op.execute(
        """
        CREATE FUNCTION authz_cascade_deactivation() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
        DECLARE
            v_col    text;
            v_going  boolean;
            v_user   uuid;
        BEGIN
            IF TG_TABLE_NAME = 'channel_partner' THEN
                v_col := 'partner_id';
                v_going := (NOT NEW.is_active AND OLD.is_active)
                        OR (NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL);
            ELSE
                v_col := 'org_unit_id';
                v_going := NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL;
            END IF;
            IF NOT v_going THEN
                RETURN NULL;
            END IF;
            -- The anchor's own state change (rule 7). Built per table: org_unit
            -- has no is_active, and a CASE over NEW.is_active is one expression
            -- that plpgsql resolves before choosing a branch (executed: an org
            -- unit could not be deactivated; cross-vendor P1). partner_id is set
            -- for a partner so ck_activity_event_reference holds.
            IF TG_TABLE_NAME = 'channel_partner' THEN
                INSERT INTO activity_event (entity_type, entity_id, kind, actor_id,
                                            partner_id, payload)
                VALUES ('channel_partner', NEW.id, 'partner.deactivated',
                        app_current_user_id(), NEW.id,
                        jsonb_build_object('is_active', NEW.is_active,
                                           'deleted', NEW.deleted_at IS NOT NULL));
            ELSE
                INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
                VALUES ('org_unit', NEW.id, 'org_unit.deactivated',
                        app_current_user_id(), jsonb_build_object('deleted', true));
            END IF;
            -- Lock order: session, then app_user. auth_claim_refresh() takes the
            -- session row first and the user row FOR SHARE second; the first
            -- version of this loop went the other way round and deadlocked
            -- against a concurrent refresh (executed, code review F-3).
            -- tests/db/test_concurrency_005.py holds the order.
            UPDATE session s SET revoked_at = now()
             WHERE s.revoked_at IS NULL
               AND s.user_id IN (SELECT u.id FROM app_user u
                                  WHERE u.is_active
                                    AND CASE v_col WHEN 'partner_id' THEN u.partner_id
                                                   ELSE u.org_unit_id END = NEW.id);
            FOR v_user IN EXECUTE format(
                'UPDATE app_user SET is_active = false, token_version = token_version + 1
                  WHERE %I = $1 AND is_active RETURNING id', v_col) USING NEW.id
            LOOP
                INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
                VALUES ('app_user', v_user, 'auth.deactivated_by_anchor',
                        app_current_user_id(),
                        jsonb_build_object('anchor', TG_TABLE_NAME, 'anchor_id', NEW.id));
            END LOOP;
            RETURN NULL;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_channel_partner_deactivation
            AFTER UPDATE OF is_active, deleted_at ON channel_partner
            FOR EACH ROW EXECUTE FUNCTION authz_cascade_deactivation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_org_unit_deactivation
            AFTER UPDATE OF deleted_at ON org_unit
            FOR EACH ROW EXECUTE FUNCTION authz_cascade_deactivation()
        """
    )

    # Parent changes on channel_partner. The generated UPDATE WITH CHECK cannot
    # see OLD, so it cannot tell a changed parent from an unchanged one; this
    # trigger can. INVOKER, so authz_visible() runs under the caller's policies.
    # A subtree caller (a partner user) may not change parent_id at all: moving
    # its own row or a descendant moves a whole subtree out of its distributor's
    # reach, and setting it NULL did exactly that (executed, code review F-1).
    # Any other caller needs to see the new parent. The owner passes: app_scope()
    # is NULL and the owner sees every row. Mirrored by predicate.can_reparent().
    op.execute(
        """
        CREATE FUNCTION authz_reparent_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $fn$
        BEGIN
            IF NEW.parent_id IS NOT DISTINCT FROM OLD.parent_id THEN
                RETURN NEW;
            END IF;
            IF (SELECT app_scope('partners')) = 'partner_subtree' THEN
                RAISE EXCEPTION 'a partner cannot move itself or a partner under it'
                    USING ERRCODE = '42501';
            END IF;
            IF NEW.parent_id IS NOT NULL
               AND NOT authz_visible('channel_partner', NEW.parent_id) THEN
                RAISE EXCEPTION 'parent % is not in your scope', NEW.parent_id
                    USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_channel_partner_reparent
            BEFORE UPDATE OF parent_id ON channel_partner
            FOR EACH ROW EXECUTE FUNCTION authz_reparent_guard()
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION authz_reparent_guard() TO {APP_ROLE}")

    # The API's entry point. INVOKER, not definer: the UPDATE it issues runs under
    # the caller's own policies, so scope is the policy's answer; it adds the actor
    # check and a clear message. A Field Officer gets 42501 (round-1 B-9).
    op.execute(
        """
        CREATE FUNCTION authz_deactivate_anchor(p_kind text, p_id uuid) RETURNS void
        LANGUAGE plpgsql SET search_path = public AS $fn$
        DECLARE v_n int;
        BEGIN
            IF app_current_user_id() IS NULL THEN
                RAISE EXCEPTION 'no caller' USING ERRCODE = '28000';
            END IF;
            IF p_kind = 'channel_partner' THEN
                IF NOT app_has_permission('partners', 'edit') THEN
                    RAISE EXCEPTION 'partners.edit required' USING ERRCODE = '42501';
                END IF;
                UPDATE channel_partner SET is_active = false WHERE id = p_id AND is_active;
            ELSIF p_kind = 'org_unit' THEN
                IF NOT app_has_permission('masters', 'edit') THEN
                    RAISE EXCEPTION 'masters.edit required' USING ERRCODE = '42501';
                END IF;
                UPDATE org_unit SET deleted_at = now() WHERE id = p_id AND deleted_at IS NULL;
            ELSE
                RAISE EXCEPTION 'unknown anchor kind %', p_kind USING ERRCODE = '22023';
            END IF;
            GET DIAGNOSTICS v_n = ROW_COUNT;
            IF v_n = 0 THEN
                RAISE EXCEPTION '% % is not in your scope, or is already inactive', p_kind, p_id
                    USING ERRCODE = '42501';
            END IF;
        END $fn$
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION authz_deactivate_anchor(text, uuid) TO {APP_ROLE}")

    # The permission invariant, at commit, on every write including DELETE. Deleting
    # a module's view row leaves mutation rows whose scope resolves to NULL, and the
    # rev-2 INSERT/UPDATE trigger let it through (cross-vendor A-6). Deferred, so one
    # transaction can replace a module's rows atomically.
    op.execute(
        """
        CREATE FUNCTION role_permission_invariant() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
        BEGIN
            PERFORM assert_role_permission_invariants();
            RETURN NULL;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_role_permission_invariant
            AFTER INSERT OR UPDATE OR DELETE ON role_permission
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION role_permission_invariant()
        """
    )

    # Self-elevation (FS-002 rev 2 EC-2): a user may not change their own role, org
    # unit or partner. In the role-family trigger, which now also fires on the two
    # anchor columns (cross-vendor non-blocking).
    op.execute("DROP TRIGGER trg_app_user_role_family ON app_user")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_user_role_family_check() RETURNS trigger
        LANGUAGE plpgsql SET search_path = public AS $fn$
        DECLARE r role%ROWTYPE;
        BEGIN
            IF TG_OP = 'UPDATE' AND NEW.id = app_current_user_id()
               AND (NEW.role_id IS DISTINCT FROM OLD.role_id
                 OR NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id
                 OR NEW.partner_id IS DISTINCT FROM OLD.partner_id) THEN
                RAISE EXCEPTION 'a user may not change their own role, org unit or partner'
                    USING ERRCODE = '42501';
            END IF;

            IF TG_OP = 'UPDATE' AND NEW.user_type IS DISTINCT FROM OLD.user_type THEN
                NEW.token_version := OLD.token_version + 1;
            END IF;

            IF NEW.user_type = 'consumer' THEN
                IF NEW.role_id IS NOT NULL THEN
                    RAISE EXCEPTION 'consumers hold no role' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;

            IF NEW.role_id IS NULL THEN
                RAISE EXCEPTION '% users must hold a role', NEW.user_type
                    USING ERRCODE = '23502';
            END IF;

            SELECT * INTO r FROM role WHERE id = NEW.role_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'role % does not exist', NEW.role_id
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.user_type = 'partner_user' AND NOT r.is_portal THEN
                RAISE EXCEPTION 'role % is not a portal role', r.code
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.user_type = 'staff' AND r.is_portal THEN
                RAISE EXCEPTION 'role % is a portal role, not a staff role', r.code
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_app_user_role_family
            BEFORE INSERT OR UPDATE OF role_id, user_type, org_unit_id, partner_id ON app_user
            FOR EACH ROW EXECUTE FUNCTION app_user_role_family_check()
        """
    )

    # pg_temp (cross-vendor P1, executed). `SET search_path = public` still
    # searches pg_temp FIRST for relations, and every role holds TEMP on the
    # database by default. As app_role: CREATE TEMP TABLE channel_partner, and an
    # unqualified read inside a definer trigger resolved to the empty temp table.
    # Two closures. TEMP is revoked from PUBLIC on the database, so app_role and
    # app_anon cannot create one (asserted). And every function that pins
    # search_path = public gets pg_temp appended, explicitly last, so a temp
    # table made by the owner (tests, scripts) cannot shadow either (ISS-063).
    dbname = op.get_bind().execute(sa.text("SELECT current_database()")).scalar_one()
    op.execute(f'REVOKE TEMP ON DATABASE "{dbname}" FROM PUBLIC')
    op.execute(
        """
        DO $$
        DECLARE f record;
        BEGIN
            FOR f IN
                SELECT p.oid::regprocedure AS sig
                  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public'
                   AND 'search_path=public' = ANY (p.proconfig)
            LOOP
                EXECUTE format('ALTER FUNCTION %s SET search_path = public, pg_temp', f.sig);
            END LOOP;
        END $$
        """
    )

    # New functions are PUBLIC-executable until this runs (ISS-040).
    op.execute(
        """
        DO $$
        DECLARE v_public int;
        BEGIN
            REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
            SELECT count(*) INTO v_public
              FROM pg_proc p
              JOIN pg_namespace n ON n.oid = p.pronamespace
              LEFT JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e'
             WHERE n.nspname = 'public' AND d.objid IS NULL
               AND has_function_privilege('public', p.oid, 'EXECUTE');
            IF v_public > 0 THEN
                RAISE EXCEPTION '% functions in public are still executable by PUBLIC', v_public;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    """Step 3, then 1, in reverse.

    Left in place on purpose: the generated indexes (harmless, and the columns
    stay policy-relevant), and the REVOKE-from-PUBLIC sweep on functions (undoing
    it would widen access below where 003 left it).
    """
    # The role-family trigger and its function go back to their 003 shape. The
    # first version recreated the trigger and kept 005's body, which left the
    # self-elevation guard half-armed (code review F-8).
    op.execute("DROP TRIGGER IF EXISTS trg_app_user_role_family ON app_user")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_user_role_family_check() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        DECLARE r role%ROWTYPE;
        BEGIN
            IF TG_OP = 'UPDATE' AND NEW.user_type IS DISTINCT FROM OLD.user_type THEN
                NEW.token_version := OLD.token_version + 1;
            END IF;

            IF NEW.user_type = 'consumer' THEN
                IF NEW.role_id IS NOT NULL THEN
                    RAISE EXCEPTION 'consumers hold no role' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;

            IF NEW.role_id IS NULL THEN
                RAISE EXCEPTION '% users must hold a role', NEW.user_type
                    USING ERRCODE = '23502';
            END IF;

            SELECT * INTO r FROM role WHERE id = NEW.role_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'role % does not exist', NEW.role_id
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.user_type = 'partner_user' AND NOT r.is_portal THEN
                RAISE EXCEPTION 'role % is not a portal role', r.code
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.user_type = 'staff' AND r.is_portal THEN
                RAISE EXCEPTION 'role % is a portal role, not a staff role', r.code
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_app_user_role_family
            BEFORE INSERT OR UPDATE OF role_id, user_type ON app_user
            FOR EACH ROW EXECUTE FUNCTION app_user_role_family_check()
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_channel_partner_reparent ON channel_partner")
    op.execute("DROP FUNCTION IF EXISTS authz_reparent_guard()")
    # pg_temp, back to the 004a state: TEMP for PUBLIC, search_path = public.
    dbname = op.get_bind().execute(sa.text("SELECT current_database()")).scalar_one()
    op.execute(f'GRANT TEMP ON DATABASE "{dbname}" TO PUBLIC')
    op.execute(
        """
        DO $$
        DECLARE f record;
        BEGIN
            FOR f IN
                SELECT p.oid::regprocedure AS sig
                  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public'
                   AND 'search_path=public, pg_temp' = ANY (p.proconfig)
            LOOP
                EXECUTE format('ALTER FUNCTION %s SET search_path = public', f.sig);
            END LOOP;
        END $$
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_role_permission_invariant ON role_permission")
    op.execute("DROP FUNCTION IF EXISTS role_permission_invariant()")
    op.execute("DROP FUNCTION IF EXISTS authz_deactivate_anchor(text, uuid)")
    op.execute("DROP TRIGGER IF EXISTS trg_org_unit_deactivation ON org_unit")
    op.execute("DROP TRIGGER IF EXISTS trg_channel_partner_deactivation ON channel_partner")
    op.execute("DROP FUNCTION IF EXISTS authz_cascade_deactivation()")
    op.execute("ALTER TABLE activity_event DROP CONSTRAINT IF EXISTS ck_activity_event_reference")
    for table in HAND_TABLES:
        op.execute(
            f"""
            DO $$
            DECLARE p record;
            BEGIN
                FOR p IN SELECT policyname FROM pg_policies WHERE tablename = '{table}' LOOP
                    EXECUTE format('DROP POLICY %I ON {table}', p.policyname);
                END LOOP;
            END $$
            """
        )
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in GENERATED_TABLES:
        op.execute(
            f"""
            DO $$
            DECLARE p record;
            BEGIN
                FOR p IN SELECT policyname FROM pg_policies WHERE tablename = '{table}' LOOP
                    EXECUTE format('DROP POLICY %I ON {table}', p.policyname);
                END LOOP;
            END $$
            """
        )
    # app_user goes back to no RLS; channel_partner stays enabled, as 004 left it.
    op.execute("ALTER TABLE app_user DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS authz_visible(text, uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_is_system()")
    # The principal rows stay: a user row is data, and 004's FK would refuse the
    # org unit's removal anyway if anything else anchored to it.

    # Step 1, in reverse.
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    for fn in DEFINER_TRIGGERS:
        op.execute(f"ALTER FUNCTION {fn} SECURITY INVOKER")
