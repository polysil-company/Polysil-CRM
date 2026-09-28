"""018: tasks, the planner, lead meetings and meeting minutes (FS-014).

- `meeting_type`: a lead lookup (the client's five meeting types, extensible),
  admin-edited like `lead_source`.
- `task`: a call, visit, meeting or follow-up, owned by its assignee, under the
  assignee's office; at most one link to a lead, a dealer or an order. The
  `tasks` ScopeSpec generates its policies, indexes and parent guard (pasted
  below; the drift test regenerates and compares).
- `meeting_minutes`: staff only, read through `minutes_visible()`.
- `task_visible()` and `minutes_visible()`: `lead_timeline()` filters task and
  minutes events through them, so a dealer on a lead reads neither (plan review
  B-4). `task_link_visible_as()`: rule 4, visibility as the assignee, guarded so
  it answers only for someone the caller may assign to (B-2).
- `authz_user_assignable()` and `staff_directory()` learn `tasks`, on 015's text,
  and exclude the System principal by id as well as the intake account (B-3).
- `lead_merge()` moves a merged lead's tasks and minutes to the survivor (EC-5).
- `activity_event`'s read policy gains the `task` and `meeting_minutes` arms.

Revision ID: 018_tasks_planner
Revises: 017_quotation_discount_approval
"""

