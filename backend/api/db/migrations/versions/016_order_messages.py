"""016: order messages and the order PDF's columns (FS-012).

- `message_template(key, provider_name, enabled)`: the one switch for the three
  order messages (EC-5), seeded enabled with the account's template names (plan
  review B-1). A definer writes a row only for an enabled key, and copies the name
  into the payload as `_template`; the adapter sends with it (B-2).
- `approval_alert`: who was alerted for which order and step, so a resubmit loop
  alerts a person once an hour, not every round (EC-3). The outbox cannot answer
  that: the worker clears a sent row's payload.
- `inr_text(numeric)`: money as the messages and the PDF print it, "1,23,456.50"
  (EC-6).
- `sales_order`: the PDF render columns, added to the list a submitted order may
  still change, and kept out of `app_role`'s grants (EC-1).
- `order_notify_step()` and `order_notify_outcome()`, internal definers, called
  from `create_approval_request()` and `advance_approval()`, which are replaced by
  patching 013's own text: the first step's alert when a request opens, the next
  step's on each approval, and on the last approval the buyer's confirmation, the
  owner's message and `pdf_state = pending`; on a rejection, the owner's message.
  Each in the same transaction as its event (rule 1).
- `order_render_claim/done/failed`: the worker's render lease, the quotation's
  shape (FS-005 5.2), guarded on the system principal.

Revision ID: 016_order_messages
Revises: 015_public_lead_capture
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "016_order_messages"
down_revision: str | None = "015_public_lead_capture"
branch_labels = None
depends_on = None

_PDF_COLUMNS = ("'pdf_state', 'pdf_key', 'pdf_error', 'pdf_attempts', 'pdf_lease', "
                "'pdf_lease_until', 'pdf_next_attempt_at'")
MAX_RENDER_ATTEMPTS = 5

TABLES = [
    """CREATE TABLE message_template (
    key text PRIMARY KEY,
    provider_name text,
    enabled boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE TABLE approval_alert (
    entity_id uuid NOT NULL,
    seq int NOT NULL,
    user_id uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now()
)""",
    "CREATE INDEX ix_approval_alert ON approval_alert (entity_id, seq, user_id, created_at DESC)",
    # definers only: no grant, no policy
    "ALTER TABLE message_template ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE approval_alert ENABLE ROW LEVEL SECURITY",
    """INSERT INTO message_template (key, provider_name, enabled) VALUES
    ('order.confirmed', 'polysil_order_confirmed', true),
    ('approval.waiting', 'polysil_approval_waiting', true),
    ('order.decided', 'polysil_order_decided', true)""",
    """ALTER TABLE sales_order
    ADD COLUMN pdf_state text,
    ADD COLUMN pdf_key text,
    ADD COLUMN pdf_error text,
    ADD COLUMN pdf_attempts int NOT NULL DEFAULT 0,
    ADD COLUMN pdf_lease uuid,
    ADD COLUMN pdf_lease_until timestamptz,
    ADD COLUMN pdf_next_attempt_at timestamptz,
    ADD CONSTRAINT ck_sales_order_pdf_state CHECK (pdf_state IS NULL OR pdf_state IN ('pending', 'rendering', 'ready', 'failed'))""",
    "CREATE INDEX ix_sales_order_pdf_due ON sales_order (pdf_state) WHERE pdf_state IN ('pending', 'rendering')",
]

FUNCTIONS = [
    """CREATE FUNCTION inr_text(p numeric) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path = public, pg_temp AS $fn$
DECLARE s text; i text; f text; r text;
BEGIN
    IF p IS NULL THEN RETURN NULL; END IF;
    s := to_char(abs(round(p, 2)), 'FM9999999999999990.00');
    i := split_part(s, '.', 1);
    f := split_part(s, '.', 2);
    IF length(i) > 3 THEN
        r := right(i, 3);
        i := left(i, length(i) - 3);
        WHILE length(i) > 2 LOOP
            r := right(i, 2) || ',' || r;
            i := left(i, length(i) - 2);
        END LOOP;
        r := i || ',' || r;
    ELSE
        r := i;
    END IF;
    RETURN CASE WHEN p < 0 THEN '-' ELSE '' END || r || '.' || f;
END $fn$""",
    # the next undecided step's approvers: everyone who could decide it, never the
    # requester, the owner or the creator (EC-2), once an hour per order and step
    """CREATE FUNCTION order_notify_step(p_request uuid) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_req approval_request%ROWTYPE; v_step approval_step%ROWTYPE; o sales_order%ROWTYPE;
    v_line boolean; v_tpl text; v_n int := 0; u record;
BEGIN
    SELECT provider_name INTO v_tpl FROM message_template
     WHERE key = 'approval.waiting' AND enabled AND provider_name IS NOT NULL;
    IF v_tpl IS NULL THEN RETURN 0; END IF;
    SELECT * INTO v_req FROM approval_request WHERE id = p_request;
    IF NOT FOUND OR v_req.doc_type <> 'sales_order' OR v_req.status <> 'pending' THEN RETURN 0; END IF;
    SELECT * INTO v_step FROM approval_step
     WHERE request_id = p_request AND decision IS NULL ORDER BY seq LIMIT 1;
    IF NOT FOUND THEN RETURN 0; END IF;
    SELECT NOT r.is_functional AND NOT r.is_portal INTO v_line FROM role r WHERE r.id = v_step.approver_role_id;
    SELECT * INTO o FROM sales_order WHERE id = v_req.entity_id;
    FOR u IN
        SELECT au.id, au.full_name, au.mobile FROM app_user au
         WHERE au.role_id = v_step.approver_role_id AND au.user_type = 'staff'
           AND au.is_active AND au.deleted_at IS NULL AND au.mobile IS NOT NULL
           AND au.id IS DISTINCT FROM v_req.requested_by
           AND au.id IS DISTINCT FROM o.owner_user_id AND au.id IS DISTINCT FROM o.created_by
           AND (NOT v_line OR au.org_unit_id IN (SELECT oc.ancestor_id FROM org_closure oc
                                                  WHERE oc.descendant_id = o.owner_org_unit_id))
           AND NOT EXISTS (SELECT 1 FROM approval_alert a WHERE a.entity_id = o.id AND a.seq = v_step.seq
                              AND a.user_id = au.id AND a.created_at > now() - interval '1 hour')
    LOOP
        INSERT INTO approval_alert (entity_id, seq, user_id) VALUES (o.id, v_step.seq, u.id);
        INSERT INTO notification_outbox (channel, template_key, recipient, payload)
        VALUES ('whatsapp', 'approval.waiting',
                CASE WHEN u.mobile LIKE '+%' THEN u.mobile ELSE '+' || u.mobile END,
                jsonb_build_object('_template', v_tpl, 'approver_name', u.full_name,
                                   'order_no', o.order_no, 'party_name', o.party_name,
                                   'total', inr_text(o.total)));
        v_n := v_n + 1;
    END LOOP;
    RETURN v_n;
END $fn$""",
    # the outcome: on approval, the buyer's confirmation and the PDF queued; either
    # way, the owner's message. Returns what happened to the buyer's confirmation
    # (EC-4): queued, no_mobile, or disabled; null on a return.
    """CREATE FUNCTION order_notify_outcome(p_order uuid, p_outcome text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE o sales_order%ROWTYPE; v_tpl text; v_conf text; ow record;
BEGIN
    SELECT * INTO o FROM sales_order WHERE id = p_order;
    IF p_outcome = 'approved' THEN
        UPDATE sales_order SET pdf_state = 'pending', pdf_attempts = 0, pdf_error = NULL,
               pdf_next_attempt_at = now()
         WHERE id = p_order;
        SELECT provider_name INTO v_tpl FROM message_template
         WHERE key = 'order.confirmed' AND enabled AND provider_name IS NOT NULL;
        IF v_tpl IS NULL THEN
            v_conf := 'disabled';
        ELSIF o.party_mobile IS NULL OR btrim(o.party_mobile) = '' THEN
            v_conf := 'no_mobile';
        ELSE
            INSERT INTO notification_outbox (channel, template_key, recipient, payload)
            VALUES ('whatsapp', 'order.confirmed',
                    CASE WHEN o.party_mobile LIKE '+%' THEN o.party_mobile ELSE '+' || o.party_mobile END,
                    jsonb_build_object('_template', v_tpl, 'party_name', o.party_name,
                                       'order_no', o.order_no, 'total', inr_text(o.total)));
            v_conf := 'queued';
        END IF;
    END IF;
    v_tpl := NULL;
    SELECT provider_name INTO v_tpl FROM message_template
     WHERE key = 'order.decided' AND enabled AND provider_name IS NOT NULL;
    SELECT u.id, u.full_name, u.mobile INTO ow FROM app_user u
     WHERE u.id = o.owner_user_id AND u.user_type = 'staff' AND u.is_active
       AND u.deleted_at IS NULL AND u.mobile IS NOT NULL;
    IF v_tpl IS NOT NULL AND ow.id IS NOT NULL THEN
        INSERT INTO notification_outbox (channel, template_key, recipient, payload)
        VALUES ('whatsapp', 'order.decided',
                CASE WHEN ow.mobile LIKE '+%' THEN ow.mobile ELSE '+' || ow.mobile END,
                jsonb_build_object('_template', v_tpl, 'owner_name', ow.full_name,
                                   'order_no', o.order_no, 'party_name', o.party_name,
                                   'outcome', CASE WHEN p_outcome = 'approved' THEN 'approved'
                                                   ELSE 'returned for changes' END));
    END IF;
    RETURN v_conf;
END $fn$""",
    # The order render lease: FS-005 5.2's shape, the quotation's functions with the
    # order's columns. The claim commits before the render, and charges the attempt
    # there and nowhere else. A cancelled order is not rendered (rule 8): the
    # endpoint refuses its PDF anyway.
    f"""CREATE FUNCTION order_render_claim(p_lease interval) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE o sales_order%ROWTYPE; v_token uuid;
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
        RETURN NULL;
    END IF;
    IF o.pdf_attempts >= {MAX_RENDER_ATTEMPTS} THEN
        UPDATE sales_order SET pdf_state = 'failed', pdf_lease_until = NULL, pdf_lease = NULL,
               pdf_error = 'render abandoned after 5 attempts: ' || COALESCE(pdf_error, 'the worker died on the last one')
         WHERE id = o.id;
        RETURN NULL;
    END IF;
    v_token := gen_random_uuid();
    UPDATE sales_order
       SET pdf_state = 'rendering', pdf_lease_until = now() + p_lease, pdf_lease = v_token,
           pdf_attempts = pdf_attempts + 1
     WHERE id = o.id;
    RETURN jsonb_build_object(
        'lease_token', v_token, 'attempt', o.pdf_attempts + 1,
        'order', to_jsonb(o) - ARRAY['pdf_lease', 'remarks', 'cancel_remark', 'close_remark']
                 || jsonb_build_object(
                        'status', o.status::text, 'order_type', o.order_type::text,
                        'payment_terms', o.payment_terms::text,
                        'place_of_supply', (SELECT t.name FROM territory t
                                             WHERE t.id = COALESCE(o.place_of_supply_state_id,
                                                                   o.place_of_supply_territory_id))),
        'lines', (SELECT COALESCE(jsonb_agg(to_jsonb(l) ORDER BY l.line_no), '[]'::jsonb)
                    FROM order_line l WHERE l.sales_order_id = o.id));
END $fn$""",
    # conditional on the lease, like the quotation's; no message rides on it (the
    # buyer's confirmation went at approval, question 1)
    """CREATE FUNCTION order_render_done(p_id uuid, p_lease_token uuid, p_key text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal renders' USING ERRCODE = '42501';
    END IF;
    UPDATE sales_order
       SET pdf_state = 'ready', pdf_key = p_key, pdf_lease_until = NULL, pdf_lease = NULL,
           pdf_error = NULL
     WHERE id = p_id AND pdf_state = 'rendering' AND pdf_lease = p_lease_token;
    RETURN FOUND;
END $fn$""",
    f"""CREATE FUNCTION order_render_failed(p_id uuid, p_lease_token uuid, p_error text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_attempts int;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal renders' USING ERRCODE = '42501';
    END IF;
    SELECT pdf_attempts INTO v_attempts FROM sales_order
     WHERE id = p_id AND pdf_state = 'rendering' AND pdf_lease = p_lease_token
       FOR UPDATE;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    UPDATE sales_order
       SET pdf_error = left(p_error, 2000), pdf_lease_until = NULL, pdf_lease = NULL,
           pdf_state = CASE WHEN v_attempts >= {MAX_RENDER_ATTEMPTS} THEN 'failed' ELSE 'pending' END,
           pdf_next_attempt_at = now() + CASE v_attempts
               WHEN 1 THEN interval '30 seconds' WHEN 2 THEN interval '2 minutes'
               WHEN 3 THEN interval '10 minutes' ELSE interval '1 hour' END
     WHERE id = p_id;
    RETURN true;
END $fn$""",
]

INTERNAL = ["order_notify_step(uuid)", "order_notify_outcome(uuid, text)"]
# the worker's, as the system principal; each refuses anyone else
RENDER_SIGS = ["order_render_claim(interval)", "order_render_done(uuid, uuid, text)",
               "order_render_failed(uuid, uuid, text)"]


def _m013() -> ModuleType:
    path = Path(__file__).with_name("013_orders_approvals_dispatch.py")
    spec = importlib.util.spec_from_file_location("mig_013_for_016", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("016: migration 013 not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _original(name: str) -> str:
    """013's text of one function, found among its module-level strings."""
    mod = _m013()
    prefix = f"CREATE FUNCTION {name}("
    for value in vars(mod).values():
        items = value if isinstance(value, list | tuple) else [value]
        for item in items:
            if isinstance(item, str) and item.lstrip().startswith(prefix):
                return item
    raise LookupError(name)


def _patched() -> list[str]:
    def replace(text: str, old: str, new: str) -> str:
        # an exception, not an assert: under python -O an assert is gone and a
        # missed anchor would leave the messages unwired in silence (code review F-8)
        if text.count(old) != 1:
            raise RuntimeError(f"016: 013 changed; anchor not found once: {old[:60]!r}")
        return text.replace(old, new)

    create = _original("create_approval_request")
    create = replace(create, "    RETURN v_request;\nEND $fn$",
                     "    PERFORM order_notify_step(v_request);\n    RETURN v_request;\nEND $fn$")
    advance = _original("advance_approval")
    advance = replace(advance, "        VALUES ('sales_order', v_req.entity_id, v_lead, 'order.returned', app_current_user_id(), '{}');\n",
                      "        VALUES ('sales_order', v_req.entity_id, v_lead, 'order.returned', app_current_user_id(), '{}');\n"
                      "        PERFORM order_notify_outcome(v_req.entity_id, 'returned');\n")
    advance = replace(advance, "    IF v_approved < v_total THEN\n        RETURN 'pending';",
                      "    IF v_approved < v_total THEN\n        PERFORM order_notify_step(p_request_id);\n        RETURN 'pending';")
    advance = replace(advance, "VALUES ('sales_order', v_req.entity_id, v_lead, 'order.approved', app_current_user_id(), '{}');",
                      "VALUES ('sales_order', v_req.entity_id, v_lead, 'order.approved', app_current_user_id(),\n"
                      "            jsonb_build_object('confirmation', order_notify_outcome(v_req.entity_id, 'approved')));")
    refuse = _original("refuse_submitted_order_edit")
    if refuse.count("'external_id'") != 2:
        raise RuntimeError("016: 013's refuse_submitted_order_edit changed shape")
    refuse = refuse.replace("'external_id'", "'external_id', " + _PDF_COLUMNS)
    return [f.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
            for f in (create, advance, refuse)]


def _restored() -> list[str]:
    return [_original(n).replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
            for n in ("create_approval_request", "advance_approval", "refuse_submitted_order_edit")]


# Orders approved before this migration have no PDF state, and only an approval
# sets one, so they would answer "not approved yet" for good (cross-vendor
# review). They are queued for a render, and nothing else: no confirmation goes
# out for an approval that happened before the messages existed.
BACKFILL = """UPDATE sales_order
   SET pdf_state = 'pending', pdf_attempts = 0, pdf_next_attempt_at = now()
 WHERE pdf_state IS NULL AND deleted_at IS NULL
   AND status IN ('approved', 'partially_dispatched', 'dispatched', 'closed_short')"""


def upgrade() -> None:
    for stmt in TABLES + FUNCTIONS:
        op.execute(stmt)
    for sig in [*INTERNAL, *RENDER_SIGS, "inr_text(numeric)"]:
        op.execute(f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC")
    for sig in RENDER_SIGS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO app_role")
    # money formatting is harmless and the service reads it
    op.execute("GRANT EXECUTE ON FUNCTION inr_text(numeric) TO app_role")
    for stmt in _patched():
        op.execute(stmt)
    op.execute(BACKFILL)


def downgrade() -> None:
    for stmt in _restored():
        op.execute(stmt)
    for sig in [*INTERNAL, *RENDER_SIGS, "inr_text(numeric)"]:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP INDEX IF EXISTS ix_sales_order_pdf_due")
    op.execute("ALTER TABLE sales_order DROP CONSTRAINT IF EXISTS ck_sales_order_pdf_state")
    for col in ("pdf_state", "pdf_key", "pdf_error", "pdf_attempts", "pdf_lease", "pdf_lease_until",
                "pdf_next_attempt_at"):
        op.execute(f"ALTER TABLE sales_order DROP COLUMN IF EXISTS {col}")
    op.execute("DROP TABLE IF EXISTS approval_alert")
    op.execute("DROP TABLE IF EXISTS message_template")
