"""007 administration: people, offices, territories, partners (FS-006)

What this migration does, in the order the spec's section 5 lists it:

* `app_user` gains `must_change_password` and `password_changed_at`, three shape
  CHECKs (a trimmed email of at most 254, an Indian mobile stored without the plus,
  a name of 1 to 200 characters) and a keyset index for the people list.
* `app_user_role_family_check()` is replaced. It becomes SECURITY DEFINER because
  it now takes a share lock on the office or partner row, and a locking read as the
  caller applies the UPDATE policies and silently returns nothing (round 5 B-1,
  executed). It refuses a self change of `is_active` or `deleted_at` at trigger
  depth 1, the `system` role on any row but the principal, a password or a state
  change on the principal's own row, a partner user whose role level is not the
  seeded level of its partner type's portal role, and, on INSERT, an anchor change
  or a reactivation, an office that is closed or a partner that is inactive.
* The administrator floor: a deferred constraint trigger that refuses, at commit
  or when the service forces it, a change that would leave no active user whose
  role holds `users.edit`. Counted under one advisory lock (namespace 4) on every
  row event, no short-circuit (round 4 B-1, executed).
* `org_unit_close_guard()`: an office with active, non-deleted users cannot close.
* `user_territory` gains DELETE for app_role and a policy for it.
* `login_kind` gains `unlock`, and `login_attempt_sel` narrows to `users.edit`.
* Unique names under a parent and unique codes per level on the trees; a state's
  code is immutable once the inquiry counter holds a row for it.
* `channel_partner_guarded_columns()`: a partner-subtree caller may edit its
  contact details and nothing that prices, credits or closes it (ISS-061); nobody
  retypes a partner with users anchored.
* `activity_event_sel` gains arms for `org_unit` and `territory`.
* Thirteen new definer functions and four replaced ones; `auth_create_session` is
  dropped and recreated with `p_token_version`, so a credential is bound to the
  version it was verified against (ISS-077).

Every function body here is `LANGUAGE plpgsql`: a `LANGUAGE sql` body or a CHECK
carrying the literal `'unlock'` fails 55P04 inside this migration's transaction, a
plpgsql body compiles (executed). No statement in this migration executes the new
enum value.

Revision ID: 007_administration
Revises: 006_leads
Created: during development
"""
# ruff: noqa: E501  (generated and embedded SQL; its line length is not ours to wrap)
from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "007_administration"
down_revision: str | None = "006_leads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_role"
SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"  # 005: uuid5(DNS, "polysil.system")

# ── grants and hand-written policies, read by tests/db/migration_grants.py ────

GRANTS: dict[str, str] = {
    "user_territory": "DELETE",
}

HAND_POLICIES: list[tuple[str, str]] = [
    # A territory assignment can be removed by the same permission that adds one.
    # A DELETE also passes user_territory_sel (self or users.view), which every
    # users.edit holder has.
    ("user_territory", """CREATE POLICY user_territory_del ON user_territory FOR DELETE USING ((SELECT app_has_permission('users', 'edit')))"""),
    # The failed-login ledger is for administrators, not for everyone who may view
    # people: the Board holds users.view at global (RBAC 6.4) and read it (round 1
    # B-7).
    ("login_attempt", """CREATE POLICY login_attempt_sel ON login_attempt FOR SELECT USING (((SELECT app_has_permission('users', 'edit')) AND (SELECT app_scope('users')) = 'global') OR (SELECT app_is_system()))"""),
    # api/authz/activity.py, regenerated: the org_unit and territory arms. Compared
    # to the generator by string equality in the drift test.
    ("activity_event", """CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (
  CASE entity_type
    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)
    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)
    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)
    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)
    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)
    ELSE (SELECT app_is_system())
  END
)"""),
]

# The 005 and 006 forms these replace, for the downgrade.
LOGIN_ATTEMPT_SEL_005 = """CREATE POLICY login_attempt_sel ON login_attempt FOR SELECT USING (((SELECT app_has_permission('users', 'view')) AND (SELECT app_scope('users')) = 'global') OR (SELECT app_is_system()))"""
ACTIVITY_EVENT_SEL_006 = """CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (
  CASE entity_type
    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)
    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)
    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)
    ELSE (SELECT app_is_system())
  END
)"""

# ── schema ───────────────────────────────────────────────────────────────────

COLUMNS = [
    "ALTER TABLE app_user ADD COLUMN must_change_password boolean NOT NULL DEFAULT false",
    "ALTER TABLE app_user ADD COLUMN password_changed_at timestamptz",
]

# Shape, in the database. The service normalises first; these refuse what it
# missed. Live rows pass all three (executed in review). email is citext, so the
# trim is compared as text and the case is the service's job alone.
CHECKS = [
    """ALTER TABLE app_user ADD CONSTRAINT ck_app_user_email_shape CHECK (
        email IS NULL OR (email::text = btrim(email::text) AND length(email::text) <= 254))""",
    """ALTER TABLE app_user ADD CONSTRAINT ck_app_user_mobile_shape CHECK (
        mobile IS NULL OR mobile ~ '^91[6-9][0-9]{9}$')""",
    """ALTER TABLE app_user ADD CONSTRAINT ck_app_user_name_shape CHECK (
        length(btrim(full_name)) BETWEEN 1 AND 200)""",
]

INDEXES = [
    "CREATE INDEX ix_app_user_list ON app_user (created_at DESC, id DESC)",
    # Rule 15. Partial: a soft-deleted row's name or code may be reissued, like an
    # email. NULLS NOT DISTINCT so two roots (parent_id NULL) with one name collide.
    """CREATE UNIQUE INDEX uq_territory_level_code ON territory (level, code)
        WHERE code IS NOT NULL AND deleted_at IS NULL""",
    """CREATE UNIQUE INDEX uq_territory_parent_name ON territory (parent_id, lower(btrim(name)))
        NULLS NOT DISTINCT WHERE deleted_at IS NULL""",
    """CREATE UNIQUE INDEX uq_org_unit_parent_name ON org_unit (parent_id, lower(btrim(name)))
        NULLS NOT DISTINCT WHERE deleted_at IS NULL""",
]
INDEX_NAMES = ["ix_app_user_list", "uq_territory_level_code", "uq_territory_parent_name",
               "uq_org_unit_parent_name"]

# ── the visibility guard for people, from the same declaration as the policies ─
#
# A definer function cannot borrow RLS (a nested invoker function runs as the
# owner, ISS-066), so the five guarded functions below ask this one, which
# evaluates api/authz/policy_sql.guard_sql(SPECS["users"]) over the claim. Pasted,
# like lead_visible() in 006; the drift test compares it to a regeneration.
USERS_GUARD = """(((SELECT app_scope('users')) = 'own'
  AND id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('users')) = 'org_subtree'
  AND org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('users')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('users')) = 'global')
  OR (id = (SELECT app_current_user_id())))
  AND (id = (SELECT app_current_user_id()) OR (SELECT app_has_permission('users', 'view')))
  AND (deleted_at IS NULL OR (SELECT app_has_permission('users', 'delete')))"""

