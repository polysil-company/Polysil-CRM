"""015: public lead capture, the website form and QR codes (FS-003a).

- `lead_qr_code`: a printed code that credits a lead to a dealer or campaign,
  read by staff through the leads scope and by the public through a definer.
- `lead.qr_code_id`: which code brought the lead.
- `lead_intake_challenge`: the WhatsApp code that proves the mobile. No grant
  and no policy for either role; only the definers below touch it.
- The intake principal: a staff user "Website and QR" on the role `intake`,
  holding leads view, create and edit at global, and partners view. Its claim is set only by
  `intake_session` in api/deps.py, after the code matched (FS-003a §5, plan review
  B-1). A trigger keeps a password, a mobile or another role off its row, so it
  can never sign in.
- Definers granted to `app_anon` (the pre-auth role): issue and consume a code,
  the form's lists, a territory's children, a QR code's label. Granted to
  `app_role`: recording the lead a code created (intake only) and the purge
  (system only).

Codes are serialised per number under an advisory lock in namespace 5 (1 is the
sign-in code, 4 the administrator floor), transaction-scoped, so PgBouncer's
transaction pooling is safe.

Revision ID: 015_public_lead_capture
Revises: 014_document_people
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "015_public_lead_capture"
down_revision: str | None = "014_document_people"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
ANON_ROLE = "app_anon"
# uuid5(NAMESPACE_DNS, "polysil.intake"); Settings.intake_user_id carries it
INTAKE_USER_ID = "3f962ae5-f0d3-5583-91b5-5cea037139fc"
SYSTEM_ORG_ID = "a1c3b0dd-6f0c-5f0e-8c1c-1b4f2f6a9e51"  # 005

TABLES = [
    """CREATE TABLE lead_qr_code (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL,
    label text NOT NULL,
    campaign text,
    partner_id uuid REFERENCES channel_partner(id),
    territory_id uuid REFERENCES territory(id),
    owner_org_unit_id uuid NOT NULL REFERENCES org_unit(id),
    is_active boolean NOT NULL DEFAULT true,
    created_by uuid REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid REFERENCES app_user(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_lead_qr_code_code UNIQUE (code),
    CONSTRAINT ck_lead_qr_code_shape CHECK (code ~ '^[A-HJ-NP-Z2-9]{6}$'),
    CONSTRAINT ck_lead_qr_code_label CHECK (length(btrim(label)) BETWEEN 1 AND 120),
    CONSTRAINT ck_lead_qr_code_campaign CHECK (campaign IS NULL OR length(campaign) <= 120)
)""",
    """CREATE TABLE lead_intake_challenge (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    mobile text NOT NULL,
    code_hash text NOT NULL,
    expires_at timestamptz NOT NULL,
    attempts int NOT NULL DEFAULT 0,
    state text NOT NULL DEFAULT 'pending',
    ip inet,
    lead_id uuid REFERENCES lead(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_lead_intake_state CHECK (state IN ('pending', 'consumed', 'burned', 'superseded'))
)""",
]

INDEXES = [
    "CREATE INDEX ix_lead_qr_code_partner ON lead_qr_code (partner_id)",
    "CREATE INDEX ix_lead_qr_code_owner_org_unit ON lead_qr_code (owner_org_unit_id)",
    "CREATE INDEX ix_lead_qr_code_territory ON lead_qr_code (territory_id)",
    "CREATE INDEX ix_lead_intake_mobile ON lead_intake_challenge (mobile, created_at DESC)",
    "CREATE INDEX ix_lead_intake_ip ON lead_intake_challenge (ip, created_at DESC)",
    "CREATE INDEX ix_lead_intake_created ON lead_intake_challenge (created_at)",
]

# The leads scope, applied to a code through its owning unit, territory or partner.
_QR_VISIBLE = """((SELECT app_scope('leads')) = 'global'
  OR ((SELECT app_scope('leads')) IN ('own', 'org_subtree')
      AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('leads')) = 'territory'
      AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('leads')) = 'partner_subtree'
      AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))))"""

HAND_POLICIES: list[tuple[str, str]] = [
    ("lead_qr_code", f"CREATE POLICY lead_qr_code_sel ON lead_qr_code FOR SELECT USING ({_QR_VISIBLE})"),
    ("lead_qr_code", "CREATE POLICY lead_qr_code_sel_perm ON lead_qr_code AS RESTRICTIVE FOR SELECT USING ((SELECT app_has_permission('leads', 'view')))"),
    ("lead_qr_code", f"CREATE POLICY lead_qr_code_ins ON lead_qr_code FOR INSERT WITH CHECK ((SELECT app_has_permission('leads', 'create')) AND created_by = (SELECT app_current_user_id()) AND {_QR_VISIBLE})"),
    ("lead_qr_code", f"CREATE POLICY lead_qr_code_upd ON lead_qr_code FOR UPDATE USING ({_QR_VISIBLE}) WITH CHECK ({_QR_VISIBLE})"),
    ("lead_qr_code", "CREATE POLICY lead_qr_code_upd_perm ON lead_qr_code AS RESTRICTIVE FOR UPDATE USING ((SELECT app_has_permission('leads', 'edit')))"),
    # activity_event gains the lead_qr_code arm (api/authz/activity.py ENTITY_BY_ID);
    # supersedes 013's literal, and the drift test compares the union's last-wins
    ("activity_event", """CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (
  CASE entity_type
    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)
    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)
    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)
    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)
    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)
    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)
    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order c WHERE c.id = entity_id)
    WHEN 'lead_qr_code' THEN EXISTS (SELECT 1 FROM lead_qr_code c WHERE c.id = entity_id)
    ELSE (SELECT app_is_system())
  END
)"""),
]

POLICIES = [
    "ALTER TABLE lead_qr_code ENABLE ROW LEVEL SECURITY",
    *(stmt for table, stmt in HAND_POLICIES if table == "lead_qr_code"),
    # enabled with no policy: neither role reads or writes a challenge directly
    "ALTER TABLE lead_intake_challenge ENABLE ROW LEVEL SECURITY",
]

GRANTS = {"lead_qr_code": "SELECT, INSERT, UPDATE"}

PRINCIPAL = [
    """INSERT INTO role (code, name, level, is_functional, is_portal)
