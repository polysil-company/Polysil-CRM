"""031: payments: receipts, allocations to orders, instalments (FS-022, ADR-045).

- **Writes go through definers** (review B-1). Accounts holds no `sales_orders.edit`,
  and under RLS a `FOR UPDATE` it may not perform matches zero rows, so a direct
  write could not lock the orders it pays. `payment_record`, `payment_allocate`,
  `payment_void` and `order_payment_schedule_set` check the `payments` permission
  and `order_visible()`, lock the orders by id and then the receipt, and raise
  SQLSTATEs the service maps. `app_role` holds SELECT only on the three tables.
- **Balances are derived.** `order_payment_position(order)` returns payable,
  received and what the instalments say is due by a date; the domain turns those
  into a status. Null when the caller may not see payments or the order.
- **RLS without a cycle.** PostgreSQL refuses policies that reference each other,
  so `payment_allocation` carries the receipt's dealer and the arrows run one way:
  payment → allocation → order or dealer.
- **No amount in any event payload** (FS-005 rule 17, review B-2). A receipt
  writes `payment.received` on its dealer (review B-3) and `payment.allocated` on
  each order it pays.
- A dealer cannot change under an order that has live allocations.

Revision ID: 031_payments
Revises: 030_field_tracking
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "031_payments"
down_revision: str | None = "030_field_tracking"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

ENUMS = ["CREATE TYPE payment_mode AS ENUM ('neft', 'upi', 'cheque', 'cash', 'adjustment')"]

_MONEY = "numeric(14,2) NOT NULL CHECK ({c} > 0)"

TABLES = [
    f"""CREATE TABLE payment (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id uuid REFERENCES channel_partner(id),
    mode payment_mode NOT NULL,
    ref_no text CHECK (ref_no IS NULL OR length(btrim(ref_no)) BETWEEN 1 AND 100),
    received_on date NOT NULL,
    amount {_MONEY.format(c='amount')},
    is_short_payment boolean NOT NULL DEFAULT false,
    remark text CHECK (remark IS NULL OR length(remark) <= 2000),
    entered_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    voided_at timestamptz,
    voided_by uuid REFERENCES app_user(id),
    void_reason text CHECK (void_reason IS NULL OR length(void_reason) BETWEEN 1 AND 2000),
    CONSTRAINT ck_payment_ref CHECK (mode IN ('cash', 'adjustment') OR ref_no IS NOT NULL),
    CONSTRAINT ck_payment_voided CHECK ((voided_at IS NULL) = (voided_by IS NULL) AND (voided_at IS NULL) = (void_reason IS NULL))
)""",
    f"""CREATE TABLE payment_allocation (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id uuid NOT NULL REFERENCES payment(id),
    sales_order_id uuid NOT NULL REFERENCES sales_order(id),
    partner_id uuid REFERENCES channel_partner(id),
    amount {_MONEY.format(c='amount')},
    voided boolean NOT NULL DEFAULT false,
    created_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now()
)""",
    f"""CREATE TABLE payment_schedule (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sales_order_id uuid NOT NULL REFERENCES sales_order(id),
    seq smallint NOT NULL CHECK (seq BETWEEN 1 AND 5),
    due_on date NOT NULL,
    amount {_MONEY.format(c='amount')},
    note text CHECK (note IS NULL OR length(note) <= 200),
    created_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_payment_schedule_seq UNIQUE (sales_order_id, seq)
)""",
]

INDEXES = [
    "CREATE INDEX ix_payment_partner ON payment (partner_id, received_on)",
    "CREATE INDEX ix_payment_entered_by ON payment (entered_by)",
    "CREATE INDEX ix_payment_voided_by ON payment (voided_by)",
    # GAP-207: one live reference per dealer and mode; NULLS NOT DISTINCT so a no-dealer receipt counts too
    "CREATE UNIQUE INDEX uq_payment_live_ref ON payment (partner_id, mode, ref_no) NULLS NOT DISTINCT "
    "WHERE voided_at IS NULL AND ref_no IS NOT NULL",
    "CREATE INDEX ix_payment_allocation_payment ON payment_allocation (payment_id) WHERE NOT voided",
    "CREATE INDEX ix_payment_allocation_order ON payment_allocation (sales_order_id) WHERE NOT voided",
    "CREATE INDEX ix_payment_allocation_payment_all ON payment_allocation (payment_id)",
    "CREATE INDEX ix_payment_allocation_order_all ON payment_allocation (sales_order_id)",
    "CREATE INDEX ix_payment_allocation_partner ON payment_allocation (partner_id)",
    "CREATE INDEX ix_payment_allocation_created_by ON payment_allocation (created_by)",
    "CREATE INDEX ix_payment_schedule_created_by ON payment_schedule (created_by)",
]

RLS_TABLES = ("payment", "payment_allocation", "payment_schedule")

# tests/db/migration_grants.py reads these two, as it does every migration's
GRANTS: dict[str, str] = {"payment": "SELECT", "payment_allocation": "SELECT", "payment_schedule": "SELECT"}

_VIEW = "(SELECT app_has_permission('payments', 'view'))"
_SCOPE = "(SELECT app_scope('payments'))"
_SUBTREE = "(SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))"

HAND_POLICIES: list[tuple[str, str]] = [
    # a receipt: company-wide; a dealer's own subtree; a staff reader of its dealer
    # (review B-5); or, with no dealer, through an order it pays
    ("payment", f"""CREATE POLICY payment_sel ON payment FOR SELECT USING (
  {_SCOPE} = 'global'
  OR ({_SCOPE} = 'partner_subtree' AND partner_id IN {_SUBTREE})
  OR ({_SCOPE} = 'org_subtree' AND (
        EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id)
        OR EXISTS (SELECT 1 FROM payment_allocation a WHERE a.payment_id = payment.id)))
)"""),
    ("payment", f"CREATE POLICY payment_res_perm ON payment AS RESTRICTIVE FOR SELECT USING (\n  {_VIEW}\n)"),
    ("payment_allocation", f"""CREATE POLICY payment_allocation_sel ON payment_allocation FOR SELECT USING (
  {_SCOPE} = 'global'
  OR ({_SCOPE} = 'partner_subtree' AND partner_id IN {_SUBTREE})
  OR ({_SCOPE} = 'org_subtree' AND (
        EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id)
        OR EXISTS (SELECT 1 FROM sales_order o WHERE o.id = sales_order_id)))
)"""),
    ("payment_allocation", f"CREATE POLICY payment_allocation_res_perm ON payment_allocation AS RESTRICTIVE FOR SELECT USING (\n  {_VIEW}\n)"),
    ("payment_schedule", "CREATE POLICY payment_schedule_sel ON payment_schedule FOR SELECT USING (\n  EXISTS (SELECT 1 FROM sales_order o WHERE o.id = sales_order_id)\n)"),
    ("payment_schedule", f"CREATE POLICY payment_schedule_res_perm ON payment_schedule AS RESTRICTIVE FOR SELECT USING (\n  {_VIEW}\n)"),
]

# the statuses an order may be paid in (rule 3)
_PAYABLE = "('submitted', 'approved', 'partially_dispatched', 'dispatched', 'closed_short')"
# what the buyer owes: the total less applied scheme and reward benefits (ADR-050,
# FS-031/032; closes GAP-206). `o` is the order row in every function that uses it.
_OWED = ("(o.total - COALESCE((SELECT sum(b.amount) FROM scheme_benefit b "
         "WHERE b.sales_order_id = o.id AND b.status = 'applied'), 0))")

FUNCTIONS = [
    # Accounts reads every receipt but holds no `partners` permission, so a dealer's
    # name reaches it through here: for global payment readers only (API test)
    """CREATE FUNCTION payment_partner_name(p_partner uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT cp.name::text FROM channel_partner cp
     WHERE cp.id = p_partner AND app_has_permission('payments', 'view') AND app_scope('payments') = 'global'
$fn$""",
    # Payable, received, and the instalments due by p_on. Null unless the caller may
    # read payments and the order (review recommendation). Payable is the total less
    # applied benefits, 0 when cancelled (GAP-209).
    f"""CREATE FUNCTION order_payment_position(p_order uuid, p_on date)
RETURNS TABLE (payable numeric, received numeric, due numeric)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT (app_has_permission('payments', 'view') AND order_visible(p_order)) THEN
        RETURN;
    END IF;
    RETURN QUERY
    SELECT CASE WHEN o.status IN {_PAYABLE} THEN {_OWED} ELSE 0::numeric END,
           COALESCE((SELECT sum(a.amount) FROM payment_allocation a
                      WHERE a.sales_order_id = o.id AND NOT a.voided), 0),
           COALESCE((SELECT sum(s.amount) FROM payment_schedule s
                      WHERE s.sales_order_id = o.id AND s.due_on <= p_on), 0)
      FROM sales_order o WHERE o.id = p_order;
END $fn$""",
    # Shared by record and allocate: orders locked by id, every check, then the rows
    # and one event per order. The receipt is locked by the caller.
    f"""CREATE FUNCTION payment_apply(p_payment payment, p_allocs jsonb, p_must_fill boolean) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); r record; o sales_order%ROWTYPE;
    v_left numeric; v_sum numeric := 0;
