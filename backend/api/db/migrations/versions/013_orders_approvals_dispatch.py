"""013: sales orders, the approval engine, and dispatch (FS-011).

Nine tables, the generated policies and indexes for the `sales_orders` ScopeSpec,
the parent guard, the immutability triggers (column grants first, triggers as the
belt), the close-short line trigger at depth 2, the approval engine's definers,
the order and dispatch definers, `lead_timeline()` replaced once more to filter
order events through the order's own visibility, and `activity_event`'s policy
regenerated with the `sales_order` arm.

Settled by review before a line was written (FS-011 §8, §9):
- `app_role` holds column grants on `sales_order`: status, the number, the seller
  snapshot and every approval and dispatch field are written by definers only.
  Executed by the delta check: an UPDATE or INSERT naming an ungranted column is
  42501, and a definer owned by the migration role still writes it (N-1, C-2).
- A line role is `is_functional = false AND is_portal = false`; escalation to a
  lower line step is by line role only, so Accounts and Dispatch (level 5,
  approve at global) never decide a manager step (plan review B-1).
- `create_approval_request()` reads the amount from the document (B-2).
- `qty_short` is written by a trigger at depth 2 (B-3); a direct statement and a
  definer's own UPDATE both run at depth 1.
- Approval event payloads carry `seq`, `role` and `decision` only (B-5).

GRANTS, HAND_POLICIES and the generated snapshots are read by
tests/db/migration_grants.py and the drift tests. The revision ends with its own
PUBLIC revoke.

Revision ID: 013_orders_approvals_dispatch
Revises: 012_quotations
"""

# ruff: noqa: E501  (generated and embedded SQL; its line length is not ours to wrap)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "013_orders_approvals_dispatch"
down_revision: str | None = "012_quotations"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
GSTIN_PATTERN = "^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}$"

TABLES = ("dispatch_line", "dispatch", "order_quotation", "order_line", "order_counter",
          "sales_order", "approval_step", "approval_request", "approval_threshold")

# ── grants: column-level on sales_order (N-1, C-2) ────────────────────────────

# what a draft edits; everything else on the row is written by a definer
_ORDER_EDITABLE = ("order_type, lead_id, partner_id, party_name, party_mobile, party_address, "
                   "party_gstin, delivery_address, territory_id, seller_gstin_id, "
                   "place_of_supply_territory_id, place_of_supply_state_id, intra_state, "
                   "price_effective_date, price_list_id, payment_terms, is_provisional, "
                   "gross, discount, taxable, cgst, sgst, igst, total, remarks, updated_by")
_ORDER_INSERTABLE = _ORDER_EDITABLE + ", owner_user_id, owner_org_unit_id, created_by"

GRANTS: dict[str, str] = {
    "sales_order": f"SELECT, INSERT ({_ORDER_INSERTABLE}), UPDATE ({_ORDER_EDITABLE})",
    # a draft's lines are replaced by delete and insert; the trigger narrows every
    # write to a draft parent
    "order_line": "SELECT, INSERT, UPDATE, DELETE",
    "order_quotation": "SELECT",
    "approval_request": "SELECT",
    "approval_step": "SELECT",
    "approval_threshold": "SELECT, INSERT, UPDATE",
    "dispatch": "SELECT",
    "dispatch_line": "SELECT",
}

_O_VIEW = "(SELECT app_has_permission('sales_orders', 'view'))"
_O_EDIT = "(SELECT app_has_permission('sales_orders', 'edit'))"
_LINE_PARENT = "EXISTS (SELECT 1 FROM sales_order o WHERE o.id = sales_order_id)"
_D_VIEW = "(SELECT app_has_permission('dispatch', 'view'))"

