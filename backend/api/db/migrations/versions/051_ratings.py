"""051: ratings (FS-043).

- `rating`: feedback, entered once and never changed. Installation and product
  ratings hang off a shipped order, service ratings off a closed complaint. Rows
  are read through the order's or the complaint's own policy; they are written
  only by `rating_record()`.
- `rating_record()`: who rates as whom (`app_user.user_type`: staff record a
  customer's rating, a partner user its dealer's own on its own documents, a
  consumer nothing this round), whether the target is rateable, one per target per
  kind of rater, and the `rating.recorded` event on the order or complaint.
- `dealer_rating()`: the derived rating. Gated once (the caller reads the dealer and
  holds `payments.view`, plan review B-1), then computed from `payment` and
  `payment_allocation` directly, so every reader gets the same figures (edge 2).
- `app_setting`: a `bands` kind (four whole numbers, rising) and three settings.

Revision ID: 051_ratings
Revises: 045_export_sample_orders
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "051_ratings"
down_revision: str | None = "045_export_sample_orders"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# the consumer floor (052): every RLS table carries it, so a new one does too
_spec = importlib.util.spec_from_file_location(
    "consumer_floor_051", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

TABLES = [
    """CREATE TABLE rating (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    target text NOT NULL CHECK (target IN ('installation', 'service', 'product')),
    sales_order_id uuid REFERENCES sales_order(id),
    complaint_id uuid REFERENCES complaint(id),
    product_id uuid REFERENCES product(id),
    lead_id uuid REFERENCES lead(id),
    partner_id uuid REFERENCES channel_partner(id),
    rated_by text NOT NULL CHECK (rated_by IN ('customer', 'dealer')),
    score smallint NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment text CHECK (comment IS NULL OR (length(comment) BETWEEN 1 AND 1000 AND comment = btrim(comment))),
    entered_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_rating_target CHECK (CASE target
        WHEN 'installation' THEN sales_order_id IS NOT NULL AND complaint_id IS NULL AND product_id IS NULL
        WHEN 'product' THEN sales_order_id IS NOT NULL AND complaint_id IS NULL AND product_id IS NOT NULL
        ELSE complaint_id IS NOT NULL AND sales_order_id IS NULL AND product_id IS NULL END)
)""",
]

INDEXES = [
    "CREATE UNIQUE INDEX ux_rating_installation ON rating (sales_order_id, rated_by) WHERE target = 'installation'",
    "CREATE UNIQUE INDEX ux_rating_service ON rating (complaint_id, rated_by) WHERE target = 'service'",
    "CREATE UNIQUE INDEX ux_rating_product ON rating (sales_order_id, product_id, rated_by) WHERE target = 'product'",
    "CREATE INDEX ix_rating_partner ON rating (partner_id, created_at DESC)",
    "CREATE INDEX ix_rating_product ON rating (product_id)",
    "CREATE INDEX ix_rating_order ON rating (sales_order_id)",
    "CREATE INDEX ix_rating_complaint ON rating (complaint_id)",
    "CREATE INDEX ix_rating_lead ON rating (lead_id)",
]

GRANTS: dict[str, str] = {"rating": "SELECT"}

# The target's own policy decides, with no per-row function (edge 18)
HAND_POLICIES: list[tuple[str, str]] = [
    ("rating", "CREATE POLICY rating_sel ON rating FOR SELECT USING (\n"
               "  CASE WHEN target = 'service' THEN EXISTS (SELECT 1 FROM complaint c WHERE c.id = complaint_id)\n"
               "       ELSE EXISTS (SELECT 1 FROM sales_order o WHERE o.id = sales_order_id) END\n)"),
]

TRIGGERS = [
    "CREATE TRIGGER trg_rating_audit AFTER INSERT OR UPDATE OR DELETE ON rating "
    "FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

SEED = """INSERT INTO app_setting (key, kind, value, allowed, min, max, description) VALUES
('dealer_rating_window_days', 'int', '365', NULL, 30, 1095,
 'The dealer rating counts orders submitted in this many days, up to today.'),
