"""Settings, env-driven. No config files in the repo.

Everything reaches Postgres through PgBouncer on 127.0.0.1:6432 (ADR-021, ADR-023).
Whether that is a tunnelled remote instance or a local container is a compose
profile choice, and nothing here knows the difference.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: Literal["local", "staging", "production"] = "local"

    database_url: PostgresDsn
    redis_url: RedisDsn = RedisDsn("redis://127.0.0.1:6379/0")

    jwt_secret: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_ttl: timedelta = timedelta(minutes=15)

    # GAP-012: 30 days is a placeholder pending the client's view on a lost field
    # phone. Changing it is a config edit; existing sessions keep their own expiry,
    # because expires_at is stamped on the row at issue (FS-001 EC-13).
    refresh_token_ttl: timedelta = timedelta(days=30)

    # FS-001 rule 17 and section 8.2. A used refresh token re-presented inside this
    # window replays the cached bundle and creates nothing. It does NOT rotate again:
    # that version handed the session to whoever presented last and suppressed the
    # reuse alarm, inverting ADR-025.
    #
    # 90s, not 10: a mobile HTTP client's default timeout is 10-30s, so a 10-second
    # window expires before the retry it exists to absorb even arrives. It matches
    # otp_replay_window because it absorbs the identical failure.
    refresh_grace: timedelta = timedelta(seconds=90)

    # GAP-013: assumed, not confirmed against a Polysil IT policy.
    password_min_length: int = 12

    # FS-001 5.1. The role get_db_anon switches to for the pre-auth path, via
    # SET LOCAL ROLE. Unset means no switch: the development database's appuser
    # holds no CREATEROLE and is a member of no role, so both CREATE ROLE and
    # SET LOCAL ROLE are rejected there -- verified against PostgreSQL 16.14.
    # Issuing it unconditionally would 500 every sign-in on that box.
    #
    # Unset is a real weakness, not a neutral default: the pre-auth path then runs
    # with the application role's full table grants. /health reports it. GAP-021.
    db_anon_role: str | None = None

    # FS-002 5.1. Every application transaction switches into this role right
    # after the claim is set. appuser stays the login: it owns the schema, so RLS
    # does not apply to it, and every policy is decorative on a transaction that
    # forgets the switch. Unset means no switch, which is a local-only state; the
    # API refuses to start outside local without it (rule 5). GAP-041 is the
    # production hardening where the login itself is a non-owner.
    db_app_role: str | None = "app_role"

    # ISS-064. asyncpg's per-statement timeout, in seconds. Without it a statement
    # whose reply is lost (the SSH tunnel to the development database dropped
    # between request and reply, three times in one evening) waits forever, and a
    # test run that hit it looked like a slow suite for thirty minutes. No
    # statement in this system should take two minutes; one that does is a bug
    # worth an error. None disables it.
    db_command_timeout: float | None = 120.0

    # FS-002 5.6. The worker's principal: a staff row at HQ holding the system
    # role, seeded by migration 005 under this stable id. The worker sets it as
    # its claim and re-validates the row on every job. Nothing looks it up by name.
    system_user_id: str = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"  # uuid5(DNS, "polysil.system")

    # FS-003 rule 4 (GAP-046). owner_org_unit_id is never user-supplied: it is the
    # sales-line unit whose territory covers the lead's territory. When no such unit
    # exists this named anchor catches the lead, so a marketing-entered or
    # partner-entered lead is never invisible to admins. Unset on the dev box, where
    # the covering-unit lookup always resolves against the seeded org tree; a lead
    # whose territory has no covering unit and no anchor is a clean 422, not a 500.
    root_org_unit_id: str | None = None

    # PROJECT-OVERVIEW section 5: Caddy terminates TLS and calls the API over
    # loopback on the same box. So request.client.host is Caddy, not the caller,
    # and every request would land in one rate-limit bucket - 200 OTP requests an
    # hour across all 700 users, after which everyone's code is silently dropped
    # (the endpoint still answers 202, so nobody can tell). login_attempt.ip would
    # be useless for the one investigation it exists for, too.
    #
    # So X-Forwarded-For is trusted, but only when the immediate peer is loopback.
    # That cannot be spoofed from outside the box: an attacker would already have
    # to be on it. Set to 0 to trust nothing, if the API is ever exposed directly.
    trusted_proxy_hops: int = 1

    login_max_failures: int = 5
    login_lockout: timedelta = timedelta(minutes=15)

    otp_length: int = 6
    otp_ttl: timedelta = timedelta(minutes=5)
    otp_max_attempts: int = 5
    # FS-001 EC-14. A lost 200 on a flaky connection otherwise tells a field
    # officer their correct code was wrong, and the code is already burned.
    otp_replay_window: timedelta = timedelta(seconds=90)
    otp_per_phone_per_15min: int = 3
    # GAP-019. The 15-minute limit bounds a burst; nothing bounded a campaign.
    # 3 codes per 15 min x 96 quarter-hours x 5 attempts = 1,440 guesses per number
    # per day against a 10**6 space: ~4% over a month, and roughly 430x the NIST
    # SP 800-63B ceiling of 100 total for a six-digit out-of-band authenticator.
    # Ten codes a day bounds it at 50. (An earlier version of this comment wrote
    # "3 codes x 5 attempts = 1,440", which is 15 - the test below has the real sum.)
    #
    # FS-001 rule 23: this cap is counted in Postgres from login_attempt rows with
    # kind='otp_issue', NOT in Redis. It is the only bound on a campaign, so a
    # restart must not clear it. The 15-minute burst limits stay in Redis, where
    # losing the counter costs nothing.
    otp_per_phone_per_day: int = 10
    # FS-001 rule 7 / EC-9: a loose backstop, not the control. Indian carriers put
    # many unrelated subscribers behind one CGNAT address and a dealership's staff
    # share one router, so a tight per-IP cap denies ordinary use.
    otp_per_ip_per_hour: int = 200

    session_retention: timedelta = timedelta(days=90)
    login_attempt_retention: timedelta = timedelta(days=90)
    idempotency_retention: timedelta = timedelta(days=30)

    whatsapp_provider: Literal["11za", "mock"] = "mock"
    whatsapp_base_url: str = "https://api.11za.in"
    whatsapp_auth_token: SecretStr | None = None
    whatsapp_origin_website: str | None = None

    sms_provider: Literal["msg91", "mock"] = "mock"
    msg91_key: SecretStr | None = None

    r2_endpoint: str | None = None
    r2_bucket: str | None = None

    sentry_dsn: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=("infra/.env", ".env"),
        env_file_encoding="utf-8",
        # No secrets_dir: Docker secrets land as env vars here, and pointing
        # pydantic-settings at a path that does not exist on Windows warns on
        # every import.
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def _through_pgbouncer(cls, v: PostgresDsn) -> PostgresDsn:
        """Refuse a direct connection outside local development.

        Developing against a direct connection hides the SET LOCAL claim leak
        until production, which is the one failure this architecture exists to
        prevent (ADR-023).
        """
        import os

        if os.getenv("POLYSIL_ALLOW_DIRECT_DB") == "1":
            return v
        # PostgresDsn is a MultiHostUrl: it permits a comma-separated host list, so
        # the port lives on each host entry rather than on the URL.
        ports = [h.get("port") for h in v.hosts()]
        wrong = [p for p in ports if p not in (6432, None)]
        if wrong:
            raise ValueError(
                f"database_url points at port {wrong[0]}, not PgBouncer's 6432. "
                "Set POLYSIL_ALLOW_DIRECT_DB=1 only for a throwaway test database."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
