"""079: a device token for the tracking app (FS-072, BE-032).

- `tracking_device_token`: one row per user and device. Holds the token's sha256,
  never the token. RLS on with the consumer floor and no other policy, and no grant
  to any role: the definers below are the only way in.
- `tracking_device_token_issue(...)`: called by the API as `app_role`. Takes the
  family lock first (003's key), then checks the session and the token version, so
  a sign-out cannot slip between the check and the write (plan review R-2, EC-5).
- `tracking_device_token_resolve(text)`: called by `get_db` as the owner, before
  any claim is set. Executable by the owner only: it maps a hash to a user (EC-14).
- `tracking_device_token_forget(uuid)`: logout, which runs as `app_anon` (plan
  review B-1). Deletes the tokens of the session's family, whatever the session's
  state, so a stale bearer still reaches them (EC-3).
- `tracking_device_token_purge(timestamptz)`: the retention job, system principal
  only. A plain DELETE as `app_role` would fail and roll back every other purge in
  that transaction (EC-2).
- `ix_session_family_live`: resolve reads the family's newest unused session on
  every batch; the family's used rows are about 50 a day per person (EC-7).

Revision ID: 079_tracking_device_token
Revises: 078_partner_application_deposit
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "079_tracking_device_token"
down_revision: str | None = "078_partner_application_deposit"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
MAX_PER_USER = 3

_spec = importlib.util.spec_from_file_location(
    "consumer_floor_079", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

TABLES = [
    """CREATE TABLE tracking_device_token (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    device_id     text        NOT NULL CHECK (length(device_id) BETWEEN 1 AND 128),
    token_hash    text        NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    family_id     uuid        NOT NULL,
    token_version int         NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    CONSTRAINT uq_tracking_device_token_user_device UNIQUE (user_id, device_id)
)""",
    "CREATE INDEX ix_tracking_device_token_family ON tracking_device_token (family_id)",
    "CREATE INDEX ix_tracking_device_token_device ON tracking_device_token (device_id)",
    "CREATE INDEX ix_session_family_live ON session (family_id, issued_at DESC) WHERE used_at IS NULL AND revoked_at IS NULL",
]

FUNCTIONS = [
    f"""CREATE FUNCTION tracking_device_token_issue(p_session uuid, p_token_version int, p_device text,
                                             p_hash text, p_ttl interval) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_user   uuid := app_current_user_id();
    v_family uuid;
    v_tv     int;
    v_exp    timestamptz;
BEGIN
    IF v_user IS NULL THEN
        RAISE EXCEPTION 'no caller' USING ERRCODE = '42501';
    END IF;
    SELECT family_id INTO v_family FROM session WHERE id = p_session;
    IF v_family IS NULL THEN
        RETURN NULL;
    END IF;
    -- the lock first, then the checks: each statement after it sees a committed sign-out
    PERFORM pg_advisory_xact_lock(3, hashtext(v_family::text));
    IF NOT EXISTS (SELECT 1 FROM session WHERE id = p_session AND user_id = v_user
                     AND revoked_at IS NULL AND expires_at > now()) THEN
        RETURN NULL;
    END IF;
    SELECT token_version INTO v_tv FROM app_user
     WHERE id = v_user AND is_active AND deleted_at IS NULL FOR SHARE;
    IF v_tv IS DISTINCT FROM p_token_version THEN
        RETURN NULL;
    END IF;

    -- one person per phone (rule 8, GAP-522)
    DELETE FROM tracking_device_token WHERE device_id = p_device AND user_id <> v_user;
    v_exp := now() + p_ttl;
    INSERT INTO tracking_device_token (user_id, device_id, token_hash, family_id, token_version, expires_at)
    VALUES (v_user, p_device, p_hash, v_family, p_token_version, v_exp)
    ON CONFLICT (user_id, device_id) DO UPDATE
       SET token_hash = EXCLUDED.token_hash, family_id = EXCLUDED.family_id,
           token_version = EXCLUDED.token_version, created_at = now(), expires_at = EXCLUDED.expires_at;
    -- at most {MAX_PER_USER} per person: the oldest go (EC-12)
    DELETE FROM tracking_device_token WHERE id IN (
        SELECT id FROM tracking_device_token WHERE user_id = v_user
         ORDER BY created_at DESC, id OFFSET {MAX_PER_USER});

    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('app_user', v_user, 'tracking.device_token_issued', v_user,
            jsonb_build_object('device_id', p_device));
    RETURN v_exp;
END $fn$""",
    """CREATE FUNCTION tracking_device_token_resolve(p_hash text)
RETURNS TABLE (user_id uuid, session_id uuid, token_version int, device_id text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT t.user_id, s.id, t.token_version, t.device_id
      FROM tracking_device_token t
      CROSS JOIN LATERAL (
            SELECT s.id FROM session s
             WHERE s.family_id = t.family_id AND s.user_id = t.user_id
               AND s.used_at IS NULL AND s.revoked_at IS NULL AND s.expires_at > now()
             ORDER BY s.issued_at DESC LIMIT 1) s
     WHERE t.token_hash = p_hash AND t.expires_at > now()
$fn$""",
    """CREATE FUNCTION tracking_device_token_forget(p_session uuid) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_family uuid;
    v_n      int;
BEGIN
    SELECT family_id INTO v_family FROM session WHERE id = p_session;
    IF v_family IS NULL THEN
        RETURN 0;
    END IF;
    PERFORM pg_advisory_xact_lock(3, hashtext(v_family::text));
    DELETE FROM tracking_device_token WHERE family_id = v_family;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END $fn$""",
    """CREATE FUNCTION tracking_device_token_purge(p_cut timestamptz) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal purges' USING ERRCODE = '42501';
    END IF;
    DELETE FROM tracking_device_token WHERE expires_at < p_cut;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END $fn$""",
]

ISSUE = "tracking_device_token_issue(uuid, integer, text, text, interval)"
RESOLVE = "tracking_device_token_resolve(text)"
FORGET = "tracking_device_token_forget(uuid)"
PURGE = "tracking_device_token_purge(timestamptz)"
GRANTED_STAFF = [ISSUE, FORGET, PURGE]


def _grant_anon(sig: str) -> None:
    """007's guard: on a box without the role, a NOTICE and nothing granted."""
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


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    op.execute("ALTER TABLE tracking_device_token ENABLE ROW LEVEL SECURITY")
    op.execute(floor.policy_sql("tracking_device_token"))
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in (ISSUE, RESOLVE, FORGET, PURGE):
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
    for sig in GRANTED_STAFF:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    _grant_anon(FORGET)


def downgrade() -> None:
    # credentials, not records: the app asks for new ones after an upgrade
    for sig in (ISSUE, RESOLVE, FORGET, PURGE):
        op.execute(f"DROP FUNCTION {sig}")
    op.execute("DROP INDEX ix_session_family_live")
    op.execute("DROP TABLE tracking_device_token")
