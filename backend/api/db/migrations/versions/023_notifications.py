"""023: in-app notifications (FS-018).

- `notification`: one row per person per event. Append-only apart from `read_at`,
  so no soft delete and no `updated_*` columns, like `activity_event`. The
  recipient reads and marks their own; `app_role` may change `read_at` only.
- `notification_failure`: one row when turning an event into notifications fails,
  so a fault there never blocks the business write, and is never silent (plan
  review B-3).
- `notify_from_event()`: an AFTER INSERT trigger on `activity_event`, a definer.
  Every path that writes an event notifies, API or not, in the same transaction.
  Who may decide is not rewritten here: the trigger asks `approval_refusal()` and
  `complaint_refusal()` as each candidate, swapping the claim for one question
  and restoring it (the pattern of `task_link_visible_as()`, 018).

Revision ID: 023_notifications
Revises: 022_timeline_actor_names
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "023_notifications"
down_revision: str | None = "022_timeline_actor_names"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# the kinds that notify; anything else never enters the function (review, cost)
KINDS = ("lead.created", "lead.assigned", "lead.note_added", "task.created", "task.reassigned",
         "order.submitted", "approval.decided", "quotation.approval_requested",
         "order.approved", "order.returned", "quotation.approval_approved",
         "quotation.approval_returned", "complaint.submitted", "complaint.approved",
         "complaint.returned", "complaint.qc_approved", "complaint.qc_rejected")

TABLES_SQL = [
    """CREATE TABLE notification (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,  -- people are soft-deleted; only tests hard-delete
    event_id uuid NOT NULL,
    kind text NOT NULL CHECK (kind ~ '^[a-z_]{1,40}$'),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
    body text CHECK (body IS NULL OR length(body) <= 500),
    actor_id uuid,
    actor_name text,
    resource_type text,
    resource_id uuid,
    resource_label text,
    created_at timestamptz NOT NULL DEFAULT now(),
    read_at timestamptz,
    CONSTRAINT uq_notification_event_recipient UNIQUE (event_id, recipient_id)
)""",
    "CREATE INDEX ix_notification_recipient ON notification (recipient_id, created_at DESC, id DESC)",
    "CREATE INDEX ix_notification_unread ON notification (recipient_id) WHERE read_at IS NULL",
    """CREATE TABLE notification_failure (
    id bigserial PRIMARY KEY,
    event_id uuid NOT NULL,
    kind text NOT NULL,
    sqlstate text NOT NULL,
    message text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
)""",
]

HAND_POLICIES: list[tuple[str, str]] = [
    ("notification", "CREATE POLICY notification_sel ON notification FOR SELECT USING (recipient_id = (SELECT app_current_user_id()))"),
    ("notification", "CREATE POLICY notification_upd ON notification FOR UPDATE USING (recipient_id = (SELECT app_current_user_id())) WITH CHECK (recipient_id = (SELECT app_current_user_id()))"),
]

GRANTS: dict[str, str] = {"notification": "SELECT, UPDATE (read_at)"}

FUNCTIONS = [
    # One notification. A dealer is never told who decided (question 15.14): the
    # actor is dropped at write time for a partner recipient (review B-2).
    """CREATE FUNCTION notify_one(p_event activity_event, p_to uuid, p_kind text, p_title text,
                                 p_body text, p_type text, p_resource uuid, p_label text,
                                 p_decided boolean) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_partner boolean; v_name text;
BEGIN
    IF p_to IS NULL OR p_to IS NOT DISTINCT FROM p_event.actor_id THEN RETURN; END IF;
    SELECT user_type = 'partner_user' INTO v_partner FROM app_user
     WHERE id = p_to AND is_active AND deleted_at IS NULL;
    IF v_partner IS NULL THEN RETURN; END IF;   -- inactive or gone
    v_name := COALESCE(p_event.payload ->> 'actor_name',
                       (SELECT full_name FROM app_user WHERE id = p_event.actor_id));
    INSERT INTO notification (recipient_id, event_id, kind, title, body, actor_id, actor_name,
                              resource_type, resource_id, resource_label)
    VALUES (p_to, p_event.id, p_kind, p_title, left(p_body, 500),
            CASE WHEN v_partner AND p_decided THEN NULL ELSE p_event.actor_id END,
            CASE WHEN v_partner AND p_decided THEN NULL ELSE v_name END,
            p_type, p_resource, p_label)
    ON CONFLICT (event_id, recipient_id) DO NOTHING;
