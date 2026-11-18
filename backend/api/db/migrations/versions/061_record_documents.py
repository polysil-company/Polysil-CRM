"""061: documents on leads, quotations, orders, dispatches and payments (FS-050).

One table for every record type. Read under a policy that asks each record type's
own visibility; written only through two definers that check who may add or remove
and write an `activity_event` carrying the record's lead, so the lead's timeline
shows it (plan review B-1).

Revision ID: 061_record_documents
Revises: 060_replacement_chain
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "061_record_documents"
down_revision: str | None = "060_replacement_chain"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PER_RECORD = 50

_spec = importlib.util.spec_from_file_location(
    "consumer_floor_061", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

RECORD_TYPES = ("lead", "quotation", "sales_order", "dispatch", "payment")
DOC_TYPES = ("purchase_order", "payment_proof", "signed_quotation", "invoice", "delivery_challan",
             "transport_receipt", "site_photo", "land_record", "subsidy_document", "other")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


TABLES = [
    f"""CREATE TABLE record_document (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    record_type text NOT NULL,
    record_id uuid NOT NULL,
    doc_type text NOT NULL,
    name text,
    storage_key text NOT NULL UNIQUE,
    filename text NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
    content_type text NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp', 'image/heic', 'application/pdf')),
    size_bytes int NOT NULL CHECK (size_bytes > 0 AND size_bytes <= {MAX_UPLOAD_BYTES}),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
    uploaded_by uuid REFERENCES app_user(id),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    deleted_by uuid REFERENCES app_user(id),
    CONSTRAINT ck_record_document_record_type CHECK (record_type IN ({_in(RECORD_TYPES)})),
    CONSTRAINT ck_record_document_doc_type CHECK (doc_type IN ({_in(DOC_TYPES)})),
    CONSTRAINT ck_record_document_name CHECK (name IS NULL OR length(btrim(name)) BETWEEN 1 AND 80),
    CONSTRAINT ck_record_document_other CHECK (doc_type <> 'other' OR name IS NOT NULL),
    CONSTRAINT ck_record_document_deleted CHECK ((deleted_at IS NULL) = (deleted_by IS NULL) OR deleted_by IS NULL)
)""",
    "CREATE INDEX ix_record_document_record ON record_document (record_type, record_id)",
    "CREATE INDEX ix_record_document_uploaded_by ON record_document (uploaded_by)",
    "CREATE INDEX ix_record_document_deleted_by ON record_document (deleted_by)",
    "CREATE UNIQUE INDEX uq_record_document_file ON record_document (record_type, record_id, doc_type, sha256) WHERE deleted_at IS NULL",
]

GRANTS: dict[str, str] = {"record_document": "SELECT"}

# Each record type's own visibility. A dispatch is visible with its order (dispatch_sel),
# a payment under 031's own policy: plain EXISTS reads them under the caller's RLS.
SELECT_POLICY = """CREATE POLICY record_document_sel ON record_document FOR SELECT USING (CASE record_type
    WHEN 'lead' THEN lead_visible(record_id)
    WHEN 'quotation' THEN quotation_visible(record_id)
    WHEN 'sales_order' THEN order_visible(record_id)
    WHEN 'dispatch' THEN EXISTS (SELECT 1 FROM dispatch d WHERE d.id = record_id)
    WHEN 'payment' THEN EXISTS (SELECT 1 FROM payment p WHERE p.id = record_id)
    ELSE false END)"""

HAND_POLICIES: list[tuple[str, str]] = [("record_document", SELECT_POLICY)]

FUNCTIONS = [
    # Why the caller may not add to a record, or NULL when they may (FS-050 "Who adds").
    # DOCNF: not visible (404). DOCCL: closed (409). DOCFB: visible, may not add (403).
    """CREATE FUNCTION record_document_refusal(p_type text, p_id uuid) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_order uuid; v_closed boolean;
