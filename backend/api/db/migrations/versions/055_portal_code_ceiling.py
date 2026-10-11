"""055: an hourly ceiling on sign-in codes to customers (FS-047, GAP-269).

With the consumer portal on, any customer's number can ask for a paid WhatsApp
code. The per-number and per-address limits bound one number and one address,
not a leaked list sent from many. `portal_otp_hourly_cap` bounds the whole: at
most N codes an hour to consumers. Dealers are not counted and never refused by
it, so customer traffic cannot lock them out.

`auth_issue_otp_challenge` is rebuilt from 008's text by anchored replacements
(020's idiom), so upgrade and downgrade share one source. The final text is
`AUTH_ISSUE_OTP_055`; `tests/db/test_drift_008.py` compares the live body with it.

Revision ID: 055_portal_code_ceiling
Revises: 054_approval_step_stalled
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "055_portal_code_ceiling"
down_revision: str | None = "054_approval_step_stalled"
branch_labels = None
depends_on = None


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_055", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"055: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"055: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


AUTH_ISSUE_OTP_008: str = _load("008_message_delivery").AUTH_ISSUE_OTP_008


def _after() -> str:
    f = AUTH_ISSUE_OTP_008
    f = _replace(f, """        v_user_id uuid;
        v_issued  int;
""", """        v_user_id uuid;
        v_issued  int;
        v_type    text;
        v_cap     int;
""")
    f = _replace(f, """        -- them, per phone, for the length of the transaction (9.6 R5-8).
        -- Two-integer key, not a single 64-bit hash. There are three
        -- advisory-lock consumers in this schema now (1 = OTP by phone,
        -- 2 = a closure tree, 3 = a session family), and a single-key hash
        -- puts them all in one unpartitioned space where unrelated requests
        -- can serialise against each other. ISS-042, which predicted exactly
        -- this moment.""", """        -- them, per phone, for the length of the transaction (FS-001 9.7 R6-3).
        -- Two-integer keys, not a single 64-bit hash, so unrelated requests
        -- never serialise against each other (ISS-042). Namespaces: 1 = OTP by
        -- phone, 2 = a closure tree, 3 = a session family, 4 = the handover and
        -- the administrator floor, 5 = a lead acknowledgement or a master's
        -- effective dates, 6 = the public lead code, 7 = the customer code
        -- ceiling (FS-047).""")
    f = _replace(f, """        SELECT u.id INTO v_user_id
          FROM app_user u""", """        SELECT u.id, u.user_type INTO v_user_id, v_type
          FROM app_user u""")
    f = _replace(f, """        IF NOT FOUND THEN
            RETURN false;
        END IF;
""", """        IF NOT FOUND THEN
            RETURN false;
        END IF;

        -- FS-047: at most portal_otp_hourly_cap codes an hour to customers,
        -- across all numbers. Dealers are neither counted nor refused. First an
        -- unlocked count, so a flood at the cap is refused without queuing on
        -- the lock (edge E-1); a stale read only undercounts, and the locked
        -- recount corrects it. Namespace 7 after namespace 1, always.
        -- The count is of numbers that belong to an active consumer now (rule 2).
        IF v_type = 'consumer' THEN
            v_cap := (app_setting_json('portal_otp_hourly_cap') #>> '{}')::numeric::int;
            -- a null cap (only reachable past the setting's trigger) fails closed
            IF v_cap IS NULL OR v_cap <= 0 OR (SELECT count(*) FROM login_attempt la
                                JOIN app_user c ON c.mobile = la.identifier
                               WHERE la.kind = 'otp_issue'
                                 AND la.attempted_at > now() - interval '1 hour'
                                 AND c.user_type = 'consumer' AND c.is_active
                                 AND c.deleted_at IS NULL) >= v_cap THEN
                RETURN false;
            END IF;
            PERFORM pg_advisory_xact_lock(7, 0);
            IF (SELECT count(*) FROM login_attempt la
                  JOIN app_user c ON c.mobile = la.identifier
                 WHERE la.kind = 'otp_issue'
                   AND la.attempted_at > now() - interval '1 hour'
                   AND c.user_type = 'consumer' AND c.is_active
                   AND c.deleted_at IS NULL) >= v_cap THEN
                RETURN false;
            END IF;
        END IF;
""")
    return f


AUTH_ISSUE_OTP_055: str = _after()

SEED = """INSERT INTO app_setting (key, kind, value, allowed, min, max, description) VALUES
('portal_otp_hourly_cap', 'int', '100', NULL, 0, 10000,
 'Most sign-in codes sent to customers in one hour, across all numbers. 0 sends none. Dealers'' codes are not counted.')
ON CONFLICT (key) DO NOTHING"""


def upgrade() -> None:
    op.execute(SEED)
    op.execute(AUTH_ISSUE_OTP_055)


def downgrade() -> None:
    op.execute(AUTH_ISSUE_OTP_008)
    op.execute("DELETE FROM activity_event WHERE kind = 'setting.changed' "
               "AND payload->>'key' = 'portal_otp_hourly_cap'")
    op.execute("DELETE FROM app_setting WHERE key = 'portal_otp_hourly_cap'")
