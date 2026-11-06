"""082: email notices and the morning summary (FS-078, REQ-007, REQ-303).

- `app_user.email_notices`, `app_user.email_morning`: each person's two switches,
  both on by default (GAP-537).
- `notification.email_queued_at`: set once, when a notice goes into an email.
  A partial index finds the unread, unqueued ones.
- `email_morning_sent (user_id, ist_day)`: one summary per person per day, however
  many runs overlap (EC-11). RLS on with the consumer floor and no other policy,
  no grant: only definers touch it.
- Two outbox indexes, one per claim (plan review SF-1): WhatsApp claims
  `channel <> 'email'`, the email drain claims by template.
- Definers, 008's pattern. The four System ones raise 42501 for anyone else:
  - `email_notice_collect(int)`: picks recipients, takes an advisory lock per
    person (namespace 10, plan review B-1), queues their notices and writes one
    outbox row each. One transaction; no SMTP inside it.
  - `email_notice_resolve(uuid, uuid[])`: at send, the address and the notices
    still unread. No row means the person is no longer eligible.
  - `email_morning_collect(date)`: one summary row per eligible person with an
    open task due today or overdue. Skips Sundays and holidays.
  - `email_morning_resolve(uuid)`: at send, the address while still eligible.
  - `email_morning_sent_purge(date)`: retention, beside the outbox purge.
  - `me_email_preferences_set(bool, bool)`: the caller's own switches. A definer
    because `app_user_upd_perm` needs users.edit. Consumers are refused.

Revision ID: 082_email_notices
Revises: 081_forecast_indexes
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "082_email_notices"
down_revision: str | None = "081_forecast_indexes"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

_spec = importlib.util.spec_from_file_location(
    "consumer_floor_082", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)
LOCK_NAMESPACE = 10        # 1 OTP, 2 closure, 3 session family, 4 handover, 5 lead ack
LISTED = 20                # rule 3: at most 20 notices listed in one email

# The address check is the sender's (`ADDRESS_RE` in api/integrations/email/provider.py,
# held equal by a test): one ASCII addr-spec, none of the characters that would make
# it a list or a header (EC-5, ISS-221, code review F-4).
ADDRESS_RE = r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$"
_ADDRESS = "u.email ~ '" + ADDRESS_RE.replace("'", "''") + "'"

# Who may get email at all (spec section 5): active staff, or an active partner
# user whose partner is open. Never a consumer (rule 6).
ELIGIBLE = f"""u.is_active AND u.deleted_at IS NULL
           AND u.user_type IN ('staff', 'partner_user')
           AND u.email IS NOT NULL AND {_ADDRESS}
           AND (u.user_type = 'staff' OR EXISTS (
                SELECT 1 FROM channel_partner p
                 WHERE p.id = u.partner_id AND p.is_active AND p.deleted_at IS NULL))"""

# Rules 1 and 2, on the database's clock (EC-26)
WINDOW = ("n.created_at <= now() - interval '10 minutes' "
          "AND n.created_at > now() - interval '24 hours'")

SCHEMA = [
    "ALTER TABLE app_user ADD COLUMN email_notices boolean NOT NULL DEFAULT true",
    "ALTER TABLE app_user ADD COLUMN email_morning boolean NOT NULL DEFAULT true",
    "ALTER TABLE notification ADD COLUMN email_queued_at timestamptz",
    "CREATE INDEX ix_notification_email_due ON notification (created_at) "
    "WHERE email_queued_at IS NULL AND read_at IS NULL",
    """CREATE TABLE email_morning_sent (
    user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    ist_day date NOT NULL,
    PRIMARY KEY (user_id, ist_day)
)""",
    "CREATE INDEX ix_email_morning_sent_day ON email_morning_sent (ist_day)",
    "ALTER TABLE email_morning_sent ENABLE ROW LEVEL SECURITY",
    "CREATE INDEX ix_notification_outbox_due_not_email ON notification_outbox (next_attempt_at) "
    "WHERE state = 'pending' AND channel <> 'email'",
    "CREATE INDEX ix_notification_outbox_due_email ON notification_outbox (template_key, next_attempt_at) "
    "WHERE state = 'pending' AND channel = 'email'",
]

_SYSTEM_ONLY = """    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal' USING ERRCODE = '42501';
    END IF;"""

FUNCTIONS = [
    f"""CREATE FUNCTION email_notice_collect(p_limit int) RETURNS int
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    r       record;
    v_ids   uuid[];
    v_total int;
    v_n     int := 0;
