"""038: marketing material ordering (FS-034).

- `marketing_material` and `marketing_material_price`: the catalogue, with price and
  company share effective-dated and never edited (rule 10). Seeded with the client's
  17 items at stand-in prices, flagged provisional (question 4.9).
- `marketing_order`, `marketing_order_line`, `marketing_order_counter`: an order copies
  price and shares onto its lines. Every write is a definer.
- `marketing_order_refusal(order, action)` decides every action for the definer, for
  `can` and for `awaiting=me`, so the three never drift (the complaint pattern).
- `activity_event_sel` gains the `marketing_order` arm from `api/authz/activity.py`.

Revision ID: 038_marketing_material
Revises: 037_dealer_commission
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "038_marketing_material"
down_revision: str | None = "037_dealer_commission"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id)"""

# The client's "Marketing & Promotional Activities" sheet, in its order. Prices are
# stand-ins of a believable size (GAP-325); every one is provisional until the admin sets it.
CATALOGUE = [
    ("MM-CANOPY-CAMP", "Canopy campaign", "Event", "15000.00"),
    ("MM-BIKE-CAMP", "Bike campaign", "Event", "12000.00"),
    ("MM-FARMER-MEET", "Farmer meeting", "Event", "8000.00"),
    ("MM-CAP", "POLYSIL CAP", "Nos", "120.00"),
    ("MM-UMBRELLA", "POLYSIL UMBRELLA", "Nos", "450.00"),
    ("MM-PEN", "POLYSIL PEN", "Nos", "15.00"),
    ("MM-KEYCHAIN", "POLYSIL KEYCHAIN", "Nos", "35.00"),
    ("MM-BAG", "POLYSIL BAG", "Nos", "260.00"),
    ("MM-NW-BAG", "POLYSIL NON WOVEN BAG", "Nos", "40.00"),
    ("MM-CANOPY", "POLYSIL CANOPY", "Nos", "6500.00"),
    ("MM-MEET-BANNER", "POLYSIL FARMER MEET BANNER", "Nos", "900.00"),
    ("MM-OFFICE-BANNER", "POLYSIL DEALER OFFICE BANNER", "Nos", "1500.00"),
    ("MM-DEALER-KIT", "POLYSIL DEALER KIT", "Nos", "2500.00"),
    ("MM-PROFILE", "POLYSIL COMPANY PROFILE LITERATURE", "Nos", "45.00"),
    ("MM-BROCHURE", "POLYSIL PRODUCT BROCHURE LITERATURE", "Nos", "20.00"),
    ("MM-DIARY-S", "POLYSIL DIARY SMALL", "Nos", "180.00"),
    ("MM-DIARY-B", "POLYSIL DIARY BIG", "Nos", "320.00"),
]