# ruff: noqa: E501  (generated and embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "018_tasks_planner"
down_revision: str | None = "017_quotation_discount_approval"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"  # 005

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id)"""

ENUMS = [
    "CREATE TYPE task_type AS ENUM ('call', 'visit', 'meeting', 'followup', 'other')",
    "CREATE TYPE task_status AS ENUM ('open', 'done', 'cancelled')",
]

TABLES_SQL = [
    f"""CREATE TABLE meeting_type (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE,
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 100),
    sort_order int NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    deleted_at timestamptz,
    external_id text,
    source_system text NOT NULL DEFAULT 'crm',
    synced_at timestamptz
)""",
    f"""CREATE TABLE meeting_minutes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid REFERENCES lead(id),
    partner_id uuid REFERENCES channel_partner(id),
    task_id uuid,
    held_at timestamptz NOT NULL,
    attendees text[] NOT NULL DEFAULT '{{}}',
    notes text NOT NULL CHECK (length(notes) <= 2000),
    {AUDIT},
    CONSTRAINT ck_meeting_minutes_link CHECK ((lead_id IS NULL) <> (partner_id IS NULL)),
    CONSTRAINT ck_meeting_minutes_attendees CHECK (cardinality(attendees) <= 50)
)""",
    f"""CREATE TABLE task (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 200),
    task_type task_type NOT NULL,
    status task_status NOT NULL DEFAULT 'open',
    due_at timestamptz NOT NULL,
    assigned_to uuid NOT NULL REFERENCES app_user(id),
    assigned_by uuid NOT NULL REFERENCES app_user(id),
    owner_org_unit_id uuid NOT NULL REFERENCES org_unit(id),
    lead_id uuid REFERENCES lead(id),
    partner_id uuid REFERENCES channel_partner(id),
    sales_order_id uuid REFERENCES sales_order(id),
    meeting_type_id uuid REFERENCES meeting_type(id),
    minutes_id uuid REFERENCES meeting_minutes(id),
    notes text CHECK (notes IS NULL OR length(notes) <= 2000),
    outcome text CHECK (outcome IS NULL OR length(outcome) <= 2000),
    gift_shown boolean,
    cancel_reason text CHECK (cancel_reason IS NULL OR length(cancel_reason) <= 2000),
    completed_at timestamptz,
    completed_by uuid REFERENCES app_user(id),
    {AUDIT},
    CONSTRAINT ck_task_one_link CHECK (num_nonnulls(lead_id, partner_id, sales_order_id) <= 1),
    CONSTRAINT ck_task_meeting_type CHECK ((meeting_type_id IS NOT NULL) = (task_type = 'meeting' AND lead_id IS NOT NULL)),
    CONSTRAINT ck_task_gift CHECK (gift_shown IS NULL OR task_type = 'meeting'),
    CONSTRAINT ck_task_done CHECK ((status = 'done') = (completed_at IS NOT NULL)),
    CONSTRAINT ck_task_done_outcome CHECK (status <> 'done' OR outcome IS NOT NULL),
    CONSTRAINT ck_task_cancel_reason CHECK (status <> 'cancelled' OR cancel_reason IS NOT NULL)
)""",
    # the circular link, added once both tables exist (plan review, recommendation)
    "ALTER TABLE meeting_minutes ADD CONSTRAINT fk_meeting_minutes_task FOREIGN KEY (task_id) REFERENCES task(id)",
    "CREATE TRIGGER trg_task_updated_at BEFORE UPDATE ON task FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_meeting_type_updated_at BEFORE UPDATE ON meeting_type FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_meeting_type_audit AFTER INSERT OR UPDATE OR DELETE ON meeting_type FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

SEED = """INSERT INTO meeting_type (code, name, sort_order) VALUES
    ('by_call', 'By call', 1), ('survey_design', 'Survey & Design', 2),
    ('cd_understanding', 'C & D understanding', 3), ('won_or_wait', 'Won or wait', 4),
    ('follow_up', 'Follow-up', 5)"""

# Generated by policy_sql.policies_for(SPECS["tasks"]) and pasted.
TASK_POLICIES = [
    'ALTER TABLE task ENABLE ROW LEVEL SECURITY',
    "CREATE POLICY task_sel_own ON task FOR SELECT USING (\n  (SELECT app_scope('tasks')) = 'own'\n  AND assigned_to = (SELECT app_current_user_id())\n)",
    "CREATE POLICY task_sel_org_subtree ON task FOR SELECT USING (\n  (SELECT app_scope('tasks')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))\n)",
    "CREATE POLICY task_sel_global ON task FOR SELECT USING (\n  (SELECT app_scope('tasks')) = 'global'\n)",
    "CREATE POLICY task_res_perm ON task AS RESTRICTIVE FOR SELECT USING (\n  (SELECT app_has_permission('tasks', 'view'))\n)",
    "CREATE POLICY task_ins ON task FOR INSERT WITH CHECK (\n  (((SELECT app_scope('tasks')) = 'own'\n  AND assigned_to = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('tasks')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('tasks')) = 'global'))\n  AND (lead_id IS NULL OR EXISTS (SELECT 1 FROM lead p WHERE p.id = lead_id))\n  AND (partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id))\n  AND (sales_order_id IS NULL OR EXISTS (SELECT 1 FROM sales_order p WHERE p.id = sales_order_id))\n  AND (owner_org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = owner_org_unit_id))\n)",
    "CREATE POLICY task_ins_perm ON task AS RESTRICTIVE FOR INSERT WITH CHECK (\n  (SELECT app_has_permission('tasks', 'create'))\n)",
    "CREATE POLICY task_upd ON task FOR UPDATE USING (\n  ((SELECT app_scope('tasks')) = 'own'\n  AND assigned_to = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('tasks')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('tasks')) = 'global')\n) WITH CHECK (\n  ((SELECT app_scope('tasks')) = 'own'\n  AND assigned_to = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('tasks')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('tasks')) = 'global')\n)",
    "CREATE POLICY task_upd_perm ON task AS RESTRICTIVE FOR UPDATE USING (\n  (SELECT app_has_permission('tasks', 'edit'))\n)",
    "CREATE POLICY task_del ON task FOR DELETE USING (\n  ((SELECT app_scope('tasks')) = 'own'\n  AND assigned_to = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('tasks')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('tasks')) = 'global')\n)",
    "CREATE POLICY task_del_perm ON task AS RESTRICTIVE FOR DELETE USING (\n  (SELECT app_has_permission('tasks', 'delete'))\n)",
]

# Generated by policy_sql.indexes_for(SPECS["tasks"]).
GENERATED_INDEXES = [
    'CREATE INDEX IF NOT EXISTS ix_task_assigned_to ON task (assigned_to)',
    'CREATE INDEX IF NOT EXISTS ix_task_owner_org_unit_id ON task (owner_org_unit_id)',
    'CREATE INDEX IF NOT EXISTS ix_task_lead_id ON task (lead_id)',
    'CREATE INDEX IF NOT EXISTS ix_task_partner_id ON task (partner_id)',
    'CREATE INDEX IF NOT EXISTS ix_task_sales_order_id ON task (sales_order_id)',
]

HAND_INDEXES = [
    "CREATE INDEX ix_task_planner ON task (assigned_to, status, due_at)",
    "CREATE INDEX ix_task_done ON task (assigned_to, completed_at) WHERE status = 'done'",
    "CREATE INDEX ix_task_office_due ON task (owner_org_unit_id, due_at)",
    # people_names looks a person up by each role on a task (code review F-5)
    "CREATE INDEX ix_task_assigned_by ON task (assigned_by)",
    "CREATE INDEX ix_task_completed_by ON task (completed_by) WHERE completed_by IS NOT NULL",
    "CREATE INDEX ix_task_meeting_type ON task (meeting_type_id)",
    "CREATE INDEX ix_task_minutes ON task (minutes_id)",
    "CREATE INDEX ix_meeting_minutes_lead ON meeting_minutes (lead_id)",
    "CREATE INDEX ix_meeting_minutes_partner ON meeting_minutes (partner_id)",
    "CREATE INDEX ix_meeting_minutes_task ON meeting_minutes (task_id)",
]

# Generated by policy_sql.parent_guard_ddl(SPECS["tasks"]).
PARENT_GUARD = [
    "CREATE FUNCTION task_parent_guard() RETURNS trigger\n        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$\n        BEGIN\n            IF NEW.lead_id IS DISTINCT FROM OLD.lead_id AND NEW.lead_id IS NOT NULL\n               AND NOT authz_visible('lead', NEW.lead_id) THEN\n                RAISE EXCEPTION 'lead_id % is not in your scope', NEW.lead_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.partner_id IS DISTINCT FROM OLD.partner_id AND NEW.partner_id IS NOT NULL\n               AND NOT authz_visible('channel_partner', NEW.partner_id) THEN\n                RAISE EXCEPTION 'partner_id % is not in your scope', NEW.partner_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.sales_order_id IS DISTINCT FROM OLD.sales_order_id AND NEW.sales_order_id IS NOT NULL\n               AND NOT authz_visible('sales_order', NEW.sales_order_id) THEN\n                RAISE EXCEPTION 'sales_order_id % is not in your scope', NEW.sales_order_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.owner_org_unit_id IS DISTINCT FROM OLD.owner_org_unit_id AND NEW.owner_org_unit_id IS NOT NULL\n               AND NOT authz_visible('org_unit', NEW.owner_org_unit_id) THEN\n                RAISE EXCEPTION 'owner_org_unit_id % is not in your scope', NEW.owner_org_unit_id\n                    USING ERRCODE = '42501';\n            END IF;\n            RETURN NEW;\n        END $fn$",
    'CREATE TRIGGER trg_task_parent_guard\n            BEFORE UPDATE OF lead_id, partner_id, sales_order_id, owner_org_unit_id ON task\n            FOR EACH ROW EXECUTE FUNCTION task_parent_guard()',
]

_MINUTES_READ = """(SELECT app_current_partner()) IS NULL
  AND (SELECT app_has_permission('tasks', 'view'))
  AND ((lead_id IS NOT NULL AND EXISTS (SELECT 1 FROM lead l WHERE l.id = lead_id))
       OR (partner_id IS NOT NULL AND EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)))"""

HAND_POLICIES: list[tuple[str, str]] = [
    # a lookup, like lead_source: everyone signed in reads, masters.edit writes
    ("meeting_type", "CREATE POLICY meeting_type_sel ON meeting_type FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"),
    ("meeting_type", "CREATE POLICY meeting_type_ins ON meeting_type FOR INSERT WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"),
    ("meeting_type", "CREATE POLICY meeting_type_upd ON meeting_type FOR UPDATE USING ((SELECT app_has_permission('masters', 'edit'))) WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"),
    # staff only (EC-9): through the lead or the dealer, never a partner caller
    ("meeting_minutes", f"CREATE POLICY meeting_minutes_sel ON meeting_minutes FOR SELECT USING (\n  {_MINUTES_READ}\n)"),
    ("meeting_minutes", f"CREATE POLICY meeting_minutes_ins ON meeting_minutes FOR INSERT WITH CHECK (\n  {_MINUTES_READ}\n  AND (SELECT app_has_permission('tasks', 'create'))\n  AND created_by = (SELECT app_current_user_id())\n)"),
    # activity_event gains the task and meeting_minutes arms (api/authz/activity.py
    # ENTITY_BY_ID); supersedes 017's literal, and the drift test compares the
    # union's last-wins
    ("activity_event", "CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (\n  CASE entity_type\n    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)\n    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)\n    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)\n    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)\n    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)\n    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)\n    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order c WHERE c.id = entity_id)\n    WHEN 'lead_qr_code' THEN EXISTS (SELECT 1 FROM lead_qr_code c WHERE c.id = entity_id)\n    WHEN 'task' THEN EXISTS (SELECT 1 FROM task c WHERE c.id = entity_id)\n    WHEN 'meeting_minutes' THEN EXISTS (SELECT 1 FROM meeting_minutes c WHERE c.id = entity_id)\n    ELSE (SELECT app_is_system())\n  END\n)"),
]

GRANTS = {"task": "SELECT, INSERT, UPDATE", "meeting_minutes": "SELECT, INSERT",
          "meeting_type": "SELECT, INSERT, UPDATE"}

# policy_sql.guard_sql(SPECS["tasks"]), evaluated over the claim as the owner
_TASK_GUARD = "(((SELECT app_scope('tasks')) = 'own'\n  AND assigned_to = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('tasks')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('tasks')) = 'global'))\n  AND ((SELECT app_has_permission('tasks', 'view')))"
# policy_sql.guard_sql(SPECS["partners"])
_PARTNER_GUARD = "(((SELECT app_scope('partners')) = 'org_subtree'\n  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))\n  OR ((SELECT app_scope('partners')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('partners')) = 'partner_subtree'\n  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('partners')) = 'global')\n  OR (id = (SELECT app_current_partner())))\n  AND (id = (SELECT app_current_partner()) OR (SELECT app_has_permission('partners', 'view')))\n  AND (deleted_at IS NULL OR (SELECT app_has_permission('partners', 'delete')))"

FUNCTIONS = [
    f"""CREATE FUNCTION task_visible(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM task WHERE id = p_id AND (
{_TASK_GUARD}
    ))
