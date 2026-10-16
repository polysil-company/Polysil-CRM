"""033: schemes, types 1 to 4 (FS-031, ADR-035, ADR-050).

- `scheme` and `scheme_target`: the master. Admins write it directly under
  `schemes.create` / `schemes.edit`; a trigger refuses any edit but the end date and
  the active flag once the scheme has given anything (rule 16).
- `scheme_benefit`: a discount or a used entitlement on one order. It reduces the
  payable and never the invoice (ADR-050).
- `scheme_entitlement`: earned now, used on a later order (types 3 and 4).
- `reward_ledger`: points, minimal here (types 2 and 4); FS-032 (036) adds the rules,
  redemption and expiry.
- One `AFTER UPDATE OF status` trigger on `sales_order` does every write: type 1 and
  entitlement use at submit, types 2 and 3 at delivery, every reversal. It fires
  inside every definer that moves an order, the complaint replacement path (026)
  included, so nothing depends on a service hook (plan review B2). Its name sorts
  after `trg_sales_order_close_short`, so `qty_short` is written before the delivered
  basis is read.
- `scheme_order_preview()` calls the same functions as the trigger, so a preview and
  the stored rows cannot disagree.
- `scheme_period_evaluate()` and `scheme_entitlement_expire()` are the nightly job's.
- `activity_event_sel` gains a `scheme` arm, from `api/authz/activity.py` (the drift
  test compares the literal with the generator).

Revision ID: 033_schemes
Revises: 028_dealer_area_access
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "033_schemes"
down_revision: str | None = "028_dealer_area_access"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id)"""

ENUMS = [
    "CREATE TYPE scheme_type AS ENUM ('order_discount', 'order_points', 'next_order', 'period')",
    "CREATE TYPE scheme_metric AS ENUM ('order_value', 'product_qty')",
    "CREATE TYPE scheme_benefit_kind AS ENUM ('pct', 'flat', 'points')",
    "CREATE TYPE scheme_period AS ENUM ('month', 'quarter')",
    "CREATE TYPE scheme_target_type AS ENUM ('territory', 'partner_type', 'partner', 'product', 'product_category')",
]