VALUES ('intake', 'Website and QR intake', 5, true, false)
ON CONFLICT (code) DO NOTHING""",
    f"""INSERT INTO app_user (id, user_type, email, full_name, role_id, org_unit_id, is_active)
SELECT '{INTAKE_USER_ID}', 'staff', 'intake@polysil.internal', 'Website and QR', r.id, '{SYSTEM_ORG_ID}', true
  FROM role r WHERE r.code = 'intake'
ON CONFLICT (id) DO UPDATE SET is_active = true, deleted_at = NULL, role_id = EXCLUDED.role_id""",
    """INSERT INTO role_permission (role_id, module, action, scope)
SELECT r.id, 'leads', a::permission_action, 'global' FROM role r, unnest(ARRAY['view', 'create', 'edit']) a
 WHERE r.code = 'intake'
ON CONFLICT (role_id, module, action) DO UPDATE SET scope = EXCLUDED.scope""",
    # a QR code's partner becomes the lead's assigned partner, and the lead's parent
    # guard refuses a partner the caller cannot see: read-only, every partner
    """INSERT INTO role_permission (role_id, module, action, scope)
SELECT r.id, 'partners', 'view', 'global' FROM role r WHERE r.code = 'intake'
ON CONFLICT (role_id, module, action) DO UPDATE SET scope = EXCLUDED.scope""",
    # the principal's row never gains a way to sign in, and never changes role
    f"""CREATE FUNCTION refuse_intake_principal_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    -- deleting, switching off or moving it would leave the public form creating
    -- leads under a dead actor (code review F-3)
    IF OLD.id = '{INTAKE_USER_ID}' AND (NEW.password_hash IS NOT NULL OR NEW.mobile IS NOT NULL
            OR NEW.role_id IS DISTINCT FROM OLD.role_id OR NEW.user_type IS DISTINCT FROM OLD.user_type
            OR NEW.deleted_at IS NOT NULL OR NOT NEW.is_active
            OR NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id) THEN
        RAISE EXCEPTION 'the intake principal is not administrable' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END $fn$""",
    "CREATE TRIGGER trg_refuse_intake_principal_edit BEFORE UPDATE ON app_user FOR EACH ROW EXECUTE FUNCTION refuse_intake_principal_edit()",
]

FUNCTIONS = [
    # the code: rate limits, the global ceiling, supersede, challenge, outbox row
    """CREATE FUNCTION lead_intake_issue(p_mobile text, p_ip inet, p_code text, p_code_hash text,
                                  p_ttl_seconds int, p_ip_per_hour int, p_codes_per_hour int)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    -- The IP and hourly budgets are shared across mobiles, so the mobile's lock
    -- alone let two numbers pass both counts before either committed (cross-vendor
    -- review). Namespace 6 is the public code budget, taken first; consume takes
    -- only the mobile's, so the order cannot cycle. A few hundred codes an hour
    -- through one lock is nothing.
    PERFORM pg_advisory_xact_lock(6, 0);
    PERFORM pg_advisory_xact_lock(5, hashtext(p_mobile));
    SELECT count(*) INTO v_n FROM lead_intake_challenge
     WHERE mobile = p_mobile AND created_at > now() - interval '15 minutes';
    IF v_n >= 3 THEN RETURN 'rate_limited'; END IF;
    SELECT count(*) INTO v_n FROM lead_intake_challenge
     WHERE mobile = p_mobile AND created_at > now() - interval '24 hours';
    IF v_n >= 10 THEN RETURN 'rate_limited'; END IF;
    SELECT count(*) INTO v_n FROM lead_intake_challenge
     WHERE ip IS NOT DISTINCT FROM p_ip AND created_at > now() - interval '1 hour';
    IF v_n >= p_ip_per_hour THEN RETURN 'rate_limited'; END IF;
    -- FS-003a rule 9: the global ceiling answers like success and writes nothing
    SELECT count(*) INTO v_n FROM lead_intake_challenge WHERE created_at > now() - interval '1 hour';
    IF v_n >= p_codes_per_hour THEN RETURN 'suppressed'; END IF;

    UPDATE lead_intake_challenge SET state = 'superseded'
     WHERE mobile = p_mobile AND state = 'pending';
    -- the sign-in code's rule 1a: only the newest code can arrive
    UPDATE notification_outbox SET state = 'dead', error = 'superseded', payload = '{}'::jsonb
     WHERE id IN (SELECT o.id FROM notification_outbox o
                   WHERE o.state = 'pending' AND o.template_key = 'lead.verify'
                     AND o.recipient = p_mobile FOR UPDATE SKIP LOCKED);
    INSERT INTO lead_intake_challenge (mobile, code_hash, expires_at, ip)
    VALUES (p_mobile, p_code_hash, clock_timestamp() + make_interval(secs => p_ttl_seconds), p_ip);
    INSERT INTO notification_outbox (channel, template_key, recipient, payload, created_at, next_attempt_at)
    VALUES ('whatsapp', 'lead.verify', p_mobile, jsonb_build_object('code', p_code),
            clock_timestamp(), clock_timestamp());
    RETURN 'issued';
