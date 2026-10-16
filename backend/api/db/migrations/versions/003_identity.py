"""003 identity: RBAC, users, sessions, and the pre-authentication surface

FS-001 rev 7 section 5. The order in this file is not cosmetic:

  1. enums          `role_permission.scope` is RBAC.md's five, not Proposed-Schema
                    section 2's - see Schema-Corrections.md 5a.1
  2. tables         role before app_user, because app_user.role_id points at it
  3. deferred FKs   including 002's, and the genuine cycle inside 003
  4. RBAC helpers   at the END, because check_function_bodies is on and every one
                    of them reads app_user
  5. pre-auth       the eight SECURITY DEFINER functions get_db_anon reaches
  6. triggers       role family, seed-only flags, audit, updated_at
  7. grants         guarded, so a missing app_anon is a NOTICE and not a failure

Four tables here are scheduled elsewhere in Proposed-Schema.md section 18 or in no
migration at all, and all four are recorded in Schema-Corrections.md 5a.5:
`login_attempt` (nowhere), `idempotency_record` (016), `notification_outbox` (015,
and POST /auth/otp/request cannot run without it) and `activity_event` (016, and
CLAUDE.md 4.1 rule 7 is absolute).

Revision ID: 003_identity
Revises: 002_hierarchy
Created: during development
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "003_identity"
down_revision: str | None = "002_hierarchy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMMON = """
    created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid,
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz
"""

# Business tables: audited, updated_at maintained, created_by/updated_by deferred.
# territory and org_unit are 002's and get their audit triggers here, where
# app_current_user_id() exists.
AUDITED = ("role", "role_permission", "app_user", "user_territory",
           "territory", "org_unit")
BUSINESS = ("role", "role_permission", "app_user", "user_territory")


def upgrade() -> None:
    _enums()
    _tables()
    _deferred_foreign_keys()
    _rbac_helpers()
    _pre_auth()
    _triggers()
    _grants()


# ── 1. enums ─────────────────────────────────────────────────────────────────

def _enums() -> None:
    op.execute("CREATE TYPE user_type AS ENUM ('staff', 'partner_user', 'consumer')")
    op.execute(
        "CREATE TYPE permission_action AS ENUM "
        "('view', 'create', 'edit', 'approve', 'delete')"
    )
    # RBAC.md section 3's five, not Proposed-Schema.md section 2's
    # (own|district|state|region|all). District, state and region were descriptive
    # labels for one mechanism - the closure table already determines depth from
    # where the user sits. Every policy in RBAC.md section 5 compares against these
    # literally, app_scope() returns them, and /auth/me already emits org_subtree.
    # Shipping the other five makes migration 017 fail with 22P02, two features
    # after the mistake. Schema-Corrections.md 5a.1.
    op.execute(
        "CREATE TYPE permission_scope AS ENUM "
        "('own', 'org_subtree', 'territory', 'partner_subtree', 'global')"
    )
    # Three values, not two. auth_issue_otp_challenge writes 'otp_issue', and a
    # two-value enum fails it with 22P02 on the first OTP request.
    op.execute("CREATE TYPE login_kind AS ENUM ('password', 'otp', 'otp_issue')")
    op.execute("CREATE TYPE idempotency_state AS ENUM ('in_progress', 'done')")
    op.execute("CREATE TYPE notification_channel AS ENUM ('whatsapp', 'sms', 'email')")
    op.execute("CREATE TYPE notification_state AS ENUM ('pending', 'sent', 'failed', 'dead')")


# ── 2. tables ────────────────────────────────────────────────────────────────

def _tables() -> None:
    op.execute(
        f"""
        CREATE TABLE role (
            id            uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
            code          citext  NOT NULL UNIQUE,
            name          text    NOT NULL,
            level         int     NOT NULL,
            is_functional boolean NOT NULL DEFAULT false,
            is_portal     boolean NOT NULL DEFAULT false,
            {COMMON}
        )
        """
    )

    # Unique on (role_id, module, action), NOT (role_id, module, action, scope):
    # the wider key permits two scopes for one action and makes app_scope()'s
    # LIMIT 1 non-deterministic. The unique index is also the one RBAC.md 5.3
    # requires for the helper lookups, so no second index is created.
    op.execute(
        f"""
        CREATE TABLE role_permission (
            id      uuid              PRIMARY KEY DEFAULT gen_random_uuid(),
            role_id uuid              NOT NULL REFERENCES role(id) ON DELETE CASCADE,
            module  text              NOT NULL,
            action  permission_action NOT NULL,
            scope   permission_scope  NOT NULL,
            {COMMON},
            CONSTRAINT uq_role_permission UNIQUE (role_id, module, action)
        )
        """
    )

    # partner_id and customer_id are bare uuid: channel_partner is 004 and customer
    # is 005. Constraints added there (Schema-Corrections.md 5a.6).
    #
    # The CHECK is tighter than Proposed-Schema.md section 2's, which is an OR of
    # three positive conditions and forbids nothing. That construction let a staff
    # row carry a mobile and become OTP-reachable with no password and no lockout
    # (round 3 B-5), and it would let a partner_user carry an org_unit_id, pointing
    # a portal user at FS-002's org policy branch. Cheaper to close here than to
    # discover there. mobile on staff stays permitted - a field officer's number is
    # legitimately useful - and is closed at the lookup instead.
    op.execute(
        f"""
        CREATE TABLE app_user (
            id            uuid      PRIMARY KEY DEFAULT gen_random_uuid(),
            user_type     user_type NOT NULL,
            email         citext,
            mobile        text,
            password_hash text,
            full_name     text      NOT NULL,
            role_id       uuid      REFERENCES role(id),
            org_unit_id   uuid      REFERENCES org_unit(id),
            partner_id    uuid,
            customer_id   uuid,
            token_version int       NOT NULL DEFAULT 0,
            is_active     boolean   NOT NULL DEFAULT true,
            last_login_at timestamptz,
            {COMMON},
            CONSTRAINT ck_app_user_anchors CHECK (
                (user_type = 'staff'        AND org_unit_id IS NOT NULL
                                            AND email       IS NOT NULL
                                            AND partner_id  IS NULL
                                            AND customer_id IS NULL) OR
                (user_type = 'partner_user' AND partner_id  IS NOT NULL
                                            AND mobile      IS NOT NULL
                                            AND org_unit_id IS NULL
                                            AND customer_id IS NULL) OR
                (user_type = 'consumer'     AND customer_id IS NOT NULL
                                            AND mobile      IS NOT NULL
                                            AND org_unit_id IS NULL
                                            AND partner_id  IS NULL)
            )
        )
        """
    )
    # Partial unique, not a table-level UNIQUE. A table-level constraint means a
    # soft-deleted user's phone number can never be issued to anyone else, and in
    # rural India numbers are reused when staff change. The corollary is a filter,
    # not a constraint: the definer lookups below must carry deleted_at IS NULL, or
    # a soft-deleted row makes the lookup ambiguous again (Schema-Corrections 5a.4).
    op.execute(
        "CREATE UNIQUE INDEX uq_app_user_email ON app_user (email) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_app_user_mobile ON app_user (mobile) "
        "WHERE deleted_at IS NULL"
    )
    # RBAC.md 5.3. Every helper looks up one app_user row by id and reads exactly
    # these three columns; INCLUDE makes that index-only, which is what keeps a
    # policy's InitPlan off the heap.
    op.execute(
        "CREATE INDEX ix_app_user_covering ON app_user (id) "
        "INCLUDE (role_id, org_unit_id, partner_id)"
    )
    for col in ("role_id", "org_unit_id", "partner_id", "customer_id"):
        op.execute(f"CREATE INDEX ix_app_user_{col} ON app_user ({col})")

    # Carries an id of its own although (user_id, territory_id) would identify it.
    # The generic audit trigger reads the row's id for audit_log.row_id, and a
    # junction without one logs NULL - which is only discovered when someone tries
    # to trace a territory assignment.
    op.execute(
        f"""
        CREATE TABLE user_territory (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            territory_id uuid NOT NULL REFERENCES territory(id) ON DELETE CASCADE,
            {COMMON},
            CONSTRAINT uq_user_territory UNIQUE (user_id, territory_id)
        )
        """
    )
    # uq_user_territory's leading column is user_id, which is the index RBAC.md 5.3
    # asks for. Only territory_id needs one of its own.
    op.execute("CREATE INDEX ix_user_territory_territory ON user_territory (territory_id)")

    for table in BUSINESS:
        op.execute(
            f"CREATE UNIQUE INDEX uq_{table}_external ON {table} "
            "(source_system, external_id) WHERE external_id IS NOT NULL"
        )

    # Infrastructure from here down: append-and-expire, no common columns, no audit
    # trigger. Auditing them would duplicate their own content at volume.
    #
    # token_version has NO default. It is snapshotted from app_user.token_version at
    # issue, and a default would substitute 0 for a missing assignment - which reads
    # as "never bumped" and disables the check that makes /auth/refresh see an
    # offboarding (Schema-Corrections 5a.2).
    op.execute(
        """
        CREATE TABLE session (
            id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id            uuid        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            refresh_token_hash text        NOT NULL,
            family_id          uuid        NOT NULL,
            token_version      int         NOT NULL,
            issued_at          timestamptz NOT NULL DEFAULT now(),
            expires_at         timestamptz NOT NULL,
            used_at            timestamptz,
            revoked_at         timestamptz,
            user_agent         text,
            ip                 inet
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_session_refresh_hash ON session (refresh_token_hash)"
    )
    # Reuse detection revokes by family: hot, and security-critical.
    op.execute("CREATE INDEX ix_session_family ON session (family_id)")
    op.execute("CREATE INDEX ix_session_user ON session (user_id)")
    # Two purge indexes, not one. The retention job deletes rows revoked OR expired
    # past 90 days, and a single index predicated on revoked_at IS NULL excludes
    # exactly the revoked half it is meant to find.
    op.execute(
        "CREATE INDEX ix_session_purge_expired ON session (expires_at) "
        "WHERE revoked_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_session_purge_revoked ON session (revoked_at) "
        "WHERE revoked_at IS NOT NULL"
    )

    # kind has NO default, for the same reason as session.token_version: a default
    # silently relabels a missing p_kind as a lockout-counting password failure.
    op.execute(
        """
        CREATE TABLE login_attempt (
            id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            identifier   citext      NOT NULL,
            ip           inet,
            succeeded    boolean     NOT NULL,
            kind         login_kind  NOT NULL,
            attempted_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # The lockout counts kind='password' rows only, so kind is in the key rather
    # than filtered after the fact.
    op.execute(
        "CREATE INDEX ix_login_attempt_lockout ON login_attempt "
        "(identifier, kind, attempted_at DESC)"
    )
    op.execute("CREATE INDEX ix_login_attempt_purge ON login_attempt (attempted_at)")

    # NULLS NOT DISTINCT is load-bearing, not tidiness. user_id is nullable because
    # intake_submit is a public endpoint (Schema-Corrections section 3), and under
    # the default NULLS DISTINCT two anonymous callers with the same key never
    # conflict - so ON CONFLICT DO NOTHING never blocks, and the exactly-once
    # guarantee every module inherits from this table does not exist.
    #
    # state is load-bearing too: the winner inserts 'in_progress', the loser's
    # ON CONFLICT DO NOTHING blocks on that uncommitted row until the winner
    # commits and sets 'done'.
    op.execute(
        """
        CREATE TABLE idempotency_record (
            id           uuid              PRIMARY KEY DEFAULT gen_random_uuid(),
            key          text              NOT NULL,
            user_id      uuid              REFERENCES app_user(id) ON DELETE CASCADE,
            route        text              NOT NULL,
            request_hash text              NOT NULL,
            state        idempotency_state NOT NULL,
            status_code  int,
            response_json jsonb,
            created_at   timestamptz       NOT NULL DEFAULT now(),
            completed_at timestamptz,
            CONSTRAINT uq_idempotency
                UNIQUE NULLS NOT DISTINCT (key, user_id, route),
            -- A 'done' record with nothing to replay returns an empty response to
            -- the retry, which is worse than executing twice would have been.
            CONSTRAINT ck_idempotency_done CHECK (
                state = 'in_progress'
                OR (status_code IS NOT NULL AND response_json IS NOT NULL)
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_idempotency_purge ON idempotency_record (created_at)")

    op.execute(
        """
        CREATE TABLE notification_outbox (
            id              uuid                 PRIMARY KEY DEFAULT gen_random_uuid(),
            channel         notification_channel NOT NULL,
            template_key    text                 NOT NULL,
            recipient       text                 NOT NULL,
            payload         jsonb                NOT NULL DEFAULT '{}'::jsonb,
            state           notification_state   NOT NULL DEFAULT 'pending',
            attempts        int                  NOT NULL DEFAULT 0,
            next_attempt_at timestamptz          NOT NULL DEFAULT now(),
            provider_msg_id text,
            error           text,
            created_at      timestamptz          NOT NULL DEFAULT now(),
            sent_at         timestamptz
        )
        """
    )
    # Proposed-Schema.md section 17 writes this as (state, next_attempt_at) WHERE
    # state = 'pending'. The predicate already fixes state, so carrying it in the
    # key is a constant column in every entry. The drain reads it with
    # FOR UPDATE SKIP LOCKED ordered by next_attempt_at.
    op.execute(
        "CREATE INDEX ix_notification_outbox_due ON notification_outbox "
        "(next_attempt_at) WHERE state = 'pending'"
    )

    # Append-only, no soft delete, no audit trigger - it IS the record. Every id
    # column here is a bare uuid: customer and lead are 005, channel_partner is
    # 004, and actor_id follows audit_log's reasoning - the event outlives the
    # deletion of whoever caused it.
    op.execute(
        """
        CREATE TABLE activity_event (
            id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type text        NOT NULL,
            entity_id   uuid,
            customer_id uuid,
            partner_id  uuid,
            lead_id     uuid,
            kind        text        NOT NULL,
            occurred_at timestamptz NOT NULL DEFAULT now(),
            actor_id    uuid,
            payload     jsonb       NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    # The first two are Proposed-Schema.md section 17's - the hottest read in the
    # system. The third is what FS-001's own events are read by: a user's timeline
    # is (entity_type, entity_id), and without it every sign-in row costs a scan.
    op.execute(
        "CREATE INDEX ix_activity_event_customer ON activity_event "
        "(customer_id, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_activity_event_partner ON activity_event "
        "(partner_id, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_activity_event_entity ON activity_event "
        "(entity_type, entity_id, occurred_at DESC)"
    )


# ── 3. deferred foreign keys ─────────────────────────────────────────────────

def _deferred_foreign_keys() -> None:
    """Proposed-Schema.md 1.2 puts created_by/updated_by on every business table.

    002's two tables could not carry them - app_user did not exist. Neither could
    `role`, and that one is a genuine cycle rather than an ordering problem:
    app_user.role_id points at role, and 1.2 puts created_by references app_user
    on role. No ordering of the two satisfies both, so one direction is a deferred
    ALTER regardless (Schema-Corrections 5a.6).
    """
    for table in ("territory", "org_unit", "role", "role_permission",
                  "app_user", "user_territory"):
        for col in ("created_by", "updated_by"):
            op.execute(
                f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_{col} "
                f"FOREIGN KEY ({col}) REFERENCES app_user(id)"
            )


# ── 4. the six RBAC helpers ──────────────────────────────────────────────────

def _rbac_helpers() -> None:
    """RBAC.md section 5.3, verbatim except where a type demanded a cast.

    All six live here rather than in 001 because check_function_bodies is on and a
    LANGUAGE sql body is validated at CREATE FUNCTION time. Five of them read
    app_user and role_permission, both of which 003 creates - so 001 is too early
    and FS-002 (round 1's first answer) is too late, since rule 19 has require()
    calling app_has_permission().

    All STABLE. Every call site wraps them in a scalar subselect so Postgres hoists
    them to an InitPlan and evaluates once per statement rather than once per row -
    40ms against 40 seconds on 500k rows (ADR-021).
    """
    op.execute(
        """
        CREATE FUNCTION app_current_user_id() RETURNS uuid
        LANGUAGE sql STABLE AS
        $$SELECT nullif(current_setting('app.current_user_id', true), '')::uuid$$
        """
    )
    for name, col in (("app_current_org_unit", "org_unit_id"),
                      ("app_current_partner", "partner_id"),
                      ("app_current_role", "role_id")):
        op.execute(
            f"""
            CREATE FUNCTION {name}() RETURNS uuid
            LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS
            $$SELECT {col} FROM app_user WHERE id = (SELECT app_current_user_id())$$
            """
        )

    # p_action is text because RBAC.md 5.3 declares it so and rule 19 has the API
    # layer passing a string. The cast to permission_action is what keeps the
    # (role_id, module, action) index usable - comparing action::text to p_action
    # would not. An unknown action string raises 22P02 rather than returning false,
    # which is the right failure for what can only be a typo in a policy.
    op.execute(
        """
        CREATE FUNCTION app_has_permission(p_module text, p_action text)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS
        $$SELECT EXISTS (SELECT 1 FROM role_permission rp
                           JOIN app_user u ON u.role_id = rp.role_id
                          WHERE u.id = (SELECT app_current_user_id())
                            AND rp.module = p_module
                            AND rp.action = p_action::permission_action)$$
        """
    )
    # Reads only the view row. RBAC.md section 6 states that as design - create,
    # edit, approve and delete inherit the view scope but check their own
    # permission - and assert_role_permission_invariants() below is what makes the
    # assumption an enforced fact (ISS-029).
    #
    # ::text because the column is an enum and the return type is text; without it
    # this fails at CREATE FUNCTION time, which is the whole reason these six are
    # in 003 rather than 001.
    op.execute(
        """
        CREATE FUNCTION app_scope(p_module text) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS
        $$SELECT rp.scope::text FROM role_permission rp
            JOIN app_user u ON u.role_id = rp.role_id
           WHERE u.id = (SELECT app_current_user_id())
             AND rp.module = p_module AND rp.action = 'view' LIMIT 1$$
        """
    )


# ── 5. the pre-authentication surface ────────────────────────────────────────

def _pre_auth() -> None:
    """The eight functions get_db_anon reaches, and nothing else.

    Four endpoints cannot present an access token - login, OTP verify, refresh and
    cookie-only logout - so all four run under a connection with no claim set. A
    connection with no claim must not be able to read app_user freely: it holds
    every password hash, and once app_user acquires RLS in FS-002 a NULL claim
    resolves every scope check to nothing and login silently returns zero rows for
    everyone. So: definer functions, and no table grants (FS-001 5.1, rule 25).
    """
    # Returns exactly one row whether or not the email exists - nulls when it does
    # not - so the caller's shape is uniform. Shape is not enough on its own: the
    # caller must still verify against a dummy hash when password_hash is NULL, or
    # the unknown-email path returns in microseconds while the known-email path
    # spends Argon2's work factor, and "one message for both" becomes an oracle by
    # stopwatch.
    #
    # user_type = 'staff' is a security filter, not a tidiness one. The CHECK above
    # requires org_unit_id and email for staff; it does not FORBID mobile. Without
    # the matching filter in auth_lookup_by_mobile, a staff row carrying a phone
    # number is reachable through POST /auth/otp/verify - no password, no argon2,
    # no lockout, because rule 12 excludes kind='otp'. That is a second, weaker
    # door onto every password account, including the two roles holding global
    # delete.
    #
    # p_max_failures and p_lockout are parameters rather than constants so
    # Settings stays the single source of truth. Baked in here they would drift
    # from Settings.login_max_failures and Settings.login_lockout, and those two
    # would become config written and read by nobody - which is round 3's B-11
    # exactly (FS-001 9.6 R5-6).
    op.execute(
        """
        CREATE FUNCTION auth_lookup_staff(p_email citext, p_max_failures int,
                                          p_lockout interval)
        RETURNS TABLE (user_id uuid, password_hash text, is_active boolean,
                       token_version int, locked_until timestamptz)
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $fn$
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
        END $fn$
        """
    )

    # The OTP door opens onto portal and consumer accounts only. See above.
    op.execute(
        """
        CREATE FUNCTION auth_lookup_by_mobile(p_mobile text)
        RETURNS TABLE (user_id uuid, is_active boolean, token_version int)
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $fn$
        BEGIN
            RETURN QUERY
            SELECT u.id, u.is_active, u.token_version
              FROM app_user u
             WHERE u.mobile = p_mobile
               AND u.deleted_at IS NULL
               AND u.user_type IN ('partner_user', 'consumer');
        END $fn$
        """
    )

    # Snapshots the user's CURRENT token_version. On rotation the successor takes
    # the current value, never the predecessor's, or a bump landing mid-rotation is
    # carried forward and never detected.
    #
    # p_door is a door, not an event kind. The pre-auth role can say which of two
    # doors a session came through; it cannot say what appears on a user's
    # timeline. A function granted to app_anon that took a free-text kind would let
    # an unauthenticated caller write timeline rows (rule 26).
    #   'password' | 'otp' -> one activity_event, in THIS transaction (rule 7)
    #   NULL               -> nothing. Rotation creates a session and is not a
    #                         sign-in; section 5 lists sign-in, sign-out and family
    #                         revocation, and rotation is none of them.
    #
    # actor_id is p_user_id. It cannot come from app_current_user_id() - the
    # pre-auth path sets no claim by design. RBAC.md 5.2c's rule that the actor is
    # never a parameter governs an authenticated caller overriding a claim that has
    # already been verified; here there is no claim to override.
    op.execute(
        """
        CREATE FUNCTION auth_create_session(p_user_id uuid, p_refresh_hash text,
                                            p_family_id uuid, p_ttl interval,
                                            p_ua text, p_ip inet,
                                            p_door text DEFAULT NULL)
        -- token_version is returned, not just stored. The access token must carry
        -- the same value the session row holds, and every caller has a value it
        -- could pass instead - which is the arrangement where the two can drift
        -- apart and produce a 401 nobody can explain. Returning the stamped value
        -- makes them the same value by construction.
        RETURNS TABLE (session_id uuid, expires_at timestamptz, token_version int)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
        DECLARE
            v_session_id uuid;
            v_expires_at timestamptz;
            v_token_version int;
        BEGIN
            IF p_door IS NOT NULL AND p_door NOT IN ('password', 'otp') THEN
                RAISE EXCEPTION 'unknown sign-in door: %', p_door
                    USING ERRCODE = '22023';
            END IF;

            -- The same family lock auth_claim_refresh and auth_revoke_sessions
            -- take, so a successor cannot be inserted into a family while a
            -- revocation of it is in flight. On rotation this transaction already
            -- holds it and re-acquiring is free; on a fresh sign-in the family is
            -- new and uncontended (FS-001 9.8 X-1).
            PERFORM pg_advisory_xact_lock(3, hashtext(p_family_id::text));

            -- deleted_at IS NULL and is_active, not just the id. Every caller
            -- checks eligibility before reaching here, so this changes no
            -- behaviour today - but this is the one function that mints a session,
            -- and a caller that forgets should get zero rows rather than a working
            -- session for a removed or disabled account (FS-001 9.8 X-3).
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

            -- No such user, or not an eligible one: nothing inserted, nothing
            -- returned. The caller sees zero rows rather than a session belonging
            -- to nobody.
            IF NOT FOUND THEN
                RETURN;
            END IF;

            IF p_door IS NOT NULL THEN
                -- last_login_at otherwise has no writer at all, and it is the only
                -- column that answers "when did this person last sign in" for a
                -- user who never creates anything (FS-001 EC-23).
                UPDATE app_user SET last_login_at = now() WHERE id = p_user_id;

                INSERT INTO activity_event (entity_type, entity_id, kind,
                                            actor_id, payload)
                VALUES ('app_user', p_user_id, 'auth.signed_in', p_user_id,
                        jsonb_build_object('door', p_door, 'session_id', v_session_id));
            END IF;

            RETURN QUERY SELECT v_session_id, v_expires_at, v_token_version;
        END $fn$
        """
    )

    # p_kind separates three ledgers that were one column in rev 2:
    #   'password'  both outcomes. Failures feed the 5-failure lockout, successes
    #               reset it (rule 5). Both clauses read this ledger.
    #   'otp'       both outcomes. Failures are audit only - excluded from the
    #               lockout (rule 12). Successes are what the daily cap resets from.
    #   'otp_issue' a code issued. THIS is what the daily cap counts, and it is in
    #               Postgres rather than Redis deliberately: it is the only bound on
    #               a campaign, so a restart must not clear it.
    op.execute(
        """
        CREATE FUNCTION auth_record_attempt(p_identifier citext, p_ip inet,
                                            p_succeeded boolean, p_kind login_kind)
        RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
        BEGIN
            INSERT INTO login_attempt (identifier, ip, succeeded, kind)
            VALUES (p_identifier, p_ip, p_succeeded, p_kind);
        END $fn$
        """
    )

    # The whole of POST /auth/otp/request, in one definer call.
    #
    # One function rather than four keeps the grant surface small: app_anon needs
    # no SELECT on login_attempt and no INSERT on notification_outbox, neither of
    # which it should ever hold.
    #
    # It takes the PLAINTEXT code, not a hash. The outbox row it writes is how the
    # code reaches the user, and a hash cannot be sent. The hash never needs to
    # reach the database at all - the 5-attempt verification is Redis, and the
    # caller hashes the code it generated (FS-001 9.6 R5-7).
    #
    # It takes NO message body, and must not. A definer function granted to
    # app_anon that accepted free-text message content would be an open SMS relay
    # to any number, at our cost. The row carries a template key and a payload; the
    # body is rendered by the drain job from the constant in integrations/
    # (GAP-022). Channel is 'sms' rather than a parameter because WhatsApp requires
    # a prior opt-in that a first-time user does not have.
    #
    # Returns false for capped, unknown and inactive alike. The caller cannot tell
    # them apart and neither can the response - section 4's always-202.
    op.execute(
        """
        CREATE FUNCTION auth_issue_otp_challenge(p_mobile text, p_ip inet,
                                                 p_code text, p_daily_cap int)
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
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

            INSERT INTO notification_outbox (channel, template_key, recipient, payload)
            VALUES ('sms', 'auth.otp', p_mobile,
                    jsonb_build_object('code', p_code));

            RETURN true;
        END $fn$
        """
    )

    # Steps 2 and 3 of POST /auth/refresh, in one call. Refresh carries no
    # Authorization header, so it runs under get_db_anon like login does - rev 5
    # left it issuing these statements from the router, against tables app_anon
    # holds no grant on (9.5 R5-1).
    #
    # The conditional UPDATE is what serialises two callers: an overlapping loser
    # BLOCKS on the row lock rather than reading zero rows, which is the mechanism
    # section 8.2 rests on. It stays a single statement.
    #
    # The step-3 re-check runs inside a sub-block so a rejection rolls used_at back
    # by savepoint rather than by a compensating UPDATE. Executed against 16.14
    # (section 8.2a): a SECURITY DEFINER plpgsql call runs in the CALLER'S
    # transaction, so the commit boundary does not move; on the success path the
    # sub-block commits into the parent and the row lock is HELD through the
    # caller's COMMIT, which is the case section 8.2 needs; on the rejection path
    # the rollback RELEASES the lock early. That last one went the other way from
    # the argument and is harmless - section 8.2's table already carries the
    # ordering, and the loser reads the same app_user row and rejects identically.
    #
    # Returns an outcome rather than raising. A raised exception reaches SQLAlchemy
    # as a DBAPIError indistinguishable from a genuine failure, turning four
    # specific 401s into a 500, and it aborts the transaction the classification
    # query still has to run in.
    op.execute(
        """
        CREATE FUNCTION auth_claim_refresh(p_refresh_hash text)
        RETURNS TABLE (outcome text, session_id uuid, user_id uuid,
                       family_id uuid, token_version int)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
        DECLARE
            v_session_id uuid;
            v_user_id    uuid;
            v_family_id  uuid;
            v_session_tv int;
            v_user_tv    int;
            v_active     boolean;
        BEGIN
            -- Take the family lock BEFORE the claim, which is why the family is
            -- read here with an ordinary SELECT rather than taken from the UPDATE's
            -- RETURNING. This read is not authoritative and does not need to be -
            -- the conditional UPDATE below is still what decides who claims. The
            -- lock only fixes an ordering.
            --
            -- Ordering is the point. auth_revoke_sessions takes the same lock
            -- before its UPDATE, so both paths take family lock then row locks, in
            -- that order. Taking it after the claim instead would invert the order
            -- against revocation and deadlock the pair.
            --
            -- What it fixes: a revocation that overlaps a rotation blocked on the
            -- predecessor's row lock, woke after the rotation committed, and its
            -- UPDATE never saw the successor inserted meanwhile - so reuse
            -- detection left a live refresh token in a family it had just revoked.
            -- Reproduced through PgBouncer (FS-001 9.8 X-1).
            SELECT s.family_id INTO v_family_id
              FROM session s WHERE s.refresh_token_hash = p_refresh_hash;
            IF FOUND THEN
                PERFORM pg_advisory_xact_lock(3, hashtext(v_family_id::text));
            END IF;

            BEGIN
                UPDATE session s SET used_at = now()
                 WHERE s.refresh_token_hash = p_refresh_hash
                   AND s.used_at    IS NULL
                   AND s.revoked_at IS NULL
                   AND s.expires_at > now()
                RETURNING s.id, s.user_id, s.family_id, s.token_version
                     INTO v_session_id, v_user_id, v_family_id, v_session_tv;

                IF NOT FOUND THEN
                    RETURN QUERY SELECT 'not_claimed'::text, NULL::uuid, NULL::uuid,
                                        NULL::uuid, NULL::int;
                    RETURN;
                END IF;

                -- FOR SHARE, and deleted_at, and both are defects this row had.
                --
                -- FOR SHARE holds the user row against a concurrent bump for the
                -- rest of this transaction. Without it an offboarding landing
                -- between this check and auth_create_session was defeated: the
                -- check passed against version 0, the bump committed, and the
                -- successor then snapshotted version 1 - so the session the bump
                -- was meant to kill refreshed cleanly under the new version.
                -- Executed with two connections (FS-001 9.8 X-2). It is a shared
                -- lock, so concurrent refreshes from several devices do not block
                -- each other; only an actual write to the user row waits.
                --
                -- deleted_at IS NULL because both sign-in lookups filter it and
                -- this one did not, so a soft-deleted account kept refreshing
                -- indefinitely - and its mobile number can be reissued to someone
                -- else while those tokens still work (FS-001 9.8 X-3).
                SELECT u.is_active, u.token_version
                  INTO v_active, v_user_tv
                  FROM app_user u
                 WHERE u.id = v_user_id AND u.deleted_at IS NULL
                   FOR SHARE;

                IF NOT FOUND
                   OR NOT coalesce(v_active, false)
                   OR v_user_tv IS DISTINCT FROM v_session_tv THEN
                    -- A private SQLSTATE, so the handler below cannot swallow a
                    -- genuine error raised by anything else in this block.
                    RAISE EXCEPTION 'step 3 rejected' USING ERRCODE = 'PT001';
                END IF;
            EXCEPTION WHEN SQLSTATE 'PT001' THEN
                RETURN QUERY SELECT 'session_revoked'::text, NULL::uuid, NULL::uuid,
                                    NULL::uuid, NULL::int;
                RETURN;
            END;

            -- v_user_tv, not v_session_tv: the successor records the user's current
            -- value, or a bump landing mid-rotation is carried forward forever.
            RETURN QUERY SELECT 'claimed'::text, v_session_id, v_user_id,
                                v_family_id, v_user_tv;
        END $fn$
        """
    )

    # The classification read, and nothing else. STABLE, so "it classifies only and
    # never writes" is a property of the function rather than a promise about the
    # caller. Zero rows is classification 4, invalid_refresh. The precedence rules
    # that act on this live in domain/, where they are tested without a database.
    op.execute(
        """
        CREATE FUNCTION auth_classify_refresh(p_refresh_hash text)
        RETURNS TABLE (session_id uuid, family_id uuid, used_at timestamptz,
                       revoked_at timestamptz, expires_at timestamptz)
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $fn$
        BEGIN
            RETURN QUERY
            SELECT s.id, s.family_id, s.used_at, s.revoked_at, s.expires_at
              FROM session s
             WHERE s.refresh_token_hash = p_refresh_hash;
        END $fn$
        """
    )

    # Sign-out, and the family revocation classification 1 triggers. Both are
    # pre-auth: logout accepts the refresh cookie alone, and a family revocation
    # happens on a request that by definition has no valid token.
    #
    # Exactly one id, and which one decides the event. Derived rather than passed,
    # for the same reason p_door is a door (rule 26). The router must return 204
    # without calling this at all when neither credential is present, or EC-17's
    # contract guard turns a 204 into a 500.
    #
    # The UPDATE ... WHERE revoked_at IS NULL RETURNING idiom is the mechanism, not
    # a detail: two reuse detections on one family arrive milliseconds apart by
    # construction, and both classify as used. They serialise on the row locks, the
    # loser matches zero rows and emits nothing. One event per distinct user AMONG
    # THE ROWS THIS CALL CHANGED, computed from RETURNING rather than from a second
    # query over family_id, so it stays correct for a family that somehow spans
    # users (EC-20, EC-24).
    op.execute(
        """
        CREATE FUNCTION auth_revoke_sessions(p_session_id uuid, p_family_id uuid)
        RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
        DECLARE
            v_kind text;
            v_n    int;
        BEGIN
            IF (p_session_id IS NULL) = (p_family_id IS NULL) THEN
                RAISE EXCEPTION
                    'exactly one of p_session_id and p_family_id must be given'
                    USING ERRCODE = '22023';
            END IF;

            v_kind := CASE WHEN p_family_id IS NOT NULL
                           THEN 'auth.family_revoked' ELSE 'auth.signed_out' END;

            -- Family lock first, then the row locks the UPDATE takes - the same
            -- order auth_claim_refresh and auth_create_session use, so the three
            -- cannot deadlock against each other.
            --
            -- Without it, a revocation racing a rotation blocked on the
            -- predecessor's row lock and its UPDATE's snapshot never included the
            -- successor the rotation committed meanwhile: the family reported as
            -- revoked while one refresh token in it stayed live. A single-session
            -- logout needs no such lock, since nothing mints into a session id
            -- (FS-001 9.8 X-1).
            IF p_family_id IS NOT NULL THEN
                PERFORM pg_advisory_xact_lock(3, hashtext(p_family_id::text));
            END IF;

            WITH revoked AS (
                UPDATE session s SET revoked_at = now()
                 WHERE s.revoked_at IS NULL
                   AND ((p_family_id IS NOT NULL AND s.family_id = p_family_id)
                     OR (p_family_id IS NULL     AND s.id        = p_session_id))
                RETURNING s.user_id
            ), emitted AS (
                INSERT INTO activity_event (entity_type, entity_id, kind,
                                            actor_id, payload)
                SELECT 'app_user', r.user_id, v_kind, r.user_id,
                       jsonb_build_object('sessions', count(*))
                  FROM revoked r
                 GROUP BY r.user_id
                RETURNING 1
            )
            SELECT count(*)::int INTO v_n FROM revoked;

            RETURN v_n;
        END $fn$
        """
    )


# ── 6. triggers and the seed assertion ───────────────────────────────────────

def _triggers() -> None:
    # EC-1. A trigger rather than a CHECK, because the check spans two tables.
    op.execute(
        """
        CREATE FUNCTION app_user_role_family_check() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        DECLARE r role%ROWTYPE;
        BEGIN
            -- Before the consumer branch returns, not after it. Rule 27 is about
            -- moving a user between doors, and converting staff or a portal user
            -- INTO a consumer is such a move - but the consumer branch returned
            -- early and skipped the bump that lives further down, so sessions
            -- minted through the old door survived the conversion. Every
            -- user_type transition bumps, in one place (FS-001 9.8 X-7).
            IF TG_OP = 'UPDATE' AND NEW.user_type IS DISTINCT FROM OLD.user_type THEN
                NEW.token_version := OLD.token_version + 1;
            END IF;

            IF NEW.user_type = 'consumer' THEN
                -- Proposed-Schema.md section 2: role_id is "null for consumers".
                -- Without this branch a consumer row holding admin_sales passes the
                -- CHECK, and app_scope() and app_has_permission() resolve global
                -- delete on it - they join on role_id and never read user_type.
                -- Reachable by OTP on a phone the holder controls.
                IF NEW.role_id IS NOT NULL THEN
                    RAISE EXCEPTION 'consumers hold no role' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;

            -- Without this, a NULL role_id falls through to "role <NULL> does not
            -- exist" with a foreign-key SQLSTATE, which is a misleading message for
            -- what is a not-null violation.
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
        END $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_app_user_role_family
            BEFORE INSERT OR UPDATE OF role_id, user_type ON app_user
            FOR EACH ROW EXECUTE FUNCTION app_user_role_family_check()
        """
    )

    # B-10. The trigger above fires on app_user, so it cannot see the change that
    # reopens EC-1 from the other side: UPDATE role SET is_portal = false
    # invalidates every partner_user holding that role and touches no app_user row.
    #
    # IS DISTINCT FROM rather than <> is load-bearing and invisible. An idempotent
    # reseed - INSERT ... ON CONFLICT (code) DO UPDATE writing identical values -
    # passes only because comparing equal values yields false. With <>, NULL
    # comparisons return NULL, which is not true, so the reseed still passes but
    # stops catching an actual flip to or from NULL.
    op.execute(
        """
        CREATE FUNCTION role_flags_are_seed_only() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        BEGIN
            IF NEW.is_portal     IS DISTINCT FROM OLD.is_portal
               OR NEW.is_functional IS DISTINCT FROM OLD.is_functional
               OR NEW.code          IS DISTINCT FROM OLD.code THEN
                RAISE EXCEPTION
                    'role family and code are seeded, not editable: %', OLD.code
                    USING ERRCODE = '23514',
                          HINT = 'change RBAC.md and reseed; app_user rows '
                                 'depend on these flags';
            END IF;
            RETURN NEW;
        END $fn$
        """
    )
    # name and level stay editable - neither is load-bearing. INSERT is untouched,
    # so adding a role stays possible, and role_permission carries no such trigger,
    # so ISS-031's matrix correction is unblocked. GAP-023 records that a consumer
    # portal would need this relaxed.
    op.execute(
        """
        CREATE TRIGGER trg_role_flags_seed_only
            BEFORE UPDATE ON role
            FOR EACH ROW EXECUTE FUNCTION role_flags_are_seed_only()
        """
    )

    # EC-4, as a function rather than an inline DO block so migration 019's seed
    # and the test suite both call the same code. It passes trivially on 003's
    # empty table; it exists for the role added in week six by someone who has not
    # read RBAC.md section 6, whose UPDATEs would otherwise return zero rows
    # forever without raising anything (ISS-029).
    op.execute(
        """
        CREATE FUNCTION assert_role_permission_invariants() RETURNS void
        LANGUAGE plpgsql AS $fn$
        DECLARE bad text;
        BEGIN
            SELECT string_agg(DISTINCT format('%s/%s', r.code, rp.module), ', ')
              INTO bad
              FROM role_permission rp
              JOIN role r ON r.id = rp.role_id
             WHERE NOT EXISTS (SELECT 1 FROM role_permission v
                                WHERE v.role_id = rp.role_id
                                  AND v.module  = rp.module
                                  AND v.action  = 'view');
            IF bad IS NOT NULL THEN
                RAISE EXCEPTION 'role_permission without a view row: %', bad;
            END IF;

            -- Scope is per row, but app_scope() reads only the view row's. A
            -- create row carrying a different scope silently claims something it
            -- does not grant. The grouped query is wrapped because plpgsql
            -- SELECT INTO keeps the first row and discards the rest - unwrapped,
            -- the migration fails while naming one arbitrary offender out of
            -- however many exist.
            SELECT string_agg(x, ', ') INTO bad FROM (
                SELECT format('%s/%s', r.code, rp.module) AS x
                  FROM role_permission rp
                  JOIN role r ON r.id = rp.role_id
                 GROUP BY r.code, rp.module
                HAVING count(DISTINCT rp.scope) > 1
            ) t;
            IF bad IS NOT NULL THEN
                RAISE EXCEPTION 'role_permission with mixed scopes for one module: %',
                    bad;
            END IF;
        END $fn$
        """
    )
    op.execute("SELECT assert_role_permission_invariants()")

    # updated_at on this migration's business tables. 002's two already have it.
    for table in BUSINESS:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION set_updated_at()
            """
        )

    # The generic audit trigger, on every business table including 002's - this is
    # the first point at which app_current_user_id() exists.
    #
    # NOT on session, login_attempt, idempotency_record, notification_outbox or
    # activity_event: those are append-and-expire infrastructure, and auditing them
    # would duplicate their own content at volume.
    for table in AUDITED:
        if table == "app_user":
            continue
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_audit
                AFTER INSERT OR UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION audit_row()
            """
        )

    # app_user is split in two so the UPDATE half can carry a WHEN clause. Every
    # sign-in writes last_login_at, and without this an audit row would be produced
    # for each one - a few thousand a day that say nothing activity_event does not
    # already say, burying the changes a human opens audit_log to find. A WHEN
    # clause cannot span INSERT and DELETE, because it may not reference OLD on an
    # insert or NEW on a delete, hence two triggers.
    #
    # updated_at is excluded from the comparison too: set_updated_at bumps it on
    # every update, so a last_login_at-only write would still differ without it.
    op.execute(
        """
        CREATE TRIGGER trg_app_user_audit_ins_del
            AFTER INSERT OR DELETE ON app_user
            FOR EACH ROW EXECUTE FUNCTION audit_row()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_app_user_audit_upd
            AFTER UPDATE ON app_user
            FOR EACH ROW
            WHEN (to_jsonb(OLD) - 'last_login_at' - 'updated_at'
                  IS DISTINCT FROM
                  to_jsonb(NEW) - 'last_login_at' - 'updated_at')
            EXECUTE FUNCTION audit_row()
        """
    )


# ── 7. grants ────────────────────────────────────────────────────────────────

def _grants() -> None:
    """Guarded, so a cluster without app_anon gets a NOTICE and not a failure.

    CREATE ROLE is NOT here. Roles are cluster-level objects and a migration is
    per-database, so the same migration against a second database in the cluster
    would fail on the duplicate - and appuser holds no CREATEROLE anyway, verified
    on this box. Provisioning is two statements a person runs: CREATE ROLE app_anon
    NOLOGIN, then GRANT app_anon TO <the application login role>. The second is not
    optional and does not look necessary: SET ROLE requires membership, and
    creating a role grants the creator nothing. See docs/workflows/
    local-environment.md and GAP-021.
    """
    op.execute(
        """
        DO $$
        DECLARE v_public int;
        BEGIN
            -- PUBLIC is the statement that carries the weight, not app_anon.
            -- Verified on 16.14: a function's proacl is NULL right after CREATE,
            -- and NULL means the default, which is EXECUTE to PUBLIC. So without
            -- these three lines app_anon inherits EXECUTE on every function in the
            -- schema - including the five SECURITY DEFINER RBAC helpers created a
            -- few statements earlier. A pre-auth connection could then call
            -- set_config('app.current_user_id', <any uuid>, true) and read that
            -- user's role, org unit, partner and entire permission set.
            --
            -- REVOKE ... FROM app_anon is not the fix and never was: it is a no-op
            -- against a freshly created role that holds nothing directly.
            REVOKE ALL     ON ALL TABLES    IN SCHEMA public FROM PUBLIC;
            REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

            -- ALTER DEFAULT PRIVILEGES ... REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC
            -- WAS here, as the line that was supposed to stop migration 004 onward
            -- reopening this. It is not, and it never was: executed against 16.14,
            -- a bare REVOKE in ALTER DEFAULT PRIVILEGES writes no pg_default_acl
            -- row at all, so it changes nothing. It is removed rather than left in,
            -- because a statement that does nothing while reading as protection is
            -- worse than no statement.
            --
            -- What enforces it instead is a test over the live schema:
            -- tests/db/test_migration_003_identity.py asserts that no function this
            -- project created is executable by PUBLIC. Migration 004 adding a
            -- function without repeating the REVOKE above fails the suite. That is
            -- verified rather than assumed, which is the property rule 24 wanted.
            -- ISS-040.
            --
            -- The REVOKE above also cannot reach the pgcrypto, pg_trgm and citext
            -- functions: their grants to PUBLIC were made by another role, and only
            -- the grantor can revoke. None of them reads an application table, so
            -- the containment argument holds - but the assertion has to say
            -- "nothing this project created" rather than "nothing". ISS-039.

            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_anon') THEN
                GRANT USAGE ON SCHEMA public TO app_anon;
                GRANT EXECUTE ON FUNCTION
                    auth_lookup_staff(citext, int, interval),
                    auth_lookup_by_mobile(text),
                    auth_create_session(uuid, text, uuid, interval, text, inet, text),
                    auth_record_attempt(citext, inet, boolean, login_kind),
                    auth_issue_otp_challenge(text, inet, text, int),
                    auth_claim_refresh(text),
                    auth_classify_refresh(text),
                    auth_revoke_sessions(uuid, uuid)
                  TO app_anon;
            ELSE
                RAISE NOTICE 'app_anon does not exist; pre-auth containment is not active. %',
                             'See GAP-021.';
            END IF;

            -- Say plainly what the REVOKE above could not reach, rather than
            -- leaving it to be discovered by a test in staging.
            SELECT count(*) INTO v_public
              FROM pg_proc p
              JOIN pg_namespace n ON n.oid = p.pronamespace
              LEFT JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e'
             WHERE n.nspname = 'public' AND d.objid IS NULL
               AND has_function_privilege('public', p.oid, 'EXECUTE');
            IF v_public > 0 THEN
                RAISE EXCEPTION
                    '% functions in public are still executable by PUBLIC', v_public;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    for table in ("activity_event", "notification_outbox", "idempotency_record",
                  "login_attempt", "session", "user_territory", "app_user",
                  "role_permission", "role"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for fn in ("assert_role_permission_invariants()", "role_flags_are_seed_only()",
               "app_user_role_family_check()", "auth_revoke_sessions(uuid, uuid)",
               "auth_classify_refresh(text)", "auth_claim_refresh(text)",
               "auth_issue_otp_challenge(text, inet, text, int)",
               "auth_record_attempt(citext, inet, boolean, login_kind)",
               "auth_create_session(uuid, text, uuid, interval, text, inet, text)",
               "auth_lookup_by_mobile(text)",
               "auth_lookup_staff(citext, int, interval)",
               "app_scope(text)", "app_has_permission(text, text)",
               "app_current_role()", "app_current_partner()",
               "app_current_org_unit()", "app_current_user_id()"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn} CASCADE")
    # 002's tables survive this downgrade, so what 003 attached to them has to be
    # taken off explicitly - the audit triggers and the deferred FK constraints.
    # Without this the next upgrade fails on "trigger already exists".
    for table in ("territory", "org_unit"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_audit ON {table}")
        for col in ("created_by", "updated_by"):
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_{col}")
    for enum in ("notification_state", "notification_channel", "idempotency_state",
                 "login_kind", "permission_scope", "permission_action", "user_type"):
        op.execute(f"DROP TYPE IF EXISTS {enum}")
