"""068: a product's category is dated, so a re-categorised product keeps its past
warranties (ISS-120, GAP-281).

`warranty_months()` read the product's current category: moving a product from a
24-month to a 12-month category showed 12 months on dispatches made under 24
(CLAUDE.md rule 10). A trigger now records each category a product takes, from the
next IST day (as `warranty_term_set` dates a term, edge EC-3), and the function
reads the category in force on the day asked. Before a product's first recorded
day, its first category applies.

The history is read only by `warranty_months()`, now a definer. No grants.

Revision ID: 068_product_category_history
Revises: 067_subsidised_orders
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "068_product_category_history"
down_revision: str | None = "067_subsidised_orders"
branch_labels = None
depends_on = None

_spec = importlib.util.spec_from_file_location(
    "consumer_floor_068", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

TABLE = """CREATE TABLE product_category_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id uuid NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    product_category_id uuid REFERENCES product_category(id),
    from_day date NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
)"""
INDEX = "CREATE INDEX ix_product_category_history_product ON product_category_history (product_id, from_day DESC, id DESC)"

# every product as it stands, from long before any order
BACKFILL = ("INSERT INTO product_category_history (product_id, product_category_id, from_day) "
            "SELECT id, product_category_id, DATE '2000-01-01' FROM product")

TRIGGER_FN = """CREATE FUNCTION product_category_record() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.product_category_id IS DISTINCT FROM OLD.product_category_id THEN
        -- from the next IST day: today's dispatches keep the category they shipped under
        INSERT INTO product_category_history (product_id, product_category_id, from_day)
        VALUES (NEW.id, NEW.product_category_id, (now() AT TIME ZONE 'Asia/Kolkata')::date + 1);
    END IF;
    RETURN NEW;
END
$fn$"""
TRIGGER = ("CREATE TRIGGER trg_product_category_record AFTER INSERT OR UPDATE OF product_category_id "
           "ON product FOR EACH ROW EXECUTE FUNCTION product_category_record()")

MONTHS = """CREATE OR REPLACE FUNCTION warranty_months(p_product uuid, p_day date) RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    -- ISS-120: the category in force on the day; before the first record, the first one
    WITH cat AS (
        SELECT coalesce(
            (SELECT h.product_category_id FROM product_category_history h
              WHERE h.product_id = p_product AND h.from_day <= p_day
              ORDER BY h.from_day DESC, h.id DESC LIMIT 1),
            (SELECT h.product_category_id FROM product_category_history h
              WHERE h.product_id = p_product ORDER BY h.from_day, h.id LIMIT 1),
            (SELECT p.product_category_id FROM product p WHERE p.id = p_product)) AS id
    )
    SELECT t.months FROM warranty_term t, cat
     WHERE (t.product_category_id = cat.id OR t.product_category_id IS NULL)
       AND t.effective_from <= p_day AND (t.effective_to IS NULL OR t.effective_to > p_day)
     ORDER BY t.product_category_id IS NULL
     LIMIT 1
$fn$"""

MONTHS_BEFORE = """CREATE OR REPLACE FUNCTION warranty_months(p_product uuid, p_day date) RETURNS integer
LANGUAGE sql STABLE SET search_path = public, pg_temp AS $fn$
    SELECT t.months FROM warranty_term t
      LEFT JOIN product p ON p.id = p_product
     WHERE (t.product_category_id = p.product_category_id OR t.product_category_id IS NULL)
       AND t.effective_from <= p_day AND (t.effective_to IS NULL OR t.effective_to > p_day)
     ORDER BY t.product_category_id IS NULL
     LIMIT 1
$fn$"""


def upgrade() -> None:
    op.execute(TABLE)
    op.execute(INDEX)
    op.execute("ALTER TABLE product_category_history ENABLE ROW LEVEL SECURITY")
    op.execute(floor.policy_sql("product_category_history"))
    op.execute(BACKFILL)
    op.execute(TRIGGER_FN)
    op.execute("REVOKE EXECUTE ON FUNCTION product_category_record() FROM PUBLIC")
    op.execute(TRIGGER)
    op.execute(MONTHS)


def downgrade() -> None:
    op.execute(MONTHS_BEFORE)
    op.execute("DROP TRIGGER IF EXISTS trg_product_category_record ON product")
    op.execute("DROP FUNCTION IF EXISTS product_category_record()")
    op.execute("DROP TABLE IF EXISTS product_category_history")