TABLES = [
    f"""CREATE TABLE scheme (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE CHECK (code ~ '^[A-Za-z0-9_-]{{2,40}}$'),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    description text CHECK (description IS NULL OR length(description) <= 2000),
    scheme_type scheme_type NOT NULL,
    metric scheme_metric NOT NULL DEFAULT 'order_value',
    condition_min numeric(14,3) NOT NULL DEFAULT 0 CHECK (condition_min >= 0),
    condition_max numeric(14,3),
    benefit_kind scheme_benefit_kind NOT NULL,
    benefit_value numeric(14,3) NOT NULL CHECK (benefit_value > 0),
    benefit_cap numeric(14,2) CHECK (benefit_cap IS NULL OR benefit_cap > 0),
    entitlement_days int CHECK (entitlement_days IS NULL OR entitlement_days BETWEEN 1 AND 3650),
    period scheme_period,
    valid_from date NOT NULL,
    valid_to date,
    priority int NOT NULL DEFAULT 100 CHECK (priority BETWEEN 0 AND 10000),
    stackable boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT ck_scheme_range CHECK (condition_max IS NULL OR condition_max >= condition_min),
    CONSTRAINT ck_scheme_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_scheme_pct CHECK (benefit_kind <> 'pct' OR benefit_value <= 100),
    CONSTRAINT ck_scheme_points CHECK (benefit_kind <> 'points' OR benefit_value = trunc(benefit_value)),
    CONSTRAINT ck_scheme_shape CHECK (
        (scheme_type = 'order_discount' AND benefit_kind IN ('pct', 'flat') AND period IS NULL AND entitlement_days IS NULL)
        OR (scheme_type = 'order_points' AND benefit_kind = 'points' AND period IS NULL AND entitlement_days IS NULL AND benefit_cap IS NULL)
        OR (scheme_type = 'next_order' AND benefit_kind IN ('pct', 'flat') AND period IS NULL AND entitlement_days IS NOT NULL)
        OR (scheme_type = 'period' AND period IS NOT NULL AND valid_to IS NOT NULL
            AND ((benefit_kind = 'points' AND entitlement_days IS NULL AND benefit_cap IS NULL)
                 OR (benefit_kind IN ('pct', 'flat') AND entitlement_days IS NOT NULL))))
)""",
    "CREATE INDEX ix_scheme_live ON scheme (scheme_type, valid_from) WHERE is_active",
    """CREATE TABLE scheme_target (
    scheme_id uuid NOT NULL REFERENCES scheme(id) ON DELETE CASCADE,
    target_type scheme_target_type NOT NULL,
    target_id text NOT NULL CHECK (length(target_id) BETWEEN 1 AND 64),
    PRIMARY KEY (scheme_id, target_type, target_id)
)""",
    """CREATE TABLE scheme_entitlement (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL REFERENCES scheme(id),
    partner_id uuid NOT NULL REFERENCES channel_partner(id),
    source_order_id uuid REFERENCES sales_order(id),
    period_start date,
    period_end date,
    kind scheme_benefit_kind NOT NULL CHECK (kind IN ('pct', 'flat')),
    value numeric(14,3) NOT NULL CHECK (value > 0),
    cap numeric(14,2) CHECK (cap IS NULL OR cap > 0),
    basis numeric(14,3) NOT NULL,
    status text NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'consumed', 'expired', 'reversed')),
    earned_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_order_id uuid REFERENCES sales_order(id),
    consumed_at timestamptz,
    reversed_at timestamptz,
    CONSTRAINT ck_scheme_entitlement_source CHECK ((source_order_id IS NULL) <> (period_start IS NULL)),
    CONSTRAINT ck_scheme_entitlement_period CHECK ((period_start IS NULL) = (period_end IS NULL)),
    CONSTRAINT ck_scheme_entitlement_pct CHECK (kind <> 'pct' OR value <= 100),
    CONSTRAINT ck_scheme_entitlement_consumed CHECK ((status = 'consumed') = (consumed_order_id IS NOT NULL)
                                                    AND (consumed_order_id IS NULL) = (consumed_at IS NULL)),
    CONSTRAINT ck_scheme_entitlement_reversed CHECK ((status = 'reversed') = (reversed_at IS NOT NULL))
)""",
    # plan review B1: unique among rows not reversed, so a void then re-dispatch earns again
    "CREATE UNIQUE INDEX uq_scheme_entitlement_order ON scheme_entitlement (scheme_id, source_order_id) WHERE source_order_id IS NOT NULL AND status <> 'reversed'",
    "CREATE UNIQUE INDEX uq_scheme_entitlement_period ON scheme_entitlement (scheme_id, partner_id, period_start) WHERE period_start IS NOT NULL AND status <> 'reversed'",
    "CREATE INDEX ix_scheme_entitlement_partner ON scheme_entitlement (partner_id, status, expires_at)",
    "CREATE INDEX ix_scheme_entitlement_consumed ON scheme_entitlement (consumed_order_id) WHERE consumed_order_id IS NOT NULL",
    "CREATE INDEX ix_scheme_entitlement_source ON scheme_entitlement (source_order_id) WHERE source_order_id IS NOT NULL",
    """CREATE TABLE scheme_benefit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sales_order_id uuid NOT NULL REFERENCES sales_order(id),
    scheme_id uuid NOT NULL REFERENCES scheme(id),
    entitlement_id uuid REFERENCES scheme_entitlement(id),
    kind text NOT NULL CHECK (kind IN ('discount', 'entitlement_used')),
    basis numeric(14,3) NOT NULL,
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    status text NOT NULL DEFAULT 'applied' CHECK (status IN ('applied', 'reversed')),
    applied_at timestamptz NOT NULL DEFAULT now(),
    reversed_at timestamptz,
    CONSTRAINT ck_scheme_benefit_entitlement CHECK ((kind = 'entitlement_used') = (entitlement_id IS NOT NULL)),
    CONSTRAINT ck_scheme_benefit_reversed CHECK ((status = 'reversed') = (reversed_at IS NOT NULL))
)""",
    "CREATE INDEX ix_scheme_benefit_order ON scheme_benefit (sales_order_id)",
    "CREATE INDEX ix_scheme_benefit_entitlement ON scheme_benefit (entitlement_id) WHERE entitlement_id IS NOT NULL",
    "CREATE UNIQUE INDEX uq_scheme_benefit_discount ON scheme_benefit (sales_order_id, scheme_id) WHERE kind = 'discount' AND status = 'applied'",
    """CREATE TABLE reward_ledger (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    holder_type text NOT NULL CHECK (holder_type IN ('partner', 'user')),
    partner_id uuid REFERENCES channel_partner(id),
    user_id uuid REFERENCES app_user(id),
    points int NOT NULL CHECK (points <> 0),
    kind text NOT NULL CHECK (kind IN ('earned', 'reversed', 'redeemed', 'released', 'expired', 'adjusted')),
    reason text NOT NULL CHECK (length(btrim(reason)) BETWEEN 1 AND 500),
    scheme_id uuid REFERENCES scheme(id),
    source_order_id uuid REFERENCES sales_order(id),
    period_start date,
    reverses_id uuid REFERENCES reward_ledger(id),
    reversed_at timestamptz,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES app_user(id),
    CONSTRAINT ck_reward_ledger_holder CHECK (
        (holder_type = 'partner' AND partner_id IS NOT NULL AND user_id IS NULL)
        OR (holder_type = 'user' AND user_id IS NOT NULL AND partner_id IS NULL)),
    CONSTRAINT ck_reward_ledger_sign CHECK (
        (kind IN ('earned', 'released') AND points > 0)
        OR (kind IN ('reversed', 'redeemed', 'expired') AND points < 0)
        OR kind = 'adjusted'),
    CONSTRAINT ck_reward_ledger_reverses CHECK ((kind = 'reversed') = (reverses_id IS NOT NULL))
)""",
    "CREATE INDEX ix_reward_ledger_partner ON reward_ledger (partner_id, created_at DESC) WHERE partner_id IS NOT NULL",
    "CREATE INDEX ix_reward_ledger_user ON reward_ledger (user_id, created_at DESC) WHERE user_id IS NOT NULL",
    "CREATE UNIQUE INDEX uq_reward_ledger_scheme_order ON reward_ledger (scheme_id, source_order_id) WHERE kind = 'earned' AND reversed_at IS NULL AND source_order_id IS NOT NULL AND scheme_id IS NOT NULL",
    "CREATE UNIQUE INDEX uq_reward_ledger_scheme_period ON reward_ledger (scheme_id, partner_id, period_start) WHERE kind = 'earned' AND reversed_at IS NULL AND period_start IS NOT NULL",
    "CREATE UNIQUE INDEX uq_reward_ledger_reverses ON reward_ledger (reverses_id) WHERE reverses_id IS NOT NULL",
]

RLS_TABLES = ("scheme", "scheme_target", "scheme_entitlement", "scheme_benefit", "reward_ledger")

GRANTS: dict[str, str] = {
    "scheme": "SELECT, INSERT, UPDATE",
    "scheme_target": "SELECT, INSERT, DELETE",
    # every write to these is the status trigger or a definer
    "scheme_entitlement": "SELECT",
    "scheme_benefit": "SELECT",
    "reward_ledger": "SELECT",
}

_VIEW = "(SELECT app_has_permission('schemes', 'view'))"
_PARTNER = "(SELECT app_current_partner())"

