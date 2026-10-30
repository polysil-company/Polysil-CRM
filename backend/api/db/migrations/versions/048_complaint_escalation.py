"""048: complaint holidays and escalation (FS-028).

- `holiday`: one company calendar, readable by every signed-in caller (the
  invoker working-hours function reads it under the caller's claim), written
  only through `holiday_add` and `holiday_remove` under masters.edit, and only
  for days after today (IST).
- `complaint_add_working_hours` skips holidays like Sundays. The holidays are
  read once, and a run of more than 400 consecutive non-working days raises 22023
  rather than looping until the statement timeout (plan review B-2). The bound is
  on the run, not the whole target, so a long policy still computes (code review
  F-1). It and `complaint_due` become STABLE; nothing depends on their volatility.
- `complaint.response_escalated_at` and `resolution_escalated_at`, set once per
  due time by `complaint_escalate_due()` (the worker, as System) with one
  `complaint.escalated` event per target; cleared by a trigger when the due time
  moves. Targets already missed at deploy are stamped without an event.
- The bell: `complaint.escalated` joins the trigger (029's kinds, 026's quiet
  clause), and `notify_from_event` gets an arm whose recipients depend on the
  complaint's stage (plan review B-1).
- `complaint_reopen` under the `continue` clock stamps a target already past, so
  a fresh round does not ring for the old clock (GAP-248).

Revision ID: 048_complaint_escalation
Revises: 047_dealer_credit_limit
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
import pathlib
from types import ModuleType

from alembic import op
from sqlalchemy import text

revision: str = "048_complaint_escalation"
down_revision: str | None = "047_dealer_credit_limit"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
HORIZON_DAYS = 400   # consecutive non-working days; the Python twin carries the same bound


def _load(name: str) -> ModuleType:
    path = pathlib.Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_048", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_M029 = _load("029_notification_fixes")
KINDS_029: tuple[str, ...] = tuple(_M029.KINDS)
KINDS: tuple[str, ...] = (*KINDS_029, "complaint.escalated")   # the next migration extends this


def _trigger(kinds: tuple[str, ...]) -> str:
    return str(_load("026_complaint_remedies")._trigger(kinds, quiet_refund_close=True))


GRANTS: dict[str, str] = {"holiday": "SELECT"}

TABLES = [
    """CREATE TABLE holiday (
    day date PRIMARY KEY,
    id uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,   -- for activity_event and audit_row()
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 80),
    created_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_holiday_not_sunday CHECK (extract(isodow FROM day) <> 7)
)""",
    "CREATE TRIGGER trg_holiday_audit AFTER INSERT OR UPDATE OR DELETE ON holiday FOR EACH ROW EXECUTE FUNCTION audit_row()",
    "ALTER TABLE holiday ENABLE ROW LEVEL SECURITY",
]

# read by tests/db/migration_grants.py, so the policy-drift and grant tests see it
HAND_POLICIES: list[tuple[str, str]] = [
    ("holiday", "CREATE POLICY holiday_sel ON holiday FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"),
]

COLUMNS = [
    "ALTER TABLE complaint ADD COLUMN response_escalated_at timestamptz",
    "ALTER TABLE complaint ADD COLUMN resolution_escalated_at timestamptz",
]

INDEXES = [
    "CREATE INDEX ix_complaint_response_overdue ON complaint (response_due_at) "
    "WHERE responded_at IS NULL AND response_escalated_at IS NULL",
    "CREATE INDEX ix_complaint_resolution_overdue ON complaint (resolution_due_at) "
    "WHERE resolved_at IS NULL AND resolution_escalated_at IS NULL",
]

# 020's live text, kept to restore on downgrade
OLD_WORKING_HOURS = """CREATE OR REPLACE FUNCTION public.complaint_add_working_hours(p_start timestamp with time zone, p_hours integer)
 RETURNS timestamp with time zone
 LANGUAGE plpgsql
 IMMUTABLE STRICT
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    t timestamp := p_start AT TIME ZONE 'Asia/Kolkata';
    remaining interval := make_interval(hours => p_hours);
    e timestamp;
