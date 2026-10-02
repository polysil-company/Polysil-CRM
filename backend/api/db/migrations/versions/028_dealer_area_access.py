"""028: the dealers that serve a user's area, and the dealer on a document they can see.

ISS-109, found in the 2 Oct demo: a field officer could not price, quote or order a
lead that had a dealer. The partners read rule matched a dealer only when its
territory was exactly an office's territory, so a taluka office never saw its
district dealer (GAP-036). FS-020 changes two things.

1. **The area rule.** A staff read on `channel_partner` reaches the dealers at,
   under or above the territories of the caller's offices. A write (create, edit,
   delete) reaches only at or under them, so a district office cannot edit a state
   distributor. Generated from `ScopeSpec.org_subtree_via`; the partners policies
   and the three functions that paste the partners guard are re-created.
2. **The dealer on a document.** `partner_on_visible_document(p)` is true when a
   lead, quotation or order the caller can see carries the dealer.
   `document_partner_tier(p)` returns that dealer's tier, and nothing else, for
   pricing. The quotation and order INSERT checks and parent guards accept such a
   dealer (`ScopeSpec.parent_fallback`), so an officer can quote a dealer a manager
   assigned from outside the officer's area.

Forward only in practice: 027 is applied on staging. The downgrade restores the
earlier text from the migrations that wrote it.

Revision ID: 028_dealer_area_access
Revises: 027_complaint_closed_check
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "028_dealer_area_access"
down_revision: str | None = "027_complaint_closed_check"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_028", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"028: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"028: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


# ── the two new functions ────────────────────────────────────────────────────

# Mirrors partner_names() (014): the same three documents. Staff only: a partner
# caller prices and orders as itself (FS-020 rule 3). A deleted dealer is out, as
# the direct read hides it.
FUNCTIONS = [
    """CREATE FUNCTION partner_on_visible_document(p_partner uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT app_current_partner() IS NULL AND EXISTS (
        SELECT 1 FROM channel_partner cp
         WHERE cp.id = p_partner AND cp.deleted_at IS NULL
           AND (EXISTS (SELECT 1 FROM lead l WHERE l.assigned_partner_id = cp.id AND lead_visible(l.id))
             OR EXISTS (SELECT 1 FROM quotation q WHERE q.partner_id = cp.id AND quotation_visible(q.id))
             OR EXISTS (SELECT 1 FROM sales_order o WHERE o.partner_id = cp.id AND order_visible(o.id))))
$fn$""",
    """CREATE FUNCTION document_partner_tier(p_partner uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT cp.price_tier::text FROM channel_partner cp
     WHERE cp.id = p_partner AND partner_on_visible_document(p_partner)
$fn$""",
]
SIGNATURES = ["partner_on_visible_document(uuid)", "document_partner_tier(uuid)"]

# ── generated: policy_sql over api/authz/modules.py, verbatim ────────────────

# guard_sql(SPECS["partners"])
PARTNERS_GUARD = "(((SELECT app_scope('partners')) = 'org_subtree'\n  AND (territory_id IN (SELECT tc.descendant_id FROM territory_closure tc WHERE tc.ancestor_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))\n    OR territory_id IN (SELECT tc.ancestor_id FROM territory_closure tc WHERE tc.descendant_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))))\n  OR ((SELECT app_scope('partners')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('partners')) = 'partner_subtree'\n  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('partners')) = 'global')\n  OR (id = (SELECT app_current_partner())))\n  AND (id = (SELECT app_current_partner()) OR (SELECT app_has_permission('partners', 'view')))\n  AND (deleted_at IS NULL OR (SELECT app_has_permission('partners', 'delete')))"

PARTNER_POLICIES = [
    'ALTER TABLE channel_partner ENABLE ROW LEVEL SECURITY',
    "CREATE POLICY channel_partner_sel_org_subtree ON channel_partner FOR SELECT USING (\n  (SELECT app_scope('partners')) = 'org_subtree'\n  AND (territory_id IN (SELECT tc.descendant_id FROM territory_closure tc WHERE tc.ancestor_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))\n    OR territory_id IN (SELECT tc.ancestor_id FROM territory_closure tc WHERE tc.descendant_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))))\n)",
    "CREATE POLICY channel_partner_sel_territory ON channel_partner FOR SELECT USING (\n  (SELECT app_scope('partners')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id()))\n)",
    "CREATE POLICY channel_partner_sel_partner_subtree ON channel_partner FOR SELECT USING (\n  (SELECT app_scope('partners')) = 'partner_subtree'\n  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))\n)",
    "CREATE POLICY channel_partner_sel_global ON channel_partner FOR SELECT USING (\n  (SELECT app_scope('partners')) = 'global'\n)",
    'CREATE POLICY channel_partner_sel_self ON channel_partner FOR SELECT USING (\n  id = (SELECT app_current_partner())\n)',
    "CREATE POLICY channel_partner_res_perm ON channel_partner AS RESTRICTIVE FOR SELECT USING (\n  id = (SELECT app_current_partner()) OR (SELECT app_has_permission('partners', 'view'))\n)",
    "CREATE POLICY channel_partner_res_deleted ON channel_partner AS RESTRICTIVE FOR SELECT USING (\n  deleted_at IS NULL OR (SELECT app_has_permission('partners', 'delete'))\n)",
    "CREATE POLICY channel_partner_ins ON channel_partner FOR INSERT WITH CHECK (\n  (((SELECT app_scope('partners')) = 'org_subtree'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc WHERE tc.ancestor_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))))\n  OR ((SELECT app_scope('partners')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('partners')) = 'partner_subtree'\n  AND ((id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))) OR (parent_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))))\n  OR ((SELECT app_scope('partners')) = 'global'))\n  AND (parent_id IS NULL OR authz_visible('channel_partner', parent_id))\n  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))\n)",
    "CREATE POLICY channel_partner_ins_perm ON channel_partner AS RESTRICTIVE FOR INSERT WITH CHECK (\n  (SELECT app_has_permission('partners', 'create'))\n)",
    "CREATE POLICY channel_partner_upd ON channel_partner FOR UPDATE USING (\n  ((SELECT app_scope('partners')) = 'org_subtree'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc WHERE tc.ancestor_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))))\n  OR ((SELECT app_scope('partners')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('partners')) = 'partner_subtree'\n  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('partners')) = 'global')\n) WITH CHECK (\n  ((SELECT app_scope('partners')) = 'org_subtree'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc WHERE tc.ancestor_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))))\n  OR ((SELECT app_scope('partners')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('partners')) = 'partner_subtree'\n  AND ((id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))) OR (parent_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))))\n  OR ((SELECT app_scope('partners')) = 'global')\n)",
    "CREATE POLICY channel_partner_upd_perm ON channel_partner AS RESTRICTIVE FOR UPDATE USING (\n  (SELECT app_has_permission('partners', 'edit'))\n)",
    "CREATE POLICY channel_partner_del ON channel_partner FOR DELETE USING (\n  ((SELECT app_scope('partners')) = 'org_subtree'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc WHERE tc.ancestor_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))))\n  OR ((SELECT app_scope('partners')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('partners')) = 'partner_subtree'\n  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('partners')) = 'global')\n)",
    "CREATE POLICY channel_partner_del_perm ON channel_partner AS RESTRICTIVE FOR DELETE USING (\n  (SELECT app_has_permission('partners', 'delete'))\n)",
]
PARTNER_DROPS = [
    'DROP POLICY IF EXISTS channel_partner_sel_org_subtree ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_sel_territory ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_sel_partner_subtree ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_sel_global ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_sel_self ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_res_perm ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_res_deleted ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_ins ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_ins_perm ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_upd ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_upd_perm ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_del ON channel_partner',
    'DROP POLICY IF EXISTS channel_partner_del_perm ON channel_partner',
]

QUOTATION_POLICIES = [
    'ALTER TABLE quotation ENABLE ROW LEVEL SECURITY',
    "CREATE POLICY quotation_sel_own ON quotation FOR SELECT USING (\n  (SELECT app_scope('quotations')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id())\n)",
    "CREATE POLICY quotation_sel_org_subtree ON quotation FOR SELECT USING (\n  (SELECT app_scope('quotations')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))\n)",
    "CREATE POLICY quotation_sel_territory ON quotation FOR SELECT USING (\n  (SELECT app_scope('quotations')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id()))\n)",
    "CREATE POLICY quotation_sel_partner_subtree ON quotation FOR SELECT USING (\n  (SELECT app_scope('quotations')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))\n)",
    "CREATE POLICY quotation_sel_global ON quotation FOR SELECT USING (\n  (SELECT app_scope('quotations')) = 'global'\n)",
    "CREATE POLICY quotation_res_perm ON quotation AS RESTRICTIVE FOR SELECT USING (\n  (SELECT app_has_permission('quotations', 'view'))\n)",
    "CREATE POLICY quotation_res_deleted ON quotation AS RESTRICTIVE FOR SELECT USING (\n  deleted_at IS NULL OR (SELECT app_has_permission('quotations', 'delete'))\n)",
    "CREATE POLICY quotation_ins ON quotation FOR INSERT WITH CHECK (\n  (((SELECT app_scope('quotations')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('quotations')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('quotations')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('quotations')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('quotations')) = 'global'))\n  AND (lead_id IS NULL OR EXISTS (SELECT 1 FROM lead p WHERE p.id = lead_id))\n  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))\n  AND (owner_org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = owner_org_unit_id))\n  AND (partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id) OR partner_on_visible_document(partner_id))\n)",
    "CREATE POLICY quotation_ins_perm ON quotation AS RESTRICTIVE FOR INSERT WITH CHECK (\n  (SELECT app_has_permission('quotations', 'create'))\n)",
    "CREATE POLICY quotation_upd ON quotation FOR UPDATE USING (\n  ((SELECT app_scope('quotations')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('quotations')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('quotations')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('quotations')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('quotations')) = 'global')\n) WITH CHECK (\n  ((SELECT app_scope('quotations')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('quotations')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('quotations')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('quotations')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('quotations')) = 'global')\n)",
    "CREATE POLICY quotation_upd_perm ON quotation AS RESTRICTIVE FOR UPDATE USING (\n  (SELECT app_has_permission('quotations', 'edit'))\n)",
    "CREATE POLICY quotation_del ON quotation FOR DELETE USING (\n  ((SELECT app_scope('quotations')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('quotations')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('quotations')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('quotations')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('quotations')) = 'global')\n)",
    "CREATE POLICY quotation_del_perm ON quotation AS RESTRICTIVE FOR DELETE USING (\n  (SELECT app_has_permission('quotations', 'delete'))\n)",
]
QUOTATION_DROPS = [
    'DROP POLICY IF EXISTS quotation_sel_own ON quotation',
    'DROP POLICY IF EXISTS quotation_sel_org_subtree ON quotation',
    'DROP POLICY IF EXISTS quotation_sel_territory ON quotation',
    'DROP POLICY IF EXISTS quotation_sel_partner_subtree ON quotation',
    'DROP POLICY IF EXISTS quotation_sel_global ON quotation',
    'DROP POLICY IF EXISTS quotation_res_perm ON quotation',
    'DROP POLICY IF EXISTS quotation_res_deleted ON quotation',
    'DROP POLICY IF EXISTS quotation_ins ON quotation',
    'DROP POLICY IF EXISTS quotation_ins_perm ON quotation',
    'DROP POLICY IF EXISTS quotation_upd ON quotation',
    'DROP POLICY IF EXISTS quotation_upd_perm ON quotation',
    'DROP POLICY IF EXISTS quotation_del ON quotation',
    'DROP POLICY IF EXISTS quotation_del_perm ON quotation',
]
QUOTATION_PARENT_GUARD = [
    "CREATE FUNCTION quotation_parent_guard() RETURNS trigger\n        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$\n        BEGIN\n            IF NEW.lead_id IS DISTINCT FROM OLD.lead_id AND NEW.lead_id IS NOT NULL\n               AND NOT authz_visible('lead', NEW.lead_id) THEN\n                RAISE EXCEPTION 'lead_id % is not in your scope', NEW.lead_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.territory_id IS DISTINCT FROM OLD.territory_id AND NEW.territory_id IS NOT NULL\n               AND NOT authz_visible('territory', NEW.territory_id) THEN\n                RAISE EXCEPTION 'territory_id % is not in your scope', NEW.territory_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.owner_org_unit_id IS DISTINCT FROM OLD.owner_org_unit_id AND NEW.owner_org_unit_id IS NOT NULL\n               AND NOT authz_visible('org_unit', NEW.owner_org_unit_id) THEN\n                RAISE EXCEPTION 'owner_org_unit_id % is not in your scope', NEW.owner_org_unit_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.partner_id IS DISTINCT FROM OLD.partner_id AND NEW.partner_id IS NOT NULL\n               AND NOT authz_visible('channel_partner', NEW.partner_id) AND NOT partner_on_visible_document(NEW.partner_id) THEN\n                RAISE EXCEPTION 'partner_id % is not in your scope', NEW.partner_id\n                    USING ERRCODE = '42501';\n            END IF;\n            RETURN NEW;\n        END $fn$",
    'CREATE TRIGGER trg_quotation_parent_guard\n            BEFORE UPDATE OF lead_id, territory_id, owner_org_unit_id, partner_id ON quotation\n            FOR EACH ROW EXECUTE FUNCTION quotation_parent_guard()',
]
QUOTATION_GUARD_DROPS = [
    'DROP TRIGGER IF EXISTS trg_quotation_parent_guard ON quotation',
    'DROP FUNCTION IF EXISTS quotation_parent_guard()',
]

ORDER_POLICIES = [
    'ALTER TABLE sales_order ENABLE ROW LEVEL SECURITY',
    "CREATE POLICY sales_order_sel_own ON sales_order FOR SELECT USING (\n  (SELECT app_scope('sales_orders')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id())\n)",
    "CREATE POLICY sales_order_sel_org_subtree ON sales_order FOR SELECT USING (\n  (SELECT app_scope('sales_orders')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))\n)",
    "CREATE POLICY sales_order_sel_territory ON sales_order FOR SELECT USING (\n  (SELECT app_scope('sales_orders')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id()))\n)",
    "CREATE POLICY sales_order_sel_partner_subtree ON sales_order FOR SELECT USING (\n  (SELECT app_scope('sales_orders')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))\n)",
    "CREATE POLICY sales_order_sel_global ON sales_order FOR SELECT USING (\n  (SELECT app_scope('sales_orders')) = 'global'\n)",
    "CREATE POLICY sales_order_res_perm ON sales_order AS RESTRICTIVE FOR SELECT USING (\n  (SELECT app_has_permission('sales_orders', 'view'))\n)",
    "CREATE POLICY sales_order_res_deleted ON sales_order AS RESTRICTIVE FOR SELECT USING (\n  deleted_at IS NULL OR (SELECT app_has_permission('sales_orders', 'delete'))\n)",
    "CREATE POLICY sales_order_ins ON sales_order FOR INSERT WITH CHECK (\n  (((SELECT app_scope('sales_orders')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('sales_orders')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('sales_orders')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('sales_orders')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('sales_orders')) = 'global'))\n  AND (lead_id IS NULL OR EXISTS (SELECT 1 FROM lead p WHERE p.id = lead_id))\n  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))\n  AND (owner_org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = owner_org_unit_id))\n  AND (partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id) OR partner_on_visible_document(partner_id))\n)",
    "CREATE POLICY sales_order_ins_perm ON sales_order AS RESTRICTIVE FOR INSERT WITH CHECK (\n  (SELECT app_has_permission('sales_orders', 'create'))\n)",
    "CREATE POLICY sales_order_upd ON sales_order FOR UPDATE USING (\n  ((SELECT app_scope('sales_orders')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('sales_orders')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('sales_orders')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('sales_orders')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('sales_orders')) = 'global')\n) WITH CHECK (\n  ((SELECT app_scope('sales_orders')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('sales_orders')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('sales_orders')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('sales_orders')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('sales_orders')) = 'global')\n)",
    "CREATE POLICY sales_order_upd_perm ON sales_order AS RESTRICTIVE FOR UPDATE USING (\n  (SELECT app_has_permission('sales_orders', 'edit'))\n)",
    "CREATE POLICY sales_order_del ON sales_order FOR DELETE USING (\n  ((SELECT app_scope('sales_orders')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('sales_orders')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('sales_orders')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('sales_orders')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('sales_orders')) = 'global')\n)",
    "CREATE POLICY sales_order_del_perm ON sales_order AS RESTRICTIVE FOR DELETE USING (\n  (SELECT app_has_permission('sales_orders', 'delete'))\n)",
]
ORDER_DROPS = [
    'DROP POLICY IF EXISTS sales_order_sel_own ON sales_order',
    'DROP POLICY IF EXISTS sales_order_sel_org_subtree ON sales_order',
    'DROP POLICY IF EXISTS sales_order_sel_territory ON sales_order',
    'DROP POLICY IF EXISTS sales_order_sel_partner_subtree ON sales_order',
    'DROP POLICY IF EXISTS sales_order_sel_global ON sales_order',
    'DROP POLICY IF EXISTS sales_order_res_perm ON sales_order',
    'DROP POLICY IF EXISTS sales_order_res_deleted ON sales_order',
    'DROP POLICY IF EXISTS sales_order_ins ON sales_order',
    'DROP POLICY IF EXISTS sales_order_ins_perm ON sales_order',
    'DROP POLICY IF EXISTS sales_order_upd ON sales_order',
    'DROP POLICY IF EXISTS sales_order_upd_perm ON sales_order',
    'DROP POLICY IF EXISTS sales_order_del ON sales_order',
    'DROP POLICY IF EXISTS sales_order_del_perm ON sales_order',
]
ORDER_PARENT_GUARD = [
    "CREATE FUNCTION sales_order_parent_guard() RETURNS trigger\n        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$\n        BEGIN\n            IF NEW.lead_id IS DISTINCT FROM OLD.lead_id AND NEW.lead_id IS NOT NULL\n               AND NOT authz_visible('lead', NEW.lead_id) THEN\n                RAISE EXCEPTION 'lead_id % is not in your scope', NEW.lead_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.territory_id IS DISTINCT FROM OLD.territory_id AND NEW.territory_id IS NOT NULL\n               AND NOT authz_visible('territory', NEW.territory_id) THEN\n                RAISE EXCEPTION 'territory_id % is not in your scope', NEW.territory_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.owner_org_unit_id IS DISTINCT FROM OLD.owner_org_unit_id AND NEW.owner_org_unit_id IS NOT NULL\n               AND NOT authz_visible('org_unit', NEW.owner_org_unit_id) THEN\n                RAISE EXCEPTION 'owner_org_unit_id % is not in your scope', NEW.owner_org_unit_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.partner_id IS DISTINCT FROM OLD.partner_id AND NEW.partner_id IS NOT NULL\n               AND NOT authz_visible('channel_partner', NEW.partner_id) AND NOT partner_on_visible_document(NEW.partner_id) THEN\n                RAISE EXCEPTION 'partner_id % is not in your scope', NEW.partner_id\n                    USING ERRCODE = '42501';\n            END IF;\n            RETURN NEW;\n        END $fn$",
    'CREATE TRIGGER trg_sales_order_parent_guard\n            BEFORE UPDATE OF lead_id, territory_id, owner_org_unit_id, partner_id ON sales_order\n            FOR EACH ROW EXECUTE FUNCTION sales_order_parent_guard()',
]
ORDER_GUARD_DROPS = [
    'DROP TRIGGER IF EXISTS trg_sales_order_parent_guard ON sales_order',
    'DROP FUNCTION IF EXISTS sales_order_parent_guard()',
]


# ── the three functions that paste the partners guard ──────────────────────────

def _counts_before() -> str:
    m = _load("007_administration")
    return next(f for f in m.FUNCTIONS if "FUNCTION channel_partner_user_counts(" in f)


def _minutes_before() -> str:
    m = _load("018_tasks_planner")
    return next(f for f in m.FUNCTIONS if "FUNCTION minutes_visible(" in f)


def _swap_guard(stmt: str, old: str) -> str:
    stmt = _replace(stmt, old, PARTNERS_GUARD)
    return _replace(stmt, "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")


def _task_link_before() -> str:
    m = _load("018_tasks_planner")
    return next(f for f in m.FUNCTIONS if "FUNCTION task_link_visible_as(" in f)


def counts_after() -> str:
    return _swap_guard(_counts_before(), _load("007_administration").PARTNERS_GUARD)


def minutes_after() -> str:
    return _swap_guard(_minutes_before(), _load("018_tasks_planner")._PARTNER_GUARD)


def task_link_after() -> str:
    """The assignee check on a task's dealer link (code review F-1): the third body
    that pastes the partners guard."""
    return _swap_guard(_task_link_before(), _load("018_tasks_planner")._PARTNER_GUARD)


def _old_partner_policies() -> list[str]:
    """005's partner policies, with channel_partner_upd as 006 re-applied it (no
    parent check on UPDATE; code review F-4)."""
    text = _load("005_authorization").GENERATED_POLICIES
    upd = str(_load("006_leads").REAPPLY["channel_partner"]["new"])
    out = [s.strip() for s in text.split(";")
           if "CREATE POLICY channel_partner_" in s and " ON channel_partner " in s]
    return [upd if p.startswith("CREATE POLICY channel_partner_upd ") else p for p in out]


def upgrade() -> None:
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in SIGNATURES:
        op.execute(f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    for stmt in PARTNER_DROPS + PARTNER_POLICIES:
        op.execute(stmt)
    for stmt in QUOTATION_DROPS + QUOTATION_POLICIES + QUOTATION_GUARD_DROPS + QUOTATION_PARENT_GUARD:
        op.execute(stmt)
    for stmt in ORDER_DROPS + ORDER_POLICIES + ORDER_GUARD_DROPS + ORDER_PARENT_GUARD:
        op.execute(stmt)
    op.execute(counts_after())
    op.execute(minutes_after())
    op.execute(task_link_after())


def downgrade() -> None:
    m12 = _load("012_quotations")
    m13 = _load("013_orders_approvals_dispatch")
    for stmt in ORDER_DROPS + m13.ORDER_POLICIES + ORDER_GUARD_DROPS + m13.PARENT_GUARD:
        op.execute(stmt)
    for stmt in QUOTATION_DROPS + m12.QUOTATION_POLICIES + QUOTATION_GUARD_DROPS + m12.PARENT_GUARD:
        op.execute(stmt)
    for stmt in PARTNER_DROPS + _old_partner_policies():
        op.execute(stmt)
    op.execute(_replace(_counts_before(), "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"))
    op.execute(_replace(_minutes_before(), "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"))
    op.execute(_replace(_task_link_before(), "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"))
    for sig in reversed(SIGNATURES):
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
