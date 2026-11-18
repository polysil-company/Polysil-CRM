"""045: export and sample orders (FS-042).

- `seller_gstin_lut`: the LUTs that zero-rate an export, one per GSTIN per
  financial year. Effective-dated: an overlap on one GSTIN is refused by an
  exclusion constraint, a range crossing 31 March by a CHECK. Never edited; a
  LUT no document carries is removed through `seller_gstin_lut_delete()`.
- `quotation` and `sales_order`: `tax_treatment` (domestic, export_lut,
  export_igst), `export_country` and `lut_arn`. CHECKs hold the treatment to the
  type, and the country and the absent party GSTIN to an export. The treatment
  is read from the setting once, by the service, and stored (rule 5).
- `sales_order.sample_pricing` (free or charged, on samples only) and
  `amended_from_gross`. A free sample's total is 0 (CHECK).
- Three settings in FS-036's `app_setting`: `export_tax_treatment`,
  `sample_pricing`, `sample_max_value`.
- Live-text swaps, each anchor count asserted:
  - `refuse_submitted_order_edit`: `amended_from_gross` joins the allow-list,
    first, as 046 and 047 did.
  - `order_submit`: the second enforcer. Staff only for export and sample, a
    free sample's lines all 100 % off, the sample limit, a LUT covering the
    submit day, and the ARN snapshot beside the seller.
  - `create_approval_request`: a sample's chain, request amount and
    `value_rises` comparison run on gross (plan review B-1).
  - `order_amend`: `amended_from_gross = gross`.
  - `order_notify_outcome`: no party confirmation for a free sample.

Revision ID: 045_export_sample_orders
Revises: 044_subsidy_scheme_setup
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision: str = "045_export_sample_orders"
down_revision: str | None = "044_subsidy_scheme_setup"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# the consumer floor (052): every RLS table carries it, so a new one does too
_spec = importlib.util.spec_from_file_location(
    "consumer_floor_045", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

# the financial year a date falls in, as its first calendar year
_FY = "(CASE WHEN extract(month FROM {d}) >= 4 THEN extract(year FROM {d}) ELSE extract(year FROM {d}) - 1 END)"
_TREATMENTS = "('domestic', 'export_lut', 'export_igst')"


def _export_checks(table: str, type_col: str, *, lut_required: str) -> list[str]:
    return [
        f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_tax_treatment CHECK (tax_treatment IN {_TREATMENTS})",
        f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_export_treatment "
        f"CHECK (({type_col}::text = 'export') = (tax_treatment <> 'domestic'))",
        f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_export_party CHECK (CASE WHEN {type_col}::text = 'export' "
        f"THEN export_country IS NOT NULL AND length(btrim(export_country)) BETWEEN 2 AND 60 AND party_gstin IS NULL "
        f"ELSE export_country IS NULL END)",
        f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_lut "
        f"CHECK ((lut_arn IS NULL OR tax_treatment = 'export_lut') AND ({lut_required}))",
    ]


COLUMNS = [
    *[f"ALTER TABLE {t} ADD COLUMN tax_treatment text NOT NULL DEFAULT 'domestic', "
      f"ADD COLUMN export_country text, ADD COLUMN lut_arn text" for t in ("quotation", "sales_order")],
    "ALTER TABLE sales_order ADD COLUMN sample_pricing text, ADD COLUMN amended_from_gross numeric(14,2)",
    # a quotation is taxed at its price date, so it carries its ARN from creation
    *_export_checks("quotation", "sales_type",
                    lut_required="tax_treatment <> 'export_lut' OR lut_arn IS NOT NULL"),
    # an order is taxed on its submit day: the ARN is taken there (edge case 4)
    *_export_checks("sales_order", "order_type",
                    lut_required="status = 'draft' OR tax_treatment <> 'export_lut' OR lut_arn IS NOT NULL"),
    "ALTER TABLE sales_order ADD CONSTRAINT ck_sales_order_sample_pricing "
    "CHECK ((order_type = 'sample') = (sample_pricing IS NOT NULL) "
    "AND (sample_pricing IS NULL OR sample_pricing IN ('free', 'charged')))",
    # a draft's header changes before its figures are rewritten, in one request;
    # from submit on, a free sample is worth nothing
    "ALTER TABLE sales_order ADD CONSTRAINT ck_sales_order_free_sample "
    "CHECK (sample_pricing IS DISTINCT FROM 'free' OR total = 0 OR status = 'draft')",
]

TABLES = [
    f"""CREATE TABLE seller_gstin_lut (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_gstin_id uuid NOT NULL REFERENCES seller_gstin(id),
    arn text NOT NULL CHECK (arn ~ '^[A-Z0-9]{{10,20}}$'),
    valid_from date NOT NULL,
    valid_to date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES app_user(id),
    CONSTRAINT uq_seller_gstin_lut_arn UNIQUE (seller_gstin_id, arn),
    CONSTRAINT ck_seller_gstin_lut_range CHECK (valid_to >= valid_from),
    CONSTRAINT ck_seller_gstin_lut_one_year CHECK ({_FY.format(d='valid_from')} = {_FY.format(d='valid_to')}),
    CONSTRAINT ex_seller_gstin_lut_overlap EXCLUDE USING gist
        (seller_gstin_id WITH =, daterange(valid_from, valid_to, '[]') WITH &&)
)""",
]

GRANTS: dict[str, str] = {
    "seller_gstin_lut": "SELECT, INSERT",
    # lut_arn is written by order_submit only
    "sales_order": "INSERT (tax_treatment, export_country, sample_pricing), "
                   "UPDATE (tax_treatment, export_country, sample_pricing)",
}

_READ = "(SELECT app_has_permission('products', 'view'))"
_EDIT = "(SELECT app_has_permission('products', 'edit'))"
HAND_POLICIES: list[tuple[str, str]] = [
    ("seller_gstin_lut", f"CREATE POLICY seller_gstin_lut_sel ON seller_gstin_lut FOR SELECT USING ({_READ})"),
    ("seller_gstin_lut", f"CREATE POLICY seller_gstin_lut_ins ON seller_gstin_lut FOR INSERT WITH CHECK ({_EDIT})"),
]

SEED = """INSERT INTO app_setting (key, kind, value, allowed, min, max, description) VALUES
('export_tax_treatment', 'choice', '"lut"', '["lut", "igst"]', NULL, NULL,
 'Exports zero-rated under a LUT (no IGST, the LUT number printed), or charged IGST at each line''s rate.'),
