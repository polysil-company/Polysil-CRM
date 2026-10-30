"""003a auth fixups: a changed return type, and a lock on the OTP lookup

**Why this is a separate revision rather than another edit to 003.**

003 was amended in place while nothing had shipped, which was the right call then
and stopped being right the moment another machine had run it. `auth_create_session`
gained a third output column (`token_version`) after 003 had already been applied
here and on at least one other checkout. `alembic upgrade head` has no new revision
to run on those databases, so they keep the two-column function while the service
selects three - and **every sign-in, OTP verify and refresh fails with an undefined
column**. A migration that only exists inside an already-applied revision is not a
migration.

The lettered suffix follows `Schema-Corrections.md` §5, which already uses `006a`,
`009a` and `013a` for exactly this: a fixup that must not take the next numbered
slot, since `004` is `channel_partner`.

Both statements below are `DROP` + `CREATE` rather than `CREATE OR REPLACE`:
PostgreSQL refuses to replace a function whose return type has changed. (An
earlier version of this note said a volatility change needs the same; it does
not. `CREATE OR REPLACE` changes volatility, executed while writing 007, which
flips two 006 functions to VOLATILE that way. A DROP also resets the ACL to
PUBLIC-executable, so the re-grant below is load-bearing.)

Revision ID: 003a_auth_fixups
Revises: 003_identity
Created: during development
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "003a_auth_fixups"
down_revision: str | None = "003_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent against a database that already has the three-column form from
    # the amended 003: dropping and recreating lands on the same definition.
    op.execute(
        "DROP FUNCTION IF EXISTS auth_create_session"
        "(uuid, text, uuid, interval, text, inet, text)"
    )
    op.execute(
        """
        CREATE FUNCTION auth_create_session(p_user_id uuid, p_refresh_hash text,
                                            p_family_id uuid, p_ttl interval,
                                            p_ua text, p_ip inet,
                                            p_door text DEFAULT NULL)
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
        END $fn$
        """
    )

    # VOLATILE now, and it takes a lock, so it is no longer a pure lookup and must
    # not claim to be one.
    #
    # Two correct OTP submissions arriving together both passed every check and
    # both minted a session - one code, two credentials. Reproduced. The lock is
    # what serialises them: the loser blocks here, wakes after the winner commits,
    # and the caller then re-reads the replay cache and returns the winner's
    # bundle. It is the same blocked-then-re-read shape FS-001 section 8.2 relies
    # on for refresh, and it reuses class 1 - the OTP namespace - so it also
    # serialises against auth_issue_otp_challenge for the same number (ISS-042).
    op.execute("DROP FUNCTION IF EXISTS auth_lookup_by_mobile(text)")
    op.execute(
        """
        CREATE FUNCTION auth_lookup_by_mobile(p_mobile text)
        RETURNS TABLE (user_id uuid, is_active boolean, token_version int)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
        BEGIN
            PERFORM pg_advisory_xact_lock(1, hashtext(p_mobile));

            RETURN QUERY
            SELECT u.id, u.is_active, u.token_version
              FROM app_user u
             WHERE u.mobile = p_mobile
               AND u.deleted_at IS NULL
               AND u.user_type IN ('partner_user', 'consumer');
        END $fn$
        """
    )

    _regrant()


def downgrade() -> None:
    """Back to 003's shapes: two output columns, and a STABLE lookup with no lock."""
    op.execute(
        "DROP FUNCTION IF EXISTS auth_create_session"
        "(uuid, text, uuid, interval, text, inet, text)"
    )
    op.execute(
        """
        CREATE FUNCTION auth_create_session(p_user_id uuid, p_refresh_hash text,
                                            p_family_id uuid, p_ttl interval,
                                            p_ua text, p_ip inet,
                                            p_door text DEFAULT NULL)
        RETURNS TABLE (session_id uuid, expires_at timestamptz)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
        DECLARE
            v_session_id uuid;
            v_expires_at timestamptz;
        BEGIN
            PERFORM pg_advisory_xact_lock(3, hashtext(p_family_id::text));
            INSERT INTO session (user_id, refresh_token_hash, family_id,
                                 token_version, expires_at, user_agent, ip)
            SELECT p_user_id, p_refresh_hash, p_family_id, u.token_version,
                   now() + p_ttl, p_ua, p_ip
              FROM app_user u
             WHERE u.id = p_user_id AND u.deleted_at IS NULL AND u.is_active
            RETURNING session.id, session.expires_at INTO v_session_id, v_expires_at;
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
            RETURN QUERY SELECT v_session_id, v_expires_at;
        END $fn$
        """
    )
    op.execute("DROP FUNCTION IF EXISTS auth_lookup_by_mobile(text)")
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
    _regrant()


def _regrant() -> None:
    """A dropped function takes its grants with it.

    Without this the two functions come back executable by nobody but the owner,
    and the pre-auth path raises `42501` on the first sign-in in any environment
    where `app_anon` exists - which is exactly the environment where nothing else
    would have caught it.
    """
    op.execute(
        """
        DO $$
        DECLARE v_public int;
        BEGIN
            REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_anon') THEN
                GRANT EXECUTE ON FUNCTION
                    auth_create_session(uuid, text, uuid, interval, text, inet, text),
                    auth_lookup_by_mobile(text)
                  TO app_anon;
            END IF;

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
