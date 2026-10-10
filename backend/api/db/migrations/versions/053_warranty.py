"""053: warranty tracking (FS-046).

- `warranty_term`: the warranty period per product category from a date (null
  category = the default), effective-dated as `complaint_sla_policy` (CLAUDE.md
  rule 10). 0 months means no warranty. Read by any signed-in caller; written only
  by `warranty_term_set()`, from tomorrow on, so no recorded dispatch is restated.
- `warranty_end()`: the last covered day, the authoritative twin of
  `api/domain/warranty.end_date`.
- `warranty_months()`: the term in force for a product on a day.
- `complaint_warranty()`: each complaint line's warranty, for whoever sees the
  complaint (edge EC-1: a QC manager cannot read the order, and must see the same
  dates as the owner). Dates and months only.

Revision ID: 053_warranty
Revises: 051_ratings
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "053_warranty"
down_revision: str | None = "051_ratings"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# the consumer floor (052): every RLS table carries it
_spec = importlib.util.spec_from_file_location(
    "consumer_floor_053", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

TABLES = [
    """CREATE TABLE warranty_term (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_category_id uuid REFERENCES product_category(id),
    months int NOT NULL CHECK (months BETWEEN 0 AND 120),
    effective_from date NOT NULL,
    effective_to date,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES app_user(id),
    CONSTRAINT ck_warranty_term_dates CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_warranty_term_default EXCLUDE USING gist (
        daterange(effective_from, effective_to, '[)') WITH &&)
        WHERE (product_category_id IS NULL),
    CONSTRAINT ex_warranty_term_category EXCLUDE USING gist (
        product_category_id WITH =, daterange(effective_from, effective_to, '[)') WITH &&)
        WHERE (product_category_id IS NOT NULL)
)""",
]

INDEXES = [
    "CREATE INDEX ix_warranty_term_category ON warranty_term (product_category_id)",
]

GRANTS: dict[str, str] = {"warranty_term": "SELECT"}

HAND_POLICIES: list[tuple[str, str]] = [
    ("warranty_term", "CREATE POLICY warranty_term_sel ON warranty_term FOR SELECT "
                      "USING ((SELECT app_current_user_id()) IS NOT NULL)"),
]

# GAP-275: the stand-in, 12 months for every category, from before any order
SEED = "INSERT INTO warranty_term (months, effective_from) VALUES (12, DATE '2020-01-01')"

TRIGGERS = [
    # plan review m-1: the close UPDATE on effective_to leaves a record
    "CREATE TRIGGER trg_warranty_term_audit AFTER INSERT OR UPDATE OR DELETE ON warranty_term "
    "FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

FUNCTIONS = [
    # FS-046 rule 3. Postgres clamps `date + interval 'n months'` to the month end;
    # a clamped end is itself the last day, otherwise the day before.
    """CREATE FUNCTION warranty_end(p_start date, p_months integer) RETURNS date
LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp AS $fn$
    SELECT CASE
        WHEN p_start IS NULL OR p_months IS NULL OR p_months = 0 THEN NULL
        WHEN extract(day FROM (p_start + make_interval(months => p_months))) < extract(day FROM p_start)
            THEN (p_start + make_interval(months => p_months))::date
        ELSE (p_start + make_interval(months => p_months))::date - 1
    END
$fn$""",
    # the category's own term in force on the day, else the default's, else null
    """CREATE FUNCTION warranty_months(p_product uuid, p_day date) RETURNS integer
LANGUAGE sql STABLE SET search_path = public, pg_temp AS $fn$
    SELECT t.months FROM warranty_term t
      LEFT JOIN product p ON p.id = p_product
     WHERE (t.product_category_id = p.product_category_id OR t.product_category_id IS NULL)
       AND t.effective_from <= p_day AND (t.effective_to IS NULL OR t.effective_to > p_day)
     ORDER BY t.product_category_id IS NULL
     LIMIT 1
$fn$""",
    """CREATE FUNCTION warranty_term_set(p_category uuid, p_months integer, p_from date) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_next date; v_id uuid;