TABLES = [
    f"""CREATE TABLE marketing_material (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE CHECK (code ~ '^[A-Za-z0-9_-]{{2,40}}$'),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    description text CHECK (description IS NULL OR length(description) <= 2000),
    unit text NOT NULL DEFAULT 'Nos' CHECK (length(btrim(unit)) BETWEEN 1 AND 20),
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT}
)""",
    """CREATE TABLE marketing_material_price (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    material_id uuid NOT NULL REFERENCES marketing_material(id),
    price numeric(14,2) NOT NULL CHECK (price >= 0),
    company_share_pct numeric(6,3) NOT NULL CHECK (company_share_pct BETWEEN 0 AND 100),
    is_provisional boolean NOT NULL DEFAULT false,
    effective_from date NOT NULL,
    effective_to date,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES app_user(id),
    CONSTRAINT ck_marketing_price_dates CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_marketing_price_overlap EXCLUDE USING gist (
        material_id WITH =, daterange(effective_from, effective_to, '[)') WITH &&)
)""",
    "CREATE INDEX ix_marketing_price_material ON marketing_material_price (material_id, effective_from DESC)",
    """CREATE TABLE marketing_order_counter (
    state_code text NOT NULL,
    financial_year text NOT NULL,
    last_value int NOT NULL DEFAULT 0,
    PRIMARY KEY (state_code, financial_year)
)""",
    """CREATE TABLE marketing_order (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_no citext NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'submitted'
        CHECK (status IN ('submitted', 'approved', 'rejected', 'cancelled', 'dispatched')),
    partner_id uuid REFERENCES channel_partner(id),
    requested_by uuid NOT NULL REFERENCES app_user(id),
    owner_org_unit_id uuid NOT NULL REFERENCES org_unit(id),
    territory_id uuid REFERENCES territory(id),
    value numeric(14,2) NOT NULL,
    company_share numeric(14,2) NOT NULL,
    dealer_share numeric(14,2) NOT NULL,
    is_provisional boolean NOT NULL,
    remark text CHECK (remark IS NULL OR length(remark) <= 1000),
    decided_by uuid REFERENCES app_user(id),
    decided_at timestamptz,
    decision_remark text CHECK (decision_remark IS NULL OR length(decision_remark) <= 1000),
    dispatched_on date,
    dispatch_reference text CHECK (dispatch_reference IS NULL OR length(btrim(dispatch_reference)) BETWEEN 1 AND 200),
    dispatched_by uuid REFERENCES app_user(id),
    cancel_remark text CHECK (cancel_remark IS NULL OR length(cancel_remark) <= 1000),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_marketing_order_shares CHECK (company_share + dealer_share = value),
    CONSTRAINT ck_marketing_order_dispatch CHECK ((status = 'dispatched') = (dispatched_on IS NOT NULL))
)""",
    "CREATE INDEX ix_marketing_order_partner ON marketing_order (partner_id) WHERE partner_id IS NOT NULL",
    "CREATE INDEX ix_marketing_order_requested_by ON marketing_order (requested_by)",
    "CREATE INDEX ix_marketing_order_office ON marketing_order (owner_org_unit_id, status)",
    "CREATE INDEX ix_marketing_order_created ON marketing_order (created_at DESC, id DESC)",
    """CREATE TABLE marketing_order_line (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id uuid NOT NULL REFERENCES marketing_order(id) ON DELETE CASCADE,
    line_no int NOT NULL,
    material_id uuid NOT NULL REFERENCES marketing_material(id),
    price_id uuid NOT NULL REFERENCES marketing_material_price(id),
    code text NOT NULL,
    name text NOT NULL,
    unit text NOT NULL,
    qty int NOT NULL CHECK (qty BETWEEN 1 AND 100000),
    price numeric(14,2) NOT NULL,
    value numeric(14,2) NOT NULL,
    company_share_pct numeric(6,3) NOT NULL,
    company_share numeric(14,2) NOT NULL,
    dealer_share numeric(14,2) NOT NULL,
    is_provisional boolean NOT NULL,
    CONSTRAINT uq_marketing_order_line UNIQUE (order_id, line_no),
    CONSTRAINT uq_marketing_order_material UNIQUE (order_id, material_id),
    CONSTRAINT ck_marketing_line_value CHECK (value = qty * price),
    CONSTRAINT ck_marketing_line_shares CHECK (
        company_share = round(value * company_share_pct / 100, 2) AND company_share + dealer_share = value)
)""",
    "CREATE INDEX ix_marketing_order_line_material ON marketing_order_line (material_id)",
    *[f"INSERT INTO marketing_material (code, name, unit) VALUES ('{c}', '{n}', '{u}')" for c, n, u, _ in CATALOGUE],
    *[f"INSERT INTO marketing_material_price (material_id, price, company_share_pct, is_provisional, effective_from) "
      f"SELECT id, {p}, 50, true, DATE '2026-04-01' FROM marketing_material WHERE code = '{c}'" for c, _, _, p in CATALOGUE],
]

RLS_TABLES = ("marketing_material", "marketing_material_price", "marketing_order", "marketing_order_line",
              "marketing_order_counter")

GRANTS: dict[str, str] = {
    "marketing_material": "SELECT, INSERT, UPDATE",
    # a price row is closed (effective_to) and never changed otherwise: the trigger refuses
    # DELETE only for a row that started today and no order uses (code review F-1)
    "marketing_material_price": "SELECT, INSERT, UPDATE (effective_to), DELETE",
    "marketing_order": "SELECT",
    "marketing_order_line": "SELECT",
}