# The partners guard, for the count a partner list shows per row: a definer runs
# unscoped, so the ids a caller passes are filtered through the same declaration
# the policies are generated from (cross-vendor P2-1: a dealer could count the
# users of any partner by id). Pasted; the drift test compares it to a regeneration.
PARTNERS_GUARD = """(((SELECT app_scope('partners')) = 'org_subtree'
  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))
  OR ((SELECT app_scope('partners')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('partners')) = 'partner_subtree'
  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('partners')) = 'global')
  OR (id = (SELECT app_current_partner())))
  AND (id = (SELECT app_current_partner()) OR (SELECT app_has_permission('partners', 'view')))
  AND (deleted_at IS NULL OR (SELECT app_has_permission('partners', 'delete')))"""

# ── functions: new ───────────────────────────────────────────────────────────

FUNCTIONS: list[str] = [
    # The lockout arithmetic, once. 003's auth_lookup_staff carried it inline; the
    # bound query now counts an 'unlock' row as a success (an administrator's
    # unlock moves the window without deleting the failures), the failure window
    # is unchanged. Granted to nobody: reached inside auth_lookup_staff and
    # auth_user_lockout as the owner (round 2 B-4: granted, it is a lockout oracle).
    """CREATE FUNCTION auth_locked_until(p_identifier citext, p_max_failures int,
                                         p_lockout interval)
RETURNS timestamptz
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_bound  timestamptz;
    v_locked timestamptz;
BEGIN
    -- Rule 5, both clauses at once (FS-001 9.5 R5-3): GREATEST, not coalesce.
    -- Two lockout durations back is the tightest bound that is still correct.
    -- An unlock row is a success for the bound and nothing else (FS-006 rule 13).
    SELECT greatest(max(la.attempted_at) FILTER (WHERE la.succeeded),
                    now() - p_lockout * 2)
      INTO v_bound
      FROM login_attempt la
     WHERE la.identifier = p_identifier
       AND la.kind IN ('password', 'unlock');

    -- The trigger failure is the one whose (p_max_failures)th predecessor is
    -- inside p_lockout of it; the lock runs p_lockout from THAT failure
    -- (FS-001 9.8 X-5: a trailing-window count ends the lock early).
    SELECT max(f.attempted_at) + p_lockout
      INTO v_locked
      FROM (
            SELECT la.attempted_at,
                   lag(la.attempted_at, p_max_failures - 1)
                       OVER (ORDER BY la.attempted_at) AS nth_prior
              FROM login_attempt la
             WHERE la.identifier = p_identifier AND la.kind = 'password'
               AND NOT la.succeeded AND la.attempted_at > v_bound
           ) f
     WHERE f.nth_prior IS NOT NULL
       AND f.attempted_at - f.nth_prior <= p_lockout
       AND f.attempted_at + p_lockout > now();

    RETURN v_locked;
END $fn$""",
    # May the caller see this person? The generated guard, over the claim.
    f"""CREATE FUNCTION authz_user_in_scope(p_user_id uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    RETURN EXISTS (SELECT 1 FROM app_user WHERE id = p_user_id AND ({USERS_GUARD}));
END $fn$""",
    # The five guarded administration functions. Each: a caller (28000 without),
    # users.edit and the target in the caller's users scope (42501 otherwise), actor
    # from the claim, target as the entity. The three that write also refuse the
    # principal by id (42501); the two reads leave that to the service, which
    # refuses it first (code review F-7).
    """CREATE FUNCTION auth_user_lockout(p_user_id uuid, p_max_failures int, p_lockout interval)
RETURNS timestamptz
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_email citext;
BEGIN
    IF app_current_user_id() IS NULL THEN
        RAISE EXCEPTION 'no caller' USING ERRCODE = '28000';
    END IF;
    IF NOT app_has_permission('users', 'edit') OR NOT authz_user_in_scope(p_user_id) THEN
        RAISE EXCEPTION 'users.edit over this person required' USING ERRCODE = '42501';
    END IF;
    SELECT u.email INTO v_email FROM app_user u
     WHERE u.id = p_user_id AND u.user_type = 'staff';
    IF v_email IS NULL THEN
        RETURN NULL;   -- a partner user has no password lockout (FS-001 rule 12)
    END IF;
    RETURN auth_locked_until(v_email, p_max_failures, p_lockout);
END $fn$""",
    f"""CREATE FUNCTION auth_revoke_user_sessions(p_user_id uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_fam uuid;
    v_n   int := 0;
BEGIN
    IF app_current_user_id() IS NULL THEN
        RAISE EXCEPTION 'no caller' USING ERRCODE = '28000';
    END IF;
    IF p_user_id = '{SYSTEM_USER_ID}' THEN
        RAISE EXCEPTION 'the system principal is not administrable' USING ERRCODE = '42501';
    END IF;
    IF NOT app_has_permission('users', 'edit') OR NOT authz_user_in_scope(p_user_id) THEN
        RAISE EXCEPTION 'users.edit over this person required' USING ERRCODE = '42501';
    END IF;
    -- Rule 6: family locks in id order, then the session rows, then the user row.
    -- The same order auth_claim_refresh and the cascade use (FS-002 9.5 F-3).
    FOR v_fam IN
        SELECT DISTINCT s.family_id FROM session s
         WHERE s.user_id = p_user_id AND s.revoked_at IS NULL
         ORDER BY s.family_id
    LOOP
        PERFORM pg_advisory_xact_lock(3, hashtext(v_fam::text));
    END LOOP;
    WITH revoked AS (
        UPDATE session s SET revoked_at = now()
         WHERE s.user_id = p_user_id AND s.revoked_at IS NULL
        RETURNING 1
    )
    SELECT count(*)::int INTO v_n FROM revoked;
    UPDATE app_user SET token_version = token_version + 1 WHERE id = p_user_id;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('app_user', p_user_id, 'auth.sessions_revoked', app_current_user_id(),
            jsonb_build_object('sessions', v_n));
    RETURN v_n;
END $fn$""",
    """CREATE FUNCTION auth_user_session_count(p_user_id uuid) RETURNS integer
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    IF app_current_user_id() IS NULL THEN
        RAISE EXCEPTION 'no caller' USING ERRCODE = '28000';
    END IF;
    IF NOT app_has_permission('users', 'edit') OR NOT authz_user_in_scope(p_user_id) THEN
        RAISE EXCEPTION 'users.edit over this person required' USING ERRCODE = '42501';
    END IF;
    SELECT count(*)::int INTO v_n FROM session s
     WHERE s.user_id = p_user_id AND s.revoked_at IS NULL AND s.expires_at > now();
    RETURN v_n;
END $fn$""",
    # Unlocking appends; it deletes nothing (rule 13). The row is a success of kind
    # 'unlock' for the person's email, which moves auth_locked_until's bound.
    f"""CREATE FUNCTION auth_unlock_user(p_user_id uuid, p_max_failures int, p_lockout interval)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_email  citext;
    v_locked boolean;
BEGIN
    IF app_current_user_id() IS NULL THEN
        RAISE EXCEPTION 'no caller' USING ERRCODE = '28000';
    END IF;
    IF p_user_id = '{SYSTEM_USER_ID}' THEN
        RAISE EXCEPTION 'the system principal is not administrable' USING ERRCODE = '42501';
    END IF;
    IF NOT app_has_permission('users', 'edit') OR NOT authz_user_in_scope(p_user_id) THEN
        RAISE EXCEPTION 'users.edit over this person required' USING ERRCODE = '42501';
    END IF;
    SELECT u.email INTO v_email FROM app_user u
     WHERE u.id = p_user_id AND u.user_type = 'staff';
    IF v_email IS NULL THEN
        RAISE EXCEPTION 'OTP sign-in has no lockout to clear' USING ERRCODE = '22023';
    END IF;
    v_locked := auth_locked_until(v_email, p_max_failures, p_lockout) IS NOT NULL;
    INSERT INTO login_attempt (identifier, ip, succeeded, kind)
    VALUES (v_email, NULL, true, 'unlock');
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('app_user', p_user_id, 'auth.unlocked', app_current_user_id(),
            jsonb_build_object('was_locked', v_locked));
    RETURN v_locked;
END $fn$""",
    # A person's own password. Rule 6's lock order (family locks in id order, the
    # session rows, then the user row) is the order auth_claim_refresh takes, so
    # the two never deadlock. The session rows are LOCKED before the compare-and-
    # set and WRITTEN after it: a failed CAS has written nothing, which is what
    # lets the service answer 409 without a revoke to undo (round 5 R-3). The
    # write matches only the hash the service verified.
    f"""CREATE FUNCTION auth_set_own_password(p_expected_hash text, p_new_hash text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me   uuid := app_current_user_id();
    v_hash text;
    v_type user_type;
    v_fam  uuid;
    v_n    int;
BEGIN
    IF v_me IS NULL THEN
        RAISE EXCEPTION 'no caller' USING ERRCODE = '28000';
    END IF;
    IF v_me = '{SYSTEM_USER_ID}' THEN
        RAISE EXCEPTION 'the system principal is not administrable' USING ERRCODE = '42501';
    END IF;
    SELECT u.password_hash, u.user_type INTO v_hash, v_type
      FROM app_user u WHERE u.id = v_me AND u.deleted_at IS NULL AND u.is_active;
    IF v_type IS DISTINCT FROM 'staff' OR v_hash IS NULL THEN
        RAISE EXCEPTION 'this account has no password' USING ERRCODE = '22023';
    END IF;
    IF v_hash <> p_expected_hash THEN
        RETURN false;   -- changed since the service verified it; nothing touched
    END IF;
    FOR v_fam IN
        SELECT DISTINCT s.family_id FROM session s
         WHERE s.user_id = v_me AND s.revoked_at IS NULL
         ORDER BY s.family_id
    LOOP
        PERFORM pg_advisory_xact_lock(3, hashtext(v_fam::text));
    END LOOP;
    PERFORM 1 FROM session s
     WHERE s.user_id = v_me AND s.revoked_at IS NULL
     FOR UPDATE;
    UPDATE app_user
       SET password_hash = p_new_hash, must_change_password = false,
           password_changed_at = now(), token_version = token_version + 1
     WHERE id = v_me AND password_hash = p_expected_hash;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n = 0 THEN
        RETURN false;   -- an administrator's reset landed first, and it stands
    END IF;
    UPDATE session s SET revoked_at = now()
     WHERE s.user_id = v_me AND s.revoked_at IS NULL;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('app_user', v_me, 'auth.password_changed', v_me, '{{}}'::jsonb);
    RETURN true;
END $fn$""",
    # One call per page of the people list. A count, not a read, so it runs
    # unscoped over lead (rule 12): deleted rows excluded explicitly, because the
    # caller's own leads.delete would otherwise admit them (round 1 B-11). The
    # PEOPLE are in the caller's users scope, though: an id outside it counts
    # nothing (cross-vendor P2-1's shape).
    """CREATE FUNCTION user_open_leads_bulk(p_ids uuid[])
RETURNS TABLE (user_id uuid, open_leads integer)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_has_permission('users', 'view') THEN
        RAISE EXCEPTION 'users.view required' USING ERRCODE = '42501';
    END IF;
    RETURN QUERY
        SELECT l.owner_user_id, count(*)::int
          FROM lead l
         WHERE l.owner_user_id = ANY(p_ids)
           AND authz_user_in_scope(l.owner_user_id)
           AND l.deleted_at IS NULL
           AND l.stage NOT IN ('won', 'lost', 'merged')
         GROUP BY l.owner_user_id;
END $fn$""",
    # The list forms of the two reads a screen needs per row: the office tree with
    # active user counts (masters.edit callers need not hold users.view) and the
    # partner list with its user counts; and the state codes locked by the counter
    # ledger, for a page of territories in one call.
    """CREATE FUNCTION org_unit_user_counts(p_ids uuid[])
RETURNS TABLE (org_unit_id uuid, active_users integer)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF app_current_user_id() IS NULL THEN
        RAISE EXCEPTION 'no caller' USING ERRCODE = '28000';
    END IF;
    RETURN QUERY
        SELECT u.org_unit_id, count(*)::int
          FROM app_user u
         WHERE u.org_unit_id = ANY(p_ids) AND u.is_active AND u.deleted_at IS NULL
         GROUP BY u.org_unit_id;
END $fn$""",
    f"""CREATE FUNCTION channel_partner_user_counts(p_ids uuid[])
RETURNS TABLE (partner_id uuid, users integer, users_inactive integer)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_has_permission('partners', 'view') THEN
        RAISE EXCEPTION 'partners.view required' USING ERRCODE = '42501';
    END IF;
    RETURN QUERY
        SELECT u.partner_id,
               count(*) FILTER (WHERE u.is_active)::int,
               count(*) FILTER (WHERE NOT u.is_active)::int
          FROM app_user u
         WHERE u.partner_id = ANY(p_ids) AND u.deleted_at IS NULL
           AND u.partner_id IN (SELECT id FROM channel_partner
                                 WHERE id = ANY(p_ids) AND ({PARTNERS_GUARD}))
         GROUP BY u.partner_id;
END $fn$""",
    # The state code a lead is numbered under, read with a share lock on the state
    # row so the read serialises against a code edit: the edit's row lock waits for
    # this transaction, and then territory_code_guard() sees the counter row; in the
    # other order this read waits and returns the new code (cross-vendor P2-3).
    # The lead service cannot take the lock itself: a locking read as the caller
    # applies the territory UPDATE policy, which a field officer does not pass.
    """CREATE FUNCTION lead_state_code(p_territory_id uuid) RETURNS text
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_code text;
BEGIN
    IF NOT app_has_permission('leads', 'create') THEN
        RAISE EXCEPTION 'not permitted to create leads' USING ERRCODE = '42501';
    END IF;
    SELECT t.code::text INTO v_code
      FROM territory_closure tc
      JOIN territory t ON t.id = tc.ancestor_id
     WHERE tc.descendant_id = p_territory_id AND t.level = 'state'
     ORDER BY tc.depth ASC
     LIMIT 1
       FOR SHARE OF t;
    RETURN v_code;
END $fn$""",
    """CREATE FUNCTION territory_codes_locked(p_ids uuid[]) RETURNS TABLE (id uuid)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF app_current_user_id() IS NULL THEN
        RAISE EXCEPTION 'no caller' USING ERRCODE = '28000';
    END IF;
    RETURN QUERY
        SELECT t.id FROM territory t
          JOIN inquiry_counter ic ON ic.state_code = t.code::text
         WHERE t.id = ANY(p_ids) AND t.level = 'state';
END $fn$""",
    # inquiry_counter is fail-closed (no grant, no policy), so the API reads the
    # lock state through this. Same condition as territory_code_guard().
    """CREATE FUNCTION territory_code_locked(p_id uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF app_current_user_id() IS NULL THEN
        RAISE EXCEPTION 'no caller' USING ERRCODE = '28000';
    END IF;
    RETURN EXISTS (
        SELECT 1 FROM territory t
          JOIN inquiry_counter ic ON ic.state_code = t.code::text
         WHERE t.id = p_id AND t.level = 'state');
END $fn$""",
]

