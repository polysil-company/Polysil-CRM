"""032: stock: warehouses, the stock ledger, dispatch decrements (FS-023, ADR-046).

- `warehouse`: one default (partial unique index), seeded `MAIN`, so every dispatch
  has somewhere to come from (review B-4).
- `stock_movement`: a signed ledger, never edited. Manual movements go through
  `stock_record()`, which serialises each (warehouse, product) with a transaction
  advisory lock: a session lock would outlive the client under PgBouncer (B-5).
  `app_role` reads only (B-6).
- **A dispatch carries its warehouse** (B-2): `dispatch_record` (026's text) stores
  `warehouse_id`, from the payload, else the order's, else the default. A trigger on
  `dispatch_line` writes `-qty` there; a trigger on `dispatch.voided_at` negates
  the stored movement. They take no lock: a dispatch may go negative (rule 5).
- `sales_order.warehouse_id` ("Order to"), granted for INSERT and UPDATE (B-3). It
  decides where `committed` counts.
- RBAC: staff `stock` rows; the portal rows go (B-1); the board's Except line names
  `stock` in RBAC.md.

Revision ID: 032_stock
Revises: 031_payments
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "032_stock"
down_revision: str | None = "031_payments"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_032", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"032: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"032: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


ENUMS = ["CREATE TYPE stock_kind AS ENUM ('receipt', 'adjustment', 'dispatch', 'dispatch_void')"]

TABLES = [
    """CREATE TABLE warehouse (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE CHECK (length(code) BETWEEN 1 AND 30),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    territory_id uuid REFERENCES territory(id),
    is_default boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_by uuid REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid REFERENCES app_user(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_warehouse_default_active CHECK (NOT is_default OR is_active)
)""",
    """CREATE TABLE stock_movement (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    warehouse_id uuid NOT NULL REFERENCES warehouse(id),
    product_id uuid NOT NULL REFERENCES product(id),
    qty numeric(14,3) NOT NULL CHECK (qty <> 0),
    kind stock_kind NOT NULL,
    reference text CHECK (reference IS NULL OR length(reference) <= 200),
    note text CHECK (note IS NULL OR length(note) <= 1000),
    dispatch_line_id uuid REFERENCES dispatch_line(id),
    created_by uuid REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_stock_movement_source CHECK ((kind IN ('dispatch', 'dispatch_void')) = (dispatch_line_id IS NOT NULL)),
    CONSTRAINT ck_stock_movement_sign CHECK (kind = 'adjustment' OR (kind IN ('receipt', 'dispatch_void')) = (qty > 0))
)""",
    "ALTER TABLE sales_order ADD COLUMN warehouse_id uuid REFERENCES warehouse(id)",
    "ALTER TABLE dispatch ADD COLUMN warehouse_id uuid REFERENCES warehouse(id)",
    "CREATE TRIGGER trg_warehouse_updated_at BEFORE UPDATE ON warehouse FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_warehouse_audit AFTER INSERT OR UPDATE OR DELETE ON warehouse FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "CREATE TRIGGER trg_stock_movement_audit AFTER INSERT OR UPDATE OR DELETE ON stock_movement FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

INDEXES = [
    "CREATE UNIQUE INDEX uq_warehouse_default ON warehouse (is_default) WHERE is_default",
    "CREATE INDEX ix_warehouse_territory ON warehouse (territory_id)",
    "CREATE INDEX ix_warehouse_created_by ON warehouse (created_by)",
    "CREATE INDEX ix_warehouse_updated_by ON warehouse (updated_by)",
    "CREATE INDEX ix_stock_movement_wp ON stock_movement (warehouse_id, product_id)",
    "CREATE INDEX ix_stock_movement_product ON stock_movement (product_id)",
    "CREATE INDEX ix_stock_movement_created ON stock_movement (created_at)",
    "CREATE INDEX ix_stock_movement_created_by ON stock_movement (created_by)",
    # a dispatch line moves stock once, and is restored once (review edge case 2)
    "CREATE UNIQUE INDEX uq_stock_movement_dispatch ON stock_movement (dispatch_line_id, kind) WHERE dispatch_line_id IS NOT NULL",
    "CREATE INDEX ix_sales_order_warehouse ON sales_order (warehouse_id)",
    "CREATE INDEX ix_dispatch_warehouse ON dispatch (warehouse_id)",
]

# tests/db/migration_grants.py reads these two, as it does every migration's
GRANTS: dict[str, str] = {
    "warehouse": "SELECT, INSERT, UPDATE",
    "stock_movement": "SELECT",
    "sales_order": "INSERT (warehouse_id), UPDATE (warehouse_id)",
}

_STAFF = "(SELECT app_current_partner()) IS NULL"
HAND_POLICIES: list[tuple[str, str]] = [
    ("warehouse", f"CREATE POLICY warehouse_sel ON warehouse FOR SELECT USING (\n  {_STAFF} AND (SELECT app_has_permission('stock', 'view'))\n)"),
    ("warehouse", "CREATE POLICY warehouse_ins ON warehouse FOR INSERT WITH CHECK (\n  (SELECT app_has_permission('stock', 'edit'))\n)"),
    ("warehouse", "CREATE POLICY warehouse_upd ON warehouse FOR UPDATE USING (\n  (SELECT app_has_permission('stock', 'edit'))\n) WITH CHECK (\n  (SELECT app_has_permission('stock', 'edit'))\n)"),
    ("stock_movement", f"CREATE POLICY stock_movement_sel ON stock_movement FOR SELECT USING (\n  {_STAFF} AND (SELECT app_has_permission('stock', 'view'))\n)"),
]

SEED = ["INSERT INTO warehouse (code, name, is_default) VALUES ('MAIN', 'Main warehouse', true) ON CONFLICT (code) DO NOTHING"]

# RBAC.md §6.1/§6.2's stock rows; the portal row is gone (review B-1)
_STAFF_ROLES = ("field_officer", "district_manager", "state_manager", "regional_manager", "account_manager",
                "qc_manager", "state_coordinator", "marketing", "support")
PERMISSIONS = ([(r, "view") for r in _STAFF_ROLES]
               + [("dispatch_manager", a) for a in ("view", "create")]
               + [(r, a) for r in ("admin_sales", "md_ceo") for a in ("view", "create", "edit")])


def _permission_sql() -> list[str]:
    rows = ", ".join(f"('{c}', '{a}')" for c, a in PERMISSIONS)
    return [
        "DELETE FROM role_permission WHERE module = 'stock' AND role_id IN "
        "(SELECT id FROM role WHERE code IN ('distributor', 'dealer', 'sub_dealer', 'board'))",
        f"""INSERT INTO role_permission (role_id, module, action, scope)
SELECT r.id, 'stock', CAST(v.action AS permission_action), CAST('global' AS permission_scope)
  FROM (VALUES {rows}) AS v(code, action) JOIN role r ON r.code = v.code
ON CONFLICT (role_id, module, action) DO NOTHING""",
    ]


_OPEN = _load("013_orders_approvals_dispatch")._OPEN

FUNCTIONS = [
    """CREATE FUNCTION stock_default_warehouse() RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT id FROM warehouse WHERE is_default
$fn$""",
    """CREATE FUNCTION stock_on_hand(p_warehouse uuid, p_product uuid) RETURNS numeric
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT COALESCE(sum(qty), 0) FROM stock_movement WHERE warehouse_id = p_warehouse AND product_id = p_product
$fn$""",
    # what submitted, approved and partly dispatched orders for the warehouse still owe
    f"""CREATE FUNCTION stock_committed(p_warehouse uuid, p_product uuid) RETURNS numeric
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT COALESCE(sum(GREATEST({_OPEN}, 0)), 0)
      FROM order_line l JOIN sales_order o ON o.id = l.sales_order_id
     WHERE l.product_id = p_product AND o.deleted_at IS NULL
       AND o.status IN ('submitted', 'approved', 'partially_dispatched')
       AND COALESCE(o.warehouse_id, stock_default_warehouse()) = p_warehouse
$fn$""",
    """CREATE FUNCTION stock_record(p_warehouse uuid, p_kind text, p_reference text, p_note text, p_lines jsonb)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); w warehouse%ROWTYPE; r record; v_id uuid; v_after numeric;
    v_out jsonb := '[]'::jsonb; v_dec smallint; v_active boolean;
