"""026: complaint remedies (FS-015b): a refund through the approval engine, a free
replacement order, or none; the complaint closes on the remedy.

The engine functions are patched from their live text by exact anchors, as 016 and
017 did: an anchor that is not found exactly once raises, so a changed function is
a failed migration, never a silently unwired arm.

PostgreSQL refuses a new enum value anywhere but inside a function body in the
transaction that added it, so `ck_complaint_closed` is 027's.

Revision ID: 026_complaint_remedies
Revises: 025_subsidy_applications
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

from alembic import op

revision = "026_complaint_remedies"
down_revision = "025_subsidy_applications"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# FS-015b D2: the refund ladder's stand-in ceilings, in rupees; NULL is uncapped
REFUND_LIMITS = {"district_manager": "25000", "state_manager": "100000", "regional_manager": None}

NEW_KINDS = ("complaint.refund_requested", "complaint.refund_paid", "complaint.refund_rejected",
             "complaint.closed")


def _load(stem: str) -> ModuleType:
    path = next(Path(__file__).parent.glob(f"{stem}_*.py"))
    spec = importlib.util.spec_from_file_location(f"mig_{stem}_for_026", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"026: migration {stem} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    # an exception, not an assert: python -O drops asserts
    if text.count(old) != 1:
        raise RuntimeError(f"026: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


def _or_replace(text: str) -> str:
    return text.replace("CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1)


def _named(texts: list[str], name: str) -> str:
    return next(t for t in texts if re.search(rf"FUNCTION\s+{name}\(", t))


# ── tables ───────────────────────────────────────────────────────────────────

TABLES = [
    "ALTER TYPE complaint_status ADD VALUE IF NOT EXISTS 'remedy_pending'",
    "ALTER TYPE complaint_status ADD VALUE IF NOT EXISTS 'closed'",
    "ALTER TABLE complaint ADD COLUMN closed_at timestamptz",
    """CREATE TABLE complaint_remedy (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id uuid NOT NULL REFERENCES complaint(id),
    kind text NOT NULL CHECK (kind IN ('refund', 'replacement', 'none')),
    status text NOT NULL CHECK (status IN ('pending', 'completed', 'rejected', 'withdrawn', 'cancelled')),
    amount numeric(14,2) CHECK (amount IS NULL OR (amount > 0 AND amount < 1000000000000)),
    payee_name text CHECK (payee_name IS NULL OR length(btrim(payee_name)) BETWEEN 1 AND 200),
    paid_through_partner_id uuid REFERENCES channel_partner(id),
    approval_request_id uuid REFERENCES approval_request(id),
    sales_order_id uuid REFERENCES sales_order(id),
    remark text NOT NULL CHECK (length(btrim(remark)) BETWEEN 1 AND 1000),
    payment_reference text CHECK (payment_reference IS NULL OR length(payment_reference) <= 1000),
    chosen_by uuid NOT NULL REFERENCES app_user(id),
    chosen_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CONSTRAINT ck_complaint_remedy_kind CHECK (
        (kind = 'refund' AND amount IS NOT NULL AND payee_name IS NOT NULL AND approval_request_id IS NOT NULL AND sales_order_id IS NULL)
        OR (kind = 'replacement' AND sales_order_id IS NOT NULL AND amount IS NULL AND approval_request_id IS NULL AND paid_through_partner_id IS NULL)
        OR (kind = 'none' AND amount IS NULL AND approval_request_id IS NULL AND sales_order_id IS NULL AND status = 'completed')),
    CONSTRAINT ck_complaint_remedy_done CHECK ((status = 'pending') = (completed_at IS NULL))
)""",
    "CREATE INDEX ix_complaint_remedy_complaint ON complaint_remedy (complaint_id)",
    # one live remedy per complaint (rule 2)
    "CREATE UNIQUE INDEX uq_complaint_remedy_live ON complaint_remedy (complaint_id) WHERE status = 'pending'",
    "CREATE UNIQUE INDEX uq_complaint_remedy_order ON complaint_remedy (sales_order_id) WHERE sales_order_id IS NOT NULL",
    "CREATE INDEX ix_complaint_remedy_request ON complaint_remedy (approval_request_id)",
    "CREATE INDEX ix_complaint_remedy_chosen_by ON complaint_remedy (chosen_by)",
    "ALTER TABLE complaint_remedy ENABLE ROW LEVEL SECURITY",
    "CREATE TRIGGER trg_complaint_remedy_audit AFTER INSERT OR UPDATE OR DELETE ON complaint_remedy FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

# tests/db/migration_grants.py reads these two, as it does every migration's
GRANTS: dict[str, str] = {"complaint_remedy": "SELECT"}

# a complaint's refund request is read by whoever sees the complaint (plan review B2)
APPROVAL_REQUEST_SEL = """CREATE POLICY approval_request_sel ON approval_request FOR SELECT USING (
  CASE doc_type
    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order d WHERE d.id = entity_id)
    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation d WHERE d.id = entity_id)
    WHEN 'complaint' THEN EXISTS (SELECT 1 FROM complaint d WHERE d.id = entity_id)
    ELSE (SELECT app_is_system())
  END
)"""

HAND_POLICIES: list[tuple[str, str]] = [
    ("complaint_remedy", "CREATE POLICY complaint_remedy_sel ON complaint_remedy FOR SELECT USING (EXISTS (SELECT 1 FROM complaint c WHERE c.id = complaint_id))"),
    ("approval_request", APPROVAL_REQUEST_SEL),
]

# ── new functions ────────────────────────────────────────────────────────────

_REMEDY_GATE = """
    v_reason := complaint_refusal(p_complaint, '{action}');
    IF v_reason = 'not_visible' THEN
        RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'CMPNF';
    ELSIF v_reason IN ('not_qc_approved', 'not_remedy_pending') THEN
        RAISE EXCEPTION 'the complaint moved on' USING ERRCODE = 'CMPSC';
    ELSIF v_reason IS NOT NULL THEN
        RAISE EXCEPTION '%', v_reason USING ERRCODE = 'CMPRF';
    END IF;"""

FUNCTIONS = [
    """CREATE FUNCTION complaint_close(p_complaint uuid, p_how text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_lead uuid;
BEGIN
    UPDATE complaint SET status = 'closed', closed_at = now(), updated_by = app_current_user_id()
     WHERE id = p_complaint RETURNING lead_id INTO v_lead;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('complaint', p_complaint, v_lead, 'complaint.closed', app_current_user_id(),
            jsonb_build_object('how', p_how));
END $fn$""",
    # a refund's last step (rules 5 and 8); called by apply_approval_outcome under
    # record_decision's complaint lock
    """CREATE FUNCTION complaint_refund_outcome(p_complaint uuid, p_outcome text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE m complaint_remedy%ROWTYPE; v_ref text; v_lead uuid;
BEGIN
    SELECT * INTO m FROM complaint_remedy
     WHERE complaint_id = p_complaint AND status = 'pending' AND kind = 'refund' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'request_closed' USING ERRCODE = 'APRCL';
    END IF;
    SELECT lead_id INTO v_lead FROM complaint WHERE id = p_complaint;
    IF p_outcome = 'approve' THEN
        SELECT s.remark INTO v_ref FROM approval_step s JOIN role r ON r.id = s.approver_role_id
         WHERE s.request_id = m.approval_request_id AND r.code = 'account_manager'
         ORDER BY s.seq DESC LIMIT 1;
        UPDATE complaint_remedy SET status = 'completed', completed_at = now(), payment_reference = v_ref
         WHERE id = m.id;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('complaint', p_complaint, v_lead, 'complaint.refund_paid', app_current_user_id(),
                jsonb_build_object('amount', m.amount));
        PERFORM complaint_close(p_complaint, 'refund');
    ELSE
        UPDATE complaint_remedy SET status = 'rejected', completed_at = now() WHERE id = m.id;
        UPDATE complaint SET status = 'qc_approved', updated_by = app_current_user_id() WHERE id = p_complaint;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('complaint', p_complaint, v_lead, 'complaint.refund_rejected', app_current_user_id(),
                jsonb_build_object('amount', m.amount));
    END IF;
END $fn$""",
    # a replacement order moved: shipped closes, cancelled or closed-short-empty
    # reopens the choice; a finished remedy is left alone (edge case 4). Called by
    # the order paths, which already hold the order: order, then complaint (B-8)
    """CREATE FUNCTION complaint_replacement_progress(p_order uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE m complaint_remedy%ROWTYPE; v_complaint uuid; v_status text; v_shipped boolean; v_lead uuid;
BEGIN
    SELECT complaint_id INTO v_complaint FROM complaint_remedy
     WHERE sales_order_id = p_order AND status = 'pending';
    IF v_complaint IS NULL THEN
        RETURN;
    END IF;
    PERFORM 1 FROM complaint WHERE id = v_complaint FOR UPDATE;
    SELECT * INTO m FROM complaint_remedy WHERE sales_order_id = p_order AND status = 'pending' FOR UPDATE;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    SELECT status::text INTO v_status FROM sales_order WHERE id = p_order;
    v_shipped := EXISTS (SELECT 1 FROM dispatch d WHERE d.sales_order_id = p_order AND d.voided_at IS NULL);
    SELECT lead_id INTO v_lead FROM complaint WHERE id = v_complaint;
    IF v_status = 'dispatched' OR (v_status = 'closed_short' AND v_shipped) THEN
        UPDATE complaint_remedy SET status = 'completed', completed_at = now() WHERE id = m.id;
        PERFORM complaint_close(v_complaint, 'replacement');
    ELSIF v_status = 'cancelled' OR (v_status = 'closed_short' AND NOT v_shipped) THEN
        UPDATE complaint_remedy SET status = 'cancelled', completed_at = now() WHERE id = m.id;
        UPDATE complaint SET status = 'qc_approved', updated_by = app_current_user_id() WHERE id = v_complaint;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('complaint', v_complaint, v_lead, 'complaint.replacement_cancelled', app_current_user_id(),
                jsonb_build_object('sales_order_id', p_order, 'order_status', v_status));
    END IF;
END $fn$""",
    # a refund (into the engine) or no action (closed at once): rules 1 to 4
    """CREATE FUNCTION complaint_remedy_choose(p_complaint uuid, p_kind text, p_amount numeric,
        p_payee text, p_partner uuid, p_remark text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); c complaint%ROWTYPE; v_reason text; v_remark text;
    v_remedy uuid; v_chain uuid[]; v_request uuid; v_role uuid; v_code text; i int;
BEGIN
    IF p_kind NOT IN ('refund', 'none') THEN
        RAISE EXCEPTION 'kind' USING ERRCODE = 'CMPRV';
    END IF;
    SELECT * INTO c FROM complaint WHERE id = p_complaint AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'CMPNF';
    END IF;""" + _REMEDY_GATE.format(action="remedy") + """
    v_remark := NULLIF(btrim(p_remark), '');
    IF v_remark IS NULL OR length(v_remark) > 1000 THEN
        RAISE EXCEPTION 'remark' USING ERRCODE = 'CMPRV';
    END IF;
    IF p_kind = 'none' THEN
        INSERT INTO complaint_remedy (complaint_id, kind, status, remark, chosen_by, completed_at)
        VALUES (c.id, 'none', 'completed', v_remark, v_me, now()) RETURNING id INTO v_remedy;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('complaint', c.id, c.lead_id, 'complaint.remedy_chosen', v_me, jsonb_build_object('kind', 'none'));
        PERFORM complaint_close(c.id, 'none');
        RETURN v_remedy;
    END IF;
    IF p_amount IS NULL OR p_amount <= 0 OR p_amount >= 1000000000000 OR p_amount <> round(p_amount, 2) THEN
        RAISE EXCEPTION 'amount' USING ERRCODE = 'CMPRV';
    END IF;
    IF NULLIF(btrim(p_payee), '') IS NULL OR length(btrim(p_payee)) > 200 THEN
        RAISE EXCEPTION 'payee_name' USING ERRCODE = 'CMPRV';
    END IF;
    IF p_partner IS NOT NULL AND NOT EXISTS (SELECT 1 FROM channel_partner WHERE id = p_partner AND deleted_at IS NULL) THEN
        RAISE EXCEPTION 'paid_through_partner_id' USING ERRCODE = 'CMPRV';
    END IF;
    v_chain := approval_chain('complaint', p_amount, c.territory_id, COALESCE(approval_owner_level(c.owner_user_id), 0));
    FOREACH v_role IN ARRAY v_chain LOOP
        SELECT code INTO v_code FROM role WHERE id = v_role AND (is_functional OR is_portal);
        IF FOUND AND NOT EXISTS (SELECT 1 FROM app_user WHERE role_id = v_role AND is_active AND deleted_at IS NULL) THEN
            RAISE EXCEPTION 'no active user holds %', v_code USING ERRCODE = 'ORDNA';
        END IF;
    END LOOP;
    INSERT INTO approval_request (doc_type, entity_id, requested_by, amount, territory_id, remark)
    VALUES ('complaint', c.id, v_me, p_amount, c.territory_id, v_remark)
    RETURNING id INTO v_request;
    FOR i IN 1 .. array_length(v_chain, 1) LOOP
        INSERT INTO approval_step (request_id, seq, approver_role_id) VALUES (v_request, i, v_chain[i]);
    END LOOP;
    INSERT INTO complaint_remedy (complaint_id, kind, status, amount, payee_name, paid_through_partner_id,
                                  approval_request_id, remark, chosen_by)
    VALUES (c.id, 'refund', 'pending', p_amount, btrim(p_payee), p_partner, v_request, v_remark, v_me)
    RETURNING id INTO v_remedy;
    UPDATE complaint SET status = 'remedy_pending', updated_by = v_me WHERE id = c.id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('complaint', c.id, c.lead_id, 'complaint.refund_requested', v_me,
            jsonb_build_object('request', v_request, 'amount', p_amount, 'remedy_id', v_remedy));
    RETURN v_remedy;
END $fn$""",
    # the free order (plan review B3): Python priced the lines under the QC claim;
    # this inserts a draft, its lines, the figures, submits it as order_submit does
    # and opens the one Dispatch step (D3)
    """CREATE FUNCTION complaint_remedy_replacement(p_complaint uuid, p_order jsonb, p_lines jsonb,
        p_remark text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); c complaint%ROWTYPE; v_reason text; v_remark text;
    v_order uuid; v_no text; v_state text; v_day date; v_y int; v_fy text; v_seller record;
    v_role uuid; v_request uuid; v_remedy uuid; v_total numeric;
BEGIN
    SELECT * INTO c FROM complaint WHERE id = p_complaint AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'CMPNF';
    END IF;""" + _REMEDY_GATE.format(action="remedy") + """
    v_remark := NULLIF(btrim(p_remark), '');
    IF v_remark IS NULL OR length(v_remark) > 1000 THEN
        RAISE EXCEPTION 'remark' USING ERRCODE = 'CMPRV';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM complaint_line WHERE complaint_id = c.id AND defective_qty > 0) THEN
        RAISE EXCEPTION 'nothing defective' USING ERRCODE = 'CMPZD';
    END IF;
    -- the lines are exactly the defective lines, each once, and free. EXCEPT ALL:
    -- a duplicated line must not pass as the set it collapses to (PR 38 review)
    IF EXISTS (
        (SELECT product_id, defective_qty FROM complaint_line WHERE complaint_id = c.id AND defective_qty > 0)
        EXCEPT ALL
        (SELECT x.product_id, x.qty FROM jsonb_to_recordset(p_lines) AS x(product_id uuid, qty numeric)))
       OR EXISTS (
        (SELECT x.product_id, x.qty FROM jsonb_to_recordset(p_lines) AS x(product_id uuid, qty numeric))
        EXCEPT ALL
        (SELECT product_id, defective_qty FROM complaint_line WHERE complaint_id = c.id AND defective_qty > 0))
       OR EXISTS (SELECT 1 FROM jsonb_to_recordset(p_lines) AS x(total numeric) WHERE x.total IS DISTINCT FROM 0)
       OR (p_order ->> 'total')::numeric IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION 'lines' USING ERRCODE = 'CMPRV';
    END IF;
    SELECT id INTO v_role FROM role WHERE code = 'dispatch_manager' AND deleted_at IS NULL;
    IF v_role IS NULL OR NOT EXISTS (SELECT 1 FROM app_user WHERE role_id = v_role AND is_active AND deleted_at IS NULL) THEN
        RAISE EXCEPTION 'no active user holds dispatch_manager' USING ERRCODE = 'ORDNA';
    END IF;
    INSERT INTO sales_order (order_type, lead_id, partner_id, party_name, party_mobile, owner_user_id,
        owner_org_unit_id, territory_id, seller_gstin_id, place_of_supply_territory_id,
        place_of_supply_state_id, intra_state, price_effective_date, remarks, created_by, updated_by)
    VALUES ('replacement', c.lead_id, c.partner_id, c.contact_name, c.contact_mobile, c.owner_user_id,
        c.owner_org_unit_id, c.territory_id, (p_order ->> 'seller_gstin_id')::uuid,
        (p_order ->> 'place_of_supply_territory_id')::uuid, (p_order ->> 'place_of_supply_state_id')::uuid,
        (p_order ->> 'intra_state')::boolean, (p_order ->> 'price_effective_date')::date,
        'Replacement for complaint ' || c.complaint_no, v_me, v_me)
    RETURNING id INTO v_order;
    INSERT INTO order_line (sales_order_id, line_no, product_id, description, hsn_code, uom, uom_decimals,
        qty, rate, price_list_id, price_list_item_id, gst_rate_id, gross, discount_pct, discount1_amt,
        after_discount1, discount2_pct, discount2_amt, after_discount2, discount3_pct, discount3_amt,
        discount, taxable, gst_slab, cgst_rate, sgst_rate, igst_rate, cgst, sgst, igst, total,
        provisional_fields)
    SELECT v_order, x.line_no, x.product_id, x.description, x.hsn_code, x.uom, x.uom_decimals, x.qty, x.rate,
           x.price_list_id, x.price_list_item_id, x.gst_rate_id, x.gross, x.discount_pct, x.discount1_amt,
           x.after_discount1, x.discount2_pct, x.discount2_amt, x.after_discount2, x.discount3_pct,
           x.discount3_amt, x.discount, x.taxable, x.gst_slab, x.cgst_rate, x.sgst_rate, x.igst_rate,
           x.cgst, x.sgst, x.igst, x.total, x.provisional_fields
      FROM jsonb_to_recordset(p_lines) AS x(line_no int, product_id uuid, description text, hsn_code text,
           uom text, uom_decimals smallint, qty numeric, rate numeric, price_list_id uuid,
           price_list_item_id uuid, gst_rate_id uuid, gross numeric, discount_pct numeric,
           discount1_amt numeric, after_discount1 numeric, discount2_pct numeric, discount2_amt numeric,
           after_discount2 numeric, discount3_pct numeric, discount3_amt numeric, discount numeric,
           taxable numeric, gst_slab numeric, cgst_rate numeric, sgst_rate numeric, igst_rate numeric,
           cgst numeric, sgst numeric, igst numeric, total numeric, provisional_fields text[]);
    UPDATE sales_order SET price_list_id = (p_order ->> 'price_list_id')::uuid,
           gross = (p_order ->> 'gross')::numeric, discount = (p_order ->> 'discount')::numeric,
           taxable = (p_order ->> 'taxable')::numeric, cgst = (p_order ->> 'cgst')::numeric,
           sgst = (p_order ->> 'sgst')::numeric, igst = (p_order ->> 'igst')::numeric,
           total = (p_order ->> 'total')::numeric, is_provisional = (p_order ->> 'is_provisional')::boolean
     WHERE id = v_order
    RETURNING total INTO v_total;
    -- order_submit's numbering and seller snapshot, without its permission gate
    v_day := (now() AT TIME ZONE 'Asia/Kolkata')::date;
    SELECT t.code::text INTO v_state
      FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id
     WHERE tc.descendant_id = c.territory_id AND t.level = 'state'
     ORDER BY tc.depth ASC LIMIT 1;
    IF v_state IS NULL THEN
        RAISE EXCEPTION 'the order territory has no coded state' USING ERRCODE = 'ORDST';
    END IF;
    v_y := CASE WHEN extract(month FROM v_day) >= 4 THEN extract(year FROM v_day)::int
                ELSE extract(year FROM v_day)::int - 1 END;
    v_fy := v_y::text || '-' || lpad(((v_y + 1) % 100)::text, 2, '0');
    v_no := order_allocate_no(v_state, v_fy);
    SELECT sg.gstin, sg.legal_name, sg.address, st.code::text AS state_code INTO v_seller
      FROM sales_order o JOIN seller_gstin sg ON sg.id = o.seller_gstin_id
      JOIN territory st ON st.id = sg.state_territory_id
     WHERE o.id = v_order;
    UPDATE sales_order
       SET status = 'submitted', order_no = v_no, submitted_at = now(), tax_date = v_day,
           seller_gstin_no = v_seller.gstin, seller_legal_name = v_seller.legal_name,
           seller_address = v_seller.address, seller_state_code = v_seller.state_code
     WHERE id = v_order;
    INSERT INTO approval_request (doc_type, entity_id, requested_by, amount, territory_id)
    VALUES ('sales_order', v_order, v_me, v_total, c.territory_id) RETURNING id INTO v_request;
    INSERT INTO approval_step (request_id, seq, approver_role_id) VALUES (v_request, 1, v_role);
    INSERT INTO complaint_remedy (complaint_id, kind, status, sales_order_id, remark, chosen_by)
    VALUES (c.id, 'replacement', 'pending', v_order, v_remark, v_me) RETURNING id INTO v_remedy;
    UPDATE complaint SET status = 'remedy_pending', updated_by = v_me WHERE id = c.id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('sales_order', v_order, c.lead_id, 'order.created', v_me,
            jsonb_build_object('lines', jsonb_array_length(p_lines), 'complaint_id', c.id)),
           ('sales_order', v_order, c.lead_id, 'order.submitted', v_me,
            jsonb_build_object('request', v_request, 'order_no', v_no)),
           ('complaint', c.id, c.lead_id, 'complaint.replacement_ordered', v_me,
            jsonb_build_object('sales_order_id', v_order, 'order_no', v_no, 'remedy_id', v_remedy));
    PERFORM order_notify_step(v_request);
    RETURN v_order;
END $fn$""",
    # QC withdraws (§3). One lock order for every path touching an order and a
    # complaint: the order first (delta B-8). The order id is read unlocked: a
    # remedy's order never changes once set.
    """CREATE FUNCTION complaint_remedy_withdraw(p_complaint uuid, p_remark text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); v_reason text; v_remark text; v_order uuid;
    m complaint_remedy%ROWTYPE; c complaint%ROWTYPE; v_req approval_request%ROWTYPE;
BEGIN""" + _REMEDY_GATE.format(action="withdraw") + """
    v_remark := NULLIF(btrim(p_remark), '');
    IF v_remark IS NULL OR length(v_remark) > 1000 THEN
        RAISE EXCEPTION 'remark' USING ERRCODE = 'CMPRV';
    END IF;
    SELECT sales_order_id INTO v_order FROM complaint_remedy WHERE complaint_id = p_complaint AND status = 'pending';
    IF v_order IS NOT NULL THEN
        PERFORM 1 FROM sales_order WHERE id = v_order FOR UPDATE;
    END IF;
    SELECT * INTO c FROM complaint WHERE id = p_complaint FOR UPDATE;
    SELECT * INTO m FROM complaint_remedy WHERE complaint_id = p_complaint AND status = 'pending' FOR UPDATE;
    -- the order read before the locks may belong to a remedy since replaced: then
    -- this one's order is not locked, and the order-first rule would break (PR 38 review)
    IF NOT FOUND OR c.status <> 'remedy_pending' OR m.sales_order_id IS DISTINCT FROM v_order THEN
        RAISE EXCEPTION 'the remedy moved on' USING ERRCODE = 'CMPSC';
    END IF;
    IF m.kind = 'refund' THEN
        SELECT * INTO v_req FROM approval_request WHERE id = m.approval_request_id FOR UPDATE;
        IF v_req.status <> 'pending' THEN
            RAISE EXCEPTION 'the refund was decided' USING ERRCODE = 'CMPSC';
        END IF;
        UPDATE approval_request SET status = 'cancelled', decided_at = now() WHERE id = v_req.id;
    ELSE
        IF EXISTS (SELECT 1 FROM dispatch d WHERE d.sales_order_id = m.sales_order_id AND d.voided_at IS NULL) THEN
            RAISE EXCEPTION 'the replacement has shipped' USING ERRCODE = 'CMPSC';
        END IF;
        UPDATE approval_request SET status = 'cancelled', decided_at = now()
         WHERE doc_type = 'sales_order' AND entity_id = m.sales_order_id AND status = 'pending';
        UPDATE sales_order SET status = 'cancelled', cancelled_at = now(),
               cancel_remark = 'Remedy withdrawn: ' || v_remark, updated_by = v_me
         WHERE id = m.sales_order_id AND status NOT IN ('cancelled', 'dispatched', 'closed_short');
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('sales_order', m.sales_order_id, c.lead_id, 'order.replacement_cancelled', v_me,
                jsonb_build_object('from', 'remedy_withdrawn'));
    END IF;
    UPDATE complaint_remedy SET status = 'withdrawn', completed_at = now() WHERE id = m.id;
    UPDATE complaint SET status = 'qc_approved', updated_by = v_me WHERE id = c.id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('complaint', c.id, c.lead_id, 'complaint.remedy_withdrawn', v_me,
            jsonb_build_object('kind', m.kind));
END $fn$""",
    # the replacement order of a remedy, for whoever sees the complaint
    """CREATE FUNCTION complaint_remedy_order(p_remedy uuid)
RETURNS TABLE (id uuid, order_no text, status text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT o.id, o.order_no::text, o.status::text
      FROM complaint_remedy m JOIN sales_order o ON o.id = m.sales_order_id
     WHERE m.id = p_remedy AND complaint_visible(m.complaint_id)
$fn$""",
    # an order's complaint, for whoever sees the order (delta R-1)
    """CREATE FUNCTION order_complaint(p_order uuid)
RETURNS TABLE (id uuid, complaint_no text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT c.id, c.complaint_no::text
      FROM complaint_remedy m JOIN complaint c ON c.id = m.complaint_id
     WHERE m.sales_order_id = p_order AND order_visible(p_order)
$fn$""",
]

GRANTED = [
    "complaint_remedy_choose(uuid, text, numeric, text, uuid, text)",
    "complaint_remedy_replacement(uuid, jsonb, jsonb, text)",
    "complaint_remedy_withdraw(uuid, text)",
    "complaint_remedy_order(uuid)",
    "order_complaint(uuid)",
]
INTERNAL = ["complaint_close(uuid, text)", "complaint_refund_outcome(uuid, text)",
            "complaint_replacement_progress(uuid)"]


# ── patches to live functions ────────────────────────────────────────────────

def _engine_live() -> list[str]:
    """The seven engine functions after 017, in 017's order."""
    return _load("017")._patched()


def _orders_live() -> dict[str, str]:
    m016 = _load("016")
    return {n: _or_replace(m016._original(n))
            for n in ("dispatch_record", "dispatch_void", "order_close_short", "order_cancel")}


def _notify_outcome_live() -> str:
    return _or_replace(_named(_load("016").FUNCTIONS, "order_notify_outcome"))


def _refusal_live() -> str:
    return _or_replace(_named(_load("019").FUNCTIONS, "complaint_refusal"))


def _people_live() -> str:
    return _or_replace(_named(_load("019")._after(), "people_names"))


def _bell_live() -> dict[str, str]:
    m023 = _load("023")
    return {n: _or_replace(_named(m023.FUNCTIONS, n)) for n in ("notify_step", "notify_from_event")}


def _engine_patched() -> list[str]:
    out = []
    for f in _engine_live():
        name = re.search(r"FUNCTION\s+(\w+)\(", f).group(1)  # type: ignore[union-attr]
        if name == "approval_chain":
            # a refund ends with Accounts, never Dispatch (FS-015b D2)
            f = _replace(f, "      FROM role WHERE code IN ('account_manager', 'dispatch_manager') AND deleted_at IS NULL;",
                         "      FROM role WHERE code IN ('account_manager', 'dispatch_manager') AND deleted_at IS NULL\n"
                         "       AND (p_doc_type <> 'complaint' OR code = 'account_manager');")
        elif name == "approval_step_stalled":
            f = _replace(f, "    ELSE\n        SELECT owner_org_unit_id, owner_user_id, created_by INTO v_org, v_owner, v_creator\n          FROM sales_order WHERE id = v_req.entity_id;",
                         "    ELSIF v_req.doc_type = 'complaint' THEN\n"
                         "        SELECT owner_org_unit_id, owner_user_id, raised_by INTO v_org, v_owner, v_creator\n"
                         "          FROM complaint WHERE id = v_req.entity_id;\n"
                         "    ELSE\n        SELECT owner_org_unit_id, owner_user_id, created_by INTO v_org, v_owner, v_creator\n          FROM sales_order WHERE id = v_req.entity_id;")
        elif name == "approval_refusal":
            f = _replace(f, "        SELECT owner_user_id, created_by INTO v_owner, v_creator FROM sales_order WHERE id = v_req.entity_id;\n    ELSE",
                         "        SELECT owner_user_id, created_by INTO v_owner, v_creator FROM sales_order WHERE id = v_req.entity_id;\n"
                         "    ELSIF v_req.doc_type = 'complaint' THEN\n"
                         "        SELECT owner_user_id, raised_by INTO v_owner, v_creator FROM complaint WHERE id = v_req.entity_id;\n"
                         "    ELSE")
            # line steps need complaints.approve; the Accounts step its role alone
            f = _replace(f, "    ELSIF NOT order_visible(v_req.entity_id) OR NOT app_has_permission('sales_orders', 'approve') THEN",
                         "    ELSIF v_req.doc_type = 'complaint' THEN\n"
                         "        IF NOT complaint_visible(v_req.entity_id)\n"
                         "           OR (v_step_line AND NOT app_has_permission('complaints', 'approve')) THEN\n"
                         "            RETURN 'not_your_step';\n"
                         "        END IF;\n"
                         "    ELSIF NOT order_visible(v_req.entity_id) OR NOT app_has_permission('sales_orders', 'approve') THEN")
        elif name == "create_approval_request":
            # only complaint_remedy_replacement opens a replacement's request (B4)
            f = _replace(f, "    SELECT * INTO v_order FROM sales_order WHERE id = p_entity_id FOR UPDATE;\n",
                         "    SELECT * INTO v_order FROM sales_order WHERE id = p_entity_id FOR UPDATE;\n"
                         "    IF v_order.order_type = 'replacement' THEN\n"
                         "        RAISE EXCEPTION 'a replacement order is opened by its complaint' USING ERRCODE = '0A000';\n"
                         "    END IF;\n")
        elif name == "apply_approval_outcome":
            f = _replace(f, "    IF p_doc_type <> 'sales_order' THEN",
                         "    IF p_doc_type = 'complaint' THEN\n"
                         "        PERFORM complaint_refund_outcome(p_entity_id, p_outcome);\n"
                         "        RETURN;\n"
                         "    END IF;\n"
                         "    IF p_doc_type <> 'sales_order' THEN")
            # a rejected replacement is cancelled, never an editable draft (B4)
            f = _replace(f, "    UPDATE sales_order\n       SET status = CASE p_outcome",
                         "    IF p_outcome <> 'approve' AND EXISTS (SELECT 1 FROM sales_order WHERE id = p_entity_id\n"
                         "                                            AND order_type = 'replacement' AND status = 'submitted') THEN\n"
                         "        UPDATE sales_order SET status = 'cancelled', cancelled_at = now(),\n"
                         "               cancel_remark = 'Rejected at approval', updated_by = app_current_user_id()\n"
                         "         WHERE id = p_entity_id;\n"
                         "        PERFORM complaint_replacement_progress(p_entity_id);\n"
                         "        RETURN;\n"
                         "    END IF;\n"
                         "    UPDATE sales_order\n       SET status = CASE p_outcome")
        elif name == "advance_approval":
            f = _replace(f, "    SELECT lead_id INTO v_lead FROM sales_order WHERE id = v_req.entity_id;\n",
                         "    IF v_req.doc_type = 'complaint' THEN\n"
                         "        IF v_rejected > 0 THEN\n"
                         "            UPDATE approval_request SET status = 'rejected', decided_at = now() WHERE id = p_request_id;\n"
                         "            PERFORM apply_approval_outcome(v_req.doc_type, v_req.entity_id, 'reject');\n"
                         "            RETURN 'rejected';\n"
                         "        END IF;\n"
                         "        IF v_approved < v_total THEN\n"
                         "            RETURN 'pending';\n"
                         "        END IF;\n"
                         "        UPDATE approval_request SET status = 'approved', decided_at = now() WHERE id = p_request_id;\n"
                         "        PERFORM apply_approval_outcome(v_req.doc_type, v_req.entity_id, 'approve');\n"
                         "        RETURN 'approved';\n"
                         "    END IF;\n"
                         "    SELECT lead_id INTO v_lead FROM sales_order WHERE id = v_req.entity_id;\n")
            # code review F-1: a rejected replacement was cancelled, not returned
            f = _replace(f, "        PERFORM apply_approval_outcome(v_req.doc_type, v_req.entity_id, 'reject');\n"
                            "        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)\n"
                            "        VALUES ('sales_order', v_req.entity_id, v_lead, 'order.returned', app_current_user_id(), '{}');\n",
                         "        PERFORM apply_approval_outcome(v_req.doc_type, v_req.entity_id, 'reject');\n"
                         "        IF EXISTS (SELECT 1 FROM sales_order WHERE id = v_req.entity_id AND order_type = 'replacement') THEN\n"
                         "            INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)\n"
                         "            VALUES ('sales_order', v_req.entity_id, v_lead, 'order.replacement_cancelled', app_current_user_id(),\n"
                         "                    jsonb_build_object('from', 'approval_rejected'));\n"
                         "            RETURN 'rejected';\n"
                         "        END IF;\n"
                         "        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)\n"
                         "        VALUES ('sales_order', v_req.entity_id, v_lead, 'order.returned', app_current_user_id(), '{}');\n")
        elif name == "record_decision":
            # the complaint first, then the request, then the step (edge case 2)
            f = _replace(f, "    ELSIF v_doc_type = 'quotation' THEN\n        SELECT lead_id INTO v_lead FROM quotation WHERE id = v_entity;",
                         "    ELSIF v_doc_type = 'complaint' THEN\n"
                         "        SELECT lead_id INTO v_lead FROM complaint WHERE id = v_entity FOR UPDATE;\n"
                         "    ELSIF v_doc_type = 'quotation' THEN\n        SELECT lead_id INTO v_lead FROM quotation WHERE id = v_entity;")
            f = _replace(f, "    IF v_doc_type = 'quotation' AND NOT EXISTS (SELECT 1 FROM quotation WHERE id = v_entity",
                         "    IF v_doc_type = 'complaint' AND NOT EXISTS (\n"
                         "        SELECT 1 FROM complaint c JOIN complaint_remedy m ON m.complaint_id = c.id\n"
                         "         WHERE c.id = v_entity AND c.status = 'remedy_pending' AND m.status = 'pending'\n"
                         "           AND m.approval_request_id = v_request) THEN\n"
                         "        RAISE EXCEPTION 'request_closed' USING ERRCODE = 'APRCL';\n"
                         "    END IF;\n"
                         "    IF v_doc_type = 'quotation' AND NOT EXISTS (SELECT 1 FROM quotation WHERE id = v_entity")
            f = _replace(f, "    VALUES (CASE WHEN v_doc_type = 'quotation' THEN 'quotation' ELSE 'sales_order' END,",
                         "    VALUES (CASE v_doc_type WHEN 'quotation' THEN 'quotation' WHEN 'complaint' THEN 'complaint' ELSE 'sales_order' END,")
        out.append(f)
    return out


def _orders_patched() -> list[str]:
    f = _orders_live()
    f["dispatch_record"] = _replace(f["dispatch_record"], "    RETURN v_dispatch;\nEND $fn$",
                                    "    PERFORM complaint_replacement_progress(p_order_id);\n    RETURN v_dispatch;\nEND $fn$")
    f["dispatch_void"] = _replace(f["dispatch_void"], "    RETURN v_status;\nEND $fn$",
                                  "    PERFORM complaint_replacement_progress(v_order_id);\n    RETURN v_status;\nEND $fn$")
    f["order_close_short"] = _replace(f["order_close_short"], "'order.closed_short', v_me, '{}');\nEND $fn$",
                                      "'order.closed_short', v_me, '{}');\n    PERFORM complaint_replacement_progress(p_order_id);\nEND $fn$")
    f["order_cancel"] = _replace(f["order_cancel"], "    RETURN 'cancelled';\nEND $fn$",
                                 "    PERFORM complaint_replacement_progress(p_order_id);\n    RETURN 'cancelled';\nEND $fn$")
    notify = _replace(_notify_outcome_live(), "        IF v_tpl IS NULL THEN\n            v_conf := 'disabled';",
                      # no "order confirmed, ₹0.00" to the farmer (D9)
                      "        IF v_tpl IS NULL OR o.order_type = 'replacement' THEN\n            v_conf := 'disabled';")
    return [*f.values(), notify]


def _refusal_patched() -> str:
    return _replace(_refusal_live(),
                    "        RETURN NULL;\n    END IF;\n    RAISE EXCEPTION 'unknown complaint action %'",
                    "        RETURN NULL;\n"
                    "    ELSIF p_action IN ('remedy', 'withdraw') THEN\n"
                    "        -- FS-015b D1: whoever may give the QC verdict, not the raiser or owner\n"
                    "        IF p_action = 'remedy' AND c.status::text <> 'qc_approved' THEN RETURN 'not_qc_approved'; END IF;\n"
                    "        IF p_action = 'withdraw' AND c.status::text <> 'remedy_pending' THEN RETURN 'not_remedy_pending'; END IF;\n"
                    "        IF NOT app_has_permission('complaints', 'approve') OR NOT COALESCE(v_functional, false) THEN\n"
                    "            RETURN 'not_qc';\n"
                    "        END IF;\n"
                    "        IF v_me IN (c.raised_by, c.owner_user_id) THEN RETURN 'self'; END IF;\n"
                    "        RETURN NULL;\n"
                    "    END IF;\n"
                    "    RAISE EXCEPTION 'unknown complaint action %'")


def _people_patched() -> str:
    return _replace(_people_live(),
                    "               OR EXISTS (SELECT 1 FROM complaint_decision cd\n"
                    "                           WHERE cd.decided_by = u.id AND complaint_visible(cd.complaint_id)))))",
                    "               OR EXISTS (SELECT 1 FROM complaint_decision cd\n"
                    "                           WHERE cd.decided_by = u.id AND complaint_visible(cd.complaint_id))\n"
                    "               -- FS-015b: a refund's approvers and the remedy's chooser, for staff\n"
                    "               OR EXISTS (SELECT 1 FROM approval_request r\n"
                    "                           LEFT JOIN approval_step s ON s.request_id = r.id\n"
                    "                           WHERE r.doc_type = 'complaint'\n"
                    "                             AND (s.approver_user_id = u.id OR r.requested_by = u.id)\n"
                    "                             AND complaint_visible(r.entity_id))\n"
                    "               OR EXISTS (SELECT 1 FROM complaint_remedy m\n"
                    "                           WHERE m.chosen_by = u.id AND complaint_visible(m.complaint_id)))))")


def _bell_patched() -> list[str]:
    f = _bell_live()
    f["notify_step"] = _replace(f["notify_step"], "    ELSE\n        v_type := 'quotation';",
                                "    ELSIF r.doc_type = 'complaint' THEN\n"
                                "        v_type := 'complaint';\n"
                                "        SELECT complaint_no::text INTO v_label FROM complaint WHERE id = r.entity_id;\n"
                                "        v_title := 'A refund on complaint ' || COALESCE(v_label, '') || ' waits for your approval';\n"
                                "    ELSE\n        v_type := 'quotation';")
    f["notify_from_event"] = _replace(f["notify_from_event"], "        WHEN 'order.submitted', 'quotation.approval_requested' THEN",
                                      "        WHEN 'order.submitted', 'quotation.approval_requested', 'complaint.refund_requested' THEN")
    f["notify_from_event"] = _replace(
        f["notify_from_event"],
        "        WHEN 'complaint.returned', 'complaint.qc_approved', 'complaint.qc_rejected' THEN\n"
        "            SELECT complaint_no::text, owner_user_id, raised_by INTO v_label, v_owner, v_who\n"
        "              FROM complaint WHERE id = e.entity_id;\n"
        "            v_title := 'Complaint ' || COALESCE(v_label, '') || CASE e.kind\n"
        "                WHEN 'complaint.returned' THEN ' was returned to you'\n"
        "                WHEN 'complaint.qc_approved' THEN ' passed the quality check'\n"
        "                ELSE ' failed the quality check' END;\n"
        "            FOREACH v_to IN ARRAY ARRAY[v_who, v_owner] LOOP",
        "        WHEN 'complaint.returned', 'complaint.qc_approved', 'complaint.qc_rejected',\n"
        "             'complaint.refund_paid', 'complaint.refund_rejected', 'complaint.closed' THEN\n"
        "            SELECT complaint_no::text, owner_user_id, raised_by INTO v_label, v_owner, v_who\n"
        "              FROM complaint WHERE id = e.entity_id;\n"
        "            v_title := 'Complaint ' || COALESCE(v_label, '') || CASE e.kind\n"
        "                WHEN 'complaint.returned' THEN ' was returned to you'\n"
        "                WHEN 'complaint.qc_approved' THEN ' passed the quality check'\n"
        "                WHEN 'complaint.refund_paid' THEN ': the refund was paid'\n"
        "                WHEN 'complaint.refund_rejected' THEN ': the refund was not approved'\n"
        "                WHEN 'complaint.closed' THEN ' is closed'\n"
        "                ELSE ' failed the quality check' END;\n"
        "            -- a refund's outcome also reaches whoever chose it (QC), read from the\n"
        "            -- remedy: a dealer reads the payload, so no person travels in it\n"
        "            IF e.kind IN ('complaint.refund_paid', 'complaint.refund_rejected') THEN\n"
        "                FOR v_to IN SELECT m.chosen_by FROM complaint_remedy m\n"
        "                             WHERE m.complaint_id = e.entity_id AND m.kind = 'refund'\n"
        "                             ORDER BY m.chosen_at DESC, m.id DESC LIMIT 1 LOOP\n"
        "                    PERFORM notify_one(e, v_to, replace(e.kind, '.', '_'),\n"
        "                                       v_title, NULL, 'complaint', e.entity_id, v_label, true);\n"
        "                END LOOP;\n"
        "            END IF;\n"
        "            FOREACH v_to IN ARRAY ARRAY[v_who, v_owner] LOOP")
    return list(f.values())


def _trigger(kinds: tuple[str, ...], quiet_refund_close: bool = False) -> str:
    # code review F-7: a paid refund already rang (`complaint.refund_paid`)
    quiet = (" AND NOT (NEW.kind = 'complaint.closed' AND NEW.payload ->> 'how' = 'refund')"
             if quiet_refund_close else "")
    return ("CREATE TRIGGER trg_notify_from_event AFTER INSERT ON activity_event FOR EACH ROW "
            "WHEN (NEW.kind IN (" + ", ".join(f"'{k}'" for k in kinds) + ")" + quiet + ") "
            "EXECUTE FUNCTION notify_from_event()")


def _seeds() -> list[str]:
    rows = ", ".join(f"('{code}', {('NULL' if v is None else v)})" for code, v in REFUND_LIMITS.items())
    return [
        f"""INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount)
SELECT 'complaint', r.id, NULL, v.max_amount
  FROM (VALUES {rows}) AS v(code, max_amount)
  JOIN role r ON r.code = v.code
ON CONFLICT (doc_type, role_id, territory_id) DO NOTHING""",
        # Accounts sees the refund it pays; not approve, which would let it give
        # QC verdicts (B7). The seed covers a fresh database (ISS-102).
        """INSERT INTO role_permission (role_id, module, action, scope)
SELECT r.id, 'complaints', 'view', 'global' FROM role r WHERE r.code = 'account_manager'
ON CONFLICT (role_id, module, action) DO NOTHING""",
    ]


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("DROP POLICY approval_request_sel ON approval_request")
    for _table, stmt in HAND_POLICIES:
        op.execute(stmt)
    op.execute(_refusal_patched())
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for stmt in _engine_patched() + _orders_patched() + [_people_patched()] + _bell_patched():
        op.execute(stmt)
    op.execute("DROP TRIGGER IF EXISTS trg_notify_from_event ON activity_event")
    op.execute(_trigger(_load("023").KINDS + NEW_KINDS, quiet_refund_close=True))
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    for stmt in _seeds():
        op.execute(stmt)


def downgrade() -> None:
    # the enum values stay: PostgreSQL cannot drop one. Rows using them go back.
    op.execute("DELETE FROM role_permission WHERE module = 'complaints' AND action = 'view' "
               "AND role_id IN (SELECT id FROM role WHERE code = 'account_manager')")
    op.execute("DROP TABLE complaint_remedy")
    op.execute("DELETE FROM approval_step WHERE request_id IN (SELECT id FROM approval_request WHERE doc_type = 'complaint')")
    op.execute("DELETE FROM approval_request WHERE doc_type = 'complaint'")
    op.execute("DELETE FROM approval_threshold WHERE doc_type = 'complaint'")
    op.execute("UPDATE complaint SET status = 'qc_approved' WHERE status::text IN ('remedy_pending', 'closed')")
    op.execute("DROP TRIGGER IF EXISTS trg_notify_from_event ON activity_event")
    op.execute(_trigger(_load("023").KINDS))
    for f in (_engine_live() + list(_orders_live().values()) + [_notify_outcome_live(), _refusal_live(),
              _people_live()] + list(_bell_live().values())):
        op.execute(f)
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("ALTER TABLE complaint DROP COLUMN closed_at")
    op.execute("DROP POLICY approval_request_sel ON approval_request")
    op.execute(_load("017").HAND_POLICIES[0][1])