('dealer_rating_payment_days', 'bands', '[7, 15, 30, 60]', NULL, NULL, NULL,
 'Days from order to full payment: at or under the first scores 5, the second 4, the third 3, the fourth 2; over the fourth, 1.'),
('dealer_rating_order_value', 'bands', '[100000, 500000, 1000000, 2500000]', NULL, NULL, NULL,
 'Rupees ordered before GST: at or over the fourth scores 5, the third 4, the second 3, the first 2; under the first, 1.')
ON CONFLICT (key) DO NOTHING"""

KIND_CHECK = ("ALTER TABLE app_setting DROP CONSTRAINT app_setting_kind_check, "
              "ADD CONSTRAINT app_setting_kind_check CHECK (kind IN ('choice', 'int', 'roles', 'bands'))")

# 041's function with a bands branch before the roles ELSE. Replaced whole: nothing
# else patches it (plan review R-4).
SETTING_CHECK = """CREATE OR REPLACE FUNCTION app_setting_check() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
DECLARE v numeric; r text; e jsonb; prev numeric;
BEGIN
    IF NEW.kind = 'choice' THEN
        IF jsonb_typeof(NEW.value) <> 'string' OR NOT (NEW.allowed @> jsonb_build_array(NEW.value)) THEN
            RAISE EXCEPTION 'setting %: one of %', NEW.key, NEW.allowed USING ERRCODE = 'SETVL';
        END IF;
    ELSIF NEW.kind = 'int' THEN
        IF jsonb_typeof(NEW.value) <> 'number' THEN
            RAISE EXCEPTION 'setting %: a whole number', NEW.key USING ERRCODE = 'SETVL';
        END IF;
        v := (NEW.value #>> '{}')::numeric;
        IF v <> trunc(v) OR (NEW.min IS NOT NULL AND v < NEW.min) OR (NEW.max IS NOT NULL AND v > NEW.max) THEN
            RAISE EXCEPTION 'setting %: % to %', NEW.key, NEW.min, NEW.max USING ERRCODE = 'SETVL';
        END IF;
    ELSIF NEW.kind = 'bands' THEN
        -- FS-043: four whole numbers, zero or more, strictly rising; strings refused
        IF jsonb_typeof(NEW.value) <> 'array' OR jsonb_array_length(NEW.value) <> 4 THEN
            RAISE EXCEPTION 'setting %: four whole numbers, rising', NEW.key USING ERRCODE = 'SETVL';
        END IF;
        prev := -1;
        FOR e IN SELECT x FROM jsonb_array_elements(NEW.value) x LOOP
            IF jsonb_typeof(e) <> 'number' THEN
                RAISE EXCEPTION 'setting %: four whole numbers, rising', NEW.key USING ERRCODE = 'SETVL';
            END IF;
            v := (e #>> '{}')::numeric;
            IF v <> trunc(v) OR v <= prev THEN
                RAISE EXCEPTION 'setting %: four whole numbers, rising', NEW.key USING ERRCODE = 'SETVL';
            END IF;
            prev := v;
        END LOOP;
    ELSE
        IF jsonb_typeof(NEW.value) <> 'array' THEN
            RAISE EXCEPTION 'setting %: a list of role codes', NEW.key USING ERRCODE = 'SETVL';
        END IF;
        -- the migrations' own rows: a fresh database migrates before the roles are seeded
        -- (CI), and 005/015 insert roles, so the role table is never empty here. The
        -- codes are checked from the first change on, by app_setting_set
        IF TG_OP = 'INSERT' THEN
            RETURN NEW;
        END IF;
        FOR r IN SELECT jsonb_array_elements_text(NEW.value) LOOP
            IF NOT EXISTS (SELECT 1 FROM role WHERE code = r AND deleted_at IS NULL) THEN
                RAISE EXCEPTION 'setting %: no role %', NEW.key, r USING ERRCODE = 'SETVL';
            END IF;
        END LOOP;
    END IF;
    RETURN NEW;
END $fn$"""

_PAYABLE = "('submitted', 'approved', 'partially_dispatched', 'dispatched', 'closed_short')"

FUNCTIONS = [
    """CREATE FUNCTION rating_record(p_target text, p_order uuid, p_complaint uuid, p_product uuid,
                              p_score integer, p_comment text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); v_type text; v_by text; v_partner uuid := app_current_partner();
    v_lead uuid; v_doc_partner uuid; v_comment text; v_id uuid; v_status text;
BEGIN
    SELECT user_type::text INTO v_type FROM app_user WHERE id = v_me AND is_active AND deleted_at IS NULL;
    IF v_type = 'staff' THEN
        v_by := 'customer';
    ELSIF v_type = 'partner_user' AND v_partner IS NOT NULL THEN
        v_by := 'dealer';
    ELSE
        RAISE EXCEPTION 'not permitted to rate' USING ERRCODE = '42501';
    END IF;
    IF p_score IS NULL OR p_score NOT BETWEEN 1 AND 5 THEN
        RAISE EXCEPTION 'score' USING ERRCODE = 'RTGSC';
    END IF;
    v_comment := NULLIF(btrim(p_comment), '');
    IF length(v_comment) > 1000 THEN
        RAISE EXCEPTION 'comment' USING ERRCODE = 'RTGCM';
    END IF;
    IF p_target IN ('installation', 'product') THEN
        IF p_order IS NULL OR p_complaint IS NOT NULL OR (p_target = 'installation') <> (p_product IS NULL) THEN
            RAISE EXCEPTION 'target' USING ERRCODE = 'RTGTG';
        END IF;
        IF NOT order_visible(p_order) THEN
            RAISE EXCEPTION 'order not found' USING ERRCODE = 'RTGNF';
        END IF;
        IF v_by = 'customer' AND NOT app_has_permission('sales_orders', 'edit') THEN
            RAISE EXCEPTION 'not permitted to rate' USING ERRCODE = '42501';
        END IF;
        SELECT lead_id, partner_id INTO v_lead, v_doc_partner FROM sales_order
         WHERE id = p_order AND deleted_at IS NULL FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'order not found' USING ERRCODE = 'RTGNF';
        END IF;
        -- a live dispatch, not a status: a closed-short order may have shipped nothing (edge 3)
        IF NOT EXISTS (SELECT 1 FROM dispatch WHERE sales_order_id = p_order AND voided_at IS NULL) THEN
            RAISE EXCEPTION 'nothing has shipped' USING ERRCODE = 'RTGNR';
        END IF;
        IF p_target = 'product' AND NOT EXISTS (
               SELECT 1 FROM dispatch_line dl JOIN dispatch d ON d.id = dl.dispatch_id
                 JOIN order_line l ON l.id = dl.order_line_id
                WHERE d.sales_order_id = p_order AND d.voided_at IS NULL AND l.product_id = p_product) THEN
            RAISE EXCEPTION 'the product has not shipped on this order' USING ERRCODE = 'RTGPS';
        END IF;
    ELSIF p_target = 'service' THEN
        IF p_complaint IS NULL OR p_order IS NOT NULL OR p_product IS NOT NULL THEN
            RAISE EXCEPTION 'target' USING ERRCODE = 'RTGTG';
        END IF;
        IF NOT complaint_visible(p_complaint) THEN
            RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'RTGNF';
        END IF;
        IF v_by = 'customer' AND NOT app_has_permission('complaints', 'edit') THEN
            RAISE EXCEPTION 'not permitted to rate' USING ERRCODE = '42501';
        END IF;
        SELECT lead_id, partner_id, status::text INTO v_lead, v_doc_partner, v_status FROM complaint
         WHERE id = p_complaint AND deleted_at IS NULL FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'RTGNF';
        END IF;
        IF v_status <> 'closed' THEN
            RAISE EXCEPTION 'the complaint is %', v_status USING ERRCODE = 'RTGNR';
        END IF;
    ELSE
        RAISE EXCEPTION 'target' USING ERRCODE = 'RTGTG';
    END IF;
    -- a dealer rates its own documents, not a sub-dealer's (edge 8)
    IF v_by = 'dealer' AND v_doc_partner IS DISTINCT FROM v_partner THEN
        RAISE EXCEPTION 'not your order' USING ERRCODE = 'RTGNY';
    END IF;
    BEGIN
        INSERT INTO rating (target, sales_order_id, complaint_id, product_id, lead_id, partner_id,
                            rated_by, score, comment, entered_by)
        VALUES (p_target, p_order, p_complaint, p_product, v_lead, v_doc_partner,
                v_by, p_score, v_comment, v_me)
        RETURNING id INTO v_id;
    EXCEPTION WHEN unique_violation THEN
        RAISE EXCEPTION 'already rated' USING ERRCODE = 'RTGEX';
    END;
    -- on the order or the complaint, so their timelines show it; never the comment
    INSERT INTO activity_event (entity_type, entity_id, lead_id, partner_id, kind, actor_id, payload)
    VALUES (CASE WHEN p_target = 'service' THEN 'complaint' ELSE 'sales_order' END,
            COALESCE(p_order, p_complaint), v_lead, v_doc_partner, 'rating.recorded', v_me,
            jsonb_build_object('rating_id', v_id, 'target', p_target, 'score', p_score,
                               'rated_by', v_by, 'product_id', p_product));
    RETURN v_id;
END $fn$""",
    f"""CREATE FUNCTION dealer_rating(p_partner uuid)
RETURNS TABLE (on_day date, window_days integer, orders integer, paid_orders integer,
               payment_days numeric, payment_score integer, order_value numeric, value_score integer,
               rating numeric, feedback_count integer, feedback_average numeric)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_today date := (now() AT TIME ZONE 'Asia/Kolkata')::date;
    v_window integer := (app_setting_json('dealer_rating_window_days') #>> '{{}}')::integer;
    v_days numeric[] := ARRAY(SELECT x::numeric FROM jsonb_array_elements_text(app_setting_json('dealer_rating_payment_days')) x);
    v_vals numeric[] := ARRAY(SELECT x::numeric FROM jsonb_array_elements_text(app_setting_json('dealer_rating_order_value')) x);
    v_orders integer; v_paid integer; v_pd numeric; v_value numeric; v_ps integer; v_vs integer;
    v_fc integer; v_fa numeric;
BEGIN
    -- the dealer's order book and payment behaviour: the class of its credit (plan review
    -- B-1), so 047's gate: Accounts at global, or a reader of the dealer who sees payments
    IF NOT (app_has_permission('payments', 'view') AND app_scope('payments') = 'global') THEN
        IF NOT partner_visible_to_caller(p_partner) THEN
            RAISE EXCEPTION 'partner not found' USING ERRCODE = 'RTGNF';
        END IF;
        IF NOT app_has_permission('payments', 'view') THEN
            RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
        END IF;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM channel_partner WHERE id = p_partner AND deleted_at IS NULL) THEN
        RAISE EXCEPTION 'partner not found' USING ERRCODE = 'RTGNF';
    END IF;
    WITH o AS (
        SELECT so.id, so.status::text AS status, so.taxable,
               (so.submitted_at AT TIME ZONE 'Asia/Kolkata')::date AS sub_day,
               so.total - COALESCE((SELECT sum(b.amount) FROM scheme_benefit b
                                     WHERE b.sales_order_id = so.id AND b.status = 'applied'), 0) AS owed
          FROM sales_order so
         WHERE so.partner_id = p_partner AND so.deleted_at IS NULL
           AND so.order_type IN ('commercial', 'industrial')
           AND so.status::text IN {_PAYABLE}
           AND so.submitted_at IS NOT NULL
           AND (so.submitted_at AT TIME ZONE 'Asia/Kolkata')::date > v_today - v_window
    ), paid AS (
        -- 046's running sum, read here rather than through order_paid_at(), which answers per caller
        SELECT o.id, (SELECT t.d FROM (
                   SELECT p.received_on AS d, sum(sum(a.amount)) OVER (ORDER BY p.received_on) AS running
                     FROM payment_allocation a JOIN payment p ON p.id = a.payment_id
                    WHERE a.sales_order_id = o.id AND NOT a.voided AND p.voided_at IS NULL
                    GROUP BY p.received_on) t
                WHERE t.running >= o.owed ORDER BY t.d LIMIT 1) AS paid_day
          FROM o WHERE o.owed > 0
    ), counted AS (
        -- rule 11: owing nothing, closed short, or unpaid and younger than the first band: left out
        SELECT o.taxable, greatest(0, COALESCE(p.paid_day, v_today) - o.sub_day) AS days
          FROM o JOIN paid p ON p.id = o.id
         WHERE o.status <> 'closed_short'
           AND (p.paid_day IS NOT NULL OR v_today - o.sub_day >= v_days[1])
    )
    SELECT (SELECT count(*) FROM o), (SELECT count(*) FROM paid WHERE paid_day IS NOT NULL),
           (SELECT round(sum(days * taxable) / NULLIF(sum(taxable), 0), 1) FROM counted),
           (SELECT COALESCE(sum(taxable), 0) FROM o)
      INTO v_orders, v_paid, v_pd, v_value;
    v_ps := CASE WHEN v_pd IS NULL THEN NULL WHEN v_pd <= v_days[1] THEN 5 WHEN v_pd <= v_days[2] THEN 4
                 WHEN v_pd <= v_days[3] THEN 3 WHEN v_pd <= v_days[4] THEN 2 ELSE 1 END;
    v_vs := CASE WHEN v_orders = 0 THEN NULL WHEN v_value >= v_vals[4] THEN 5 WHEN v_value >= v_vals[3] THEN 4
                 WHEN v_value >= v_vals[2] THEN 3 WHEN v_value >= v_vals[1] THEN 2 ELSE 1 END;
    SELECT count(*), round(avg(score), 2) INTO v_fc, v_fa FROM rating
     WHERE partner_id = p_partner AND rated_by = 'customer';
    RETURN QUERY SELECT v_today, v_window, v_orders, v_paid, v_pd, v_ps, v_value, v_vs,
        CASE WHEN v_ps IS NULL OR v_vs IS NULL THEN NULL ELSE round((v_ps + v_vs) / 2.0, 1) END,
        v_fc, v_fa;
END $fn$""",
]

GRANTED = ["rating_record(text, uuid, uuid, uuid, integer, text)", "dealer_rating(uuid)"]


def _load(stem: str) -> ModuleType:
    path = next(Path(__file__).parent.glob(f"{stem}_*.py"))
    spec = importlib.util.spec_from_file_location(f"mig_{stem}_for_051", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"051: migration {stem} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def upgrade() -> None:
    op.execute(KIND_CHECK)
    op.execute(SETTING_CHECK)
    op.execute(SEED)
    for stmt in TABLES + INDEXES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("ALTER TABLE rating ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    op.execute(floor.policy_sql("rating"))
    for stmt in TRIGGERS + FUNCTIONS:
        op.execute(stmt)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for sig in GRANTED:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DELETE FROM activity_event WHERE kind = 'rating.recorded'")
    op.execute("DROP TABLE IF EXISTS rating")
    keys = "('dealer_rating_window_days', 'dealer_rating_payment_days', 'dealer_rating_order_value')"
    op.execute(f"DELETE FROM activity_event WHERE kind = 'setting.changed' AND payload ->> 'key' IN {keys}")
    op.execute(f"DELETE FROM app_setting WHERE key IN {keys}")
    m041 = _load("041")
    check = next(f for f in m041.FUNCTIONS if "FUNCTION app_setting_check()" in f)  # type: ignore[attr-defined]
    op.execute(check.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    op.execute("ALTER TABLE app_setting DROP CONSTRAINT app_setting_kind_check, "
               "ADD CONSTRAINT app_setting_kind_check CHECK (kind IN ('choice', 'int', 'roles'))")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