BEGIN
    IF p_hours < 0 THEN
        RAISE EXCEPTION 'hours must not be negative' USING ERRCODE = '22023';
    END IF;
    LOOP
        LOOP
            e := t::date + time '18:30';
            IF extract(isodow FROM t::date) <> 7 AND t < e THEN
                t := greatest(t, t::date + time '09:30');
                EXIT;
            END IF;
            t := (t::date + 1) + time '09:30';
        END LOOP;
        e := t::date + time '18:30';
        IF t + remaining <= e THEN
            RETURN (t + remaining) AT TIME ZONE 'Asia/Kolkata';
        END IF;
        remaining := remaining - (e - t);
        t := e;
    END LOOP;
END $function$"""

# the SQL twin of api/domain/complaints.add_working_hours; a test compares them
NEW_WORKING_HOURS = f"""CREATE OR REPLACE FUNCTION public.complaint_add_working_hours(p_start timestamp with time zone, p_hours integer)
 RETURNS timestamp with time zone
 LANGUAGE plpgsql
 STABLE STRICT
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    t timestamp := p_start AT TIME ZONE 'Asia/Kolkata';
    remaining interval := make_interval(hours => p_hours);
    e timestamp;
    v_skip int;
    -- read once: a day-by-day lookup per iteration would scan the table repeatedly
    v_off date[] := ARRAY(SELECT day FROM holiday WHERE day >= (p_start AT TIME ZONE 'Asia/Kolkata')::date);
BEGIN
    IF p_hours < 0 THEN
        RAISE EXCEPTION 'hours must not be negative' USING ERRCODE = '22023';
    END IF;
    LOOP
        v_skip := 0;
        LOOP
            e := t::date + time '18:30';
            IF extract(isodow FROM t::date) <> 7 AND NOT (t::date = ANY (v_off)) AND t < e THEN
                t := greatest(t, t::date + time '09:30');
                EXIT;
            END IF;
            -- a run of holidays must end the scan, not the statement (plan review B-2)
            v_skip := v_skip + 1;
            IF v_skip > {HORIZON_DAYS} THEN
                RAISE EXCEPTION 'no working day within {HORIZON_DAYS} days' USING ERRCODE = '22023';
            END IF;
            t := (t::date + 1) + time '09:30';
        END LOOP;
        e := t::date + time '18:30';
        IF t + remaining <= e THEN
            RETURN (t + remaining) AT TIME ZONE 'Asia/Kolkata';
        END IF;
        remaining := remaining - (e - t);
        t := e;
    END LOOP;
