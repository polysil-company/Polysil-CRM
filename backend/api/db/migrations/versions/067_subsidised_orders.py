"""067: subsidised sales orders, typed in, with the subsidy entered by hand (FS-054).

A subsidised order is priced from the price list like any direct order and carries
a subsidy block: the material amount (null means the order total, read at the time),
the subsidy, and the farmer's share (null means material less subsidy). It names one
or more leads; the first is the order's `lead_id` and routes it, so it cannot change.

The block and the lead links are read through the order and written only by
`order_subsidy_set`, a definer, as `order_quotations_claim` writes its links: each
lead needs `lead_visible`, which a row policy on the link table cannot ask cheaply.

`order_submit`'s dealer gate (045) gains `subsidised` as the second enforcer.

Revision ID: 067_subsidised_orders
Revises: 066_int_setting_whole
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision: str = "067_subsidised_orders"
down_revision: str | None = "066_int_setting_whole"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
MAX_LEADS = 50
# the stages a lead may be ordered in: domain.orders.LEAD_STAGES_ORDERABLE (a test holds them equal)
ORDERABLE = ("qualified", "quoted", "negotiation", "won")

_spec = importlib.util.spec_from_file_location(
    "consumer_floor_067", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

_STAGES = ", ".join(f"'{s}'" for s in ORDERABLE)

TABLES = [
    """CREATE TABLE order_subsidy (
    sales_order_id uuid PRIMARY KEY REFERENCES sales_order(id) ON DELETE CASCADE,
    material_amount numeric(14,2) CHECK (material_amount >= 0),
    subsidy_amount numeric(14,2) NOT NULL CHECK (subsidy_amount >= 0),
    farmer_payable numeric(14,2) CHECK (farmer_payable >= 0),
    updated_by uuid NOT NULL REFERENCES app_user(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_order_subsidy_subsidy CHECK (material_amount IS NULL OR subsidy_amount <= material_amount),
    CONSTRAINT ck_order_subsidy_payable CHECK (material_amount IS NULL OR farmer_payable IS NULL OR farmer_payable <= material_amount)
)""",
    """CREATE TABLE order_subsidy_lead (
    sales_order_id uuid NOT NULL REFERENCES sales_order(id) ON DELETE CASCADE,
    lead_id uuid NOT NULL REFERENCES lead(id),
    position smallint NOT NULL CHECK (position >= 1),
    PRIMARY KEY (sales_order_id, lead_id),
    CONSTRAINT uq_order_subsidy_lead_position UNIQUE (sales_order_id, position)
)""",
    "CREATE INDEX ix_order_subsidy_lead_lead ON order_subsidy_lead (lead_id)",
]

GRANTS: dict[str, str] = {"order_subsidy": "SELECT", "order_subsidy_lead": "SELECT"}

_O_VIEW = "(SELECT app_has_permission('sales_orders', 'view'))"
_PARENT = "EXISTS (SELECT 1 FROM sales_order o WHERE o.id = sales_order_id)"

HAND_POLICIES: list[tuple[str, str]] = [
    # read through the order, as order_quotation is; written by the definer only
    ("order_subsidy", f"CREATE POLICY order_subsidy_sel ON order_subsidy FOR SELECT USING (\n  {_PARENT}\n)"),
    ("order_subsidy", f"CREATE POLICY order_subsidy_res_perm ON order_subsidy AS RESTRICTIVE FOR SELECT USING (\n  {_O_VIEW}\n)"),
    ("order_subsidy_lead", f"CREATE POLICY order_subsidy_lead_sel ON order_subsidy_lead FOR SELECT USING (\n  {_PARENT}\n)"),
    ("order_subsidy_lead", f"CREATE POLICY order_subsidy_lead_res_perm ON order_subsidy_lead AS RESTRICTIVE FOR SELECT USING (\n  {_O_VIEW}\n)"),
]

FUNCTIONS = [
    f"""CREATE FUNCTION order_subsidy_set(p_order uuid, p_material numeric, p_subsidy numeric,
                                  p_payable numeric, p_leads uuid[]) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_order record; v_material numeric; v_me uuid := app_current_user_id(); l record; v_lead uuid; i int := 0;
BEGIN
    IF NOT app_has_permission('sales_orders', 'edit') OR NOT order_visible(p_order) THEN
        RAISE EXCEPTION 'not permitted on this order' USING ERRCODE = '42501';
    END IF;
    -- the same row lock as a lines edit, so a total cannot move under the cap check
    SELECT id, status::text AS status, order_type::text AS order_type, lead_id, total INTO v_order
      FROM sales_order WHERE id = p_order AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND OR v_order.status <> 'draft' THEN
        RAISE EXCEPTION 'only a draft takes a subsidy' USING ERRCODE = 'ORDNS';
    END IF;
    IF v_order.order_type <> 'subsidised' THEN
        RAISE EXCEPTION 'only a subsidised order takes a subsidy' USING ERRCODE = 'OSBTY';
    END IF;
    IF cardinality(p_leads) IS NULL OR cardinality(p_leads) < 1 OR cardinality(p_leads) > {MAX_LEADS}
       OR (SELECT count(DISTINCT x) FROM unnest(p_leads) x) <> cardinality(p_leads) THEN
        RAISE EXCEPTION 'one to {MAX_LEADS} different leads' USING ERRCODE = 'OSBLD';
    END IF;
    IF v_order.lead_id IS DISTINCT FROM p_leads[1] THEN
        RAISE EXCEPTION 'the first lead routes the order and cannot change' USING ERRCODE = 'OSBFL';
    END IF;
    FOR l IN SELECT x.id AS id, ld.stage::text AS stage, ld.merged_into_id, ld.deleted_at
               FROM unnest(p_leads) AS x(id) LEFT JOIN lead ld ON ld.id = x.id LOOP
        IF l.deleted_at IS NOT NULL OR l.stage IS NULL OR NOT lead_visible(l.id) THEN
            RAISE EXCEPTION 'lead % not visible', l.id USING ERRCODE = 'OSBLV';
        END IF;
        IF l.stage NOT IN ({_STAGES}) OR l.merged_into_id IS NOT NULL THEN
            RAISE EXCEPTION 'lead % is %', l.id, l.stage USING ERRCODE = 'OSBLO';
        END IF;
    END LOOP;
    v_material := coalesce(p_material, v_order.total);
    IF p_subsidy > v_material THEN
        RAISE EXCEPTION 'the subsidy is above the material' USING ERRCODE = 'OSBAM';
    END IF;
    IF p_payable > v_material THEN
        RAISE EXCEPTION 'the farmer payable is above the material' USING ERRCODE = 'OSBPM';
    END IF;
    INSERT INTO order_subsidy (sales_order_id, material_amount, subsidy_amount, farmer_payable, updated_by)
    VALUES (p_order, p_material, p_subsidy, p_payable, v_me)
    ON CONFLICT (sales_order_id) DO UPDATE SET material_amount = EXCLUDED.material_amount,
        subsidy_amount = EXCLUDED.subsidy_amount, farmer_payable = EXCLUDED.farmer_payable,
        updated_by = EXCLUDED.updated_by, updated_at = now();
    DELETE FROM order_subsidy_lead WHERE sales_order_id = p_order;
    FOREACH v_lead IN ARRAY p_leads LOOP
        i := i + 1;
        INSERT INTO order_subsidy_lead (sales_order_id, lead_id, position) VALUES (p_order, v_lead, i);
        -- no money in the payload (FS-005 rule 17): the timeline is wider than the order
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('sales_order', p_order, v_lead, 'order.subsidy_set', v_me,
                jsonb_build_object('leads', cardinality(p_leads), 'position', i));
    END LOOP;
END
$fn$""",
]

GRANTED = ["order_subsidy_set(uuid, numeric, numeric, numeric, uuid[])"]

# 045's dealer gate on submit, by live text as 045 wrote it
_GATE = "IF v_order.order_type IN ('export', 'sample') AND app_current_partner() IS NOT NULL THEN"
_GATE_NEW = "IF v_order.order_type IN ('export', 'sample', 'subsidised') AND app_current_partner() IS NOT NULL THEN"


def _swap_submit(old: str, new: str) -> None:
    bind = op.get_bind()
    body = str(bind.execute(text("SELECT pg_get_functiondef('order_submit(uuid)'::regprocedure)")).scalar_one())
    if body.count(old) != 1:
        raise RuntimeError(f"067: order_submit gate found {body.count(old)} times")
    op.execute(body.replace(old, new))


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for table in GRANTS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for table in GRANTS:
        op.execute(floor.policy_sql(table))
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    _swap_submit(_GATE, _GATE_NEW)


def downgrade() -> None:
    _swap_submit(_GATE_NEW, _GATE)
    for sig in GRANTED:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DELETE FROM activity_event WHERE kind = 'order.subsidy_set'")
    op.execute("DROP TABLE IF EXISTS order_subsidy_lead")
    op.execute("DROP TABLE IF EXISTS order_subsidy")
    op.execute("UPDATE sales_order SET deleted_at = now() WHERE order_type = 'subsidised' AND deleted_at IS NULL")
