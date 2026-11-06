"""037: dealer commission and TOD, subsidy stage 18 (FS-033).

- `commission_rate`: by subsidy scheme, system, partner type or one partner,
  effective-dated. SELECT and INSERT only: a rate is never edited, a later one
  supersedes it, a 0% one retires it (rule 10).
- `dealer_commission`: one live row per application. Every figure is stored with the
  rate it used; nothing is recomputed on read.
- Definers for every write: `commission_record` (the State Co-ordinator, on an
  application with full FP received), `commission_decide` (Accounts approves, returns,
  cancels, marks paid). The self-approval rule is checked here, as complaints do,
  because the approval engine is the line hierarchy's threshold chain (ADR-042).
- Events go through `subsidy_event()`, so the application's timeline shows them.

Revision ID: 037_dealer_commission
Revises: 036_rewards
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "037_dealer_commission"
down_revision: str | None = "036_rewards"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

TABLES = [
    """CREATE TABLE commission_rate (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL REFERENCES subsidy_scheme(id),
    system_type text CHECK (system_type IS NULL OR system_type IN ('drip', 'mini_sprinkler', 'sprinkler')),
    partner_type text CHECK (partner_type IS NULL OR partner_type IN ('distributor', 'dealer', 'sub_dealer')),
    partner_id uuid REFERENCES channel_partner(id),
    commission_pct numeric(6,3) NOT NULL CHECK (commission_pct BETWEEN 0 AND 100),
    tod_pct numeric(6,3) NOT NULL CHECK (tod_pct BETWEEN 0 AND 100),
    effective_from date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES app_user(id),
    CONSTRAINT uq_commission_rate UNIQUE NULLS NOT DISTINCT (scheme_id, system_type, partner_type, partner_id, effective_from)
)""",
    "CREATE INDEX ix_commission_rate_partner ON commission_rate (partner_id) WHERE partner_id IS NOT NULL",
    """CREATE TABLE dealer_commission (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL REFERENCES subsidy_application(id),
    partner_id uuid NOT NULL REFERENCES channel_partner(id),
    rate_id uuid NOT NULL REFERENCES commission_rate(id),
    status text NOT NULL DEFAULT 'calculated'
        CHECK (status IN ('calculated', 'approved', 'returned', 'paid', 'cancelled')),
    cost_excl_gst numeric(14,2) NOT NULL,
    a_plus_b numeric(14,2),
    gi_fitting numeric(14,2) NOT NULL CHECK (gi_fitting >= 0),
    pvc_hdpe_fitting numeric(14,2) NOT NULL CHECK (pvc_hdpe_fitting >= 0),
    installation numeric(14,2) NOT NULL CHECK (installation >= 0),
    commission_base numeric(14,2) NOT NULL CHECK (commission_base >= 0),
    commission_pct numeric(6,3) NOT NULL,
    commission_amount numeric(14,2) NOT NULL,
    tod_base numeric(14,2) NOT NULL CHECK (tod_base >= 0),
    tod_pct numeric(6,3) NOT NULL,
    tod_amount numeric(14,2) NOT NULL,
    total numeric(14,2) NOT NULL,
    remark text CHECK (remark IS NULL OR length(remark) <= 1000),
    first_recorded_by uuid NOT NULL REFERENCES app_user(id),
    recorded_by uuid NOT NULL REFERENCES app_user(id),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    decided_by uuid REFERENCES app_user(id),
    decided_at timestamptz,
    decision_remark text CHECK (decision_remark IS NULL OR length(decision_remark) <= 1000),
    paid_on date,
    payment_reference text CHECK (payment_reference IS NULL OR length(btrim(payment_reference)) BETWEEN 1 AND 200),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_dealer_commission_base CHECK (commission_base = cost_excl_gst - gi_fitting - pvc_hdpe_fitting - installation),
    CONSTRAINT ck_dealer_commission_amounts CHECK (
        commission_amount = round(commission_base * commission_pct / 100, 2)
        AND tod_amount = round(tod_base * tod_pct / 100, 2)
        AND total = commission_amount + tod_amount),
    CONSTRAINT ck_dealer_commission_paid CHECK ((status = 'paid') = (paid_on IS NOT NULL AND payment_reference IS NOT NULL))
)""",
    # one live commission per application (review finding 5)
    "CREATE UNIQUE INDEX uq_dealer_commission_live ON dealer_commission (application_id) WHERE status <> 'cancelled'",
    "CREATE INDEX ix_dealer_commission_partner ON dealer_commission (partner_id, status)",
    "CREATE INDEX ix_dealer_commission_status ON dealer_commission (status, recorded_at DESC)",
    # stand-ins (GAP-323): GGRC dealers 5% + 2% TOD, distributors 3% + 1%
    "INSERT INTO commission_rate (scheme_id, partner_type, commission_pct, tod_pct, effective_from) SELECT id, 'dealer', 5, 2, DATE '2026-04-01' FROM subsidy_scheme WHERE code = 'GGRC'",
    "INSERT INTO commission_rate (scheme_id, partner_type, commission_pct, tod_pct, effective_from) SELECT id, 'distributor', 3, 1, DATE '2026-04-01' FROM subsidy_scheme WHERE code = 'GGRC'",
]

GRANTS: dict[str, str] = {
    "commission_rate": "SELECT, INSERT",
    "dealer_commission": "SELECT",
}

HAND_POLICIES: list[tuple[str, str]] = [
    ("commission_rate", "CREATE POLICY commission_rate_sel ON commission_rate FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL AND (SELECT app_current_partner()) IS NULL)"),
    ("commission_rate", "CREATE POLICY commission_rate_ins ON commission_rate FOR INSERT WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"),
    # a commission is read by whoever reads its application (dealers: GAP-330)
    ("dealer_commission", "CREATE POLICY dealer_commission_sel ON dealer_commission FOR SELECT USING (EXISTS (SELECT 1 FROM subsidy_application a WHERE a.id = application_id))"),
]

FUNCTIONS = [
    # rule 5: score = 4 one partner + 2 partner type + 1 system, highest first, then the latest start
    """CREATE FUNCTION commission_rate_for(p_scheme uuid, p_system text, p_partner uuid, p_on date) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT r.id FROM commission_rate r JOIN channel_partner c ON c.id = p_partner
     WHERE r.scheme_id = p_scheme AND r.effective_from <= p_on
       AND (r.system_type IS NULL OR r.system_type = p_system)
       AND (r.partner_type IS NULL OR r.partner_type = c.partner_type::text)
       AND (r.partner_id IS NULL OR r.partner_id = p_partner)
     ORDER BY (CASE WHEN r.partner_id IS NOT NULL THEN 4 ELSE 0 END
               + CASE WHEN r.partner_type IS NOT NULL THEN 2 ELSE 0 END
               + CASE WHEN r.system_type IS NOT NULL THEN 1 ELSE 0 END) DESC,
              r.effective_from DESC, r.created_at DESC
     LIMIT 1
