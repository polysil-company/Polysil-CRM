"""039: subsidy follow-ups (FS-009a).

One function, `subsidy_value_date(application, field_key)`: the date a field holds on
the latest stage entry that carries it (FS-009's rule), read under the caller's own
policies (SECURITY INVOKER), for the ageing view and the stage reports. The lookup uses
025's unique index on (entry_id, field_key). The masters
revisions need nothing new: 009 granted INSERT and UPDATE under `masters.edit`, and 011
refuses any edit but closing a row.

Revision ID: 039_subsidy_follow_ups
Revises: 038_marketing_material
"""

from __future__ import annotations

from alembic import op

revision: str = "039_subsidy_follow_ups"
down_revision: str | None = "038_marketing_material"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

FUNCTION = """CREATE FUNCTION subsidy_value_date(p_app uuid, p_key text) RETURNS date
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = public, pg_temp AS $fn$
    -- the latest entry carrying the field, even one that cleared it (code review F-3)
    SELECT v.value_date FROM subsidy_stage_value v
      JOIN subsidy_stage_entry e ON e.id = v.entry_id
     WHERE e.application_id = p_app AND v.field_key = p_key
     ORDER BY e.entered_at DESC, e.id DESC
     LIMIT 1
$fn$"""


def upgrade() -> None:
    op.execute(FUNCTION)
    op.execute(f"GRANT EXECUTE ON FUNCTION subsidy_value_date(uuid, text) TO {APP_ROLE}")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS subsidy_value_date(uuid, text)")
