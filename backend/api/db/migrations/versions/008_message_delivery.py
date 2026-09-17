"""008 message delivery: WhatsApp through 11za (FS-007)

What this migration does, in the order the spec's section 5 lists it:

* `auth_issue_otp_challenge()` is replaced in place (CREATE OR REPLACE keeps its
  grant to `app_anon`; a DROP would reset the ACL to PUBLIC-executable, executed in
  007). Two changes in the body, both after the cap and the lookup have passed and
  immediately before the outbox INSERT: any pending `auth.otp` row for the number
  that the worker has not already claimed is retired as `superseded`, and the new
  row is written with channel `whatsapp` (ADR-040). The SKIP LOCKED is what keeps a
  resend from waiting behind an in-flight send while holding the per-number lock,
  a wait that would exist only for registered numbers (plan review B-3, executed).
* `outbox_lead_withdrawn(citext)`: the worker's principal holds no matrix rows and
  `lead_res_perm` is restrictive on `leads.view`, so it reads zero leads (plan
  review B-1, executed). This definer answers the one question the worker has.
* `notification_outbox` gains DELETE for the system principal (the retention
  purge, rule 12) and four indexes: the purge's, the once-a-day acknowledgement
  check's, and the supersede lookup's two halves (the definer's on pending rows,
  the worker's on every row of the number).
* Pending rows the old definer wrote with channel `sms` become `whatsapp`, so the
  worker never meets a channel it has no adapter for at the switch (rule 14).

Revision ID: 008_message_delivery
Revises: 007_administration
Created: during development
"""
# ruff: noqa: E501

from __future__ import annotations

from alembic import op

revision: str = "008_message_delivery"
down_revision: str | None = "007_administration"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# ── grants and hand-written policies, read by tests/db/migration_grants.py ────

GRANTS: dict[str, str] = {
    "notification_outbox": "DELETE",
}

HAND_POLICIES: list[tuple[str, str]] = [
    # The retention purge runs as the system principal and nothing else deletes
    # from the outbox: it IS the record of what was attempted (003).
    ("notification_outbox", """CREATE POLICY notification_outbox_del ON notification_outbox FOR DELETE USING ((SELECT app_is_system()))"""),
]

INDEXES = [
    # The purge's predicate (created_at < cut AND state <> 'pending'): the existing
    # index is partial on state = 'pending' and cannot serve it.
    "CREATE INDEX ix_notification_outbox_created ON notification_outbox (created_at)",
    # Rule 10b: one acknowledgement per number per day.
    """CREATE INDEX ix_notification_outbox_ack_sent ON notification_outbox (recipient, sent_at)
        WHERE template_key = 'lead_ack' AND state = 'sent'""",
    # Rule 1a, the definer's half: the pending rows for a number.
    """CREATE INDEX ix_notification_outbox_otp_pending ON notification_outbox (recipient)
        WHERE template_key = 'auth.otp' AND state = 'pending'""",
    # Rule 1a, the worker's half: a newer code for the number whatever its state
    # (the newer row may already be sent). The partial index above cannot serve a
    # predicate without the state clause (code review F-4, executed: the planner
    # fell back to the purge's index and a filter over every later row).
    """CREATE INDEX ix_notification_outbox_otp_recipient ON notification_outbox
        (recipient, created_at) WHERE template_key = 'auth.otp'""",
]
INDEX_NAMES = ["ix_notification_outbox_created", "ix_notification_outbox_ack_sent",
               "ix_notification_outbox_otp_pending", "ix_notification_outbox_otp_recipient"]

# ── functions: new ────────────────────────────────────────────────────────────

FUNCTION_SIGS = [
    "outbox_lead_withdrawn(citext)",
]