_VIEW = "(SELECT app_has_permission('marketing_material', 'view'))"
_EDIT = "(SELECT app_has_permission('marketing_material', 'edit')) AND (SELECT app_current_partner()) IS NULL"
_PARTNER = "(SELECT app_current_partner())"


# api/authz/activity.py policy_sql(), pasted; test_policy_drift_005 compares the two
ACTIVITY_SEL = "CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (\n  CASE entity_type\n    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)\n    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)\n    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)\n    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)\n    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)\n    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)\n    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order c WHERE c.id = entity_id)\n    WHEN 'lead_qr_code' THEN EXISTS (SELECT 1 FROM lead_qr_code c WHERE c.id = entity_id)\n    WHEN 'task' THEN EXISTS (SELECT 1 FROM task c WHERE c.id = entity_id)\n    WHEN 'meeting_minutes' THEN EXISTS (SELECT 1 FROM meeting_minutes c WHERE c.id = entity_id)\n    WHEN 'complaint' THEN EXISTS (SELECT 1 FROM complaint c WHERE c.id = entity_id)\n    WHEN 'subsidy_application' THEN EXISTS (SELECT 1 FROM subsidy_application c WHERE c.id = entity_id)\n    WHEN 'scheme' THEN EXISTS (SELECT 1 FROM scheme c WHERE c.id = entity_id)\n    WHEN 'marketing_order' THEN EXISTS (SELECT 1 FROM marketing_order c WHERE c.id = entity_id)\n    WHEN 'reward_rule' THEN EXISTS (SELECT 1 FROM reward_rule c WHERE c.id = entity_id)\n    WHEN 'gift' THEN EXISTS (SELECT 1 FROM gift c WHERE c.id = entity_id)\n    WHEN 'reward_setting' THEN EXISTS (SELECT 1 FROM reward_setting c WHERE c.id = entity_id)\n    ELSE (SELECT app_is_system())\n  END\n)"

HAND_POLICIES: list[tuple[str, str]] = [
    # a partner user reads only the active catalogue
    ("marketing_material", f"CREATE POLICY marketing_material_sel ON marketing_material FOR SELECT USING ({_VIEW} AND ({_PARTNER} IS NULL OR is_active))"),
    ("marketing_material", f"CREATE POLICY marketing_material_ins ON marketing_material FOR INSERT WITH CHECK ({_EDIT})"),
    ("marketing_material", f"CREATE POLICY marketing_material_upd ON marketing_material FOR UPDATE USING ({_EDIT})"),
    ("marketing_material_price", "CREATE POLICY marketing_material_price_sel ON marketing_material_price FOR SELECT USING (EXISTS (SELECT 1 FROM marketing_material m WHERE m.id = material_id))"),
    ("marketing_material_price", f"CREATE POLICY marketing_material_price_ins ON marketing_material_price FOR INSERT WITH CHECK ({_EDIT})"),
    ("marketing_material_price", f"CREATE POLICY marketing_material_price_upd ON marketing_material_price FOR UPDATE USING ({_EDIT})"),
    ("marketing_material_price", f"CREATE POLICY marketing_material_price_del ON marketing_material_price FOR DELETE USING ({_EDIT} AND effective_from = (now() AT TIME ZONE 'Asia/Kolkata')::date AND NOT EXISTS (SELECT 1 FROM marketing_order_line l WHERE l.price_id = marketing_material_price.id))"),
    # staff: V:global (RBAC 6); a partner user: its own subtree's orders
    ("marketing_order", f"CREATE POLICY marketing_order_sel ON marketing_order FOR SELECT USING ({_VIEW} AND ({_PARTNER} IS NULL OR partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = {_PARTNER})))"),
    ("marketing_order_line", "CREATE POLICY marketing_order_line_sel ON marketing_order_line FOR SELECT USING (EXISTS (SELECT 1 FROM marketing_order o WHERE o.id = order_id))"),
    ("activity_event", ACTIVITY_SEL),
]