END $fn$""",
    # never raises for a wrong code, so the attempt count commits (FS-003a EC-3)
    """CREATE FUNCTION lead_intake_consume(p_mobile text, p_code_hash text)
RETURNS TABLE (outcome text, challenge_id uuid, inquiry_no text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE c lead_intake_challenge%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(5, hashtext(p_mobile));
    SELECT * INTO c FROM lead_intake_challenge
     WHERE mobile = p_mobile AND state IN ('pending', 'consumed')
     ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
    IF NOT FOUND OR c.expires_at <= now() THEN
        RETURN QUERY SELECT 'invalid'::text, NULL::uuid, NULL::text; RETURN;
    END IF;
    IF c.state = 'consumed' THEN
        -- a lost 201: the same code again within its life answers the lead it made
        IF c.code_hash = p_code_hash AND c.lead_id IS NOT NULL THEN
            RETURN QUERY SELECT 'replay'::text, c.id, (SELECT l.inquiry_no::text FROM lead l WHERE l.id = c.lead_id);
        ELSE
            -- counted like a pending code's, or a used code could be guessed for
            -- its whole life to learn the inquiry number (code review F-5)
            UPDATE lead_intake_challenge
               SET attempts = attempts + 1,
                   state = CASE WHEN attempts + 1 >= 5 THEN 'burned' ELSE state END
             WHERE id = c.id;
            RETURN QUERY SELECT 'invalid'::text, NULL::uuid, NULL::text;
        END IF;
        RETURN;
    END IF;
    IF c.code_hash <> p_code_hash THEN
        UPDATE lead_intake_challenge
           SET attempts = attempts + 1,
               state = CASE WHEN attempts + 1 >= 5 THEN 'burned' ELSE state END
         WHERE id = c.id;
        RETURN QUERY SELECT 'invalid'::text, NULL::uuid, NULL::text; RETURN;
    END IF;
    UPDATE lead_intake_challenge SET state = 'consumed' WHERE id = c.id;
    RETURN QUERY SELECT 'ok'::text, c.id, NULL::text;
END $fn$""",
    f"""CREATE FUNCTION lead_intake_record(p_challenge uuid, p_lead uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF app_current_user_id() IS DISTINCT FROM '{INTAKE_USER_ID}'::uuid THEN
        RAISE EXCEPTION 'only the intake principal records a public lead' USING ERRCODE = '42501';
    END IF;
    UPDATE lead_intake_challenge SET lead_id = p_lead WHERE id = p_challenge AND state = 'consumed';
END $fn$""",
    """CREATE FUNCTION lead_intake_purge(p_cut timestamptz) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal purges' USING ERRCODE = '42501';
    END IF;
    DELETE FROM lead_intake_challenge WHERE created_at < p_cut;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END $fn$""",
    """CREATE FUNCTION lead_qr_public(p_code text)
RETURNS TABLE (code text, label text, campaign text, territory_id uuid, partner_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT q.code::text, q.label, q.campaign, q.territory_id, q.partner_id
      FROM lead_qr_code q
      LEFT JOIN channel_partner cp ON cp.id = q.partner_id
     WHERE q.code = p_code::citext AND q.is_active
       AND (q.partner_id IS NULL OR (cp.is_active AND cp.deleted_at IS NULL))
$fn$""",
    """CREATE FUNCTION lead_public_form() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT jsonb_build_object(
        'states', COALESCE((SELECT jsonb_agg(jsonb_build_object('id', t.id, 'name', t.name) ORDER BY t.name)
                              FROM territory t WHERE t.level = 'state' AND t.deleted_at IS NULL
                               AND t.code IS NOT NULL), '[]'::jsonb),
        'mis_systems', COALESCE((SELECT jsonb_agg(jsonb_build_object('code', m.code, 'name', m.name) ORDER BY m.name)
                                   FROM mis_system m WHERE m.is_active AND m.deleted_at IS NULL), '[]'::jsonb),
        'inquiry_types', jsonb_build_array('commercial', 'subsidised', 'industrial'))
$fn$""",
    """CREATE FUNCTION lead_public_territories(p_parent uuid)
RETURNS TABLE (id uuid, name text, level text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT t.id, t.name::text, t.level::text FROM territory t
     WHERE t.parent_id = p_parent AND t.deleted_at IS NULL
     ORDER BY t.name LIMIT 200
$fn$""",
]

ANON_SIGS = ["lead_intake_issue(text, inet, text, text, integer, integer, integer)",
             "lead_intake_consume(text, text)", "lead_qr_public(text)", "lead_public_form()",
             "lead_public_territories(uuid)"]
ROLE_SIGS = ["lead_intake_record(uuid, uuid)", "lead_intake_purge(timestamptz)"]


def _m007_text(name: str) -> str:
    """007's text of one function, found among its module-level strings."""
    path = Path(__file__).with_name("007_administration.py")
    spec = importlib.util.spec_from_file_location("mig_007_for_015", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("015: migration 007 not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    prefix = f"CREATE OR REPLACE FUNCTION {name}("
    for value in vars(mod).values():
        for item in value if isinstance(value, list | tuple) else [value]:
            if isinstance(item, str) and item.lstrip().startswith(prefix):
                return item
    raise RuntimeError(f"015: {name} not found in 007")


# The intake account's role holds leads edit, so 007's assignee rule admitted it:
# an admin saw "Website and QR" in the lead owner picker and could hand it leads
# (the ISS-075 shape; found after the code review). Both functions leave it out.
_ASSIGNEE_PATCHES = {
    "authz_user_assignable": ("WHERE u.id = p_user_id AND u.user_type = 'staff' AND u.is_active",
                              f"WHERE u.id = p_user_id AND u.user_type = 'staff' AND u.is_active\n"
                              f"        AND u.id <> '{INTAKE_USER_ID}'"),
    "staff_directory": ("WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL",
                        f"WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL\n"
                        f"           AND u.id <> '{INTAKE_USER_ID}'"),
}


def _assignee_functions(patched: bool) -> list[str]:
    out = []
    for name, (old, new) in _ASSIGNEE_PATCHES.items():
        body = _m007_text(name)
        if body.count(old) != 1:
            raise RuntimeError(f"015: 007's {name} changed; anchor not found once")
        out.append(body.replace(old, new) if patched else body)
    return out


def upgrade() -> None:
    op.execute("ALTER TABLE lead ADD COLUMN qr_code_id uuid")
    for stmt in TABLES:
        op.execute(stmt)
    op.execute("ALTER TABLE lead ADD CONSTRAINT fk_lead_qr_code FOREIGN KEY (qr_code_id) REFERENCES lead_qr_code(id)")
    op.execute("CREATE INDEX ix_lead_qr_code_id ON lead (qr_code_id)")
    for stmt in INDEXES + POLICIES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for stmt in PRINCIPAL + FUNCTIONS:
        op.execute(stmt)
    for sig in ANON_SIGS + ROLE_SIGS + ["refuse_intake_principal_edit()"]:
        op.execute(f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC")
    for sig in ANON_SIGS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {ANON_ROLE}")
    for sig in ROLE_SIGS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    for stmt in _assignee_functions(patched=True):
        op.execute(stmt)
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(next(stmt for table, stmt in HAND_POLICIES if table == "activity_event"))
    op.execute("SELECT assert_role_permission_invariants()")


def _m013_event_policy() -> str:
    path = Path(__file__).with_name("013_orders_approvals_dispatch.py")
    spec = importlib.util.spec_from_file_location("mig_013_for_015", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("015: migration 013 not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return next(stmt for table, stmt in mod.HAND_POLICIES if table == "activity_event")


def downgrade() -> None:
    for stmt in _assignee_functions(patched=False):
        op.execute(stmt)
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(_m013_event_policy())
    op.execute("DELETE FROM activity_event WHERE entity_type = 'lead_qr_code'")
    for sig in ANON_SIGS + ROLE_SIGS:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP TRIGGER IF EXISTS trg_refuse_intake_principal_edit ON app_user")
    op.execute("DROP FUNCTION IF EXISTS refuse_intake_principal_edit()")
    # Once a public lead exists, the account is the actor on its events, audit rows
    # and stamps, which many columns reference. History is not erased on a
    # downgrade: the account and its role stay, switched off (code review F-7).
    op.execute(f"""
        DO $$
        BEGIN
            DELETE FROM app_user WHERE id = '{INTAKE_USER_ID}';
            DELETE FROM role_permission WHERE role_id = (SELECT id FROM role WHERE code = 'intake');
            DELETE FROM role WHERE code = 'intake';
        EXCEPTION WHEN foreign_key_violation THEN
            UPDATE app_user SET is_active = false WHERE id = '{INTAKE_USER_ID}';
            RAISE NOTICE 'the intake account is referenced; kept and switched off';
        END $$
    """)
    op.execute("DROP INDEX IF EXISTS ix_lead_qr_code_id")
    op.execute("ALTER TABLE lead DROP CONSTRAINT IF EXISTS fk_lead_qr_code")
    op.execute("ALTER TABLE lead DROP COLUMN IF EXISTS qr_code_id")
    op.execute("DROP TABLE IF EXISTS lead_intake_challenge")
    op.execute("DROP TABLE IF EXISTS lead_qr_code")