('sample_pricing', 'choice', '"free"', '["free", "charged"]', NULL, NULL,
 'Sample orders are free (every line 100 % off, no GST), or priced like a commercial order.'),
('sample_max_value', 'int', '50000', NULL, 1, 10000000,
 'The largest sample order, in rupees of list value before any discount.')
ON CONFLICT (key) DO NOTHING"""

FUNCTIONS = [
    # Whether a document carries the LUT, seen by the definer: RLS would hide some
    # documents from the caller, and the list and the delete must agree (code review F-2).
    """CREATE FUNCTION seller_gstin_lut_in_use(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM seller_gstin_lut l JOIN quotation q
                     ON q.seller_gstin_id = l.seller_gstin_id AND q.lut_arn = l.arn WHERE l.id = p_id)
        OR EXISTS (SELECT 1 FROM seller_gstin_lut l JOIN sales_order o
                     ON o.seller_gstin_id = l.seller_gstin_id AND o.lut_arn = l.arn WHERE l.id = p_id)
$fn$""",
    # A LUT a document carries is history (CLAUDE.md 4.1 rule 10). Documents store
    # the ARN, not an id, and RLS would hide some of them from the caller, so the
    # check runs as the definer.
    """CREATE FUNCTION seller_gstin_lut_delete(p_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v seller_gstin_lut%ROWTYPE;
BEGIN
    IF NOT app_has_permission('products', 'edit') THEN
        RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO v FROM seller_gstin_lut WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'lut not found' USING ERRCODE = 'LUTNF';
    END IF;
    IF seller_gstin_lut_in_use(p_id) THEN
        RAISE EXCEPTION 'a document carries this LUT' USING ERRCODE = 'LUTUS';
    END IF;
    DELETE FROM seller_gstin_lut WHERE id = p_id;
END $fn$""",
    # The ARN covering a day, for the service and order_submit. NULL when none.
    """CREATE FUNCTION seller_gstin_lut_on(p_gstin uuid, p_day date) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT arn FROM seller_gstin_lut
     WHERE seller_gstin_id = p_gstin AND p_day BETWEEN valid_from AND valid_to
$fn$""",
]

TRIGGERS = [
    "CREATE TRIGGER trg_seller_gstin_lut_audit AFTER INSERT OR UPDATE OR DELETE ON seller_gstin_lut "
    "FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

GRANTED = ["seller_gstin_lut_delete(uuid)", "seller_gstin_lut_on(uuid, date)",
           "seller_gstin_lut_in_use(uuid)"]

# ── live-text swaps ──────────────────────────────────────────────────────────

_COLS = "'over_credit_limit']"
_COLS_NEW = "'over_credit_limit', 'amended_from_gross']"
GUARD = [("refuse_submitted_order_edit", [(_COLS, _COLS_NEW, 2)])]

_SUBMIT_DECL = "    v_no text; v_seller record;\n"
_SUBMIT_DECL_NEW = "    v_no text; v_seller record; v_lut text;\n"
_SUBMIT_GATE = "    v_day := (now() AT TIME ZONE 'Asia/Kolkata')::date;\n    v_no := v_order.order_no;\n"
_SUBMIT_GATE_NEW = """    v_day := (now() AT TIME ZONE 'Asia/Kolkata')::date;
    -- FS-042: the second enforcer for export and sample orders
    IF v_order.order_type IN ('export', 'sample') AND app_current_partner() IS NOT NULL THEN
        RAISE EXCEPTION 'export and sample orders are raised by staff' USING ERRCODE = 'ORDXS';
    END IF;
    IF v_order.order_type = 'sample' THEN
        IF v_order.sample_pricing = 'free' AND EXISTS (
               SELECT 1 FROM order_line WHERE sales_order_id = p_order_id AND discount_pct <> 100) THEN
            RAISE EXCEPTION 'a free sample has a priced line' USING ERRCODE = 'ORDSF';
        END IF;
        IF v_order.gross > (app_setting_json('sample_max_value') #>> '{}')::numeric THEN
            RAISE EXCEPTION 'the sample is over its limit' USING ERRCODE = 'ORDSL';
        END IF;
    END IF;
    IF v_order.tax_treatment = 'export_lut' THEN
        IF EXISTS (SELECT 1 FROM order_line WHERE sales_order_id = p_order_id AND igst_rate <> 0) THEN
            RAISE EXCEPTION 'an export under a LUT has a taxed line' USING ERRCODE = 'ORDLX';
        END IF;
        v_lut := seller_gstin_lut_on(v_order.seller_gstin_id, v_day);
        IF v_lut IS NULL THEN
            RAISE EXCEPTION 'no LUT covers today' USING ERRCODE = 'ORDLT';
        END IF;
    END IF;
    v_no := v_order.order_no;
"""
_SUBMIT_SNAP = "           seller_address = v_seller.address, seller_state_code = v_seller.state_code,\n"
_SUBMIT_SNAP_NEW = _SUBMIT_SNAP + "           lut_arn = v_lut,\n"

_CHAIN = "approval_chain(p_doc_type, v_order.total, v_order.territory_id,"
_CHAIN_NEW = ("approval_chain(p_doc_type, CASE WHEN v_order.order_type = 'sample' THEN v_order.gross "
              "ELSE v_order.total END, v_order.territory_id,")
_RISES = "AND v_order.total <= v_order.amended_from_total"
_RISES_NEW = ("AND CASE WHEN v_order.order_type = 'sample' THEN v_order.gross <= v_order.amended_from_gross\n"
              "                                            ELSE v_order.total <= v_order.amended_from_total END")
_AMOUNT = "VALUES (p_doc_type, p_entity_id, app_current_user_id(), v_order.total, v_order.territory_id)"
_AMOUNT_NEW = ("VALUES (p_doc_type, p_entity_id, app_current_user_id(),\n"
               "            CASE WHEN v_order.order_type = 'sample' THEN v_order.gross ELSE v_order.total END,\n"
               "            v_order.territory_id)")

_AMEND = "amended_from_total = total, amended_at = now(),"
_AMEND_NEW = "amended_from_total = total, amended_from_gross = gross, amended_at = now(),"

_OUTCOME = "IF v_tpl IS NULL OR o.order_type = 'replacement' THEN"
_OUTCOME_NEW = "IF v_tpl IS NULL OR o.order_type = 'replacement' OR o.sample_pricing = 'free' THEN"

SWAPS = [
    ("order_submit", [(_SUBMIT_DECL, _SUBMIT_DECL_NEW, 1), (_SUBMIT_GATE, _SUBMIT_GATE_NEW, 1),
                      (_SUBMIT_SNAP, _SUBMIT_SNAP_NEW, 1)]),
    ("create_approval_request", [(_CHAIN, _CHAIN_NEW, 1), (_RISES, _RISES_NEW, 1), (_AMOUNT, _AMOUNT_NEW, 1)]),
    ("order_amend", [(_AMEND, _AMEND_NEW, 1)]),
    ("order_notify_outcome", [(_OUTCOME, _OUTCOME_NEW, 1)]),
]


def _live(name: str) -> str:
    bind = op.get_bind()
    defs = bind.execute(text("SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                             "JOIN pg_namespace n ON n.oid = p.pronamespace "
                             "WHERE n.nspname = 'public' AND p.proname = :n"), {"n": name}).scalars().all()
    if len(defs) != 1:
        raise RuntimeError(f"045: expected one function {name}, found {len(defs)}")
    return str(defs[0])


def _apply(name: str, swaps: list[tuple[str, str, int]], *, reverse: bool) -> None:
    body = _live(name)
    for old, new, times in swaps:
        a, b = (new, old) if reverse else (old, new)
        if body.count(a) != times:
            raise RuntimeError(f"045: {name}: anchor found {body.count(a)} times, expected {times}: {a[:60]!r}")
        body = body.replace(a, b)
    op.execute(body)


def upgrade() -> None:
    for name, swaps in GUARD:              # before anything writes the column
        _apply(name, swaps, reverse=False)
    for stmt in COLUMNS + TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("ALTER TABLE seller_gstin_lut ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    op.execute(floor.policy_sql("seller_gstin_lut"))
    for stmt in FUNCTIONS + TRIGGERS:
        op.execute(stmt)
    op.execute(SEED)
    for name, swaps in SWAPS:              # last: the functions they call exist now
        _apply(name, swaps, reverse=False)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for name, swaps in reversed(SWAPS):
        _apply(name, swaps, reverse=True)
    keys = "('export_tax_treatment', 'sample_pricing', 'sample_max_value')"
    op.execute(f"DELETE FROM activity_event WHERE kind = 'setting.changed' AND payload ->> 'key' IN {keys}")
    op.execute(f"DELETE FROM app_setting WHERE key IN {keys}")
    for sig in GRANTED:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP TABLE IF EXISTS seller_gstin_lut")
    for table in ("quotation", "sales_order"):
        for ck in ("tax_treatment", "export_treatment", "export_party", "lut"):
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_{ck}")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tax_treatment, "
                   f"DROP COLUMN IF EXISTS export_country, DROP COLUMN IF EXISTS lut_arn")
    op.execute("ALTER TABLE sales_order DROP CONSTRAINT IF EXISTS ck_sales_order_sample_pricing, "
               "DROP CONSTRAINT IF EXISTS ck_sales_order_free_sample")
    op.execute("ALTER TABLE sales_order DROP COLUMN IF EXISTS sample_pricing, "
               "DROP COLUMN IF EXISTS amended_from_gross")
    for name, swaps in reversed(GUARD):
        _apply(name, swaps, reverse=True)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