FUNCTIONS: list[str] = [
    # Rule 10a. STABLE: one read. Refuses anyone but the system principal, so the
    # grant to app_role hands nobody an "is this enquiry withdrawn" oracle.
    """CREATE FUNCTION outbox_lead_withdrawn(p_inquiry_no citext) RETURNS boolean
    LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    DECLARE
        v_withdrawn boolean;
    BEGIN
        IF NOT app_is_system() THEN
            RAISE EXCEPTION 'outbox_lead_withdrawn is for the system principal'
                USING ERRCODE = '42501';
        END IF;
        SELECT (l.deleted_at IS NOT NULL OR l.merged_into_id IS NOT NULL)
          INTO v_withdrawn
          FROM lead l
         WHERE l.inquiry_no = p_inquiry_no;
        IF NOT FOUND THEN
            RETURN true;
        END IF;
        RETURN v_withdrawn;
    END $fn$""",
]

# ── functions: replaced, CREATE OR REPLACE with the signature unchanged ────────

AUTH_ISSUE_OTP_008 = """CREATE OR REPLACE FUNCTION auth_issue_otp_challenge(p_mobile text, p_ip inet,
                                                    p_code text, p_daily_cap int)
    RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    DECLARE
        v_user_id uuid;
        v_issued  int;
    BEGIN
        -- One function is NOT atomicity on its own, and rev 5 said it was.
        -- Two concurrent requests still both read nine and both issue, so a
        -- cap of ten admits eleven - the defect the composite function was
        -- introduced to fix. The advisory lock is what actually serialises
        -- them, per phone, for the length of the transaction (9.6 R5-8).
        -- Two-integer key, not a single 64-bit hash. There are three
        -- advisory-lock consumers in this schema now (1 = OTP by phone,
        -- 2 = a closure tree, 3 = a session family), and a single-key hash
        -- puts them all in one unpartitioned space where unrelated requests
        -- can serialise against each other. ISS-042, which predicted exactly
        -- this moment.
        PERFORM pg_advisory_xact_lock(1, hashtext(p_mobile));

        -- Counted since the most recent successful verify, which is what makes
        -- "a successful sign-in resets the cap" a mechanism rather than an
        -- assertion. GREATEST for the same reason as the lockout bound: a
        -- success older than 24 hours must not widen the window.
        SELECT count(*) INTO v_issued
          FROM login_attempt la
         WHERE la.identifier = p_mobile
           AND la.kind = 'otp_issue'
           AND la.attempted_at > greatest(
                   (SELECT max(s.attempted_at) FROM login_attempt s
                     WHERE s.identifier = p_mobile AND s.kind = 'otp'
                       AND s.succeeded),
                   now() - interval '24 hours');

        IF v_issued >= p_daily_cap THEN
            RETURN false;
        END IF;

        SELECT u.id INTO v_user_id
          FROM app_user u
         WHERE u.mobile = p_mobile
           AND u.deleted_at IS NULL
           AND u.user_type IN ('partner_user', 'consumer')
           AND u.is_active;

        IF NOT FOUND THEN
            RETURN false;
        END IF;

        -- succeeded is true meaning "a code was issued". This ledger records
        -- an issue, not an outcome; the column is NOT NULL and shared with the
        -- two ledgers that do record outcomes.
        INSERT INTO login_attempt (identifier, ip, succeeded, kind)
        VALUES (p_mobile, p_ip, true, 'otp_issue');

        -- FS-007 rule 1a. Only the newest code can arrive: an earlier code still
        -- waiting to be sent is retired here, after the cap and the lookup so a
        -- capped or unknown request burns nothing. SKIP LOCKED: a row the worker
        -- has claimed for sending is left alone, or this request would wait up to
        -- the send timeout behind the worker's row lock while holding the number's
        -- advisory lock, and that wait would exist only for registered numbers
        -- (plan review B-3, executed). The worker retires that row itself on its
        -- next claim (rule 1a, the worker's half).
        UPDATE notification_outbox
           SET state = 'dead', error = 'superseded', payload = '{}'::jsonb
         WHERE id IN (SELECT o.id
                        FROM notification_outbox o
                       WHERE o.state = 'pending'
                         AND o.template_key = 'auth.otp'
                         AND o.recipient = p_mobile
                         FOR UPDATE SKIP LOCKED);

        -- ADR-040: the code goes out on WhatsApp. The request itself is the
        -- opt-in, stated on the sign-in screen.
        INSERT INTO notification_outbox (channel, template_key, recipient, payload)
        VALUES ('whatsapp', 'auth.otp', p_mobile,
                jsonb_build_object('code', p_code));

        RETURN true;
    END $fn$"""