BEGIN
    IF app_current_partner() IS NOT NULL OR NOT app_has_permission('stock', 'create') THEN
        RAISE EXCEPTION 'not permitted to record stock' USING ERRCODE = '42501';
    END IF;
    IF p_kind NOT IN ('receipt', 'adjustment') THEN
        RAISE EXCEPTION 'kind must be receipt or adjustment' USING ERRCODE = '22023';
    END IF;
    SELECT * INTO w FROM warehouse WHERE id = p_warehouse;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'warehouse not found' USING ERRCODE = 'STKNF';
    END IF;
    IF NOT w.is_active THEN
        RAISE EXCEPTION 'the warehouse is inactive' USING ERRCODE = 'STKWI';
    END IF;
    -- sorted, so two writers never take the locks in opposite orders
    FOR r IN SELECT (x ->> 'product_id')::uuid AS product_id, (x ->> 'qty')::numeric AS qty
               FROM jsonb_array_elements(p_lines) x ORDER BY 1 LOOP
        PERFORM pg_advisory_xact_lock(hashtextextended(p_warehouse::text || r.product_id::text, 0));
        SELECT u.decimals, p.is_active INTO v_dec, v_active
          FROM product p JOIN uom u ON u.id = p.uom_id WHERE p.id = r.product_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'product % not found', r.product_id USING ERRCODE = 'STKNF';
        END IF;
        IF r.qty IS NULL OR r.qty = 0 OR r.qty <> round(r.qty, v_dec) THEN
            RAISE EXCEPTION 'product % takes % decimal places, not zero', r.product_id, v_dec USING ERRCODE = 'STKPR';
        END IF;
        IF p_kind = 'receipt' AND r.qty < 0 THEN
            RAISE EXCEPTION 'a receipt is positive' USING ERRCODE = '22023';
        END IF;
        IF r.qty > 0 AND NOT v_active THEN
            RAISE EXCEPTION 'product % is inactive', r.product_id USING ERRCODE = 'STKPI';
        END IF;
        v_after := stock_on_hand(p_warehouse, r.product_id) + r.qty;
        IF r.qty < 0 AND v_after < 0 THEN
            RAISE EXCEPTION 'product % would go below zero', r.product_id USING ERRCODE = 'STKNG';
        END IF;
        INSERT INTO stock_movement (warehouse_id, product_id, qty, kind, reference, note, created_by)
        VALUES (p_warehouse, r.product_id, r.qty, p_kind::stock_kind, NULLIF(btrim(p_reference), ''),
                NULLIF(btrim(p_note), ''), v_me)
        RETURNING id INTO v_id;
        v_out := v_out || jsonb_build_object('id', v_id, 'product_id', r.product_id, 'qty', r.qty, 'on_hand_after', v_after);
    END LOOP;
    RETURN v_out;
