"""019: complaints, from entry to the quality check (FS-015).

- `complaint_type` (a lookup, admin-edited) and `complaint_sla_policy` (targets in
  working hours, effective-dated, two partial exclusion constraints: plan review
  B-5).
- `complaint` with its lines, decisions (and staff-only decision notes),
  attachments and a per-state, per-year counter. The `complaints` ScopeSpec
  generates the policies, indexes and parent guard pasted below; the drift test
  regenerates and compares.
- Definers for every write a caller's RLS cannot make (ADR-042, not the approval
  engine): `complaint_submit`, `complaint_check`, `complaint_qc`,
  `complaint_cancel`, the SLA policy writer; `complaint_refusal` is the one rule
  for who may do what, read by the definers, `can` and the queue.
- `complaint_add_working_hours`: the SQL twin of `api/domain/complaints.py`; a
  test compares them.
- `lead_timeline()` hides complaint events a reader cannot see; `people_names()`
  names a complaint's owner and raiser, and its deciders to staff only.
- `activity_event`'s read policy gains the `complaint` arm.
- Two message keys, seeded off until 11za approves their templates (GAP-153).

Revision ID: 019_complaints
Revises: 018_tasks_planner
"""

# ruff: noqa: E501  (generated and embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "019_complaints"
down_revision: str | None = "018_tasks_planner"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"  # 005
INTAKE_USER_ID = "3f962ae5-f0d3-5583-91b5-5cea037139fc"  # 015
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id)"""

ENUMS = [
    "CREATE TYPE complaint_status AS ENUM ('draft', 'submitted', 'under_qc', 'qc_approved', 'qc_rejected', 'cancelled')",
    "CREATE TYPE complaint_severity AS ENUM ('low', 'medium', 'high')",
]

TABLES_SQL = [
    f"""CREATE TABLE complaint_type (
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
    f"""CREATE TABLE complaint (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_no citext UNIQUE,
    status complaint_status NOT NULL DEFAULT 'draft',
    complaint_type_id uuid NOT NULL REFERENCES complaint_type(id),
    severity complaint_severity NOT NULL DEFAULT 'medium',
    description text NOT NULL CHECK (length(btrim(description)) BETWEEN 1 AND 2000),
    contact_name text NOT NULL CHECK (length(btrim(contact_name)) BETWEEN 1 AND 120),
    contact_mobile text NOT NULL CHECK (contact_mobile ~ '^[+]91[6-9][0-9]{{9}}$'),
    territory_id uuid NOT NULL REFERENCES territory(id),
    state_code text NOT NULL CHECK (state_code ~ '^[A-Z0-9]{{1,10}}$'),
    partner_id uuid REFERENCES channel_partner(id),
    lead_id uuid REFERENCES lead(id),
    sales_order_id uuid REFERENCES sales_order(id),
    owner_user_id uuid REFERENCES app_user(id),
    owner_org_unit_id uuid NOT NULL REFERENCES org_unit(id),
    raised_by uuid NOT NULL REFERENCES app_user(id),
    dc_no text CHECK (dc_no IS NULL OR length(btrim(dc_no)) BETWEEN 1 AND 60),
    supply_date date,
    reg_no text CHECK (reg_no IS NULL OR length(reg_no) <= 60),
    pims_no text CHECK (pims_no IS NULL OR length(pims_no) <= 60),
    sample_courier_date date,
    sample_courier_detail text CHECK (sample_courier_detail IS NULL OR length(sample_courier_detail) <= 500),
    submit_count int NOT NULL DEFAULT 0 CHECK (submit_count >= 0),
    submitted_at timestamptz,
    first_submitted_at timestamptz,
    responded_at timestamptz,
    resolved_at timestamptz,
    response_due_at timestamptz,
    resolution_due_at timestamptz,
    deleted_at timestamptz,
    {AUDIT},
    CONSTRAINT ck_complaint_numbered CHECK ((submit_count = 0) = (complaint_no IS NULL)),
    CONSTRAINT ck_complaint_first_submit CHECK ((submit_count = 0) = (first_submitted_at IS NULL)),
    CONSTRAINT ck_complaint_delete_draft CHECK (deleted_at IS NULL OR submit_count = 0)
)""",
    """CREATE TABLE complaint_line (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id uuid NOT NULL REFERENCES complaint(id),
    line_no int NOT NULL CHECK (line_no BETWEEN 1 AND 20),
    product_id uuid NOT NULL REFERENCES product(id),
    uom text,
    supplied_qty numeric(14,3) NOT NULL CHECK (supplied_qty > 0),
    defective_qty numeric(14,3) NOT NULL CHECK (defective_qty >= 0 AND defective_qty <= supplied_qty),
    failure_frequency text CHECK (failure_frequency IS NULL OR length(failure_frequency) <= 200),
    remark text CHECK (remark IS NULL OR length(remark) <= 500),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_complaint_line_product UNIQUE (complaint_id, product_id),
    CONSTRAINT uq_complaint_line_no UNIQUE (complaint_id, line_no)
)""",
    """CREATE TABLE complaint_decision (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id uuid NOT NULL REFERENCES complaint(id),
    stage text NOT NULL CHECK (stage IN ('check', 'qc', 'cancel')),
    decision text NOT NULL,
    remark text NOT NULL CHECK (length(btrim(remark)) BETWEEN 1 AND 2000),
    severity_before complaint_severity,
    severity_after complaint_severity,
    sample_received_on date,
    tested_on date,
    field_visit_on date,
    submit_no int NOT NULL,
    decided_by uuid NOT NULL REFERENCES app_user(id),
    decided_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_complaint_decision_pair CHECK (
        (stage = 'check' AND decision IN ('approve', 'return'))
        OR (stage = 'qc' AND decision IN ('approved', 'rejected'))
        OR (stage = 'cancel' AND decision = 'cancelled'))
)""",
    """CREATE TABLE complaint_decision_note (
    decision_id uuid PRIMARY KEY REFERENCES complaint_decision(id),
    internal_note text NOT NULL CHECK (length(btrim(internal_note)) BETWEEN 1 AND 2000)
)""",
    f"""CREATE TABLE complaint_attachment (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id uuid NOT NULL REFERENCES complaint(id),
    kind text NOT NULL CHECK (kind IN ('photo', 'document', 'challan')),
    storage_key text NOT NULL UNIQUE,
    filename text NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
    content_type text NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp', 'image/heic', 'application/pdf')),
    size_bytes int NOT NULL CHECK (size_bytes > 0 AND size_bytes <= {MAX_UPLOAD_BYTES}),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
    uploaded_by uuid NOT NULL REFERENCES app_user(id),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    deleted_by uuid REFERENCES app_user(id),
    CONSTRAINT ck_complaint_attachment_deleted CHECK ((deleted_at IS NULL) = (deleted_by IS NULL))
)""",
    """CREATE TABLE complaint_counter (
    state_code text NOT NULL,
    financial_year text NOT NULL,
    last_value int NOT NULL,
    PRIMARY KEY (state_code, financial_year)
)""",
    """CREATE TABLE complaint_sla_policy (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    severity complaint_severity NOT NULL,
    complaint_type_id uuid REFERENCES complaint_type(id),
    response_hours int NOT NULL CHECK (response_hours BETWEEN 1 AND 8760),
    resolution_hours int NOT NULL CHECK (resolution_hours BETWEEN 1 AND 8760 AND resolution_hours >= response_hours),
    business_hours_only boolean NOT NULL DEFAULT true,
    effective_from date NOT NULL,
    effective_to date,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES app_user(id),
    CONSTRAINT ck_complaint_sla_policy_dates CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_complaint_sla_policy_untyped EXCLUDE USING gist (
        severity WITH =, daterange(effective_from, effective_to, '[)') WITH &&)
        WHERE (complaint_type_id IS NULL),
    CONSTRAINT ex_complaint_sla_policy_typed EXCLUDE USING gist (
        severity WITH =, complaint_type_id WITH =, daterange(effective_from, effective_to, '[)') WITH &&)
        WHERE (complaint_type_id IS NOT NULL)
)""",
    "CREATE TRIGGER trg_complaint_updated_at BEFORE UPDATE ON complaint FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_complaint_type_updated_at BEFORE UPDATE ON complaint_type FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_complaint_type_audit AFTER INSERT OR UPDATE OR DELETE ON complaint_type FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

SEED = [
    """INSERT INTO complaint_type (code, name, sort_order) VALUES
    ('short_material', 'Short Material', 1), ('dripline', 'Dripline / Lateral / PVC', 2),
    ('components', 'Components', 3), ('oem_components', 'OEM''s Components', 4),
    ('material_handling', 'Material Handling', 5)""",
    # stand-ins in hours, a working day is 9 (GAP-147)
    """INSERT INTO complaint_sla_policy (severity, response_hours, resolution_hours, business_hours_only, effective_from) VALUES
    ('high', 4, 18, true, DATE '2026-04-01'), ('medium', 8, 27, true, DATE '2026-04-01'),
    ('low', 9, 45, true, DATE '2026-04-01')""",
    # off until 11za approves them; scripts/sync_message_templates.py switches them on
    """INSERT INTO message_template (key, provider_name, enabled) VALUES
    ('complaint.registered', 'polysil_complaint_registered', false),
    ('complaint.updated', 'polysil_complaint_update', false)
    ON CONFLICT (key) DO NOTHING""",
]

# Generated by policy_sql.policies_for(SPECS["complaints"]) and pasted.
COMPLAINT_POLICIES = [
    'ALTER TABLE complaint ENABLE ROW LEVEL SECURITY',
    "CREATE POLICY complaint_sel_own ON complaint FOR SELECT USING (\n  (SELECT app_scope('complaints')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id())\n)",
    "CREATE POLICY complaint_sel_org_subtree ON complaint FOR SELECT USING (\n  (SELECT app_scope('complaints')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))\n)",
    "CREATE POLICY complaint_sel_partner_subtree ON complaint FOR SELECT USING (\n  (SELECT app_scope('complaints')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))\n)",
    "CREATE POLICY complaint_sel_global ON complaint FOR SELECT USING (\n  (SELECT app_scope('complaints')) = 'global'\n)",
    "CREATE POLICY complaint_res_perm ON complaint AS RESTRICTIVE FOR SELECT USING (\n  (SELECT app_has_permission('complaints', 'view'))\n)",
    "CREATE POLICY complaint_res_deleted ON complaint AS RESTRICTIVE FOR SELECT USING (\n  deleted_at IS NULL OR (SELECT app_has_permission('complaints', 'delete'))\n)",
    "CREATE POLICY complaint_ins ON complaint FOR INSERT WITH CHECK (\n  (((SELECT app_scope('complaints')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('complaints')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('complaints')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('complaints')) = 'global'))\n  AND (lead_id IS NULL OR EXISTS (SELECT 1 FROM lead p WHERE p.id = lead_id))\n  AND (sales_order_id IS NULL OR EXISTS (SELECT 1 FROM sales_order p WHERE p.id = sales_order_id))\n  AND (partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id))\n  AND (owner_org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = owner_org_unit_id))\n  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))\n)",
    "CREATE POLICY complaint_ins_perm ON complaint AS RESTRICTIVE FOR INSERT WITH CHECK (\n  (SELECT app_has_permission('complaints', 'create'))\n)",
    "CREATE POLICY complaint_upd ON complaint FOR UPDATE USING (\n  ((SELECT app_scope('complaints')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('complaints')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('complaints')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('complaints')) = 'global')\n) WITH CHECK (\n  ((SELECT app_scope('complaints')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('complaints')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('complaints')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('complaints')) = 'global')\n)",
    "CREATE POLICY complaint_upd_perm ON complaint AS RESTRICTIVE FOR UPDATE USING (\n  (SELECT app_has_permission('complaints', 'edit'))\n)",
    "CREATE POLICY complaint_del ON complaint FOR DELETE USING (\n  ((SELECT app_scope('complaints')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('complaints')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('complaints')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('complaints')) = 'global')\n)",
    "CREATE POLICY complaint_del_perm ON complaint AS RESTRICTIVE FOR DELETE USING (\n  (SELECT app_has_permission('complaints', 'delete'))\n)",
]

GENERATED_INDEXES = [
    'CREATE INDEX IF NOT EXISTS ix_complaint_owner_user_id ON complaint (owner_user_id)',
    'CREATE INDEX IF NOT EXISTS ix_complaint_owner_org_unit_id ON complaint (owner_org_unit_id)',
    'CREATE INDEX IF NOT EXISTS ix_complaint_partner_id ON complaint (partner_id)',
    'CREATE INDEX IF NOT EXISTS ix_complaint_deleted_at_live ON complaint (deleted_at) WHERE deleted_at IS NULL',
    'CREATE INDEX IF NOT EXISTS ix_complaint_lead_id ON complaint (lead_id)',
    'CREATE INDEX IF NOT EXISTS ix_complaint_sales_order_id ON complaint (sales_order_id)',
    'CREATE INDEX IF NOT EXISTS ix_complaint_territory_id ON complaint (territory_id)',
]

PARENT_GUARD = [
    "CREATE FUNCTION complaint_parent_guard() RETURNS trigger\n        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$\n        BEGIN\n            IF NEW.lead_id IS DISTINCT FROM OLD.lead_id AND NEW.lead_id IS NOT NULL\n               AND NOT authz_visible('lead', NEW.lead_id) THEN\n                RAISE EXCEPTION 'lead_id % is not in your scope', NEW.lead_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.sales_order_id IS DISTINCT FROM OLD.sales_order_id AND NEW.sales_order_id IS NOT NULL\n               AND NOT authz_visible('sales_order', NEW.sales_order_id) THEN\n                RAISE EXCEPTION 'sales_order_id % is not in your scope', NEW.sales_order_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.partner_id IS DISTINCT FROM OLD.partner_id AND NEW.partner_id IS NOT NULL\n               AND NOT authz_visible('channel_partner', NEW.partner_id) THEN\n                RAISE EXCEPTION 'partner_id % is not in your scope', NEW.partner_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.owner_org_unit_id IS DISTINCT FROM OLD.owner_org_unit_id AND NEW.owner_org_unit_id IS NOT NULL\n               AND NOT authz_visible('org_unit', NEW.owner_org_unit_id) THEN\n                RAISE EXCEPTION 'owner_org_unit_id % is not in your scope', NEW.owner_org_unit_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.territory_id IS DISTINCT FROM OLD.territory_id AND NEW.territory_id IS NOT NULL\n               AND NOT authz_visible('territory', NEW.territory_id) THEN\n                RAISE EXCEPTION 'territory_id % is not in your scope', NEW.territory_id\n                    USING ERRCODE = '42501';\n            END IF;\n            RETURN NEW;\n        END $fn$",
    'CREATE TRIGGER trg_complaint_parent_guard\n            BEFORE UPDATE OF lead_id, sales_order_id, partner_id, owner_org_unit_id, territory_id ON complaint\n            FOR EACH ROW EXECUTE FUNCTION complaint_parent_guard()',
]

_COMPLAINT_GUARD = "(((SELECT app_scope('complaints')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('complaints')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('complaints')) = 'partner_subtree'\n  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))\n  OR ((SELECT app_scope('complaints')) = 'global'))\n  AND ((SELECT app_has_permission('complaints', 'view')))\n  AND (deleted_at IS NULL OR (SELECT app_has_permission('complaints', 'delete')))"

_EDITABLE = 'complaint_type_id, severity, description, contact_name, contact_mobile, territory_id, state_code, partner_id, lead_id, sales_order_id, dc_no, supply_date, reg_no, pims_no, sample_courier_date, sample_courier_detail, deleted_at, updated_by'
_INSERTABLE = 'complaint_type_id, severity, description, contact_name, contact_mobile, territory_id, state_code, partner_id, lead_id, sales_order_id, dc_no, supply_date, reg_no, pims_no, sample_courier_date, sample_courier_detail, deleted_at, updated_by, owner_user_id, owner_org_unit_id, raised_by, created_by'

ACTIVITY_POLICY = "CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (\n  CASE entity_type\n    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)\n    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)\n    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)\n    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)\n    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)\n    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)\n    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order c WHERE c.id = entity_id)\n    WHEN 'lead_qr_code' THEN EXISTS (SELECT 1 FROM lead_qr_code c WHERE c.id = entity_id)\n    WHEN 'task' THEN EXISTS (SELECT 1 FROM task c WHERE c.id = entity_id)\n    WHEN 'meeting_minutes' THEN EXISTS (SELECT 1 FROM meeting_minutes c WHERE c.id = entity_id)\n    WHEN 'complaint' THEN EXISTS (SELECT 1 FROM complaint c WHERE c.id = entity_id)\n    ELSE (SELECT app_is_system())\n  END\n)"

HAND_INDEXES = [
    "CREATE INDEX ix_complaint_line_complaint ON complaint_line (complaint_id)",
    "CREATE INDEX ix_complaint_decision_complaint ON complaint_decision (complaint_id)",
    "CREATE INDEX ix_complaint_decision_decided_by ON complaint_decision (decided_by)",
    "CREATE INDEX ix_complaint_attachment_complaint ON complaint_attachment (complaint_id) WHERE deleted_at IS NULL",
    "CREATE INDEX ix_complaint_attachment_uploaded_by ON complaint_attachment (uploaded_by)",
    "CREATE UNIQUE INDEX uq_complaint_attachment_hash ON complaint_attachment (complaint_id, sha256) WHERE deleted_at IS NULL",
    "CREATE INDEX ix_complaint_raised_by ON complaint (raised_by)",
    "CREATE INDEX ix_complaint_queue ON complaint (status, first_submitted_at)",
    "CREATE INDEX ix_complaint_lead ON complaint (lead_id) WHERE lead_id IS NOT NULL",
    "CREATE INDEX ix_complaint_order ON complaint (sales_order_id) WHERE sales_order_id IS NOT NULL",
    "CREATE INDEX ix_complaint_sla_policy_type ON complaint_sla_policy (complaint_type_id)",
]

_C_VIEW = "(SELECT app_has_permission('complaints', 'view'))"
_C_EDIT = "(SELECT app_has_permission('complaints', 'edit'))"
_C_WRITE = "((SELECT app_has_permission('complaints', 'edit')) OR (SELECT app_has_permission('complaints', 'create')))"
_PARENT = "EXISTS (SELECT 1 FROM complaint c WHERE c.id = complaint_id)"
_ME = "(SELECT app_current_user_id())"

HAND_POLICIES: list[tuple[str, str]] = [
    # a lookup, like meeting_type: everyone signed in reads, masters.edit writes
    ("complaint_type", "CREATE POLICY complaint_type_sel ON complaint_type FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"),
    ("complaint_type", "CREATE POLICY complaint_type_ins ON complaint_type FOR INSERT WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"),
    ("complaint_type", "CREATE POLICY complaint_type_upd ON complaint_type FOR UPDATE USING ((SELECT app_has_permission('masters', 'edit'))) WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"),
    ("complaint_sla_policy", "CREATE POLICY complaint_sla_policy_sel ON complaint_sla_policy FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"),
    # the lines follow their complaint; the trigger narrows every write to a draft
    ("complaint_line", f"CREATE POLICY complaint_line_sel ON complaint_line FOR SELECT USING (\n  {_PARENT}\n)"),
    ("complaint_line", f"CREATE POLICY complaint_line_res_perm ON complaint_line AS RESTRICTIVE FOR SELECT USING (\n  {_C_VIEW}\n)"),
    ("complaint_line", f"CREATE POLICY complaint_line_ins ON complaint_line FOR INSERT WITH CHECK (\n  {_PARENT}\n)"),
    ("complaint_line", f"CREATE POLICY complaint_line_ins_perm ON complaint_line AS RESTRICTIVE FOR INSERT WITH CHECK (\n  {_C_WRITE}\n)"),
    ("complaint_line", f"CREATE POLICY complaint_line_del ON complaint_line FOR DELETE USING (\n  {_PARENT}\n)"),
    ("complaint_line", f"CREATE POLICY complaint_line_del_perm ON complaint_line AS RESTRICTIVE FOR DELETE USING (\n  {_C_WRITE}\n)"),
    # decisions are read through the complaint and written by the definers only
    ("complaint_decision", f"CREATE POLICY complaint_decision_sel ON complaint_decision FOR SELECT USING (\n  {_PARENT}\n)"),
    ("complaint_decision", f"CREATE POLICY complaint_decision_res_perm ON complaint_decision AS RESTRICTIVE FOR SELECT USING (\n  {_C_VIEW}\n)"),
    # the internal note never reaches a partner claim (EC-13)
    ("complaint_decision_note", "CREATE POLICY complaint_decision_note_sel ON complaint_decision_note FOR SELECT USING (\n  (SELECT app_current_partner()) IS NULL\n  AND EXISTS (SELECT 1 FROM complaint_decision d WHERE d.id = decision_id)\n)"),
    # attachments: read through the complaint; added by whoever may write it, as
    # themselves; removed by the uploader or an editor (the service narrows by status)
    ("complaint_attachment", f"CREATE POLICY complaint_attachment_sel ON complaint_attachment FOR SELECT USING (\n  {_PARENT}\n)"),
    ("complaint_attachment", f"CREATE POLICY complaint_attachment_res_perm ON complaint_attachment AS RESTRICTIVE FOR SELECT USING (\n  {_C_VIEW}\n)"),
    ("complaint_attachment", f"CREATE POLICY complaint_attachment_ins ON complaint_attachment FOR INSERT WITH CHECK (\n  {_PARENT}\n  AND uploaded_by = {_ME}\n)"),
    ("complaint_attachment", f"CREATE POLICY complaint_attachment_ins_perm ON complaint_attachment AS RESTRICTIVE FOR INSERT WITH CHECK (\n  {_C_WRITE} OR (SELECT app_has_permission('complaints', 'approve'))\n)"),
    ("complaint_attachment", f"CREATE POLICY complaint_attachment_upd ON complaint_attachment FOR UPDATE USING (\n  {_PARENT}\n  AND (uploaded_by = {_ME} OR {_C_EDIT})\n) WITH CHECK (\n  deleted_by = {_ME}\n)"),
    ("activity_event", ACTIVITY_POLICY),
]

GRANTS: dict[str, str] = {
    "complaint": f"SELECT, INSERT ({_INSERTABLE}), UPDATE ({_EDITABLE})",
    "complaint_line": "SELECT, INSERT, DELETE",
    "complaint_attachment": "SELECT, INSERT, UPDATE (deleted_at, deleted_by)",
    "complaint_decision": "SELECT",
    "complaint_decision_note": "SELECT",
    "complaint_type": "SELECT, INSERT, UPDATE",
    "complaint_sla_policy": "SELECT",
}

# ── functions ────────────────────────────────────────────────────────────────

# Messages in the complainant's words; never the internal status names (EC-14).
_WORDS = {"approve": "passed to our quality team", "return": "returned to the person who raised it",
          "approved": "approved by our quality team", "rejected": "not accepted by our quality team"}

FUNCTIONS = [
    f"""CREATE FUNCTION complaint_visible(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM complaint WHERE id = p_id AND (
{_COMPLAINT_GUARD}
    ))
$fn$""",
    # the SQL twin of api/domain/complaints.add_working_hours; a test compares them
    """CREATE FUNCTION complaint_add_working_hours(p_start timestamptz, p_hours int) RETURNS timestamptz
LANGUAGE plpgsql IMMUTABLE SET search_path = public, pg_temp AS $fn$
DECLARE
    t timestamp := p_start AT TIME ZONE 'Asia/Kolkata';
    remaining interval := make_interval(hours => p_hours);
    e timestamp;
BEGIN
    LOOP
        LOOP
            e := t::date + time '18:30';
            IF extract(isodow FROM t::date) <> 7 AND t < e THEN
                t := greatest(t, t::date + time '09:30');
                EXIT;
            END IF;
            t := (t::date + 1) + time '09:30';
        END LOOP;
        e := t::date + time '18:30';
        IF t + remaining <= e THEN
            RETURN (t + remaining) AT TIME ZONE 'Asia/Kolkata';
        END IF;
        remaining := remaining - (e - t);
        t := e;
    END LOOP;
END $fn$""",
    """CREATE FUNCTION complaint_sla_policy_at(p_type uuid, p_severity complaint_severity, p_day date)
RETURNS complaint_sla_policy
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT * FROM complaint_sla_policy
     WHERE severity = p_severity AND (complaint_type_id = p_type OR complaint_type_id IS NULL)
       AND effective_from <= p_day AND (effective_to IS NULL OR effective_to > p_day)
     ORDER BY complaint_type_id NULLS LAST LIMIT 1
$fn$""",
    """CREATE FUNCTION complaint_due(p_from timestamptz, p_hours int, p_business boolean) RETURNS timestamptz
LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp AS $fn$
    SELECT CASE WHEN p_hours IS NULL THEN NULL
                WHEN p_business THEN complaint_add_working_hours(p_from, p_hours)
                ELSE p_from + make_interval(hours => p_hours) END
$fn$""",
    """CREATE FUNCTION complaint_allocate_no(p_state_code text, p_fy text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    INSERT INTO complaint_counter (state_code, financial_year, last_value)
    VALUES (p_state_code, p_fy, 1)
    ON CONFLICT (state_code, financial_year)
    DO UPDATE SET last_value = complaint_counter.last_value + 1
    RETURNING last_value INTO v_n;
    RETURN 'Poly/Comp./' || p_fy || '/' || p_state_code || '/'
           || lpad(v_n::text, greatest(2, length(v_n::text)), '0');
END $fn$""",
    # Why the caller may not act, or null (ADR-042, rules 6 to 8). One rule for the
    # definers, `can` and the queue (approval_refusal()'s shape).
    """CREATE FUNCTION complaint_refusal(p_id uuid, p_action text) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id();
    c complaint%ROWTYPE;
    v_level int; v_line boolean; v_functional boolean; v_ref int;
BEGIN
    SELECT * INTO c FROM complaint WHERE id = p_id AND deleted_at IS NULL;
    IF c.id IS NULL OR NOT complaint_visible(p_id) THEN
        RETURN 'not_visible';
    END IF;
    SELECT r.level, NOT r.is_functional AND NOT r.is_portal, r.is_functional AND NOT r.is_portal
      INTO v_level, v_line, v_functional
      FROM app_user u JOIN role r ON r.id = u.role_id WHERE u.id = v_me;
    IF p_action = 'submit' THEN
        IF c.status <> 'draft' THEN RETURN 'not_draft'; END IF;
        IF v_me IN (c.raised_by, c.owner_user_id) OR app_has_permission('complaints', 'edit') THEN
            RETURN NULL;
        END IF;
        RETURN 'not_yours';
    ELSIF p_action = 'cancel' THEN
        IF c.status NOT IN ('draft', 'submitted') THEN RETURN 'not_open'; END IF;
        IF v_me IN (c.raised_by, c.owner_user_id) OR app_has_permission('complaints', 'delete') THEN
            RETURN NULL;
        END IF;
        RETURN 'not_yours';
    ELSIF p_action = 'check' THEN
        IF c.status <> 'submitted' THEN RETURN 'not_submitted'; END IF;
        IF NOT app_has_permission('complaints', 'approve') OR NOT COALESCE(v_line, false) THEN
            RETURN 'not_a_manager';
        END IF;
        IF v_me IN (c.raised_by, c.owner_user_id) THEN RETURN 'self'; END IF;
        v_ref := COALESCE(approval_owner_level(c.owner_user_id), 0);
        IF (v_ref >= 5 AND v_level >= 5) OR v_level > v_ref THEN
            RETURN NULL;
        END IF;
        RETURN 'not_above';
    ELSIF p_action = 'qc' THEN
        IF c.status <> 'under_qc' THEN RETURN 'not_under_qc'; END IF;
        IF NOT app_has_permission('complaints', 'approve') OR NOT COALESCE(v_functional, false) THEN
            RETURN 'not_qc';
        END IF;
        IF v_me IN (c.raised_by, c.owner_user_id) THEN RETURN 'self'; END IF;
        RETURN NULL;
    END IF;
    RAISE EXCEPTION 'unknown complaint action %', p_action USING ERRCODE = '22023';
END $fn$""",
    # rule 6's `no_checker`: someone active who would pass the check, by the org
    # closure (approval_step_stalled()'s form), not by swapping the claim
    """CREATE FUNCTION complaint_has_checker(p_id uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE c complaint%ROWTYPE; v_ref int;
BEGIN
    SELECT * INTO c FROM complaint WHERE id = p_id;
    v_ref := COALESCE(approval_owner_level(c.owner_user_id), 0);
    RETURN EXISTS (
        SELECT 1 FROM app_user u JOIN role r ON r.id = u.role_id
          JOIN role_permission ap ON ap.role_id = r.id AND ap.module = 'complaints'
                                 AND ap.action = 'approve' AND ap.deleted_at IS NULL
          JOIN role_permission vp ON vp.role_id = r.id AND vp.module = 'complaints'
                                 AND vp.action = 'view' AND vp.deleted_at IS NULL
         WHERE u.is_active AND u.deleted_at IS NULL AND u.user_type = 'staff'
           AND NOT r.is_functional AND NOT r.is_portal
           AND u.id <> c.raised_by AND u.id IS DISTINCT FROM c.owner_user_id
           AND ((v_ref >= 5 AND r.level >= 5) OR r.level > v_ref)
           AND (vp.scope = 'global'
                OR (vp.scope = 'org_subtree' AND EXISTS (
                      SELECT 1 FROM org_closure oc
                       WHERE oc.ancestor_id = u.org_unit_id AND oc.descendant_id = c.owner_org_unit_id))));
END $fn$""",
    # the owner picker and the check's assignee rule (B-6): active staff holding
    # complaints.edit in the checker's office tree, or anywhere for a global checker
    f"""CREATE FUNCTION complaint_assignees(p_id uuid)
RETURNS TABLE (id uuid, full_name text, org_unit_id uuid)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_scope text := app_scope('complaints'); v_org uuid := app_current_org_unit();
BEGIN
    IF complaint_refusal(p_id, 'check') IS NOT NULL THEN
        RAISE EXCEPTION 'not your check' USING ERRCODE = '42501';
    END IF;
    RETURN QUERY
        SELECT u.id, u.full_name::text, u.org_unit_id FROM app_user u
          JOIN role_permission ep ON ep.role_id = u.role_id AND ep.module = 'complaints'
                                 AND ep.action = 'edit' AND ep.deleted_at IS NULL
         WHERE u.is_active AND u.deleted_at IS NULL AND u.user_type = 'staff'
           AND u.id NOT IN ('{SYSTEM_USER_ID}', '{INTAKE_USER_ID}')
           AND (v_scope = 'global' OR u.org_unit_id IN (
                  SELECT descendant_id FROM org_closure WHERE ancestor_id = v_org))
         ORDER BY u.full_name, u.id;
END $fn$""",
    # the WhatsApp to the complainant, only when its template is switched on
    """CREATE FUNCTION complaint_notify(p_id uuid, p_key text, p_status text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE c complaint%ROWTYPE; v_tpl text;
BEGIN
    SELECT provider_name INTO v_tpl FROM message_template
     WHERE key = p_key AND enabled AND provider_name IS NOT NULL;
    IF v_tpl IS NULL THEN
        RETURN;
    END IF;
    SELECT * INTO c FROM complaint WHERE id = p_id;
    INSERT INTO notification_outbox (channel, template_key, recipient, payload)
    VALUES ('whatsapp', p_key, c.contact_mobile,
            jsonb_build_object('_template', v_tpl, 'contact_name', c.contact_name,
                               'complaint_no', c.complaint_no, 'status', p_status));
END $fn$""",
    """CREATE FUNCTION complaint_event(p_id uuid, p_kind text, p_payload jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_name text; v_lead uuid;
BEGIN
    SELECT full_name INTO v_name FROM app_user WHERE id = v_me;
    SELECT lead_id INTO v_lead FROM complaint WHERE id = p_id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('complaint', p_id, v_lead, p_kind, v_me,
            jsonb_build_object('actor_name', COALESCE(v_name, '')) || COALESCE(p_payload, '{}'));
END $fn$""",
    # The submit (rules 2, 5, 6, 9): lock, the one rule, the form, the number on the
    # first submit only, the targets from the policy of the first submit's IST date.
    """CREATE FUNCTION complaint_submit(p_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    c complaint%ROWTYPE; v_why text; v_missing text[] := '{}';
    v_day date; v_y int; v_fy text; v_no text; v_first timestamptz; p complaint_sla_policy%ROWTYPE;
BEGIN
    SELECT * INTO c FROM complaint WHERE id = p_id AND deleted_at IS NULL FOR UPDATE;
    v_why := complaint_refusal(p_id, 'submit');
    IF v_why = 'not_visible' THEN
        RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'CMPNF';
    ELSIF v_why = 'not_draft' THEN
        RAISE EXCEPTION 'the complaint moved on' USING ERRCODE = 'CMPSC';
    ELSIF v_why IS NOT NULL THEN
        RAISE EXCEPTION '%', v_why USING ERRCODE = 'CMPRF';
    END IF;
    IF c.dc_no IS NULL THEN v_missing := v_missing || 'dc_no'::text; END IF;
    IF c.supply_date IS NULL THEN v_missing := v_missing || 'supply_date'::text; END IF;
    IF NOT EXISTS (SELECT 1 FROM complaint_line WHERE complaint_id = p_id) THEN
        v_missing := v_missing || 'lines'::text;
    END IF;
    IF cardinality(v_missing) > 0 THEN
        RAISE EXCEPTION '%', array_to_string(v_missing, ',') USING ERRCODE = 'CMPMS';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM complaint_line WHERE complaint_id = p_id AND defective_qty > 0) THEN
        RAISE EXCEPTION 'nothing defective' USING ERRCODE = 'CMPZD';
    END IF;
    IF NOT complaint_has_checker(p_id) THEN
        RAISE EXCEPTION 'nobody may check this complaint' USING ERRCODE = 'CMPNC';
    END IF;
    -- one statement: the number and the count are held together by a CHECK
    IF c.submit_count = 0 THEN
        v_first := now();
        v_day := (v_first AT TIME ZONE 'Asia/Kolkata')::date;
        v_y := CASE WHEN extract(month FROM v_day) >= 4 THEN extract(year FROM v_day)::int
                    ELSE extract(year FROM v_day)::int - 1 END;
        v_fy := v_y || '-' || lpad(((v_y + 1) % 100)::text, 2, '0');
        v_no := complaint_allocate_no(c.state_code, v_fy);
        p := complaint_sla_policy_at(c.complaint_type_id, c.severity, v_day);
        UPDATE complaint SET complaint_no = v_no, first_submitted_at = v_first,
               response_due_at = complaint_due(v_first, p.response_hours, p.business_hours_only),
               resolution_due_at = complaint_due(v_first, p.resolution_hours, p.business_hours_only),
               status = 'submitted', submitted_at = now(), submit_count = 1,
               updated_by = app_current_user_id()
         WHERE id = p_id;
    ELSE
        p := complaint_sla_policy_at(c.complaint_type_id, c.severity,
                                     (c.first_submitted_at AT TIME ZONE 'Asia/Kolkata')::date);
        UPDATE complaint SET status = 'submitted', submitted_at = now(), submit_count = submit_count + 1,
               response_due_at = complaint_due(c.first_submitted_at, p.response_hours, p.business_hours_only),
               resolution_due_at = complaint_due(c.first_submitted_at, p.resolution_hours, p.business_hours_only),
               updated_by = app_current_user_id()
         WHERE id = p_id;
    END IF;
    SELECT * INTO c FROM complaint WHERE id = p_id;
    PERFORM complaint_event(p_id, 'complaint.submitted',
                            jsonb_build_object('complaint_no', c.complaint_no, 'submit_no', c.submit_count));
    IF c.submit_count = 1 THEN
        PERFORM complaint_notify(p_id, 'complaint.registered', 'registered');
    END IF;
END $fn$""",
    # The manager check (rule 6). Owner and severity only on approve; a severity
    # change recomputes both targets from the first submit, with that day's policy.
    f"""CREATE FUNCTION complaint_check(p_id uuid, p_decision text, p_remark text,
                                p_severity complaint_severity, p_owner uuid, p_note text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE c complaint%ROWTYPE; v_why text; v_decision uuid; p complaint_sla_policy%ROWTYPE; v_sev complaint_severity;
BEGIN
    SELECT * INTO c FROM complaint WHERE id = p_id AND deleted_at IS NULL FOR UPDATE;
    v_why := complaint_refusal(p_id, 'check');
    IF v_why = 'not_visible' THEN
        RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'CMPNF';
    ELSIF v_why = 'not_submitted' THEN
        RAISE EXCEPTION 'the complaint moved on' USING ERRCODE = 'CMPSC';
    ELSIF v_why IS NOT NULL THEN
        RAISE EXCEPTION '%', v_why USING ERRCODE = 'CMPRF';
    END IF;
    IF p_decision NOT IN ('approve', 'return') THEN
        RAISE EXCEPTION 'decision' USING ERRCODE = 'CMPBD';
    END IF;
    IF p_decision = 'return' AND (p_severity IS NOT NULL OR p_owner IS NOT NULL) THEN
        RAISE EXCEPTION 'severity and owner only with approve' USING ERRCODE = 'CMPBD';
    END IF;
    IF p_owner IS NOT NULL THEN
        IF c.owner_user_id IS NOT NULL
           OR NOT EXISTS (SELECT 1 FROM complaint_assignees(p_id) a WHERE a.id = p_owner) THEN
            RAISE EXCEPTION 'owner' USING ERRCODE = 'CMPAS';
        END IF;
    END IF;
    v_sev := COALESCE(p_severity, c.severity);
    INSERT INTO complaint_decision (complaint_id, stage, decision, remark, severity_before, severity_after,
                                    submit_no, decided_by)
    VALUES (p_id, 'check', p_decision, btrim(p_remark), c.severity, v_sev, c.submit_count, app_current_user_id())
    RETURNING id INTO v_decision;
    IF p_note IS NOT NULL AND btrim(p_note) <> '' THEN
        INSERT INTO complaint_decision_note (decision_id, internal_note) VALUES (v_decision, btrim(p_note));
    END IF;
    UPDATE complaint SET status = CASE p_decision WHEN 'approve' THEN 'under_qc' ELSE 'draft' END::complaint_status,
           responded_at = COALESCE(responded_at, now()),
           severity = v_sev,
           owner_user_id = COALESCE(p_owner, owner_user_id),
           updated_by = app_current_user_id()
     WHERE id = p_id;
    IF v_sev <> c.severity THEN
        p := complaint_sla_policy_at(c.complaint_type_id, v_sev, (c.first_submitted_at AT TIME ZONE 'Asia/Kolkata')::date);
        UPDATE complaint
           SET response_due_at = complaint_due(c.first_submitted_at, p.response_hours, p.business_hours_only),
               resolution_due_at = complaint_due(c.first_submitted_at, p.resolution_hours, p.business_hours_only)
         WHERE id = p_id;
    END IF;
    PERFORM complaint_event(p_id, CASE p_decision WHEN 'approve' THEN 'complaint.approved' ELSE 'complaint.returned' END,
                            jsonb_build_object('severity', v_sev, 'owner_user_id', p_owner));
    PERFORM complaint_notify(p_id, 'complaint.updated',
                             CASE p_decision WHEN 'approve' THEN '{_WORDS["approve"]}' ELSE '{_WORDS["return"]}' END);
END $fn$""",
    f"""CREATE FUNCTION complaint_qc(p_id uuid, p_verdict text, p_remark text, p_received date,
                             p_tested date, p_visit date, p_note text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE c complaint%ROWTYPE; v_why text; v_decision uuid;
BEGIN
    SELECT * INTO c FROM complaint WHERE id = p_id AND deleted_at IS NULL FOR UPDATE;
    v_why := complaint_refusal(p_id, 'qc');
    IF v_why = 'not_visible' THEN
        RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'CMPNF';
    ELSIF v_why = 'not_under_qc' THEN
        RAISE EXCEPTION 'the complaint moved on' USING ERRCODE = 'CMPSC';
    ELSIF v_why IS NOT NULL THEN
        RAISE EXCEPTION '%', v_why USING ERRCODE = 'CMPRF';
    END IF;
    IF p_verdict NOT IN ('approved', 'rejected') THEN
        RAISE EXCEPTION 'verdict' USING ERRCODE = 'CMPBD';
    END IF;
    INSERT INTO complaint_decision (complaint_id, stage, decision, remark, sample_received_on, tested_on,
                                    field_visit_on, submit_no, decided_by)
    VALUES (p_id, 'qc', p_verdict, btrim(p_remark), p_received, p_tested, p_visit, c.submit_count,
            app_current_user_id())
    RETURNING id INTO v_decision;
    IF p_note IS NOT NULL AND btrim(p_note) <> '' THEN
        INSERT INTO complaint_decision_note (decision_id, internal_note) VALUES (v_decision, btrim(p_note));
    END IF;
    UPDATE complaint SET status = CASE p_verdict WHEN 'approved' THEN 'qc_approved' ELSE 'qc_rejected' END::complaint_status,
           resolved_at = now(), updated_by = app_current_user_id()
     WHERE id = p_id;
    PERFORM complaint_event(p_id, 'complaint.qc_' || p_verdict, '{{}}'::jsonb);
    PERFORM complaint_notify(p_id, 'complaint.updated',
                             CASE p_verdict WHEN 'approved' THEN '{_WORDS["approved"]}' ELSE '{_WORDS["rejected"]}' END);
END $fn$""",
    """CREATE FUNCTION complaint_cancel(p_id uuid, p_reason text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE c complaint%ROWTYPE; v_why text;
BEGIN
    SELECT * INTO c FROM complaint WHERE id = p_id AND deleted_at IS NULL FOR UPDATE;
    v_why := complaint_refusal(p_id, 'cancel');
    IF v_why = 'not_visible' THEN
        RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'CMPNF';
    ELSIF v_why = 'not_open' THEN
        RAISE EXCEPTION 'the complaint moved on' USING ERRCODE = 'CMPSC';
    ELSIF v_why IS NOT NULL THEN
        RAISE EXCEPTION '%', v_why USING ERRCODE = 'CMPRF';
    END IF;
    INSERT INTO complaint_decision (complaint_id, stage, decision, remark, submit_no, decided_by)
    VALUES (p_id, 'cancel', 'cancelled', btrim(p_reason), c.submit_count, app_current_user_id());
    UPDATE complaint SET status = 'cancelled', updated_by = app_current_user_id() WHERE id = p_id;
    PERFORM complaint_event(p_id, 'complaint.cancelled', '{}'::jsonb);
END $fn$""",
    # A master is never edited in place by the caller: the row in force is closed
    # and the new one opened (EC-12). A row starting the same day is refused.
    """CREATE FUNCTION complaint_sla_policy_set(p_severity complaint_severity, p_type uuid, p_response int,
                                         p_resolution int, p_business boolean, p_from date) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_next date; v_id uuid;
BEGIN
    IF NOT app_has_permission('masters', 'edit') THEN
        RAISE EXCEPTION 'masters.edit required' USING ERRCODE = '42501';
    END IF;
    PERFORM pg_advisory_xact_lock(5, hashtext('complaint_sla_policy'));
    IF EXISTS (SELECT 1 FROM complaint_sla_policy WHERE severity = p_severity
                 AND complaint_type_id IS NOT DISTINCT FROM p_type AND effective_from = p_from) THEN
        RAISE EXCEPTION 'a target already starts that day' USING ERRCODE = 'CMPSP';
    END IF;
    SELECT min(effective_from) INTO v_next FROM complaint_sla_policy
     WHERE severity = p_severity AND complaint_type_id IS NOT DISTINCT FROM p_type AND effective_from > p_from;
    UPDATE complaint_sla_policy SET effective_to = p_from
     WHERE severity = p_severity AND complaint_type_id IS NOT DISTINCT FROM p_type
       AND effective_from < p_from AND (effective_to IS NULL OR effective_to > p_from);
    INSERT INTO complaint_sla_policy (severity, complaint_type_id, response_hours, resolution_hours,
                                      business_hours_only, effective_from, effective_to, created_by)
    VALUES (p_severity, p_type, p_response, p_resolution, p_business, p_from, v_next, app_current_user_id())
    RETURNING id INTO v_id;
    RETURN v_id;
END $fn$""",
    # ADR-039: both enforcers agree that a submitted complaint's lines are frozen
    """CREATE FUNCTION complaint_line_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_status complaint_status;
BEGIN
    SELECT status INTO v_status FROM complaint
     WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.complaint_id ELSE NEW.complaint_id END;
    IF v_status IS DISTINCT FROM 'draft' THEN
        RAISE EXCEPTION 'the complaint is not a draft' USING ERRCODE = 'CMPND';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $fn$""",
    "CREATE TRIGGER trg_complaint_line_guard BEFORE INSERT OR UPDATE OR DELETE ON complaint_line FOR EACH ROW EXECUTE FUNCTION complaint_line_guard()",
    # The raiser is the caller: it gates submit, cancel and the self-check (delta
    # Q2). A trigger, not a policy, so the complaint table carries only generated
    # policies and the drift test stays exact. Invoker: current_user is the role
    # the request switched into; the table owner (seeds, tests) is not held to it.
    """CREATE FUNCTION complaint_raiser_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF current_user = 'app_role' AND NEW.raised_by IS DISTINCT FROM app_current_user_id() THEN
        RAISE EXCEPTION 'raised_by must be the caller' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END $fn$""",
    "CREATE TRIGGER trg_complaint_raiser_guard BEFORE INSERT ON complaint FOR EACH ROW EXECUTE FUNCTION complaint_raiser_guard()",
    """CREATE FUNCTION complaint_header_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF current_user = 'app_role' AND OLD.status <> 'draft' THEN
        RAISE EXCEPTION 'the complaint is not a draft' USING ERRCODE = 'CMPND';
    END IF;
    RETURN NEW;
END $fn$""",
    "CREATE TRIGGER trg_complaint_header_guard BEFORE UPDATE ON complaint FOR EACH ROW EXECUTE FUNCTION complaint_header_guard()",
]

INTERNAL = ["complaint_visible(uuid)", "complaint_has_checker(uuid)", "complaint_notify(uuid, text, text)",
            "complaint_event(uuid, text, jsonb)", "complaint_allocate_no(text, text)",
            "complaint_sla_policy_at(uuid, complaint_severity, date)", "complaint_line_guard()",
            "complaint_raiser_guard()", "complaint_header_guard()"]
GRANTED = ["complaint_refusal(uuid, text)", "complaint_assignees(uuid)", "complaint_submit(uuid)",
           "complaint_check(uuid, text, text, complaint_severity, uuid, text)",
           "complaint_qc(uuid, text, text, date, date, date, text)", "complaint_cancel(uuid, text)",
           "complaint_sla_policy_set(complaint_severity, uuid, int, int, boolean, date)",
           "complaint_add_working_hours(timestamptz, int)", "complaint_due(timestamptz, int, boolean)"]


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_019", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"019: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"019: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


def _before() -> dict[str, str]:
    """The two functions this migration replaces, as 018 left them."""
    after = _load("018_tasks_planner")._after_map()
    return {"lead_timeline": after["lead_timeline"], "people_names": after["people_names"]}


def _after() -> list[str]:
    f = _before()
    f["lead_timeline"] = _replace(
        f["lead_timeline"],
        "           AND (entity_type <> 'meeting_minutes' OR minutes_visible(entity_id))",
        "           AND (entity_type <> 'meeting_minutes' OR minutes_visible(entity_id))\n"
        "           AND (entity_type <> 'complaint' OR complaint_visible(entity_id))")
    # a complaint's owner and raiser for whoever sees it; its deciders for staff only
    f["people_names"] = _replace(
        f["people_names"],
        "         -- who approved and who dispatched are internal to Polysil (question 15.14)",
        "         OR EXISTS (SELECT 1 FROM complaint c\n"
        "                     WHERE (c.owner_user_id = u.id OR c.raised_by = u.id) AND complaint_visible(c.id))\n"
        "         -- who approved and who dispatched are internal to Polysil (question 15.14)")
    f["people_names"] = _replace(
        f["people_names"],
        "AND order_visible(d.sales_order_id)))))",
        "AND order_visible(d.sales_order_id))\n"
        "               OR EXISTS (SELECT 1 FROM complaint_decision cd\n"
        "                           WHERE cd.decided_by = u.id AND complaint_visible(cd.complaint_id)))))")
    return list(f.values())


def upgrade() -> None:
    for stmt in ENUMS + TABLES_SQL + GENERATED_INDEXES + HAND_INDEXES + SEED:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for table in ("complaint_type", "complaint_line", "complaint_decision", "complaint_decision_note",
                  "complaint_attachment", "complaint_counter", "complaint_sla_policy"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for stmt in COMPLAINT_POLICIES:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for table, stmt in HAND_POLICIES:
        if table != "activity_event":
            op.execute(stmt)
    for stmt in PARENT_GUARD:
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
    # the last activity_event literal before this one is 018's
    op.execute(next(s for t, s in _load("018_tasks_planner").HAND_POLICIES if t == "activity_event"))
    for body in _before().values():
        op.execute(body)
    op.execute("DELETE FROM activity_event WHERE entity_type = 'complaint'")
    op.execute("DELETE FROM notification_outbox WHERE template_key IN ('complaint.registered', 'complaint.updated')")
    op.execute("DELETE FROM message_template WHERE key IN ('complaint.registered', 'complaint.updated')")
    op.execute("DROP TRIGGER IF EXISTS trg_complaint_line_guard ON complaint_line")
    op.execute("DROP TRIGGER IF EXISTS trg_complaint_raiser_guard ON complaint")
    op.execute("DROP TRIGGER IF EXISTS trg_complaint_header_guard ON complaint")
    for stmt in PARENT_GUARD:
        if stmt.lstrip().startswith("CREATE TRIGGER"):
            name = stmt.split("CREATE TRIGGER ")[1].split()[0]
            op.execute(f"DROP TRIGGER IF EXISTS {name} ON complaint")
    # functions first: complaint_sla_policy_at() returns the table's row type
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    for table in ("complaint_decision_note", "complaint_decision", "complaint_attachment", "complaint_line",
                  "complaint_sla_policy", "complaint_counter", "complaint", "complaint_type"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    for stmt in PARENT_GUARD:
        if stmt.lstrip().startswith("CREATE FUNCTION") or stmt.lstrip().startswith("CREATE OR REPLACE FUNCTION"):
            name = stmt.split("FUNCTION ")[1].split("(")[0]
            op.execute(f"DROP FUNCTION IF EXISTS {name}()")
    op.execute("DROP TYPE IF EXISTS complaint_severity")
    op.execute("DROP TYPE IF EXISTS complaint_status")