HAND_POLICIES: list[tuple[str, str]] = [
    # order_line follows its order, 012's quotation_line shape
    ("order_line", f"CREATE POLICY order_line_sel ON order_line FOR SELECT USING (\n  {_LINE_PARENT}\n)"),
    ("order_line", f"CREATE POLICY order_line_res_perm ON order_line AS RESTRICTIVE FOR SELECT USING (\n  {_O_VIEW}\n)"),
    ("order_line", f"CREATE POLICY order_line_ins ON order_line FOR INSERT WITH CHECK (\n  {_LINE_PARENT}\n)"),
    ("order_line", f"CREATE POLICY order_line_ins_perm ON order_line AS RESTRICTIVE FOR INSERT WITH CHECK (\n  {_O_EDIT}\n)"),
    ("order_line", f"CREATE POLICY order_line_upd ON order_line FOR UPDATE USING (\n  {_LINE_PARENT}\n) WITH CHECK (\n  {_LINE_PARENT}\n)"),
    ("order_line", f"CREATE POLICY order_line_upd_perm ON order_line AS RESTRICTIVE FOR UPDATE USING (\n  {_O_EDIT}\n)"),
    ("order_line", f"CREATE POLICY order_line_del ON order_line FOR DELETE USING (\n  {_LINE_PARENT}\n)"),
    ("order_line", f"CREATE POLICY order_line_del_perm ON order_line AS RESTRICTIVE FOR DELETE USING (\n  {_O_EDIT}\n)"),
    # the links are read through the order and written by definers only
    ("order_quotation", f"CREATE POLICY order_quotation_sel ON order_quotation FOR SELECT USING (\n  {_LINE_PARENT}\n)"),
    ("order_quotation", f"CREATE POLICY order_quotation_res_perm ON order_quotation AS RESTRICTIVE FOR SELECT USING (\n  {_O_VIEW}\n)"),
    # the approval rows are read through their document; no write policy at all
    # (RBAC 5.2a's step_upd belongs to a direct path FS-011 does not build)
    ("approval_request", """CREATE POLICY approval_request_sel ON approval_request FOR SELECT USING (
  CASE doc_type
    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order d WHERE d.id = entity_id)
    ELSE (SELECT app_is_system())
  END
)"""),
    ("approval_step", """CREATE POLICY approval_step_sel ON approval_step FOR SELECT USING (
  EXISTS (SELECT 1 FROM approval_request r WHERE r.id = request_id)
)"""),
    # the bands: readable by admins and by anyone who approves (the queue shows
    # them), written with masters.edit
    ("approval_threshold", """CREATE POLICY approval_threshold_sel ON approval_threshold FOR SELECT USING (
  (SELECT app_has_permission('masters', 'view')) OR (SELECT app_has_permission('sales_orders', 'approve'))
)"""),
    ("approval_threshold", """CREATE POLICY approval_threshold_ins ON approval_threshold FOR INSERT WITH CHECK (
  (SELECT app_has_permission('masters', 'edit'))
)"""),
    ("approval_threshold", """CREATE POLICY approval_threshold_upd ON approval_threshold FOR UPDATE USING (
  (SELECT app_has_permission('masters', 'edit'))
) WITH CHECK (
  (SELECT app_has_permission('masters', 'edit'))
)"""),
    # dispatch rows are read through their order with dispatch.view; written by
    # definers only
    ("dispatch", f"CREATE POLICY dispatch_sel ON dispatch FOR SELECT USING (\n  {_LINE_PARENT}\n)"),
    ("dispatch", f"CREATE POLICY dispatch_res_perm ON dispatch AS RESTRICTIVE FOR SELECT USING (\n  {_D_VIEW}\n)"),
    ("dispatch_line", """CREATE POLICY dispatch_line_sel ON dispatch_line FOR SELECT USING (
  EXISTS (SELECT 1 FROM dispatch d WHERE d.id = dispatch_id)
)"""),
    # activity_event gains the sales_order arm (api/authz/activity.py ENTITY_BY_ID);
    # supersedes 012's literal, and the drift test compares the union's last-wins
    ("activity_event", """CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (
  CASE entity_type
    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)
    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)
    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)
    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)
    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)
    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)
    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order c WHERE c.id = entity_id)
    ELSE (SELECT app_is_system())
  END
)"""),
]

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz"""

# ── the schema ───────────────────────────────────────────────────────────────

ENUMS = [
    "CREATE TYPE order_type AS ENUM ('commercial', 'industrial', 'export', 'sample', 'marketing_material', 'subsidised', 'replacement')",
    "CREATE TYPE order_status AS ENUM ('draft', 'submitted', 'approved', 'partially_dispatched', 'dispatched', 'closed_short', 'cancelled')",
    "CREATE TYPE order_payment_terms AS ENUM ('full_payment', 'credit')",
    "CREATE TYPE approval_status AS ENUM ('pending', 'approved', 'rejected', 'cancelled')",
    "CREATE TYPE approval_decision AS ENUM ('approve', 'reject')",
]

TABLES_SQL = [
    f"""CREATE TABLE approval_threshold (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_type text NOT NULL,
    role_id uuid NOT NULL REFERENCES role(id),
    territory_id uuid REFERENCES territory(id),
    max_amount numeric(14,2),
    {AUDIT},
    CONSTRAINT uq_approval_threshold UNIQUE NULLS NOT DISTINCT (doc_type, role_id, territory_id),
    CONSTRAINT ck_approval_threshold_doc_type CHECK (doc_type IN ('sales_order', 'quotation', 'complaint')),
    CONSTRAINT ck_approval_threshold_amount CHECK (max_amount IS NULL OR max_amount > 0)
)""",
    """CREATE TABLE approval_request (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_type text NOT NULL,
    entity_id uuid NOT NULL,
    requested_by uuid NOT NULL REFERENCES app_user(id),
    status approval_status NOT NULL DEFAULT 'pending',
    amount numeric(14,2) NOT NULL,
    territory_id uuid REFERENCES territory(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz,
    CONSTRAINT ck_approval_request_doc_type CHECK (doc_type IN ('sales_order', 'quotation', 'complaint')),
    CONSTRAINT ck_approval_request_decided CHECK ((status = 'pending') = (decided_at IS NULL))
)""",
    """CREATE TABLE approval_step (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL REFERENCES approval_request(id) ON DELETE CASCADE,
    seq int NOT NULL,
    approver_role_id uuid NOT NULL REFERENCES role(id),
    approver_user_id uuid REFERENCES app_user(id),
    decided_role_id uuid REFERENCES role(id),
    decision approval_decision,
    remark text,
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_approval_step_seq UNIQUE (request_id, seq),
    CONSTRAINT ck_approval_step_seq CHECK (seq >= 1),
    CONSTRAINT ck_approval_step_remark CHECK (remark IS NULL OR length(remark) <= 2000),
    CONSTRAINT ck_approval_step_decided CHECK (decision IS NULL OR (approver_user_id IS NOT NULL AND decided_at IS NOT NULL AND decided_role_id IS NOT NULL))
)""",
    f"""CREATE TABLE sales_order (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_no citext UNIQUE,
    order_type order_type NOT NULL,
    status order_status NOT NULL DEFAULT 'draft',
    lead_id uuid REFERENCES lead(id),
    partner_id uuid REFERENCES channel_partner(id),
    party_name text NOT NULL,
    party_mobile text,
    party_address text,
    party_gstin citext,
    delivery_address text,
    owner_user_id uuid REFERENCES app_user(id),
    owner_org_unit_id uuid NOT NULL REFERENCES org_unit(id),
    territory_id uuid NOT NULL REFERENCES territory(id),
    seller_gstin_id uuid NOT NULL REFERENCES seller_gstin(id),
    seller_legal_name text,
    seller_gstin_no citext,
    seller_address text,
    seller_state_code text,
    place_of_supply_territory_id uuid NOT NULL REFERENCES territory(id),
    place_of_supply_state_id uuid NOT NULL REFERENCES territory(id),
    intra_state boolean NOT NULL,
    price_effective_date date NOT NULL,
    tax_date date,
    price_list_id uuid REFERENCES price_list(id),
    payment_terms order_payment_terms NOT NULL DEFAULT 'full_payment',
    is_provisional boolean NOT NULL DEFAULT false,
    gross numeric(14,2) NOT NULL DEFAULT 0,
    discount numeric(14,2) NOT NULL DEFAULT 0,
    taxable numeric(14,2) NOT NULL DEFAULT 0,
    cgst numeric(14,2) NOT NULL DEFAULT 0,
    sgst numeric(14,2) NOT NULL DEFAULT 0,
    igst numeric(14,2) NOT NULL DEFAULT 0,
    total numeric(14,2) NOT NULL DEFAULT 0,
    remarks text,
    submitted_at timestamptz,
    approved_at timestamptz,
    cancelled_at timestamptz,
    cancel_remark text,
    closed_at timestamptz,
    close_remark text,
    dispatch_seq int NOT NULL DEFAULT 0,
    {AUDIT},
    CONSTRAINT ck_sales_order_party_name CHECK (length(btrim(party_name)) BETWEEN 1 AND 200),
    CONSTRAINT ck_sales_order_lengths CHECK (
        (party_address IS NULL OR length(party_address) <= 500)
        AND (delivery_address IS NULL OR length(delivery_address) <= 500)
        AND (remarks IS NULL OR length(remarks) <= 2000)
        AND (cancel_remark IS NULL OR length(cancel_remark) <= 2000)
        AND (close_remark IS NULL OR length(close_remark) <= 2000)),
    CONSTRAINT ck_sales_order_party_gstin CHECK (party_gstin IS NULL OR (party_gstin ~ '{GSTIN_PATTERN}' AND party_gstin = upper(party_gstin))),
    CONSTRAINT ck_sales_order_total CHECK (total = taxable + cgst + sgst + igst),
    CONSTRAINT ck_sales_order_submitted CHECK (status IN ('draft', 'cancelled') OR (
        order_no IS NOT NULL AND submitted_at IS NOT NULL AND tax_date IS NOT NULL
        AND seller_legal_name IS NOT NULL AND seller_gstin_no IS NOT NULL AND seller_state_code IS NOT NULL)),
    CONSTRAINT ck_sales_order_approved CHECK (status IN ('draft', 'submitted', 'cancelled') OR approved_at IS NOT NULL),
    CONSTRAINT ck_sales_order_cancelled CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL)),
    CONSTRAINT ck_sales_order_closed CHECK ((status = 'closed_short') = (closed_at IS NOT NULL))
)""",
    """CREATE TABLE order_line (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sales_order_id uuid NOT NULL REFERENCES sales_order(id) ON DELETE CASCADE,
    line_no int NOT NULL,
    product_id uuid NOT NULL REFERENCES product(id),
    description text NOT NULL,
    hsn_code text NOT NULL,
    uom text NOT NULL,
    uom_decimals smallint NOT NULL,
    qty numeric(12,3) NOT NULL,
    rate numeric(14,2) NOT NULL,
    price_list_id uuid NOT NULL REFERENCES price_list(id),
    price_list_item_id uuid NOT NULL REFERENCES price_list_item(id),
    gst_rate_id uuid NOT NULL REFERENCES gst_rate(id),
    gross numeric(14,2) NOT NULL,
    discount_pct numeric(6,3) NOT NULL DEFAULT 0,
    discount1_amt numeric(14,2) NOT NULL DEFAULT 0,
    after_discount1 numeric(14,2) NOT NULL,
    discount2_pct numeric(6,3) NOT NULL DEFAULT 0,
    discount2_amt numeric(14,2) NOT NULL DEFAULT 0,
    after_discount2 numeric(14,2) NOT NULL,
    discount3_pct numeric(6,3) NOT NULL DEFAULT 0,
    discount3_amt numeric(14,2) NOT NULL DEFAULT 0,
    discount numeric(14,2) NOT NULL DEFAULT 0,
    taxable numeric(14,2) NOT NULL,
    gst_slab numeric(6,3) NOT NULL,
    cgst_rate numeric(6,3) NOT NULL,
    sgst_rate numeric(6,3) NOT NULL,
    igst_rate numeric(6,3) NOT NULL,
    cgst numeric(14,2) NOT NULL,
    sgst numeric(14,2) NOT NULL,
    igst numeric(14,2) NOT NULL,
    total numeric(14,2) NOT NULL,
    provisional_fields text[] NOT NULL DEFAULT '{}',
    qty_short numeric(12,3) NOT NULL DEFAULT 0,
    source_quotation_line_id uuid REFERENCES quotation_line(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_order_line_no UNIQUE (sales_order_id, line_no),
    CONSTRAINT ck_order_line_qty CHECK (qty > 0 AND round(qty, uom_decimals) = qty),
    CONSTRAINT ck_order_line_short CHECK (qty_short >= 0 AND qty_short <= qty),
    CONSTRAINT ck_order_line_decimals CHECK (uom_decimals BETWEEN 0 AND 3),
    CONSTRAINT ck_order_line_pcts CHECK (
        discount_pct BETWEEN 0 AND 100 AND discount2_pct BETWEEN 0 AND 100
        AND discount3_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_order_line_cascade CHECK (
        after_discount1 = gross - discount1_amt
        AND after_discount2 = after_discount1 - discount2_amt
        AND taxable = after_discount2 - discount3_amt
        AND discount = discount1_amt + discount2_amt + discount3_amt),
    CONSTRAINT ck_order_line_total CHECK (total = taxable + cgst + sgst + igst)
)""",
    """CREATE TABLE order_quotation (
    sales_order_id uuid NOT NULL REFERENCES sales_order(id) ON DELETE CASCADE,
    quotation_id uuid NOT NULL REFERENCES quotation(id),
    released_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sales_order_id, quotation_id)
)""",
    """CREATE TABLE order_counter (
    state_code text NOT NULL,
    financial_year text NOT NULL,
    last_value int NOT NULL DEFAULT 0,
    PRIMARY KEY (state_code, financial_year)
)""",
    """CREATE TABLE dispatch (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sales_order_id uuid NOT NULL REFERENCES sales_order(id),
    dispatch_no text NOT NULL UNIQUE,
    dc_no text,
    dc_date date,
    invoice_no text,
    invoice_date date,
    dispatched_at timestamptz NOT NULL,
    transporter text,
    vehicle_no text,
    dispatched_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    voided_at timestamptz,
    voided_by uuid REFERENCES app_user(id),
    void_remark text,
    CONSTRAINT ck_dispatch_lengths CHECK (
        (dc_no IS NULL OR length(dc_no) <= 200) AND (invoice_no IS NULL OR length(invoice_no) <= 200)
        AND (transporter IS NULL OR length(transporter) <= 200) AND (vehicle_no IS NULL OR length(vehicle_no) <= 200)
        AND (void_remark IS NULL OR length(void_remark) <= 2000)),
    CONSTRAINT ck_dispatch_voided CHECK ((voided_at IS NULL) = (voided_by IS NULL))
)""",
    """CREATE TABLE dispatch_line (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dispatch_id uuid NOT NULL REFERENCES dispatch(id) ON DELETE CASCADE,
    order_line_id uuid NOT NULL REFERENCES order_line(id),
    qty numeric(12,3) NOT NULL,
    CONSTRAINT uq_dispatch_line UNIQUE (dispatch_id, order_line_id),
    CONSTRAINT ck_dispatch_line_qty CHECK (qty > 0)
)""",
]

# Generated by policy_sql.policies_for(SPECS["sales_orders"]) and pasted; the drift
# test regenerates and compares against pg_policies.
ORDER_POLICIES = [
    "ALTER TABLE sales_order ENABLE ROW LEVEL SECURITY",
    """CREATE POLICY sales_order_sel_own ON sales_order FOR SELECT USING (
  (SELECT app_scope('sales_orders')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id())
)""",
    """CREATE POLICY sales_order_sel_org_subtree ON sales_order FOR SELECT USING (
  (SELECT app_scope('sales_orders')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))
)""",
    """CREATE POLICY sales_order_sel_territory ON sales_order FOR SELECT USING (
  (SELECT app_scope('sales_orders')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id()))
)""",
    """CREATE POLICY sales_order_sel_partner_subtree ON sales_order FOR SELECT USING (
  (SELECT app_scope('sales_orders')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))
)""",
    """CREATE POLICY sales_order_sel_global ON sales_order FOR SELECT USING (
  (SELECT app_scope('sales_orders')) = 'global'
)""",
    """CREATE POLICY sales_order_res_perm ON sales_order AS RESTRICTIVE FOR SELECT USING (
  (SELECT app_has_permission('sales_orders', 'view'))
)""",
    """CREATE POLICY sales_order_res_deleted ON sales_order AS RESTRICTIVE FOR SELECT USING (
  deleted_at IS NULL OR (SELECT app_has_permission('sales_orders', 'delete'))
)""",
    """CREATE POLICY sales_order_ins ON sales_order FOR INSERT WITH CHECK (
  (((SELECT app_scope('sales_orders')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('sales_orders')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('sales_orders')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('sales_orders')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('sales_orders')) = 'global'))
  AND (lead_id IS NULL OR EXISTS (SELECT 1 FROM lead p WHERE p.id = lead_id))
  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))
  AND (owner_org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = owner_org_unit_id))
  AND (partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id))
)""",
    """CREATE POLICY sales_order_ins_perm ON sales_order AS RESTRICTIVE FOR INSERT WITH CHECK (
  (SELECT app_has_permission('sales_orders', 'create'))
)""",
    """CREATE POLICY sales_order_upd ON sales_order FOR UPDATE USING (
  ((SELECT app_scope('sales_orders')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('sales_orders')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('sales_orders')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('sales_orders')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('sales_orders')) = 'global')
) WITH CHECK (
  ((SELECT app_scope('sales_orders')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('sales_orders')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('sales_orders')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('sales_orders')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('sales_orders')) = 'global')
)""",
    """CREATE POLICY sales_order_upd_perm ON sales_order AS RESTRICTIVE FOR UPDATE USING (
  (SELECT app_has_permission('sales_orders', 'edit'))
)""",
    """CREATE POLICY sales_order_del ON sales_order FOR DELETE USING (
  ((SELECT app_scope('sales_orders')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('sales_orders')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('sales_orders')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('sales_orders')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('sales_orders')) = 'global')
)""",
    """CREATE POLICY sales_order_del_perm ON sales_order AS RESTRICTIVE FOR DELETE USING (
  (SELECT app_has_permission('sales_orders', 'delete'))
)""",
]

GENERATED_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_sales_order_owner_user_id ON sales_order (owner_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_order_owner_org_unit_id ON sales_order (owner_org_unit_id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_order_territory_id ON sales_order (territory_id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_order_partner_id ON sales_order (partner_id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_order_deleted_at_live ON sales_order (deleted_at) WHERE deleted_at IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_sales_order_lead_id ON sales_order (lead_id)",
]

HAND_INDEXES = [
    "CREATE INDEX ix_approval_threshold_role ON approval_threshold (role_id)",
    "CREATE INDEX ix_approval_threshold_territory ON approval_threshold (territory_id)",
    "CREATE UNIQUE INDEX uq_approval_request_pending ON approval_request (doc_type, entity_id) WHERE status = 'pending'",
    "CREATE INDEX ix_approval_request_pending ON approval_request (status, created_at) WHERE status = 'pending'",
    "CREATE INDEX ix_approval_request_latest ON approval_request (doc_type, entity_id, created_at DESC)",
    "CREATE INDEX ix_approval_step_open ON approval_step (request_id, seq) WHERE decision IS NULL",
    "CREATE INDEX ix_approval_step_role_open ON approval_step (approver_role_id) WHERE decision IS NULL",
    "CREATE INDEX ix_sales_order_list ON sales_order (created_at DESC, id DESC) WHERE deleted_at IS NULL",
    "CREATE INDEX ix_sales_order_party_name_trgm ON sales_order USING gin (party_name gin_trgm_ops)",
    "CREATE INDEX ix_sales_order_order_no_trgm ON sales_order USING gin ((order_no::text) gin_trgm_ops)",
    "CREATE INDEX ix_sales_order_party_mobile ON sales_order (party_mobile)",
    "CREATE INDEX ix_order_line_product ON order_line (product_id)",
    "CREATE INDEX ix_order_line_source ON order_line (source_quotation_line_id)",
    "CREATE UNIQUE INDEX uq_order_quotation_live ON order_quotation (quotation_id) WHERE released_at IS NULL",
    "CREATE INDEX ix_order_quotation_order ON order_quotation (sales_order_id)",
    "CREATE INDEX ix_dispatch_order ON dispatch (sales_order_id)",
    "CREATE INDEX ix_dispatch_invoice ON dispatch (invoice_no)",
    "CREATE INDEX ix_dispatch_line_order_line ON dispatch_line (order_line_id)",
]

PARENT_GUARD = [
    """CREATE FUNCTION sales_order_parent_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$
        BEGIN
            IF NEW.lead_id IS DISTINCT FROM OLD.lead_id AND NEW.lead_id IS NOT NULL
               AND NOT authz_visible('lead', NEW.lead_id) THEN
                RAISE EXCEPTION 'lead_id % is not in your scope', NEW.lead_id
                    USING ERRCODE = '42501';
            END IF;
            IF NEW.territory_id IS DISTINCT FROM OLD.territory_id AND NEW.territory_id IS NOT NULL
               AND NOT authz_visible('territory', NEW.territory_id) THEN
                RAISE EXCEPTION 'territory_id % is not in your scope', NEW.territory_id
                    USING ERRCODE = '42501';
            END IF;
            IF NEW.owner_org_unit_id IS DISTINCT FROM OLD.owner_org_unit_id AND NEW.owner_org_unit_id IS NOT NULL
               AND NOT authz_visible('org_unit', NEW.owner_org_unit_id) THEN
                RAISE EXCEPTION 'owner_org_unit_id % is not in your scope', NEW.owner_org_unit_id
                    USING ERRCODE = '42501';
            END IF;
            IF NEW.partner_id IS DISTINCT FROM OLD.partner_id AND NEW.partner_id IS NOT NULL
               AND NOT authz_visible('channel_partner', NEW.partner_id) THEN
                RAISE EXCEPTION 'partner_id % is not in your scope', NEW.partner_id
                    USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END $fn$""",
    """CREATE TRIGGER trg_sales_order_parent_guard
            BEFORE UPDATE OF lead_id, territory_id, owner_org_unit_id, partner_id ON sales_order
            FOR EACH ROW EXECUTE FUNCTION sales_order_parent_guard()""",
]

# ── immutability: the belt behind the column grants ───────────────────────────

# the columns a submitted order may still change; everything else is the document
_MUTABLE_AFTER_SUBMIT = ("'status', 'approved_at', 'cancelled_at', 'cancel_remark', 'closed_at', "
                         "'close_remark', 'dispatch_seq', 'updated_at', 'updated_by', 'synced_at', "
                         "'external_id'")

# FS-011 §3.1, the order's lifecycle; the refuse trigger checks every status move
_TRANSITIONS = """(OLD.status, NEW.status) IN (
            ('draft', 'submitted'), ('draft', 'cancelled'),
            ('submitted', 'draft'), ('submitted', 'approved'), ('submitted', 'cancelled'),
            ('approved', 'partially_dispatched'), ('approved', 'dispatched'),
            ('approved', 'closed_short'), ('approved', 'cancelled'),
            ('partially_dispatched', 'dispatched'), ('partially_dispatched', 'closed_short'),
            ('partially_dispatched', 'approved'),
            ('dispatched', 'partially_dispatched'), ('dispatched', 'approved'))"""

TRIGGER_FUNCTIONS = [
    # A new row is a fresh draft, whatever the INSERT named (C-2's belt: the
    # column grant already refuses naming these as app_role).
    """CREATE FUNCTION refuse_order_insert_not_draft() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NEW.status <> 'draft' OR NEW.order_no IS NOT NULL OR NEW.submitted_at IS NOT NULL
       OR NEW.approved_at IS NOT NULL OR NEW.cancelled_at IS NOT NULL OR NEW.closed_at IS NOT NULL
       OR NEW.tax_date IS NOT NULL OR NEW.seller_legal_name IS NOT NULL OR NEW.dispatch_seq <> 0
       OR NEW.deleted_at IS NOT NULL THEN
        RAISE EXCEPTION 'a new order is a fresh draft' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$""",
    f"""CREATE FUNCTION refuse_submitted_order_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status AND NOT {_TRANSITIONS} THEN
        RAISE EXCEPTION 'an order cannot move from % to %', OLD.status, NEW.status
            USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> 'draft'
       AND (to_jsonb(NEW) - ARRAY[{_MUTABLE_AFTER_SUBMIT}]) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY[{_MUTABLE_AFTER_SUBMIT}]) THEN
        RAISE EXCEPTION 'a submitted order cannot change; reject it back to draft or cancel it'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$""",
    # Both parents on an UPDATE (FS-005 9.7 A-2). The one admitted change under a
    # non-draft parent is qty_short, and only from the close-short trigger at
    # depth 2: a direct statement and a definer's own UPDATE run at depth 1 (B-3).
    """CREATE FUNCTION refuse_submitted_order_line_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