FUNCTIONS = [
    """CREATE FUNCTION refuse_marketing_price_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    IF (to_jsonb(NEW) - 'effective_to') IS DISTINCT FROM (to_jsonb(OLD) - 'effective_to') THEN
        RAISE EXCEPTION 'a price row is never edited; add a new one' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$""",
    """CREATE FUNCTION marketing_allocate_no(p_state text, p_fy text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    INSERT INTO marketing_order_counter (state_code, financial_year, last_value) VALUES (p_state, p_fy, 1)
    ON CONFLICT (state_code, financial_year) DO UPDATE SET last_value = marketing_order_counter.last_value + 1
    RETURNING last_value INTO v_n;
    RETURN 'MM/' || p_state || '/' || p_fy || '/' || lpad(v_n::text, greatest(5, length(v_n::text)), '0');
END $fn$""",
    # one rule for every action (review): null when allowed, else the reason
    """CREATE FUNCTION marketing_order_refusal(p_order uuid, p_action text) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE o marketing_order%ROWTYPE; v_me uuid := app_current_user_id(); v_partner uuid := app_current_partner();
BEGIN
    SELECT * INTO o FROM marketing_order WHERE id = p_order;
    IF o.id IS NULL OR NOT app_has_permission('marketing_material', 'view')
       OR (v_partner IS NOT NULL AND (o.partner_id IS NULL OR o.partner_id NOT IN
           (SELECT descendant_id FROM partner_closure WHERE ancestor_id = v_partner))) THEN
        RETURN 'not_visible';
    END IF;
    IF p_action IN ('approve', 'reject') THEN
        IF o.status <> 'submitted' THEN RETURN 'status_changed'; END IF;
        IF v_partner IS NOT NULL OR NOT app_has_permission('marketing_material', 'approve') THEN
            RETURN 'not_permitted';
        END IF;
        IF o.requested_by = v_me THEN RETURN 'own_order'; END IF;
        IF NOT app_has_permission('marketing_material', 'delete')
           AND o.owner_org_unit_id NOT IN (SELECT descendant_id FROM org_closure
                                            WHERE ancestor_id = app_current_org_unit()) THEN
            RETURN 'not_your_approval';
        END IF;
        RETURN NULL;
    ELSIF p_action = 'cancel' THEN
        IF o.status = 'submitted' AND o.requested_by = v_me THEN RETURN NULL; END IF;
        IF o.status = 'approved' AND v_partner IS NULL AND app_has_permission('marketing_material', 'edit') THEN
            RETURN NULL;
        END IF;
        IF o.status NOT IN ('submitted', 'approved') THEN RETURN 'status_changed'; END IF;
        RETURN 'not_permitted';
    ELSIF p_action = 'dispatch' THEN
        IF o.status <> 'approved' THEN RETURN 'status_changed'; END IF;
        IF v_partner IS NOT NULL OR NOT app_has_permission('marketing_material', 'edit') THEN
            RETURN 'not_permitted';
        END IF;
        RETURN NULL;
    END IF;
    RETURN 'unknown_action';
END $fn$""",
    """CREATE FUNCTION marketing_event(p_order uuid, p_kind text, p_payload jsonb) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    INSERT INTO activity_event (entity_type, entity_id, partner_id, kind, actor_id, payload)
    SELECT 'marketing_order', o.id, o.partner_id, p_kind, app_current_user_id(),
           jsonb_build_object('order_no', o.order_no,
                              'actor_name', coalesce((SELECT full_name FROM app_user WHERE id = app_current_user_id()), ''))
           || coalesce(p_payload, '{}')
      FROM marketing_order o WHERE o.id = p_order
$fn$""",
    # p_office is routed by the service (the lead routing rule); p_lines: [{material_id, qty}]
    """CREATE FUNCTION marketing_order_create(p_partner uuid, p_office uuid, p_lines jsonb, p_remark text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_caller_partner uuid := app_current_partner();
        v_partner uuid; v_territory uuid; v_state text; v_day date := (now() AT TIME ZONE 'Asia/Kolkata')::date;
        v_fy text; v_y int; v_id uuid; l jsonb; m record; v_n int := 0; v_value numeric; v_pct numeric;
        v_company numeric; v_seen uuid[] := '{}';
BEGIN
    IF NOT app_has_permission('marketing_material', 'create') THEN
        RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
    END IF;
    v_partner := coalesce(v_caller_partner, p_partner);
    IF v_partner IS NOT NULL THEN
        SELECT territory_id INTO v_territory FROM channel_partner WHERE id = v_partner AND is_active
           AND (v_caller_partner IS NOT NULL OR EXISTS (SELECT 1 FROM channel_partner WHERE id = v_partner));
        IF NOT FOUND THEN
            RAISE EXCEPTION 'no such partner' USING ERRCODE = 'MKTVL';
        END IF;
    ELSE
        SELECT territory_id INTO v_territory FROM org_unit WHERE id = p_office;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM org_unit WHERE id = p_office) THEN
        RAISE EXCEPTION 'no office' USING ERRCODE = 'MKTVL';
    END IF;
    IF jsonb_typeof(p_lines) <> 'array' OR jsonb_array_length(p_lines) = 0 THEN
        RAISE EXCEPTION 'at least one line' USING ERRCODE = 'MKTVL';
    END IF;
    SELECT t.code::text INTO v_state FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id
     WHERE tc.descendant_id = v_territory AND t.level = 'state' AND t.code IS NOT NULL ORDER BY tc.depth LIMIT 1;
    v_y := CASE WHEN extract(month FROM v_day) >= 4 THEN extract(year FROM v_day)::int ELSE extract(year FROM v_day)::int - 1 END;
    v_fy := v_y::text || '-' || lpad(((v_y + 1) % 100)::text, 2, '0');
    INSERT INTO marketing_order (order_no, partner_id, requested_by, owner_org_unit_id, territory_id, value,
                                 company_share, dealer_share, is_provisional, remark)
    VALUES (marketing_allocate_no(coalesce(v_state, 'HQ'), v_fy), v_partner, v_me, p_office, v_territory,
            0, 0, 0, false, nullif(btrim(p_remark), ''))
    RETURNING id INTO v_id;
    FOR l IN SELECT * FROM jsonb_array_elements(p_lines) LOOP
        v_n := v_n + 1;
        SELECT mm.id, mm.code::text AS code, mm.name, mm.unit, mm.is_active, pr.id AS price_id, pr.price,
               pr.company_share_pct, pr.is_provisional
          INTO m
          FROM marketing_material mm
          JOIN marketing_material_price pr ON pr.material_id = mm.id
               AND daterange(pr.effective_from, pr.effective_to, '[)') @> v_day
         WHERE mm.id = (l ->> 'material_id')::uuid;
        IF m.id IS NULL OR NOT m.is_active THEN
            RAISE EXCEPTION 'line %: the item is not available', v_n USING ERRCODE = 'MKTIN';
        END IF;
        IF m.id = ANY(v_seen) THEN
            RAISE EXCEPTION 'line %: the item is listed twice', v_n USING ERRCODE = 'MKTVL';
        END IF;
        v_seen := v_seen || m.id;
        IF (l ->> 'qty')::int IS NULL OR (l ->> 'qty')::int <= 0 THEN
            RAISE EXCEPTION 'line %: quantity', v_n USING ERRCODE = 'MKTVL';
        END IF;
        v_value := (l ->> 'qty')::int * m.price;
        v_pct := CASE WHEN v_partner IS NULL THEN 100 ELSE m.company_share_pct END;   -- rule 4
        v_company := round(v_value * v_pct / 100, 2);
        INSERT INTO marketing_order_line (order_id, line_no, material_id, price_id, code, name, unit, qty, price, value,
                                          company_share_pct, company_share, dealer_share, is_provisional)
        VALUES (v_id, v_n, m.id, m.price_id, m.code, m.name, m.unit, (l ->> 'qty')::int, m.price, v_value,
                v_pct, v_company, v_value - v_company, m.is_provisional);
    END LOOP;
    UPDATE marketing_order SET value = t.v, company_share = t.c, dealer_share = t.d, is_provisional = t.p
      FROM (SELECT sum(value) v, sum(company_share) c, sum(dealer_share) d, bool_or(is_provisional) p
              FROM marketing_order_line WHERE order_id = v_id) t
     WHERE id = v_id;
    PERFORM marketing_event(v_id, 'marketing_order.submitted', '{}'::jsonb);
    RETURN v_id;
END $fn$""",
    """CREATE FUNCTION marketing_order_act(p_order uuid, p_action text, p_remark text, p_date date, p_reference text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE o marketing_order%ROWTYPE; v_reason text; v_to text;
BEGIN
    SELECT * INTO o FROM marketing_order WHERE id = p_order FOR UPDATE;
    v_reason := marketing_order_refusal(p_order, p_action);
    IF v_reason = 'not_visible' THEN
        RAISE EXCEPTION 'not found' USING ERRCODE = 'MKTNF';
    ELSIF v_reason = 'status_changed' THEN
        RAISE EXCEPTION 'the order is %', o.status USING ERRCODE = 'MKTSC';
    ELSIF v_reason IS NOT NULL THEN
        RAISE EXCEPTION '%', v_reason USING ERRCODE = '42501';
    END IF;
    IF (p_action = 'reject' OR (p_action = 'cancel' AND o.status = 'approved'))
       AND (p_remark IS NULL OR btrim(p_remark) = '') THEN
        RAISE EXCEPTION 'a remark is required' USING ERRCODE = 'APRRM';
    END IF;
    IF p_action = 'dispatch' AND (p_date IS NULL OR p_date > (now() AT TIME ZONE 'Asia/Kolkata')::date
                                  OR p_reference IS NULL OR btrim(p_reference) = '') THEN
        RAISE EXCEPTION 'a dispatch date, not in the future, and a reference are required' USING ERRCODE = 'MKTVL';
    END IF;
    v_to := CASE p_action WHEN 'approve' THEN 'approved' WHEN 'reject' THEN 'rejected'
                          WHEN 'cancel' THEN 'cancelled' ELSE 'dispatched' END;
    UPDATE marketing_order SET status = v_to, updated_at = now(),
           decided_by = CASE WHEN p_action IN ('approve', 'reject') THEN app_current_user_id() ELSE decided_by END,
           decided_at = CASE WHEN p_action IN ('approve', 'reject') THEN now() ELSE decided_at END,
           decision_remark = CASE WHEN p_action IN ('approve', 'reject') THEN nullif(btrim(p_remark), '') ELSE decision_remark END,
           cancel_remark = CASE WHEN p_action = 'cancel' THEN nullif(btrim(p_remark), '') ELSE cancel_remark END,
           dispatched_on = CASE WHEN p_action = 'dispatch' THEN p_date ELSE dispatched_on END,
           dispatch_reference = CASE WHEN p_action = 'dispatch' THEN btrim(p_reference) ELSE dispatch_reference END,
           dispatched_by = CASE WHEN p_action = 'dispatch' THEN app_current_user_id() ELSE dispatched_by END
     WHERE id = p_order;
    PERFORM marketing_event(p_order, 'marketing_order.' || v_to, '{}'::jsonb);
END $fn$""",
]

