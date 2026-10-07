"""041: company settings, amending an approved order, reopening a complaint (FS-036).

- `app_setting`: one row per company-wide setting, with its own kind, allowed
  values and range, so a later migration adds a key by inserting a row (the other
  Phase 2 session's 046 does). `app_setting_check()` refuses a bad value on insert
  and update; `app_setting_set()` is the one writer, with an event per change;
  `app_setting_text()` and `app_setting_json()` are the readers for SQL.
- `order_amend()`: an approved order with nothing shipped and nothing paid goes back
  to draft under its number. The order guard admits approved -> draft and the amend
  columns; `create_approval_request` skips the managers under `value_rises` when the
  total did not rise; `order_cancel` keeps the approved-cancel rule for an order that
  was ever approved (plan review B-2).
- `complaint_reopen()`: a closed or QC-rejected complaint starts a new round.
  `clock_from` carries a restarted clock through `complaint_submit` and
  `complaint_check` (plan review B-8).

The five existing functions are patched from their live text, read from the
database, by exact anchors that must each appear the stated number of times. The
downgrade swaps every anchor back. Their text was composed by 013, 016, 017, 019,
026, 029 and 032; reading it live is what 004a does, and it keeps a later patch
by either session from being lost.

Revision ID: 041_settings_amend_reopen
Revises: 040_lead_small_gaps
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "041_settings_amend_reopen"
down_revision: str | None = "040_lead_small_gaps"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

TABLES = [
    """CREATE TABLE app_setting (
    key citext PRIMARY KEY,
    id uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    kind text NOT NULL CHECK (kind IN ('choice', 'int', 'roles')),
    value jsonb NOT NULL,
    allowed jsonb CHECK (allowed IS NULL OR jsonb_typeof(allowed) = 'array'),
    min numeric,
    max numeric,
    description text NOT NULL CHECK (length(btrim(description)) BETWEEN 1 AND 300),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid REFERENCES app_user(id),
    CONSTRAINT ck_app_setting_choice CHECK (kind <> 'choice' OR allowed IS NOT NULL),
    CONSTRAINT ck_app_setting_range CHECK (min IS NULL OR max IS NULL OR min <= max)
)""",
    "ALTER TABLE sales_order ADD COLUMN amend_count int NOT NULL DEFAULT 0, "
    "ADD COLUMN amended_from_total numeric(14,2), ADD COLUMN amended_at timestamptz, "
    "ADD COLUMN amend_reason text CHECK (amend_reason IS NULL OR length(amend_reason) <= 1000)",
    "ALTER TABLE complaint ADD COLUMN reopen_count int NOT NULL DEFAULT 0, "
    "ADD COLUMN reopened_at timestamptz, ADD COLUMN clock_from timestamptz, "
    "ADD COLUMN reopen_reason text CHECK (reopen_reason IS NULL OR length(reopen_reason) <= 1000)",
]

SEED = """INSERT INTO app_setting (key, kind, value, allowed, min, max, description) VALUES
('order_amend_reapproval', 'choice', '"always"', '["always", "value_rises"]', NULL, NULL,
 'An amended order goes through the managers again always, or only when its total rises (Accounts and Dispatch always confirm).'),
('complaint_reopen_days', 'int', '30', NULL, 1, 365,
 'Days after a complaint closes, or QC rejects it, during which it may be reopened.'),
('complaint_reopen_roles', 'roles', '["qc_manager", "support"]', NULL, NULL, NULL,
 'Roles that may reopen a complaint. The person who raised it may also reopen a closed one.'),
('complaint_reopen_clock', 'choice', '"restart"', '["restart", "continue"]', NULL, NULL,
 'On reopening, count the response and resolution targets again from now, or keep the original dates.'),
('complaint_reopen_max', 'int', '2', NULL, 1, 10,
 'How many times one complaint may be reopened.')"""

FUNCTIONS = [
    """CREATE FUNCTION app_setting_check() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
