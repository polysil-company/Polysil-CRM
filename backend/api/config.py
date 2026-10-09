"""Settings, env-driven. No config files in the repo.

Everything reaches Postgres through PgBouncer on 127.0.0.1:6432 (ADR-021, ADR-023).
Whether that is a tunnelled remote instance or a local container is a compose
profile choice, and nothing here knows the difference.
"""

from __future__ import annotations

import re
from datetime import timedelta
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import PostgresDsn, RedisDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Any port on the developer's own machine. One definition: the CORS middleware
# matches origins with it, and the refresh endpoints decide with it who may
# spend a cookie. Two copies would drift, and the drift shows up as an attack.
LOCALHOST_ORIGIN = re.compile(r"http://(localhost|127\.0\.0\.1)(:\d+)?")


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
    # FS-003a: the public form's principal, migration 015; uuid5(DNS, "polysil.intake")
    intake_user_id: str = "3f962ae5-f0d3-5583-91b5-5cea037139fc"
    public_lead_code_ttl_seconds: int = 600
    # rule 5: the sign-in value, so one carrier address at a fair is not a lockout
    public_lead_codes_per_ip_per_hour: int = 200
    # rule 9: a ceiling on paid messages from the public form, whatever the source
    public_lead_codes_per_hour: int = 300
    public_lead_code_retention: timedelta = timedelta(days=30)

    # FS-003 rule 4 (GAP-046, ISS-067). owner_org_unit_id is never user-supplied: it
    # is the sales-line unit whose territory covers the lead's territory. When no
    # such unit exists this named anchor catches the lead, so a marketing-entered or
    # partner-entered lead is never invisible to admins. Migration 006 seeds the row
    # under this stable id (Polysil HQ, role_level 5); a database without it would
    # fail the insert's foreign key, which the bootstrap test guards against.
    # uuid5(DNS, "polysil.hq")
    root_org_unit_id: str | None = "73f0fdc5-8adb-50e6-b1b9-04005fe9e2ea"

    # PROJECT-OVERVIEW section 5: Caddy terminates TLS and calls the API over
    # loopback on the same box. So request.client.host is Caddy, not the caller,
    # and every request would land in one rate-limit bucket - 200 OTP requests an
    # hour across all 700 users, after which everyone's code is silently dropped
    # (the endpoint still answers 202, so nobody can tell). login_attempt.ip would
    # be useless for the one investigation it exists for, too.
    #
    # So X-Forwarded-For is trusted, but only from a peer we have named. Set to 0
    # to trust nothing, if the API is ever exposed directly.
    trusted_proxy_hops: int = 1

    # Which peers may set that header. Loopback alone is right when the proxy runs
    # on the host, and wrong the moment it runs in a container: a reverse proxy on
    # another Docker network arrives as 172.x, the header is then ignored, and
    # **every login and every one-time code collapses into one rate-limit bucket**
    # under the proxy's address. The endpoint still answers 202 once that trips, so
    # nobody can tell from the outside that codes have stopped (ISS-084).
    #
    # Entries are addresses or CIDR blocks. Widening this is a real decision: any
    # peer named here can choose its own rate-limit bucket, so it must only ever
    # list proxies we run.
    # `NoDecode` so the env source hands the raw string to the validator below
    # rather than insisting it be JSON.
    trusted_proxy_peers: Annotated[tuple[str, ...], NoDecode] = ("127.0.0.1", "::1")

    # ── the browser contract ─────────────────────────────────────────────────
    #
    # Two settings that have to agree, or sign-in works and staying signed in does
    # not. A frontend on another origin needs both: the CORS allowance to make the
    # call at all, and a refresh cookie the browser will send back on it.
    #
    # `SameSite=Lax` is right when the frontend is same-origin or proxied through
    # its own dev server, and it silently breaks a cross-site refresh: a Lax cookie
    # is not attached to a background request, so login succeeds and the session
    # dies at the first refresh. `None` is the cross-site answer and requires
    # `Secure`, which means HTTPS, which is why this is not the default.
    cors_allow_origins: Annotated[tuple[str, ...], NoDecode] = ()
    # Any port on the developer's own machine, so nobody has to tell us which one.
    # Credentials require echoing a specific origin rather than `*`, and a regex
    # does exactly that for the origin it matched.
    cors_allow_localhost: bool = True
    refresh_cookie_samesite: Literal["lax", "none"] = "lax"

    def origin_allowed(self, origin: str) -> bool:
        """Whether a browser at this origin may use a cookie credential here.

        One answer for two questions that have to agree: which origins CORS
        echoes back, and which origins may spend the refresh cookie. Read from
        two places and they drift, and the drift is only visible as an attack.
        """
        return origin in self.cors_allow_origins or (
            self.cors_allow_localhost and LOCALHOST_ORIGIN.fullmatch(origin) is not None)

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
    # FS-007 section 5.1. The template names on the client's account, and the
    # language until question 3.2 is answered (GAP-022).
    whatsapp_template_otp: str = "polysil_auth_otp"
    whatsapp_template_lead_ack: str = "polysil_lead_ack"
    # FS-005: the quotation link. Optional, because a bare str would refuse to
    # start every process until the client's BSP approves the template (GAP-110);
    # the checker reports an unset name on its own line.
    whatsapp_template_quotation_share: str | None = None
    whatsapp_template_language: str = "en"
    # A total deadline per send: httpx's timeout bounds each socket operation, not
    # the request. Re-sized from the smoke's slowest sends.
    whatsapp_send_timeout: float = 10.0
    # FS-038: the path secret on the webhook URLs 11za calls. 11za signs nothing,
    # so this is the credential; unset, the routes answer 404 (GAP-355).
    whatsapp_webhook_secret: SecretStr | None = None
    # FS-038 rule 6: raw calls hold farmers' numbers and words (GAP-356)
    whatsapp_webhook_retention: timedelta = timedelta(days=30)
    # FS-007 rule 7: how long one drain keeps claiming rows. Under the ten-second
    # tick, eight seconds lets at most two drains overlap.
    outbox_drain_budget: float = 8.0
    # FS-007 rule 12: rows that are not pending are purged after this.
    outbox_retention: timedelta = timedelta(days=90)

    sms_provider: Literal["msg91", "mock"] = "mock"
    msg91_key: SecretStr | None = None

    r2_endpoint: str | None = None
    r2_bucket: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: SecretStr | None = None
    # FS-005 5.3. The local adapter is for the dev box only (ADR-026 rejects local
    # disk outright); outside local R2 is required, validated below.
    storage_dir: str = "infra/storage"
    # The frontend origin the share link points at, no trailing slash. A link is
    # the origin plus 46 characters and the adapter's value bound is 100, so the
    # origin is bounded at 54 (edge case 17).
    public_web_url: str = "http://localhost:3000"
    # weasyprint renders a PDF; html stores the rendered HTML as the document and
    # is allowed on the dev box only, where WeasyPrint's native libraries are not.
    pdf_renderer: Literal["weasyprint", "html"] = "weasyprint"
    # The render lease (FS-005 5.2): longer than any render, shorter than a
    # user's patience.
    pdf_lease_minutes: int = 5
    # seconds one render tick may keep claiming; under the 5 s cadence, so ticks do
    # not pile up and hold the worker's job slots the outbox drain needs
    pdf_render_budget: float = 4.0

    sentry_dsn: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=("infra/.env", ".env"),
        env_file_encoding="utf-8",
        # No secrets_dir: Docker secrets land as env vars here, and pointing
        # pydantic-settings at a path that does not exist on Windows warns on
        # every import.
        extra="ignore",
        # A refused configuration (FS-007 rule 11) is printed by whoever started
        # the process; the raw input would put the token in that traceback
        # (cross-vendor review of the code, P2).
        hide_input_in_errors=True,
    )

    @field_validator("trusted_proxy_peers", "cors_allow_origins", mode="before")
    @classmethod
    def _accept_a_comma_separated_list(cls, v: object) -> object:
        """A list in an env file is JSON to pydantic and commas to a person.

        Without this, `TRUSTED_PROXY_PEERS=127.0.0.1,::1` fails at startup with a
        JSON parse error that names neither the format it wanted nor the one it
        got. Commas are what anyone editing `.env.staging` will reach for, so both
        are accepted and the failure is reserved for a value that is actually wrong.
        """
        if not isinstance(v, str):
            return v
        text = v.strip()
        if text.startswith("["):
            import json

            return tuple(json.loads(text))
        return tuple(part.strip() for part in text.split(",") if part.strip())

    @field_validator("trusted_proxy_peers")
    @classmethod
    def _peers_are_addresses(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        """Refuse a peer list that is not addresses, rather than silently trusting
        nobody. A typo here does not fail loudly on its own: the header is simply
        never believed, and the symptom is a rate-limit bucket everyone shares."""
        import ipaddress

        for entry in v:
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError as exc:
                raise ValueError(
                    f"trusted_proxy_peers entry {entry!r} is not an address or CIDR block"
                ) from exc
        return v

    @model_validator(mode="after")
    def _cross_site_needs_a_secure_cookie(self) -> Settings:
        """`SameSite=None` without `Secure` is refused by every current browser, so
        the session would die at the first refresh with nothing in the log. Secure
        follows the environment, so this is really a check that cross-site is not
        being asked for over plain HTTP."""
        if self.refresh_cookie_samesite == "none" and self.environment == "local":
            raise ValueError(
                "refresh_cookie_samesite='none' needs Secure, which needs HTTPS. "
                "Proxy the API through the frontend's dev server instead, or run "
                "against the staging deployment.")
        return self

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
        # 6433 is pgbouncer-b, the second PgBouncer a parallel worktree uses for its
        # own copy of the database (infra/docker-compose.yml). Still pooled.
        wrong = [p for p in ports if p not in (6432, 6433, None)]
        if wrong:
            raise ValueError(
                f"database_url points at port {wrong[0]}, not PgBouncer's 6432. "
                "Set POLYSIL_ALLOW_DIRECT_DB=1 only for a throwaway test database."
            )
        return v

    @model_validator(mode="after")
    def _messaging_is_configured(self) -> Settings:
        """FS-007 rule 11. A misconfigured provider must be loud: the symptom of a
        mock in production is "no farmer ever hears from us" and no error, and a
        provider without its token fails every send in the same silence."""
        if self.whatsapp_provider == "11za" and self.whatsapp_auth_token is None:
            raise ValueError("whatsapp_provider is 11za but whatsapp_auth_token is unset")
        if self.environment == "production" and self.whatsapp_provider == "mock":
            raise ValueError("whatsapp_provider is mock in production; no message would leave")
        secret = self.whatsapp_webhook_secret
        if secret is not None and len(secret.get_secret_value()) < 32:
            raise ValueError("whatsapp_webhook_secret must be at least 32 characters")
        return self

    @field_validator("whatsapp_template_quotation_share", "r2_endpoint", "r2_bucket",
                     "r2_access_key_id", "r2_secret_access_key", "whatsapp_webhook_secret",
                     mode="before")
    @classmethod
    def _empty_is_unset(cls, v: object) -> object:
        """The compose files pass `${VAR:-}`, and an empty string is not a value:
        an empty template name would read as configured and fail every send."""
        return None if isinstance(v, str) and not v.strip() else v

    @model_validator(mode="after")
    def _quotations_are_configured(self) -> Settings:
        """FS-005 5.3. Three things that are fine on the dev box and wrong anywhere
        else, refused at startup: HTML in place of a PDF, a share link the
        WhatsApp adapter would truncate, and a share link that points at
        localhost, which is what an unset origin would send to a farmer's phone.
        A missing R2 bucket is not refused here: it takes the quotation PDF down,
        not the CRM (edge case 20), and `storage_configured` says so at startup
        and on every render."""
        origin = self.public_web_url.strip().rstrip("/")
        if not origin and self.environment == "local":
            origin = "http://localhost:3000"
        self.public_web_url = origin
        if self.environment != "local":
            parts = urlsplit(origin) if origin else None
            host = parts.hostname if parts else None
            if (parts is None or not host or host in _LOCAL_HOSTS
                    or parts.scheme not in ("http", "https")):
                raise ValueError("public_web_url must be the frontend's real origin outside "
                                 "local: the share link and the WhatsApp message carry it")
        if len(self.public_web_url) > 54:
            raise ValueError("public_web_url is longer than 54 characters; the share link "
                             "would exceed the WhatsApp value bound of 100")
        if self.environment != "local" and self.pdf_renderer != "weasyprint":
            raise ValueError("pdf_renderer must be weasyprint outside local")
        return self

    @property
    def storage_configured(self) -> bool:
        """R2 in full, or the local directory on the dev box. ADR-026 rejects local
        disk anywhere else, so outside local an unset R2 means no storage at all."""
        r2 = bool(self.r2_endpoint and self.r2_bucket and self.r2_access_key_id
                  and self.r2_secret_access_key)
        return r2 or self.environment == "local"


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