# Signatures granted to app_role. auth_locked_until and authz_user_in_scope are
# deliberately absent: reached only inside the definers above.
FUNCTION_SIGS = [
    "auth_user_lockout(uuid, int, interval)",
    "auth_revoke_user_sessions(uuid)",
    "auth_user_session_count(uuid)",
    "auth_unlock_user(uuid, int, interval)",
    "auth_set_own_password(text, text)",
    "user_open_leads_bulk(uuid[])",
    "territory_code_locked(uuid)",
    "org_unit_user_counts(uuid[])",
    "channel_partner_user_counts(uuid[])",
    "territory_codes_locked(uuid[])",
    "lead_state_code(uuid)",
]
ALL_NEW_SIGS = [*FUNCTION_SIGS, "auth_locked_until(citext, int, interval)",
                "authz_user_in_scope(uuid)"]

# ── functions: replaced, CREATE OR REPLACE with the signature unchanged ────────
#
# A DROP resets the ACL to PUBLIC-executable (executed); CREATE OR REPLACE keeps
# it, and does change volatility (executed; 003a's docstring said otherwise).

REPLACED: list[str] = [
    # 003's auth_lookup_staff, now calling auth_locked_until() and excluding the
    # principal's row (rule 19): no hash can ever be set on it, and even one forced
    # in as the owner opens no door.
    f"""CREATE OR REPLACE FUNCTION auth_lookup_staff(p_email citext, p_max_failures int,
                                                  p_lockout interval)
RETURNS TABLE (user_id uuid, password_hash text, is_active boolean,
               token_version int, locked_until timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_locked timestamptz;
BEGIN
    v_locked := auth_locked_until(p_email, p_max_failures, p_lockout);
    -- The LEFT JOIN against a one-row source is what makes "always one row"
    -- true; a plain SELECT returns none for an unknown address (FS-001).
    RETURN QUERY
    SELECT u.id, u.password_hash, u.is_active, u.token_version, v_locked
      FROM (SELECT 1) AS one
      LEFT JOIN app_user u
             ON u.email = p_email
            AND u.deleted_at IS NULL
            AND u.user_type = 'staff'
            AND u.password_hash IS NOT NULL
            AND u.id <> '{SYSTEM_USER_ID}';
END $fn$""",
    # 006's three pickers: a candidate must be able to work the module (its role
    # holds edit), which excludes the principal, the Board, the functional roles
    # and a regional manager (ISS-075). The two that pick a candidate share the
    # row (rule 20), so they are VOLATILE now.
    """CREATE OR REPLACE FUNCTION authz_user_assignable(p_module text, p_user_id uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_scope text;
BEGIN
    IF p_module NOT IN ('leads') THEN RETURN false; END IF;
    IF NOT app_has_permission(p_module, 'edit') THEN RETURN false; END IF;
    v_scope := app_scope(p_module);
    PERFORM 1
       FROM app_user u
       JOIN role_permission rp ON rp.role_id = u.role_id
      WHERE u.id = p_user_id AND u.user_type = 'staff' AND u.is_active
        AND u.deleted_at IS NULL
        AND rp.module = p_module AND rp.action = 'edit'
        AND (v_scope = 'global'
             OR (v_scope = 'org_subtree' AND u.org_unit_id IN
                 (SELECT descendant_id FROM org_closure
                   WHERE ancestor_id = app_current_org_unit())))
      FOR SHARE OF u;
    RETURN FOUND;
END $fn$""",
    """CREATE OR REPLACE FUNCTION staff_directory(p_module text)
RETURNS TABLE (id uuid, full_name text, org_unit_id uuid)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_scope text;
BEGIN
    IF p_module NOT IN ('leads') THEN RETURN; END IF;
    IF NOT app_has_permission(p_module, 'edit') THEN RETURN; END IF;
    v_scope := app_scope(p_module);
    RETURN QUERY
        SELECT u.id, u.full_name, u.org_unit_id
          FROM app_user u
          JOIN role_permission rp ON rp.role_id = u.role_id
         WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL
           AND rp.module = p_module AND rp.action = 'edit'
           AND (v_scope = 'global'
                OR (v_scope = 'org_subtree' AND u.org_unit_id IN
                    (SELECT descendant_id FROM org_closure
                      WHERE ancestor_id = app_current_org_unit())));
END $fn$""",
    """CREATE OR REPLACE FUNCTION lead_auto_owner(p_territory_id uuid) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_owner uuid;
BEGIN
    IF NOT app_has_permission('leads', 'create') THEN
        RAISE EXCEPTION 'not permitted to create leads' USING ERRCODE = '42501';
    END IF;
    SELECT u.id INTO v_owner
      FROM app_user u
      JOIN role r ON r.id = u.role_id
      JOIN role_permission rp ON rp.role_id = u.role_id
                             AND rp.module = 'leads' AND rp.action = 'edit'
      JOIN org_unit ou ON ou.id = u.org_unit_id
      JOIN territory_closure tc ON tc.ancestor_id = ou.territory_id
                               AND tc.descendant_id = p_territory_id
     WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL
       AND r.level = 1
     ORDER BY tc.depth ASC,
              (SELECT count(*) FROM lead l
                WHERE l.owner_user_id = u.id
                  AND l.deleted_at IS NULL
                  AND l.stage NOT IN ('won', 'lost', 'merged', 'dormant')) ASC,
              u.id ASC
     LIMIT 1
       FOR SHARE OF u;
    RETURN v_owner;
END $fn$""",
    # 005's role-family trigger, extended. SECURITY DEFINER: the anchor read below
    # takes a share lock, and a locking read as the caller applies the UPDATE
    # policies and silently returns nothing (round 5 B-1). The self-guard reads
    # the claim, not current_user, so it still applies. Check order: family, then
    # level against type, then the principal, then the anchor last.
    f"""CREATE OR REPLACE FUNCTION app_user_role_family_check() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    r        role%ROWTYPE;
    v_rank   int;
    v_check  boolean;
    v_open   boolean;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.id = app_current_user_id() THEN
        IF NEW.role_id IS DISTINCT FROM OLD.role_id
           OR NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id
           OR NEW.partner_id IS DISTINCT FROM OLD.partner_id THEN
            RAISE EXCEPTION 'a user may not change their own role, org unit or partner'
                USING ERRCODE = '42501';
        END IF;
        -- Depth 1 only: the partner-close cascade (a definer trigger, depth 2)
        -- writes is_active on rows the caller may be one of. No path reaches it
        -- today (rule 14); the gate is defensive.
        IF pg_trigger_depth() = 1
           AND (NEW.is_active IS DISTINCT FROM OLD.is_active
                OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at) THEN
            RAISE EXCEPTION 'a user may not deactivate or delete themself'
                USING ERRCODE = '42501';
        END IF;
    END IF;

    IF TG_OP = 'UPDATE' AND NEW.user_type IS DISTINCT FROM OLD.user_type THEN
        NEW.token_version := OLD.token_version + 1;
    END IF;

    IF NEW.user_type = 'consumer' THEN
        IF NEW.role_id IS NOT NULL THEN
            RAISE EXCEPTION 'consumers hold no role' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.role_id IS NULL THEN
        RAISE EXCEPTION '% users must hold a role', NEW.user_type
            USING ERRCODE = '23502';
    END IF;

    SELECT * INTO r FROM role WHERE id = NEW.role_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'role % does not exist', NEW.role_id
            USING ERRCODE = '23503';
    END IF;
    IF NEW.user_type = 'partner_user' AND NOT r.is_portal THEN
        RAISE EXCEPTION 'role % is not a portal role', r.code
            USING ERRCODE = '23514';
    END IF;
    IF NEW.user_type = 'staff' AND r.is_portal THEN
        RAISE EXCEPTION 'role % is a portal role, not a staff role', r.code
            USING ERRCODE = '23514';
    END IF;

    -- Rule 2: the role's level is the seeded level of the type's portal role
    -- (sub_dealer 1, dealer 2, distributor 3). This is the INVERSE of
    -- channel_partner_type_order()'s depth ranks; do not reuse that CASE. Into a
    -- variable first: an inline CASE inside IF ... THEN does not parse in plpgsql.
    IF NEW.user_type = 'partner_user' THEN
        SELECT CASE cp.partner_type
                   WHEN 'sub_dealer' THEN 1
                   WHEN 'dealer' THEN 2
                   WHEN 'distributor' THEN 3
               END
          INTO v_rank
          FROM channel_partner cp WHERE cp.id = NEW.partner_id;
        IF v_rank IS NOT NULL AND r.level <> v_rank THEN
            RAISE EXCEPTION 'role % (level %) does not match the partner type (level %)',
                r.code, r.level, v_rank USING ERRCODE = '23514';
        END IF;
    END IF;

    -- Rule 19: the principal is not a person, and the system role is nobody
    -- else's. 005's reseed sets active, undeleted and the system role.
    IF NEW.id = '{SYSTEM_USER_ID}' THEN
        IF NEW.password_hash IS NOT NULL OR NOT NEW.is_active
           OR NEW.deleted_at IS NOT NULL OR r.code <> 'system'
           OR (TG_OP = 'UPDATE' AND NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id) THEN
            RAISE EXCEPTION 'the system principal is not administrable'
                USING ERRCODE = '42501';
        END IF;
    ELSIF r.code = 'system' THEN
        RAISE EXCEPTION 'the system role is not assignable' USING ERRCODE = '42501';
    END IF;

    -- Anchor state: on INSERT, on an anchor change, or on activation. Never on
    -- deactivation, or the partner-close cascade would refuse itself (round 3
    -- B-2). The share lock serialises a create against a concurrent close.
    IF TG_OP = 'INSERT' THEN
        v_check := true;
    ELSE
        v_check := NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id
                   OR NEW.partner_id IS DISTINCT FROM OLD.partner_id
                   OR (NEW.is_active AND NOT OLD.is_active);
    END IF;
    -- The anchor's STATE, read after a share lock on its row. The lock is taken
    -- whatever the state, so a create or reactivation serialises against a
    -- concurrent close and the locking read returns the row the close wrote. A
    -- missing anchor is left to the foreign key (23503), so 003's and 004's
    -- constraint tests keep their messages.
    IF v_check THEN
        IF NEW.user_type = 'staff' THEN
            SELECT ou.deleted_at IS NULL INTO v_open
              FROM org_unit ou WHERE ou.id = NEW.org_unit_id FOR SHARE;
            IF FOUND AND NOT v_open THEN
                RAISE EXCEPTION 'office is closed' USING ERRCODE = '23514';
            END IF;
        ELSIF NEW.user_type = 'partner_user' THEN
            SELECT (cp.is_active AND cp.deleted_at IS NULL) INTO v_open
              FROM channel_partner cp WHERE cp.id = NEW.partner_id FOR SHARE;
            IF FOUND AND NOT v_open THEN
                RAISE EXCEPTION 'partner is inactive or deleted' USING ERRCODE = '23514';
            END IF;
        END IF;
    END IF;

    RETURN NEW;
END $fn$""",
]