# api/authz/activity.py policy_sql(), pasted; test_policy_drift_005 compares the two
ACTIVITY_SEL = "CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (\n  CASE entity_type\n    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)\n    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)\n    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)\n    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)\n    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)\n    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)\n    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order c WHERE c.id = entity_id)\n    WHEN 'lead_qr_code' THEN EXISTS (SELECT 1 FROM lead_qr_code c WHERE c.id = entity_id)\n    WHEN 'task' THEN EXISTS (SELECT 1 FROM task c WHERE c.id = entity_id)\n    WHEN 'meeting_minutes' THEN EXISTS (SELECT 1 FROM meeting_minutes c WHERE c.id = entity_id)\n    WHEN 'complaint' THEN EXISTS (SELECT 1 FROM complaint c WHERE c.id = entity_id)\n    WHEN 'subsidy_application' THEN EXISTS (SELECT 1 FROM subsidy_application c WHERE c.id = entity_id)\n    WHEN 'scheme' THEN EXISTS (SELECT 1 FROM scheme c WHERE c.id = entity_id)\n    ELSE (SELECT app_is_system())\n  END\n)"

# rewards V:own (a field officer) reads no partner's points, even of a dealer it can see
# (FS-032 review B3)
HAND_POLICIES: list[tuple[str, str]] = [
    # staff read every scheme; a partner user only the active ones that target it (RBAC 6.3)
    ("scheme", f"CREATE POLICY scheme_sel ON scheme FOR SELECT USING ({_VIEW} AND ({_PARTNER} IS NULL OR (is_active AND scheme_applies_to_partner(id, {_PARTNER}))))"),
    ("scheme", "CREATE POLICY scheme_ins ON scheme FOR INSERT WITH CHECK ((SELECT app_has_permission('schemes', 'create')) AND (SELECT app_current_partner()) IS NULL)"),
    ("scheme", "CREATE POLICY scheme_upd ON scheme FOR UPDATE USING ((SELECT app_has_permission('schemes', 'edit')) AND (SELECT app_current_partner()) IS NULL)"),
    # a partner user never sees which other partners a scheme names
    ("scheme_target", f"CREATE POLICY scheme_target_sel ON scheme_target FOR SELECT USING (EXISTS (SELECT 1 FROM scheme s WHERE s.id = scheme_id) AND ({_PARTNER} IS NULL OR target_type <> 'partner'))"),
    ("scheme_target", "CREATE POLICY scheme_target_ins ON scheme_target FOR INSERT WITH CHECK (((SELECT app_has_permission('schemes', 'create')) OR (SELECT app_has_permission('schemes', 'edit'))) AND (SELECT app_current_partner()) IS NULL)"),
    ("scheme_target", "CREATE POLICY scheme_target_del ON scheme_target FOR DELETE USING ((SELECT app_has_permission('schemes', 'edit')) AND (SELECT app_current_partner()) IS NULL)"),
    ("scheme_benefit", "CREATE POLICY scheme_benefit_sel ON scheme_benefit FOR SELECT USING (EXISTS (SELECT 1 FROM sales_order o WHERE o.id = sales_order_id))"),
    ("scheme_entitlement", f"CREATE POLICY scheme_entitlement_sel ON scheme_entitlement FOR SELECT USING ({_VIEW} AND EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id))"),
    ("activity_event", ACTIVITY_SEL),
    ("reward_ledger", "CREATE POLICY reward_ledger_sel ON reward_ledger FOR SELECT USING ((SELECT app_has_permission('rewards', 'view')) AND CASE holder_type WHEN 'partner' THEN ((SELECT app_current_partner()) IS NOT NULL OR (SELECT app_scope('rewards')) <> 'own') AND EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id) ELSE user_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = user_id) END)"),
]

# ── functions ────────────────────────────────────────────────────────────────

