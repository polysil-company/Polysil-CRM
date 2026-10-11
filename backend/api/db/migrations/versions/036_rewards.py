"""036: reward points and redemption (FS-032).

- `reward_rule`: earning rules. `order_value` rules earn on a delivered order's value
  before GST, for the partner or for the staff owner; `lead_won` rules earn a flat
  number of points for the staff owner of a won lead.
- `reward_setting`: the rupee value of a point and the most of an order's total points
  may pay, one effective-dated row each time it changes.
- `gift` and `reward_redemption`: a request to spend points on an order or a gift.
  The points are held at once by a `redeemed` ledger row; a reject, a withdrawal, a
  cancel or an unneeded remainder writes a `released` row.
- `reward_ledger` (033) gains the rule, the lead, the redemption and the lot an
  expiry row closes.
- Every spend goes through `reward_spend()`, under a per-holder advisory lock (plan
  review B2). The nightly expiry takes the same lock.
- Earning is triggers, never service hooks (plan review B4): 033's order trigger is
  re-created from its own text by exact anchors, and a new trigger on `lead` earns on
  a win, whichever of the three writers won it.
- An order redemption becomes a `scheme_benefit` of kind `reward_redemption` at
  submit, after the scheme benefits, so `payable` stays one sum (plan review B1).

Revision ID: 036_rewards
Revises: 033_schemes
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "036_rewards"
down_revision: str | None = "033_schemes"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id)"""