DECLARE
    v_frozen boolean;
BEGIN
    SELECT bool_or(status <> 'draft') INTO v_frozen FROM sales_order
     WHERE id IN (NEW.sales_order_id, OLD.sales_order_id);
    IF v_frozen THEN
        IF TG_OP = 'UPDATE' AND pg_trigger_depth() >= 2
           AND (to_jsonb(NEW) - ARRAY['qty_short', 'updated_at']) = (to_jsonb(OLD) - ARRAY['qty_short', 'updated_at']) THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'the lines of a submitted order cannot change; reject it back to draft'
            USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END $fn$""",
    # Closing short records every line's open quantity as short, here, at depth 2.
    """CREATE FUNCTION order_close_short_lines() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    UPDATE order_line l
       SET qty_short = l.qty - COALESCE((
             SELECT sum(dl.qty) FROM dispatch_line dl JOIN dispatch d ON d.id = dl.dispatch_id
              WHERE dl.order_line_id = l.id AND d.voided_at IS NULL), 0)
     WHERE l.sales_order_id = NEW.id;
    RETURN NULL;
END $fn$""",
    # A dispatch is voided, never edited; a line disappears only with its dispatch.
    """CREATE FUNCTION refuse_dispatch_line_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    IF TG_OP = 'DELETE' AND NOT EXISTS (SELECT 1 FROM dispatch WHERE id = OLD.dispatch_id) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'a dispatch line cannot change; void the dispatch' USING ERRCODE = '23514';
