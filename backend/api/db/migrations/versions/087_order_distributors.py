"""087: the distributors a field officer can order through (FS-084, BE-043).

A field officer's order picker lists the partners their policies show. That misses
a distributor based in a neighbouring district that supplies dealers in the
officer's area. This adds:

1. `order_area_partner_ids()`: the active partners under the caller's area, from
   the generator's own predicates (rule 7). Staff with `partners.view` only.
2. `partner_supplies_caller_area(p)`: p is an active distributor above one of them.
3. `order_suppliers(like, limit)`: those distributors the caller does not already
   see, with display fields only (rule 5).
4. `supplier_partner_tier(p)`: the tier, for pricing (step 3 after 028's).
5. `partner_orderable(p)`: 028's `partner_on_visible_document(p)` or (2). The
   quotation and order INSERT checks and parent guards take it in place of 028's
   function, so a supplier can be saved (EC-1). Their text is 028's with that one
   name changed; a test compares it with the generator.

Revision ID: 087_order_distributors
Revises: 086_lead_owner_active
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "087_order_distributors"
down_revision: str | None = "086_lead_owner_active"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# branch_predicate(SPECS["partners"], scope, write=True), pasted. The org_subtree
# one is the "under" half only: the read rule's "above" half would make a dealer
# registered for a whole state a reason to offer its distributor to every officer
# in the state (rule 7, GAP-568). tests/db/test_migration_087.py checks the paste.
UNDER_OFFICES = "territory_id IN (SELECT tc.descendant_id FROM territory_closure tc WHERE tc.ancestor_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))"
UNDER_TERRITORIES = "territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id()))"

FUNCTIONS = [
    f"""CREATE FUNCTION order_area_partner_ids() RETURNS SETOF uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    -- staff only, and only with partners.view: global and the other scopes add
    -- nothing, a global caller already sees every distributor (plan review C-4)
    SELECT id FROM channel_partner
     WHERE (SELECT app_current_partner()) IS NULL
       AND (SELECT app_has_permission('partners', 'view'))
       AND is_active AND deleted_at IS NULL
       AND (((SELECT app_scope('partners')) = 'org_subtree' AND {UNDER_OFFICES})
         OR ((SELECT app_scope('partners')) = 'territory' AND {UNDER_TERRITORIES}))
$fn$""",
    """CREATE FUNCTION partner_supplies_caller_area(p_partner uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    -- GAP-569: a switched-off or deleted dealer links its distributor to nobody
    SELECT EXISTS (
        SELECT 1 FROM channel_partner s
          JOIN partner_closure pc ON pc.ancestor_id = s.id AND pc.depth >= 1
         WHERE s.id = p_partner AND s.partner_type = 'distributor'
           AND s.is_active AND s.deleted_at IS NULL
           AND pc.descendant_id IN (SELECT order_area_partner_ids()))
$fn$""",
    """CREATE FUNCTION order_suppliers(p_like text, p_limit int)
RETURNS TABLE (id uuid, code text, name text, territory_id uuid, territory_name text,
               territory_level text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    -- the area is computed once, then joined on partner_closure's descendant index
    -- (EC-8). Display fields only (rule 5)
    WITH area AS MATERIALIZED (SELECT order_area_partner_ids() AS pid)
    SELECT s.id, s.code::text, s.name, t.id, t.name::text, t.level::text
      FROM channel_partner s
      LEFT JOIN territory t ON t.id = s.territory_id
     WHERE s.partner_type = 'distributor' AND s.is_active AND s.deleted_at IS NULL
       AND EXISTS (SELECT 1 FROM partner_closure pc JOIN area a ON a.pid = pc.descendant_id
                    WHERE pc.ancestor_id = s.id AND pc.depth >= 1)
       AND NOT partner_visible_to_caller(s.id)
       AND (p_like IS NULL OR s.name ILIKE p_like OR s.code::text ILIKE p_like
            OR s.contact_name ILIKE p_like)
     ORDER BY s.name, s.id
     LIMIT p_limit
$fn$""",
    """CREATE FUNCTION supplier_partner_tier(p_partner uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT price_tier::text FROM channel_partner
     WHERE id = p_partner AND partner_supplies_caller_area(p_partner)
$fn$""",
    """CREATE FUNCTION partner_orderable(p_partner uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT partner_on_visible_document(p_partner) OR partner_supplies_caller_area(p_partner)
$fn$""",
]
SIGNATURES = ["order_area_partner_ids()", "partner_supplies_caller_area(uuid)",
              "order_suppliers(text, int)", "supplier_partner_tier(uuid)",
              "partner_orderable(uuid)"]


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_087", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"087: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OLD, NEW = "partner_on_visible_document(", "partner_orderable("


def _swapped(stmts: list[str], old: str, new: str) -> list[str]:
    """028's quotation and order INSERT policies and parent guards, the fallback
    renamed. Each one that names it names it exactly once."""
    out = []
    for s in stmts:
        if old in s:
            if s.count(old) != 1:
                raise RuntimeError(f"087: {old!r} more than once in {s[:60]!r}")
            s = s.replace(old, new)
        out.append(s)
    return out


def _statements(old: str, new: str) -> list[str]:
    m = _load("028_dealer_area_access")
    ins = [s for s in m.QUOTATION_POLICIES + m.ORDER_POLICIES
           if s.startswith(("CREATE POLICY quotation_ins ", "CREATE POLICY sales_order_ins "))]
    assert len(ins) == 2, "087: 028's two INSERT policies"
    drops = ["DROP POLICY IF EXISTS quotation_ins ON quotation",
             "DROP POLICY IF EXISTS sales_order_ins ON sales_order"]
    guards = (m.QUOTATION_GUARD_DROPS + m.QUOTATION_PARENT_GUARD
              + m.ORDER_GUARD_DROPS + m.ORDER_PARENT_GUARD)
    return drops + _swapped(ins, old, new) + _swapped(guards, old, new)


def upgrade() -> None:
    for stmt in FUNCTIONS:
        op.execute(stmt)
    # a new function is executable by PUBLIC unless revoked (plan review C-2)
    for sig in SIGNATURES:
        op.execute(f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    for stmt in _statements(OLD, NEW):
        op.execute(stmt)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    # 028's text again (nothing renamed), then the functions it no longer names
    for stmt in _statements(OLD, OLD):
        op.execute(stmt)
    for sig in reversed(SIGNATURES):
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