BEGIN
    IF p_type = 'lead' THEN
        IF NOT lead_visible(p_id) THEN RETURN 'DOCNF'; END IF;
        SELECT deleted_at IS NOT NULL OR stage = 'merged' INTO v_closed FROM lead WHERE id = p_id;
        IF v_closed THEN RETURN 'DOCCL'; END IF;
        RETURN CASE WHEN app_has_permission('leads', 'edit') THEN NULL ELSE 'DOCFB' END;
    ELSIF p_type = 'quotation' THEN
        IF NOT quotation_visible(p_id) THEN RETURN 'DOCNF'; END IF;
        RETURN CASE WHEN app_has_permission('quotations', 'edit') THEN NULL ELSE 'DOCFB' END;
    ELSIF p_type = 'sales_order' THEN
        IF NOT order_visible(p_id) THEN RETURN 'DOCNF'; END IF;
        RETURN CASE WHEN app_has_permission('sales_orders', 'edit') THEN NULL ELSE 'DOCFB' END;
    ELSIF p_type = 'dispatch' THEN
        SELECT sales_order_id, voided_at IS NOT NULL INTO v_order, v_closed FROM dispatch WHERE id = p_id;
        IF v_order IS NULL OR NOT order_visible(v_order) OR NOT app_has_permission('dispatch', 'view') THEN
            RETURN 'DOCNF';
        END IF;
        IF v_closed THEN RETURN 'DOCCL'; END IF;
        RETURN CASE WHEN app_has_permission('dispatch', 'edit') OR app_has_permission('sales_orders', 'edit')
                    THEN NULL ELSE 'DOCFB' END;
    ELSIF p_type = 'payment' THEN
        -- as 031's own definers: Accounts, at global scope
        -- a definer cannot ask 031's policy as the caller: visible here only at global
        -- scope, so a narrower caller probing a payment id learns nothing (code review 4)
        IF NOT EXISTS (SELECT 1 FROM payment WHERE id = p_id) OR NOT app_has_permission('payments', 'view')
           OR app_scope('payments') IS DISTINCT FROM 'global' THEN
            RETURN 'DOCNF';
        END IF;
        RETURN CASE WHEN app_has_permission('payments', 'edit') AND app_scope('payments') = 'global'
                    THEN NULL ELSE 'DOCFB' END;
    END IF;
    RETURN 'DOCNF';
END $fn$""",
    # The record's lead, for the event and the lead timeline
    """CREATE FUNCTION record_document_lead(p_type text, p_id uuid) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT CASE p_type
        WHEN 'lead' THEN p_id
        WHEN 'quotation' THEN (SELECT lead_id FROM quotation WHERE id = p_id)
        WHEN 'sales_order' THEN (SELECT lead_id FROM sales_order WHERE id = p_id)
        WHEN 'dispatch' THEN (SELECT o.lead_id FROM dispatch d JOIN sales_order o ON o.id = d.sales_order_id WHERE d.id = p_id)
    END
