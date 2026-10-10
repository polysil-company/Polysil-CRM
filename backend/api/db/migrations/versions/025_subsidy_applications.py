"""025: subsidy applications (FS-009).

- `subsidy_stage_def` and `subsidy_stage_field`: the stages as rows (ADR-029),
  seeded with GGRC stages 4 to 17 and their fields from the client's
  `Application-Process-Flow.xlsx`, column B (FS-009 §5.1). `pairs_with_key` ties a
  stage-16 amount to its stage-17 received date, which is how an application
  closes (rule 7).
- `subsidy_application`: one live application per lead, its FS-008 calculation
  stored as it was at create, the chosen category's figures in numeric columns,
  and the lead's scope copied and frozen (D5). The `subsidy` ScopeSpec generates
  its policies, pasted below; the drift test regenerates and compares.
- `subsidy_stage_entry` and `subsidy_stage_value`: append-only. A field's current
  value is the one on the latest entry that carries it.
- `subsidy_document_type` (the 20 enclosures of the Sprinkler BOQ's check list)
  and `subsidy_document`: uploads through the API (ADR-041).
- Definers for every write to the application: `subsidy_application_create` (it
  gates on `subsidy.create`, not `leads.edit`, which the State Co-ordinator lacks:
  plan review B-2), `subsidy_stage_record`, `subsidy_application_cancel`.
- `activity_event_sel` gains the `subsidy_application` arm (plan review B-3).

Revision ID: 025_subsidy_applications
Revises: 024_messages
"""

