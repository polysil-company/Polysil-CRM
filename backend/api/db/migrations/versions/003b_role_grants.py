"""003b role grants: the grants 003 skipped because the role did not exist yet

**Why this exists.** Roles are cluster objects and are provisioned by a person, not
by a migration (`local-environment.md`, GAP-021). Grants are per-database and live
in migrations. So there is an ordering problem: 003's grant block is guarded on
`app_anon` existing, and on every database migrated before that role was provisioned it took the
NOTICE branch. The eight `GRANT EXECUTE` statements never ran.

The role now exists and `DB_ANON_ROLE=app_anon` is set, so `get_db_anon` switches
into a role that holds nothing. Every sign-in, OTP verify, refresh and cookie
logout raises `42501`.

003 has run on more than one machine, so this is forward-only (ISS-046). It is
idempotent: `GRANT` on something already granted is a no-op.

**The guard stays, and that is a known weakness.** Without it the `local` compose
profile cannot migrate. `tests/db/test_pre_auth_grants.py` is what turns a silent
skip into a red suite: when `DB_ANON_ROLE` is set, it asserts all eight grants are
present. ISS-052 records the rule for the next migration that grants to a role:
if the feature is meaningless without the role, raise, do not NOTICE.

Revision ID: 003b_role_grants
Revises: 003a_auth_fixups
Created: during development
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "003b_role_grants"
down_revision: str | None = "003a_auth_fixups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The same eight, with the same signatures, as 003's grant block. Enumerated here
# rather than "ALL FUNCTIONS" because the containment argument is that app_anon
# reaches exactly these and nothing else.
PRE_AUTH_FUNCTIONS = """
    auth_lookup_staff(citext, int, interval),
    auth_lookup_by_mobile(text),
    auth_create_session(uuid, text, uuid, interval, text, inet, text),
    auth_record_attempt(citext, inet, boolean, login_kind),
    auth_issue_otp_challenge(text, inet, text, int),
    auth_claim_refresh(text),
    auth_classify_refresh(text),
    auth_revoke_sessions(uuid, uuid)
"""


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_anon') THEN
                GRANT USAGE ON SCHEMA public TO app_anon;
                GRANT EXECUTE ON FUNCTION {PRE_AUTH_FUNCTIONS} TO app_anon;
            ELSE
                RAISE NOTICE 'app_anon does not exist; nothing granted. See GAP-021.';
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_anon') THEN
                REVOKE EXECUTE ON FUNCTION {PRE_AUTH_FUNCTIONS} FROM app_anon;
                REVOKE USAGE ON SCHEMA public FROM app_anon;
            END IF;
        END $$
        """
    )
