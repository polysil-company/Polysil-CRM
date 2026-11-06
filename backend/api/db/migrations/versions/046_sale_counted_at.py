"""046: when an order counts as a sale (FS-026).

- `sale_counted_at`: one company setting in FS-036's `app_setting` (submission,
  approval, dispatch or payment; default approval). The row carries its allowed
  values, so `app_setting_check()` refuses anything else.
- `sales_order.fully_dispatched_at`: set by a BEFORE UPDATE OF status trigger when
  the order reaches dispatched or closed short (the latest live dispatch time),
  null on any other status. The dispatch definers write the dispatch row before
  the order status, so the trigger sees it. Backfilled.
- `order_paid_at()`: the first receipt day by which live allocations cover what
  is owed (plan review B-4). A day, not an amount, for anyone who can see the
  order (rule 11).

`refuse_submitted_order_edit` compares the whole row against an allow-list, so it
is patched from its live text first (plan review B-1), the way 041 patches it.

Revision ID: 046_sale_counted_at
Revises: 042_dealer_tasks
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "046_sale_counted_at"
down_revision: str | None = "042_dealer_tasks"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# the statuses an order may be paid in (031 _PAYABLE)
_PAYABLE = "('submitted', 'approved', 'partially_dispatched', 'dispatched', 'closed_short')"

COLUMNS = [
    "ALTER TABLE sales_order ADD COLUMN fully_dispatched_at timestamptz",
    "ALTER TABLE sales_order ADD CONSTRAINT ck_sales_order_fully_dispatched "
    "CHECK (status IN ('dispatched', 'closed_short') OR fully_dispatched_at IS NULL) NOT VALID",
]

FUNCTIONS = [
    # The latest live dispatch, on reaching dispatched or closed short; null otherwise.
    # A closed-short order with nothing shipped keeps null, so no mode counts it.
    """CREATE FUNCTION sales_order_fully_dispatched() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NEW.status::text IN ('dispatched', 'closed_short') THEN
        NEW.fully_dispatched_at := (SELECT max(d.dispatched_at) FROM dispatch d
                                     WHERE d.sales_order_id = NEW.id AND d.voided_at IS NULL);
    ELSE
        NEW.fully_dispatched_at := NULL;
    END IF;
    RETURN NEW;
END $fn$""",
    "CREATE TRIGGER trg_sales_order_fully_dispatched BEFORE UPDATE OF status ON sales_order "
    "FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status) EXECUTE FUNCTION sales_order_fully_dispatched()",
    # The least receipt day d such that live allocations on live receipts dated on or
    # before d reach payable; independent of the order the allocations were entered
    # in. Null for an order the caller cannot see, one not in a payable status, or
    # one owing nothing (plan review B-2, edge 7).
    f"""CREATE FUNCTION order_paid_at(p_order uuid) RETURNS timestamptz
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    o sales_order%ROWTYPE; v_owed numeric; v_day date;
BEGIN
    IF NOT order_visible(p_order) THEN
        RETURN NULL;
    END IF;
    SELECT * INTO o FROM sales_order WHERE id = p_order;
    IF NOT FOUND OR o.deleted_at IS NOT NULL OR o.status::text NOT IN {_PAYABLE} THEN
        RETURN NULL;
    END IF;
    v_owed := o.total - COALESCE((SELECT sum(b.amount) FROM scheme_benefit b
                                   WHERE b.sales_order_id = o.id AND b.status = 'applied'), 0);
    IF v_owed <= 0 THEN
        RETURN NULL;
    END IF;
    SELECT d INTO v_day FROM (
        SELECT p.received_on AS d,
               sum(sum(a.amount)) OVER (ORDER BY p.received_on) AS running
          FROM payment_allocation a JOIN payment p ON p.id = a.payment_id
         WHERE a.sales_order_id = o.id AND NOT a.voided AND p.voided_at IS NULL
         GROUP BY p.received_on) t
     WHERE running >= v_owed ORDER BY d LIMIT 1;
    RETURN CASE WHEN v_day IS NULL THEN NULL
                ELSE v_day::timestamp AT TIME ZONE 'Asia/Kolkata' END;