FUNCTIONS = [
    # the header targets: territory, partner type, partner. Same type OR'd, types AND'd (ADR-035)
    """CREATE FUNCTION scheme_header_fits(p_scheme uuid, p_partner uuid, p_territory uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT (NOT EXISTS (SELECT 1 FROM scheme_target t WHERE t.scheme_id = p_scheme AND t.target_type = 'territory')
            OR EXISTS (SELECT 1 FROM scheme_target t JOIN territory_closure tc ON tc.ancestor_id::text = t.target_id
                        WHERE t.scheme_id = p_scheme AND t.target_type = 'territory' AND tc.descendant_id = p_territory))
       AND (NOT EXISTS (SELECT 1 FROM scheme_target t WHERE t.scheme_id = p_scheme AND t.target_type = 'partner_type')
            OR EXISTS (SELECT 1 FROM scheme_target t JOIN channel_partner c ON c.id = p_partner
                        WHERE t.scheme_id = p_scheme AND t.target_type = 'partner_type' AND t.target_id = c.partner_type::text))
       AND (NOT EXISTS (SELECT 1 FROM scheme_target t WHERE t.scheme_id = p_scheme AND t.target_type = 'partner')
            OR EXISTS (SELECT 1 FROM scheme_target t JOIN partner_closure pc ON pc.ancestor_id::text = t.target_id
                        WHERE t.scheme_id = p_scheme AND t.target_type = 'partner' AND pc.descendant_id = p_partner))
$fn$""",
    """CREATE FUNCTION scheme_applies_to_partner(p_scheme uuid, p_partner uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT scheme_header_fits(p_scheme, p_partner, (SELECT territory_id FROM channel_partner WHERE id = p_partner))
$fn$""",
    # the order's lines a scheme counts (product and category targets are one line filter,
    # OR'd), as the full figures or the delivered ones (rule 9)
    """CREATE FUNCTION scheme_line_basis(p_scheme uuid, p_order uuid, p_delivered boolean,
                                     OUT value numeric, OUT qty numeric, OUT lines int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(sum(CASE WHEN p_delivered THEN round(l.taxable * s.sent / l.qty, 2) ELSE l.taxable END), 0),
           coalesce(sum(CASE WHEN p_delivered THEN s.sent ELSE l.qty END), 0),
           count(*) FILTER (WHERE NOT p_delivered OR s.sent > 0)::int
      FROM order_line l
      JOIN product pr ON pr.id = l.product_id
      CROSS JOIN LATERAL (SELECT coalesce(sum(dl.qty), 0) AS sent FROM dispatch_line dl
                            JOIN dispatch d ON d.id = dl.dispatch_id
                           WHERE dl.order_line_id = l.id AND d.voided_at IS NULL) s
     WHERE l.sales_order_id = p_order
       AND (NOT EXISTS (SELECT 1 FROM scheme_target t WHERE t.scheme_id = p_scheme
                          AND t.target_type IN ('product', 'product_category'))
            OR EXISTS (SELECT 1 FROM scheme_target t WHERE t.scheme_id = p_scheme
                          AND ((t.target_type = 'product' AND t.target_id = l.product_id::text)
                               OR (t.target_type = 'product_category' AND t.target_id = pr.product_category_id::text))))
$fn$""",
    """CREATE FUNCTION scheme_meets(p_scheme scheme, p_value numeric, p_qty numeric) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp AS $fn$
    SELECT CASE p_scheme.metric WHEN 'order_value' THEN p_value ELSE p_qty END >= p_scheme.condition_min
       AND (p_scheme.condition_max IS NULL
            OR CASE p_scheme.metric WHEN 'order_value' THEN p_value ELSE p_qty END <= p_scheme.condition_max)
$fn$""",
    # rule 5: pct of the value basis or the flat value, then the cap
    """CREATE FUNCTION scheme_amount(p_kind scheme_benefit_kind, p_value numeric, p_cap numeric, p_basis numeric) RETURNS numeric
LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp AS $fn$
    SELECT least(CASE p_kind WHEN 'pct' THEN round(p_basis * p_value / 100, 2) ELSE round(p_value, 2) END,
                 coalesce(p_cap, 'Infinity'::numeric))
$fn$""",
    # type 1 at p_on: priority, then code; a non-stackable one ends the chain (rule 6)
    """CREATE FUNCTION scheme_discounts(p_order uuid, p_on date)
RETURNS TABLE (scheme_id uuid, basis numeric, amount numeric)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE o sales_order%ROWTYPE; s scheme%ROWTYPE; b record; v_left numeric; v_amt numeric;
        v_any boolean := false; v_all_stack boolean := true;
BEGIN
    SELECT * INTO o FROM sales_order WHERE id = p_order;
    IF o.id IS NULL OR o.order_type NOT IN ('commercial', 'industrial') THEN RETURN; END IF;
    v_left := o.total;
    FOR s IN SELECT * FROM scheme x WHERE x.scheme_type = 'order_discount' AND x.is_active
               AND x.valid_from <= p_on AND (x.valid_to IS NULL OR x.valid_to >= p_on)
             ORDER BY x.priority, x.code LOOP
        CONTINUE WHEN NOT scheme_header_fits(s.id, o.partner_id, o.territory_id);
        SELECT * INTO b FROM scheme_line_basis(s.id, p_order, false);
        CONTINUE WHEN b.lines = 0 OR NOT scheme_meets(s, b.value, b.qty);
        CONTINUE WHEN v_any AND NOT (s.stackable AND v_all_stack);
        v_amt := least(scheme_amount(s.benefit_kind, s.benefit_value, s.benefit_cap, b.value), v_left);
        CONTINUE WHEN v_amt <= 0;
        v_left := v_left - v_amt;
        v_any := true;
        v_all_stack := v_all_stack AND s.stackable;
        scheme_id := s.id; basis := b.value; amount := v_amt;
        RETURN NEXT;
    END LOOP;
END $fn$""",
    # rule 7: what each available, unexpired entitlement is worth on this order
    """CREATE FUNCTION scheme_entitlement_value(e scheme_entitlement, p_taxable numeric) RETURNS numeric
LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp AS $fn$
    SELECT scheme_amount(e.kind, e.value, e.cap, p_taxable)
$fn$""",
    # types 2 and 3 at p_on, on the delivered or the full basis
    """CREATE FUNCTION scheme_delivery_awards(p_order uuid, p_on date, p_delivered boolean)
RETURNS TABLE (scheme_id uuid, scheme_type scheme_type, basis numeric, points int,
               kind scheme_benefit_kind, value numeric, cap numeric, entitlement_days int)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE o sales_order%ROWTYPE; s scheme%ROWTYPE; b record;
BEGIN
    SELECT * INTO o FROM sales_order WHERE id = p_order;
    IF o.id IS NULL OR o.partner_id IS NULL OR o.order_type NOT IN ('commercial', 'industrial') THEN RETURN; END IF;
    FOR s IN SELECT * FROM scheme x WHERE x.scheme_type IN ('order_points', 'next_order') AND x.is_active
               AND x.valid_from <= p_on AND (x.valid_to IS NULL OR x.valid_to >= p_on)
             ORDER BY x.priority, x.code LOOP
        CONTINUE WHEN NOT scheme_header_fits(s.id, o.partner_id, o.territory_id);
        SELECT * INTO b FROM scheme_line_basis(s.id, p_order, p_delivered);
        CONTINUE WHEN b.lines = 0 OR NOT scheme_meets(s, b.value, b.qty);
        scheme_id := s.id; scheme_type := s.scheme_type; basis := b.value;
        points := CASE WHEN s.benefit_kind = 'points' THEN s.benefit_value::int END;
        kind := s.benefit_kind; value := s.benefit_value; cap := s.benefit_cap;
        entitlement_days := s.entitlement_days;
        RETURN NEXT;
    END LOOP;
END $fn$""",
    """CREATE FUNCTION scheme_event(p_entity text, p_id uuid, p_partner uuid, p_lead uuid, p_kind text, p_payload jsonb)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    INSERT INTO activity_event (entity_type, entity_id, partner_id, lead_id, kind, actor_id, payload)
    VALUES (p_entity, p_id, p_partner, p_lead, p_kind, app_current_user_id(),
            jsonb_build_object('actor_name', coalesce((SELECT full_name FROM app_user WHERE id = app_current_user_id()), ''))
            || p_payload)
$fn$""",
    # the one writer (plan review B2): every status move of every order, every path
    """CREATE FUNCTION scheme_on_order_status() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE r record; e scheme_entitlement%ROWTYPE; v_left numeric; v_amt numeric; v_on date;
        v_ref jsonb; v_id uuid; v_n int; v_st text;
BEGIN
    IF NEW.order_type NOT IN ('commercial', 'industrial') THEN RETURN NULL; END IF;
    v_ref := jsonb_build_object('order_no', NEW.order_no);

    IF OLD.status = 'draft' AND NEW.status = 'submitted' THEN
        IF EXISTS (SELECT 1 FROM scheme_benefit WHERE sales_order_id = NEW.id AND status = 'applied') THEN
            RETURN NULL;
        END IF;
        v_left := NEW.total;
        FOR r IN SELECT * FROM scheme_discounts(NEW.id, NEW.tax_date) LOOP
            INSERT INTO scheme_benefit (sales_order_id, scheme_id, kind, basis, amount)
            VALUES (NEW.id, r.scheme_id, 'discount', r.basis, r.amount);
            v_left := v_left - r.amount;
            PERFORM scheme_event('sales_order', NEW.id, NEW.partner_id, NEW.lead_id, 'order.scheme_applied',
                                 v_ref || jsonb_build_object('scheme_code', (SELECT code FROM scheme WHERE id = r.scheme_id)));
        END LOOP;
        IF NEW.partner_id IS NOT NULL THEN
            -- plan review B3: the order is locked by order_submit; then each entitlement
            FOR e IN SELECT * FROM scheme_entitlement x WHERE x.partner_id = NEW.partner_id
                       AND x.status = 'available' AND x.expires_at > now()
                     ORDER BY x.expires_at, x.id FOR UPDATE LOOP
                v_amt := scheme_entitlement_value(e, NEW.taxable);
                CONTINUE WHEN v_amt <= 0 OR v_amt > v_left;      -- skipped, not cut (rule 7)
                UPDATE scheme_entitlement SET status = 'consumed', consumed_order_id = NEW.id, consumed_at = now()
                 WHERE id = e.id AND status = 'available';
                GET DIAGNOSTICS v_n = ROW_COUNT;
                CONTINUE WHEN v_n = 0;
                INSERT INTO scheme_benefit (sales_order_id, scheme_id, entitlement_id, kind, basis, amount)
                VALUES (NEW.id, e.scheme_id, e.id, 'entitlement_used', NEW.taxable, v_amt);
                v_left := v_left - v_amt;
                PERFORM scheme_event('channel_partner', e.id, NEW.partner_id, NULL, 'partner.entitlement_consumed', v_ref);
            END LOOP;
        END IF;

    ELSIF NEW.status IN ('draft', 'cancelled') THEN
        FOR r IN UPDATE scheme_benefit SET status = 'reversed', reversed_at = now()
                  WHERE sales_order_id = NEW.id AND status = 'applied' RETURNING * LOOP
            IF r.entitlement_id IS NOT NULL THEN
                UPDATE scheme_entitlement
                   SET status = CASE WHEN expires_at > now() THEN 'available' ELSE 'expired' END,
                       consumed_order_id = NULL, consumed_at = NULL
                 WHERE id = r.entitlement_id AND status = 'consumed' AND consumed_order_id = NEW.id
                RETURNING status INTO v_st;
                -- a credit past its date comes back expired, and the event says so (code review F-6)
                PERFORM scheme_event('channel_partner', r.entitlement_id, NEW.partner_id, NULL,
                                     CASE WHEN v_st = 'expired' THEN 'partner.entitlement_expired'
                                          ELSE 'partner.entitlement_released' END, v_ref);
            ELSE
                PERFORM scheme_event('sales_order', NEW.id, NEW.partner_id, NEW.lead_id, 'order.scheme_reversed',
                                     v_ref || jsonb_build_object('scheme_code', (SELECT code FROM scheme WHERE id = r.scheme_id)));
            END IF;
        END LOOP;

    ELSIF NEW.status IN ('dispatched', 'closed_short') THEN
        IF NEW.partner_id IS NULL THEN RETURN NULL; END IF;
        SELECT (max(dispatched_at) AT TIME ZONE 'Asia/Kolkata')::date INTO v_on
          FROM dispatch WHERE sales_order_id = NEW.id AND voided_at IS NULL;
        IF v_on IS NULL THEN RETURN NULL; END IF;        -- closed short with nothing sent
        FOR r IN SELECT * FROM scheme_delivery_awards(NEW.id, v_on, true) LOOP
            IF r.scheme_type = 'order_points' THEN
                INSERT INTO reward_ledger (holder_type, partner_id, points, kind, reason, scheme_id, source_order_id, created_by)
                VALUES ('partner', NEW.partner_id, r.points, 'earned',
                        'Scheme ' || (SELECT code FROM scheme WHERE id = r.scheme_id) || ' on order ' || NEW.order_no,
                        r.scheme_id, NEW.id, app_current_user_id())
                ON CONFLICT (scheme_id, source_order_id) WHERE kind = 'earned' AND reversed_at IS NULL
                    AND source_order_id IS NOT NULL AND scheme_id IS NOT NULL DO NOTHING
                RETURNING id INTO v_id;
                IF v_id IS NOT NULL THEN
                    PERFORM scheme_event('channel_partner', v_id, NEW.partner_id, NULL, 'partner.points_earned',
                                         v_ref || jsonb_build_object('points', r.points));
                END IF;
            ELSE
                INSERT INTO scheme_entitlement (scheme_id, partner_id, source_order_id, kind, value, cap, basis, expires_at)
                VALUES (r.scheme_id, NEW.partner_id, NEW.id, r.kind, r.value, r.cap, r.basis,
                        ((v_on + r.entitlement_days + 1)::timestamp AT TIME ZONE 'Asia/Kolkata'))
                ON CONFLICT (scheme_id, source_order_id) WHERE source_order_id IS NOT NULL AND status <> 'reversed' DO NOTHING
                RETURNING id INTO v_id;
                IF v_id IS NOT NULL THEN
                    PERFORM scheme_event('channel_partner', v_id, NEW.partner_id, NULL, 'partner.entitlement_earned', v_ref);
                END IF;
            END IF;
            v_id := NULL;
        END LOOP;

    ELSIF OLD.status = 'dispatched' AND NEW.status IN ('approved', 'partially_dispatched') THEN
        -- a void (rule 13): what this order earned and nobody has used yet
        FOR r IN UPDATE scheme_entitlement SET status = 'reversed', reversed_at = now()
                  WHERE source_order_id = NEW.id AND status = 'available' RETURNING id LOOP
            PERFORM scheme_event('channel_partner', r.id, NEW.partner_id, NULL, 'partner.entitlement_reversed', v_ref);
        END LOOP;
        -- GAP-312: a consumed one stays; the event records that it was not reversed
        FOR r IN SELECT id FROM scheme_entitlement WHERE source_order_id = NEW.id AND status = 'consumed' LOOP
            PERFORM scheme_event('channel_partner', r.id, NEW.partner_id, NULL, 'partner.entitlement_kept_after_void', v_ref);
        END LOOP;
        FOR r IN UPDATE reward_ledger SET reversed_at = now()
                  WHERE source_order_id = NEW.id AND kind = 'earned' AND reversed_at IS NULL AND scheme_id IS NOT NULL
                  RETURNING * LOOP
            INSERT INTO reward_ledger (holder_type, partner_id, user_id, points, kind, reason, scheme_id, source_order_id,
                                       reverses_id, created_by)
            VALUES (r.holder_type, r.partner_id, r.user_id, -r.points, 'reversed',
                    'Dispatch voided on order ' || NEW.order_no, r.scheme_id, NEW.id, r.id, app_current_user_id());
            PERFORM scheme_event('channel_partner', r.id, NEW.partner_id, NULL, 'partner.points_reversed',
                                 v_ref || jsonb_build_object('points', r.points));
        END LOOP;
    END IF;
    RETURN NULL;
END $fn$""",
    # GET /orders/{id}/schemes: the trigger's own functions, read-only, on a draft
    """CREATE FUNCTION scheme_order_preview(p_order uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE o sales_order%ROWTYPE; v_today date := (now() AT TIME ZONE 'Asia/Kolkata')::date;
        v_left numeric; v_amt numeric; e scheme_entitlement%ROWTYPE; r record;
        v_disc jsonb := '[]'; v_ents jsonb := '[]'; v_del jsonb := '[]';
BEGIN
    IF NOT order_visible(p_order) THEN
        RAISE EXCEPTION 'order not found' USING ERRCODE = 'ORDNF';
    END IF;
    SELECT * INTO o FROM sales_order WHERE id = p_order;
    IF o.status <> 'draft' THEN
        RAISE EXCEPTION 'the order is %', o.status USING ERRCODE = 'ORDNS';
    END IF;
    v_left := o.total;
    FOR r IN SELECT * FROM scheme_discounts(p_order, v_today) LOOP
        v_disc := v_disc || jsonb_build_object('scheme_id', r.scheme_id, 'basis', r.basis, 'amount', r.amount);
        v_left := v_left - r.amount;
    END LOOP;
    IF o.partner_id IS NOT NULL AND o.order_type IN ('commercial', 'industrial') THEN
        FOR e IN SELECT * FROM scheme_entitlement x WHERE x.partner_id = o.partner_id
                   AND x.status = 'available' AND x.expires_at > now() ORDER BY x.expires_at, x.id LOOP
            v_amt := scheme_entitlement_value(e, o.taxable);
            CONTINUE WHEN v_amt <= 0 OR v_amt > v_left;
            v_ents := v_ents || jsonb_build_object('entitlement_id', e.id, 'scheme_id', e.scheme_id, 'amount', v_amt);
            v_left := v_left - v_amt;
        END LOOP;
    END IF;
    FOR r IN SELECT * FROM scheme_delivery_awards(p_order, v_today, false) LOOP
        v_del := v_del || jsonb_build_object('scheme_id', r.scheme_id, 'kind', r.scheme_type::text,
                                             'points', r.points, 'basis', r.basis);
    END LOOP;
    RETURN jsonb_build_object('discounts', v_disc, 'entitlements', v_ents, 'on_delivery', v_del,
                              'total', o.total, 'payable', v_left);
END $fn$""",
    # a partner's delivered figures over a period: the latest live dispatch decides the day (rule 10)
    """CREATE FUNCTION scheme_period_basis(p_scheme uuid, p_partner uuid, p_from date, p_to date,
                                       OUT value numeric, OUT qty numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(sum(b.value), 0), coalesce(sum(b.qty), 0)
      FROM sales_order o
      CROSS JOIN LATERAL (SELECT (max(d.dispatched_at) AT TIME ZONE 'Asia/Kolkata')::date AS day
                            FROM dispatch d WHERE d.sales_order_id = o.id AND d.voided_at IS NULL) dd
      CROSS JOIN LATERAL scheme_line_basis(p_scheme, o.id, true) b
     WHERE o.partner_id = p_partner AND o.order_type IN ('commercial', 'industrial')
       AND o.status IN ('dispatched', 'closed_short') AND o.deleted_at IS NULL
       AND dd.day BETWEEN p_from AND p_to
       AND scheme_header_fits(p_scheme, o.partner_id, o.territory_id)
$fn$""",
    # the periods of a scheme that ended before p_today, clipped to its dates (rule 11)
    """CREATE FUNCTION scheme_periods(p_scheme scheme, p_until date)
RETURNS TABLE (period_start date, period_end date)
LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp AS $fn$
    SELECT greatest(gs::date, p_scheme.valid_from),
           least((gs + CASE p_scheme.period WHEN 'month' THEN interval '1 month' ELSE interval '3 months' END
                  - interval '1 day')::date, p_scheme.valid_to)
      FROM generate_series(date_trunc(CASE p_scheme.period WHEN 'month' THEN 'month' ELSE 'quarter' END,
                                      p_scheme.valid_from::timestamp),
                           least(p_until, p_scheme.valid_to)::timestamp,
                           CASE p_scheme.period WHEN 'month' THEN interval '1 month' ELSE interval '3 months' END) gs
$fn$""",
    # the nightly type 4 run. Idempotent: unique per scheme, partner and period
    """CREATE FUNCTION scheme_period_evaluate(p_today date) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE s scheme%ROWTYPE; p record; c record; v_amt numeric; v_n int := 0; v_id uuid;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'the period run is the worker''s' USING ERRCODE = '42501';
    END IF;
    FOR s IN SELECT * FROM scheme WHERE scheme_type = 'period' AND is_active LOOP
        FOR p IN SELECT * FROM scheme_periods(s, p_today)
                  WHERE period_end < p_today AND period_end >= p_today - 100 LOOP
            FOR c IN SELECT o.partner_id, b.value, b.qty
                       FROM (SELECT DISTINCT partner_id FROM sales_order
                              WHERE partner_id IS NOT NULL AND status IN ('dispatched', 'closed_short')
                                AND order_type IN ('commercial', 'industrial')) o
                       CROSS JOIN LATERAL scheme_period_basis(s.id, o.partner_id, p.period_start, p.period_end) b
                      WHERE (b.value > 0 OR b.qty > 0) LOOP
                CONTINUE WHEN NOT scheme_meets(s, c.value, c.qty);
                v_id := NULL;
                IF s.benefit_kind = 'points' THEN
                    INSERT INTO reward_ledger (holder_type, partner_id, points, kind, reason, scheme_id, period_start)
                    VALUES ('partner', c.partner_id, s.benefit_value::int, 'earned',
                            'Scheme ' || s.code || ' for ' || p.period_start || ' to ' || p.period_end,
                            s.id, p.period_start)
                    ON CONFLICT (scheme_id, partner_id, period_start) WHERE kind = 'earned' AND reversed_at IS NULL
                        AND period_start IS NOT NULL DO NOTHING
                    RETURNING id INTO v_id;
                    IF v_id IS NOT NULL THEN
                        PERFORM scheme_event('channel_partner', v_id, c.partner_id, NULL, 'partner.points_earned',
                                             jsonb_build_object('scheme_code', s.code, 'points', s.benefit_value::int));
                    END IF;
                ELSE
                    -- a period pct is a share of what was achieved, fixed now as a flat credit
                    v_amt := scheme_amount(s.benefit_kind, s.benefit_value, s.benefit_cap, c.value);
                    CONTINUE WHEN v_amt <= 0;
                    INSERT INTO scheme_entitlement (scheme_id, partner_id, period_start, period_end, kind, value,
                                                    basis, expires_at)
                    VALUES (s.id, c.partner_id, p.period_start, p.period_end, 'flat', v_amt, c.value,
                            ((p_today + s.entitlement_days + 1)::timestamp AT TIME ZONE 'Asia/Kolkata'))
                    ON CONFLICT (scheme_id, partner_id, period_start) WHERE period_start IS NOT NULL
                        AND status <> 'reversed' DO NOTHING
                    RETURNING id INTO v_id;
                    IF v_id IS NOT NULL THEN
                        PERFORM scheme_event('channel_partner', v_id, c.partner_id, NULL, 'partner.entitlement_earned',
                                             jsonb_build_object('scheme_code', s.code));
                    END IF;
                END IF;
                IF v_id IS NOT NULL THEN v_n := v_n + 1; END IF;
            END LOOP;
        END LOOP;
    END LOOP;
    RETURN v_n;
END $fn$""",
    """CREATE FUNCTION scheme_entitlement_expire() RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE r record; v_n int := 0;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'the expiry run is the worker''s' USING ERRCODE = '42501';
    END IF;
    FOR r IN UPDATE scheme_entitlement SET status = 'expired'
              WHERE status = 'available' AND expires_at <= now() RETURNING id, partner_id LOOP
        PERFORM scheme_event('channel_partner', r.id, r.partner_id, NULL, 'partner.entitlement_expired', '{}'::jsonb);
        v_n := v_n + 1;
    END LOOP;
    RETURN v_n;
END $fn$""",
    # type 4's progress bar: the partner's delivered total in the period holding p_today
    """CREATE FUNCTION scheme_standing(p_scheme uuid, p_partner uuid, p_today date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE s scheme%ROWTYPE; p record; b record;
BEGIN
    SELECT * INTO s FROM scheme WHERE id = p_scheme;
    IF s.id IS NULL OR NOT EXISTS (SELECT 1 FROM channel_partner WHERE id = p_partner) THEN
        RETURN NULL;
    END IF;
    SELECT * INTO p FROM scheme_periods(s, greatest(p_today, s.valid_from))
     WHERE period_start <= greatest(p_today, s.valid_from) ORDER BY period_start DESC LIMIT 1;
    IF p.period_start IS NULL THEN RETURN NULL; END IF;
    SELECT * INTO b FROM scheme_period_basis(s.id, p_partner, p.period_start, p.period_end);
    RETURN jsonb_build_object('period_start', p.period_start, 'period_end', p.period_end,
                              'metric', s.metric::text,
                              'achieved', CASE s.metric WHEN 'order_value' THEN b.value ELSE b.qty END,
                              'min', s.condition_min, 'max', s.condition_max,
                              'qualifies', scheme_meets(s, b.value, b.qty));
END $fn$""",
    # a benefit on an order names its scheme even when the scheme row is hidden from the
    # reader (a dealer, after the scheme stopped targeting it): code and name only
    """CREATE FUNCTION scheme_names(p_ids uuid[]) RETURNS TABLE (id uuid, code citext, name text, priority int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT s.id, s.code, s.name, s.priority FROM scheme s WHERE s.id = ANY(p_ids)
$fn$""",
    # rule 16: a scheme that has given anything keeps its terms
    """CREATE FUNCTION scheme_used(p_scheme uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM scheme_benefit WHERE scheme_id = p_scheme)
        OR EXISTS (SELECT 1 FROM scheme_entitlement WHERE scheme_id = p_scheme)
        OR EXISTS (SELECT 1 FROM reward_ledger WHERE scheme_id = p_scheme)
$fn$""",
    """CREATE FUNCTION refuse_used_scheme_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT scheme_used(OLD.id) THEN RETURN NEW; END IF;
    IF (to_jsonb(NEW) - ARRAY['valid_to', 'is_active', 'updated_at', 'updated_by'])
       IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['valid_to', 'is_active', 'updated_at', 'updated_by']) THEN
        RAISE EXCEPTION 'the scheme has been used; end it and create a new one' USING ERRCODE = 'SCHIU';
    END IF;
    IF NEW.valid_to IS DISTINCT FROM OLD.valid_to AND (NEW.valid_to IS NULL
         OR (OLD.valid_to IS NOT NULL AND NEW.valid_to > OLD.valid_to)
         OR NEW.valid_to < (now() AT TIME ZONE 'Asia/Kolkata')::date) THEN
        RAISE EXCEPTION 'a used scheme''s end date only moves earlier, and not before today' USING ERRCODE = 'SCHIU';
    END IF;
    RETURN NEW;
END $fn$""",
    """CREATE FUNCTION refuse_used_scheme_target() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    IF scheme_used(coalesce(NEW.scheme_id, OLD.scheme_id)) THEN
        RAISE EXCEPTION 'the scheme has been used; its targets are fixed' USING ERRCODE = 'SCHIU';
    END IF;
    RETURN coalesce(NEW, OLD);
END $fn$""",
]