BEGIN
{_SYSTEM_ONLY}
    -- a loop, so the try-lock is taken only on a recipient actually handled
    -- (delta re-check note); never a row lock on app_user (plan review B-1)
    FOR r IN
        SELECT n.recipient_id AS id
          FROM notification n
          JOIN app_user u ON u.id = n.recipient_id
         WHERE n.email_queued_at IS NULL AND n.read_at IS NULL AND {WINDOW}
           AND u.email_notices AND {ELIGIBLE}
         GROUP BY n.recipient_id
         -- the longest waiting first, so a limit never starves the same people (F-7)
         ORDER BY min(n.created_at), n.recipient_id
    LOOP
        EXIT WHEN v_n >= p_limit;
        CONTINUE WHEN NOT pg_try_advisory_xact_lock({LOCK_NAMESPACE}, hashtext(r.id::text));
        -- every eligible notice is queued, listed or not (EC-9); only the ids this
        -- UPDATE actually took go in the row
        WITH q AS (
            UPDATE notification SET email_queued_at = now()
             WHERE id IN (SELECT n.id FROM notification n
                           WHERE n.recipient_id = r.id AND {WINDOW}
                             AND n.read_at IS NULL AND n.email_queued_at IS NULL
                           ORDER BY n.id FOR UPDATE SKIP LOCKED)
            RETURNING id, created_at)
        SELECT (array_agg(id ORDER BY created_at DESC, id DESC))[1:{LISTED}], count(*)
          INTO v_ids, v_total FROM q;
        IF v_total > 0 THEN
            INSERT INTO notification_outbox (channel, template_key, recipient, payload)
            VALUES ('email', 'email_notices', r.id::text,
                    jsonb_build_object('ids', to_jsonb(v_ids), 'total', v_total));
            v_n := v_n + 1;
        END IF;
    END LOOP;
    RETURN v_n;
END $fn$""",
    f"""CREATE FUNCTION email_notice_resolve(p_user uuid, p_ids uuid[])
RETURNS TABLE (email text, full_name text, user_type text, notice_id uuid, title text,
               created_at timestamptz, resource_type text, resource_id uuid)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
{_SYSTEM_ONLY}
    -- no row: not eligible any more. One row with a null notice: all read (EC-1, EC-3)
    RETURN QUERY
    SELECT u.email::text, u.full_name, u.user_type::text, n.id, n.title, n.created_at,
           n.resource_type, n.resource_id
      FROM app_user u
      -- rule 2 at send too: a notice past 24 hours is never emailed (code review F-5)
      LEFT JOIN notification n ON n.recipient_id = u.id AND n.id = ANY (p_ids) AND n.read_at IS NULL
                              AND n.created_at > now() - interval '24 hours'
     WHERE u.id = p_user AND u.email_notices AND {ELIGIBLE}
     ORDER BY n.created_at DESC NULLS LAST, n.id DESC;
END $fn$""",
    f"""CREATE FUNCTION email_morning_collect(p_day date) RETURNS int
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_day   date := coalesce(p_day, (now() AT TIME ZONE 'Asia/Kolkata')::date);
    v_start timestamptz;
    v_end   timestamptz;
    r       record;
    v_n     int := 0;