END $fn$""",
]

GRANTED = ["order_paid_at(uuid)"]

# the backfill, run while the trigger cannot fire (it is BEFORE UPDATE OF status)
BACKFILL = """UPDATE sales_order o SET fully_dispatched_at = d.at
  FROM (SELECT sales_order_id, max(dispatched_at) AS at FROM dispatch
         WHERE voided_at IS NULL GROUP BY sales_order_id) d
 WHERE d.sales_order_id = o.id AND o.status::text IN ('dispatched', 'closed_short')"""

INDEXES = [
    "CREATE INDEX ix_sales_order_fully_dispatched ON sales_order (fully_dispatched_at) "
    "WHERE fully_dispatched_at IS NOT NULL",
    "CREATE INDEX ix_sales_order_approved_at ON sales_order (approved_at) WHERE approved_at IS NOT NULL",
]

SEED = """INSERT INTO app_setting (key, kind, value, allowed, min, max, description) VALUES
('sale_counted_at', 'choice', '"approval"', '["submission", "approval", "dispatch", "payment"]', NULL, NULL,
 'When an order counts as a sale in the reports and targets: when it is submitted, approved, fully dispatched or paid in full. Changing it restates past periods.')
ON CONFLICT (key) DO NOTHING"""

# 041 put amend_reason last on both copies of the after-submit list
_COLS = "'amend_reason']"
_COLS_NEW = "'amend_reason', 'fully_dispatched_at']"
PATCHES: list[tuple[str, list[tuple[str, str, int]]]] = [
    ("refuse_submitted_order_edit", [(_COLS, _COLS_NEW, 2)]),
]


def _live(name: str) -> str:
    bind = op.get_bind()
    defs = bind.execute(text("SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                             "JOIN pg_namespace n ON n.oid = p.pronamespace "
                             "WHERE n.nspname = 'public' AND p.proname = :n"), {"n": name}).scalars().all()
    if len(defs) != 1:
        raise RuntimeError(f"046: expected one function {name}, found {len(defs)}")
    return str(defs[0])


def _apply(name: str, swaps: list[tuple[str, str, int]], *, reverse: bool) -> None:
    body = _live(name)
    for old, new, times in swaps:
        a, b = (new, old) if reverse else (old, new)
        if body.count(a) != times:
            raise RuntimeError(f"046: {name}: anchor found {body.count(a)} times, expected {times}: {a[:60]!r}")
        body = body.replace(a, b)
    op.execute(body)


def upgrade() -> None:
    for name, swaps in PATCHES:            # before the backfill writes the column (B-1)
        _apply(name, swaps, reverse=False)
    for stmt in COLUMNS:
        op.execute(stmt)
    op.execute(BACKFILL)
    op.execute("ALTER TABLE sales_order VALIDATE CONSTRAINT ck_sales_order_fully_dispatched")
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for stmt in INDEXES:
        op.execute(stmt)
    op.execute(SEED)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DELETE FROM activity_event WHERE kind = 'setting.changed' AND payload ->> 'key' = 'sale_counted_at'")
    op.execute("DELETE FROM app_setting WHERE key = 'sale_counted_at'")
    for sig in GRANTED:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP TRIGGER IF EXISTS trg_sales_order_fully_dispatched ON sales_order")
    op.execute("DROP FUNCTION IF EXISTS sales_order_fully_dispatched()")
    for name in ("ix_sales_order_approved_at", "ix_sales_order_fully_dispatched"):
        op.execute(f"DROP INDEX IF EXISTS {name}")
    op.execute("ALTER TABLE sales_order DROP CONSTRAINT IF EXISTS ck_sales_order_fully_dispatched")
    op.execute("ALTER TABLE sales_order DROP COLUMN IF EXISTS fully_dispatched_at")
    for name, swaps in reversed(PATCHES):
        _apply(name, swaps, reverse=True)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
