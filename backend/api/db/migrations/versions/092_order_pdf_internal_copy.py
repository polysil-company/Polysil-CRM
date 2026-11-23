"""092: the order PDF gets an internal copy with the approval trail (FS-091).

The customer copy stays as FS-012 rule 9 has it: no names, no remarks. The worker
renders a second, staff-only copy beside it.

* `sales_order.pdf_internal_key`, `pdf_internal_attempts`, `pdf_internal_error`:
  the internal copy's object and its own retry count. Cleared on an amend.
* `order_render_claim()` has two branches.
  1. As before: a pending order, or a lapsed `rendering` lease. Mode `both`: the
     worker renders both copies, and the order is ready only with both.
  2. Only when branch 1 finds nothing: a `ready` order with no internal copy (one
     approved before 092, or whose internal render failed). Mode `internal`. The
     lease is taken with `pdf_state` left at `ready`, so the customer copy and its
     link do not change (edge case EC-1). Fresh approvals go first (EC-4).
  The document gains a top-level `internal` key: the order's remarks, the amend
  reason and count, and every approval round with its amount, steps, names and
  remarks. `order` drops `amend_reason` and `amended_from_total` too (EC-6).
* `order_render_done(id, lease, key, internal_key)`: `key` is null in mode
  `internal`. In mode `both` the internal key may be null: the internal copy failed,
  the customer copy is published anyway, and branch 2 retries the internal one (plan
  review R-4). The three-argument function stays for one release as a shim, for a
  worker older than this migration (EC-3).
* A partial index finds the orders branch 2 owes (plan review R-6).
* `order_render_failed()` charges the internal copy's attempts in mode `internal`
  and leaves the customer copy alone.
* `refuse_submitted_order_edit()` lets the three new columns change after submit.

`order_render_claim`, `order_render_failed` and the shim are written whole; the
guard and `order_amend` are patched by their live text, as 064 and 091 do.

Revision ID: 092_order_pdf_internal_copy
Revises: 091_reward_points_cap
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op
from sqlalchemy import text

revision: str = "092_order_pdf_internal_copy"
down_revision: str | None = "091_reward_points_cap"
branch_labels = None
depends_on = None

MAX_RENDER_ATTEMPTS = 5

COLUMNS = ("ALTER TABLE sales_order ADD COLUMN pdf_internal_key text, "
           "ADD COLUMN pdf_internal_attempts int NOT NULL DEFAULT 0, "
           "ADD COLUMN pdf_internal_error text")

GUARD = "refuse_submitted_order_edit()"
GUARD_OLD = "'pdf_key', 'pdf_error'"
GUARD_NEW = ("'pdf_key', 'pdf_internal_key', 'pdf_internal_attempts', 'pdf_internal_error', "
             "'pdf_error'")

AMEND = "order_amend(uuid, text, text)"
AMEND_OLD = "pdf_state = NULL, pdf_key = NULL, pdf_error = NULL,"
AMEND_NEW = ("pdf_state = NULL, pdf_key = NULL, pdf_error = NULL,\n"
             "           pdf_internal_key = NULL, pdf_internal_attempts = 0, "
             "pdf_internal_error = NULL,")

# the staff-only part of the render document (FS-091 §5)
_INTERNAL = """jsonb_build_object(
            'remarks', o.remarks, 'amend_reason', o.amend_reason, 'amend_count', o.amend_count,
            'approvals', (
                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                           'round', q.rn, 'status', q.status::text, 'amount', q.amount::text,
                           'requested_at', q.created_at, 'requested_by', ru.full_name::text,
                           'request_remark', q.remark, 'decided_at', q.decided_at,
                           'steps', (
                               SELECT COALESCE(jsonb_agg(jsonb_build_object(
                                          'seq', s.seq, 'role', r.name,
                                          'decided_role', CASE WHEN dr.id <> r.id THEN dr.name END,
                                          'decision', s.decision::text, 'by', u.full_name::text,
                                          'decided_at', s.decided_at, 'remark', s.remark)
                                          ORDER BY s.seq), '[]'::jsonb)
                                 FROM approval_step s
                                 JOIN role r ON r.id = s.approver_role_id
                                 LEFT JOIN role dr ON dr.id = s.decided_role_id
                                 LEFT JOIN app_user u ON u.id = s.approver_user_id
                                WHERE s.request_id = q.id))
                           ORDER BY q.rn), '[]'::jsonb)
                  FROM (SELECT a.*, row_number() OVER (
                                ORDER BY a.created_at, a.decided_at NULLS LAST, a.id) AS rn
                          FROM approval_request a
                         WHERE a.doc_type = 'sales_order' AND a.entity_id = o.id) q
                  LEFT JOIN app_user ru ON ru.id = q.requested_by))"""

CLAIM = f"""CREATE OR REPLACE FUNCTION order_render_claim(p_lease interval) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE o sales_order%ROWTYPE; v_token uuid; v_mode text := 'both';
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal renders' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO o FROM sales_order
     WHERE deleted_at IS NULL AND status <> 'cancelled'
       AND ((pdf_state = 'pending' AND COALESCE(pdf_next_attempt_at, '-infinity') <= now())
            OR (pdf_state = 'rendering' AND pdf_lease_until < now()))
     ORDER BY pdf_next_attempt_at NULLS FIRST
     LIMIT 1
       FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN
        -- FS-091: an internal copy still owed on a ready order; the customer copy
        -- and pdf_state stay as they are
        SELECT * INTO o FROM sales_order
         WHERE deleted_at IS NULL AND status <> 'cancelled'
           AND pdf_state = 'ready' AND pdf_internal_key IS NULL
           AND pdf_internal_attempts < {MAX_RENDER_ATTEMPTS}
           AND COALESCE(pdf_lease_until, '-infinity') < now()
           AND COALESCE(pdf_next_attempt_at, '-infinity') <= now()
         ORDER BY approved_at DESC NULLS LAST, id
         LIMIT 1
           FOR UPDATE SKIP LOCKED;
        IF NOT FOUND THEN
            RETURN NULL;
        END IF;
        v_mode := 'internal';
    ELSIF o.pdf_attempts >= {MAX_RENDER_ATTEMPTS} THEN
        UPDATE sales_order SET pdf_state = 'failed', pdf_lease_until = NULL, pdf_lease = NULL,
               pdf_error = 'render abandoned after 5 attempts: '
                           || COALESCE(pdf_error, 'the worker died on the last one')
         WHERE id = o.id;
        RETURN NULL;
    END IF;
    v_token := gen_random_uuid();
    IF v_mode = 'both' THEN
        UPDATE sales_order
           SET pdf_state = 'rendering', pdf_lease_until = now() + p_lease, pdf_lease = v_token,
               pdf_attempts = pdf_attempts + 1
         WHERE id = o.id;
    ELSE
        UPDATE sales_order
           SET pdf_lease_until = now() + p_lease, pdf_lease = v_token,
               pdf_internal_attempts = pdf_internal_attempts + 1
         WHERE id = o.id;
    END IF;
    RETURN jsonb_build_object(
        'lease_token', v_token, 'mode', v_mode,
        'attempt', CASE v_mode WHEN 'both' THEN o.pdf_attempts ELSE o.pdf_internal_attempts END + 1,
        'order', to_jsonb(o) - ARRAY['pdf_lease', 'remarks', 'cancel_remark', 'close_remark',
                                     'amend_reason', 'amended_from_total', 'pdf_internal_error']
                 || jsonb_build_object(
                        'status', o.status::text, 'order_type', o.order_type::text,
                        'payment_terms', o.payment_terms::text,
                        'place_of_supply', (SELECT t.name FROM territory t
                                             WHERE t.id = COALESCE(o.place_of_supply_state_id,
                                                                   o.place_of_supply_territory_id))),
        'lines', (SELECT COALESCE(jsonb_agg(to_jsonb(l) ORDER BY l.line_no), '[]'::jsonb)
                    FROM order_line l WHERE l.sales_order_id = o.id),
        -- FS-091: staff-only, for the internal copy; never inside 'order'
        'internal', {_INTERNAL});