END $fn$""",
    # Who may decide a waiting approval step: its role's holders the rule accepts,
    # asked as each of them (rule 3). The prefilter is the WhatsApp alert's (016).
    # With nobody of the role in the line, nobody is told (GAP-160).
    """CREATE FUNCTION notify_step(p_event activity_event, p_step uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_prev text := current_setting('app.current_user_id', true);
    s approval_step%ROWTYPE; r approval_request%ROWTYPE; u record; v_ok boolean;
    v_type text; v_label text; v_title text;
BEGIN
    SELECT * INTO s FROM approval_step WHERE id = p_step;
    SELECT * INTO r FROM approval_request WHERE id = s.request_id;
    IF r.doc_type = 'sales_order' THEN
        v_type := 'sales_order';
        SELECT COALESCE(order_no::text, 'a draft order') INTO v_label FROM sales_order WHERE id = r.entity_id;
        v_title := 'Order ' || v_label || ' waits for your approval';
    ELSE
        v_type := 'quotation';
        SELECT COALESCE(quote_no::text, 'the draft for ' || party_name) INTO v_label FROM quotation WHERE id = r.entity_id;
        v_title := 'A discount on ' || v_label || ' waits for your approval';
    END IF;
    FOR u IN
        SELECT au.id FROM app_user au
         WHERE au.role_id = s.approver_role_id AND au.user_type = 'staff'
           AND au.is_active AND au.deleted_at IS NULL AND au.id IS DISTINCT FROM r.requested_by
    LOOP
        PERFORM set_config('app.current_user_id', u.id::text, true);
        BEGIN
            v_ok := approval_refusal(p_step) IS NULL;
        EXCEPTION WHEN OTHERS THEN
            -- restore here, not only in the caller's handler (code review F-5)
            PERFORM set_config('app.current_user_id', COALESCE(v_prev, ''), true);
            RAISE;
        END;
        PERFORM set_config('app.current_user_id', COALESCE(v_prev, ''), true);
        IF v_ok THEN
            PERFORM notify_one(p_event, u.id, 'approval_requested', v_title, NULL, v_type, r.entity_id, v_label, false);
        END IF;
    END LOOP;
END $fn$""",
    # A complaint's check or QC: the candidates the rule accepts, asked as each.
    # A check goes to the lowest accepting line level only (rule 4, GAP-161).
    """CREATE FUNCTION notify_complaint_deciders(p_event activity_event, p_action text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_prev text := current_setting('app.current_user_id', true);
    u record; v_label text; v_min int; v_ok uuid[] := '{}'; v_lvl int[] := '{}'; i int;
BEGIN
    SELECT complaint_no::text INTO v_label FROM complaint WHERE id = p_event.entity_id;
    FOR u IN
        SELECT au.id, ro.level FROM app_user au
          JOIN role ro ON ro.id = au.role_id AND NOT ro.is_portal
                      AND (CASE p_action WHEN 'qc' THEN ro.is_functional ELSE NOT ro.is_functional END)
          JOIN role_permission rp ON rp.role_id = au.role_id AND rp.module = 'complaints'
                                 AND rp.action = 'approve' AND rp.deleted_at IS NULL
         WHERE au.user_type = 'staff' AND au.is_active AND au.deleted_at IS NULL
    LOOP
        PERFORM set_config('app.current_user_id', u.id::text, true);
        BEGIN
            IF complaint_refusal(p_event.entity_id, p_action) IS NULL THEN
                v_ok := v_ok || u.id; v_lvl := v_lvl || COALESCE(u.level, 0);
            END IF;
        EXCEPTION WHEN OTHERS THEN
            PERFORM set_config('app.current_user_id', COALESCE(v_prev, ''), true);
            RAISE;
        END;
        PERFORM set_config('app.current_user_id', COALESCE(v_prev, ''), true);
    END LOOP;
    SELECT min(x) INTO v_min FROM unnest(v_lvl) AS x;
    FOR i IN 1 .. COALESCE(array_length(v_ok, 1), 0) LOOP
        IF p_action = 'qc' OR v_lvl[i] = v_min THEN
            PERFORM notify_one(p_event, v_ok[i],
                CASE p_action WHEN 'qc' THEN 'complaint_to_qc' ELSE 'complaint_to_check' END,
                'Complaint ' || COALESCE(v_label, '') ||
                CASE p_action WHEN 'qc' THEN ' waits for the quality check' ELSE ' waits for your check' END,
                NULL, 'complaint', p_event.entity_id, v_label, false);
        END IF;
    END LOOP;
END $fn$""",
    # The trigger. Its own fault is logged and never blocks the write, except the
    # faults that mean an outage or a cancelled statement (review B-3).
    """CREATE FUNCTION notify_from_event() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    e activity_event := NEW; v_label text; v_owner uuid; v_title text; v_step uuid;
    v_req approval_request%ROWTYPE; v_who uuid; v_to uuid; v_state text; v_msg text;
BEGIN
    BEGIN
        CASE e.kind
        WHEN 'lead.created', 'lead.assigned', 'lead.note_added' THEN
            SELECT inquiry_no::text, owner_user_id, farmer_name INTO v_label, v_owner, v_msg
              FROM lead WHERE id = e.entity_id;
            IF e.kind = 'lead.assigned' THEN
                -- the payload, not the row: the two emitters order the event and the UPDATE differently
                IF e.payload ->> 'owner_user_id' ~* '^[0-9a-f-]{36}$' THEN
                    PERFORM notify_one(e, (e.payload ->> 'owner_user_id')::uuid, 'lead_assigned',
                                       'Lead ' || v_label || ' is now yours', NULL, 'lead', e.entity_id, v_label, false);
                END IF;
            ELSIF e.kind = 'lead.created' THEN
                PERFORM notify_one(e, v_owner, 'lead_assigned', 'Lead ' || v_label || ' is now yours',
                                   v_msg, 'lead', e.entity_id, v_label, false);
            ELSE
                PERFORM notify_one(e, v_owner, 'lead_note', 'A note on lead ' || v_label,
                                   e.payload ->> 'note', 'lead', e.entity_id, v_label, false);
            END IF;
        WHEN 'task.created', 'task.reassigned' THEN
            IF e.payload ->> 'assigned_to' ~* '^[0-9a-f-]{36}$' THEN
                SELECT title INTO v_label FROM task WHERE id = e.entity_id;
                PERFORM notify_one(e, (e.payload ->> 'assigned_to')::uuid, 'task_assigned',
                                   'A task for you', v_label, 'task', e.entity_id, v_label, false);
            END IF;
        WHEN 'order.submitted', 'quotation.approval_requested' THEN
            SELECT st.id INTO v_step FROM approval_step st
             WHERE st.request_id = (COALESCE(e.payload ->> 'request', e.payload ->> 'request_id'))::uuid
               AND st.decision IS NULL ORDER BY st.seq LIMIT 1;
            IF v_step IS NOT NULL THEN PERFORM notify_step(e, v_step); END IF;
        WHEN 'approval.decided' THEN
            -- only an approve moves the chain on; a reject returns it (review B-1)
            IF e.payload ->> 'decision' = 'approve' THEN
                SELECT st.id INTO v_step FROM approval_request ar
                  JOIN approval_step st ON st.request_id = ar.id
                 WHERE ar.doc_type = e.entity_type AND ar.entity_id = e.entity_id AND ar.status = 'pending'
                   AND st.decision IS NULL AND st.seq > (e.payload ->> 'seq')::int
                 ORDER BY st.seq LIMIT 1;
                IF v_step IS NOT NULL THEN PERFORM notify_step(e, v_step); END IF;
            END IF;
        WHEN 'order.approved', 'order.returned', 'quotation.approval_approved', 'quotation.approval_returned' THEN
            SELECT * INTO v_req FROM approval_request
             WHERE doc_type = e.entity_type AND entity_id = e.entity_id AND status <> 'pending'
             -- the request just decided: one pending at a time, so the latest (code review F-1)
             ORDER BY decided_at DESC NULLS LAST, created_at DESC, id DESC LIMIT 1;
            IF e.entity_type = 'sales_order' THEN
                SELECT COALESCE(order_no::text, 'your order'), owner_user_id INTO v_label, v_owner
                  FROM sales_order WHERE id = e.entity_id;
                v_title := 'Order ' || v_label || CASE WHEN e.kind = 'order.approved' THEN ' was approved' ELSE ' was returned' END;
                FOREACH v_to IN ARRAY ARRAY[v_req.requested_by, v_owner] LOOP
                    PERFORM notify_one(e, v_to, CASE WHEN e.kind = 'order.approved' THEN 'order_approved' ELSE 'order_returned' END,
                                       v_title, NULL, 'sales_order', e.entity_id, v_label, true);
                END LOOP;
            ELSE
                SELECT COALESCE(quote_no::text, 'the draft for ' || party_name) INTO v_label FROM quotation WHERE id = e.entity_id;
                PERFORM notify_one(e, v_req.requested_by,
                    CASE WHEN e.kind = 'quotation.approval_approved' THEN 'discount_approved' ELSE 'discount_returned' END,
                    'The discount on ' || v_label || CASE WHEN e.kind = 'quotation.approval_approved' THEN ' was approved' ELSE ' was returned' END,
                    NULL, 'quotation', e.entity_id, v_label, true);
            END IF;
        WHEN 'complaint.submitted' THEN
            PERFORM notify_complaint_deciders(e, 'check');
        WHEN 'complaint.approved' THEN
            PERFORM notify_complaint_deciders(e, 'qc');
            -- an owner picked at the check is told (review edge case 5)
            IF e.payload ->> 'owner_user_id' ~* '^[0-9a-f-]{36}$' THEN
                SELECT complaint_no::text INTO v_label FROM complaint WHERE id = e.entity_id;
                PERFORM notify_one(e, (e.payload ->> 'owner_user_id')::uuid, 'complaint_assigned',
                                   'Complaint ' || v_label || ' is now yours', NULL, 'complaint', e.entity_id, v_label, false);
            END IF;
        WHEN 'complaint.returned', 'complaint.qc_approved', 'complaint.qc_rejected' THEN
            SELECT complaint_no::text, owner_user_id, raised_by INTO v_label, v_owner, v_who
              FROM complaint WHERE id = e.entity_id;
            v_title := 'Complaint ' || COALESCE(v_label, '') || CASE e.kind
                WHEN 'complaint.returned' THEN ' was returned to you'
                WHEN 'complaint.qc_approved' THEN ' passed the quality check'
                ELSE ' failed the quality check' END;
            FOREACH v_to IN ARRAY ARRAY[v_who, v_owner] LOOP
                PERFORM notify_one(e, v_to, replace(e.kind, '.', '_'),
                                   v_title, NULL, 'complaint', e.entity_id, v_label, true);
            END LOOP;
        ELSE
            NULL;
        END CASE;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS v_state = RETURNED_SQLSTATE, v_msg = MESSAGE_TEXT;
        -- an outage, a cancel or a deadlock is the write's problem too
        IF left(v_state, 2) IN ('53', '57', '58', 'XX') OR v_state IN ('40001', '40P01') THEN
            RAISE;
        END IF;
        RAISE WARNING 'notify_from_event % on %: % %', e.kind, e.id, v_state, v_msg;
        INSERT INTO notification_failure (event_id, kind, sqlstate, message)
        VALUES (e.id, e.kind, v_state, left(v_msg, 1000));
    END;
    RETURN NULL;
END $fn$""",
    "CREATE TRIGGER trg_notify_from_event AFTER INSERT ON activity_event FOR EACH ROW "
    "WHEN (NEW.kind IN (" + ", ".join(f"'{k}'" for k in KINDS) + ")) EXECUTE FUNCTION notify_from_event()",
]

INTERNAL = ["notify_one(activity_event, uuid, text, text, text, text, uuid, text, boolean)",
            "notify_step(activity_event, uuid)", "notify_complaint_deciders(activity_event, text)",
            "notify_from_event()"]


def upgrade() -> None:
    for stmt in TABLES_SQL:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("ALTER TABLE notification ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notification_failure ENABLE ROW LEVEL SECURITY")   # no policy: owner only
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_notify_from_event ON activity_event")
    for sig in INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP TABLE IF EXISTS notification_failure")
    op.execute("DROP TABLE IF EXISTS notification")