END $fn$""",
    # Fired inside dispatch_record as the owner. No lock: a dispatch may go negative,
    # and dispatch_record inserts lines unordered (review B-5).
    """CREATE FUNCTION stock_on_dispatch_line() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_wh uuid; v_product uuid; v_by uuid;
BEGIN
    SELECT d.warehouse_id, d.dispatched_by INTO v_wh, v_by FROM dispatch d WHERE d.id = NEW.dispatch_id;
    SELECT l.product_id INTO v_product FROM order_line l WHERE l.id = NEW.order_line_id;
    IF v_wh IS NULL THEN
        RAISE EXCEPTION 'no warehouse for this dispatch, and no default warehouse' USING ERRCODE = 'STKNW';
    END IF;
    INSERT INTO stock_movement (warehouse_id, product_id, qty, kind, dispatch_line_id, created_by)
    VALUES (v_wh, v_product, -NEW.qty, 'dispatch', NEW.id, v_by);
    RETURN NULL;
END $fn$""",
    "CREATE TRIGGER trg_dispatch_line_stock AFTER INSERT ON dispatch_line FOR EACH ROW WHEN (NEW.qty > 0) "
    "EXECUTE FUNCTION stock_on_dispatch_line()",
    # a void puts back exactly what was taken, wherever the order points now (edge case 2)
    """CREATE FUNCTION stock_on_dispatch_void() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    INSERT INTO stock_movement (warehouse_id, product_id, qty, kind, dispatch_line_id, created_by)
    SELECT m.warehouse_id, m.product_id, -m.qty, 'dispatch_void', m.dispatch_line_id, NEW.voided_by
      FROM stock_movement m JOIN dispatch_line dl ON dl.id = m.dispatch_line_id
     WHERE dl.dispatch_id = NEW.id AND m.kind = 'dispatch';
    RETURN NULL;