# The 005 body, for the downgrade (with 005's ISS-063 search path).
ROLE_FAMILY_005 = """CREATE OR REPLACE FUNCTION app_user_role_family_check() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
DECLARE r role%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.id = app_current_user_id()
       AND (NEW.role_id IS DISTINCT FROM OLD.role_id
         OR NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id
         OR NEW.partner_id IS DISTINCT FROM OLD.partner_id) THEN
        RAISE EXCEPTION 'a user may not change their own role, org unit or partner'
            USING ERRCODE = '42501';
    END IF;

    IF TG_OP = 'UPDATE' AND NEW.user_type IS DISTINCT FROM OLD.user_type THEN
        NEW.token_version := OLD.token_version + 1;
    END IF;

    IF NEW.user_type = 'consumer' THEN
        IF NEW.role_id IS NOT NULL THEN
            RAISE EXCEPTION 'consumers hold no role' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.role_id IS NULL THEN
        RAISE EXCEPTION '% users must hold a role', NEW.user_type
            USING ERRCODE = '23502';
    END IF;

    SELECT * INTO r FROM role WHERE id = NEW.role_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'role % does not exist', NEW.role_id
            USING ERRCODE = '23503';
    END IF;
    IF NEW.user_type = 'partner_user' AND NOT r.is_portal THEN
        RAISE EXCEPTION 'role % is not a portal role', r.code
            USING ERRCODE = '23514';
    END IF;
    IF NEW.user_type = 'staff' AND r.is_portal THEN
        RAISE EXCEPTION 'role % is a portal role, not a staff role', r.code
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END $fn$"""