BEGIN
    IF jsonb_typeof(p_allocs) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'allocations must be a list' USING ERRCODE = '22023';
    END IF;
    v_left := p_payment.amount - COALESCE((SELECT sum(amount) FROM payment_allocation
                                            WHERE payment_id = p_payment.id AND NOT voided), 0);
    FOR r IN SELECT (x ->> 'sales_order_id')::uuid AS order_id, (x ->> 'amount')::numeric AS amount
               FROM jsonb_array_elements(p_allocs) x ORDER BY 1 LOOP
        IF r.amount IS NULL OR r.amount <= 0 OR r.amount <> round(r.amount, 2) THEN
            RAISE EXCEPTION 'allocation % must be positive, two places', r.order_id USING ERRCODE = '22023';
        END IF;
        IF NOT order_visible(r.order_id) THEN
            RAISE EXCEPTION 'order % not found', r.order_id USING ERRCODE = 'PAYNF';
        END IF;
        SELECT * INTO o FROM sales_order WHERE id = r.order_id FOR UPDATE;
        IF o.deleted_at IS NOT NULL OR o.status::text NOT IN {_PAYABLE} OR {_OWED} <= 0 THEN
            RAISE EXCEPTION 'order % is not payable', r.order_id USING ERRCODE = 'PAYNP';
        END IF;
        IF o.partner_id IS DISTINCT FROM p_payment.partner_id THEN
            RAISE EXCEPTION 'order % has another dealer', r.order_id USING ERRCODE = 'PAYPM';
        END IF;
        v_sum := v_sum + r.amount;
        INSERT INTO payment_allocation (payment_id, sales_order_id, partner_id, amount, created_by)
        VALUES (p_payment.id, r.order_id, p_payment.partner_id, r.amount, v_me);
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('sales_order', o.id, o.lead_id, 'payment.allocated', v_me,
                jsonb_build_object('payment_id', p_payment.id, 'mode', p_payment.mode));
    END LOOP;
    IF v_sum > v_left THEN
        RAISE EXCEPTION 'allocations % exceed what is left, %', v_sum, v_left USING ERRCODE = 'PAYOA';
    END IF;
    IF p_must_fill AND v_sum <> p_payment.amount THEN
        RAISE EXCEPTION 'a receipt with no dealer is allocated in full' USING ERRCODE = 'PAYMA';
    END IF;