END $fn$""",
]

TRIGGERS = [
    *PARENT_GUARD[1:],
    "CREATE TRIGGER trg_sales_order_insert_draft BEFORE INSERT ON sales_order FOR EACH ROW EXECUTE FUNCTION refuse_order_insert_not_draft()",
    "CREATE TRIGGER trg_sales_order_refuse_edit BEFORE UPDATE ON sales_order FOR EACH ROW EXECUTE FUNCTION refuse_submitted_order_edit()",
    "CREATE TRIGGER trg_sales_order_updated_at BEFORE UPDATE ON sales_order FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_sales_order_audit AFTER INSERT OR UPDATE OR DELETE ON sales_order FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_sales_order_close_short AFTER UPDATE OF status ON sales_order FOR EACH ROW WHEN (NEW.status = 'closed_short' AND OLD.status IS DISTINCT FROM NEW.status) EXECUTE FUNCTION order_close_short_lines()",
    "CREATE TRIGGER trg_order_line_refuse_edit BEFORE INSERT OR UPDATE OR DELETE ON order_line FOR EACH ROW EXECUTE FUNCTION refuse_submitted_order_line_edit()",
    "CREATE TRIGGER trg_order_line_updated_at BEFORE UPDATE ON order_line FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_order_line_audit AFTER INSERT OR UPDATE OR DELETE ON order_line FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_dispatch_line_refuse_edit BEFORE UPDATE OR DELETE ON dispatch_line FOR EACH ROW EXECUTE FUNCTION refuse_dispatch_line_edit()",
    "CREATE TRIGGER trg_approval_threshold_updated_at BEFORE UPDATE ON approval_threshold FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_approval_threshold_audit AFTER INSERT OR UPDATE OR DELETE ON approval_threshold FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

# ── the definers ─────────────────────────────────────────────────────────────

# policy_sql.guard_sql(SPECS["sales_orders"]), evaluated over the claim as the owner
_VISIBLE = """(((SELECT app_scope('sales_orders')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('sales_orders')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('sales_orders')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('sales_orders')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('sales_orders')) = 'global'))
  AND ((SELECT app_has_permission('sales_orders', 'view')))
  AND (deleted_at IS NULL OR (SELECT app_has_permission('sales_orders', 'delete')))"""

# the open quantity of a line: ordered, less short, less every live dispatch
_OPEN = """(l.qty - l.qty_short - COALESCE((
            SELECT sum(dl.qty) FROM dispatch_line dl JOIN dispatch d ON d.id = dl.dispatch_id
             WHERE dl.order_line_id = l.id AND d.voided_at IS NULL), 0))"""

FUNCTIONS = [
    f"""CREATE FUNCTION order_visible(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM sales_order WHERE id = p_id AND (
{_VISIBLE}
    ))
$fn$""",
    # The owner's place on the line: a line role's level, else 0 (plan review B-1:
    # every seeded role has a level, so the flags decide, not coalesce).
    """CREATE FUNCTION approval_owner_level(p_user_id uuid) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT COALESCE((
        SELECT CASE WHEN NOT r.is_functional AND NOT r.is_portal THEN r.level ELSE 0 END
          FROM app_user u JOIN role r ON r.id = u.role_id WHERE u.id = p_user_id), 0)
$fn$""",
    # FS-011 2.3. Per manager role, the nearest threshold row up the territory
    # tree, else the global row; a role with no row is not on the chain. The band
    # is the lowest level whose ceiling covers the amount; the highest level with a
    # row has no ceiling in effect. Levels at or below the owner's are dropped.
    """CREATE FUNCTION approval_chain(p_doc_type text, p_amount numeric, p_territory_id uuid,
                               p_owner_level int) RETURNS uuid[]
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    r record;
    v_found boolean;
    v_ceiling numeric;
    v_ids uuid[] := '{}';
    v_levels int[] := '{}';
    v_ceilings numeric[] := '{}';
    v_chain uuid[] := '{}';
    i int;