# 003's auth_lookup_staff, for the downgrade.
AUTH_LOOKUP_STAFF_003 = """CREATE OR REPLACE FUNCTION auth_lookup_staff(p_email citext, p_max_failures int,
                                                  p_lockout interval)
RETURNS TABLE (user_id uuid, password_hash text, is_active boolean,
               token_version int, locked_until timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_bound  timestamptz;
    v_locked timestamptz;
BEGIN
    -- Rule 5, both clauses at once. GREATEST, not coalesce: it ignores
    -- NULLs so the never-succeeded case needs no coalesce, and it applies
    -- both bounds instead of letting a success older than the window widen
    -- it. Under coalesce a success at 09:00, four mistypes at 09:05-09:08
    -- and one at 14:00 locks the account on failures five hours outside
    -- the trailing fifteen minutes AC-AUTH-4 bounds it to (9.5 R5-3).
    -- Two lockout durations back, not one. A lock triggered by a failure
    -- up to p_lockout ago is still live, and the four failures that
    -- triggered it with it can be a further p_lockout earlier. Anything
    -- older than that cannot produce a live lock, so this is the tightest
    -- bound that is still correct - it keeps the scan bounded when an
    -- identifier has never succeeded.
    SELECT greatest(max(la.attempted_at) FILTER (WHERE la.succeeded),
                    now() - p_lockout * 2)
      INTO v_bound
      FROM login_attempt la
     WHERE la.identifier = p_email AND la.kind = 'password';

    -- A lock triggers at any failure whose p_max_failures'th predecessor
    -- (itself included) is within p_lockout of it, and runs p_lockout from
    -- THAT failure. The most recent such trigger wins.
    --
    -- The obvious version - count the failures currently inside a trailing
    -- window and take the fifth - ends the lock early rather than at its
    -- deadline. Five failures at 09:00 to 09:04 lock until 09:19, but by
    -- 09:16 the 09:00 one has left the trailing window, only four remain,
    -- and the count version reports not-locked three minutes early.
    -- Executed, and it is the whole reason for the window function
    -- (FS-001 9.8 X-5).
    SELECT max(f.attempted_at) + p_lockout
      INTO v_locked
      FROM (
            SELECT la.attempted_at,
                   lag(la.attempted_at, p_max_failures - 1)
                       OVER (ORDER BY la.attempted_at) AS nth_prior
              FROM login_attempt la
             WHERE la.identifier = p_email AND la.kind = 'password'
               AND NOT la.succeeded AND la.attempted_at > v_bound
           ) f
     WHERE f.nth_prior IS NOT NULL
       AND f.attempted_at - f.nth_prior <= p_lockout
       -- Expired locks resolve to NULL rather than to a past timestamp, so
       -- "not locked" has one representation and a caller cannot forget the
       -- comparison.
       AND f.attempted_at + p_lockout > now();

    -- The LEFT JOIN against a one-row source is what makes "always one
    -- row" true; a plain SELECT returns none for an unknown address.
    RETURN QUERY
    SELECT u.id, u.password_hash, u.is_active, u.token_version, v_locked
      FROM (SELECT 1) AS one
      LEFT JOIN app_user u
             ON u.email = p_email
            AND u.deleted_at IS NULL
            AND u.user_type = 'staff'
            -- email is nullable and the CHECK does not forbid it on a
            -- partner_user, so a portal row carrying one must fail as
            -- invalid_credentials rather than verify against NULL.
            AND u.password_hash IS NOT NULL;
END $fn$"""