END $fn$""",
    """CREATE FUNCTION payment_record(p jsonb) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); v payment%ROWTYPE; v_amount numeric := (p ->> 'amount')::numeric;
    v_partner uuid := (p ->> 'partner_id')::uuid; v_mode payment_mode := (p ->> 'mode')::payment_mode;
    v_ref text := NULLIF(btrim(COALESCE(p ->> 'ref_no', '')), '');
BEGIN
    IF NOT app_has_permission('payments', 'create') OR app_scope('payments') <> 'global' THEN
        RAISE EXCEPTION 'not permitted to record payments' USING ERRCODE = '42501';
    END IF;
    IF v_amount IS NULL OR v_amount <= 0 OR v_amount <> round(v_amount, 2) THEN
        RAISE EXCEPTION 'amount must be positive, two places' USING ERRCODE = '22023';
    END IF;
    IF v_mode NOT IN ('cash', 'adjustment') AND v_ref IS NULL THEN
        RAISE EXCEPTION 'reference required' USING ERRCODE = 'PAYRF';
    END IF;
    IF v_partner IS NOT NULL AND NOT EXISTS (SELECT 1 FROM channel_partner WHERE id = v_partner AND deleted_at IS NULL) THEN
        RAISE EXCEPTION 'dealer not found' USING ERRCODE = 'PAYNF';
    END IF;
    BEGIN
        INSERT INTO payment (partner_id, mode, ref_no, received_on, amount, is_short_payment, remark, entered_by)
        VALUES (v_partner, v_mode, v_ref, (p ->> 'received_on')::date, v_amount,
                COALESCE((p ->> 'is_short_payment')::boolean, false),
                NULLIF(btrim(COALESCE(p ->> 'remark', '')), ''), v_me)
        RETURNING * INTO v;
    EXCEPTION WHEN unique_violation THEN
        RAISE EXCEPTION 'reference % is already recorded', v_ref USING ERRCODE = 'PAYDR';
    END;
    IF v_partner IS NOT NULL THEN
        INSERT INTO activity_event (entity_type, entity_id, partner_id, kind, actor_id, payload)
        VALUES ('channel_partner', v_partner, v_partner, 'payment.received', v_me,
                jsonb_build_object('payment_id', v.id, 'mode', v.mode));
    END IF;
    PERFORM payment_apply(v, COALESCE(p -> 'allocations', '[]'::jsonb), v_partner IS NULL);
    RETURN v.id;