END $fn$""",
    "CREATE TRIGGER trg_dispatch_void_stock AFTER UPDATE OF voided_at ON dispatch FOR EACH ROW "
    "WHEN (OLD.voided_at IS NULL AND NEW.voided_at IS NOT NULL) EXECUTE FUNCTION stock_on_dispatch_void()",
]

GRANTED = ["stock_on_hand(uuid, uuid)", "stock_committed(uuid, uuid)", "stock_default_warehouse()",
           "stock_record(uuid, text, text, text, jsonb)"]
INTERNAL = ["stock_on_dispatch_line()", "stock_on_dispatch_void()"]


def _dispatch_record_before() -> str:
    (f,) = [x for x in _load("026_complaint_remedies")._orders_patched() if "FUNCTION dispatch_record(" in x]
    return str(f)


def dispatch_record_after() -> str:
    """The warehouse goods left from: the payload's, else the order's, else the
    default (review B-2). An inactive warehouse is refused."""
    f = _dispatch_record_before()
    f = _replace(f, "    v_dispatch uuid; v_seq int; r record;\n",
                 "    v_dispatch uuid; v_seq int; r record; v_wh uuid;\n")
    f = _replace(f, "    v_seq := v_order.dispatch_seq + 1;\n",
                 "    v_wh := COALESCE((p_payload ->> 'warehouse_id')::uuid, v_order.warehouse_id, stock_default_warehouse());\n"
                 "    IF v_wh IS NULL THEN\n"
                 "        RAISE EXCEPTION 'no warehouse for this dispatch, and no default warehouse' USING ERRCODE = 'STKNW';\n"
                 "    END IF;\n"
                 "    IF NOT EXISTS (SELECT 1 FROM warehouse WHERE id = v_wh) THEN\n"
                 "        RAISE EXCEPTION 'no such warehouse' USING ERRCODE = 'STKNF';\n"
                 "    END IF;\n"
                 "    IF NOT EXISTS (SELECT 1 FROM warehouse WHERE id = v_wh AND is_active) THEN\n"
                 "        RAISE EXCEPTION 'the warehouse is inactive' USING ERRCODE = 'STKWI';\n"
                 "    END IF;\n"
                 "    v_seq := v_order.dispatch_seq + 1;\n")
    f = _replace(f, "                          dispatched_at, transporter, vehicle_no, dispatched_by)",
                 "                          dispatched_at, transporter, vehicle_no, dispatched_by, warehouse_id)")
    f = _replace(f, "            p_payload ->> 'transporter', p_payload ->> 'vehicle_no', v_me)",
                 "            p_payload ->> 'transporter', p_payload ->> 'vehicle_no', v_me, v_wh)")
    return f


def upgrade() -> None:
    for stmt in ENUMS + TABLES + INDEXES + SEED:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for t in ("warehouse", "stock_movement"):
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute(dispatch_record_after())
    for stmt in _permission_sql():
        op.execute(stmt)
    # created and re-created functions are PUBLIC-executable until this runs (028)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    op.execute("GRANT EXECUTE ON FUNCTION dispatch_record(uuid, jsonb) TO app_role")


def downgrade() -> None:
    op.execute(_dispatch_record_before())
    op.execute("GRANT EXECUTE ON FUNCTION dispatch_record(uuid, jsonb) TO app_role")
    op.execute("DROP TRIGGER IF EXISTS trg_dispatch_line_stock ON dispatch_line")
    op.execute("DROP TRIGGER IF EXISTS trg_dispatch_void_stock ON dispatch")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DELETE FROM role_permission WHERE module = 'stock'")
    op.execute("ALTER TABLE dispatch DROP COLUMN IF EXISTS warehouse_id")
    op.execute("ALTER TABLE sales_order DROP COLUMN IF EXISTS warehouse_id")
    op.execute("DROP TABLE IF EXISTS stock_movement, warehouse")
    op.execute("DROP TYPE IF EXISTS stock_kind")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