$fn$""",
    # One event per document change on the records that have a read arm and a lead
    # timeline arm: a dispatch's on its order, a payment's on each allocated order,
    # else on its partner (edge E-1, plan review B-1, R-4)
    """CREATE FUNCTION record_document_event(p_doc uuid, p_kind text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE d record_document%ROWTYPE; v_payload jsonb; v_partner uuid;
BEGIN
    SELECT * INTO d FROM record_document WHERE id = p_doc;
    v_payload := jsonb_build_object('document_id', d.id, 'record_type', d.record_type, 'record_id', d.record_id,
                                    'doc_type', d.doc_type, 'name', d.name);
    IF d.record_type IN ('lead', 'quotation', 'sales_order') THEN
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES (d.record_type, d.record_id, record_document_lead(d.record_type, d.record_id), p_kind,
                app_current_user_id(), v_payload);
    ELSIF d.record_type = 'dispatch' THEN
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        SELECT 'sales_order', x.sales_order_id, o.lead_id, p_kind, app_current_user_id(), v_payload
          FROM dispatch x JOIN sales_order o ON o.id = x.sales_order_id WHERE x.id = d.record_id;
    ELSE
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        SELECT DISTINCT 'sales_order', a.sales_order_id, o.lead_id, p_kind, app_current_user_id(), v_payload
          FROM payment_allocation a JOIN sales_order o ON o.id = a.sales_order_id
         WHERE a.payment_id = d.record_id AND NOT a.voided;
        IF NOT FOUND THEN
            SELECT partner_id INTO v_partner FROM payment WHERE id = d.record_id;
            IF v_partner IS NOT NULL THEN
                INSERT INTO activity_event (entity_type, entity_id, partner_id, kind, actor_id, payload)
                VALUES ('channel_partner', v_partner, v_partner, p_kind, app_current_user_id(), v_payload);
            END IF;
        END IF;
    END IF;
END $fn$""",
    f"""CREATE FUNCTION record_document_add(p_type text, p_id uuid, p_doc_type text, p_name text, p_key text,
        p_filename text, p_content_type text, p_size int, p_sha text)
RETURNS TABLE (id uuid, created boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_why text; v_id uuid; v_count int;
BEGIN
    -- visibility before any lock (plan review R-5)
    v_why := record_document_refusal(p_type, p_id);
    IF v_why IS NOT NULL THEN
        RAISE EXCEPTION 'record document: %', v_why USING ERRCODE = v_why;
    END IF;
    -- the record's row, so two uploads at once do not both count 49 (edge E-9)
    IF p_type = 'lead' THEN PERFORM 1 FROM lead WHERE lead.id = p_id FOR UPDATE;
    ELSIF p_type = 'quotation' THEN PERFORM 1 FROM quotation WHERE quotation.id = p_id FOR UPDATE;
    ELSIF p_type = 'sales_order' THEN PERFORM 1 FROM sales_order WHERE sales_order.id = p_id FOR UPDATE;
    ELSIF p_type = 'dispatch' THEN PERFORM 1 FROM dispatch WHERE dispatch.id = p_id FOR UPDATE;
    ELSE PERFORM 1 FROM payment WHERE payment.id = p_id FOR UPDATE;
    END IF;
    v_why := record_document_refusal(p_type, p_id);
    IF v_why IS NOT NULL THEN
        RAISE EXCEPTION 'record document: %', v_why USING ERRCODE = v_why;
    END IF;
    INSERT INTO record_document (record_type, record_id, doc_type, name, storage_key, filename, content_type,
                                 size_bytes, sha256, uploaded_by)
    SELECT p_type, p_id, p_doc_type, NULLIF(btrim(p_name), ''), p_key, p_filename, p_content_type, p_size, p_sha,
           app_current_user_id()
     WHERE (SELECT count(*) FROM record_document r WHERE r.record_type = p_type AND r.record_id = p_id
              AND r.deleted_at IS NULL) < {MAX_PER_RECORD}
    ON CONFLICT (record_type, record_id, doc_type, sha256) WHERE deleted_at IS NULL DO NOTHING
    RETURNING record_document.id INTO v_id;
    IF v_id IS NOT NULL THEN
        PERFORM record_document_event(v_id, 'document.added');
        RETURN QUERY SELECT v_id, true;
        RETURN;
    END IF;
    SELECT r.id INTO v_id FROM record_document r WHERE r.record_type = p_type AND r.record_id = p_id
       AND r.doc_type = p_doc_type AND r.sha256 = p_sha AND r.deleted_at IS NULL;
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'at most {MAX_PER_RECORD} documents on one record' USING ERRCODE = 'DOCMX';
    END IF;
    RETURN QUERY SELECT v_id, false;
END $fn$""",
    # The uploader, or a staff member who may add to the record (edge E-3)
    """CREATE FUNCTION record_document_remove(p_doc uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE d record_document%ROWTYPE; v_why text;
BEGIN
    SELECT * INTO d FROM record_document WHERE id = p_doc AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no such document' USING ERRCODE = 'DOCNF';
    END IF;
    v_why := record_document_refusal(d.record_type, d.record_id);
    IF v_why = 'DOCNF' THEN
        RAISE EXCEPTION 'no such document' USING ERRCODE = 'DOCNF';
    END IF;
    IF d.uploaded_by IS DISTINCT FROM app_current_user_id()
       AND (app_current_partner() IS NOT NULL OR v_why IS NOT NULL) THEN
        RAISE EXCEPTION 'only the uploader or a staff editor removes it' USING ERRCODE = 'DOCFB';
    END IF;
    UPDATE record_document SET deleted_at = now(), deleted_by = app_current_user_id() WHERE id = p_doc;
    PERFORM record_document_event(p_doc, 'document.removed');
END $fn$""",
]

GRANTED = ["record_document_refusal(text, uuid)",
           "record_document_add(text, uuid, text, text, text, text, text, int, text)",
           "record_document_remove(uuid)"]
INTERNAL = ["record_document_lead(text, uuid)", "record_document_event(uuid, text)"]


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("ALTER TABLE record_document ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    op.execute(floor.policy_sql("record_document"))
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED + INTERNAL:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for sig in reversed(GRANTED + INTERNAL):
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DELETE FROM activity_event WHERE kind IN ('document.added', 'document.removed')")
    op.execute("DROP TABLE IF EXISTS record_document")