$fn$""",
    """CREATE FUNCTION commission_preview(p_app uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a subsidy_application%ROWTYPE; v_rate uuid; r commission_rate%ROWTYPE; v_blocks jsonb;
BEGIN
    IF NOT subsidy_application_visible(p_app) THEN
        RAISE EXCEPTION 'application not found' USING ERRCODE = 'SAPNF';
    END IF;
    SELECT * INTO a FROM subsidy_application WHERE id = p_app;
    IF a.status <> 'full_fp_received' THEN
        RAISE EXCEPTION 'stage 18 waits for full FP' USING ERRCODE = 'COMNC';
    END IF;
    IF a.partner_id IS NULL THEN
        RAISE EXCEPTION 'the application has no dealer' USING ERRCODE = 'COMNP';
    END IF;
    v_rate := commission_rate_for(a.scheme_id, a.system_type, a.partner_id, a.full_fp_received_on);
    SELECT * INTO r FROM commission_rate WHERE id = v_rate;
    v_blocks := a.calculation -> 'total' -> 'blocks';
    RETURN jsonb_build_object(
        'partner_id', a.partner_id,
        'cost_excl_gst', round((v_blocks ->> 'cost_excl_gst')::numeric, 2),
        'installation', round(coalesce((v_blocks ->> 'installation')::numeric, 0), 2),
        'a_plus_b', round((v_blocks ->> 'a_plus_b')::numeric, 2),
        'rate_id', v_rate, 'commission_pct', r.commission_pct, 'tod_pct', r.tod_pct);
END $fn$""",
    """CREATE FUNCTION commission_record(p_app uuid, p_gi numeric, p_pvc numeric, p_installation numeric,
                                     p_tod_base numeric, p_remark text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); a subsidy_application%ROWTYPE; p jsonb; v_cost numeric;
        v_base numeric; v_tod_base numeric; c dealer_commission%ROWTYPE; v_id uuid; r commission_rate%ROWTYPE;
BEGIN
    IF NOT app_has_permission('subsidy', 'edit') OR app_current_partner() IS NOT NULL THEN
        RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
    END IF;
    p := commission_preview(p_app);                     -- visibility, closed, dealer
    SELECT * INTO a FROM subsidy_application WHERE id = p_app FOR UPDATE;
    IF p ->> 'rate_id' IS NULL THEN
        RAISE EXCEPTION 'no commission rate in force' USING ERRCODE = 'COMNR';
    END IF;
    SELECT * INTO r FROM commission_rate WHERE id = (p ->> 'rate_id')::uuid;
    v_cost := (p ->> 'cost_excl_gst')::numeric;
    IF p_gi < 0 OR p_pvc < 0 OR p_installation < 0 OR coalesce(p_tod_base, 0) < 0 THEN
        RAISE EXCEPTION 'amounts cannot be negative' USING ERRCODE = 'COMVL';
    END IF;
    v_base := v_cost - p_gi - p_pvc - p_installation;
    IF v_base < 0 THEN
        RAISE EXCEPTION 'fittings and installation exceed the cost' USING ERRCODE = 'COMVL';
    END IF;
    v_tod_base := coalesce(p_tod_base, v_base);
    SELECT * INTO c FROM dealer_commission WHERE application_id = p_app AND status <> 'cancelled' FOR UPDATE;
    IF c.id IS NOT NULL AND c.status IN ('approved', 'paid') THEN
        RAISE EXCEPTION 'the commission is %', c.status USING ERRCODE = 'COMEX';
    END IF;
    IF c.id IS NULL THEN
        INSERT INTO dealer_commission (application_id, partner_id, rate_id, cost_excl_gst, a_plus_b, gi_fitting,
            pvc_hdpe_fitting, installation, commission_base, commission_pct, commission_amount, tod_base, tod_pct,
            tod_amount, total, remark, first_recorded_by, recorded_by)
        VALUES (p_app, a.partner_id, r.id, v_cost, (p ->> 'a_plus_b')::numeric, p_gi, p_pvc, p_installation, v_base,
                r.commission_pct, round(v_base * r.commission_pct / 100, 2), v_tod_base, r.tod_pct,
                round(v_tod_base * r.tod_pct / 100, 2),
                round(v_base * r.commission_pct / 100, 2) + round(v_tod_base * r.tod_pct / 100, 2),
                nullif(btrim(p_remark), ''), v_me, v_me)
        RETURNING id INTO v_id;
    ELSE
        -- recorded again: new figures, the old decision cleared (review finding 9)
        UPDATE dealer_commission SET status = 'calculated', rate_id = r.id, cost_excl_gst = v_cost,
               a_plus_b = (p ->> 'a_plus_b')::numeric, gi_fitting = p_gi, pvc_hdpe_fitting = p_pvc,
               installation = p_installation, commission_base = v_base, commission_pct = r.commission_pct,
               commission_amount = round(v_base * r.commission_pct / 100, 2), tod_base = v_tod_base,
               tod_pct = r.tod_pct, tod_amount = round(v_tod_base * r.tod_pct / 100, 2),
               total = round(v_base * r.commission_pct / 100, 2) + round(v_tod_base * r.tod_pct / 100, 2),
               remark = nullif(btrim(p_remark), ''), recorded_by = v_me, recorded_at = now(),
               decided_by = NULL, decided_at = NULL, decision_remark = NULL, updated_at = now()
         WHERE id = c.id;
        v_id := c.id;
    END IF;
    PERFORM subsidy_event(p_app, 'subsidy.commission_recorded', jsonb_build_object('commission_id', v_id));
    RETURN v_id;
END $fn$""",
    """CREATE FUNCTION commission_decide(p_id uuid, p_action text, p_remark text, p_paid_on date, p_reference text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); c dealer_commission%ROWTYPE; v_to text;
        v_today date := (now() AT TIME ZONE 'Asia/Kolkata')::date;
BEGIN
    SELECT * INTO c FROM dealer_commission WHERE id = p_id FOR UPDATE;
    IF c.id IS NULL OR NOT subsidy_application_visible(c.application_id) OR app_current_partner() IS NOT NULL THEN
        RAISE EXCEPTION 'commission not found' USING ERRCODE = 'COMNF';
    END IF;
    IF p_action IN ('approve', 'return') THEN
        IF NOT app_has_permission('payments', 'approve') THEN
            RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
        END IF;
        IF v_me IN (c.recorded_by, c.first_recorded_by) THEN
            RAISE EXCEPTION 'self_approval' USING ERRCODE = '42501';
        END IF;
        IF c.status <> 'calculated' THEN
            RAISE EXCEPTION 'the commission is %', c.status USING ERRCODE = 'COMSC';
        END IF;
        IF p_action = 'return' AND (p_remark IS NULL OR btrim(p_remark) = '') THEN
            RAISE EXCEPTION 'a remark is required' USING ERRCODE = 'APRRM';
        END IF;
        v_to := CASE p_action WHEN 'approve' THEN 'approved' ELSE 'returned' END;
    ELSIF p_action = 'cancel' THEN
        IF p_remark IS NULL OR btrim(p_remark) = '' THEN
            RAISE EXCEPTION 'a remark is required' USING ERRCODE = 'APRRM';
        END IF;
        IF c.status IN ('calculated', 'returned') THEN
            IF NOT app_has_permission('subsidy', 'edit') THEN
                RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
            END IF;
        ELSIF c.status = 'approved' THEN
            IF NOT app_has_permission('payments', 'approve') THEN
                RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
            END IF;
        ELSE
            RAISE EXCEPTION 'the commission is %', c.status USING ERRCODE = 'COMSC';
        END IF;
        v_to := 'cancelled';
    ELSIF p_action = 'pay' THEN
        -- Accounts and admins only: a State Manager holds payments.edit at org scope (review finding 3)
        IF NOT app_has_permission('payments', 'edit') OR app_scope('payments') IS DISTINCT FROM 'global' THEN
            RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
        END IF;
        IF c.status <> 'approved' THEN
            RAISE EXCEPTION 'the commission is %', c.status USING ERRCODE = 'COMSC';
        END IF;
        IF p_paid_on IS NULL OR p_paid_on > v_today OR p_reference IS NULL OR btrim(p_reference) = '' THEN
            RAISE EXCEPTION 'a payment date, not in the future, and a reference are required' USING ERRCODE = 'COMVL';
        END IF;
        v_to := 'paid';
    ELSE
        RAISE EXCEPTION 'unknown action' USING ERRCODE = 'COMVL';
    END IF;
    UPDATE dealer_commission SET status = v_to, decided_by = v_me, decided_at = now(),
           decision_remark = coalesce(nullif(btrim(p_remark), ''), decision_remark),
           paid_on = CASE WHEN v_to = 'paid' THEN p_paid_on ELSE paid_on END,
           payment_reference = CASE WHEN v_to = 'paid' THEN btrim(p_reference) ELSE payment_reference END,
           updated_at = now()
     WHERE id = p_id;
    PERFORM subsidy_event(c.application_id, 'subsidy.commission_' || v_to, jsonb_build_object('commission_id', p_id));
END $fn$""",
]

TRIGGERS = [
    "CREATE TRIGGER trg_commission_rate_audit AFTER INSERT OR UPDATE OR DELETE ON commission_rate FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_dealer_commission_audit AFTER INSERT OR UPDATE OR DELETE ON dealer_commission FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

GRANTED = [
    "commission_preview(uuid)",
    "commission_record(uuid, numeric, numeric, numeric, numeric, text)",
    "commission_decide(uuid, text, text, date, text)",
]
INTERNAL = ["commission_rate_for(uuid, text, uuid, date)"]


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for table in GRANTS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for _table, stmt in HAND_POLICIES:
        op.execute(stmt)
    for stmt in FUNCTIONS + TRIGGERS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DELETE FROM activity_event WHERE kind LIKE 'subsidy.commission_%'")
    for table in ("dealer_commission", "commission_rate"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
