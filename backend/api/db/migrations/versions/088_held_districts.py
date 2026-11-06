"""088: a person's assigned districts count toward their area (FS-086).

The partners rule read a staff member's area from their offices' territories
only. An admin already sets a person's districts on the user form
(`user_territory`), and on prod several Field Officers hold two or three. Each
copy of the rule that names the offices' territories now also takes the caller's
assigned districts, never a state (rule 7). The office text is swapped for the
area text in the latest source of each body, as 028 and 087 do:

| Source | Bodies |
|---|---|
| 028 | the `channel_partner` policies; `channel_partner_user_counts`, `minutes_visible`, `task_link_visible_as` |
| 040 | `partner_visible_to_caller` |
| 062 | `dealer_application_sel`; `dealer_application_visible` |
| 087 | `order_area_partner_ids` |

`lead_auto_owner()` takes an officer whose office's own territory, or an assigned
district, covers the lead. A tie goes to the office match. Its signature does not
change. tests/db/test_migration_088.py checks the text against the generator and
scans every stored body for a copy that was missed.

Revision ID: 088_held_districts
Revises: 087_order_distributors
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "088_held_districts"
down_revision: str | None = "087_order_distributors"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# policy_sql.OFFICE_TERRITORIES and policy_sql.AREA_TERRITORIES, pasted
OFFICE = "SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))"
AREA = (OFFICE + " UNION SELECT ut.territory_id FROM user_territory ut "
        "JOIN territory t ON t.id = ut.territory_id "
        "WHERE ut.user_id = (SELECT app_current_user_id()) AND ut.deleted_at IS NULL "
        "AND (SELECT app_current_org_unit()) IS NOT NULL "
        "AND t.deleted_at IS NULL AND t.level <> 'state'")


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_088", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"088: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _swap(text: str, old: str, new: str) -> str:
    """A read text names the offices twice (under and above), a write text once."""
    n = text.count(old)
    if n not in (1, 2):
        raise RuntimeError(f"088: {n} copies of the office text in {text[:60]!r}")
    return text.replace(old, new)


def _replaceable(stmt: str) -> str:
    return stmt.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


def _bodies() -> list[str]:
    """The latest source of every body that names the offices' territories."""
    m28, m40, m62, m87 = (_load("028_dealer_area_access"), _load("040_lead_small_gaps"),
                          _load("062_dealer_recruitment"), _load("087_order_distributors"))
    partner_policies = [s for s in m28.PARTNER_POLICIES if OFFICE in s]
    assert len(partner_policies) == 4, "088: 028's org_subtree, ins, upd and del policies"
    application_fn = next(s for s in m62.FUNCTIONS
                          if s.startswith("CREATE FUNCTION dealer_application_visible("))
    application_sel = next(st for t, st in m62.HAND_POLICIES if t == "dealer_application")
    return [*partner_policies,
            _replaceable(m28.counts_after()), _replaceable(m28.minutes_after()),
            _replaceable(m28.task_link_after()), _replaceable(m40._visible_fn()),
            application_sel, _replaceable(application_fn), _replaceable(m87.FUNCTIONS[0])]


_POLICY_DROPS = {"channel_partner_sel_org_subtree": "channel_partner",
                 "channel_partner_ins": "channel_partner", "channel_partner_upd": "channel_partner",
                 "channel_partner_del": "channel_partner",
                 "dealer_application_sel": "dealer_application"}


def _apply(old: str, new: str) -> None:
    for body in _bodies():
        if body.startswith("CREATE POLICY "):
            name = body.split()[2]
            op.execute(f"DROP POLICY IF EXISTS {name} ON {_POLICY_DROPS[name]}")
        op.execute(_swap(body, OFFICE, OFFICE) if old == new else _swap(body, old, new))


# the drift suite reads each table's hand-written policies from the latest
# migration that declares them (tests/db/migration_grants.py hand_policies)
HAND_POLICIES: list[tuple[str, str]] = [
    ("dealer_application", _swap(
        next(st for t, st in _load("062_dealer_recruitment").HAND_POLICIES
             if t == "dealer_application"), OFFICE, AREA)),
]


AUTO_OWNER = """CREATE OR REPLACE FUNCTION lead_auto_owner(p_territory_id uuid) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_owner uuid;
BEGIN
    IF NOT app_has_permission('leads', 'create') THEN
        RAISE EXCEPTION 'not permitted to create leads' USING ERRCODE = '42501';
    END IF;
    -- GAP-379: an officer whose territory covers the lead, nearest first; failing that, one
    -- whose territory lies inside the lead's (a district-only lead, walk F-6). FS-086: the
    -- office's own territory or an assigned district, never a state. Nearest first, then
    -- fewest open leads, then the office match (code review F-3).
    -- Not the office subtree: at HQ that covers everything (EC-6)
    SELECT u.id INTO v_owner
      FROM app_user u
      JOIN role r ON r.id = u.role_id
      JOIN role_permission rp ON rp.role_id = u.role_id
                             AND rp.module = 'leads' AND rp.action = 'edit'
      JOIN (SELECT u2.id AS uid, ou.territory_id AS tid, 0 AS via
              FROM app_user u2 JOIN org_unit ou ON ou.id = u2.org_unit_id
             WHERE ou.territory_id IS NOT NULL
            UNION ALL
            SELECT ut.user_id, ut.territory_id, 1
              FROM user_territory ut JOIN territory t ON t.id = ut.territory_id
             WHERE ut.deleted_at IS NULL AND t.deleted_at IS NULL AND t.level <> 'state') a
        ON a.uid = u.id
      JOIN territory_closure tc
        ON (tc.ancestor_id = a.tid AND tc.descendant_id = p_territory_id)
        OR (tc.ancestor_id = p_territory_id AND tc.descendant_id = a.tid)
     WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL
       AND r.level = 1
     ORDER BY (tc.descendant_id <> p_territory_id) ASC,
              tc.depth ASC,
              (SELECT count(*) FROM lead l
                WHERE l.owner_user_id = u.id
                  AND l.deleted_at IS NULL
                  AND l.stage NOT IN ('won', 'lost', 'merged', 'dormant')) ASC,
              a.via ASC,
              u.id ASC
     LIMIT 1
       FOR SHARE OF u;
    RETURN v_owner;
END $fn$"""


def upgrade() -> None:
    _apply(OFFICE, AREA)
    op.execute(AUTO_OWNER)
    # a re-created function is executable by PUBLIC unless revoked (028, 087)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    _apply(OFFICE, OFFICE)
    op.execute(next(s for s in _load("056_walk_fixes").FUNCTIONS
                    if "FUNCTION lead_auto_owner" in s))
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