# ruff: noqa: E501  (generated and embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "025_subsidy_applications"
down_revision: str | None = "024_messages"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id)"""

ENUMS = [
    "CREATE TYPE subsidy_app_status AS ENUM ('open', 'full_fp_received', 'cancelled')",
    "CREATE TYPE subsidy_field_type AS ENUM ('date', 'text', 'amount')",
]

TABLES_SQL = [
    f"""CREATE TABLE subsidy_stage_def (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL REFERENCES subsidy_scheme(id),
    seq int NOT NULL CHECK (seq BETWEEN 1 AND 99),
    code text NOT NULL CHECK (code ~ '^[a-z0-9_]{{1,60}}$'),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT uq_subsidy_stage_code UNIQUE (scheme_id, code),
    CONSTRAINT uq_subsidy_stage_id_scheme UNIQUE (id, scheme_id),
    CONSTRAINT uq_subsidy_stage_seq UNIQUE (scheme_id, seq)
)""",
    f"""CREATE TABLE subsidy_stage_field (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL,
    stage_def_id uuid NOT NULL,
    field_key text NOT NULL CHECK (field_key ~ '^[a-z0-9_]{{1,60}}$'),
    label text NOT NULL CHECK (length(btrim(label)) BETWEEN 1 AND 120),
    type subsidy_field_type NOT NULL,
    is_required boolean NOT NULL DEFAULT false,
    pairs_with_key text,
    sort_order int NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    -- values and closure key on field_key across an application's entries (review F-7)
    CONSTRAINT uq_subsidy_stage_field UNIQUE (scheme_id, field_key),
    CONSTRAINT fk_subsidy_stage_field_stage FOREIGN KEY (stage_def_id, scheme_id)
        REFERENCES subsidy_stage_def (id, scheme_id),
    CONSTRAINT ck_subsidy_pair_amount CHECK (pairs_with_key IS NULL OR type = 'amount')
)""",
    "CREATE INDEX ix_subsidy_stage_field_stage ON subsidy_stage_field (stage_def_id)",
    f"""CREATE TABLE subsidy_application (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_no citext NOT NULL UNIQUE,
    reg_no citext,
    status subsidy_app_status NOT NULL DEFAULT 'open',
    scheme_id uuid NOT NULL REFERENCES subsidy_scheme(id),
    system_type text NOT NULL CHECK (system_type IN ('drip', 'mini_sprinkler', 'sprinkler')),
    category_code text NOT NULL,
    category_name text NOT NULL,
    category_pct numeric(6,3) NOT NULL,
    lead_id uuid NOT NULL REFERENCES lead(id),
    farmer_name text NOT NULL,
    mobile text NOT NULL,
    village text,
    survey_no text CHECK (survey_no IS NULL OR length(survey_no) <= 100),
    territory_id uuid NOT NULL REFERENCES territory(id),
    partner_id uuid REFERENCES channel_partner(id),
    total_area numeric(10,3) NOT NULL CHECK (total_area > 0),
    group_total_area numeric(10,3),
    calculation_request jsonb NOT NULL,
    calculation jsonb NOT NULL,
    total_cost numeric(14,2) NOT NULL,
    subsidy numeric(14,2) NOT NULL,
    farmer_share numeric(14,2) NOT NULL,
    formula_version text NOT NULL,
    regular_matrix_id uuid NOT NULL,
    seven_year_matrix_id uuid NOT NULL,
    as_of date NOT NULL,
    current_stage_id uuid NOT NULL REFERENCES subsidy_stage_def(id),
    current_since date NOT NULL,
    owner_user_id uuid REFERENCES app_user(id),
    owner_org_unit_id uuid NOT NULL REFERENCES org_unit(id),
    cancel_reason text CHECK (cancel_reason IS NULL OR length(btrim(cancel_reason)) BETWEEN 1 AND 500),
    closed_at timestamptz,
    full_fp_received_on date,
    {AUDIT},
    CONSTRAINT ck_subsidy_cancelled CHECK ((status = 'cancelled') = (cancel_reason IS NOT NULL)),
    CONSTRAINT ck_subsidy_closed CHECK ((status = 'full_fp_received') = (full_fp_received_on IS NOT NULL))
)""",
    # one live application per lead (plan review R-3)
    "CREATE UNIQUE INDEX uq_subsidy_application_live_lead ON subsidy_application (lead_id) WHERE status <> 'cancelled'",
    "CREATE INDEX ix_subsidy_application_reg_no ON subsidy_application (reg_no)",
    "CREATE INDEX ix_subsidy_application_created ON subsidy_application (created_at DESC, id DESC)",
    "CREATE INDEX ix_subsidy_application_partner ON subsidy_application (partner_id)",
    "CREATE INDEX ix_subsidy_application_stage ON subsidy_application (current_stage_id)",
    """CREATE TABLE subsidy_stage_entry (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL REFERENCES subsidy_application(id),
    stage_def_id uuid NOT NULL REFERENCES subsidy_stage_def(id),
    occurred_on date NOT NULL,
    remark text CHECK (remark IS NULL OR length(btrim(remark)) BETWEEN 1 AND 1000),
    entered_by uuid NOT NULL REFERENCES app_user(id),
    entered_at timestamptz NOT NULL DEFAULT clock_timestamp()
)""",
    "CREATE INDEX ix_subsidy_entry_app ON subsidy_stage_entry (application_id, entered_at DESC, id DESC)",
    "CREATE INDEX ix_subsidy_entry_stage ON subsidy_stage_entry (stage_def_id)",
    "CREATE INDEX ix_subsidy_entry_by ON subsidy_stage_entry (entered_by)",
    """CREATE TABLE subsidy_stage_value (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id uuid NOT NULL REFERENCES subsidy_stage_entry(id),
    field_key text NOT NULL,
    value_text text CHECK (value_text IS NULL OR length(value_text) <= 500),
    value_date date,
    value_amount numeric(14,2) CHECK (value_amount IS NULL OR (value_amount >= 0 AND value_amount <> 'NaN')),
    CONSTRAINT uq_subsidy_value UNIQUE (entry_id, field_key),
    CONSTRAINT ck_subsidy_value_one CHECK (num_nonnulls(value_text, value_date, value_amount) <= 1)
)""",
    f"""CREATE TABLE subsidy_document_type (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE CHECK (code::text ~ '^[a-z0-9_]+$'),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    sort_order int NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    deleted_at timestamptz
)""",
    """CREATE TABLE subsidy_document (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL REFERENCES subsidy_application(id),
    document_type_id uuid NOT NULL REFERENCES subsidy_document_type(id),
    storage_key text NOT NULL,
    content_type text NOT NULL,
    size_bytes int NOT NULL CHECK (size_bytes > 0),
    sha256 text NOT NULL,
    original_name text CHECK (original_name IS NULL OR length(original_name) <= 255),
    uploaded_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    deleted_by uuid REFERENCES app_user(id)
)""",
    "CREATE UNIQUE INDEX uq_subsidy_document_file ON subsidy_document (application_id, sha256) WHERE deleted_at IS NULL",
    "CREATE INDEX ix_subsidy_document_type ON subsidy_document (document_type_id)",
    "CREATE INDEX ix_subsidy_document_by ON subsidy_document (uploaded_by)",
    """CREATE TABLE subsidy_app_counter (
    state_code text NOT NULL,
    financial_year text NOT NULL,
    last_value int NOT NULL,
    PRIMARY KEY (state_code, financial_year)
)""",
]

SEED = ["INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 4, 'application_in_process', 'Application in process' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'app_inward', 'App. Inward Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'application_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'app_re_inward', 'App. Re-Inward Date', 'date', NULL, 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'application_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'apply_date', 'Apply Date', 'date', NULL, 30 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'application_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'reg_no', 'Reg. No.', 'text', NULL, 40 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'application_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'doc_check', 'App. Document Check Date', 'date', NULL, 50 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'application_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'app_query', 'App Query Date', 'date', NULL, 60 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'application_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'app_query_solved', 'App Query Solve Date', 'date', NULL, 70 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'application_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'return_to_field', 'Return to Field Date', 'date', NULL, 80 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'application_in_process'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 5, 'technical_in_process', 'Technical in process' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tech_received', 'Tech. Received Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'technical_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tech_check', 'Tech Check Date', 'date', NULL, 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'technical_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tech_query', 'Tech Query Date', 'date', NULL, 30 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'technical_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tech_query_solved', 'Tech Query Solve Date', 'date', NULL, 40 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'technical_in_process'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tech_return_to_field', 'Return to Field Date', 'date', NULL, 50 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'technical_in_process'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 6, 'submitted_wo_pending', 'Application submitted, WO pending' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'submission', 'App. Submission Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'submitted_wo_pending'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 7, 'farmer_share', 'Farmer share detail' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'farmer_share_amt', 'Farmer Share Amt.', 'amount', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'farmer_share'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'fs_credited_1', 'FS Credited Date-1', 'date', NULL, 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'farmer_share'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'fs_credited_2', 'FS Credited Date-2', 'date', NULL, 30 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'farmer_share'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'supply', 'Original Material Supply Date', 'date', NULL, 40 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'farmer_share'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 8, 'ggrc_query', 'GGRC query' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'query_1', 'Query-1 Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'ggrc_query'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'query_1_solved', 'Query-1 Solve Date', 'date', NULL, 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'ggrc_query'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'query_2', 'Query-2 Date', 'date', NULL, 30 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'ggrc_query'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'query_2_solved', 'Query-2 Solve Date', 'date', NULL, 40 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'ggrc_query'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'query_3', 'Query-3 Date', 'date', NULL, 50 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'ggrc_query'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'query_3_solved', 'Query-3 Solve Date', 'date', NULL, 60 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'ggrc_query'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 9, 'wo_issued', 'WO issued, TPA pending' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'wo_received', 'WO Received Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'wo_issued'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 10, 'tpa_sent', 'TPA sent' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tpa_received', 'TPA Received Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tpa_sent'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tpa_date', 'TPA Date', 'date', NULL, 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tpa_sent'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tpa_sent', 'TPA Sent Date', 'date', NULL, 30 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tpa_sent'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 11, 'inspection_call_pending', 'Inspection call pending' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tpa_cleared', 'TPA Cleared Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'inspection_call_pending'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 12, 'tr_pending', 'TR pending' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'inspection_sent', 'Inspection Sent Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tr_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tpia_name', 'TPIA Name', 'text', NULL, 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tr_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tr_planning_1', 'TR Planning Date-1', 'date', NULL, 30 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tr_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tr_planning_2', 'TR Planning Date-2', 'date', NULL, 40 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tr_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tr_not_ok', 'TR Not Ok Date', 'date', NULL, 50 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tr_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tr_not_ok_remark', 'TR Not Ok Remark', 'text', NULL, 60 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tr_pending'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 13, 'tr_done', 'TR done' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tr_received', 'TR Received Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tr_done'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'tr_date', 'TR Date', 'date', NULL, 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'tr_done'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 14, 'fp_invoice_submitted', 'FP invoice submitted' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'fp_amount', 'FP Amount', 'amount', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_invoice_submitted'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'deduction_amount', 'Deduction Amount', 'amount', NULL, 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_invoice_submitted'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'fp_submitted', 'FP Invoice Submitted Date', 'date', NULL, 30 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_invoice_submitted'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 15, 'fp_query', 'FP query' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'fp_query_remark', 'FP Query Remark', 'text', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_query'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'fp_query_received', 'FP Query Received Date', 'date', NULL, 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_query'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'fp_query_solved', 'FP Query Solve Date', 'date', NULL, 30 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_query'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 16, 'fp_cleared_pay_pending', 'FP cleared, payment pending' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'fp_cleared', 'FP Cleared Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_cleared_pay_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'pfms_amt', 'PFMS/Central Amt.', 'amount', 'pfms_received', 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_cleared_pay_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'state_share_amt', 'State Share Amt.', 'amount', 'state_share_received', 30 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_cleared_pay_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'fp_farmer_share_amt', 'Farmer Share Amt.', 'amount', 'farmer_share_received', 40 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_cleared_pay_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'fp_deduction_amt', 'Deduction Amt.', 'amount', 'deduction_recovered', 50 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_cleared_pay_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'retention_amt', 'Retention Amt.', 'amount', 'retention_received', 60 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_cleared_pay_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'dept_hold_amt', 'Dept. Hold Amt.', 'amount', 'dept_hold_received', 70 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_cleared_pay_pending'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'total_fp_amt', 'Total FP Amount', 'amount', NULL, 80 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'fp_cleared_pay_pending'", "INSERT INTO subsidy_stage_def (scheme_id, seq, code, name) SELECT id, 17, 'payment_received', 'Payment received' FROM subsidy_scheme WHERE code = 'GGRC'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'pfms_received', 'PFMS/Central Amt. Date', 'date', NULL, 10 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'payment_received'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'state_share_received', 'State Share Amt. Date', 'date', NULL, 20 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'payment_received'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'farmer_share_received', 'Farmer Share Amt. Date', 'date', NULL, 30 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'payment_received'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'deduction_recovered', 'Deduction Amt. Recovery Date', 'date', NULL, 40 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'payment_received'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'retention_received', 'Retention Amt. Rec. Date', 'date', NULL, 50 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'payment_received'", "INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, pairs_with_key, sort_order) SELECT d.scheme_id, d.id, 'dept_hold_received', 'Dept. Hold Amt. Date', 'date', NULL, 60 FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id WHERE s.code = 'GGRC' AND d.code = 'payment_received'", "INSERT INTO subsidy_document_type (code, name, sort_order) VALUES ('farmer_application_form_1', 'Farmer Application (Form-1)', 10), ('8a_7_12', '8 A & 7/12', 20), ('form_16', 'Form No. 16', 30), ('bank_sanction_letter', 'Bank Sanction Letter', 40), ('farmer_type_certificate', 'Type of Farmer Certificate', 50), ('caste_certificate', 'Caste certificate', 60), ('affidavit_8a', 'Affidavit by Farmer for Form No. 8A', 70), ('joint_owner_undertaking', 'Undertaking (Rs 20 stamp paper) from other joint owners on 7-12', 80), ('water_sharing_agreement', 'Water sharing Agreement on Rs 20 stamp paper', 90), ('photo_identity', 'Attested photo identity card', 100), ('irrigation_data', 'Irrigation Data', 110), ('form_6', 'Form No. 6', 120), ('quotation_summary', 'Quotation Summary (A+B+C)', 130), ('quotation_a', 'Quotation A (head and field unit, with transportation)', 140), ('quotation_b', 'Quotation B (agronomy consultancy)', 150), ('quotation_c', 'Quotation C (installation)', 160), ('consent_letter', 'Farmer''s consent letter (Sammati Patrak)', 170), ('design', 'Design', 180), ('soil_water_report', 'Soil & Water Analysis Report', 190), ('techno_economic_report', 'Techno Economic Report', 200)"]

GENERATED_POLICIES = ["CREATE POLICY subsidy_application_sel_own ON subsidy_application FOR SELECT USING (\n  (SELECT app_scope('subsidy')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id())\n)", "CREATE POLICY subsidy_application_sel_org_subtree ON subsidy_application FOR SELECT USING (\n  (SELECT app_scope('subsidy')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))\n)", "CREATE POLICY subsidy_application_sel_territory ON subsidy_application FOR SELECT USING (\n  (SELECT app_scope('subsidy')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id()))\n)", "CREATE POLICY subsidy_application_sel_global ON subsidy_application FOR SELECT USING (\n  (SELECT app_scope('subsidy')) = 'global'\n)", "CREATE POLICY subsidy_application_res_perm ON subsidy_application AS RESTRICTIVE FOR SELECT USING (\n  (SELECT app_has_permission('subsidy', 'view'))\n)", "CREATE POLICY subsidy_application_ins ON subsidy_application FOR INSERT WITH CHECK (\n  (((SELECT app_scope('subsidy')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('subsidy')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('subsidy')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('subsidy')) = 'global'))\n  AND (lead_id IS NULL OR EXISTS (SELECT 1 FROM lead p WHERE p.id = lead_id))\n  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))\n  AND (owner_org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = owner_org_unit_id))\n)", "CREATE POLICY subsidy_application_ins_perm ON subsidy_application AS RESTRICTIVE FOR INSERT WITH CHECK (\n  (SELECT app_has_permission('subsidy', 'create'))\n)", "CREATE POLICY subsidy_application_upd ON subsidy_application FOR UPDATE USING (\n  ((SELECT app_scope('subsidy')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('subsidy')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('subsidy')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('subsidy')) = 'global')\n) WITH CHECK (\n  ((SELECT app_scope('subsidy')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('subsidy')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('subsidy')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('subsidy')) = 'global')\n)", "CREATE POLICY subsidy_application_upd_perm ON subsidy_application AS RESTRICTIVE FOR UPDATE USING (\n  (SELECT app_has_permission('subsidy', 'edit'))\n)", "CREATE POLICY subsidy_application_del ON subsidy_application FOR DELETE USING (\n  ((SELECT app_scope('subsidy')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('subsidy')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('subsidy')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('subsidy')) = 'global')\n)", "CREATE POLICY subsidy_application_del_perm ON subsidy_application AS RESTRICTIVE FOR DELETE USING (\n  (SELECT app_has_permission('subsidy', 'delete'))\n)"]
GENERATED_INDEXES = ['CREATE INDEX IF NOT EXISTS ix_subsidy_application_owner_user_id ON subsidy_application (owner_user_id)', 'CREATE INDEX IF NOT EXISTS ix_subsidy_application_owner_org_unit_id ON subsidy_application (owner_org_unit_id)', 'CREATE INDEX IF NOT EXISTS ix_subsidy_application_territory_id ON subsidy_application (territory_id)', 'CREATE INDEX IF NOT EXISTS ix_subsidy_application_lead_id ON subsidy_application (lead_id)']
PARENT_GUARD = ["CREATE FUNCTION subsidy_application_parent_guard() RETURNS trigger\n        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$\n        BEGIN\n            IF NEW.lead_id IS DISTINCT FROM OLD.lead_id AND NEW.lead_id IS NOT NULL\n               AND NOT authz_visible('lead', NEW.lead_id) THEN\n                RAISE EXCEPTION 'lead_id % is not in your scope', NEW.lead_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.territory_id IS DISTINCT FROM OLD.territory_id AND NEW.territory_id IS NOT NULL\n               AND NOT authz_visible('territory', NEW.territory_id) THEN\n                RAISE EXCEPTION 'territory_id % is not in your scope', NEW.territory_id\n                    USING ERRCODE = '42501';\n            END IF;\n            IF NEW.owner_org_unit_id IS DISTINCT FROM OLD.owner_org_unit_id AND NEW.owner_org_unit_id IS NOT NULL\n               AND NOT authz_visible('org_unit', NEW.owner_org_unit_id) THEN\n                RAISE EXCEPTION 'owner_org_unit_id % is not in your scope', NEW.owner_org_unit_id\n                    USING ERRCODE = '42501';\n            END IF;\n            RETURN NEW;\n        END $fn$", 'CREATE TRIGGER trg_subsidy_application_parent_guard\n            BEFORE UPDATE OF lead_id, territory_id, owner_org_unit_id ON subsidy_application\n            FOR EACH ROW EXECUTE FUNCTION subsidy_application_parent_guard()']
_GUARD = "(((SELECT app_scope('subsidy')) = 'own'\n  AND owner_user_id = (SELECT app_current_user_id()))\n  OR ((SELECT app_scope('subsidy')) = 'org_subtree'\n  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))\n  OR ((SELECT app_scope('subsidy')) = 'territory'\n  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))\n  OR ((SELECT app_scope('subsidy')) = 'global'))\n  AND ((SELECT app_has_permission('subsidy', 'view')))"

HAND_POLICIES: list[tuple[str, str]] = [
    # the definitions: a lookup, read by every signed-in caller
    ("subsidy_stage_def", "CREATE POLICY subsidy_stage_def_sel ON subsidy_stage_def FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"),
    ("subsidy_stage_field", "CREATE POLICY subsidy_stage_field_sel ON subsidy_stage_field FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"),
    ("subsidy_document_type", "CREATE POLICY subsidy_document_type_sel ON subsidy_document_type FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"),
    # the history and the documents: visible through their application
    ("subsidy_stage_entry", "CREATE POLICY subsidy_stage_entry_sel ON subsidy_stage_entry FOR SELECT USING (EXISTS (SELECT 1 FROM subsidy_application a WHERE a.id = application_id))"),
    ("subsidy_stage_value", "CREATE POLICY subsidy_stage_value_sel ON subsidy_stage_value FOR SELECT USING (EXISTS (SELECT 1 FROM subsidy_stage_entry e WHERE e.id = entry_id))"),
    ("subsidy_document", "CREATE POLICY subsidy_document_sel ON subsidy_document FOR SELECT USING (EXISTS (SELECT 1 FROM subsidy_application a WHERE a.id = application_id))"),
    ("subsidy_document", "CREATE POLICY subsidy_document_ins ON subsidy_document FOR INSERT WITH CHECK (uploaded_by = (SELECT app_current_user_id()) AND ((SELECT app_has_permission('subsidy', 'create')) OR (SELECT app_has_permission('subsidy', 'edit'))) AND EXISTS (SELECT 1 FROM subsidy_application a WHERE a.id = application_id AND a.status <> 'cancelled'))"),
    ("subsidy_document", "CREATE POLICY subsidy_document_upd ON subsidy_document FOR UPDATE USING (deleted_at IS NULL AND ((SELECT app_has_permission('subsidy', 'create')) OR (SELECT app_has_permission('subsidy', 'edit'))) AND EXISTS (SELECT 1 FROM subsidy_application a WHERE a.id = application_id)) WITH CHECK (deleted_at IS NOT NULL AND deleted_by = (SELECT app_current_user_id()) AND EXISTS (SELECT 1 FROM subsidy_application a WHERE a.id = application_id))"),
    ("activity_event", "CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (\n  CASE entity_type\n    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)\n    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)\n    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)\n    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)\n    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)\n    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)\n    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order c WHERE c.id = entity_id)\n    WHEN 'lead_qr_code' THEN EXISTS (SELECT 1 FROM lead_qr_code c WHERE c.id = entity_id)\n    WHEN 'task' THEN EXISTS (SELECT 1 FROM task c WHERE c.id = entity_id)\n    WHEN 'meeting_minutes' THEN EXISTS (SELECT 1 FROM meeting_minutes c WHERE c.id = entity_id)\n    WHEN 'complaint' THEN EXISTS (SELECT 1 FROM complaint c WHERE c.id = entity_id)\n    WHEN 'subsidy_application' THEN EXISTS (SELECT 1 FROM subsidy_application c WHERE c.id = entity_id)\n    ELSE (SELECT app_is_system())\n  END\n)"),
]

TRIGGERED = ('subsidy_application', 'subsidy_stage_def', 'subsidy_stage_field', 'subsidy_document_type')

GRANTS: dict[str, str] = {
    "subsidy_stage_def": "SELECT",
    "subsidy_stage_field": "SELECT",
    "subsidy_document_type": "SELECT",
    # every write to the application goes through the definers (the FS-011 pattern)
    "subsidy_application": "SELECT",
    "subsidy_stage_entry": "SELECT",
    "subsidy_stage_value": "SELECT",
    "subsidy_document": "SELECT, INSERT, UPDATE (deleted_at, deleted_by)",
}

FUNCTIONS = [
    f"""CREATE FUNCTION subsidy_application_visible(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM subsidy_application WHERE id = p_id AND (
{_GUARD}
    ))