END $fn$""",
    """CREATE FUNCTION payment_allocate(p_id uuid, p_allocs jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v payment%ROWTYPE;
BEGIN
    IF NOT app_has_permission('payments', 'create') OR app_scope('payments') <> 'global' THEN
        RAISE EXCEPTION 'not permitted to allocate payments' USING ERRCODE = '42501';
    END IF;
    -- orders before the receipt, as payment_record takes them: lock the orders first
    PERFORM 1 FROM sales_order WHERE id IN (SELECT (x ->> 'sales_order_id')::uuid
                                               FROM jsonb_array_elements(p_allocs) x) ORDER BY id FOR UPDATE;
    SELECT * INTO v FROM payment WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'payment not found' USING ERRCODE = 'PAYNF';
    END IF;
    IF v.voided_at IS NOT NULL THEN
        RAISE EXCEPTION 'the payment is void' USING ERRCODE = 'PAYAV';
    END IF;
    PERFORM payment_apply(v, p_allocs, false);
END $fn$""",
    """CREATE FUNCTION payment_void(p_id uuid, p_reason text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v payment%ROWTYPE; v_reason text := NULLIF(btrim(p_reason), ''); r record;
BEGIN
    IF NOT app_has_permission('payments', 'edit') OR app_scope('payments') <> 'global' THEN
        RAISE EXCEPTION 'not permitted to void payments' USING ERRCODE = '42501';
    END IF;
    IF v_reason IS NULL THEN
        RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'PAYRS';
    END IF;
    PERFORM 1 FROM sales_order WHERE id IN (SELECT sales_order_id FROM payment_allocation
                                             WHERE payment_id = p_id AND NOT voided) ORDER BY id FOR UPDATE;
    SELECT * INTO v FROM payment WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'payment not found' USING ERRCODE = 'PAYNF';
    END IF;
    IF v.voided_at IS NOT NULL THEN
        RAISE EXCEPTION 'the payment is already void' USING ERRCODE = 'PAYAV';
    END IF;
    UPDATE payment SET voided_at = now(), voided_by = v_me, void_reason = v_reason WHERE id = p_id;
    FOR r IN UPDATE payment_allocation a SET voided = true WHERE a.payment_id = p_id AND NOT a.voided
             RETURNING a.sales_order_id LOOP
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        SELECT 'sales_order', o.id, o.lead_id, 'payment.voided', v_me, jsonb_build_object('payment_id', p_id)
          FROM sales_order o WHERE o.id = r.sales_order_id;
    END LOOP;
    IF v.partner_id IS NOT NULL THEN
        INSERT INTO activity_event (entity_type, entity_id, partner_id, kind, actor_id, payload)
        VALUES ('channel_partner', v.partner_id, v.partner_id, 'payment.voided', v_me,
                jsonb_build_object('payment_id', p_id));
    END IF;
END $fn$""",
    f"""CREATE FUNCTION order_payment_schedule_set(p_order uuid, p_rows jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); o sales_order%ROWTYPE; v_sum numeric;
BEGIN
    IF NOT app_has_permission('payments', 'edit') OR app_scope('payments') <> 'global' THEN
        RAISE EXCEPTION 'not permitted to set instalments' USING ERRCODE = '42501';
    END IF;
    IF NOT order_visible(p_order) THEN
        RAISE EXCEPTION 'order not found' USING ERRCODE = 'PAYNF';
    END IF;
    SELECT * INTO o FROM sales_order WHERE id = p_order FOR UPDATE;
    IF o.deleted_at IS NOT NULL OR o.status::text NOT IN {_PAYABLE} OR {_OWED} <= 0 THEN
        RAISE EXCEPTION 'order is not payable' USING ERRCODE = 'PAYNP';
    END IF;
    IF jsonb_array_length(p_rows) > 5 THEN
        RAISE EXCEPTION 'up to five instalments' USING ERRCODE = '22023';
    END IF;
    SELECT COALESCE(sum((x ->> 'amount')::numeric), 0) INTO v_sum FROM jsonb_array_elements(p_rows) x;
    IF v_sum > {_OWED} THEN
        RAISE EXCEPTION 'instalments % exceed payable %', v_sum, {_OWED} USING ERRCODE = 'PAYSP';
    END IF;
    DELETE FROM payment_schedule WHERE sales_order_id = p_order;
    INSERT INTO payment_schedule (sales_order_id, seq, due_on, amount, note, created_by)
    SELECT p_order, ord, (x ->> 'due_on')::date, (x ->> 'amount')::numeric, NULLIF(btrim(COALESCE(x ->> 'note', '')), ''), v_me
      FROM jsonb_array_elements(p_rows) WITH ORDINALITY AS t(x, ord);
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('sales_order', p_order, o.lead_id, 'payment.schedule_set', v_me,
            jsonb_build_object('instalments', jsonb_array_length(p_rows)));
END $fn$""",
    # review edge case 7: a paid order's dealer does not change under its receipts
    """CREATE FUNCTION refuse_partner_change_when_paid() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF EXISTS (SELECT 1 FROM payment_allocation WHERE sales_order_id = NEW.id AND NOT voided) THEN
        RAISE EXCEPTION 'the order has payments; its dealer cannot change' USING ERRCODE = 'PAYPC';
    END IF;
    RETURN NEW;
END $fn$""",
    "CREATE TRIGGER trg_sales_order_partner_paid BEFORE UPDATE OF partner_id ON sales_order FOR EACH ROW "
    "WHEN (OLD.partner_id IS DISTINCT FROM NEW.partner_id) EXECUTE FUNCTION refuse_partner_change_when_paid()",
]

GRANTED = ["payment_partner_name(uuid)", "order_payment_position(uuid, date)", "payment_record(jsonb)", "payment_allocate(uuid, jsonb)",
           "payment_void(uuid, text)", "order_payment_schedule_set(uuid, jsonb)"]
INTERNAL = ["payment_apply(payment, jsonb, boolean)", "refuse_partner_change_when_paid()"]


def upgrade() -> None:
    for stmt in ENUMS + TABLES + INDEXES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for t in RLS_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for t in RLS_TABLES:
        op.execute(f"CREATE TRIGGER trg_{t}_audit AFTER INSERT OR UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION audit_row()")
    # created functions are PUBLIC-executable until this runs (006, 028)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    # code review F-8: only global scope writes payments; RBAC.md §6.1 drops the
    # state manager's E, and the seeded row goes with it
    op.execute("DELETE FROM role_permission WHERE module = 'payments' AND action = 'edit' "
               "AND role_id IN (SELECT id FROM role WHERE code = 'state_manager')")


def downgrade() -> None:
    op.execute("INSERT INTO role_permission (role_id, module, action, scope) "
               "SELECT id, 'payments', 'edit', 'org_subtree' FROM role WHERE code = 'state_manager' "
               "ON CONFLICT (role_id, module, action) DO NOTHING")
    op.execute("DROP TRIGGER IF EXISTS trg_sales_order_partner_paid ON sales_order")
    op.execute("DELETE FROM activity_event WHERE kind LIKE 'payment.%'")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    # one statement: payment's read policy depends on payment_allocation
    op.execute("DROP TABLE IF EXISTS payment_schedule, payment_allocation, payment")
    op.execute("DROP TYPE IF EXISTS payment_mode")