def _load(stem: str) -> ModuleType:
    path = next(Path(__file__).parent.glob(f"{stem}_*.py"))
    spec = importlib.util.spec_from_file_location(f"mig_{stem}_for_036", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"036: migration {stem} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    # an exception, not an assert: python -O drops asserts
    if text.count(old) != 1:
        raise RuntimeError(f"036: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


TABLES = [
    f"""CREATE TABLE reward_rule (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE CHECK (code ~ '^[A-Za-z0-9_-]{{2,40}}$'),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    holder text NOT NULL CHECK (holder IN ('partner', 'staff')),
    basis text NOT NULL CHECK (basis IN ('order_value', 'lead_won')),
    points int NOT NULL CHECK (points BETWEEN 1 AND 1000000),
    per_amount numeric(14,2) CHECK (per_amount IS NULL OR per_amount > 0),
    valid_from date NOT NULL,
    valid_to date,
    expiry_days int CHECK (expiry_days IS NULL OR expiry_days BETWEEN 1 AND 3650),
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT ck_reward_rule_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_reward_rule_shape CHECK (
        (basis = 'order_value' AND per_amount IS NOT NULL)
        OR (basis = 'lead_won' AND holder = 'staff' AND per_amount IS NULL))
)""",
    f"""CREATE TABLE reward_setting (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    point_value numeric(10,2) NOT NULL CHECK (point_value > 0),
    max_redeem_pct numeric(5,2) NOT NULL CHECK (max_redeem_pct > 0 AND max_redeem_pct <= 100),
    effective_from date NOT NULL UNIQUE,
    {AUDIT}
)""",
    f"""CREATE TABLE gift (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    description text CHECK (description IS NULL OR length(description) <= 2000),
    points_cost int NOT NULL CHECK (points_cost BETWEEN 1 AND 10000000),
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT}
)""",
    """CREATE TABLE reward_redemption (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind text NOT NULL CHECK (kind IN ('order', 'gift')),
    holder_type text NOT NULL CHECK (holder_type IN ('partner', 'user')),
    partner_id uuid REFERENCES channel_partner(id),
    user_id uuid REFERENCES app_user(id),
    sales_order_id uuid REFERENCES sales_order(id),
    gift_id uuid REFERENCES gift(id),
    points int NOT NULL CHECK (points > 0),
    amount numeric(14,2),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'applied', 'fulfilled', 'rejected', 'withdrawn', 'released')),
    remark text CHECK (remark IS NULL OR length(remark) <= 1000),
    decided_by uuid REFERENCES app_user(id),
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES app_user(id),
    CONSTRAINT ck_reward_redemption_holder CHECK (
        (holder_type = 'partner' AND partner_id IS NOT NULL AND user_id IS NULL)
        OR (holder_type = 'user' AND user_id IS NOT NULL AND partner_id IS NULL)),
    CONSTRAINT ck_reward_redemption_kind CHECK (
        (kind = 'order' AND sales_order_id IS NOT NULL AND gift_id IS NULL AND holder_type = 'partner'
         AND status IN ('pending', 'applied', 'released'))
        OR (kind = 'gift' AND gift_id IS NOT NULL AND sales_order_id IS NULL
            AND status IN ('pending', 'fulfilled', 'rejected', 'withdrawn')))
)""",
    "CREATE UNIQUE INDEX uq_reward_redemption_order ON reward_redemption (sales_order_id) WHERE kind = 'order' AND status IN ('pending', 'applied')",
    "CREATE INDEX ix_reward_redemption_partner ON reward_redemption (partner_id, created_at DESC) WHERE partner_id IS NOT NULL",
    "CREATE INDEX ix_reward_redemption_user ON reward_redemption (user_id, created_at DESC) WHERE user_id IS NOT NULL",
    "CREATE INDEX ix_reward_redemption_pending ON reward_redemption (status, created_at) WHERE status = 'pending'",
    "ALTER TABLE reward_ledger ADD COLUMN rule_id uuid REFERENCES reward_rule(id)",
    "ALTER TABLE reward_ledger ADD COLUMN lead_id uuid REFERENCES lead(id)",
    "ALTER TABLE reward_ledger ADD COLUMN redemption_id uuid REFERENCES reward_redemption(id)",
    "ALTER TABLE reward_ledger ADD COLUMN expires_id uuid REFERENCES reward_ledger(id)",
    # plan review S3: an event earns once per rule, among rows not reversed
    "CREATE UNIQUE INDEX uq_reward_ledger_rule_order ON reward_ledger (rule_id, source_order_id, holder_type) WHERE kind = 'earned' AND reversed_at IS NULL AND rule_id IS NOT NULL AND source_order_id IS NOT NULL",
    "CREATE UNIQUE INDEX uq_reward_ledger_rule_lead ON reward_ledger (rule_id, lead_id) WHERE kind = 'earned' AND reversed_at IS NULL AND rule_id IS NOT NULL AND lead_id IS NOT NULL",
    "CREATE UNIQUE INDEX uq_reward_ledger_expires ON reward_ledger (expires_id) WHERE expires_id IS NOT NULL",
    "CREATE INDEX ix_reward_ledger_lots ON reward_ledger (expires_at) WHERE kind = 'earned' AND reversed_at IS NULL AND expires_at IS NOT NULL",
    "CREATE INDEX ix_reward_ledger_redemption ON reward_ledger (redemption_id) WHERE redemption_id IS NOT NULL",
    "CREATE INDEX ix_reward_ledger_source_order ON reward_ledger (source_order_id) WHERE source_order_id IS NOT NULL",
    "CREATE INDEX ix_reward_ledger_lead ON reward_ledger (lead_id) WHERE lead_id IS NOT NULL",
    # an order redemption is a benefit with no scheme (plan review B1)
    "ALTER TABLE scheme_benefit DROP CONSTRAINT scheme_benefit_kind_check",
    "ALTER TABLE scheme_benefit ADD CONSTRAINT scheme_benefit_kind_check CHECK (kind IN ('discount', 'entitlement_used', 'reward_redemption'))",
    "ALTER TABLE scheme_benefit ALTER COLUMN scheme_id DROP NOT NULL",
    "ALTER TABLE scheme_benefit ADD COLUMN redemption_id uuid REFERENCES reward_redemption(id)",
    "ALTER TABLE scheme_benefit ADD CONSTRAINT ck_scheme_benefit_redemption CHECK ((kind = 'reward_redemption') = (scheme_id IS NULL) AND (kind = 'reward_redemption') = (redemption_id IS NOT NULL))",
    "CREATE INDEX ix_scheme_benefit_redemption ON scheme_benefit (redemption_id) WHERE redemption_id IS NOT NULL",
    # stand-ins (GAP-319): ₹1 a point, at most 10% of an order's total
    "INSERT INTO reward_setting (point_value, max_redeem_pct, effective_from) VALUES (1.00, 10.00, DATE '2026-04-01')",
]

RLS_TABLES = ("reward_rule", "reward_setting", "gift", "reward_redemption")

GRANTS: dict[str, str] = {
    "reward_rule": "SELECT, INSERT, UPDATE",
    "reward_setting": "SELECT, INSERT",
    "gift": "SELECT, INSERT, UPDATE",
    # spending and deciding go through the definers
    "reward_redemption": "SELECT",
}

_ADMIN = "(SELECT app_current_partner()) IS NULL"
_HOLDER = ("CASE holder_type WHEN 'partner' THEN ((SELECT app_current_partner()) IS NOT NULL "
           "OR (SELECT app_scope('rewards')) <> 'own') AND EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id) "
           "ELSE user_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = user_id) END")

HAND_POLICIES: list[tuple[str, str]] = [
    ("reward_rule", "CREATE POLICY reward_rule_sel ON reward_rule FOR SELECT USING ((SELECT app_has_permission('rewards', 'view')))"),
    ("reward_rule", f"CREATE POLICY reward_rule_ins ON reward_rule FOR INSERT WITH CHECK ((SELECT app_has_permission('rewards', 'edit')) AND {_ADMIN})"),
    ("reward_rule", f"CREATE POLICY reward_rule_upd ON reward_rule FOR UPDATE USING ((SELECT app_has_permission('rewards', 'edit')) AND {_ADMIN})"),
    ("reward_setting", "CREATE POLICY reward_setting_sel ON reward_setting FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"),
    ("reward_setting", f"CREATE POLICY reward_setting_ins ON reward_setting FOR INSERT WITH CHECK ((SELECT app_has_permission('rewards', 'edit')) AND {_ADMIN})"),
    ("gift", "CREATE POLICY gift_sel ON gift FOR SELECT USING ((SELECT app_has_permission('rewards', 'view')))"),
    ("gift", f"CREATE POLICY gift_ins ON gift FOR INSERT WITH CHECK ((SELECT app_has_permission('rewards', 'edit')) AND {_ADMIN})"),
    ("gift", f"CREATE POLICY gift_upd ON gift FOR UPDATE USING ((SELECT app_has_permission('rewards', 'edit')) AND {_ADMIN})"),
    ("reward_redemption", f"CREATE POLICY reward_redemption_sel ON reward_redemption FOR SELECT USING ((SELECT app_has_permission('rewards', 'view')) AND {_HOLDER})"),
]

# ── functions ────────────────────────────────────────────────────────────────

FUNCTIONS = [
    """CREATE FUNCTION reward_lock(p_holder_type text, p_holder uuid) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT pg_advisory_xact_lock(hashtext('reward:' || p_holder_type || ':' || p_holder::text))
$fn$""",
    """CREATE FUNCTION reward_balance(p_holder_type text, p_holder uuid) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(sum(points), 0)::int FROM reward_ledger
     WHERE holder_type = p_holder_type
       AND CASE p_holder_type WHEN 'partner' THEN partner_id ELSE user_id END = p_holder
$fn$""",
    """CREATE FUNCTION reward_setting_on(p_day date, OUT point_value numeric, OUT max_redeem_pct numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT s.point_value, s.max_redeem_pct FROM reward_setting s
     WHERE s.effective_from <= p_day ORDER BY s.effective_from DESC LIMIT 1
$fn$""",
    """CREATE FUNCTION reward_event(p_holder_type text, p_partner uuid, p_user uuid, p_ref uuid, p_kind text, p_payload jsonb)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT scheme_event(CASE p_holder_type WHEN 'partner' THEN 'channel_partner' ELSE 'app_user' END,
                        CASE p_holder_type WHEN 'partner' THEN p_ref ELSE p_user END,
                        p_partner, NULL, p_kind, p_payload)
$fn$""",
    # the one writer of a hold (plan review B2): lock, check, write
    """CREATE FUNCTION reward_spend(p_kind text, p_holder_type text, p_holder uuid, p_points int,
                                p_order uuid, p_gift uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_partner uuid := app_current_partner();
        o sales_order%ROWTYPE; g gift%ROWTYPE; s record; v_id uuid; v_reason text;
BEGIN
    IF NOT app_has_permission('rewards', 'create') THEN
        RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
    END IF;
    -- a partner user spends its own partner's points; staff spend their own
    IF (p_holder_type = 'partner' AND (v_partner IS NULL OR v_partner <> p_holder))
       OR (p_holder_type = 'user' AND (v_partner IS NOT NULL OR p_holder <> v_me)) THEN
        RAISE EXCEPTION 'not your points' USING ERRCODE = '42501';
    END IF;
    IF p_points IS NULL OR p_points <= 0 THEN
        RAISE EXCEPTION 'points must be positive' USING ERRCODE = 'RWDVL';
    END IF;
    PERFORM reward_lock(p_holder_type, p_holder);
    IF p_kind = 'order' THEN
        IF NOT order_visible(p_order) THEN
            RAISE EXCEPTION 'order not found' USING ERRCODE = 'ORDNF';
        END IF;
        SELECT * INTO o FROM sales_order WHERE id = p_order FOR UPDATE;
        IF o.status <> 'draft' THEN
            RAISE EXCEPTION 'the order is %', o.status USING ERRCODE = 'ORDNS';
        END IF;
        IF o.partner_id IS DISTINCT FROM p_holder OR o.order_type NOT IN ('commercial', 'industrial') THEN
            RAISE EXCEPTION 'points pay only on the partner''s own commercial order' USING ERRCODE = 'RWDOR';
        END IF;
        SELECT * INTO s FROM reward_setting_on((now() AT TIME ZONE 'Asia/Kolkata')::date);
        IF p_points * s.point_value > round(o.total * s.max_redeem_pct / 100, 2) THEN
            RAISE EXCEPTION 'more than % percent of the order', s.max_redeem_pct USING ERRCODE = 'RWDMX';
        END IF;
        IF EXISTS (SELECT 1 FROM reward_redemption WHERE sales_order_id = p_order AND kind = 'order'
                     AND status IN ('pending', 'applied')) THEN
            RAISE EXCEPTION 'points are already on this order' USING ERRCODE = 'RWDEX';
        END IF;
        v_reason := 'Held for order ' || coalesce(o.order_no, 'draft');
    ELSE
        SELECT * INTO g FROM gift WHERE id = p_gift;
        IF g.id IS NULL OR NOT g.is_active THEN
            RAISE EXCEPTION 'no such gift' USING ERRCODE = 'RWDGF';
        END IF;
        p_points := g.points_cost;
        v_reason := 'Held for gift: ' || g.name;
    END IF;
    IF reward_balance(p_holder_type, p_holder) < p_points THEN
        RAISE EXCEPTION 'not enough points' USING ERRCODE = 'RWDIN';
    END IF;
    INSERT INTO reward_redemption (kind, holder_type, partner_id, user_id, sales_order_id, gift_id, points, created_by)
    VALUES (p_kind, p_holder_type, CASE WHEN p_holder_type = 'partner' THEN p_holder END,
            CASE WHEN p_holder_type = 'user' THEN p_holder END,
            CASE WHEN p_kind = 'order' THEN p_order END, CASE WHEN p_kind = 'gift' THEN p_gift END,
            p_points, v_me)
    RETURNING id INTO v_id;
    INSERT INTO reward_ledger (holder_type, partner_id, user_id, points, kind, reason, redemption_id, created_by)
    VALUES (p_holder_type, CASE WHEN p_holder_type = 'partner' THEN p_holder END,
            CASE WHEN p_holder_type = 'user' THEN p_holder END, -p_points, 'redeemed', v_reason, v_id, v_me);
    PERFORM reward_event(p_holder_type, CASE WHEN p_holder_type = 'partner' THEN p_holder END,
                         CASE WHEN p_holder_type = 'user' THEN p_holder END, v_id,
                         'rewards.redemption_requested', jsonb_build_object('kind', p_kind, 'points', p_points));
    RETURN v_id;
END $fn$""",
    # give back what a redemption still holds; the redemption keeps its history
    """CREATE FUNCTION reward_release(p_redemption uuid, p_points int, p_reason text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE r reward_redemption%ROWTYPE;
BEGIN
    SELECT * INTO r FROM reward_redemption WHERE id = p_redemption;
    IF p_points <= 0 THEN RETURN; END IF;
    INSERT INTO reward_ledger (holder_type, partner_id, user_id, points, kind, reason, redemption_id, created_by)
    VALUES (r.holder_type, r.partner_id, r.user_id, p_points, 'released', p_reason, r.id, app_current_user_id());
END $fn$""",
    # the dealer takes its points off a draft, or a gift request is decided or withdrawn
    """CREATE FUNCTION reward_redemption_close(p_redemption uuid, p_to text, p_remark text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE r reward_redemption%ROWTYPE; v_me uuid := app_current_user_id(); v_status text;
BEGIN
    SELECT * INTO r FROM reward_redemption WHERE id = p_redemption FOR UPDATE;
    IF r.id IS NULL THEN
        RAISE EXCEPTION 'not found' USING ERRCODE = 'RWDNF';
    END IF;
    IF r.status <> 'pending' THEN
        RAISE EXCEPTION 'the request is %', r.status USING ERRCODE = 'RWDCL';
    END IF;
    IF p_to IN ('fulfilled', 'rejected') THEN
        IF r.kind <> 'gift' OR NOT app_has_permission('rewards', 'approve') OR app_current_partner() IS NOT NULL THEN
            RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
        END IF;
        IF r.created_by = v_me THEN
            RAISE EXCEPTION 'self_approval' USING ERRCODE = '42501';
        END IF;
        IF p_to = 'rejected' AND (p_remark IS NULL OR btrim(p_remark) = '') THEN
            RAISE EXCEPTION 'a remark is required' USING ERRCODE = 'APRRM';
        END IF;
    ELSIF p_to IN ('withdrawn', 'released') THEN
        -- the holder's own: its partner's user or the staff member
        IF NOT ((r.holder_type = 'partner' AND app_current_partner() = r.partner_id)
                OR (r.holder_type = 'user' AND r.user_id = v_me)) THEN
            RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
        END IF;
        IF (p_to = 'withdrawn') <> (r.kind = 'gift') THEN
            RAISE EXCEPTION 'wrong action for this request' USING ERRCODE = 'RWDCL';
        END IF;
    ELSE
        RAISE EXCEPTION 'unknown action' USING ERRCODE = 'RWDVL';
    END IF;
    PERFORM reward_lock(r.holder_type, coalesce(r.partner_id, r.user_id));
    UPDATE reward_redemption SET status = p_to, remark = nullif(btrim(p_remark), ''),
           decided_by = v_me, decided_at = now() WHERE id = r.id;
    IF p_to <> 'fulfilled' THEN
        PERFORM reward_release(r.id, r.points, initcap(p_to) || ': ' || coalesce(nullif(btrim(p_remark), ''), 'points returned'));
    END IF;
    PERFORM reward_event(r.holder_type, r.partner_id, r.user_id, r.id, 'rewards.redemption_' || p_to,
                         jsonb_build_object('kind', r.kind, 'points', r.points));
END $fn$""",
    # admin corrections; may take a balance below zero
    """CREATE FUNCTION reward_adjust(p_holder_type text, p_holder uuid, p_points int, p_reason text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_id uuid;
BEGIN
    IF NOT app_has_permission('rewards', 'edit') OR app_current_partner() IS NOT NULL THEN
        RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
    END IF;
    IF p_points = 0 OR p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'points and a reason are required' USING ERRCODE = 'RWDVL';
    END IF;
    PERFORM reward_lock(p_holder_type, p_holder);
    INSERT INTO reward_ledger (holder_type, partner_id, user_id, points, kind, reason, created_by)
    VALUES (p_holder_type, CASE WHEN p_holder_type = 'partner' THEN p_holder END,
            CASE WHEN p_holder_type = 'user' THEN p_holder END, p_points, 'adjusted', btrim(p_reason),
            app_current_user_id())
    RETURNING id INTO v_id;
    PERFORM reward_event(p_holder_type, CASE WHEN p_holder_type = 'partner' THEN p_holder END,
                         CASE WHEN p_holder_type = 'user' THEN p_holder END, v_id, 'rewards.adjusted',
                         jsonb_build_object('points', p_points));
    RETURN v_id;
END $fn$""",
    # rule earnings on a delivered order, for the partner and for a staff owner (rules 1 to 3)
    """CREATE FUNCTION reward_earn_order(p_order uuid, p_on date) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE o sales_order%ROWTYPE; r reward_rule%ROWTYPE; v_value numeric; v_points int; v_id uuid;
        v_staff boolean;
BEGIN
    SELECT * INTO o FROM sales_order WHERE id = p_order;
    SELECT b.value INTO v_value FROM scheme_line_basis(NULL::uuid, p_order, true) b;
    IF coalesce(v_value, 0) <= 0 THEN RETURN; END IF;
    v_staff := o.owner_user_id IS NOT NULL
               AND EXISTS (SELECT 1 FROM app_user WHERE id = o.owner_user_id AND partner_id IS NULL);
    FOR r IN SELECT * FROM reward_rule x WHERE x.basis = 'order_value' AND x.is_active
               AND x.valid_from <= p_on AND (x.valid_to IS NULL OR x.valid_to >= p_on) LOOP
        CONTINUE WHEN (r.holder = 'partner' AND o.partner_id IS NULL) OR (r.holder = 'staff' AND NOT v_staff);
        v_points := (floor(v_value / r.per_amount) * r.points)::int;
        CONTINUE WHEN v_points <= 0;
        v_id := NULL;
        INSERT INTO reward_ledger (holder_type, partner_id, user_id, points, kind, reason, rule_id,
                                   source_order_id, expires_at, created_by)
        VALUES (CASE r.holder WHEN 'partner' THEN 'partner' ELSE 'user' END,
                CASE r.holder WHEN 'partner' THEN o.partner_id END,
                CASE r.holder WHEN 'staff' THEN o.owner_user_id END,
                v_points, 'earned', r.name || ' on order ' || o.order_no, r.id, o.id,
                CASE WHEN r.expiry_days IS NOT NULL THEN now() + make_interval(days => r.expiry_days) END,
                app_current_user_id())
        ON CONFLICT (rule_id, source_order_id, holder_type) WHERE kind = 'earned' AND reversed_at IS NULL
            AND rule_id IS NOT NULL AND source_order_id IS NOT NULL DO NOTHING
        RETURNING id INTO v_id;
        IF v_id IS NOT NULL THEN
            PERFORM reward_event(CASE r.holder WHEN 'partner' THEN 'partner' ELSE 'user' END, o.partner_id,
                                 CASE r.holder WHEN 'staff' THEN o.owner_user_id END, v_id,
                                 'rewards.points_earned',
                                 jsonb_build_object('order_no', o.order_no, 'points', v_points));
        END IF;
    END LOOP;
END $fn$""",
    # a won lead earns for its staff owner; a lead leaving won gives the points back (rule 4)
    """CREATE FUNCTION reward_on_lead_stage() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE r reward_rule%ROWTYPE; v_on date := (now() AT TIME ZONE 'Asia/Kolkata')::date; v_id uuid; x record;
        v_left int;
BEGIN
    IF NEW.stage = 'won' AND OLD.stage IS DISTINCT FROM 'won' THEN
        IF NEW.owner_user_id IS NULL
           OR NOT EXISTS (SELECT 1 FROM app_user WHERE id = NEW.owner_user_id AND partner_id IS NULL) THEN
            RETURN NULL;
        END IF;
        FOR r IN SELECT * FROM reward_rule y WHERE y.basis = 'lead_won' AND y.is_active
                   AND y.valid_from <= v_on AND (y.valid_to IS NULL OR y.valid_to >= v_on) LOOP
            v_id := NULL;
            INSERT INTO reward_ledger (holder_type, user_id, points, kind, reason, rule_id, lead_id, expires_at, created_by)
            VALUES ('user', NEW.owner_user_id, r.points, 'earned', r.name || ': lead ' || NEW.inquiry_no,
                    r.id, NEW.id,
                    CASE WHEN r.expiry_days IS NOT NULL THEN now() + make_interval(days => r.expiry_days) END,
                    app_current_user_id())
            ON CONFLICT (rule_id, lead_id) WHERE kind = 'earned' AND reversed_at IS NULL
                AND rule_id IS NOT NULL AND lead_id IS NOT NULL DO NOTHING
            RETURNING id INTO v_id;
            IF v_id IS NOT NULL THEN
                PERFORM reward_event('user', NULL, NEW.owner_user_id, v_id, 'rewards.points_earned',
                                     jsonb_build_object('inquiry_no', NEW.inquiry_no, 'points', r.points));
            END IF;
        END LOOP;
    ELSIF OLD.stage = 'won' AND NEW.stage IS DISTINCT FROM 'won' THEN
        FOR x IN UPDATE reward_ledger SET reversed_at = now()
                  WHERE lead_id = NEW.id AND kind = 'earned' AND reversed_at IS NULL RETURNING * LOOP
            -- what already expired from this lot is gone; take back only the rest (code review F-2)
            v_left := x.points + coalesce((SELECT sum(points) FROM reward_ledger WHERE expires_id = x.id), 0);
            CONTINUE WHEN v_left <= 0;
            INSERT INTO reward_ledger (holder_type, user_id, points, kind, reason, rule_id, lead_id, reverses_id, created_by)
            VALUES ('user', x.user_id, -v_left, 'reversed', 'Lead ' || NEW.inquiry_no || ' is no longer won',
                    x.rule_id, NEW.id, x.id, app_current_user_id());
        END LOOP;
    END IF;
    RETURN NULL;
END $fn$""",
    # rule 6 and plan review S1: per holder, lots in expiry order, no per-row remainder
    """CREATE FUNCTION reward_points_expire() RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE h record; lot record; v_spent numeric; v_expired numeric; v_cum numeric; v_take int; v_n int := 0;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'the expiry run is the worker''s' USING ERRCODE = '42501';
    END IF;
    FOR h IN SELECT DISTINCT holder_type, coalesce(partner_id, user_id) AS holder FROM reward_ledger
              WHERE kind = 'earned' AND reversed_at IS NULL AND expires_at <= now()
                AND NOT EXISTS (SELECT 1 FROM reward_ledger e WHERE e.expires_id = reward_ledger.id) LOOP
        PERFORM reward_lock(h.holder_type, h.holder);
        SELECT coalesce(-sum(points) FILTER (WHERE kind IN ('redeemed', 'released', 'adjusted')), 0),
               coalesce(-sum(points) FILTER (WHERE kind = 'expired'), 0)
          INTO v_spent, v_expired
          FROM reward_ledger WHERE holder_type = h.holder_type AND coalesce(partner_id, user_id) = h.holder;
        v_cum := 0;
        FOR lot IN SELECT * FROM reward_ledger WHERE holder_type = h.holder_type
                     AND coalesce(partner_id, user_id) = h.holder AND kind = 'earned' AND reversed_at IS NULL
                   ORDER BY expires_at NULLS LAST, created_at, id LOOP
            v_cum := v_cum + lot.points;
            CONTINUE WHEN lot.expires_at IS NULL OR lot.expires_at > now()
                       OR EXISTS (SELECT 1 FROM reward_ledger e WHERE e.expires_id = lot.id);
            v_take := greatest(0, least(lot.points, v_cum - v_spent - v_expired))::int;
            CONTINUE WHEN v_take <= 0;
            INSERT INTO reward_ledger (holder_type, partner_id, user_id, points, kind, reason, expires_id)
            VALUES (lot.holder_type, lot.partner_id, lot.user_id, -v_take, 'expired',
                    'Expired: ' || lot.reason, lot.id);
            v_expired := v_expired + v_take;
            v_n := v_n + 1;
        END LOOP;
    END LOOP;
    RETURN v_n;
END $fn$""",
    """CREATE FUNCTION reward_rule_used(p_rule uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM reward_ledger WHERE rule_id = p_rule)
$fn$""",
    """CREATE FUNCTION refuse_used_reward_rule_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT reward_rule_used(OLD.id) THEN RETURN NEW; END IF;
    IF (to_jsonb(NEW) - ARRAY['valid_to', 'is_active', 'updated_at', 'updated_by'])
       IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['valid_to', 'is_active', 'updated_at', 'updated_by']) THEN
        RAISE EXCEPTION 'the rule has awarded points; end it and create a new one' USING ERRCODE = 'RWDIU';
    END IF;
    RETURN NEW;
END $fn$""",
]

# The order trigger's three new arms, pasted into 033's text by exact anchors.
_SUBMIT_ANCHOR = """                PERFORM scheme_event('channel_partner', e.id, NEW.partner_id, NULL, 'partner.entitlement_consumed', v_ref);
            END LOOP;
        END IF;
"""
_SUBMIT_ADD = """        -- FS-032: points the dealer put on the draft, after the scheme benefits (plan review B1)
        FOR r IN SELECT * FROM reward_redemption x WHERE x.sales_order_id = NEW.id AND x.kind = 'order'
                   AND x.status = 'pending' FOR UPDATE LOOP
            SELECT * INTO v_set FROM reward_setting_on(NEW.tax_date);
            -- the draft may have changed since the hold: another dealer gets nothing (code review F-1)
            IF r.partner_id IS DISTINCT FROM NEW.partner_id THEN
                UPDATE reward_redemption SET status = 'released', decided_at = now() WHERE id = r.id;
                PERFORM reward_release(r.id, r.points, 'The order is no longer this dealer''s');
                CONTINUE;
            END IF;
            -- and smaller lines still keep points within the limit of the total
            v_amt := least(round(r.points * v_set.point_value, 2), v_left,
                           round(NEW.total * v_set.max_redeem_pct / 100, 2));
            -- whole points only: a point is never spent for less than its value (GAP-316)
            v_used := CASE WHEN v_amt <= 0 THEN 0 ELSE floor(v_amt / v_set.point_value)::int END;
            v_amt := round(v_used * v_set.point_value, 2);
            IF v_used > 0 THEN
                INSERT INTO scheme_benefit (sales_order_id, redemption_id, kind, basis, amount)
                VALUES (NEW.id, r.id, 'reward_redemption', v_used, v_amt);
                v_left := v_left - v_amt;
                UPDATE reward_redemption SET status = 'applied', amount = v_amt, points = v_used WHERE id = r.id;
                IF r.points > v_used THEN
                    PERFORM reward_release(r.id, r.points - v_used, 'Not needed on order ' || NEW.order_no);
                END IF;
            ELSE
                -- the scheme benefits already cover the order: every point goes back
                UPDATE reward_redemption SET status = 'released', decided_at = now() WHERE id = r.id;
                PERFORM reward_release(r.id, r.points, 'Nothing left to pay on order ' || NEW.order_no);
            END IF;
        END LOOP;
"""
_REVERSE_ANCHOR = """            IF r.entitlement_id IS NOT NULL THEN"""
_REVERSE_NEW = """            IF r.kind = 'reward_redemption' THEN
                -- back to the draft: the hold stays; cancelled: below, with any pending one
                UPDATE reward_redemption SET status = 'pending', amount = NULL
                 WHERE id = r.redemption_id AND status = 'applied';
            ELSIF r.entitlement_id IS NOT NULL THEN"""
_REVERSE_TAIL_ANCHOR = """                                     v_ref || jsonb_build_object('scheme_code', (SELECT code FROM scheme WHERE id = r.scheme_id)));
            END IF;
        END LOOP;
"""
_REVERSE_TAIL_ADD = """        IF NEW.status = 'cancelled' THEN
            FOR r IN UPDATE reward_redemption SET status = 'released', decided_at = now()
                      WHERE sales_order_id = NEW.id AND kind = 'order' AND status IN ('pending', 'applied')
                      RETURNING * LOOP
                PERFORM reward_release(r.id, r.points, 'Order ' || coalesce(NEW.order_no, 'draft') || ' cancelled');
            END LOOP;
        END IF;
"""
_DELIVERY_OLD = """        IF NEW.partner_id IS NULL THEN RETURN NULL; END IF;
        SELECT (max(dispatched_at) AT TIME ZONE 'Asia/Kolkata')::date INTO v_on
          FROM dispatch WHERE sales_order_id = NEW.id AND voided_at IS NULL;
        IF v_on IS NULL THEN RETURN NULL; END IF;        -- closed short with nothing sent
"""
_DELIVERY_NEW = """        SELECT (max(dispatched_at) AT TIME ZONE 'Asia/Kolkata')::date INTO v_on
          FROM dispatch WHERE sales_order_id = NEW.id AND voided_at IS NULL;
        IF v_on IS NULL THEN RETURN NULL; END IF;        -- closed short with nothing sent
        -- FS-032: rule points, for the partner and for a staff owner, before the partner check
        PERFORM reward_earn_order(NEW.id, v_on);
        IF NEW.partner_id IS NULL THEN RETURN NULL; END IF;
"""
_VOID_OLD = """                  WHERE source_order_id = NEW.id AND kind = 'earned' AND reversed_at IS NULL AND scheme_id IS NOT NULL"""
_VOID_NEW = """                  WHERE source_order_id = NEW.id AND kind = 'earned' AND reversed_at IS NULL
                    AND (scheme_id IS NOT NULL OR rule_id IS NOT NULL)"""
_VOID_INSERT_OLD = """            INSERT INTO reward_ledger (holder_type, partner_id, user_id, points, kind, reason, scheme_id, source_order_id,
                                       reverses_id, created_by)
            VALUES (r.holder_type, r.partner_id, r.user_id, -r.points, 'reversed',
                    'Dispatch voided on order ' || NEW.order_no, r.scheme_id, NEW.id, r.id, app_current_user_id());"""
_VOID_INSERT_NEW = """            -- what already expired from this lot is gone; take back only the rest (code review F-2)
            v_n := r.points + coalesce((SELECT sum(points) FROM reward_ledger WHERE expires_id = r.id), 0);
            CONTINUE WHEN v_n <= 0;
            INSERT INTO reward_ledger (holder_type, partner_id, user_id, points, kind, reason, scheme_id, rule_id,
                                       source_order_id, reverses_id, created_by)
            VALUES (r.holder_type, r.partner_id, r.user_id, -v_n, 'reversed',
                    'Dispatch voided on order ' || NEW.order_no, r.scheme_id, r.rule_id, NEW.id, r.id,
                    app_current_user_id());"""
_VOID_EVENT_OLD = """            PERFORM scheme_event('channel_partner', r.id, NEW.partner_id, NULL, 'partner.points_reversed',
                                 v_ref || jsonb_build_object('points', r.points));"""
_VOID_EVENT_NEW = """            PERFORM reward_event(r.holder_type, r.partner_id, r.user_id, r.id, 'rewards.points_reversed',
                                 v_ref || jsonb_build_object('points', v_n));"""
_DECLARE_OLD = """DECLARE r record; e scheme_entitlement%ROWTYPE; v_left numeric; v_amt numeric; v_on date;
        v_ref jsonb; v_id uuid; v_n int; v_st text;"""
_DECLARE_NEW = """DECLARE r record; e scheme_entitlement%ROWTYPE; v_left numeric; v_amt numeric; v_on date;
        v_ref jsonb; v_id uuid; v_n int; v_st text; v_set record; v_used int;"""


def _order_trigger(m033: ModuleType) -> str:
    text = next(t for t in m033.FUNCTIONS if re.search(r"FUNCTION\s+scheme_on_order_status\(", t))
    text = text.replace("CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1)
    text = _replace(text, _DECLARE_OLD, _DECLARE_NEW)
    text = _replace(text, _SUBMIT_ANCHOR, _SUBMIT_ANCHOR + _SUBMIT_ADD)
    text = _replace(text, _REVERSE_ANCHOR, _REVERSE_NEW)
    text = _replace(text, _REVERSE_TAIL_ANCHOR, _REVERSE_TAIL_ANCHOR + _REVERSE_TAIL_ADD)
    text = _replace(text, _DELIVERY_OLD, _DELIVERY_NEW)
    text = _replace(text, _VOID_OLD, _VOID_NEW)
    text = _replace(text, _VOID_INSERT_OLD, _VOID_INSERT_NEW)
    return _replace(text, _VOID_EVENT_OLD, _VOID_EVENT_NEW)


TRIGGERS = [
    "CREATE TRIGGER trg_reward_rule_updated_at BEFORE UPDATE ON reward_rule FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_reward_rule_audit AFTER INSERT OR UPDATE OR DELETE ON reward_rule FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_reward_rule_refuse_used BEFORE UPDATE ON reward_rule FOR EACH ROW EXECUTE FUNCTION refuse_used_reward_rule_edit()",
    "CREATE TRIGGER trg_reward_setting_audit AFTER INSERT OR UPDATE OR DELETE ON reward_setting FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_gift_updated_at BEFORE UPDATE ON gift FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_gift_audit AFTER INSERT OR UPDATE OR DELETE ON gift FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_reward_redemption_audit AFTER INSERT OR UPDATE OR DELETE ON reward_redemption FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_lead_zz_rewards AFTER UPDATE OF stage ON lead FOR EACH ROW WHEN (OLD.stage IS DISTINCT FROM NEW.stage) EXECUTE FUNCTION reward_on_lead_stage()",
]

GRANTED = [
    "reward_setting_on(date)",
    "reward_spend(text, text, uuid, integer, uuid, uuid)",
    "reward_redemption_close(uuid, text, text)",
    "reward_adjust(text, uuid, integer, text)",
    "reward_points_expire()",
    "reward_rule_used(uuid)",
]
INTERNAL = [
    # used only inside the definers; balances are read under the caller's policies (code review F-5)
    "reward_balance(text, uuid)",
    "reward_lock(text, uuid)",
    "reward_event(text, uuid, uuid, uuid, text, jsonb)",
    "reward_release(uuid, integer, text)",
    "reward_earn_order(uuid, date)",
    "reward_on_lead_stage()",
    "refuse_used_reward_rule_edit()",
]


def upgrade() -> None:
    m033 = _load("033")
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute(_order_trigger(m033))
    for _table, stmt in HAND_POLICIES:
        op.execute(stmt)
    for stmt in TRIGGERS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    # a re-created function is PUBLIC-executable again (028's lesson)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    m033 = _load("033")
    op.execute("DROP TRIGGER IF EXISTS trg_lead_zz_rewards ON lead")
    original = next(t for t in m033.FUNCTIONS if re.search(r"FUNCTION\s+scheme_on_order_status\(", t))
    op.execute(original.replace("CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1))
    op.execute("DELETE FROM activity_event WHERE kind LIKE 'rewards.%'")
    op.execute("DELETE FROM scheme_benefit WHERE kind = 'reward_redemption'")
    op.execute("ALTER TABLE scheme_benefit DROP CONSTRAINT ck_scheme_benefit_redemption")
    op.execute("ALTER TABLE scheme_benefit DROP COLUMN redemption_id")
    op.execute("ALTER TABLE scheme_benefit ALTER COLUMN scheme_id SET NOT NULL")
    op.execute("ALTER TABLE scheme_benefit DROP CONSTRAINT scheme_benefit_kind_check")
    op.execute("ALTER TABLE scheme_benefit ADD CONSTRAINT scheme_benefit_kind_check CHECK (kind IN ('discount', 'entitlement_used'))")
    op.execute("DELETE FROM reward_ledger WHERE scheme_id IS NULL")
    # these two index 033's columns, so dropping 036's columns does not take them
    op.execute("DROP INDEX IF EXISTS ix_reward_ledger_lots")
    op.execute("DROP INDEX IF EXISTS ix_reward_ledger_source_order")
    for col in ("expires_id", "redemption_id", "lead_id", "rule_id"):
        op.execute(f"ALTER TABLE reward_ledger DROP COLUMN {col}")
    for table in ("reward_redemption", "gift", "reward_setting", "reward_rule"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
