"""035: monthly sales targets per person (FS-025).

- `sales_target`: append-only; the current value is the latest row per (person,
  month, metric), by `effective_from` then `id` (two PUTs in one instant).
- RLS hand-written on `app_scope('targets')`. An insert needs `targets.create`, and
  either global scope or a person who is in the caller's subtree, is not the
  caller, and holds a lower role level (review B-1: the subtree has self rows, so a
  subtree test alone admits the caller and every peer at their office).
- A trigger on `app_user.org_unit_id` re-stamps the current and later months, so a
  transferred person's targets follow them (review B-2), as tasks do (018).
- The `targets` permission rows from RBAC.md §6.1.

Revision ID: 035_targets
Revises: 034_reports
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "035_targets"
down_revision: str | None = "034_reports"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

TABLES = [
    """CREATE TABLE sales_target (
    id bigserial PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES app_user(id),
    org_unit_id uuid REFERENCES org_unit(id),
    month date NOT NULL CHECK (month = date_trunc('month', month)::date),
    metric text NOT NULL CHECK (metric IN ('order_value', 'orders', 'leads_won', 'visits')),
    value numeric(14,2) NOT NULL CHECK (value >= 0),
    effective_from timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES app_user(id),
    CONSTRAINT ck_sales_target_whole CHECK (metric = 'order_value' OR value = round(value))
)""",
    "CREATE INDEX ix_sales_target_latest ON sales_target (user_id, month, metric, effective_from DESC, id DESC)",
    "CREATE INDEX ix_sales_target_org_unit ON sales_target (org_unit_id)",
    "CREATE INDEX ix_sales_target_created_by ON sales_target (created_by)",
    "ALTER TABLE sales_target ENABLE ROW LEVEL SECURITY",
    # no audit_row: it keys rows by a uuid id, and this table is append-only, so its
    # rows are the history; each change also writes target.set
]

# tests/db/migration_grants.py reads these two, as it does every migration's
GRANTS: dict[str, str] = {"sales_target": "SELECT, INSERT"}

_ME = "(SELECT app_current_user_id())"
_SCOPE = "(SELECT app_scope('targets'))"
_SUBTREE = "(SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))"
_MY_LEVEL = f"(SELECT r.level FROM app_user me JOIN role r ON r.id = me.role_id WHERE me.id = {_ME})"

HAND_POLICIES: list[tuple[str, str]] = [
    ("sales_target", f"""CREATE POLICY sales_target_sel ON sales_target FOR SELECT USING (
  ({_SCOPE} = 'own' AND user_id = {_ME})
  OR ({_SCOPE} = 'org_subtree' AND org_unit_id IN {_SUBTREE})
  OR ({_SCOPE} = 'global')
)"""),
    ("sales_target", "CREATE POLICY sales_target_res_perm ON sales_target AS RESTRICTIVE FOR SELECT USING (\n  (SELECT app_has_permission('targets', 'view'))\n)"),
    ("sales_target", f"""CREATE POLICY sales_target_ins ON sales_target FOR INSERT WITH CHECK (
  created_by = {_ME}
  AND (({_SCOPE} = 'global')
    OR ({_SCOPE} = 'org_subtree' AND user_id <> {_ME} AND EXISTS (
          SELECT 1 FROM app_user u JOIN role r ON r.id = u.role_id
           WHERE u.id = user_id AND u.org_unit_id IN {_SUBTREE} AND r.level < {_MY_LEVEL})))
)"""),
    ("sales_target", "CREATE POLICY sales_target_ins_perm ON sales_target AS RESTRICTIVE FOR INSERT WITH CHECK (\n  (SELECT app_has_permission('targets', 'create'))\n)"),
]

FUNCTIONS = [
    # review B-2: this month and later follow the person; past months stay
    """CREATE FUNCTION sales_target_follow_office() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    UPDATE sales_target SET org_unit_id = NEW.org_unit_id
     WHERE user_id = NEW.id
       AND month >= date_trunc('month', (now() AT TIME ZONE 'Asia/Kolkata'))::date;
    RETURN NULL;
END $fn$""",
    "CREATE TRIGGER trg_app_user_target_office AFTER UPDATE OF org_unit_id ON app_user FOR EACH ROW "
    "WHEN (OLD.org_unit_id IS DISTINCT FROM NEW.org_unit_id) EXECUTE FUNCTION sales_target_follow_office()",
]

PERMISSIONS = [("field_officer", "own", ("view",)),
               ("district_manager", "org_subtree", ("view", "create")),
               ("state_manager", "org_subtree", ("view", "create")),
               ("regional_manager", "org_subtree", ("view", "create")),
               ("admin_sales", "global", ("view", "create")),
               ("md_ceo", "global", ("view", "create")),
               ("board", "global", ("view",))]


def _permission_seed() -> str:
    rows = ", ".join(f"('{c}', '{a}', '{s}')" for c, s, acts in PERMISSIONS for a in acts)
    return f"""INSERT INTO role_permission (role_id, module, action, scope)
SELECT r.id, 'targets', CAST(v.action AS permission_action), CAST(v.scope AS permission_scope)
  FROM (VALUES {rows}) AS v(code, action, scope) JOIN role r ON r.code = v.code
ON CONFLICT (role_id, module, action) DO NOTHING"""


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON SEQUENCE sales_target_id_seq TO {APP_ROLE}")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute(_permission_seed())
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_app_user_target_office ON app_user")
    op.execute("DROP FUNCTION IF EXISTS sales_target_follow_office()")
    op.execute("DELETE FROM role_permission WHERE module = 'targets'")
    op.execute("DELETE FROM activity_event WHERE kind = 'target.set'")
    op.execute("DROP TABLE IF EXISTS sales_target")