BEGIN
    IF NOT app_has_permission('masters', 'edit') THEN
        RAISE EXCEPTION 'masters.edit required' USING ERRCODE = '42501';
    END IF;
    -- edge EC-3: a term from today would restate today's dispatches
    IF p_from <= (now() AT TIME ZONE 'Asia/Kolkata')::date THEN
        RAISE EXCEPTION 'a term starts tomorrow or later' USING ERRCODE = 'WRTPA';
    END IF;
    IF p_category IS NOT NULL AND NOT EXISTS (SELECT 1 FROM product_category WHERE id = p_category) THEN
        RAISE EXCEPTION 'no such category' USING ERRCODE = 'WRTNC';
    END IF;
    PERFORM pg_advisory_xact_lock(5, hashtext('warranty_term'));
    IF EXISTS (SELECT 1 FROM warranty_term WHERE product_category_id IS NOT DISTINCT FROM p_category
                 AND effective_from = p_from) THEN
        RAISE EXCEPTION 'a term already starts that day' USING ERRCODE = 'WRTEX';
    END IF;
    SELECT min(effective_from) INTO v_next FROM warranty_term
     WHERE product_category_id IS NOT DISTINCT FROM p_category AND effective_from > p_from;
    UPDATE warranty_term SET effective_to = p_from
     WHERE product_category_id IS NOT DISTINCT FROM p_category
       AND effective_from < p_from AND (effective_to IS NULL OR effective_to > p_from);
    INSERT INTO warranty_term (product_category_id, months, effective_from, effective_to, created_by)
    VALUES (p_category, p_months, p_from, v_next, app_current_user_id())
    RETURNING id INTO v_id;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('warranty_term', v_id, 'warranty_term.set', app_current_user_id(),
            jsonb_build_object('product_category_id', p_category, 'months', p_months, 'effective_from', p_from));
    RETURN v_id;
END $fn$""",
    # Edge EC-1: whoever sees the complaint gets the same dates, whether or not they
    # can read its order. Rule 10: the latest-ending live dispatch of the product on
    # the linked order, across every line of it; else the complaint's supply date.
    """CREATE FUNCTION complaint_warranty(p_complaint uuid)
RETURNS TABLE (line_id uuid, product_id uuid, start_day date, months integer, end_day date,
               basis text, raised_on date)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT complaint_visible(p_complaint) THEN
        RETURN;
    END IF;
    RETURN QUERY
    WITH c AS (
        SELECT cm.id, cm.sales_order_id, cm.supply_date,
               COALESCE((cm.first_submitted_at AT TIME ZONE 'Asia/Kolkata')::date,
                        (now() AT TIME ZONE 'Asia/Kolkata')::date) AS raised_on
          FROM complaint cm WHERE cm.id = p_complaint
    ), shipped AS (
        SELECT ol.product_id,
               COALESCE(d.dc_date, (d.dispatched_at AT TIME ZONE 'Asia/Kolkata')::date) AS start_day
          FROM c JOIN dispatch d ON d.sales_order_id = c.sales_order_id AND d.voided_at IS NULL
          JOIN dispatch_line dl ON dl.dispatch_id = d.id
          JOIN order_line ol ON ol.id = dl.order_line_id
    ), dated AS (
        SELECT s.product_id, s.start_day, warranty_months(s.product_id, s.start_day) AS months
          FROM shipped s
    )
    SELECT cl.id, cl.product_id, pick.start_day, pick.months, warranty_end(pick.start_day, pick.months),
           pick.basis, c.raised_on
      FROM c JOIN complaint_line cl ON cl.complaint_id = c.id
      LEFT JOIN LATERAL (
          SELECT x.start_day, x.months, x.basis FROM (
              SELECT dt.start_day, dt.months, 'dispatch'::text AS basis, 0 AS rank
                FROM dated dt WHERE dt.product_id = cl.product_id
              UNION ALL
              SELECT c.supply_date, warranty_months(cl.product_id, c.supply_date), 'supply_date', 1
               WHERE c.supply_date IS NOT NULL
          ) x
          ORDER BY x.rank, warranty_end(x.start_day, x.months) DESC NULLS LAST, x.start_day DESC
          LIMIT 1
      ) pick ON true
     ORDER BY cl.line_no;
END $fn$""",
]

GRANTED = ["warranty_end(date, integer)", "warranty_months(uuid, date)",
           "warranty_term_set(uuid, integer, date)", "complaint_warranty(uuid)"]


def upgrade() -> None:
    for stmt in TABLES + INDEXES:
        op.execute(stmt)
    op.execute(SEED)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("ALTER TABLE warranty_term ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    op.execute(floor.policy_sql("warranty_term"))
    for stmt in TRIGGERS + FUNCTIONS:
        op.execute(stmt)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for sig in reversed(GRANTED):
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DELETE FROM activity_event WHERE kind = 'warranty_term.set'")
    op.execute("DROP TABLE IF EXISTS warranty_term")
