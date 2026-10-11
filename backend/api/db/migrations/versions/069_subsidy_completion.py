"""069: subsidy completion (FS-055).

- A subsidised order is paid by the farmer's share: `order_owed()` replaces the
  inline owed expression in the six definers that carry it (GAP-450).
- The buyer's order confirmation and the farmer portal show that share (GAP-451).
- `subsidy_dispatched_on()`: the first dispatch date for an application's lead (GAP-176).
- Stage entries name the fields they filled; the bell tells the owners of a return,
  a query, a failed trial run, a close, a cancel and a reopen (GAP-178).
- `subsidy_application_reopen()`: a closed application opens again (GAP-175).
- `exact_area_match_required` revised to 0 for sprinkler from today (GAP-076).

Every edit is made on the function's LIVE text with a counted anchor; nothing is
rebuilt from an earlier migration's source (064's lesson).

Revision ID: 069_subsidy_completion
Revises: 068_product_category_history
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import re

from alembic import op
from sqlalchemy import text

revision: str = "069_subsidy_completion"
down_revision: str | None = "068_product_category_history"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
MARK = "069_subsidy_completion"   # subsidy_parameter.external_id of the revision row

# ── A: the farmer total and the amount owed ──────────────────────────────────

FUNCTIONS = [
    """CREATE FUNCTION order_farmer_total(p_order uuid) RETURNS numeric
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    -- FS-055 rule 1: the farmer's share on a subsidised order with a block; else the total
    SELECT CASE WHEN o.order_type::text = 'subsidised' AND s.sales_order_id IS NOT NULL
                -- never below 0 nor above the order (EC-6, EC-12)
                THEN GREATEST(0, LEAST(o.total, COALESCE(s.farmer_payable,
                                                         COALESCE(s.material_amount, o.total) - s.subsidy_amount)))
                ELSE o.total END
      FROM sales_order o LEFT JOIN order_subsidy s ON s.sales_order_id = o.id
     WHERE o.id = p_order
$fn$""",
    """CREATE FUNCTION order_owed(p_order uuid) RETURNS numeric
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT order_farmer_total(p_order)
           - COALESCE((SELECT sum(b.amount) FROM scheme_benefit b
                        WHERE b.sales_order_id = p_order AND b.status = 'applied'), 0)
$fn$""",
    # GAP-176: read by the application list as the caller, who may not see the order
    """CREATE FUNCTION subsidy_dispatched_on(p_lead uuid) RETURNS date
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT min((d.dispatched_at AT TIME ZONE 'Asia/Kolkata')::date)
      FROM sales_order o JOIN dispatch d ON d.sales_order_id = o.id AND d.voided_at IS NULL
     WHERE o.order_type::text = 'subsidised' AND o.status::text <> 'cancelled' AND o.deleted_at IS NULL
       AND (o.lead_id = p_lead
            OR o.id IN (SELECT l.sales_order_id FROM order_subsidy_lead l WHERE l.lead_id = p_lead))
       -- a date only for a caller who sees an application on the lead (plan review S-2)
       AND EXISTS (SELECT 1 FROM subsidy_application a
                    WHERE a.lead_id = p_lead AND subsidy_application_visible(a.id))