REPLACED: list[str] = [AUTH_ISSUE_OTP_008]

# 003's body, for the downgrade. CREATE OR REPLACE keeps the grant to app_anon.
AUTH_ISSUE_OTP_003 = """CREATE OR REPLACE FUNCTION auth_issue_otp_challenge(p_mobile text, p_ip inet,
                                                    p_code text, p_daily_cap int)
    RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    DECLARE
        v_user_id uuid;
        v_issued  int;
    BEGIN
        PERFORM pg_advisory_xact_lock(1, hashtext(p_mobile));

        SELECT count(*) INTO v_issued
          FROM login_attempt la
         WHERE la.identifier = p_mobile
           AND la.kind = 'otp_issue'
           AND la.attempted_at > greatest(
                   (SELECT max(s.attempted_at) FROM login_attempt s
                     WHERE s.identifier = p_mobile AND s.kind = 'otp'
                       AND s.succeeded),
                   now() - interval '24 hours');

        IF v_issued >= p_daily_cap THEN
            RETURN false;
        END IF;

        SELECT u.id INTO v_user_id
          FROM app_user u
         WHERE u.mobile = p_mobile
           AND u.deleted_at IS NULL
           AND u.user_type IN ('partner_user', 'consumer')
           AND u.is_active;

        IF NOT FOUND THEN
            RETURN false;
        END IF;

        INSERT INTO login_attempt (identifier, ip, succeeded, kind)
        VALUES (p_mobile, p_ip, true, 'otp_issue');

        INSERT INTO notification_outbox (channel, template_key, recipient, payload)
        VALUES ('sms', 'auth.otp', p_mobile,
                jsonb_build_object('code', p_code));

        RETURN true;
    END $fn$"""


def _sweep() -> None:
    """New functions are PUBLIC-executable until this runs; a migration's sweep does
    not reach a later migration's (cross-vendor B-6 on FS-003). Asserted, the way
    003a asserts it."""
    op.execute(
        """
        DO $$
        DECLARE v_public int;
        BEGIN
            REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
            SELECT count(*) INTO v_public
              FROM pg_proc p
              JOIN pg_namespace n ON n.oid = p.pronamespace
              LEFT JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e'
             WHERE n.nspname = 'public' AND d.objid IS NULL
               AND has_function_privilege('public', p.oid, 'EXECUTE');
            IF v_public > 0 THEN
                RAISE EXCEPTION '% project functions are PUBLIC-executable after the sweep', v_public;
            END IF;
        END $$
        """
    )


def upgrade() -> None:
    for stmt in INDEXES:
        op.execute(stmt)

    op.execute(f"GRANT DELETE ON notification_outbox TO {APP_ROLE}")
    for _table, stmt in HAND_POLICIES:
        op.execute(stmt)

    # The new function, then the replacement (which keeps its grant to app_anon).
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in FUNCTION_SIGS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    for stmt in REPLACED:
        op.execute(stmt)

    # Rule 14: rows the previous definer wrote seconds before this ran.
    op.execute("UPDATE notification_outbox SET channel = 'whatsapp' "
               "WHERE channel = 'sms' AND state = 'pending'")

    _sweep()


def downgrade() -> None:
    op.execute(AUTH_ISSUE_OTP_003)
    for sig in FUNCTION_SIGS:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP POLICY IF EXISTS notification_outbox_del ON notification_outbox")
    op.execute(f"REVOKE DELETE ON notification_outbox FROM {APP_ROLE}")
    for name in INDEX_NAMES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    # The converted rows stay whatsapp: a downgrade that turned them back would
    # hand the old worker rows it can send.
    _sweep()