# ── auth_create_session: dropped and recreated with the version parameter ──────
#
# A CREATE OR REPLACE with an extra mandatory parameter creates a second overload
# that the seven-argument callers resolve to silently, so the old body would keep
# minting without the check and nothing would error (round 7 R-1, executed). Hence
# DROP, CREATE, and the app_anon re-grant inside 003b's guard. 003b itself is not
# touched: it names the seven-argument form, which exists at its own point in
# history in both directions.
SESSION_OLD_SIG = "auth_create_session(uuid, text, uuid, interval, text, inet, text)"
SESSION_NEW_SIG = "auth_create_session(uuid, text, uuid, interval, text, inet, text, int)"

AUTH_CREATE_SESSION_007 = """CREATE FUNCTION auth_create_session(p_user_id uuid, p_refresh_hash text,
                                    p_family_id uuid, p_ttl interval,
                                    p_ua text, p_ip inet,
                                    p_door text, p_token_version int)
RETURNS TABLE (session_id uuid, expires_at timestamptz, token_version int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_session_id uuid;
    v_expires_at timestamptz;
    v_token_version int;
BEGIN
    IF p_door IS NOT NULL AND p_door NOT IN ('password', 'otp') THEN
        RAISE EXCEPTION 'unknown sign-in door: %', p_door
            USING ERRCODE = '22023';
    END IF;

    PERFORM pg_advisory_xact_lock(3, hashtext(p_family_id::text));

    -- Rule 6 of FS-006 (ISS-077): the credential is bound to the version it was
    -- verified against. A password change that lands between Argon2 verification
    -- and this statement moves token_version, matches nothing, and the caller
    -- answers invalid_credentials. One statement, so it is atomic against the
    -- bump.
    INSERT INTO session (user_id, refresh_token_hash, family_id,
                         token_version, expires_at, user_agent, ip)
    SELECT p_user_id, p_refresh_hash, p_family_id, u.token_version,
           now() + p_ttl, p_ua, p_ip
      FROM app_user u
     WHERE u.id = p_user_id
       AND u.deleted_at IS NULL
       AND u.is_active
       AND u.token_version = p_token_version
    RETURNING session.id, session.expires_at, session.token_version
         INTO v_session_id, v_expires_at, v_token_version;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF p_door IS NOT NULL THEN
        UPDATE app_user SET last_login_at = now() WHERE id = p_user_id;

        INSERT INTO activity_event (entity_type, entity_id, kind,
                                    actor_id, payload)
        VALUES ('app_user', p_user_id, 'auth.signed_in', p_user_id,
                jsonb_build_object('door', p_door, 'session_id', v_session_id));
    END IF;

    RETURN QUERY SELECT v_session_id, v_expires_at, v_token_version;
END $fn$"""