TRIGGERS = [
    "CREATE TRIGGER trg_scheme_updated_at BEFORE UPDATE ON scheme FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_scheme_audit AFTER INSERT OR UPDATE OR DELETE ON scheme FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_scheme_refuse_used BEFORE UPDATE ON scheme FOR EACH ROW EXECUTE FUNCTION refuse_used_scheme_edit()",
    "CREATE TRIGGER trg_scheme_target_refuse_used BEFORE INSERT OR DELETE ON scheme_target FOR EACH ROW EXECUTE FUNCTION refuse_used_scheme_target()",
    "CREATE TRIGGER trg_scheme_target_audit AFTER INSERT OR UPDATE OR DELETE ON scheme_target FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_scheme_entitlement_audit AFTER INSERT OR UPDATE OR DELETE ON scheme_entitlement FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_scheme_benefit_audit AFTER INSERT OR UPDATE OR DELETE ON scheme_benefit FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_reward_ledger_audit AFTER INSERT OR UPDATE OR DELETE ON reward_ledger FOR EACH ROW EXECUTE FUNCTION audit_row()",
    # zz: after trg_sales_order_close_short, which writes qty_short (plan review B2)
    "CREATE TRIGGER trg_sales_order_zz_schemes AFTER UPDATE OF status ON sales_order FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status) EXECUTE FUNCTION scheme_on_order_status()",
]