DECLARE v numeric; r text;
BEGIN
    IF NEW.kind = 'choice' THEN
        IF jsonb_typeof(NEW.value) <> 'string' OR NOT (NEW.allowed @> jsonb_build_array(NEW.value)) THEN
            RAISE EXCEPTION 'setting %: one of %', NEW.key, NEW.allowed USING ERRCODE = 'SETVL';
        END IF;
    ELSIF NEW.kind = 'int' THEN
        IF jsonb_typeof(NEW.value) <> 'number' THEN
            RAISE EXCEPTION 'setting %: a whole number', NEW.key USING ERRCODE = 'SETVL';
        END IF;
        v := (NEW.value #>> '{}')::numeric;
        IF v <> trunc(v) OR (NEW.min IS NOT NULL AND v < NEW.min) OR (NEW.max IS NOT NULL AND v > NEW.max) THEN
            RAISE EXCEPTION 'setting %: % to %', NEW.key, NEW.min, NEW.max USING ERRCODE = 'SETVL';
        END IF;
    ELSE
        IF jsonb_typeof(NEW.value) <> 'array' THEN
            RAISE EXCEPTION 'setting %: a list of role codes', NEW.key USING ERRCODE = 'SETVL';
        END IF;
        -- the migrations' own rows: a fresh database migrates before the roles are seeded
        -- (CI), and 005/015 insert roles, so the role table is never empty here. The
        -- codes are checked from the first change on, by app_setting_set
        IF TG_OP = 'INSERT' THEN
            RETURN NEW;
        END IF;
        FOR r IN SELECT jsonb_array_elements_text(NEW.value) LOOP
            IF NOT EXISTS (SELECT 1 FROM role WHERE code = r AND deleted_at IS NULL) THEN
                RAISE EXCEPTION 'setting %: no role %', NEW.key, r USING ERRCODE = 'SETVL';
            END IF;
        END LOOP;
    END IF;
    RETURN NEW;
END $fn$""",

    """CREATE FUNCTION app_setting_json(p_key text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v jsonb;
BEGIN
    SELECT value INTO v FROM app_setting WHERE key = p_key;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no setting %', p_key USING ERRCODE = 'SETNF';
    END IF;
    RETURN v;
END $fn$""",

    """CREATE FUNCTION app_setting_text(p_key text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT app_setting_json(p_key) #>> '{}'
$fn$""",

    # the one writer: masters.edit, the row's own check, one event per change
    """CREATE FUNCTION app_setting_set(p_key text, p_value jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE s app_setting%ROWTYPE;
BEGIN
    IF NOT app_has_permission('masters', 'edit') THEN
        RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO s FROM app_setting WHERE key = p_key FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no setting %', p_key USING ERRCODE = 'SETNF';
    END IF;
    IF s.value = p_value THEN
        RETURN false;
    END IF;
    UPDATE app_setting SET value = p_value, updated_at = now(), updated_by = app_current_user_id()
     WHERE key = p_key;
    -- unmapped in activity_event_sel, so the system principal reads it; the audit row keeps it too
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('app_setting', s.id, 'setting.changed', app_current_user_id(),
            jsonb_build_object('key', s.key::text, 'from', s.value, 'to', p_value));
    RETURN true;
END $fn$""",

    # FS-036 §3: back to draft under the same number, before anything ships or is paid
    """CREATE FUNCTION order_amend(p_order_id uuid, p_reason text, p_expected text DEFAULT NULL)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := app_current_user_id(); v_order sales_order%ROWTYPE; v_reason text; v_schedule jsonb;
BEGIN
    IF NOT order_visible(p_order_id) THEN
        RAISE EXCEPTION 'order not found' USING ERRCODE = 'ORDNF';
    END IF;
    SELECT * INTO v_order FROM sales_order WHERE id = p_order_id FOR UPDATE;
    IF v_order.deleted_at IS NOT NULL THEN
        RAISE EXCEPTION 'order not found' USING ERRCODE = 'ORDNF';
    END IF;
    -- staff only: portal roles hold sales_orders.edit at partner_subtree (GAP-352)
    IF app_current_partner() IS NOT NULL
       OR NOT (app_has_permission('sales_orders', 'edit') OR v_me IS NOT DISTINCT FROM v_order.owner_user_id
               OR v_me IS NOT DISTINCT FROM v_order.created_by) THEN
        RAISE EXCEPTION 'not permitted to amend this order' USING ERRCODE = '42501';
    END IF;
    IF p_expected IS NOT NULL AND v_order.status::text <> p_expected THEN
        RAISE EXCEPTION 'the order is now %', v_order.status USING ERRCODE = 'ORDSC';
    END IF;
    v_reason := NULLIF(btrim(p_reason), '');
    IF v_reason IS NULL THEN
        RAISE EXCEPTION 'remark_required' USING ERRCODE = 'APRRM';
    END IF;
    IF v_order.order_type = 'replacement' THEN
        RAISE EXCEPTION 'a replacement order follows its complaint' USING ERRCODE = 'ORDTF';
    END IF;
    IF EXISTS (SELECT 1 FROM dispatch WHERE sales_order_id = p_order_id AND voided_at IS NULL) THEN
        RAISE EXCEPTION 'the order has shipped' USING ERRCODE = 'ORDDS';
    END IF;
    IF v_order.status <> 'approved' THEN
        RAISE EXCEPTION 'the order is now %', v_order.status USING ERRCODE = 'ORDSC';
    END IF;
    IF EXISTS (SELECT 1 FROM payment_allocation WHERE sales_order_id = p_order_id AND NOT voided) THEN
        RAISE EXCEPTION 'money is allocated to this order' USING ERRCODE = 'ORDPA';
    END IF;
    -- the instalments were planned against the old total; Accounts sets them again (review N-5)
    WITH gone AS (DELETE FROM payment_schedule WHERE sales_order_id = p_order_id
                  RETURNING seq, due_on, amount)
    SELECT coalesce(jsonb_agg(jsonb_build_object('seq', seq, 'due_on', due_on, 'amount', amount::text)
                              ORDER BY seq), '[]'::jsonb) INTO v_schedule FROM gone;
    UPDATE sales_order SET status = 'draft', approved_at = NULL,
           pdf_state = NULL, pdf_key = NULL, pdf_error = NULL,
           amend_count = amend_count + 1, amended_from_total = total, amended_at = now(),
           amend_reason = v_reason, updated_by = v_me
     WHERE id = p_order_id;
    -- no reason in the payload: a dealer reads its order's timeline (FS-015b trap)
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('sales_order', p_order_id, v_order.lead_id, 'order.amended', v_me,
            jsonb_build_object('from', 'approved', 'to', 'draft', 'amend', v_order.amend_count + 1,
                               'from_total', v_order.total::text, 'schedule_cleared', v_schedule));
END $fn$""",

    # FS-036 §3: the one rule for the definer and the detail's `can.reopen`, like 019's
    # complaint_refusal(): null when the caller may reopen now, else the reason
    """CREATE FUNCTION complaint_reopen_refusal(p_id uuid) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE c complaint%ROWTYPE; v_me uuid := app_current_user_id(); v_role text; v_since timestamptz;
BEGIN
    IF NOT complaint_visible(p_id) THEN
        RETURN 'not_visible';
    END IF;
    SELECT * INTO c FROM complaint WHERE id = p_id AND deleted_at IS NULL;
    IF NOT FOUND THEN
        RETURN 'not_visible';
    END IF;
    IF c.status NOT IN ('closed', 'qc_rejected') THEN
        RETURN 'not_reopenable';
    END IF;
    SELECT r.code::text INTO v_role FROM app_user u JOIN role r ON r.id = u.role_id WHERE u.id = v_me;
    -- the raiser reopens a closed complaint; a rejection only the allowed roles (review N-11)
    IF NOT (app_setting_json('complaint_reopen_roles') @> jsonb_build_array(v_role)
            OR (c.status = 'closed' AND v_me IS NOT DISTINCT FROM c.raised_by)) THEN
        RETURN 'not_permitted';
    END IF;
    v_since := CASE WHEN c.status = 'closed' THEN c.closed_at ELSE c.resolved_at END;
    IF v_since IS NULL
       OR now() > v_since + make_interval(days => app_setting_text('complaint_reopen_days')::int)
       OR c.reopen_count >= app_setting_text('complaint_reopen_max')::int THEN
        RETURN 'window_closed';
    END IF;
    RETURN NULL;
END $fn$""",

    """CREATE FUNCTION complaint_reopen(p_id uuid, p_reason text, p_expected text DEFAULT NULL)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    c complaint%ROWTYPE; v_me uuid := app_current_user_id(); v_reason text; v_why text;
    v_clock text; v_from timestamptz; p complaint_sla_policy%ROWTYPE;
BEGIN
    SELECT * INTO c FROM complaint WHERE id = p_id AND deleted_at IS NULL FOR UPDATE;
    v_why := complaint_reopen_refusal(p_id);
    IF v_why = 'not_visible' THEN
        RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'CMPNF';
    END IF;
    IF (p_expected IS NOT NULL AND c.status::text <> p_expected) OR v_why = 'not_reopenable' THEN
        RAISE EXCEPTION 'the complaint moved on' USING ERRCODE = 'CMPSC';
    END IF;
    IF v_why = 'not_permitted' THEN
        RAISE EXCEPTION 'not permitted to reopen this complaint' USING ERRCODE = '42501';
    END IF;
    v_reason := NULLIF(btrim(p_reason), '');
    IF v_reason IS NULL THEN
        RAISE EXCEPTION 'remark_required' USING ERRCODE = 'CMPRK';
    END IF;
    IF v_why = 'window_closed' THEN
        RAISE EXCEPTION 'the reopen window has closed' USING ERRCODE = 'CMPRW';
    END IF;
    IF NOT complaint_has_checker(p_id) THEN
        RAISE EXCEPTION 'nobody can check this complaint' USING ERRCODE = 'CMPNC';
    END IF;
    v_clock := app_setting_text('complaint_reopen_clock');
    v_from := CASE WHEN v_clock = 'restart' THEN now() ELSE coalesce(c.clock_from, c.first_submitted_at) END;
    p := complaint_sla_policy_at(c.complaint_type_id, c.severity, (c.first_submitted_at AT TIME ZONE 'Asia/Kolkata')::date);
    UPDATE complaint
       SET status = 'submitted', submit_count = submit_count + 1, submitted_at = now(),
           closed_at = NULL, responded_at = NULL, resolved_at = NULL,
           clock_from = CASE WHEN v_clock = 'restart' THEN now() ELSE clock_from END,
           response_due_at = complaint_due(v_from, p.response_hours, p.business_hours_only),
           resolution_due_at = complaint_due(v_from, p.resolution_hours, p.business_hours_only),
           reopen_count = reopen_count + 1, reopened_at = now(), reopen_reason = v_reason,
           updated_by = v_me
     WHERE id = p_id;
    -- complaint.submitted, so the bell and the checker's queue need nothing new (review N-10)
    INSERT INTO activity_event (entity_type, entity_id, lead_id, partner_id, kind, actor_id, payload)
    VALUES ('complaint', p_id, c.lead_id, c.partner_id, 'complaint.submitted', v_me,
            jsonb_build_object('reopened', true, 'from', c.status::text, 'round', c.submit_count + 1,
                               'clock', v_clock));
END $fn$""",
]

GRANTED = ["app_setting_text(text)", "app_setting_json(text)", "app_setting_set(text, jsonb)",
           "order_amend(uuid, text, text)", "complaint_reopen(uuid, text, text)",
           "complaint_reopen_refusal(uuid)"]

GRANTS: dict[str, str] = {"app_setting": "SELECT"}
HAND_POLICIES: list[tuple[str, str]] = [
    ("app_setting", "CREATE POLICY app_setting_sel ON app_setting FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"),
]

_ORDER_COLS = "'pdf_next_attempt_at']"
_ORDER_COLS_NEW = "'pdf_next_attempt_at', 'amend_count', 'amended_from_total', 'amended_at', 'amend_reason']"
_COMPLAINT_DUE_OLD = "complaint_due(c.first_submitted_at,"
_COMPLAINT_DUE_NEW = "complaint_due(coalesce(c.clock_from, c.first_submitted_at),"

# (function, [(old, new, times)])
PATCHES: list[tuple[str, list[tuple[str, str, int]]]] = [
    ("refuse_submitted_order_edit", [
        ("('dispatched', 'partially_dispatched'), ('dispatched', 'approved')) THEN",
         "('dispatched', 'partially_dispatched'), ('dispatched', 'approved'),\n"
         "            ('approved', 'draft')) THEN", 1),
        (_ORDER_COLS, _ORDER_COLS_NEW, 2),
    ]),
    ("create_approval_request", [
        ("                              approval_owner_level(v_order.owner_user_id));",
         "                              CASE WHEN v_order.amended_from_total IS NOT NULL\n"
         "                                    AND app_setting_text('order_amend_reapproval') = 'value_rises'\n"
         "                                    AND v_order.total <= v_order.amended_from_total\n"
         "                                   THEN 2147483647\n"
         "                                   ELSE approval_owner_level(v_order.owner_user_id) END);", 1),
    ]),
    ("order_cancel", [
        ("    IF v_order.status IN ('draft', 'submitted') THEN",
         "    IF v_order.status IN ('draft', 'submitted') AND v_order.amend_count = 0 THEN", 1),
        ("    ELSIF v_order.status = 'approved' THEN",
         "    ELSIF v_order.status = 'approved' OR v_order.amend_count > 0 THEN", 1),
    ]),
    ("complaint_submit", [(_COMPLAINT_DUE_OLD, _COMPLAINT_DUE_NEW, 2)]),
    ("complaint_check", [(_COMPLAINT_DUE_OLD, _COMPLAINT_DUE_NEW, 2)]),
]


def _live(name: str) -> str:
    bind = op.get_bind()
    defs = bind.execute(text("SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                             "JOIN pg_namespace n ON n.oid = p.pronamespace "
                             "WHERE n.nspname = 'public' AND p.proname = :n"), {"n": name}).scalars().all()
    if len(defs) != 1:
        raise RuntimeError(f"041: expected one function {name}, found {len(defs)}")
    return str(defs[0])


def _apply(name: str, swaps: list[tuple[str, str, int]], *, reverse: bool) -> None:
    body = _live(name)
    for old, new, times in swaps:
        a, b = (new, old) if reverse else (old, new)
        if body.count(a) != times:
            raise RuntimeError(f"041: {name}: anchor found {body.count(a)} times, expected {times}: {a[:60]!r}")
        body = body.replace(a, b)
    op.execute(body)


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute("CREATE TRIGGER trg_app_setting_check BEFORE INSERT OR UPDATE ON app_setting "
               "FOR EACH ROW EXECUTE FUNCTION app_setting_check()")
    op.execute("CREATE TRIGGER trg_app_setting_audit AFTER INSERT OR UPDATE OR DELETE ON app_setting "
               "FOR EACH ROW EXECUTE FUNCTION audit_row()")
    op.execute(SEED)
    op.execute("ALTER TABLE app_setting ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    for name, swaps in PATCHES:
        _apply(name, swaps, reverse=False)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    for name, swaps in reversed(PATCHES):
        _apply(name, swaps, reverse=True)
    op.execute("DELETE FROM activity_event WHERE kind = 'setting.changed' OR kind = 'order.amended' "
               "OR (kind = 'complaint.submitted' AND payload ? 'reopened')")
    for sig in GRANTED:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP TABLE IF EXISTS app_setting")
    op.execute("DROP FUNCTION IF EXISTS app_setting_check()")
    op.execute("ALTER TABLE complaint DROP COLUMN IF EXISTS reopen_reason, DROP COLUMN IF EXISTS clock_from, "
               "DROP COLUMN IF EXISTS reopened_at, DROP COLUMN IF EXISTS reopen_count")
    op.execute("ALTER TABLE sales_order DROP COLUMN IF EXISTS amend_reason, DROP COLUMN IF EXISTS amended_at, "
               "DROP COLUMN IF EXISTS amended_from_total, DROP COLUMN IF EXISTS amend_count")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
