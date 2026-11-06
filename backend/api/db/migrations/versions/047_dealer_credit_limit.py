"""047: the dealer credit limit at submit (FS-027).

- `dealer_credit_check`: one company setting in FS-036's `app_setting` (off, warn or
  block; default warn, GAP-242).
- `partner_credit_exposure()`: owed on the dealer's payable orders less its live
  receipts (plan review B-1). Allocations drop out, so money on an order later
  cancelled or rejected stays a credit, as on the dealer ledger.
- `order_credit_check()`: called by `order_submit` after its status UPDATE, so the
  benefits the schemes and rewards triggers apply are already counted. Locks the
  dealer row FOR NO KEY UPDATE: two submits for one dealer queue, while order
  inserts (KEY SHARE) do not. Raises CRDLM under block; sets the flag under warn.
- `sales_order.over_credit_limit`: null when unchecked, else the answer at submit;
  nulled by a trigger on any move to draft.
- `partner_credit_position()`: limit, exposure and available, for Accounts
  (payments global) or non-portal staff with partners.edit who see the dealer
  (plan review B-2); 42501 for anyone else.

Order of steps, as 046: the edit guard's allow-list first, then the column, then
the functions, then `order_submit`. Every live-text anchor count is asserted.

Revision ID: 047_dealer_credit_limit
Revises: 046_sale_counted_at
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "047_dealer_credit_limit"
down_revision: str | None = "046_sale_counted_at"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# 031's payable statuses and what the buyer owes; `o` is the order row
_PAYABLE = "('submitted', 'approved', 'partially_dispatched', 'dispatched', 'closed_short')"
_OWED = ("(o.total - COALESCE((SELECT sum(b.amount) FROM scheme_benefit b "
         "WHERE b.sales_order_id = o.id AND b.status = 'applied'), 0))")

COLUMNS = ["ALTER TABLE sales_order ADD COLUMN over_credit_limit boolean"]

FUNCTIONS = [
    f"""CREATE FUNCTION partner_credit_exposure(p_partner uuid) RETURNS numeric
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT COALESCE((SELECT sum({_OWED}) FROM sales_order o
                      WHERE o.partner_id = p_partner AND o.deleted_at IS NULL
                        AND o.status::text IN {_PAYABLE}), 0)
         - COALESCE((SELECT sum(p.amount) FROM payment p
                      WHERE p.partner_id = p_partner AND p.voided_at IS NULL), 0)