BEGIN
    FOR r IN SELECT id, level FROM role
              WHERE code IN ('district_manager', 'state_manager', 'regional_manager')
                AND deleted_at IS NULL AND NOT is_functional AND NOT is_portal
              ORDER BY level LOOP
        v_found := false;
        SELECT true, t.max_amount INTO v_found, v_ceiling
          FROM approval_threshold t
          LEFT JOIN territory_closure tc
            ON tc.ancestor_id = t.territory_id AND tc.descendant_id = p_territory_id
         WHERE t.doc_type = p_doc_type AND t.role_id = r.id AND t.deleted_at IS NULL
           AND (t.territory_id IS NULL OR tc.descendant_id IS NOT NULL)
         ORDER BY (t.territory_id IS NULL), tc.depth ASC
         LIMIT 1;
        IF v_found THEN
            v_ids := v_ids || r.id;
            v_levels := v_levels || r.level;
            v_ceilings := v_ceilings || v_ceiling;
        END IF;
    END LOOP;
    FOR i IN 1 .. COALESCE(array_length(v_ids, 1), 0) LOOP
        IF v_levels[i] > p_owner_level THEN
            v_chain := v_chain || v_ids[i];
        END IF;
        -- a null ceiling is no ceiling: that level is enough for any amount
        EXIT WHEN i = array_length(v_ids, 1)
               OR v_ceilings[i] IS NULL OR p_amount <= v_ceilings[i];
    END LOOP;
    SELECT v_chain || array_agg(id ORDER BY CASE code WHEN 'account_manager' THEN 1 ELSE 2 END)
      INTO v_chain
      FROM role WHERE code IN ('account_manager', 'dispatch_manager') AND deleted_at IS NULL;
    RETURN v_chain;