AUTH_CREATE_SESSION_003A = """CREATE FUNCTION auth_create_session(p_user_id uuid, p_refresh_hash text,
                                    p_family_id uuid, p_ttl interval,
                                    p_ua text, p_ip inet,
                                    p_door text DEFAULT NULL)
RETURNS TABLE (session_id uuid, expires_at timestamptz, token_version int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_session_id uuid;
    v_expires_at timestamptz;
    v_token_version int;
BEGIN
    IF p_door IS NOT NULL AND p_door NOT IN ('password', 'otp') THEN
        RAISE EXCEPTION 'unknown sign-in door: %', p_door
            USING ERRCODE = '22023';
    END IF;

    PERFORM pg_advisory_xact_lock(3, hashtext(p_family_id::text));

    INSERT INTO session (user_id, refresh_token_hash, family_id,
                         token_version, expires_at, user_agent, ip)
    SELECT p_user_id, p_refresh_hash, p_family_id, u.token_version,
           now() + p_ttl, p_ua, p_ip
      FROM app_user u
     WHERE u.id = p_user_id
       AND u.deleted_at IS NULL
       AND u.is_active
    RETURNING session.id, session.expires_at, session.token_version
         INTO v_session_id, v_expires_at, v_token_version;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF p_door IS NOT NULL THEN
        UPDATE app_user SET last_login_at = now() WHERE id = p_user_id;

        INSERT INTO activity_event (entity_type, entity_id, kind,
                                    actor_id, payload)
        VALUES ('app_user', p_user_id, 'auth.signed_in', p_user_id,
                jsonb_build_object('door', p_door, 'session_id', v_session_id));
    END IF;

    RETURN QUERY SELECT v_session_id, v_expires_at, v_token_version;
END $fn$"""


def _regrant_anon(sig: str) -> None:
    """A dropped function takes its grants with it (003a). The same guard 003b
    uses: on a box without the role, a NOTICE and nothing granted."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_anon') THEN
                GRANT EXECUTE ON FUNCTION {sig} TO app_anon;
            ELSE
                RAISE NOTICE 'app_anon does not exist; nothing granted. See GAP-021.';
            END IF;
        END $$
        """
    )


# ── triggers ─────────────────────────────────────────────────────────────────

TRIGGER_FUNCTIONS: list[str] = [
    # Rule 16. A deferred constraint trigger, 005's role_permission_invariant idiom:
    # at commit the rows are already written, so a plain count is right (round 2
    # B-2, executed). The service forces it earlier with SET CONSTRAINTS ... IMMEDIATE
    # and maps 23514 to a 422; a bare UPDATE still meets it at commit. Gated on the
    # row that changed having been an administrator, so tests and reseeds that
    # touch ordinary users never count. SECURITY DEFINER: as INVOKER a district
    # manager closing a partner counted zero administrators through their own RLS
    # (round 3 B-7, executed).
    """CREATE FUNCTION app_user_admin_floor() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permission rp
                    WHERE rp.role_id = OLD.role_id
                      AND rp.module = 'users' AND rp.action = 'edit') THEN
        RETURN NULL;
    END IF;
    PERFORM pg_advisory_xact_lock(4, hashtext('admin_floor'));
    SELECT count(*)::int INTO v_n
      FROM app_user u
      JOIN role_permission rp ON rp.role_id = u.role_id
     WHERE u.is_active AND u.deleted_at IS NULL
       AND rp.module = 'users' AND rp.action = 'edit';
    IF v_n = 0 THEN
        RAISE EXCEPTION 'the last administrator cannot be deactivated'
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END $fn$""",
    # The same floor on the permission rows (cross-vendor P2-2): a masters.edit
    # holder can UPDATE or DELETE role_permission under 005's policies, and taking
    # users.edit away from every administrator's role leaves nobody either.
    """CREATE FUNCTION role_permission_admin_floor() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    IF NOT (OLD.module = 'users' AND OLD.action = 'edit') THEN
        RETURN NULL;
    END IF;
    PERFORM pg_advisory_xact_lock(4, hashtext('admin_floor'));
    SELECT count(*)::int INTO v_n
      FROM app_user u
      JOIN role_permission rp ON rp.role_id = u.role_id
     WHERE u.is_active AND u.deleted_at IS NULL
       AND rp.module = 'users' AND rp.action = 'edit';
    IF v_n = 0 THEN
        RAISE EXCEPTION 'the last administrator cannot be deactivated'
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END $fn$""",
    # Rule 9, in the database. SECURITY DEFINER: a masters.edit caller without
    # users.view sees no anchored users as INVOKER and the office closes with staff
    # in it (round 3 B-7, executed).
    """CREATE FUNCTION org_unit_close_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL
       AND EXISTS (SELECT 1 FROM app_user u
                    WHERE u.org_unit_id = NEW.id AND u.is_active AND u.deleted_at IS NULL) THEN
        RAISE EXCEPTION 'active users are anchored here' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$""",
    # Rule 15. Keyed on OLD.code (a rename away would otherwise be free), on the
    # state level (a district may carry a state's letters under the (level, code)
    # index), against the counter ledger, which is durable evidence that numbers
    # were issued where "a lead under the subtree" is not. SECURITY DEFINER:
    # inquiry_counter is fail-closed and an INVOKER read is 42501 (round 5 B-3).
    """CREATE FUNCTION territory_code_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF OLD.level = 'state' AND OLD.code IS NOT NULL
       AND NEW.code IS DISTINCT FROM OLD.code
       AND EXISTS (SELECT 1 FROM inquiry_counter ic WHERE ic.state_code = OLD.code::text) THEN
        RAISE EXCEPTION 'leads are numbered under this code' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$""",
    # Rule 14 (ISS-061) and rule 21. SECURITY DEFINER: the anchored-user read must
    # see users a district manager cannot (they hold partners edit and no users
    # row; round 5 B-2). app_scope() reads the claim and is unaffected. parent_id
    # is not in the list: 005's authz_reparent_guard() already refuses a
    # partner-subtree caller's move ('cannot move'), and repeating it here would
    # only change which message wins. territory_id IS in the list (code review
    # F-4): the org_subtree branch of the partners policies keys on it, so a move
    # would change which managers see the partner at all.
    """CREATE FUNCTION channel_partner_guarded_columns() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF app_scope('partners') = 'partner_subtree'
       AND (NEW.credit_limit IS DISTINCT FROM OLD.credit_limit
            OR NEW.payment_terms_days IS DISTINCT FROM OLD.payment_terms_days
            OR NEW.price_tier IS DISTINCT FROM OLD.price_tier
            OR NEW.partner_type IS DISTINCT FROM OLD.partner_type
            OR NEW.is_active IS DISTINCT FROM OLD.is_active
            OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
            OR NEW.territory_id IS DISTINCT FROM OLD.territory_id) THEN
        RAISE EXCEPTION 'a partner may edit its contact details only'
            USING ERRCODE = '42501';
    END IF;
    IF NEW.partner_type IS DISTINCT FROM OLD.partner_type
       AND EXISTS (SELECT 1 FROM app_user u
                    WHERE u.partner_id = NEW.id AND u.deleted_at IS NULL) THEN
        RAISE EXCEPTION 'users are anchored here; the type cannot change'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$""",
]