END $function$"""

FUNCTIONS = [
    """CREATE FUNCTION holiday_add(p_day date, p_name text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_id uuid; v_name text := NULLIF(btrim(p_name), '');
BEGIN
    IF NOT app_has_permission('masters', 'edit') THEN
        RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
    END IF;
    IF p_day <= (now() AT TIME ZONE 'Asia/Kolkata')::date THEN
        RAISE EXCEPTION 'a holiday must be after today' USING ERRCODE = 'HOLPS';
    END IF;
    IF extract(isodow FROM p_day) = 7 THEN
        RAISE EXCEPTION 'Sunday is already closed' USING ERRCODE = 'HOLSU';
    END IF;
    IF v_name IS NULL OR length(v_name) > 80 THEN
        RAISE EXCEPTION 'name a holiday in 1 to 80 characters' USING ERRCODE = '22023';
    END IF;
    INSERT INTO holiday (day, name, created_by) VALUES (p_day, v_name, app_current_user_id())
    ON CONFLICT (day) DO NOTHING RETURNING id INTO v_id;
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'that day is already a holiday' USING ERRCODE = 'HOLEX';
    END IF;
    -- unmapped in activity_event_sel: System reads it; the audit row keeps it too
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('holiday', v_id, 'holiday.added', app_current_user_id(),
            jsonb_build_object('day', p_day, 'name', v_name));
    RETURN v_id;
END $fn$""",
    """CREATE FUNCTION holiday_remove(p_day date) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE h holiday%ROWTYPE;
BEGIN
    IF NOT app_has_permission('masters', 'edit') THEN
        RAISE EXCEPTION 'not permitted' USING ERRCODE = '42501';
    END IF;
    IF p_day <= (now() AT TIME ZONE 'Asia/Kolkata')::date THEN
        -- a past holiday explains due times already stored (rule 3)
        RAISE EXCEPTION 'a past holiday stays' USING ERRCODE = 'HOLPS';
    END IF;
    DELETE FROM holiday WHERE day = p_day RETURNING * INTO h;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no such holiday' USING ERRCODE = 'HOLNF';
    END IF;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('holiday', h.id, 'holiday.removed', app_current_user_id(),
            jsonb_build_object('day', h.day, 'name', h.name));
END $fn$""",
    # A new due time is a new target: its stamp goes (a resubmit, a severity change
    # at the check, a restarted reopen)
    """CREATE FUNCTION complaint_escalation_reset() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NEW.response_due_at IS DISTINCT FROM OLD.response_due_at THEN
        NEW.response_escalated_at := NULL;
    END IF;
    IF NEW.resolution_due_at IS DISTINCT FROM OLD.resolution_due_at THEN
        NEW.resolution_escalated_at := NULL;
    END IF;
    RETURN NEW;
END $fn$""",
    "CREATE TRIGGER trg_complaint_escalation_reset BEFORE UPDATE OF response_due_at, resolution_due_at ON complaint "
    "FOR EACH ROW EXECUTE FUNCTION complaint_escalation_reset()",
    # Who hears of a missed target, by stage (plan review B-1). complaint_refusal
    # answers 'check' only while submitted, so with QC the QC managers and the
    # manager who gave the check are told instead. Asked as each candidate, as
    # notify_complaint_deciders does; the claim is restored on every path.
    """CREATE FUNCTION complaint_escalation_recipients(p_id uuid) RETURNS uuid[]
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_prev text := current_setting('app.current_user_id', true);
    c complaint%ROWTYPE; v_action text; v_out uuid[] := '{}'; v_lvl int[] := '{}'; v_ids uuid[] := '{}';
    v_min int; u record; i int;
BEGIN
    SELECT * INTO c FROM complaint WHERE id = p_id;
    v_out := array_append(v_out, c.owner_user_id);
    v_out := array_append(v_out, (SELECT d.decided_by FROM complaint_decision d
                                    WHERE d.complaint_id = p_id AND d.stage::text = 'check'
                                    ORDER BY d.decided_at DESC LIMIT 1));
    v_action := CASE c.status::text WHEN 'submitted' THEN 'check' WHEN 'under_qc' THEN 'qc' END;
    IF v_action IS NOT NULL THEN
        FOR u IN
            SELECT au.id, ro.level FROM app_user au
              JOIN role ro ON ro.id = au.role_id AND NOT ro.is_portal
                          AND (CASE v_action WHEN 'qc' THEN ro.is_functional ELSE NOT ro.is_functional END)
              JOIN role_permission rp ON rp.role_id = au.role_id AND rp.module = 'complaints'
                                     AND rp.action = 'approve' AND rp.deleted_at IS NULL
             WHERE au.user_type = 'staff' AND au.is_active AND au.deleted_at IS NULL
        LOOP
            PERFORM set_config('app.current_user_id', u.id::text, true);
            BEGIN
                IF complaint_refusal(p_id, v_action) IS NULL THEN
                    v_ids := v_ids || u.id; v_lvl := v_lvl || COALESCE(u.level, 0);
                END IF;
            EXCEPTION WHEN OTHERS THEN
                PERFORM set_config('app.current_user_id', COALESCE(v_prev, ''), true);
                RAISE;
            END;
            PERFORM set_config('app.current_user_id', COALESCE(v_prev, ''), true);
        END LOOP;
        SELECT min(x) INTO v_min FROM unnest(v_lvl) AS x;
        FOR i IN 1 .. COALESCE(array_length(v_ids, 1), 0) LOOP
            -- the check goes to the lowest level that may decide it, as its bell does
            IF v_action = 'qc' OR v_lvl[i] = v_min THEN
                v_out := array_append(v_out, v_ids[i]);
            END IF;
        END LOOP;
    END IF;
    RETURN ARRAY(SELECT DISTINCT x FROM unnest(v_out) AS x WHERE x IS NOT NULL);
END $fn$""",
    # The worker's sweep, as System only (the lead_dormant_sweep pattern)
    """CREATE FUNCTION complaint_escalate_due(p_now timestamptz, p_limit int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE r record; v_count int := 0; v_me uuid;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal escalates complaints' USING ERRCODE = '42501';
    END IF;
    IF app_setting_text('complaint_escalation') = 'off' THEN
        RETURN 0;
    END IF;
    v_me := app_current_user_id();
    FOR r IN
        SELECT * FROM (
            SELECT c.id, 'response'::text AS target, c.response_due_at AS due_at
              FROM complaint c
             WHERE c.status::text NOT IN ('draft', 'cancelled', 'closed') AND c.deleted_at IS NULL
               AND c.response_due_at < p_now AND c.responded_at IS NULL AND c.response_escalated_at IS NULL
            UNION ALL
            SELECT c.id, 'resolution', c.resolution_due_at
              FROM complaint c
             WHERE (c.status::text NOT IN ('draft', 'cancelled', 'closed')
                    -- a returned complaint's clock keeps running (GAP-248)
                    OR (c.status::text = 'draft' AND c.submit_count > 0))
               AND c.deleted_at IS NULL
               AND c.resolution_due_at < p_now AND c.resolved_at IS NULL AND c.resolution_escalated_at IS NULL
        ) due ORDER BY due_at LIMIT p_limit
    LOOP
        -- the row is re-checked under its lock: a QC verdict that won the race drops it
        PERFORM 1 FROM complaint c WHERE c.id = r.id AND c.deleted_at IS NULL
           AND (c.status::text NOT IN ('draft', 'cancelled', 'closed')
                OR (r.target = 'resolution' AND c.status::text = 'draft' AND c.submit_count > 0))
           AND CASE r.target WHEN 'response' THEN c.responded_at IS NULL AND c.response_escalated_at IS NULL
                             ELSE c.resolved_at IS NULL AND c.resolution_escalated_at IS NULL END
           FOR UPDATE SKIP LOCKED;           -- a cancel committed mid-run drops out (code review F-2)
        CONTINUE WHEN NOT FOUND;
        IF r.target = 'response' THEN
            UPDATE complaint SET response_escalated_at = p_now WHERE id = r.id;
        ELSE
            UPDATE complaint SET resolution_escalated_at = p_now WHERE id = r.id;
        END IF;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, partner_id, kind, actor_id, payload)
        SELECT 'complaint', c.id, c.lead_id, c.partner_id, 'complaint.escalated', v_me,
               jsonb_build_object('actor_name', 'System', 'target', r.target, 'due_at', r.due_at)
          FROM complaint c WHERE c.id = r.id;
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END $fn$""",
]

GRANTED = ["holiday_add(date, text)", "holiday_remove(date)", "complaint_escalate_due(timestamptz, integer)"]

SEED = """INSERT INTO app_setting (key, kind, value, allowed, min, max, description) VALUES
('complaint_escalation', 'choice', '"bell"', '["off", "bell"]', NULL, NULL,
 'When a complaint misses its response or resolution target: do nothing, or ring the bell for its owner and the managers handling it.')
ON CONFLICT (key) DO NOTHING"""

# targets already missed at deploy are history, not news (plan review R-3)
STAMP_OLD = [
    "UPDATE complaint SET response_escalated_at = now() WHERE response_due_at < now() AND responded_at IS NULL "
    "AND status::text NOT IN ('draft', 'cancelled', 'closed')",
    "UPDATE complaint SET resolution_escalated_at = now() WHERE resolution_due_at < now() AND resolved_at IS NULL "
    "AND (status::text NOT IN ('draft', 'cancelled', 'closed') OR (status::text = 'draft' AND submit_count > 0))",
]

_ARM_ANCHOR = """        ELSE
            NULL;
        END CASE;"""
_ARM = """        WHEN 'complaint.escalated' THEN
            -- FS-028: the owner and the managers at this stage, never the dealer
            SELECT complaint_no::text INTO v_label FROM complaint WHERE id = e.entity_id;
            v_title := 'Complaint ' || COALESCE(v_label, '') || ' missed its '
                       || COALESCE(e.payload ->> 'target', '') || ' target';
            FOREACH v_to IN ARRAY complaint_escalation_recipients(e.entity_id) LOOP
                PERFORM notify_one(e, v_to, 'complaint_escalated', v_title, NULL, 'complaint', e.entity_id, v_label, false);
            END LOOP;
"""
_REOPEN_ANCHOR = """           updated_by = v_me
     WHERE id = p_id;
    -- complaint.submitted, so the bell"""
_REOPEN_NEW = """           updated_by = v_me
     WHERE id = p_id;
    IF v_clock <> 'restart' THEN
        -- FS-028: the old clock continues, so a target already past is not a new miss
        UPDATE complaint
           SET response_escalated_at = CASE WHEN response_due_at < now()
                                            THEN COALESCE(response_escalated_at, now()) ELSE response_escalated_at END,
               resolution_escalated_at = CASE WHEN resolution_due_at < now()
                                              THEN COALESCE(resolution_escalated_at, now()) ELSE resolution_escalated_at END
         WHERE id = p_id;
    END IF;
    -- complaint.submitted, so the bell"""
PATCHES: list[tuple[str, list[tuple[str, str, int]]]] = [
    ("complaint_due", [("IMMUTABLE STRICT", "STABLE STRICT", 1)]),
    ("notify_from_event", [(_ARM_ANCHOR, _ARM + _ARM_ANCHOR, 1)]),
    ("complaint_reopen", [(_REOPEN_ANCHOR, _REOPEN_NEW, 1)]),
]


def _live(name: str) -> str:
    bind = op.get_bind()
    defs = bind.execute(text("SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                             "JOIN pg_namespace n ON n.oid = p.pronamespace "
                             "WHERE n.nspname = 'public' AND p.proname = :n"), {"n": name}).scalars().all()
    if len(defs) != 1:
        raise RuntimeError(f"048: expected one function {name}, found {len(defs)}")
    return str(defs[0])


def _apply(name: str, swaps: list[tuple[str, str, int]], *, reverse: bool) -> None:
    body = _live(name)
    for old, new, times in swaps:
        a, b = (new, old) if reverse else (old, new)
        if body.count(a) != times:
            raise RuntimeError(f"048: {name}: anchor found {body.count(a)} times, expected {times}: {a[:60]!r}")
        body = body.replace(a, b)
    op.execute(body)


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for stmt in COLUMNS:
        op.execute(stmt)
    if _live("complaint_add_working_hours").strip() != OLD_WORKING_HOURS.strip():
        raise RuntimeError("048: complaint_add_working_hours is not 020's text; patch from what is live")
    op.execute(NEW_WORKING_HOURS)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for name, swaps in PATCHES:
        _apply(name, swaps, reverse=False)
    for stmt in INDEXES:
        op.execute(stmt)
    for stmt in STAMP_OLD:                 # before the trigger could matter: due times do not change here
        op.execute(stmt)
    op.execute(SEED)
    op.execute("DROP TRIGGER trg_notify_from_event ON activity_event")
    op.execute(_trigger(KINDS))
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_notify_from_event ON activity_event")
    op.execute(_trigger(KINDS_029))
    op.execute("DELETE FROM notification WHERE kind = 'complaint_escalated'")
    op.execute("DELETE FROM activity_event WHERE kind IN ('complaint.escalated', 'holiday.added', 'holiday.removed')")
    op.execute("DELETE FROM activity_event WHERE kind = 'setting.changed' AND payload ->> 'key' = 'complaint_escalation'")
    op.execute("DELETE FROM app_setting WHERE key = 'complaint_escalation'")
    for name, swaps in reversed(PATCHES):
        _apply(name, swaps, reverse=True)
    op.execute("DROP TRIGGER IF EXISTS trg_complaint_escalation_reset ON complaint")
    for sig in ("complaint_escalate_due(timestamptz, integer)", "complaint_escalation_recipients(uuid)",
                "complaint_escalation_reset()", "holiday_remove(date)", "holiday_add(date, text)"):
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute(OLD_WORKING_HOURS)
    for name in ("ix_complaint_resolution_overdue", "ix_complaint_response_overdue"):
        op.execute(f"DROP INDEX IF EXISTS {name}")
    op.execute("ALTER TABLE complaint DROP COLUMN IF EXISTS resolution_escalated_at")
    op.execute("ALTER TABLE complaint DROP COLUMN IF EXISTS response_escalated_at")
    op.execute("DROP TABLE IF EXISTS holiday")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