$fn$""",
    f"""CREATE FUNCTION minutes_visible(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM meeting_minutes m WHERE m.id = p_id
       AND app_current_partner() IS NULL AND app_has_permission('tasks', 'view')
       AND ((m.lead_id IS NOT NULL AND lead_visible(m.lead_id))
            OR (m.partner_id IS NOT NULL AND EXISTS (
                  SELECT 1 FROM channel_partner WHERE id = m.partner_id AND (
{_PARTNER_GUARD}
                  )))))
$fn$""",
    # Rule 4 (plan review B-2): the link as the assignee sees it. The claim is
    # swapped transaction-locally and restored; an error inside restores it too.
    # Answers only for the caller or someone the caller may assign to, or it would
    # tell anyone whether any user can see any lead.
    f"""CREATE FUNCTION task_link_visible_as(p_user uuid, p_lead uuid, p_partner uuid, p_order uuid)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_prev text := current_setting('app.current_user_id', true); v_ok boolean := true;
BEGIN
    IF p_user IS DISTINCT FROM app_current_user_id() AND NOT authz_user_assignable('tasks', p_user) THEN
        RAISE EXCEPTION 'not assignable' USING ERRCODE = '42501';
    END IF;
    PERFORM set_config('app.current_user_id', p_user::text, true);
    BEGIN
        IF p_lead IS NOT NULL THEN
            v_ok := v_ok AND lead_visible(p_lead);
        END IF;
        IF p_order IS NOT NULL THEN
            v_ok := v_ok AND order_visible(p_order);
        END IF;
        IF p_partner IS NOT NULL THEN
            v_ok := v_ok AND EXISTS (SELECT 1 FROM channel_partner WHERE id = p_partner AND (
{_PARTNER_GUARD}
            ));
        END IF;
    EXCEPTION WHEN OTHERS THEN
        PERFORM set_config('app.current_user_id', COALESCE(v_prev, ''), true);
        RAISE;
    END;
    PERFORM set_config('app.current_user_id', COALESCE(v_prev, ''), true);
    RETURN v_ok;