TRIGGERS = [
    "CREATE TRIGGER trg_marketing_material_updated_at BEFORE UPDATE ON marketing_material FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_marketing_material_audit AFTER INSERT OR UPDATE OR DELETE ON marketing_material FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_marketing_material_price_refuse BEFORE UPDATE ON marketing_material_price FOR EACH ROW EXECUTE FUNCTION refuse_marketing_price_edit()",
    "CREATE TRIGGER trg_marketing_material_price_audit AFTER INSERT OR UPDATE OR DELETE ON marketing_material_price FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_marketing_order_audit AFTER INSERT OR UPDATE OR DELETE ON marketing_order FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

GRANTED = [
    "marketing_order_refusal(uuid, text)",
    "marketing_order_create(uuid, uuid, jsonb, text)",
    "marketing_order_act(uuid, text, text, date, text)",
]
INTERNAL = ["marketing_allocate_no(text, text)", "marketing_event(uuid, text, jsonb)",
            "refuse_marketing_price_edit()"]


def _load(stem: str) -> ModuleType:
    path = next(Path(__file__).parent.glob(f"{stem}_*.py"))
    spec = importlib.util.spec_from_file_location(f"mig_{stem}_for_038", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"038: migration {stem} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def upgrade() -> None:
    for stmt in TABLES:
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
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    m033 = _load("033")
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(next(st for t, st in m033.HAND_POLICIES if t == "activity_event"))  # type: ignore[attr-defined]
    op.execute("DELETE FROM activity_event WHERE entity_type = 'marketing_order'")
    for table in ("marketing_order_line", "marketing_order", "marketing_order_counter",
                  "marketing_material_price", "marketing_material"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