$fn$""",
    # Internal: only order_submit calls it, holding the order row and the counter.
    # Lock order: order, counter, dealer. No path locks a dealer row and then an
    # order (plan review Q2), so the new edge cannot deadlock.
    """CREATE FUNCTION order_credit_check(p_order uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_mode text; v_partner uuid; v_limit numeric; v_over boolean;
BEGIN
    -- a missing row reads as the default, explicitly (code review finding 4)
    v_mode := COALESCE(app_setting_text('dealer_credit_check'), 'warn');
    SELECT partner_id INTO v_partner FROM sales_order WHERE id = p_order;
    IF v_mode = 'off' OR v_partner IS NULL THEN
        RETURN;
    END IF;
    SELECT credit_limit INTO v_limit FROM channel_partner WHERE id = v_partner FOR NO KEY UPDATE;
    IF v_limit IS NULL THEN                -- no limit set: unchecked (GAP-240)
        RETURN;
    END IF;
    v_over := partner_credit_exposure(v_partner) > v_limit;
    IF v_over AND v_mode = 'block' THEN
        RAISE EXCEPTION 'This order would take the dealer over its credit limit.' USING ERRCODE = 'CRDLM';
    END IF;
    UPDATE sales_order SET over_credit_limit = v_over WHERE id = p_order;
END $fn$""",
    # One writer for the clearing: any move to draft (a rejection, an amendment)
    """CREATE FUNCTION sales_order_credit_flag_clear() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NEW.status::text = 'draft' THEN
        NEW.over_credit_limit := NULL;
    END IF;
    RETURN NEW;
END $fn$""",
    "CREATE TRIGGER trg_sales_order_credit_flag BEFORE UPDATE OF status ON sales_order "
    "FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status) EXECUTE FUNCTION sales_order_credit_flag_clear()",
    # Credit terms never reach a partner caller (FS-006, FS-020 rule 6): portal roles
    # hold partners.edit at partner_subtree, so the portal test comes first (B-2)
    """CREATE FUNCTION partner_credit_position(p_partner uuid)
RETURNS TABLE (credit_limit numeric, exposure numeric, available numeric)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_limit numeric; v_exposure numeric;
BEGIN
    IF NOT ((app_has_permission('payments', 'view') AND app_scope('payments') = 'global')
            OR (app_current_partner() IS NULL AND app_has_permission('partners', 'edit')
                AND partner_visible_to_caller(p_partner))) THEN
        RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
    END IF;
    SELECT cp.credit_limit INTO v_limit FROM channel_partner cp WHERE cp.id = p_partner;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'partner not found' USING ERRCODE = 'P0002';
    END IF;
    v_exposure := partner_credit_exposure(p_partner);
    RETURN QUERY SELECT v_limit, v_exposure, v_limit - v_exposure;
END $fn$""",
]

GRANTED = ["partner_credit_position(uuid)"]

SEED = """INSERT INTO app_setting (key, kind, value, allowed, min, max, description) VALUES
('dealer_credit_check', 'choice', '"warn"', '["off", "warn", "block"]', NULL, NULL,
 'On submitting a dealer''s order: ignore its credit limit, warn the approvers, or refuse the order.')
ON CONFLICT (key) DO NOTHING"""

# 046 put fully_dispatched_at last on both copies of the after-submit list
_COLS = "'fully_dispatched_at']"
_COLS_NEW = "'fully_dispatched_at', 'over_credit_limit']"
_SUBMIT = "RETURN create_approval_request('sales_order', p_order_id);"
_SUBMIT_NEW = "PERFORM order_credit_check(p_order_id);\n    " + _SUBMIT
GUARD = [("refuse_submitted_order_edit", [(_COLS, _COLS_NEW, 2)])]
SUBMIT = [("order_submit", [(_SUBMIT, _SUBMIT_NEW, 1)])]


def _live(name: str) -> str:
    bind = op.get_bind()
    defs = bind.execute(text("SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                             "JOIN pg_namespace n ON n.oid = p.pronamespace "
                             "WHERE n.nspname = 'public' AND p.proname = :n"), {"n": name}).scalars().all()
    if len(defs) != 1:
        raise RuntimeError(f"047: expected one function {name}, found {len(defs)}")
    return str(defs[0])


def _apply(name: str, swaps: list[tuple[str, str, int]], *, reverse: bool) -> None:
    body = _live(name)
    for old, new, times in swaps:
        a, b = (new, old) if reverse else (old, new)
        if body.count(a) != times:
            raise RuntimeError(f"047: {name}: anchor found {body.count(a)} times, expected {times}: {a[:60]!r}")
        body = body.replace(a, b)
    op.execute(body)


def upgrade() -> None:
    for name, swaps in GUARD:              # before anything writes the column
        _apply(name, swaps, reverse=False)
    for stmt in COLUMNS:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute(SEED)
    for name, swaps in SUBMIT:             # last: the function it calls exists now
        _apply(name, swaps, reverse=False)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for name, swaps in SUBMIT:
        _apply(name, swaps, reverse=True)
    op.execute("DELETE FROM activity_event WHERE kind = 'setting.changed' AND payload ->> 'key' = 'dealer_credit_check'")
    op.execute("DELETE FROM app_setting WHERE key = 'dealer_credit_check'")
    op.execute("DROP TRIGGER IF EXISTS trg_sales_order_credit_flag ON sales_order")
    for sig in ("partner_credit_position(uuid)", "sales_order_credit_flag_clear()",
                "order_credit_check(uuid)", "partner_credit_exposure(uuid)"):
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("ALTER TABLE sales_order DROP COLUMN IF EXISTS over_credit_limit")
    for name, swaps in reversed(GUARD):
        _apply(name, swaps, reverse=True)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
