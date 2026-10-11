"""056: fixes from the 10 Oct frontend walk.

- `partner_ids_by_user_name()`: the partners whose live users match a name. The
  partner picker searches by the person as well as the firm (walk F-9). A district
  manager cannot read partner users (app_user is org-scoped), so this is a definer
  function. It returns ids only, and the picker joins them to channel_partner
  under the caller's own policies, so it never widens what the caller sees.
- `lead_auto_owner()`: a lead whose territory is above every officer's (a QR lead
  with only a district) now goes to the least-loaded officer inside that territory
  (walk F-6). An officer whose own territory covers the lead still comes first.
- Lead scores are whole numbers from now on (walk R-12); stored scores are rounded
  half up to match, and the band is set again from the rounded score. A closed lead
  is never scored again, so its band must agree now (code review F-4).

Revision ID: 056_walk_fixes
Revises: 054_approval_step_stalled
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "056_walk_fixes"
down_revision: str | None = "054_approval_step_stalled"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

FUNCTIONS = [
    """CREATE FUNCTION partner_ids_by_user_name(p_like text) RETURNS SETOF uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT DISTINCT u.partner_id
      FROM app_user u
     WHERE u.user_type = 'partner_user' AND u.partner_id IS NOT NULL
       AND u.deleted_at IS NULL AND u.is_active
       AND u.full_name ILIKE p_like
$fn$""",
    """CREATE OR REPLACE FUNCTION lead_auto_owner(p_territory_id uuid) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_owner uuid;
BEGIN
    IF NOT app_has_permission('leads', 'create') THEN
        RAISE EXCEPTION 'not permitted to create leads' USING ERRCODE = '42501';
    END IF;
    -- GAP-379: an officer whose territory covers the lead, nearest first; failing that, one
    -- whose territory lies inside the lead's (a district-only lead, walk F-6)
    SELECT u.id INTO v_owner
      FROM app_user u
      JOIN role r ON r.id = u.role_id
      JOIN role_permission rp ON rp.role_id = u.role_id
                             AND rp.module = 'leads' AND rp.action = 'edit'
      JOIN org_unit ou ON ou.id = u.org_unit_id
      JOIN territory_closure tc
        ON (tc.ancestor_id = ou.territory_id AND tc.descendant_id = p_territory_id)
        OR (tc.ancestor_id = p_territory_id AND tc.descendant_id = ou.territory_id)
     WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL
       AND r.level = 1
     ORDER BY (tc.descendant_id <> p_territory_id) ASC,
              tc.depth ASC,
              (SELECT count(*) FROM lead l
                WHERE l.owner_user_id = u.id
                  AND l.deleted_at IS NULL
                  AND l.stage NOT IN ('won', 'lost', 'merged', 'dormant')) ASC,
              u.id ASC
     LIMIT 1
       FOR SHARE OF u;
    RETURN v_owner;
END $fn$""",
]

GRANTED = ["partner_ids_by_user_name(text)", "lead_auto_owner(uuid)"]

# the band from the rounded score, by the same inclusive thresholds as domain.score
ROUND_SCORES = """UPDATE lead l
   SET score = round(l.score),
       priority = CASE WHEN round(l.score) >= t.hot THEN 'hot'
                       WHEN round(l.score) >= t.warm THEN 'warm'
                       ELSE 'cold' END::lead_priority
  FROM (SELECT max(value) FILTER (WHERE key = 'threshold_hot') AS hot,
               max(value) FILTER (WHERE key = 'threshold_warm') AS warm
          FROM lead_score_rule) t
 WHERE l.score IS NOT NULL AND t.hot IS NOT NULL AND t.warm IS NOT NULL
   AND (l.score <> round(l.score)
        OR l.priority IS DISTINCT FROM (CASE WHEN round(l.score) >= t.hot THEN 'hot'
                                             WHEN round(l.score) >= t.warm THEN 'warm'
                                             ELSE 'cold' END)::lead_priority)"""


def _m007_auto_owner() -> str:
    spec = importlib.util.spec_from_file_location(
        "m007_for_056", Path(__file__).with_name("007_administration.py"))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for body in mod.REPLACED:
        if "FUNCTION lead_auto_owner" in body:
            return str(body)
    raise RuntimeError("007 no longer defines lead_auto_owner")


def upgrade() -> None:
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    op.execute(ROUND_SCORES)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS partner_ids_by_user_name(text)")
    op.execute(_m007_auto_owner())
    op.execute(f"GRANT EXECUTE ON FUNCTION lead_auto_owner(uuid) TO {APP_ROLE}")