GRANTED = [
    "scheme_applies_to_partner(uuid, uuid)",
    "scheme_order_preview(uuid)",
    "scheme_standing(uuid, uuid, date)",
    "scheme_period_evaluate(date)",
    "scheme_entitlement_expire()",
    "scheme_used(uuid)",
    "scheme_names(uuid[])",
]
INTERNAL = [
    "scheme_header_fits(uuid, uuid, uuid)",
    "scheme_line_basis(uuid, uuid, boolean)",
    "scheme_meets(scheme, numeric, numeric)",
    "scheme_amount(scheme_benefit_kind, numeric, numeric, numeric)",
    "scheme_discounts(uuid, date)",
    "scheme_entitlement_value(scheme_entitlement, numeric)",
    "scheme_delivery_awards(uuid, date, boolean)",
    "scheme_event(text, uuid, uuid, uuid, text, jsonb)",
    "scheme_on_order_status()",
    "scheme_period_basis(uuid, uuid, date, date)",
    "scheme_periods(scheme, date)",
    "refuse_used_scheme_edit()",
    "refuse_used_scheme_target()",
]


def _load(stem: str) -> object:
    path = next(Path(__file__).parent.glob(f"{stem}_*.py"))
    spec = importlib.util.spec_from_file_location(f"mig_{stem}_for_033", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"033: migration {stem} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def upgrade() -> None:
    for stmt in ENUMS + TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for table, stmt in HAND_POLICIES:
        if table == "activity_event":
            op.execute("DROP POLICY activity_event_sel ON activity_event")
        op.execute(stmt)
    for stmt in TRIGGERS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    # a function created here is PUBLIC-executable until this runs (028's lesson)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    m025 = _load("025")
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(next(st for t, st in m025.HAND_POLICIES if t == "activity_event"))  # type: ignore[attr-defined]
    op.execute("DELETE FROM activity_event WHERE entity_type = 'scheme' OR kind LIKE 'partner.entitlement_%' "
               "OR kind IN ('partner.points_earned', 'partner.points_reversed', 'order.scheme_applied', "
               "'order.scheme_reversed')")
    op.execute("DROP TRIGGER IF EXISTS trg_sales_order_zz_schemes ON sales_order")
    for table in ("reward_ledger", "scheme_benefit", "scheme_entitlement", "scheme_target", "scheme"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    for name in ("scheme_target_type", "scheme_period", "scheme_benefit_kind", "scheme_metric", "scheme_type"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
