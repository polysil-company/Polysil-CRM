"""052: the consumer portal (FS-044).

- Setting `consumer_portal`, off by default. Switching it flips every live consumer
  account (only the rows that differ); switching off also bumps `token_version`, so
  sessions end and a farmer signs in afresh.
- A consumer `app_user` for every customer with an Indian mobile (the app_user shape
  has no plus), made by an AFTER INSERT trigger on customer and by a backfill. Active
  only while the portal is on; the setting is read FOR SHARE so a switch at the same
  moment waits. `ON CONFLICT (mobile) WHERE deleted_at IS NULL DO NOTHING`: a number
  that already signs in as staff or a dealer gets none (GAP-266). It never raises.
- The consumer floor: `app_is_consumer()` and one restrictive policy on every table
  with RLS on (api/authz/consumer_floor.py). A consumer keeps its own app_user and
  idempotency rows and nothing else.
- Portal reads as definers keyed on `portal_customer()`, and only on leads still on
  the customer's own number (plan review B-2).
- `customer.consent_channel` gains `portal`.

Revision ID: 052_consumer_portal
Revises: 050_customer_record
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision: str = "052_consumer_portal"
down_revision: str | None = "050_customer_record"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

_spec = importlib.util.spec_from_file_location(
    "consumer_floor_052", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

INDIAN = "^91[6-9][0-9]{9}$"

SEED = """INSERT INTO app_setting (key, kind, value, allowed, description) VALUES
('consumer_portal', 'choice', '"off"', '["off", "on"]',
 'Farmers sign in with a WhatsApp code and see their own enquiries, quotations, orders and complaints. On, every customer number can be sent a code.')
ON CONFLICT (key) DO NOTHING"""

CONSENT = [
    "ALTER TABLE customer DROP CONSTRAINT customer_consent_channel_check",
    "ALTER TABLE customer ADD CONSTRAINT customer_consent_channel_check "
    "CHECK (consent_channel IN ('whatsapp', 'form', 'verbal', 'written', 'portal'))",
]

FUNCTIONS = [
    # the floor's one question; a PK lookup, hoisted to an InitPlan by every policy
    """CREATE FUNCTION app_is_consumer() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM app_user WHERE id = app_current_user_id() AND user_type = 'consumer')
$fn$""",
    f"""CREATE FUNCTION customer_consumer_account() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_mobile text := ltrim(NEW.mobile, '+'); v_on boolean;
