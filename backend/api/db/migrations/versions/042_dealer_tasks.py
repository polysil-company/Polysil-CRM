"""042: tasks for dealers (FS-037), behind the `tasks_for_dealers` setting.

- Portal roles gain `tasks` view and edit at own scope (RBAC.md §6.3); the rows go in
  here for staging and in the seed for a fresh database. The tasks ScopeSpec already
  has an own branch on `assigned_to`, so no policy changes.
- `authz_user_assignable` gains a tasks-only arm for an active user of an active,
  visible partner, when the setting is on; patched from its live text, as 041 does.
- `task_partner_assignees()`: the picker's dealer users, a definer because a manager
  cannot read partner users' rows.
- `task_partner_guard()`: a partner user may only complete its own task (ADR-034 as
  amended); the service refuses first, the database agrees.

Revision ID: 042_dealer_tasks
Revises: 041_settings_amend_reopen
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "042_dealer_tasks"
down_revision: str | None = "041_settings_amend_reopen"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
PORTAL_ROLES = ("distributor", "dealer", "sub_dealer")

GRANTS: dict[str, str] = {}
HAND_POLICIES: list[tuple[str, str]] = []

PERMISSIONS = f"""INSERT INTO role_permission (role_id, module, action, scope)
SELECT r.id, 'tasks', CAST(a.action AS permission_action), CAST('own' AS permission_scope)
  FROM role r CROSS JOIN (VALUES ('view'), ('edit')) AS a(action)
 WHERE r.code IN {PORTAL_ROLES!r}
ON CONFLICT (role_id, module, action) DO NOTHING"""

SETTING = """INSERT INTO app_setting (key, kind, value, allowed, description) VALUES
('tasks_for_dealers', 'choice', '"off"', '["off", "on"]',
 'Managers may assign tasks to the users of dealers they can see; the dealer completes them.')"""

FUNCTIONS = [
    """CREATE FUNCTION task_partner_assignees()
RETURNS TABLE (id uuid, full_name text, partner_id uuid, partner_name text, partner_type text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF app_setting_text('tasks_for_dealers') <> 'on' OR NOT app_has_permission('tasks', 'edit')
       OR app_scope('tasks') NOT IN ('global', 'org_subtree') THEN
        RETURN;
    END IF;
    RETURN QUERY
    SELECT u.id, u.full_name, cp.id, cp.name, cp.partner_type::text
      FROM app_user u JOIN channel_partner cp ON cp.id = u.partner_id
     WHERE u.user_type = 'partner_user' AND u.is_active AND u.deleted_at IS NULL
       AND cp.is_active AND cp.deleted_at IS NULL AND partner_visible_to_caller(cp.id)
     ORDER BY cp.name, u.full_name;
END $fn$""",

    """CREATE FUNCTION task_partner_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
DECLARE v_keep text[] := ARRAY['status', 'outcome', 'gift_shown', 'completed_at', 'completed_by',
                               'updated_at', 'updated_by'];
BEGIN
    IF app_current_partner() IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT (OLD.status = 'open' AND NEW.status IN ('open', 'done'))
       OR (to_jsonb(NEW) - v_keep) IS DISTINCT FROM (to_jsonb(OLD) - v_keep) THEN
        RAISE EXCEPTION 'a dealer only completes its own task' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END $fn$""",
]

GRANTED = ["task_partner_assignees()"]

_ASSIGNABLE_OLD = """    RETURN FOUND;
END"""
_ASSIGNABLE_NEW = """    IF FOUND THEN
        RETURN true;
    END IF;
    -- FS-037: a dealer's user, for tasks only, behind the setting (ADR-034 as amended)
    IF p_module = 'tasks' AND v_scope IN ('global', 'org_subtree')
       AND app_setting_text('tasks_for_dealers') = 'on' THEN
        PERFORM 1 FROM app_user u JOIN channel_partner cp ON cp.id = u.partner_id
         WHERE u.id = p_user_id AND u.user_type = 'partner_user' AND u.is_active
           AND u.deleted_at IS NULL AND cp.is_active AND cp.deleted_at IS NULL
           AND partner_visible_to_caller(cp.id)
         FOR SHARE OF u;
        RETURN FOUND;
    END IF;
    RETURN false;
END"""


def _live(name: str) -> str:
    defs = op.get_bind().execute(text(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = :n"), {"n": name}).scalars().all()
    if len(defs) != 1:
        raise RuntimeError(f"042: expected one function {name}, found {len(defs)}")
    return str(defs[0])


def _swap(name: str, old: str, new: str) -> None:
    body = _live(name)
    if body.count(old) != 1:
        raise RuntimeError(f"042: {name}: anchor found {body.count(old)} times, expected 1")
    op.execute(body.replace(old, new))


def upgrade() -> None:
    op.execute(SETTING)
    op.execute(PERMISSIONS)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute("CREATE TRIGGER trg_task_partner_guard BEFORE UPDATE ON task "
               "FOR EACH ROW EXECUTE FUNCTION task_partner_guard()")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    _swap("authz_user_assignable", _ASSIGNABLE_OLD, _ASSIGNABLE_NEW)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    _swap("authz_user_assignable", _ASSIGNABLE_NEW, _ASSIGNABLE_OLD)
    op.execute("DROP TRIGGER IF EXISTS trg_task_partner_guard ON task")
    op.execute("DROP FUNCTION IF EXISTS task_partner_guard()")
    op.execute("DROP FUNCTION IF EXISTS task_partner_assignees()")
    op.execute(f"DELETE FROM role_permission WHERE module = 'tasks' AND role_id IN "
               f"(SELECT id FROM role WHERE code IN {PORTAL_ROLES!r})")
    op.execute("DELETE FROM app_setting WHERE key = 'tasks_for_dealers'")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