END $fn$""",
    # Rule 9b. The admin paths count and move a person's tasks whether or not the
    # caller's own tasks scope reaches them: users.* is the permission that matters
    # here, and the person must be in the caller's users scope.
    """CREATE FUNCTION user_open_tasks(p_user uuid) RETURNS integer
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_has_permission('users', 'view') OR NOT authz_user_in_scope(p_user) THEN
        RAISE EXCEPTION 'users.view required' USING ERRCODE = '42501';
    END IF;
    RETURN (SELECT count(*)::int FROM task WHERE assigned_to = p_user AND status = 'open');
END $fn$""",
    """CREATE FUNCTION user_tasks_handover(p_from uuid, p_to uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_ou uuid; v_me uuid := app_current_user_id(); v_name text; v_n integer := 0; r record;
BEGIN
    IF NOT app_has_permission('users', 'edit') OR NOT authz_user_in_scope(p_from)
       OR NOT authz_user_in_scope(p_to) THEN
        RAISE EXCEPTION 'users.edit required' USING ERRCODE = '42501';
    END IF;
    SELECT org_unit_id INTO v_ou FROM app_user
     WHERE id = p_to AND user_type = 'staff' AND is_active AND deleted_at IS NULL;
    IF v_ou IS NULL THEN
        RAISE EXCEPTION 'receiver is not active staff with an office' USING ERRCODE = '42501';
    END IF;
    SELECT full_name INTO v_name FROM app_user WHERE id = v_me;
    FOR r IN SELECT id, lead_id FROM task WHERE assigned_to = p_from AND status = 'open'
              ORDER BY id FOR UPDATE LOOP
        UPDATE task SET assigned_to = p_to, owner_org_unit_id = v_ou, updated_by = v_me
         WHERE id = r.id;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('task', r.id, r.lead_id, 'task.reassigned', v_me,
                jsonb_build_object('actor_name', COALESCE(v_name, ''), 'assigned_to', p_to,
                                   'previous_assigned_to', p_from, 'handover', true));
        v_n := v_n + 1;
    END LOOP;
    RETURN v_n;
END $fn$""",
    # An office move takes the person's open tasks with them, whatever path moved
    # them, so the new manager sees them and the old one stops (rule 9b)
    f"""CREATE FUNCTION task_follow_office() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := COALESCE(app_current_user_id(), '{SYSTEM_USER_ID}'::uuid); v_name text; r record;
BEGIN
    IF NEW.org_unit_id IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT full_name INTO v_name FROM app_user WHERE id = v_me;
    FOR r IN UPDATE task SET owner_org_unit_id = NEW.org_unit_id
              WHERE assigned_to = NEW.id AND status = 'open'
                AND owner_org_unit_id IS DISTINCT FROM NEW.org_unit_id
          RETURNING id, lead_id LOOP
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('task', r.id, r.lead_id, 'task.rehomed', v_me,
                jsonb_build_object('actor_name', COALESCE(v_name, ''),
                                   'owner_org_unit_id', NEW.org_unit_id,
                                   'previous_org_unit_id', OLD.org_unit_id));
    END LOOP;
    RETURN NULL;
END $fn$""",
    """CREATE TRIGGER trg_app_user_task_office AFTER UPDATE OF org_unit_id ON app_user
FOR EACH ROW WHEN (OLD.org_unit_id IS DISTINCT FROM NEW.org_unit_id)
EXECUTE FUNCTION task_follow_office()""",
]

INTERNAL = ["task_visible(uuid)", "minutes_visible(uuid)", "task_follow_office()"]
GRANTED = ["task_link_visible_as(uuid, uuid, uuid, uuid)", "user_open_tasks(uuid)",
           "user_tasks_handover(uuid, uuid)"]


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_018", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"018: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"018: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


def _before() -> dict[str, str]:
    """Each function this migration replaces, as it stands before it."""
    m015, m013, m012 = _load("015_public_lead_capture"), _load("013_orders_approvals_dispatch"), _load("012_quotations")
    assignable, directory = m015._assignee_functions(patched=True)
    m017 = _load("017_quotation_discount_approval")
    return {"authz_user_assignable": assignable, "staff_directory": directory,
            "lead_timeline": m013._timeline_013(), "lead_merge": m012._replaced_006()[0],
            "people_names": m017._people_names(extended=True)}


def _after_map() -> dict[str, str]:
    """Each replaced function as this migration leaves it, by name (019 builds on it)."""
    f = _before()
    for name in ("authz_user_assignable", "staff_directory"):
        body = f[name]
        body = body.replace("IF p_module NOT IN ('leads')", "IF p_module NOT IN ('leads', 'tasks')")
        body = _replace(body, "AND u.id <> '3f962ae5-f0d3-5583-91b5-5cea037139fc'",
                        f"AND u.id <> '3f962ae5-f0d3-5583-91b5-5cea037139fc' AND u.id <> '{SYSTEM_USER_ID}'")
        f[name] = body
    f["lead_timeline"] = _replace(
        f["lead_timeline"],
        "           AND (entity_type <> 'sales_order' OR order_visible(entity_id))",
        "           AND (entity_type <> 'sales_order' OR order_visible(entity_id))\n"
        "           AND (entity_type <> 'task' OR task_visible(entity_id))\n"
        "           AND (entity_type <> 'meeting_minutes' OR minutes_visible(entity_id))")
    # the people on a task are named for whoever sees the task (FS-014; the
    # cross-vendor finding on FS-013 in another form)
    f["people_names"] = _replace(
        f["people_names"],
        "         -- who approved and who dispatched are internal to Polysil (question 15.14)",
        "         OR EXISTS (SELECT 1 FROM task t WHERE t.assigned_to = u.id AND task_visible(t.id))\n"
        "         OR EXISTS (SELECT 1 FROM task t WHERE t.assigned_by = u.id AND task_visible(t.id))\n"
        "         OR EXISTS (SELECT 1 FROM task t WHERE t.completed_by = u.id AND task_visible(t.id))\n"
        "         -- who approved and who dispatched are internal to Polysil (question 15.14)")
    merge = f["lead_merge"].rstrip()
    if not merge.endswith("END $fn$"):
        raise RuntimeError("018: 012's lead_merge() does not end where expected")
    f["lead_merge"] = merge[: -len("END $fn$")] + """    -- FS-014 EC-5: the group's tasks and minutes follow the lead; their events stay
    -- where they were written and show through the timeline's merged-into union
    UPDATE task SET lead_id = p_survivor
     WHERE lead_id IN (SELECT id FROM lead WHERE merged_into_id = p_survivor);
    UPDATE meeting_minutes SET lead_id = p_survivor
     WHERE lead_id IN (SELECT id FROM lead WHERE merged_into_id = p_survivor);
END $fn$"""
    return f


def _after() -> list[str]:
    return list(_after_map().values())


def upgrade() -> None:
    for stmt in ENUMS + TABLES_SQL + GENERATED_INDEXES + HAND_INDEXES:
        op.execute(stmt)
    op.execute(SEED)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for stmt in TASK_POLICIES:
        op.execute(stmt)
    op.execute("ALTER TABLE meeting_type ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE meeting_minutes ENABLE ROW LEVEL SECURITY")
    for table, stmt in HAND_POLICIES:
        if table != "activity_event":
            op.execute(stmt)
    for stmt in PARENT_GUARD:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for stmt in _after():
        op.execute(stmt)
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(next(s for t, s in HAND_POLICIES if t == "activity_event"))
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    # new functions are PUBLIC-executable until this runs (006, cross-vendor B-6)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    # the last activity_event literal before this one is 015's
    op.execute(next(s for t, s in _load("015_public_lead_capture").HAND_POLICIES
                    if t == "activity_event"))
    for body in _before().values():
        op.execute(body)
    op.execute("DELETE FROM activity_event WHERE entity_type IN ('task', 'meeting_minutes')")
    op.execute("DROP TRIGGER IF EXISTS trg_app_user_task_office ON app_user")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    for stmt in reversed(PARENT_GUARD):
        if stmt.lstrip().startswith("CREATE TRIGGER"):
            op.execute("DROP TRIGGER IF EXISTS trg_task_parent_guard ON task")
    op.execute("DROP FUNCTION IF EXISTS task_parent_guard()")
    op.execute("ALTER TABLE meeting_minutes DROP CONSTRAINT IF EXISTS fk_meeting_minutes_task")
    for table in ("task", "meeting_minutes", "meeting_type"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DROP TYPE IF EXISTS task_status")
    op.execute("DROP TYPE IF EXISTS task_type")