END $fn$""",
    # B-6: nobody of the step's role can take it. A line step: no active user with
    # the role in an office at or above the order's (the line roles' view scope is
    # org_subtree, pinned by a test). A functional step: no active user with it.
    """CREATE FUNCTION approval_step_stalled(p_step_id uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_role uuid; v_line boolean; v_req approval_request%ROWTYPE; v_org uuid; v_owner uuid; v_creator uuid;
BEGIN
    SELECT s.approver_role_id, NOT r.is_functional AND NOT r.is_portal INTO v_role, v_line
      FROM approval_step s JOIN role r ON r.id = s.approver_role_id WHERE s.id = p_step_id;
    SELECT q.* INTO v_req FROM approval_request q JOIN approval_step s ON s.request_id = q.id WHERE s.id = p_step_id;
    SELECT owner_org_unit_id, owner_user_id, created_by INTO v_org, v_owner, v_creator
      FROM sales_order WHERE id = v_req.entity_id;
    IF v_line THEN
        RETURN NOT EXISTS (
            SELECT 1 FROM app_user u JOIN org_closure oc ON oc.ancestor_id = u.org_unit_id
             WHERE oc.descendant_id = v_org AND u.role_id = v_role
               AND u.is_active AND u.deleted_at IS NULL
               AND u.id IS DISTINCT FROM v_req.requested_by
               AND u.id IS DISTINCT FROM v_owner AND u.id IS DISTINCT FROM v_creator);
    END IF;
    RETURN NOT EXISTS (SELECT 1 FROM app_user u WHERE u.role_id = v_role AND u.is_active AND u.deleted_at IS NULL);
END $fn$""",
    # Why the caller may not decide this step, or null when they may. The one
    # rule for record_decision() and the queue (plan review B-1, B-6).
    """CREATE FUNCTION approval_refusal(p_step_id uuid) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id();
    v_my_role uuid; v_my_level int; v_my_line boolean;
    v_step_role uuid; v_step_level int; v_step_line boolean;
    v_req approval_request%ROWTYPE; v_owner uuid; v_creator uuid;
BEGIN
    SELECT r.id, r.level, NOT r.is_functional AND NOT r.is_portal INTO v_my_role, v_my_level, v_my_line
      FROM app_user u JOIN role r ON r.id = u.role_id WHERE u.id = v_me;
    SELECT r.id, r.level, NOT r.is_functional AND NOT r.is_portal INTO v_step_role, v_step_level, v_step_line
      FROM approval_step s JOIN role r ON r.id = s.approver_role_id WHERE s.id = p_step_id;
    SELECT q.* INTO v_req FROM approval_request q JOIN approval_step s ON s.request_id = q.id WHERE s.id = p_step_id;
    IF v_req.doc_type <> 'sales_order' THEN
        RETURN 'not_your_step';
    END IF;
    SELECT owner_user_id, created_by INTO v_owner, v_creator FROM sales_order WHERE id = v_req.entity_id;
    IF v_me = v_req.requested_by OR v_me IS NOT DISTINCT FROM v_owner OR v_me IS NOT DISTINCT FROM v_creator THEN
        RETURN 'self_approval';
    END IF;
    IF NOT order_visible(v_req.entity_id) OR NOT app_has_permission('sales_orders', 'approve') THEN
        RETURN 'not_your_step';
    END IF;
    IF v_my_role = v_step_role THEN
        RETURN NULL;
    END IF;
    IF v_step_line AND v_my_line AND v_my_level > v_step_level THEN
        RETURN NULL;
    END IF;
    RETURN 'not_your_step';
END $fn$""",
    # The only INSERT path into the approval tables (RBAC 5.2a). Takes no amount:
    # it reads the document, which must already be submitted (plan review B-2).
    """CREATE FUNCTION create_approval_request(p_doc_type text, p_entity_id uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_order sales_order%ROWTYPE;
    v_chain uuid[];
    v_request uuid;
    v_role uuid;
    v_code text;
    i int;
BEGIN
    IF p_doc_type <> 'sales_order' THEN
        RAISE EXCEPTION 'approval for % is not built yet', p_doc_type USING ERRCODE = '0A000';
    END IF;
    IF NOT app_has_permission('sales_orders', 'edit') OR NOT order_visible(p_entity_id) THEN
        RAISE EXCEPTION 'not permitted on this order' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO v_order FROM sales_order WHERE id = p_entity_id FOR UPDATE;
    IF v_order.status <> 'submitted' OR v_order.order_no IS NULL THEN
        RAISE EXCEPTION 'the order is %; only a submitted order is approved', v_order.status
            USING ERRCODE = 'ORDNS';
    END IF;
    IF EXISTS (SELECT 1 FROM approval_request WHERE doc_type = p_doc_type AND entity_id = p_entity_id
                                                  AND status = 'pending') THEN
        RAISE EXCEPTION 'this order already has an open approval' USING ERRCODE = 'APRPD';
    END IF;
    v_chain := approval_chain(p_doc_type, v_order.total, v_order.territory_id,
                              approval_owner_level(v_order.owner_user_id));
    FOREACH v_role IN ARRAY v_chain LOOP
        SELECT code INTO v_code FROM role WHERE id = v_role AND (is_functional OR is_portal);
        IF FOUND AND NOT EXISTS (SELECT 1 FROM app_user WHERE role_id = v_role AND is_active
                                                           AND deleted_at IS NULL) THEN
            RAISE EXCEPTION 'no active user holds %', v_code USING ERRCODE = 'ORDNA';
        END IF;
    END LOOP;
    INSERT INTO approval_request (doc_type, entity_id, requested_by, amount, territory_id)
    VALUES (p_doc_type, p_entity_id, app_current_user_id(), v_order.total, v_order.territory_id)
    RETURNING id INTO v_request;
    FOR i IN 1 .. array_length(v_chain, 1) LOOP
        INSERT INTO approval_step (request_id, seq, approver_role_id) VALUES (v_request, i, v_chain[i]);
    END LOOP;
    RETURN v_request;
END $fn$""",
    # RBAC 5.2d, with the status guard as the second belt (delta check R-4).
    """CREATE FUNCTION apply_approval_outcome(p_doc_type text, p_entity_id uuid, p_outcome text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF p_doc_type <> 'sales_order' THEN
        RAISE EXCEPTION 'unknown doc_type %', p_doc_type;
    END IF;
    UPDATE sales_order
       SET status = CASE p_outcome WHEN 'approve' THEN 'approved'::order_status ELSE 'draft'::order_status END,
           approved_at = CASE p_outcome WHEN 'approve' THEN now() ELSE approved_at END
     WHERE id = p_entity_id AND status = 'submitted';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'the order is no longer waiting for approval' USING ERRCODE = 'APRCL';
    END IF;
END $fn$""",
    # RBAC 5.2b's five guards.
    """CREATE FUNCTION advance_approval(p_request_id uuid) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_req approval_request%ROWTYPE; v_total int; v_approved int; v_rejected int; v_lead uuid;
BEGIN
    SELECT * INTO v_req FROM approval_request WHERE id = p_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'approval_request % not found', p_request_id;
    END IF;
    IF v_req.status <> 'pending' THEN
        RETURN v_req.status::text;
    END IF;
    SELECT count(*), count(*) FILTER (WHERE decision = 'approve'), count(*) FILTER (WHERE decision = 'reject')
      INTO v_total, v_approved, v_rejected FROM approval_step WHERE request_id = p_request_id;
    IF v_total = 0 THEN
        RAISE EXCEPTION 'approval_request % has no steps', p_request_id;
    END IF;
    SELECT lead_id INTO v_lead FROM sales_order WHERE id = v_req.entity_id;
    IF v_rejected > 0 THEN
        UPDATE approval_request SET status = 'rejected', decided_at = now() WHERE id = p_request_id;
        PERFORM apply_approval_outcome(v_req.doc_type, v_req.entity_id, 'reject');
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('sales_order', v_req.entity_id, v_lead, 'order.returned', app_current_user_id(), '{}');
        RETURN 'rejected';
    END IF;
    IF v_approved < v_total THEN
        RETURN 'pending';
    END IF;
    UPDATE approval_request SET status = 'approved', decided_at = now() WHERE id = p_request_id;
    PERFORM apply_approval_outcome(v_req.doc_type, v_req.entity_id, 'approve');
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('sales_order', v_req.entity_id, v_lead, 'order.approved', app_current_user_id(), '{}');
    RETURN 'approved';
END $fn$""",
    # RBAC 5.2c: the actor from the claim, every check a policy would make, and the
    # document locked first, then the request, then the step.
    """CREATE FUNCTION record_decision(p_step_id uuid, p_decision text, p_remark text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_actor uuid := app_current_user_id();
    v_request uuid; v_doc_type text; v_entity uuid;
    v_req approval_request%ROWTYPE; v_step approval_step%ROWTYPE;
    v_reason text; v_remark text; v_role_code text; v_my_role uuid; v_lead uuid;
BEGIN
    IF v_actor IS NULL THEN
        RAISE EXCEPTION 'no_authenticated_actor' USING ERRCODE = '28000';
    END IF;
    IF p_decision NOT IN ('approve', 'reject') THEN
        RAISE EXCEPTION 'invalid_decision' USING ERRCODE = '22023';
    END IF;
    SELECT s.request_id, r.doc_type, r.entity_id INTO v_request, v_doc_type, v_entity
      FROM approval_step s JOIN approval_request r ON r.id = s.request_id WHERE s.id = p_step_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'step_not_found' USING ERRCODE = 'APRNF';
    END IF;
    IF v_doc_type = 'sales_order' THEN
        SELECT lead_id INTO v_lead FROM sales_order WHERE id = v_entity FOR UPDATE;
    END IF;
    SELECT * INTO v_req FROM approval_request WHERE id = v_request FOR UPDATE;
    IF v_req.status <> 'pending' THEN
        RAISE EXCEPTION 'request_closed' USING ERRCODE = 'APRCL';
    END IF;
    SELECT * INTO v_step FROM approval_step WHERE id = p_step_id FOR UPDATE;
    IF v_step.decision IS NOT NULL THEN
        RAISE EXCEPTION 'step_already_decided' USING ERRCODE = 'APRSD';
    END IF;
    IF EXISTS (SELECT 1 FROM approval_step WHERE request_id = v_request AND seq < v_step.seq
                                                AND decision IS NULL) THEN
        RAISE EXCEPTION 'earlier_step_undecided' USING ERRCODE = 'APREU';
    END IF;
    v_reason := approval_refusal(p_step_id);
    IF v_reason IS NOT NULL THEN
        RAISE EXCEPTION '%', v_reason USING ERRCODE = '42501';
    END IF;
    SELECT code INTO v_role_code FROM role WHERE id = v_step.approver_role_id;
    v_remark := NULLIF(btrim(p_remark), '');
    IF v_remark IS NULL AND (p_decision = 'reject' OR v_role_code = 'account_manager') THEN
        RAISE EXCEPTION 'remark_required' USING ERRCODE = 'APRRM';
    END IF;
    SELECT role_id INTO v_my_role FROM app_user WHERE id = v_actor;
    UPDATE approval_step
       SET decision = p_decision::approval_decision, approver_user_id = v_actor,
           decided_role_id = v_my_role, remark = v_remark, decided_at = now()
     WHERE id = p_step_id;
    -- no remark and no name in the payload: these rows reach the lead timeline (B-5)
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('sales_order', v_entity, v_lead, 'approval.decided', v_actor,
            jsonb_build_object('seq', v_step.seq, 'role', v_role_code, 'decision', p_decision));
    RETURN advance_approval(v_request);
END $fn$""",
    # The caller's queue (FS-011 4): my role's steps, plus lower line steps that
    # are stalled or, with p_include_below, all of them. Oldest first.
    """CREATE FUNCTION approval_queue(p_before_at timestamptz, p_before_id uuid, p_limit int,
                               p_include_below boolean)
RETURNS TABLE (step_id uuid, seq int, role_code text, stalled boolean, doc_type text,
               entity_id uuid, waiting_since timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_my_role uuid;
BEGIN
    SELECT role_id INTO v_my_role FROM app_user WHERE id = app_current_user_id();
    RETURN QUERY
    WITH open AS (
        SELECT s.id, s.seq, s.approver_role_id, r.code::text AS code, q.doc_type, q.entity_id,
               COALESCE((SELECT max(p.decided_at) FROM approval_step p
                          WHERE p.request_id = s.request_id AND p.seq < s.seq), q.created_at) AS since
          FROM approval_step s
          JOIN approval_request q ON q.id = s.request_id AND q.status = 'pending'
          JOIN role r ON r.id = s.approver_role_id
         WHERE s.decision IS NULL
           AND NOT EXISTS (SELECT 1 FROM approval_step e WHERE e.request_id = s.request_id
                                                            AND e.seq < s.seq AND e.decision IS NULL)
    )
    SELECT o.id, o.seq, o.code, approval_step_stalled(o.id), o.doc_type, o.entity_id, o.since
      FROM open o
     WHERE approval_refusal(o.id) IS NULL
       AND (o.approver_role_id = v_my_role OR p_include_below OR approval_step_stalled(o.id))
       AND (p_before_at IS NULL OR (o.since, o.id) > (p_before_at, p_before_id))
     ORDER BY o.since, o.id
     LIMIT p_limit;
END $fn$""",
    """CREATE FUNCTION order_quotations_release(p_order_id uuid) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    UPDATE order_quotation SET released_at = now()
     WHERE sales_order_id = p_order_id AND released_at IS NULL
$fn$""",
    # Locks the quotations in id order and checks what only the owner can count:
    # a colleague's live order holding one (FS-005's RLS-lies lesson). The service
    # has already checked that they agree (FS-011 4).
    """CREATE FUNCTION order_quotations_claim(p_order_id uuid, p_quotation_ids uuid[]) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    q record; v_holder uuid; v_holder_no text;
BEGIN
    IF NOT app_has_permission('sales_orders', 'edit') OR NOT order_visible(p_order_id) THEN
        RAISE EXCEPTION 'not permitted on this order' USING ERRCODE = '42501';
    END IF;
    PERFORM 1 FROM sales_order WHERE id = p_order_id AND status = 'draft'
       AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'only a draft takes quotations' USING ERRCODE = 'ORDNS';
    END IF;
    FOR q IN SELECT id, status::text AS status, superseded_by_id, deleted_at, quote_no
               FROM quotation WHERE id = ANY(p_quotation_ids) ORDER BY id FOR UPDATE LOOP
        IF q.deleted_at IS NOT NULL OR NOT quotation_visible(q.id) THEN
            RAISE EXCEPTION 'quotation % not found', q.id USING ERRCODE = 'ORQNF';
        END IF;
        IF q.status <> 'accepted' OR q.superseded_by_id IS NOT NULL THEN
            RAISE EXCEPTION 'quotation % is % and cannot be ordered', q.quote_no, q.status
                USING ERRCODE = 'ORQNA';
        END IF;
        SELECT oq.sales_order_id INTO v_holder FROM order_quotation oq
         WHERE oq.quotation_id = q.id AND oq.released_at IS NULL AND oq.sales_order_id <> p_order_id;
        IF FOUND THEN
            SELECT CASE WHEN order_visible(v_holder) THEN COALESCE(order_no::text, 'a draft order')
                        ELSE 'another order' END INTO v_holder_no FROM sales_order WHERE id = v_holder;
            RAISE EXCEPTION 'quotation % is on %', q.quote_no, v_holder_no USING ERRCODE = 'ORQON';
        END IF;
        INSERT INTO order_quotation (sales_order_id, quotation_id) VALUES (p_order_id, q.id)
        ON CONFLICT (sales_order_id, quotation_id) DO UPDATE SET released_at = NULL;
    END LOOP;
    IF (SELECT count(*) FROM quotation WHERE id = ANY(p_quotation_ids)) <> cardinality(p_quotation_ids) THEN
        RAISE EXCEPTION 'a quotation was not found' USING ERRCODE = 'ORQNF';
    END IF;
END $fn$""",
    """CREATE FUNCTION order_allocate_no(p_state_code text, p_fy text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    INSERT INTO order_counter (state_code, financial_year, last_value)
    VALUES (p_state_code, p_fy, 1)
    ON CONFLICT (state_code, financial_year)
    DO UPDATE SET last_value = order_counter.last_value + 1
    RETURNING last_value INTO v_n;
    RETURN 'SO/' || p_state_code || '/' || p_fy || '/'
           || lpad(v_n::text, greatest(5, length(v_n::text)), '0');
END $fn$""",
    # The submit's database half (N-1): the number, the seller snapshot, the tax
    # date, the status, and the chain. The service has re-priced and checked the
    # lines, the total and the lead before calling it.
    """CREATE FUNCTION order_submit(p_order_id uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_order sales_order%ROWTYPE; v_state text; v_day date; v_y int; v_fy text;
    v_no text; v_seller record;
BEGIN
    IF NOT app_has_permission('sales_orders', 'edit') OR NOT order_visible(p_order_id) THEN
        RAISE EXCEPTION 'not permitted on this order' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO v_order FROM sales_order WHERE id = p_order_id FOR UPDATE;
    IF v_order.deleted_at IS NOT NULL THEN
        RAISE EXCEPTION 'order not found' USING ERRCODE = 'ORDNF';
    END IF;
    IF v_order.status <> 'draft' THEN
        RAISE EXCEPTION 'the order is %', v_order.status USING ERRCODE = 'ORDNS';
    END IF;
    v_day := (now() AT TIME ZONE 'Asia/Kolkata')::date;
    v_no := v_order.order_no;
    IF v_no IS NULL THEN
        SELECT t.code::text INTO v_state
          FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id
         WHERE tc.descendant_id = v_order.territory_id AND t.level = 'state'
         ORDER BY tc.depth ASC LIMIT 1;
        IF v_state IS NULL THEN
            RAISE EXCEPTION 'the order territory has no coded state' USING ERRCODE = 'ORDST';
        END IF;
        v_y := CASE WHEN extract(month FROM v_day) >= 4 THEN extract(year FROM v_day)::int
                    ELSE extract(year FROM v_day)::int - 1 END;
        v_fy := v_y::text || '-' || lpad(((v_y + 1) % 100)::text, 2, '0');
        v_no := order_allocate_no(v_state, v_fy);
    END IF;
    SELECT sg.gstin, sg.legal_name, sg.address, st.code::text AS state_code INTO v_seller
      FROM seller_gstin sg JOIN territory st ON st.id = sg.state_territory_id
     WHERE sg.id = v_order.seller_gstin_id;
    UPDATE sales_order
       SET status = 'submitted', order_no = v_no, submitted_at = now(), tax_date = v_day,
           seller_gstin_no = v_seller.gstin, seller_legal_name = v_seller.legal_name,
           seller_address = v_seller.address, seller_state_code = v_seller.state_code,
           updated_by = app_current_user_id()
     WHERE id = p_order_id;
    RETURN create_approval_request('sales_order', p_order_id);
END $fn$""",
    # FS-011 3.1's cancel rules, and the request and the quotations with it.
    """CREATE FUNCTION order_cancel(p_order_id uuid, p_remark text, p_expected text DEFAULT NULL)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); v_order sales_order%ROWTYPE; v_remark text;
    v_can_delete boolean := app_has_permission('sales_orders', 'delete');
BEGIN
    IF NOT order_visible(p_order_id) THEN
        RAISE EXCEPTION 'order not found' USING ERRCODE = 'ORDNF';
    END IF;
    SELECT * INTO v_order FROM sales_order WHERE id = p_order_id FOR UPDATE;
    IF v_order.deleted_at IS NOT NULL THEN
        RAISE EXCEPTION 'order not found' USING ERRCODE = 'ORDNF';
    END IF;
    IF p_expected IS NOT NULL AND v_order.status::text <> p_expected THEN
        RAISE EXCEPTION 'the order is now %', v_order.status USING ERRCODE = 'ORDSC';
    END IF;
    v_remark := NULLIF(btrim(p_remark), '');
    IF v_remark IS NULL THEN
        RAISE EXCEPTION 'remark_required' USING ERRCODE = 'APRRM';
    END IF;
    IF EXISTS (SELECT 1 FROM dispatch WHERE sales_order_id = p_order_id AND voided_at IS NULL) THEN
        RAISE EXCEPTION 'the order has shipped' USING ERRCODE = 'ORDDS';
    END IF;
    IF v_order.status IN ('draft', 'submitted') THEN
        IF NOT (v_can_delete OR v_me IS NOT DISTINCT FROM v_order.owner_user_id
                OR v_me IS NOT DISTINCT FROM v_order.created_by) THEN
            RAISE EXCEPTION 'not permitted to cancel this order' USING ERRCODE = '42501';
        END IF;
    ELSIF v_order.status = 'approved' THEN
        IF NOT v_can_delete THEN
            RAISE EXCEPTION 'not permitted to cancel an approved order' USING ERRCODE = '42501';
        END IF;
    ELSE
        RAISE EXCEPTION 'a % order cannot be cancelled', v_order.status USING ERRCODE = 'ORDCN';
    END IF;
    UPDATE approval_request SET status = 'cancelled', decided_at = now()
     WHERE doc_type = 'sales_order' AND entity_id = p_order_id AND status = 'pending';
    UPDATE sales_order SET status = 'cancelled', cancelled_at = now(), cancel_remark = v_remark,
                           updated_by = v_me
     WHERE id = p_order_id;
    PERFORM order_quotations_release(p_order_id);
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('sales_order', p_order_id, v_order.lead_id, 'order.cancelled', v_me,
            jsonb_build_object('from', v_order.status));
    RETURN 'cancelled';
END $fn$""",
    """CREATE FUNCTION order_delete(p_order_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_order sales_order%ROWTYPE;
BEGIN
    IF NOT app_has_permission('sales_orders', 'delete') OR NOT order_visible(p_order_id) THEN
        RAISE EXCEPTION 'not permitted on this order' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO v_order FROM sales_order WHERE id = p_order_id FOR UPDATE;
    IF v_order.deleted_at IS NOT NULL THEN
        RAISE EXCEPTION 'order not found' USING ERRCODE = 'ORDNF';
    END IF;
    IF v_order.order_no IS NOT NULL THEN
        RAISE EXCEPTION 'a submitted order is cancelled, not deleted' USING ERRCODE = 'ORDSB';
    END IF;
    IF v_order.status <> 'draft' THEN
        RAISE EXCEPTION 'the order is %', v_order.status USING ERRCODE = 'ORDNS';
    END IF;
    UPDATE sales_order SET deleted_at = now(), updated_by = app_current_user_id() WHERE id = p_order_id;
    PERFORM order_quotations_release(p_order_id);
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('sales_order', p_order_id, v_order.lead_id, 'order.deleted', app_current_user_id(), '{}');
END $fn$""",
    # The status after a dispatch or a void, from the lines (FS-011 rule 17).
    f"""CREATE FUNCTION order_dispatch_status(p_order_id uuid) RETURNS order_status
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT CASE
        WHEN bool_and({_OPEN} <= 0) THEN 'dispatched'::order_status
        WHEN bool_or(l.qty - l.qty_short - {_OPEN} > 0) THEN 'partially_dispatched'::order_status
        ELSE 'approved'::order_status END
      FROM order_line l WHERE l.sales_order_id = p_order_id
$fn$""",
    # One dispatch: the payload is {{dc_no, dc_date, invoice_no, invoice_date,
    # dispatched_at, transporter, vehicle_no, lines: [{{order_line_id, qty}}]}},
    # validated for shape by the service; quantities are checked here under the
    # order lock, summed per line (edge case 9).
    f"""CREATE FUNCTION dispatch_record(p_order_id uuid, p_payload jsonb) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); v_order sales_order%ROWTYPE;
    v_dispatch uuid; v_seq int; r record;
BEGIN
    IF NOT app_has_permission('dispatch', 'create') OR NOT order_visible(p_order_id) THEN
        RAISE EXCEPTION 'not permitted to dispatch this order' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO v_order FROM sales_order WHERE id = p_order_id FOR UPDATE;
    IF v_order.status NOT IN ('approved', 'partially_dispatched') THEN
        RAISE EXCEPTION 'a % order cannot be dispatched', v_order.status USING ERRCODE = 'ORDND';
    END IF;
    PERFORM 1 FROM order_line WHERE sales_order_id = p_order_id ORDER BY id FOR UPDATE;
    FOR r IN
        SELECT (x ->> 'order_line_id')::uuid AS line_id, sum((x ->> 'qty')::numeric) AS qty
          FROM jsonb_array_elements(p_payload -> 'lines') x GROUP BY 1
    LOOP
        PERFORM 1 FROM order_line l WHERE l.id = r.line_id AND l.sales_order_id = p_order_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'line % is not on this order', r.line_id USING ERRCODE = 'DSPLN';
        END IF;
        IF r.qty > (SELECT {_OPEN} FROM order_line l WHERE l.id = r.line_id) THEN
            RAISE EXCEPTION 'line % has % open', r.line_id,
                (SELECT {_OPEN} FROM order_line l WHERE l.id = r.line_id) USING ERRCODE = 'DSPOV';
        END IF;
        IF r.qty <> round(r.qty, (SELECT uom_decimals FROM order_line WHERE id = r.line_id)) THEN
            RAISE EXCEPTION 'line % takes % decimal places', r.line_id,
                (SELECT uom_decimals FROM order_line WHERE id = r.line_id) USING ERRCODE = 'DSPPR';
        END IF;
    END LOOP;
    v_seq := v_order.dispatch_seq + 1;
    INSERT INTO dispatch (sales_order_id, dispatch_no, dc_no, dc_date, invoice_no, invoice_date,
                          dispatched_at, transporter, vehicle_no, dispatched_by)
    VALUES (p_order_id, 'D/' || v_order.order_no || '/' || v_seq,
            p_payload ->> 'dc_no', (p_payload ->> 'dc_date')::date,
            p_payload ->> 'invoice_no', (p_payload ->> 'invoice_date')::date,
            (p_payload ->> 'dispatched_at')::timestamptz,
            p_payload ->> 'transporter', p_payload ->> 'vehicle_no', v_me)
    RETURNING id INTO v_dispatch;
    INSERT INTO dispatch_line (dispatch_id, order_line_id, qty)
    SELECT v_dispatch, (x ->> 'order_line_id')::uuid, (x ->> 'qty')::numeric
      FROM jsonb_array_elements(p_payload -> 'lines') x;
    UPDATE sales_order SET dispatch_seq = v_seq, status = order_dispatch_status(p_order_id),
                           updated_by = v_me
     WHERE id = p_order_id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('sales_order', p_order_id, v_order.lead_id, 'dispatch.recorded', v_me,
            jsonb_build_object('dispatch_no', 'D/' || v_order.order_no || '/' || v_seq,
                               'lines', jsonb_array_length(p_payload -> 'lines')));
    RETURN v_dispatch;
END $fn$""",
    """CREATE FUNCTION dispatch_void(p_dispatch_id uuid, p_remark text) RETURNS order_status
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); v_order_id uuid; v_order sales_order%ROWTYPE;
    v_d dispatch%ROWTYPE; v_remark text; v_status order_status;
BEGIN
    SELECT sales_order_id INTO v_order_id FROM dispatch WHERE id = p_dispatch_id;
    IF NOT FOUND OR NOT order_visible(v_order_id) THEN
        RAISE EXCEPTION 'dispatch not found' USING ERRCODE = 'DSPNF';
    END IF;
    IF NOT app_has_permission('dispatch', 'edit') THEN
        RAISE EXCEPTION 'not permitted to void a dispatch' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO v_order FROM sales_order WHERE id = v_order_id FOR UPDATE;
    SELECT * INTO v_d FROM dispatch WHERE id = p_dispatch_id FOR UPDATE;
    IF v_d.voided_at IS NOT NULL THEN
        RAISE EXCEPTION 'the dispatch is already void' USING ERRCODE = 'DSPVD';
    END IF;
    IF v_order.status = 'closed_short' THEN
        RAISE EXCEPTION 'the order is closed' USING ERRCODE = 'ORDCL';
    END IF;
    v_remark := NULLIF(btrim(p_remark), '');
    IF v_remark IS NULL THEN
        RAISE EXCEPTION 'remark_required' USING ERRCODE = 'APRRM';
    END IF;
    UPDATE dispatch SET voided_at = now(), voided_by = v_me, void_remark = v_remark WHERE id = p_dispatch_id;
    v_status := order_dispatch_status(v_order_id);
    UPDATE sales_order SET status = v_status, updated_by = v_me WHERE id = v_order_id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('sales_order', v_order_id, v_order.lead_id, 'dispatch.voided', v_me,
            jsonb_build_object('dispatch_no', v_d.dispatch_no));
    RETURN v_status;
END $fn$""",
    # Writes the order row only; the close-short trigger writes the lines at
    # depth 2 (B-3).
    """CREATE FUNCTION order_close_short(p_order_id uuid, p_remark text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_order sales_order%ROWTYPE; v_remark text;
BEGIN
    IF NOT app_has_permission('dispatch', 'edit') OR NOT order_visible(p_order_id) THEN
        RAISE EXCEPTION 'not permitted to close this order' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO v_order FROM sales_order WHERE id = p_order_id FOR UPDATE;
    IF v_order.status NOT IN ('approved', 'partially_dispatched') THEN
        RAISE EXCEPTION 'a % order cannot be closed short', v_order.status USING ERRCODE = 'ORDND';
    END IF;
    v_remark := NULLIF(btrim(p_remark), '');
    IF v_remark IS NULL THEN
        RAISE EXCEPTION 'remark_required' USING ERRCODE = 'APRRM';
    END IF;
    UPDATE sales_order SET status = 'closed_short', closed_at = now(), close_remark = v_remark,
                           updated_by = v_me
     WHERE id = p_order_id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('sales_order', p_order_id, v_order.lead_id, 'order.closed_short', v_me, '{}');
END $fn$""",
]

GRANTED = [
    "order_visible(uuid)", "create_approval_request(text, uuid)", "record_decision(uuid, text, text)",
    "approval_queue(timestamptz, uuid, integer, boolean)", "order_submit(uuid)",
    "order_cancel(uuid, text, text)", "order_delete(uuid)", "order_quotations_claim(uuid, uuid[])",
    "dispatch_record(uuid, jsonb)", "dispatch_void(uuid, text)", "order_close_short(uuid, text)",
]
INTERNAL = [
    "approval_owner_level(uuid)", "approval_chain(text, numeric, uuid, integer)",
    "approval_step_stalled(uuid)", "approval_refusal(uuid)", "apply_approval_outcome(text, uuid, text)",
    "advance_approval(uuid)", "order_quotations_release(uuid)", "order_allocate_no(text, text)",
    "order_dispatch_status(uuid)",
]
TRIGGER_FUNCTION_SIGS = [
    "sales_order_parent_guard()", "refuse_order_insert_not_draft()", "refuse_submitted_order_edit()",
    "refuse_submitted_order_line_edit()", "order_close_short_lines()", "refuse_dispatch_line_edit()",
]
ALL_NEW_FUNCTIONS = GRANTED + INTERNAL + TRIGGER_FUNCTION_SIGS

# stand-ins until the client answers question 15.1 (GAP-122)
SEED_THRESHOLDS = """INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount)
SELECT 'sales_order', r.id, NULL, v.amount
  FROM (VALUES ('district_manager', 100000.00::numeric), ('state_manager', 500000.00), ('regional_manager', NULL)) v(code, amount)
  JOIN role r ON r.code = v.code"""

# ── lead_timeline(), once more ───────────────────────────────────────────────

_ORDER_FILTER = """           AND (entity_type <> 'quotation' OR quotation_visible(entity_id))
           AND (entity_type <> 'sales_order' OR order_visible(entity_id))"""


def _012() -> object:
    path = Path(__file__).with_name("012_quotations.py")
    spec = importlib.util.spec_from_file_location("mig_012_for_013", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _timeline_012() -> str:
    return _012()._replaced_006()[1]  # type: ignore[attr-defined]


def _timeline_013() -> str:
    old = _timeline_012()
    line = "           AND (entity_type <> 'quotation' OR quotation_visible(entity_id))"
    assert line in old, "012's lead_timeline() reads as expected"
    return old.replace(line, _ORDER_FILTER)


def _activity_012() -> str:
    return next(s for t, s in _012().HAND_POLICIES if t == "activity_event")  # type: ignore[attr-defined]


def _hand(table: str) -> None:
    for t, stmt in HAND_POLICIES:
        if t == table:
            op.execute(stmt)


def upgrade() -> None:
    for stmt in ENUMS + TABLES_SQL + GENERATED_INDEXES + HAND_INDEXES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")

    for stmt in ORDER_POLICIES + PARENT_GUARD[:1]:
        op.execute(stmt)
    for table in ("order_line", "order_quotation", "approval_request", "approval_step",
                  "approval_threshold", "dispatch", "dispatch_line"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        _hand(table)
    # the counter carries no grant and no policy: the definer allocator writes it
    op.execute("ALTER TABLE order_counter ENABLE ROW LEVEL SECURITY")

    for stmt in FUNCTIONS[:1]:  # order_visible, which the trigger functions do not need
        op.execute(stmt)
    for stmt in TRIGGER_FUNCTIONS + TRIGGERS:
        op.execute(stmt)
    for stmt in FUNCTIONS[1:]:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    op.execute(SEED_THRESHOLDS)

    op.execute(_timeline_013())
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    _hand("activity_event")

    # New functions are PUBLIC-executable until this runs.
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(_activity_012())
    op.execute(_timeline_012())
    op.execute("DELETE FROM activity_event WHERE entity_type = 'sales_order'")
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for sig in ALL_NEW_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    for name in ("approval_decision", "approval_status", "order_payment_terms", "order_status", "order_type"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