TRIGGERS = [
    """CREATE CONSTRAINT TRIGGER trg_app_user_admin_floor
        AFTER UPDATE OF role_id, is_active, deleted_at OR DELETE ON app_user
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION app_user_admin_floor()""",
    """CREATE CONSTRAINT TRIGGER trg_role_permission_admin_floor
        AFTER UPDATE OF role_id, module, action OR DELETE ON role_permission
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION role_permission_admin_floor()""",
    """CREATE TRIGGER trg_org_unit_close_guard
        BEFORE UPDATE OF deleted_at ON org_unit
        FOR EACH ROW EXECUTE FUNCTION org_unit_close_guard()""",
    """CREATE TRIGGER trg_territory_code_guard
        BEFORE UPDATE OF code ON territory
        FOR EACH ROW EXECUTE FUNCTION territory_code_guard()""",
    """CREATE TRIGGER trg_channel_partner_guarded_columns
        BEFORE UPDATE ON channel_partner
        FOR EACH ROW EXECUTE FUNCTION channel_partner_guarded_columns()""",
]
TRIGGER_DROPS = [
    ("trg_app_user_admin_floor", "app_user", "app_user_admin_floor()"),
    ("trg_role_permission_admin_floor", "role_permission", "role_permission_admin_floor()"),
    ("trg_org_unit_close_guard", "org_unit", "org_unit_close_guard()"),
    ("trg_territory_code_guard", "territory", "territory_code_guard()"),
    ("trg_channel_partner_guarded_columns", "channel_partner", "channel_partner_guarded_columns()"),
]

ROLE_FAMILY_TRIGGER_007 = """CREATE TRIGGER trg_app_user_role_family
    BEFORE INSERT OR UPDATE OF role_id, user_type, org_unit_id, partner_id,
                              is_active, deleted_at, password_hash ON app_user
    FOR EACH ROW EXECUTE FUNCTION app_user_role_family_check()"""
ROLE_FAMILY_TRIGGER_005 = """CREATE TRIGGER trg_app_user_role_family
    BEFORE INSERT OR UPDATE OF role_id, user_type, org_unit_id, partner_id ON app_user
    FOR EACH ROW EXECUTE FUNCTION app_user_role_family_check()"""


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


def _module_006() -> object:
    """006's own text, for the downgrade of the three pickers it created."""
    path = Path(__file__).with_name("006_leads.py")
    spec = importlib.util.spec_from_file_location("mig_006_for_007", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def upgrade() -> None:
    for stmt in COLUMNS + CHECKS + INDEXES:
        op.execute(stmt)

    # The ledger's new kind. Not used by any statement below (55P04).
    op.execute("ALTER TYPE login_kind ADD VALUE IF NOT EXISTS 'unlock'")

    # Grants and policies this migration adds or narrows.
    op.execute(f"GRANT DELETE ON user_territory TO {APP_ROLE}")
    op.execute(next(s for t, s in HAND_POLICIES if t == "user_territory"))
    op.execute("DROP POLICY login_attempt_sel ON login_attempt")
    op.execute(next(s for t, s in HAND_POLICIES if t == "login_attempt"))
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(next(s for t, s in HAND_POLICIES if t == "activity_event"))

    # New functions, then the replacements (which keep their grants).
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in FUNCTION_SIGS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    for stmt in REPLACED:
        op.execute(stmt)

    # The role-family trigger fires on three more columns.
    op.execute("DROP TRIGGER trg_app_user_role_family ON app_user")
    op.execute(ROLE_FAMILY_TRIGGER_007)

    # The four new guards.
    for stmt in TRIGGER_FUNCTIONS + TRIGGERS:
        op.execute(stmt)

    # auth_create_session, with the version bound (ISS-077).
    op.execute(f"DROP FUNCTION {SESSION_OLD_SIG}")
    op.execute(AUTH_CREATE_SESSION_007)
    _regrant_anon(SESSION_NEW_SIG)

    _sweep()


def downgrade() -> None:
    # The enum value stays: PostgreSQL has no DROP VALUE. Harmless: nothing
    # writes it once the functions below are gone.
    op.execute(f"DROP FUNCTION {SESSION_NEW_SIG}")
    op.execute(AUTH_CREATE_SESSION_003A)
    _regrant_anon(SESSION_OLD_SIG)

    for trigger, table, fn in TRIGGER_DROPS:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")

    op.execute("DROP TRIGGER trg_app_user_role_family ON app_user")
    op.execute(ROLE_FAMILY_005)
    op.execute(ROLE_FAMILY_TRIGGER_005)

    op.execute(AUTH_LOOKUP_STAFF_003)
    m006 = _module_006()
    for body in m006.FUNCTIONS:  # type: ignore[attr-defined]
        if any(name in body for name in ("FUNCTION authz_user_assignable",
                                         "FUNCTION staff_directory",
                                         "FUNCTION lead_auto_owner")):
            op.execute(body.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))

    for sig in ALL_NEW_SIGS:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")

    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(ACTIVITY_EVENT_SEL_006)
    op.execute("DROP POLICY login_attempt_sel ON login_attempt")
    op.execute(LOGIN_ATTEMPT_SEL_005)
    op.execute("DROP POLICY IF EXISTS user_territory_del ON user_territory")
    op.execute(f"REVOKE DELETE ON user_territory FROM {APP_ROLE}")

    for name in INDEX_NAMES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    for name in ("ck_app_user_email_shape", "ck_app_user_mobile_shape", "ck_app_user_name_shape"):
        op.execute(f"ALTER TABLE app_user DROP CONSTRAINT IF EXISTS {name}")
    op.execute("ALTER TABLE app_user DROP COLUMN IF EXISTS password_changed_at")
    op.execute("ALTER TABLE app_user DROP COLUMN IF EXISTS must_change_password")

    _sweep()