END $fn$"""

DONE_4 = "order_render_done(uuid, uuid, text, text)"
DONE_4_SQL = """CREATE FUNCTION order_render_done(p_id uuid, p_lease_token uuid, p_key text,
                                  p_internal_key text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal renders' USING ERRCODE = '42501';
    END IF;
    IF p_key IS NULL AND p_internal_key IS NULL THEN
        RAISE EXCEPTION 'nothing was rendered' USING ERRCODE = '22004';
    END IF;
    -- mode both: a key, from rendering; the internal key may be null, and branch 2
    -- owes it. Mode internal: no key, the order stays ready.
    UPDATE sales_order
       SET pdf_state = 'ready', pdf_key = COALESCE(p_key, pdf_key),
           pdf_internal_key = p_internal_key, pdf_internal_error = NULL,
           pdf_lease_until = NULL, pdf_lease = NULL,
           pdf_error = CASE WHEN p_key IS NULL THEN pdf_error END
     WHERE id = p_id AND pdf_lease = p_lease_token
       AND ((p_key IS NOT NULL AND pdf_state = 'rendering')
            OR (p_key IS NULL AND pdf_state = 'ready'));
    RETURN FOUND;
END $fn$"""

# EC-3: an old worker's done during the deploy. Nothing is published; the lease goes
# back uncharged, and a new worker renders both copies. GAP-601: drop it in a later
# migration.
DONE_3 = "order_render_done(uuid, uuid, text)"
DONE_3_SHIM = """CREATE OR REPLACE FUNCTION order_render_done(p_id uuid, p_lease_token uuid,
                                             p_key text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal renders' USING ERRCODE = '42501';
    END IF;
    UPDATE sales_order
       SET pdf_state = CASE WHEN pdf_state = 'rendering' THEN 'pending' ELSE pdf_state END,
           pdf_attempts = CASE WHEN pdf_state = 'rendering' THEN greatest(0, pdf_attempts - 1)
                               ELSE pdf_attempts END,
           pdf_internal_attempts = CASE WHEN pdf_state = 'ready'
                                        THEN greatest(0, pdf_internal_attempts - 1)
                                        ELSE pdf_internal_attempts END,
           pdf_next_attempt_at = now(), pdf_lease_until = NULL, pdf_lease = NULL
     WHERE id = p_id AND pdf_lease = p_lease_token;
    RETURN false;
END $fn$"""

FAILED = f"""CREATE OR REPLACE FUNCTION order_render_failed(p_id uuid, p_lease_token uuid,
                                               p_error text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_state text; v_attempts int; v_internal int;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal renders' USING ERRCODE = '42501';
    END IF;
    SELECT pdf_state, pdf_attempts, pdf_internal_attempts INTO v_state, v_attempts, v_internal
      FROM sales_order
     WHERE id = p_id AND pdf_state IN ('rendering', 'ready') AND pdf_lease = p_lease_token
       FOR UPDATE;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    IF v_state = 'ready' THEN
        -- FS-091 mode internal: only the internal copy failed; the customer copy stands
        UPDATE sales_order
           SET pdf_internal_error = left(p_error, 2000), pdf_lease_until = NULL, pdf_lease = NULL,
               pdf_next_attempt_at = now() + CASE v_internal
                   WHEN 1 THEN interval '30 seconds' WHEN 2 THEN interval '2 minutes'
                   WHEN 3 THEN interval '10 minutes' ELSE interval '1 hour' END
         WHERE id = p_id;
        RETURN true;
    END IF;
    UPDATE sales_order
       SET pdf_error = left(p_error, 2000), pdf_lease_until = NULL, pdf_lease = NULL,
           pdf_state = CASE WHEN v_attempts >= {MAX_RENDER_ATTEMPTS} THEN 'failed'
                            ELSE 'pending' END,
           pdf_next_attempt_at = now() + CASE v_attempts
               WHEN 1 THEN interval '30 seconds' WHEN 2 THEN interval '2 minutes'
               WHEN 3 THEN interval '10 minutes' ELSE interval '1 hour' END
     WHERE id = p_id;
    RETURN true;
END $fn$"""


INDEX = ("CREATE INDEX ix_sales_order_internal_pdf_owed ON sales_order (approved_at) "
         "WHERE pdf_state = 'ready' AND pdf_internal_key IS NULL AND deleted_at IS NULL")


def _m016() -> ModuleType:
    path = Path(__file__).with_name("016_order_messages.py")
    spec = importlib.util.spec_from_file_location("mig_016_for_092", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("092: migration 016 not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _original(name: str) -> str:
    """016's text of one render function, as CREATE OR REPLACE."""
    prefix = f"CREATE FUNCTION {name}("
    for item in _m016().FUNCTIONS:
        if isinstance(item, str) and item.lstrip().startswith(prefix):
            return item.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    raise LookupError(name)


def _swap(sig: str, old: str, new: str, times: int = 1) -> None:
    body = str(op.get_bind().execute(
        text(f"SELECT pg_get_functiondef('{sig}'::regprocedure)")).scalar_one())
    if body.count(old) != times:
        raise RuntimeError(f"092: {sig} anchor {old[:40]!r} found {body.count(old)} times, "
                           f"expected {times}")
    op.execute(body.replace(old, new))


def upgrade() -> None:
    op.execute(COLUMNS)
    _swap(GUARD, GUARD_OLD, GUARD_NEW, times=2)
    _swap(AMEND, AMEND_OLD, AMEND_NEW)
    op.execute(CLAIM)
    op.execute(FAILED)
    op.execute(DONE_3_SHIM)
    op.execute(DONE_4_SQL)
    op.execute(INDEX)
    op.execute(f"REVOKE ALL ON FUNCTION {DONE_4} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {DONE_4} TO app_role")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sales_order_internal_pdf_owed")
    op.execute(f"DROP FUNCTION {DONE_4}")
    # an internal-only lease would leave a ready order holding a lease 016 never clears
    op.execute("UPDATE sales_order SET pdf_lease = NULL, pdf_lease_until = NULL "
               "WHERE pdf_state = 'ready' AND pdf_lease IS NOT NULL")
    for name in ("order_render_claim", "order_render_done", "order_render_failed"):
        op.execute(_original(name))
    _swap(AMEND, AMEND_NEW, AMEND_OLD)
    _swap(GUARD, GUARD_NEW, GUARD_OLD, times=2)
    op.execute("ALTER TABLE sales_order DROP COLUMN pdf_internal_key, "
               "DROP COLUMN pdf_internal_attempts, DROP COLUMN pdf_internal_error")