$fn$""",
    """CREATE FUNCTION subsidy_allocate_no(p_state_code text, p_fy text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    INSERT INTO subsidy_app_counter (state_code, financial_year, last_value)
    VALUES (p_state_code, p_fy, 1)
    ON CONFLICT (state_code, financial_year)
    DO UPDATE SET last_value = subsidy_app_counter.last_value + 1
    RETURNING last_value INTO v_n;
    RETURN 'SA/' || p_state_code || '/' || p_fy || '/' || lpad(v_n::text, greatest(5, length(v_n::text)), '0');
END $fn$""",
    """CREATE FUNCTION subsidy_event(p_app uuid, p_kind text, p_payload jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_lead uuid; v_name text;
BEGIN
    SELECT lead_id INTO v_lead FROM subsidy_application WHERE id = p_app;
    SELECT full_name INTO v_name FROM app_user WHERE id = app_current_user_id();
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('subsidy_application', p_app, v_lead, p_kind, app_current_user_id(),
            jsonb_build_object('actor_name', COALESCE(v_name, '')) || COALESCE(p_payload, '{}'));
END $fn$""",
    # Forward a lead (rules 1 to 4). The lead is locked here, not through
    # lead_lock_for_quotation(), whose leads.edit the State Co-ordinator lacks.
    """CREATE FUNCTION subsidy_application_create(
        p_lead uuid, p_category_code text, p_category_name text, p_category_pct numeric,
        p_request jsonb, p_calc jsonb, p_total_cost numeric, p_subsidy numeric, p_farmer_share numeric,
        p_total_area numeric, p_group_total numeric, p_formula text, p_regular uuid, p_seven uuid,
        p_as_of date, p_survey text, p_fy text, p_system text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    l lead%ROWTYPE; v_mis text; v_scheme uuid; v_stage uuid; v_state text; v_no text; v_id uuid;
    v_today date := (now() AT TIME ZONE 'Asia/Kolkata')::date; v_actor text;
BEGIN
    IF NOT app_has_permission('subsidy', 'create') THEN
        RAISE EXCEPTION 'subsidy.create required' USING ERRCODE = '42501';
    END IF;
    IF NOT lead_visible(p_lead) THEN
        RAISE EXCEPTION 'lead not found' USING ERRCODE = 'SAPNF';
    END IF;
    SELECT * INTO l FROM lead WHERE id = p_lead AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'lead not found' USING ERRCODE = 'SAPNF';
    END IF;
    IF l.inquiry_type::text <> 'subsidised' THEN
        RAISE EXCEPTION 'the lead is not subsidised' USING ERRCODE = 'SAPNS';
    END IF;
    IF l.stage::text NOT IN ('qualified', 'quoted', 'negotiation', 'won') THEN
        RAISE EXCEPTION 'the lead is %', l.stage USING ERRCODE = 'SAPST';
    END IF;
    SELECT code INTO v_mis FROM mis_system WHERE id = l.mis_system_id;
    IF v_mis IS DISTINCT FROM p_system OR p_system NOT IN ('drip', 'mini_sprinkler', 'sprinkler') THEN
        RAISE EXCEPTION 'the lead''s system has no subsidy calculation' USING ERRCODE = 'SAPSY';
    END IF;
    IF EXISTS (SELECT 1 FROM subsidy_application WHERE lead_id = p_lead AND status <> 'cancelled') THEN
        RAISE EXCEPTION 'the lead has an application' USING ERRCODE = 'SAPDU';
    END IF;
    SELECT id INTO v_scheme FROM subsidy_scheme WHERE code = 'GGRC';
    SELECT id INTO v_stage FROM subsidy_stage_def WHERE scheme_id = v_scheme AND seq = 4;
    -- not lead_state_code(): it gates on leads.create, which the State Co-ordinator
    -- lacks. The same read, with the same share lock against a code change.
    SELECT t.code::text INTO v_state
      FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id
     WHERE tc.descendant_id = l.territory_id AND t.level = 'state'
     ORDER BY tc.depth ASC LIMIT 1
       FOR SHARE OF t;
    IF v_state IS NULL THEN
        RAISE EXCEPTION 'no coded state' USING ERRCODE = 'SAPSC';
    END IF;
    v_no := subsidy_allocate_no(v_state, p_fy);
    INSERT INTO subsidy_application (
        application_no, scheme_id, system_type, category_code, category_name, category_pct,
        lead_id, farmer_name, mobile, village, survey_no, territory_id, partner_id,
        total_area, group_total_area, calculation_request, calculation,
        total_cost, subsidy, farmer_share, formula_version, regular_matrix_id, seven_year_matrix_id, as_of,
        current_stage_id, current_since, owner_user_id, owner_org_unit_id, created_by, updated_by)
    VALUES (
        v_no, v_scheme, p_system, p_category_code, p_category_name, p_category_pct,
        p_lead, l.farmer_name, l.mobile, l.village, p_survey, l.territory_id, l.assigned_partner_id,
        p_total_area, p_group_total, p_request, p_calc,
        p_total_cost, p_subsidy, p_farmer_share, p_formula, p_regular, p_seven, p_as_of,
        v_stage, v_today, l.owner_user_id, l.owner_org_unit_id, app_current_user_id(), app_current_user_id())
    RETURNING id INTO v_id;
    INSERT INTO subsidy_stage_entry (application_id, stage_def_id, occurred_on, entered_by)
    VALUES (v_id, v_stage, v_today, app_current_user_id());
    IF l.stage::text <> 'won' THEN
        UPDATE lead SET stage = 'won', last_activity_at = now() WHERE id = p_lead;
        SELECT full_name INTO v_actor FROM app_user WHERE id = app_current_user_id();
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('lead', p_lead, p_lead, 'lead.stage_changed', app_current_user_id(),
                jsonb_build_object('from', l.stage::text, 'to', 'won', 'via', 'subsidy_application',
                                   'application_id', v_id, 'actor_name', v_actor));
    END IF;
    PERFORM subsidy_event(v_id, 'subsidy.created', jsonb_build_object('application_no', v_no));
    RETURN v_id;
END $fn$""",
    # Record a stage (rules 5 to 7). The application's lock first; every rule is
    # checked against the locked row (plan review R-8).
    """CREATE FUNCTION subsidy_stage_record(p_app uuid, p_stage_code text, p_occurred date,
                                     p_values jsonb, p_remark text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    a subsidy_application%ROWTYPE; s subsidy_stage_def%ROWTYPE; v_cur int; v_entry uuid;
    k text; v jsonb; v_field subsidy_stage_field%ROWTYPE; v_amt numeric; v_date date;
    v_paid int; v_dated int; v_last date;
BEGIN
    IF NOT app_has_permission('subsidy', 'edit') THEN
        RAISE EXCEPTION 'subsidy.edit required' USING ERRCODE = '42501';
    END IF;
    IF NOT subsidy_application_visible(p_app) THEN
        RAISE EXCEPTION 'application not found' USING ERRCODE = 'SAPAN';
    END IF;
    SELECT * INTO a FROM subsidy_application WHERE id = p_app FOR UPDATE;
    IF a.status <> 'open' THEN
        RAISE EXCEPTION 'the application is %', a.status USING ERRCODE = 'SAPCL';
    END IF;
    SELECT * INTO s FROM subsidy_stage_def WHERE scheme_id = a.scheme_id AND code = p_stage_code AND is_active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown stage %', p_stage_code USING ERRCODE = 'SAPSG';
    END IF;
    IF p_occurred IS NULL OR p_occurred > (now() AT TIME ZONE 'Asia/Kolkata')::date THEN
        RAISE EXCEPTION 'a date after today' USING ERRCODE = 'SAPDT';
    END IF;
    SELECT seq INTO v_cur FROM subsidy_stage_def WHERE id = a.current_stage_id;
    IF s.seq <= v_cur AND (p_remark IS NULL OR btrim(p_remark) = '') THEN
        RAISE EXCEPTION 'a backward or same-stage entry needs a remark' USING ERRCODE = 'SAPRM';
    END IF;
    INSERT INTO subsidy_stage_entry (application_id, stage_def_id, occurred_on, remark, entered_by, entered_at)
    VALUES (p_app, s.id, p_occurred, NULLIF(btrim(p_remark), ''), app_current_user_id(), clock_timestamp())
    RETURNING id INTO v_entry;
    FOR k, v IN SELECT * FROM jsonb_each(COALESCE(p_values, '{}'::jsonb)) LOOP
        SELECT * INTO v_field FROM subsidy_stage_field WHERE stage_def_id = s.id AND field_key = k AND is_active;
        IF NOT FOUND THEN
            RAISE EXCEPTION '%', k USING ERRCODE = 'SAPFK';
        END IF;
        IF v = 'null'::jsonb THEN
            INSERT INTO subsidy_stage_value (entry_id, field_key) VALUES (v_entry, k);
            CONTINUE;
        END IF;
        BEGIN
            IF v_field.type = 'date' THEN
                INSERT INTO subsidy_stage_value (entry_id, field_key, value_date) VALUES (v_entry, k, (v #>> '{}')::date);
            ELSIF v_field.type = 'amount' THEN
                v_amt := (v #>> '{}')::numeric;
                IF v_amt = 'NaN'::numeric OR v_amt < 0 OR v_amt <> round(v_amt, 2) THEN
                    RAISE EXCEPTION 'bad amount' USING ERRCODE = '22023';
                END IF;
                INSERT INTO subsidy_stage_value (entry_id, field_key, value_amount) VALUES (v_entry, k, v_amt);
            ELSE
                INSERT INTO subsidy_stage_value (entry_id, field_key, value_text) VALUES (v_entry, k, NULLIF(btrim(v #>> '{}'), ''));
            END IF;
        EXCEPTION WHEN invalid_datetime_format OR invalid_text_representation OR datetime_field_overflow
                       OR invalid_parameter_value OR check_violation OR numeric_value_out_of_range THEN
            RAISE EXCEPTION '%', k USING ERRCODE = 'SAPFV';
        END;
    END LOOP;
    UPDATE subsidy_application
       SET current_stage_id = s.id, current_since = p_occurred, updated_by = app_current_user_id(),
           reg_no = CASE WHEN COALESCE(p_values, '{}'::jsonb) ? 'reg_no'
                         THEN NULLIF(btrim(p_values ->> 'reg_no'), '') ELSE reg_no END
     WHERE id = p_app;
    -- closure (rule 7): every paired amount above zero has its date, and one exists
    WITH cur AS (
        SELECT DISTINCT ON (sv.field_key) sv.field_key, sv.value_amount, sv.value_date
          FROM subsidy_stage_value sv JOIN subsidy_stage_entry e ON e.id = sv.entry_id
         WHERE e.application_id = p_app
         ORDER BY sv.field_key, e.entered_at DESC, e.id DESC
    ), pairs AS (
        SELECT f.field_key, f.pairs_with_key FROM subsidy_stage_field f
          JOIN subsidy_stage_def d ON d.id = f.stage_def_id
         WHERE d.scheme_id = a.scheme_id AND f.pairs_with_key IS NOT NULL AND f.is_active
    )
    SELECT count(*) FILTER (WHERE amt.value_amount > 0),
           count(*) FILTER (WHERE amt.value_amount > 0 AND dt.value_date IS NOT NULL),
           max(dt.value_date) FILTER (WHERE amt.value_amount > 0)
      INTO v_paid, v_dated, v_last
      FROM pairs p
      LEFT JOIN cur amt ON amt.field_key = p.field_key
      LEFT JOIN cur dt ON dt.field_key = p.pairs_with_key;
    PERFORM subsidy_event(p_app, 'subsidy.stage_recorded',
                          jsonb_build_object('stage', s.code, 'seq', s.seq, 'occurred_on', p_occurred,
                                             'direction', CASE WHEN s.seq > v_cur THEN 'forward'
                                                               WHEN s.seq = v_cur THEN 'same' ELSE 'back' END));
    IF v_paid > 0 AND v_paid = v_dated THEN
        UPDATE subsidy_application
           SET status = 'full_fp_received', closed_at = now(), full_fp_received_on = v_last
         WHERE id = p_app;
        PERFORM subsidy_event(p_app, 'subsidy.closed', jsonb_build_object('full_fp_received_on', v_last));
    END IF;
    RETURN v_entry;
END $fn$""",
    # An upload's lock and count (FS-009 edge case 19). A definer, because app_role
    # holds no UPDATE on the application, which FOR UPDATE needs.
    """CREATE FUNCTION subsidy_document_lock(p_app uuid) RETURNS TABLE (status text, files int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_status text;
BEGIN
    IF NOT (app_has_permission('subsidy', 'create') OR app_has_permission('subsidy', 'edit')) THEN
        RAISE EXCEPTION 'subsidy.create or edit required' USING ERRCODE = '42501';
    END IF;
    IF NOT subsidy_application_visible(p_app) THEN
        RAISE EXCEPTION 'application not found' USING ERRCODE = 'SAPAN';
    END IF;
    SELECT a.status::text INTO v_status FROM subsidy_application a WHERE a.id = p_app FOR UPDATE;
    RETURN QUERY SELECT v_status, (SELECT count(*)::int FROM subsidy_document d
                                    WHERE d.application_id = p_app AND d.deleted_at IS NULL);
END $fn$""",
    """CREATE FUNCTION subsidy_application_cancel(p_app uuid, p_reason text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a subsidy_application%ROWTYPE;
BEGIN
    IF NOT app_has_permission('subsidy', 'edit') THEN
        RAISE EXCEPTION 'subsidy.edit required' USING ERRCODE = '42501';
    END IF;
    IF NOT subsidy_application_visible(p_app) THEN
        RAISE EXCEPTION 'application not found' USING ERRCODE = 'SAPAN';
    END IF;
    SELECT * INTO a FROM subsidy_application WHERE id = p_app FOR UPDATE;
    IF a.status <> 'open' THEN
        RAISE EXCEPTION 'the application is %', a.status USING ERRCODE = 'SAPCL';
    END IF;
    UPDATE subsidy_application SET status = 'cancelled', cancel_reason = btrim(p_reason),
                                   updated_by = app_current_user_id()
     WHERE id = p_app;
    PERFORM subsidy_event(p_app, 'subsidy.cancelled', jsonb_build_object('reason', btrim(p_reason)));
END $fn$""",
]

GRANTED = [
    "subsidy_application_visible(uuid)",
    "subsidy_application_create(uuid, text, text, numeric, jsonb, jsonb, numeric, numeric, numeric, numeric, numeric, text, uuid, uuid, date, text, text, text)",
    "subsidy_stage_record(uuid, text, date, jsonb, text)",
    "subsidy_application_cancel(uuid, text)",
    "subsidy_document_lock(uuid)",
]
INTERNAL = ["subsidy_allocate_no(text, text)", "subsidy_event(uuid, text, jsonb)"]


def upgrade() -> None:
    for stmt in ENUMS + TABLES_SQL + GENERATED_INDEXES + SEED:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for table in ("subsidy_application", "subsidy_stage_def", "subsidy_stage_field", "subsidy_document_type",
                  "subsidy_stage_entry", "subsidy_stage_value", "subsidy_document", "subsidy_app_counter"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for stmt in GENERATED_POLICIES:
        op.execute(stmt)
    for stmt in PARENT_GUARD:
        op.execute(stmt)
    # updated_at moves on every write, and the application and its lookups are
    # audited, as quotations and orders are (PR 33 review)
    for table in TRIGGERED:
        op.execute(f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
        op.execute(f"CREATE TRIGGER trg_{table}_audit AFTER INSERT OR UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION audit_row()")
    for table, stmt in HAND_POLICIES:
        if table == "activity_event":
            op.execute("DROP POLICY activity_event_sel ON activity_event")
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("mig019_for_025", Path(__file__).with_name("019_complaints.py"))
    assert spec is not None and spec.loader is not None
    m019 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m019)
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(next(s for t, s in m019.HAND_POLICIES if t == "activity_event"))
    op.execute("DELETE FROM activity_event WHERE entity_type = 'subsidy_application'")
    for stmt in PARENT_GUARD:
        if stmt.lstrip().startswith("CREATE TRIGGER"):
            name = stmt.split("CREATE TRIGGER ")[1].split()[0]
            op.execute(f"DROP TRIGGER IF EXISTS {name} ON subsidy_application")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    for stmt in PARENT_GUARD:
        if "FUNCTION " in stmt and not stmt.lstrip().startswith("CREATE TRIGGER"):
            name = stmt.split("FUNCTION ")[1].split("(")[0]
            op.execute(f"DROP FUNCTION IF EXISTS {name}()")
    for table in ("subsidy_document", "subsidy_stage_value", "subsidy_stage_entry", "subsidy_application",
                  "subsidy_document_type", "subsidy_stage_field", "subsidy_stage_def", "subsidy_app_counter"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DROP TYPE IF EXISTS subsidy_field_type")
    op.execute("DROP TYPE IF EXISTS subsidy_app_status")