$fn$""",
    """CREATE FUNCTION subsidy_application_reopen(p_app uuid, p_reason text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a subsidy_application%ROWTYPE;
BEGIN
    IF NOT app_has_permission('subsidy', 'approve') OR app_current_partner() IS NOT NULL THEN
        RAISE EXCEPTION 'subsidy.approve required' USING ERRCODE = '42501';
    END IF;
    IF NOT subsidy_application_visible(p_app) THEN
        RAISE EXCEPTION 'application not found' USING ERRCODE = 'SAPAN';
    END IF;
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'SAPRM';
    END IF;
    SELECT * INTO a FROM subsidy_application WHERE id = p_app FOR UPDATE;
    IF a.status <> 'full_fp_received' THEN
        RAISE EXCEPTION 'the application is %', a.status USING ERRCODE = 'SAPOP';
    END IF;
    -- a settled commission was paid on these figures (EC-2)
    IF EXISTS (SELECT 1 FROM dealer_commission c WHERE c.application_id = p_app
                AND c.status::text IN ('approved', 'paid')) THEN
        RAISE EXCEPTION 'the commission is settled' USING ERRCODE = 'SAPCM';
    END IF;
    UPDATE subsidy_application
       SET status = 'open', closed_at = NULL, full_fp_received_on = NULL, updated_by = app_current_user_id()
     WHERE id = p_app;
    PERFORM subsidy_event(p_app, 'subsidy.reopened',
                          jsonb_build_object('reason', btrim(p_reason), 'was_closed_on', a.full_fp_received_on));
END $fn$""",
]
SIGNATURES = ["order_farmer_total(uuid)", "order_owed(uuid)", "subsidy_dispatched_on(uuid)",
              "subsidy_application_reopen(uuid, text)"]
GRANTED = ["subsidy_dispatched_on(uuid)", "subsidy_application_reopen(uuid, text)"]

# The six definers and how many owed expressions each holds today.
OWED_IN = {
    "order_payment_position(uuid, date)": 1,
    "partner_credit_exposure(uuid)": 1,
    "order_payment_schedule_set(uuid, jsonb)": 3,
    "payment_apply(payment, jsonb, boolean)": 1,
    "dealer_rating(uuid)": 1,
    "order_paid_at(uuid)": 1,
}
OWED = re.compile(r"(?P<a>\bs?o)\.total\s*-\s*COALESCE\(\(SELECT sum\(b\.amount\) FROM scheme_benefit b\s+"
                  r"WHERE b\.sales_order_id = (?P=a)\.id AND b\.status = 'applied'\), 0\)")
OWED_BACK = re.compile(r"order_owed\((?P<a>s?o)\.id\)")


def _owed_text(alias: str) -> str:
    return (f"{alias}.total - COALESCE((SELECT sum(b.amount) FROM scheme_benefit b "
            f"WHERE b.sales_order_id = {alias}.id AND b.status = 'applied'), 0)")


# ── B: what the farmer sees ──────────────────────────────────────────────────

CONFIRMED_OLD = "'order_no', o.order_no, 'total', inr_text(o.total)"
CONFIRMED_NEW = "'order_no', o.order_no, 'total', inr_text(order_farmer_total(o.id))"
PORTAL_OLD = "'total', CASE WHEN o.partner_id IS NULL THEN o.total END"
PORTAL_NEW = "'total', CASE WHEN o.partner_id IS NULL THEN order_farmer_total(o.id) END"

# ── D: the stage event names its fields; the bell ────────────────────────────

STAGE_OLD = "jsonb_build_object('stage', s.code, 'seq', s.seq, 'occurred_on', p_occurred,"
STAGE_NEW = ("jsonb_build_object('stage', s.code, 'seq', s.seq, 'occurred_on', p_occurred,\n"
             "                                             'fields', (SELECT COALESCE(jsonb_agg(f.key ORDER BY f.key), '[]'::jsonb)\n"
             "                                                          FROM jsonb_each(COALESCE(p_values, '{}'::jsonb)) f\n"
             "                                                         WHERE f.value <> 'null'::jsonb),")

# EC-3: an entry closes the file only when it writes an amount that pairs with a
# date, or such a date; a correction elsewhere after a reopen leaves it open
CLOSE_OLD = "    IF v_paid > 0 AND v_paid = v_dated THEN"
CLOSE_NEW = ("""    IF v_paid > 0 AND v_paid = v_dated AND EXISTS (
           SELECT 1 FROM subsidy_stage_field f JOIN subsidy_stage_def d ON d.id = f.stage_def_id
            WHERE d.scheme_id = a.scheme_id AND f.pairs_with_key IS NOT NULL AND f.is_active
              AND COALESCE(p_values, '{}'::jsonb) ?| ARRAY[f.field_key, f.pairs_with_key]) THEN""")

NEW_KINDS = ("subsidy.stage_recorded", "subsidy.closed", "subsidy.cancelled", "subsidy.reopened")
TRIGGER_OLD = "'complaint.escalated'::text]"
TRIGGER_NEW = "'complaint.escalated'::text, " + ", ".join(f"'{k}'::text" for k in NEW_KINDS) + "]"

RETURNED = ("return_to_field", "tech_return_to_field")
QUERIED = ("app_query", "tech_query", "query_1", "query_2", "query_3", "fp_query_received")
TR_FAILED = ("tr_not_ok",)


def _arr(keys: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{k}'" for k in keys) + "]"


NOTIFY_ANCHOR = """        ELSE
            NULL;
        END CASE;"""
NOTIFY_BLOCK = f"""        WHEN 'subsidy.stage_recorded', 'subsidy.closed', 'subsidy.cancelled', 'subsidy.reopened' THEN
            -- FS-055 rule 13: the application's owner and the lead's owner
            SELECT a.application_no::text, a.owner_user_id, l.owner_user_id INTO v_label, v_owner, v_who
              FROM subsidy_application a LEFT JOIN lead l ON l.id = a.lead_id AND l.deleted_at IS NULL
             WHERE a.id = e.entity_id;
            v_title := NULL;
            IF e.kind = 'subsidy.stage_recorded' THEN
                IF COALESCE(e.payload -> 'fields', '[]'::jsonb) ?| {_arr(RETURNED)} THEN
                    v_title := 'Subsidy file ' || v_label || ' was sent back to the field'; v_msg := 'subsidy_returned';
                ELSIF COALESCE(e.payload -> 'fields', '[]'::jsonb) ?| {_arr(QUERIED)} THEN
                    v_title := 'Subsidy file ' || v_label || ' has a query from the department'; v_msg := 'subsidy_query';
                ELSIF COALESCE(e.payload -> 'fields', '[]'::jsonb) ?| {_arr(TR_FAILED)} THEN
                    v_title := 'Subsidy file ' || v_label || ' failed the trial run'; v_msg := 'subsidy_tr_failed';
                END IF;
            ELSE
                v_msg := replace(e.kind, '.', '_');
                v_title := 'Subsidy file ' || v_label || CASE e.kind
                    WHEN 'subsidy.closed' THEN ' is closed'
                    WHEN 'subsidy.cancelled' THEN ' was cancelled'
                    ELSE ' was reopened' END;
            END IF;
            IF v_title IS NOT NULL THEN
                -- staff only: a dealer's user owns leads but holds no subsidy view
                FOR v_to IN SELECT u.id FROM app_user u
                             WHERE u.id IN (v_owner, v_who) AND u.user_type = 'staff' LOOP
                    PERFORM notify_one(e, v_to, v_msg, v_title, e.payload ->> 'reason',
                                       'subsidy_application', e.entity_id, v_label, false);
                END LOOP;
            END IF;
"""

# ── F: the sprinkler area flag ───────────────────────────────────────────────

_TODAY = "(now() AT TIME ZONE 'Asia/Kolkata')::date"
PARAM_UP = [
    # the old row ends today, half-open, as the masters revision endpoint writes it;
    # it ends first, or the new row overlaps it (ex_subsidy_parameter_one_system).
    # Only the rows this ended get a successor (code review F-7).
    """CREATE TEMP TABLE _069_closed (scheme_id uuid, system_type subsidy_system_type, key text,
        unit subsidy_param_unit) ON COMMIT DROP""",
    f"""WITH ended AS (
        UPDATE subsidy_parameter p SET effective_to = {_TODAY}
         WHERE p.key = 'exact_area_match_required' AND p.system_type::text = 'sprinkler' AND p.deleted_at IS NULL
           AND p.value <> 0 AND p.effective_to IS NULL AND p.effective_from < {_TODAY}
        RETURNING p.scheme_id, p.system_type, p.key, p.unit)
        INSERT INTO _069_closed SELECT scheme_id, system_type, key, unit FROM ended""",
    f"""INSERT INTO subsidy_parameter (scheme_id, system_type, key, value, unit, effective_from, external_id, source_system)
        SELECT c.scheme_id, c.system_type, c.key, 0, c.unit, {_TODAY}, '{MARK}', 'crm' FROM _069_closed c""",
]
PARAM_DOWN = [
    # the revision row goes first, or the reopened old row overlaps it
    f"""CREATE TEMP TABLE _069_ended ON COMMIT DROP AS
        SELECT scheme_id, system_type, key, effective_from FROM subsidy_parameter WHERE external_id = '{MARK}'""",
    f"DELETE FROM subsidy_parameter WHERE external_id = '{MARK}'",
    """UPDATE subsidy_parameter p SET effective_to = NULL
          FROM _069_ended n
         WHERE p.scheme_id = n.scheme_id AND p.system_type = n.system_type
           AND p.key = n.key AND p.effective_to = n.effective_from""",
]


def _def(sig: str) -> str:
    return str(op.get_bind().execute(text(
        f"SELECT pg_get_functiondef('{sig}'::regprocedure)")).scalar_one())


def _swap(sig: str, old: str, new: str, times: int = 1) -> None:
    body = _def(sig)
    if body.count(old) != times:
        raise RuntimeError(f"069: {sig} anchor found {body.count(old)} times, wanted {times}")
    op.execute(body.replace(old, new))


def _owed_swap(forward: bool) -> None:
    for sig, times in OWED_IN.items():
        body = _def(sig)
        pattern = OWED if forward else OWED_BACK
        found = len(pattern.findall(body))
        if found != times:
            raise RuntimeError(f"069: {sig} holds {found} owed expressions, wanted {times}")
        if forward:
            body = pattern.sub(lambda m: f"order_owed({m.group('a')}.id)", body)
        else:
            body = pattern.sub(lambda m: _owed_text(m.group("a")), body)
        op.execute(body)


def _trigger(old: str, new: str) -> None:
    ddl = str(op.get_bind().execute(text(
        "SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE tgname = 'trg_notify_from_event' "
        "AND tgrelid = 'activity_event'::regclass")).scalar_one())
    if ddl.count(old) != 1:
        raise RuntimeError(f"069: trg_notify_from_event anchor found {ddl.count(old)} times")
    op.execute("DROP TRIGGER trg_notify_from_event ON activity_event")
    op.execute(ddl.replace(old, new))


def upgrade() -> None:
    for ddl in FUNCTIONS:
        op.execute(ddl)
    for sig in SIGNATURES:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    _owed_swap(forward=True)
    _swap("order_notify_outcome(uuid, text)", CONFIRMED_OLD, CONFIRMED_NEW)
    _swap("portal_orders()", PORTAL_OLD, PORTAL_NEW)
    _swap("subsidy_stage_record(uuid, text, date, jsonb, text)", STAGE_OLD, STAGE_NEW)
    _swap("subsidy_stage_record(uuid, text, date, jsonb, text)", CLOSE_OLD, CLOSE_NEW)
    _swap("notify_from_event()", NOTIFY_ANCHOR, NOTIFY_BLOCK + NOTIFY_ANCHOR)
    _trigger(TRIGGER_OLD, TRIGGER_NEW)
    for sql in PARAM_UP:
        op.execute(sql)


def downgrade() -> None:
    for sql in PARAM_DOWN:
        op.execute(sql)
    _trigger(TRIGGER_NEW, TRIGGER_OLD)
    _swap("notify_from_event()", NOTIFY_BLOCK + NOTIFY_ANCHOR, NOTIFY_ANCHOR)
    _swap("subsidy_stage_record(uuid, text, date, jsonb, text)", CLOSE_NEW, CLOSE_OLD)
    _swap("subsidy_stage_record(uuid, text, date, jsonb, text)", STAGE_NEW, STAGE_OLD)
    _swap("portal_orders()", PORTAL_NEW, PORTAL_OLD)
    _swap("order_notify_outcome(uuid, text)", CONFIRMED_NEW, CONFIRMED_OLD)
    _owed_swap(forward=False)
    for sig in reversed(SIGNATURES):
        op.execute(f"DROP FUNCTION {sig}")