BEGIN
{_SYSTEM_ONLY}
    -- Monday to Saturday, not on a company holiday (EC-33)
    IF extract(isodow FROM v_day) = 7 OR EXISTS (SELECT 1 FROM holiday WHERE day = v_day) THEN
        RETURN 0;
    END IF;
    v_start := v_day::timestamp AT TIME ZONE 'Asia/Kolkata';
    v_end := (v_day + 1)::timestamp AT TIME ZONE 'Asia/Kolkata';
    -- ORDER BY id, so two overlapping runs wait rather than deadlock (delta note)
    FOR r IN
        SELECT u.id,
               count(*) FILTER (WHERE t.due_at >= v_start) AS due_today,
               count(*) FILTER (WHERE t.due_at < v_start) AS overdue
          FROM app_user u
          JOIN task t ON t.assigned_to = u.id AND t.status = 'open' AND t.due_at < v_end
         WHERE u.email_morning AND {ELIGIBLE}
         GROUP BY u.id
         ORDER BY u.id
    LOOP
        INSERT INTO email_morning_sent (user_id, ist_day) VALUES (r.id, v_day)
        ON CONFLICT DO NOTHING;
        IF FOUND THEN
            INSERT INTO notification_outbox (channel, template_key, recipient, payload)
            VALUES ('email', 'email_morning', r.id::text,
                    jsonb_build_object('day', v_day, 'due_today', r.due_today, 'overdue', r.overdue));
            v_n := v_n + 1;
        END IF;
    END LOOP;
    RETURN v_n;
END $fn$""",
    f"""CREATE FUNCTION email_morning_resolve(p_user uuid)
RETURNS TABLE (email text, full_name text, user_type text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
{_SYSTEM_ONLY}
    RETURN QUERY
    SELECT u.email::text, u.full_name, u.user_type::text FROM app_user u
     WHERE u.id = p_user AND u.email_morning AND {ELIGIBLE};
END $fn$""",
    f"""CREATE FUNCTION email_morning_sent_purge(p_cut date) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
{_SYSTEM_ONLY}
    DELETE FROM email_morning_sent WHERE ist_day < p_cut;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END $fn$""",
    """CREATE FUNCTION me_email_preferences_set(p_notices boolean, p_morning boolean)
RETURNS TABLE (notices boolean, morning_summary boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_user uuid := app_current_user_id();
BEGIN
    IF v_user IS NULL OR p_notices IS NULL OR p_morning IS NULL THEN
        RAISE EXCEPTION 'no caller' USING ERRCODE = '42501';
    END IF;
    -- the caller's own row only, and never a consumer (EC-21)
    UPDATE app_user SET email_notices = p_notices, email_morning = p_morning
     WHERE id = v_user AND user_type IN ('staff', 'partner_user')
       AND is_active AND deleted_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'not a staff or partner user' USING ERRCODE = '42501';
    END IF;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('app_user', v_user, 'user.email_preferences_changed', v_user,
            jsonb_build_object('notices', p_notices, 'morning_summary', p_morning));
    RETURN QUERY SELECT p_notices, p_morning;
END $fn$""",
]

COLLECT = "email_notice_collect(integer)"
RESOLVE = "email_notice_resolve(uuid, uuid[])"
MORNING = "email_morning_collect(date)"
MORNING_RESOLVE = "email_morning_resolve(uuid)"
PURGE = "email_morning_sent_purge(date)"
PREFERENCES = "me_email_preferences_set(boolean, boolean)"
SIGNATURES = (COLLECT, RESOLVE, MORNING, MORNING_RESOLVE, PURGE, PREFERENCES)


def upgrade() -> None:
    for stmt in SCHEMA:
        op.execute(stmt)
    op.execute(floor.policy_sql("email_morning_sent"))
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in SIGNATURES:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for sig in SIGNATURES:
        op.execute(f"DROP FUNCTION {sig}")
    op.execute("DROP INDEX ix_notification_outbox_due_email")
    op.execute("DROP INDEX ix_notification_outbox_due_not_email")
    op.execute("DROP TABLE email_morning_sent")
    op.execute("DROP INDEX ix_notification_email_due")
    op.execute("ALTER TABLE notification DROP COLUMN email_queued_at")
    op.execute("ALTER TABLE app_user DROP COLUMN email_morning")
    op.execute("ALTER TABLE app_user DROP COLUMN email_notices")
