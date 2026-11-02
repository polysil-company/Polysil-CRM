"""083: reporting lines for the org chart (FS-080).

One definer, `reporting_lines()`, and no table change. Every active staff member's
managers are worked out from their office and role (rule 2): walk up from the
person's office, stop at the first office holding an active line-role person above
the person's level, and take everyone there at the lowest such level.

The function returns only what the caller may see (section 5): their own row, the
chain above them, everyone below them over the manager edges, and the co-managers
of people below them. A caller holding `users.view` at global scope gets everyone,
the rest marked `other`, and staff on the System office as `unplaced`. A caller who
is not an active staff member, or is a service account, gets no rows.

Revision ID: 083_reporting_lines
Revises: 082_email_notices
"""



from __future__ import annotations

from alembic import op

revision: str = "083_reporting_lines"
down_revision: str | None = "082_email_notices"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"  # 005
INTAKE_USER_ID = "3f962ae5-f0d3-5583-91b5-5cea037139fc"  # 015
SYSTEM_ORG_ID = "a1c3b0dd-6f0c-5f0e-8c1c-1b4f2f6a9e51"   # 005
_NOT_PEOPLE = f"'{SYSTEM_USER_ID}'::uuid, '{INTAKE_USER_ID}'::uuid"

SIGNATURE = "reporting_lines()"

FUNCTION = f"""CREATE FUNCTION reporting_lines()
RETURNS TABLE (id uuid, full_name text, role_code text, role_name text, level int,
               org_unit_id uuid, org_unit_name text, manager_ids uuid[], relation text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
#variable_conflict use_column
DECLARE
    v_me uuid := app_current_user_id();
    v_global boolean;
BEGIN
    -- EC-7: nothing for anyone but an active staff member who is a person
    IF v_me IS NULL OR v_me IN ({_NOT_PEOPLE}) OR NOT EXISTS (
        SELECT 1 FROM app_user u WHERE u.id = v_me AND u.user_type = 'staff'
           AND u.is_active AND u.deleted_at IS NULL) THEN
        RETURN;
    END IF;
    -- EC-8: the view permission and global scope, once (CLAUDE.md 4.1 rule 8)
    v_global := app_has_permission('users', 'view') AND app_scope('users') = 'global';

    RETURN QUERY
    WITH RECURSIVE staff AS (
        -- rule 1: active, non-deleted staff; never a portal role or a service account
        SELECT u.id, u.full_name, r.code::text AS role_code, r.name AS role_name, r.level,
               NOT r.is_functional AS line, u.org_unit_id,
               u.org_unit_id = '{SYSTEM_ORG_ID}'::uuid AS unplaced
          FROM app_user u JOIN role r ON r.id = u.role_id
         WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL
           AND NOT r.is_portal AND u.id NOT IN ({_NOT_PEOPLE})
    ),
    edge AS (
        -- rule 2: the nearest office up the tree holding a line person above me,
        -- then the lowest such level there; ties all manage (rule 4). One set-based
        -- pass with hash joins, not a lookup per person (code review F-1).
        SELECT c.person_id, c.manager_id
          FROM (SELECT s.id AS person_id, m.id AS manager_id,
                       rank() OVER (PARTITION BY s.id ORDER BY oc.depth, m.level) AS rk
                  FROM staff s
                  JOIN org_closure oc ON oc.descendant_id = s.org_unit_id
                  JOIN staff m ON m.org_unit_id = oc.ancestor_id
                 WHERE NOT s.unplaced AND m.line AND NOT m.unplaced AND m.level > s.level) c
         WHERE c.rk = 1
    ),
    mgr AS (
        -- COLLATE "C" so the order is code point order, the same as Python's sort in
        -- api/domain/org_chart.py on any server (code review F-6)
        SELECT e.person_id,
               array_agg(e.manager_id ORDER BY m.full_name COLLATE "C", m.id) AS ids
          FROM edge e JOIN staff m ON m.id = e.manager_id
         GROUP BY e.person_id
    ),
    down AS (
        SELECT v_me AS id
        UNION
        SELECT e.person_id FROM edge e JOIN down d ON e.manager_id = d.id
    ),
    up AS (
        SELECT v_me AS id
        UNION
        SELECT e.manager_id FROM edge e JOIN up u ON e.person_id = u.id
    ),
    co AS (
        SELECT DISTINCT e.manager_id AS id
          FROM edge e JOIN down d ON d.id = e.person_id
         WHERE d.id <> v_me
    ),
    rel AS (
        SELECT s.*,
               CASE WHEN s.unplaced THEN 'unplaced'
                    WHEN s.id = v_me THEN 'self'
                    WHEN s.id IN (SELECT up.id FROM up) THEN 'above'
                    WHEN s.id IN (SELECT down.id FROM down) THEN 'below'
                    WHEN s.id IN (SELECT co.id FROM co) THEN 'co_manager'
                    ELSE 'other' END AS relation
          FROM staff s
    )
    SELECT rel.id, rel.full_name, rel.role_code, rel.role_name, rel.level,
           rel.org_unit_id, o.name::text,
           COALESCE(mgr.ids, '{{}}'::uuid[]),
           rel.relation
      FROM rel
      JOIN org_unit o ON o.id = rel.org_unit_id
      LEFT JOIN mgr ON mgr.person_id = rel.id
     WHERE v_global OR rel.id = v_me
        OR rel.relation IN ('above', 'below', 'co_manager');
END $fn$"""


def upgrade() -> None:
    op.execute(FUNCTION)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {SIGNATURE}")