BEGIN
    IF v_mobile !~ '{INDIAN}' THEN
        RETURN NEW;
    END IF;
    -- FOR SHARE: a switch committing now waits for this insert, or this waits for it
    SELECT (value #>> '{{}}') = 'on' INTO v_on FROM app_setting WHERE key = 'consumer_portal' FOR SHARE;
    BEGIN
        INSERT INTO app_user (user_type, mobile, full_name, customer_id, is_active)
        VALUES ('consumer', v_mobile, left(NEW.name, 200), NEW.id, coalesce(v_on, false))
        ON CONFLICT (mobile) WHERE deleted_at IS NULL DO NOTHING;
    EXCEPTION WHEN check_violation OR unique_violation THEN
        NULL;   -- a qualification never fails for a portal account (edge case 2)
    END;
    RETURN NEW;
END $fn$""",
    """CREATE FUNCTION app_setting_consumer_portal() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_on boolean := (NEW.value #>> '{}') = 'on';
BEGIN
    UPDATE app_user SET is_active = v_on,
           token_version = token_version + CASE WHEN v_on THEN 0 ELSE 1 END
     WHERE user_type = 'consumer' AND deleted_at IS NULL AND is_active IS DISTINCT FROM v_on;
    RETURN NEW;
END $fn$""",
    # the signed-in consumer's customer while the portal is on, else null
    """CREATE FUNCTION portal_customer() RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT u.customer_id FROM app_user u
     WHERE u.id = app_current_user_id() AND u.user_type = 'consumer'
       AND u.is_active AND u.deleted_at IS NULL
       AND coalesce(app_setting_text('consumer_portal'), 'off') = 'on'
$fn$""",
    # the customer's live leads still on its own number (plan review B-2), and their
    # merge losers, whose documents show under the survivor (edge case 14)
    """CREATE FUNCTION portal_leads(p_customer uuid, p_with_losers boolean) RETURNS SETOF uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    WITH mine AS (
        SELECT l.id FROM lead l JOIN customer c ON c.id = l.customer_id AND c.mobile = l.mobile
         WHERE c.id = p_customer AND l.deleted_at IS NULL AND l.stage <> 'merged')
    SELECT id FROM mine
    UNION
    SELECT l.id FROM lead l WHERE p_with_losers AND l.merged_into_id IN (SELECT id FROM mine)
       AND l.deleted_at IS NULL
$fn$""",
    """CREATE FUNCTION portal_me() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT jsonb_build_object('name', c.name, 'mobile', c.mobile, 'email', c.email::text,
               'village', c.village, 'territory_name', t.name,
               'consent_given_at', c.consent_given_at, 'consent_channel', c.consent_channel)
      FROM customer c LEFT JOIN territory t ON t.id = c.territory_id
     WHERE c.id = portal_customer()
$fn$""",
    """CREATE FUNCTION portal_enquiries() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(jsonb_agg(x ORDER BY x->>'created_at' DESC), '[]') FROM (
        SELECT jsonb_build_object('inquiry_no', l.inquiry_no::text,
                   'status', CASE l.stage::text WHEN 'won' THEN 'won' WHEN 'lost' THEN 'closed'
                                  ELSE 'in_progress' END,
                   'system', ms.name, 'created_at', l.created_at) AS x
          FROM lead l JOIN mis_system ms ON ms.id = l.mis_system_id
         WHERE l.id IN (SELECT portal_leads(portal_customer(), false))
         ORDER BY l.created_at DESC LIMIT 100) s
$fn$""",
    """CREATE FUNCTION portal_quotations() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(jsonb_agg(x ORDER BY x->>'sent_at' DESC NULLS LAST), '[]') FROM (
        SELECT jsonb_build_object('quote_no', q.quote_no::text,
                   'status', CASE q.status::text WHEN 'accepted' THEN 'accepted'
                                  WHEN 'rejected' THEN 'closed' WHEN 'expired' THEN 'closed' ELSE 'sent' END,
                   -- a dealer's document carries the dealer's buying price (GAP-271)
                   'total', CASE WHEN q.partner_id IS NULL THEN q.total END,
                   'sent_at', q.sent_at, 'valid_until', q.valid_until,
                   'share_token', CASE WHEN q.partner_id IS NULL THEN q.share_token END) AS x
          FROM quotation q
         WHERE q.lead_id IN (SELECT portal_leads(portal_customer(), true))
           AND q.deleted_at IS NULL AND q.status <> 'draft' AND q.superseded_by_id IS NULL
         ORDER BY q.sent_at DESC NULLS LAST LIMIT 100) s
$fn$""",
    """CREATE FUNCTION portal_orders() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(jsonb_agg(x ORDER BY x->>'submitted_at' DESC NULLS LAST), '[]') FROM (
        SELECT jsonb_build_object('order_no', o.order_no::text,
                   'status', CASE o.status::text WHEN 'draft' THEN 'being_revised'
                                  WHEN 'partially_dispatched' THEN 'dispatched' WHEN 'dispatched' THEN 'dispatched'
                                  WHEN 'closed_short' THEN 'closed' WHEN 'cancelled' THEN 'cancelled'
                                  ELSE 'in_progress' END,
                   'total', CASE WHEN o.partner_id IS NULL THEN o.total END,
                   'submitted_at', o.submitted_at,
                   'dispatches', coalesce((SELECT jsonb_agg(jsonb_build_object('dc_no', d.dc_no,
                                                    'dispatched_at', d.dispatched_at) ORDER BY d.dispatched_at)
                                             FROM dispatch d WHERE d.sales_order_id = o.id AND d.voided_at IS NULL), '[]')) AS x
          FROM sales_order o
         WHERE o.lead_id IN (SELECT portal_leads(portal_customer(), true))
           AND o.deleted_at IS NULL AND o.order_no IS NOT NULL
         ORDER BY o.submitted_at DESC NULLS LAST LIMIT 100) s
$fn$""",
    """CREATE FUNCTION portal_complaints() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(jsonb_agg(x ORDER BY x->>'raised_at' DESC NULLS LAST), '[]') FROM (
        SELECT jsonb_build_object('complaint_no', c.complaint_no::text,
                   'status', CASE WHEN c.status::text IN ('closed', 'qc_rejected', 'cancelled') THEN 'closed'
                                  ELSE 'in_progress' END,
                   'raised_at', c.first_submitted_at) AS x
          FROM complaint c
         WHERE c.deleted_at IS NULL AND c.complaint_no IS NOT NULL AND c.status <> 'draft'
           AND (c.lead_id IN (SELECT portal_leads(portal_customer(), true))
                OR c.sales_order_id IN (SELECT o.id FROM sales_order o
                                         WHERE o.lead_id IN (SELECT portal_leads(portal_customer(), true))))
           -- never on a dealer's order (edge case 12)
           AND NOT EXISTS (SELECT 1 FROM sales_order o WHERE o.id = c.sales_order_id AND o.partner_id IS NOT NULL)
         ORDER BY c.first_submitted_at DESC LIMIT 100) s
$fn$""",
    """CREATE FUNCTION portal_set_consent(p_given boolean) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_customer uuid := portal_customer(); c customer%ROWTYPE;
BEGIN
    IF v_customer IS NULL THEN
        RAISE EXCEPTION 'portal off or not a consumer' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO c FROM customer WHERE id = v_customer FOR UPDATE;
    IF p_given AND c.consent_channel IS NOT DISTINCT FROM 'portal' THEN
        RETURN;          -- the first date stays (FS-041 edge case 13)
    END IF;
    IF NOT p_given AND c.consent_given_at IS NULL THEN
        RETURN;
    END IF;
    UPDATE customer SET consent_given_at = CASE WHEN p_given THEN now() END,
           consent_channel = CASE WHEN p_given THEN 'portal' END, updated_at = now()
     WHERE id = v_customer;
    -- CLAUDE.md rule 7: the consumer is the actor
    INSERT INTO activity_event (entity_type, entity_id, customer_id, kind, actor_id, payload)
    VALUES ('customer', v_customer, v_customer, 'customer.updated', app_current_user_id(),
            jsonb_build_object('name', c.name, 'actor_name', c.name, 'changed', '{}'::jsonb,
                               'consent', jsonb_build_object('from', c.consent_channel,
                                   'to', CASE WHEN p_given THEN 'portal' END,
                                   'was_given_at', c.consent_given_at)));
END $fn$""",
]

RELEASE = """CREATE FUNCTION consumer_release_mobile(p_mobile text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_id uuid; v_fam uuid; v_n int;
BEGIN
    IF NOT (app_has_permission('users', 'create') OR app_has_permission('users', 'edit')) THEN
        RETURN;
    END IF;
    SELECT id INTO v_id FROM app_user
     WHERE mobile = p_mobile AND user_type = 'consumer' AND deleted_at IS NULL FOR UPDATE;
    IF v_id IS NULL THEN
        RETURN;
    END IF;
    -- sessions first, as every deactivation path does (FS-006 cross-vendor P1), inline:
    -- auth_revoke_user_sessions() checks the users scope, which a consumer row has no
    -- anchor for, so a scoped admin would be refused (code review F-1). 007's lock order.
    FOR v_fam IN SELECT DISTINCT s.family_id FROM session s
                  WHERE s.user_id = v_id AND s.revoked_at IS NULL ORDER BY s.family_id LOOP
        PERFORM pg_advisory_xact_lock(3, hashtext(v_fam::text));
    END LOOP;
    WITH revoked AS (UPDATE session s SET revoked_at = now()
                      WHERE s.user_id = v_id AND s.revoked_at IS NULL RETURNING 1)
    SELECT count(*)::int INTO v_n FROM revoked;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('app_user', v_id, 'auth.sessions_revoked', app_current_user_id(), jsonb_build_object('sessions', v_n));
    UPDATE app_user SET deleted_at = now(), is_active = false, token_version = token_version + 1
     WHERE id = v_id;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('app_user', v_id, 'user.deleted', app_current_user_id(),
            jsonb_build_object('reason', 'mobile_reassigned',
                               'actor_name', coalesce((SELECT full_name FROM app_user WHERE id = app_current_user_id()), '')));
END $fn$"""

BACKFILL = f"""INSERT INTO app_user (user_type, mobile, full_name, customer_id, is_active)
SELECT 'consumer', ltrim(c.mobile, '+'), left(c.name, 200), c.id, false
  FROM customer c WHERE ltrim(c.mobile, '+') ~ '{INDIAN}'
ON CONFLICT (mobile) WHERE deleted_at IS NULL DO NOTHING"""

TRIGGERS = [
    "CREATE TRIGGER trg_customer_consumer_account AFTER INSERT ON customer FOR EACH ROW EXECUTE FUNCTION customer_consumer_account()",
    "CREATE TRIGGER trg_app_setting_consumer_portal AFTER UPDATE ON app_setting FOR EACH ROW "
    "WHEN (NEW.key = 'consumer_portal' AND NEW.value IS DISTINCT FROM OLD.value) "
    "EXECUTE FUNCTION app_setting_consumer_portal()",
]

GRANTED = ["app_is_consumer()", "portal_customer()", "portal_me()", "portal_enquiries()",
           "portal_quotations()", "portal_orders()", "portal_complaints()", "portal_set_consent(boolean)",
           "consumer_release_mobile(text)"]
INTERNAL = ["customer_consumer_account()", "app_setting_consumer_portal()", "portal_leads(uuid, boolean)"]

# No grant to app_anon: it reads no RLS table directly (every public path is a
# definer), as with the other policy helpers; test_migration_003 pins its list.


def _rls_tables() -> list[str]:
    rows = op.get_bind().execute(text(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity ORDER BY c.relname")).scalars()
    return [str(r) for r in rows]


def upgrade() -> None:
    op.execute(SEED)
    for stmt in CONSENT:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute(RELEASE)
    op.execute(BACKFILL)
    for stmt in TRIGGERS:
        op.execute(stmt)
    for table in _rls_tables():
        op.execute(floor.policy_sql(table))
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for table in _rls_tables():
        op.execute(f"DROP POLICY IF EXISTS {floor.name(table)} ON {table}")
    op.execute("DROP TRIGGER IF EXISTS trg_app_setting_consumer_portal ON app_setting")
    op.execute("DROP TRIGGER IF EXISTS trg_customer_consumer_account ON customer")
    op.execute("DELETE FROM activity_event WHERE entity_type = 'app_user' AND entity_id IN "
               "(SELECT id FROM app_user WHERE user_type = 'consumer')")
    op.execute("DELETE FROM app_user WHERE user_type = 'consumer'")
    op.execute("ALTER TABLE customer DROP CONSTRAINT customer_consent_channel_check")
    op.execute("UPDATE customer SET consent_given_at = NULL, consent_channel = NULL WHERE consent_channel = 'portal'")
    op.execute("ALTER TABLE customer ADD CONSTRAINT customer_consent_channel_check "
               "CHECK (consent_channel IN ('whatsapp', 'form', 'verbal', 'written'))")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DELETE FROM app_setting WHERE key = 'consumer_portal'")
