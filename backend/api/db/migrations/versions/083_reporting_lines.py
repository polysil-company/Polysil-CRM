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

_PROLOGUE = f"""CREATE FUNCTION reporting_lines()
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
"""

_CTES = f"""
    WITH RECURSIVE staff AS (
        -- rule 1: active, non-deleted staff; never a portal role or a service account
        SELECT u.id, u.full_name, r.code::text AS role_code, r.name AS role_name, r.level,
               NOT r.is_functional AS line, u.org_unit_id,
               u.org_unit_id = '{SYSTEM_ORG_ID}'::uuid AS unplaced
          FROM app_user u JOIN role r ON r.id = u.role_id
         WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL
           AND NOT r.is_portal AND u.id NOT IN ({_NOT_PEOPLE})
    ),
    boss AS (
        -- the people who can manage anyone: line roles above the lowest level
        SELECT s.id, s.full_name, s.level, s.org_unit_id
          FROM staff s WHERE s.line AND NOT s.unplaced AND s.level > 1
    ),
    slot AS (
        -- rule 2 is the same for everyone in one office at one level, so it is worked
        -- out once per (office, level) pair, a few hundred, not once per person. Every
        -- join here is small, so even a nested-loop plan on tables with no statistics
        -- yet stays fast (CI's fresh database chose one: 4 s and 6 s at 3,000 staff)
        SELECT c.org_unit_id, c.level, c.manager_id
          FROM (SELECT p.org_unit_id, p.level, b.id AS manager_id,
                       rank() OVER (PARTITION BY p.org_unit_id, p.level
                                    ORDER BY oc.depth, b.level) AS rk
                  FROM (SELECT DISTINCT s.org_unit_id, s.level FROM staff s WHERE NOT s.unplaced) p
                  JOIN org_closure oc ON oc.descendant_id = p.org_unit_id
                  JOIN boss b ON b.org_unit_id = oc.ancestor_id AND b.level > p.level) c
         WHERE c.rk = 1
    ),
    slot_ids AS MATERIALIZED (
        -- COLLATE "C" so the order is code point order, the same as Python's sort in
        -- api/domain/org_chart.py on any server (code review F-6).
        -- MATERIALIZED: the global branch reads it once, so Postgres would inline it
        -- as the inner side of a join. With no statistics (CI) it then re-ran the
        -- whole grouping once per person: 26 s for an admin at 3,000 staff
        SELECT sl.org_unit_id, sl.level,
               array_agg(sl.manager_id ORDER BY b.full_name COLLATE "C", b.id) AS ids
          FROM slot sl JOIN boss b ON b.id = sl.manager_id
         GROUP BY sl.org_unit_id, sl.level
    )"""

# A global caller sees everyone, so its rows need no walk up or down: only self,
# unplaced and other. The walks are what cost most on a large company (code review
# of the CI run: 1.6 s each at 3,000 staff under nested loops), and a non-global
# caller's walk covers only their own line.
_GLOBAL = """
    SELECT s.id, s.full_name, s.role_code, s.role_name, s.level, s.org_unit_id, o.name::text,
           COALESCE(si.ids, '{}'::uuid[]),
           CASE WHEN s.unplaced THEN 'unplaced' WHEN s.id = v_me THEN 'self' ELSE 'other' END
      FROM staff s
      JOIN org_unit o ON o.id = s.org_unit_id
      LEFT JOIN slot_ids si ON NOT s.unplaced AND si.org_unit_id = s.org_unit_id
                           AND si.level = s.level"""

_LINE = """,
    mgr AS (
        SELECT s.id AS person_id, si.ids
          FROM staff s
          JOIN slot_ids si ON si.org_unit_id = s.org_unit_id AND si.level = s.level
         WHERE NOT s.unplaced
    ),
    edge AS (
        SELECT m.person_id, unnest(m.ids) AS manager_id FROM mgr m
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
           COALESCE(si.ids, '{}'::uuid[]),
           rel.relation
      FROM rel
      JOIN org_unit o ON o.id = rel.org_unit_id
      LEFT JOIN slot_ids si ON NOT rel.unplaced AND si.org_unit_id = rel.org_unit_id
                           AND si.level = rel.level
     WHERE rel.id = v_me OR rel.relation IN ('above', 'below', 'co_manager')"""

FUNCTION = (_PROLOGUE
            + "    IF v_global THEN\n        RETURN QUERY" + _CTES + _GLOBAL + ";\n"
            + "    ELSE\n        RETURN QUERY" + _CTES + _LINE + ";\n"
            + "    END IF;\nEND $fn$")


def upgrade() -> None:
    op.execute(FUNCTION)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {SIGNATURE}")
