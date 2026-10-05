"""Settings behaviour that is load-bearing rather than declarative."""

from __future__ import annotations

import pytest

from api.config import Settings

BASE = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@127.0.0.1:6432/appdb",
    "JWT_SECRET": "x" * 32,
}


def _settings(monkeypatch: pytest.MonkeyPatch, **over: str) -> Settings:
    monkeypatch.delenv("POLYSIL_ALLOW_DIRECT_DB", raising=False)
    # And the two role variables, for the same reason `_env_file=None` is below:
    # these tests describe Settings' own defaults. The env file was covered and
    # the process environment was not, so CI - which exports DB_ANON_ROLE so the
    # pre-auth grant test runs rather than skips - failed the defaults test.
    for name in ("DB_ANON_ROLE", "DB_APP_ROLE"):
        monkeypatch.delenv(name, raising=False)
    # FS-005: the origin is required outside local; a test that builds staging
    # or production settings for another reason gets a real one
    if over.get("ENVIRONMENT", "local") != "local":
        over.setdefault("PUBLIC_WEB_URL", "https://crm.polysil.in")
    for k, v in {**BASE, **over}.items():
        monkeypatch.setenv(k, v)
    # _env_file=None: these tests describe Settings' own defaults, not whatever the
    # developer's infra/.env says today. Without it, setting DB_ANON_ROLE in .env
    # during development made the default-is-unset test fail for an unrelated reason.
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_pgbouncer_url_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch).environment == "local"


def test_direct_connection_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-023. A direct connection hides the SET LOCAL claim leak until production,
    which is the one failure this architecture exists to prevent."""
    with pytest.raises(ValueError, match="6432"):
        _settings(monkeypatch, DATABASE_URL="postgresql+asyncpg://u:p@127.0.0.1:5432/appdb")


def test_second_pgbouncer_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """pgbouncer-b on 6433 serves a parallel worktree's database copy."""
    s = _settings(monkeypatch, DATABASE_URL="postgresql+asyncpg://u:p@127.0.0.1:6433/appdb_b")
    assert s.environment == "local"


def test_direct_connection_escape_hatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Throwaway test databases need it; nothing else may use it."""
    monkeypatch.setenv("POLYSIL_ALLOW_DIRECT_DB", "1")
    for k, v in {**BASE, "DATABASE_URL": "postgresql+asyncpg://u:p@127.0.0.1:5432/x"}.items():
        monkeypatch.setenv(k, v)
    assert Settings().environment == "local"  # type: ignore[call-arg]


def test_otp_campaign_arithmetic_matches_fs001_rule_12(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 12 excludes OTP failures from the lockout, so the daily code cap is the
    only thing bounding a campaign rather than a burst.

    The 15-minute rate alone allows 1,440 guesses per number per day, roughly 430x
    the NIST SP 800-63B ceiling of 100 for a six-digit out-of-band authenticator.
    The daily cap is what brings it back into range.
    """
    s = _settings(monkeypatch)
    space = 10**s.otp_length
    assert space == 1_000_000

    unbounded_per_day = s.otp_per_phone_per_15min * 4 * 24 * s.otp_max_attempts
    assert unbounded_per_day == 1_440

    capped_per_day = s.otp_per_phone_per_day * s.otp_max_attempts
    assert capped_per_day == 50
    # Under 0.2% over a 30-day campaign against one number.
    assert capped_per_day * 30 / space < 0.002


def test_refresh_grace_outlasts_a_mobile_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """FS-001 section 8.2. The window exists to absorb a retry after a lost response
    on a slow connection, so it has to outlast the timeout that triggers the retry.

    A 10-second window - the rev 3 value - expires before a mobile client with a
    default 10-30s timeout has even given up on the first call, which revokes the
    whole session family for a dropped packet.
    """
    s = _settings(monkeypatch)
    worst_case_client_timeout = 30
    assert s.refresh_grace.total_seconds() > worst_case_client_timeout
    # It absorbs the identical failure as the OTP cache, so it matches it.
    assert s.refresh_grace == s.otp_replay_window


def test_db_anon_role_defaults_to_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """FS-001 section 5.1. The default is unset, not a role name.

    A box where the role does not exist must still start: `SET LOCAL ROLE` on a
    missing role is a 500 on every sign-in. The development cluster has the role
    on the dev cluster and infra/.env sets it, which is why this test isolates
    itself from that file. Unset is a weakness, not a neutral default, so /health
    reports it.
    """
    assert _settings(monkeypatch).db_anon_role is None


def test_db_anon_role_is_honoured_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch, DB_ANON_ROLE="app_anon").db_anon_role == "app_anon"


def test_the_mock_provider_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch).whatsapp_provider == "mock"


def test_the_real_provider_needs_its_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """FS-007 rule 11: a provider without its token fails every send in silence."""
    with pytest.raises(ValueError, match="token"):
        _settings(monkeypatch, WHATSAPP_PROVIDER="11za")
    assert _settings(monkeypatch, WHATSAPP_PROVIDER="11za",
                     WHATSAPP_AUTH_TOKEN="x").whatsapp_provider == "11za"


def test_production_refuses_the_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """FS-007 rule 11: the symptom of a mock in production is "no farmer ever
    hears from us" and no error."""
    with pytest.raises(ValueError, match="mock"):
        _settings(monkeypatch, ENVIRONMENT="production")
    assert _settings(monkeypatch, ENVIRONMENT="production", WHATSAPP_PROVIDER="11za",
                     WHATSAPP_AUTH_TOKEN="x").environment == "production"


# ── FS-005: the quotation settings ───────────────────────────────────────────

def test_a_long_public_origin_is_refused_because_the_link_would_be_truncated(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge case 17: a share link is the origin plus 46 characters, and the WhatsApp
    adapter silently cuts a value at 100."""
    ok = _settings(monkeypatch, PUBLIC_WEB_URL="https://crm.polysil.in/")
    assert ok.public_web_url == "https://crm.polysil.in", "no trailing slash"
    with pytest.raises(ValueError, match="54 characters"):
        _settings(monkeypatch,
                  PUBLIC_WEB_URL="https://polysil-irrigation-crm.staging.example.co.in/portal")


def test_the_html_renderer_is_a_dev_box_convenience_only(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch, PDF_RENDERER="html").pdf_renderer == "html"
    with pytest.raises(ValueError, match="weasyprint outside local"):
        _settings(monkeypatch, ENVIRONMENT="staging", PDF_RENDERER="html",
                  WHATSAPP_PROVIDER="11za", WHATSAPP_AUTH_TOKEN="x")


def test_storage_is_the_directory_locally_and_r2_or_nothing_elsewhere(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-026 rejects local disk outside local. A missing bucket does not refuse
    startup (edge case 20); it makes storage_configured false, and every render
    fails with the reason."""
    assert _settings(monkeypatch).storage_configured is True
    staging = _settings(monkeypatch, ENVIRONMENT="staging", WHATSAPP_PROVIDER="11za",
                        WHATSAPP_AUTH_TOKEN="x")
    assert staging.storage_configured is False
    with_r2 = _settings(monkeypatch, ENVIRONMENT="staging", WHATSAPP_PROVIDER="11za",
                        WHATSAPP_AUTH_TOKEN="x", R2_ENDPOINT="https://x.r2.cloudflarestorage.com",
                        R2_BUCKET="polysil", R2_ACCESS_KEY_ID="k", R2_SECRET_ACCESS_KEY="s")
    assert with_r2.storage_configured is True


def test_the_share_template_is_optional_until_the_bsp_approves_it(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """GAP-110: a bare str would refuse to start every process."""
    from api.integrations.whatsapp.check import unconfigured_templates

    assert _settings(monkeypatch).whatsapp_template_quotation_share is None
    assert unconfigured_templates(_settings(monkeypatch)) == ["quotation_share"]
    named = _settings(monkeypatch, WHATSAPP_TEMPLATE_QUOTATION_SHARE="polysil_quotation")
    assert unconfigured_templates(named) == []


def test_the_public_origin_is_required_outside_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Code review F-4, FS-005 5.3: an unset origin is localhost, and a share link
    to localhost would reach a farmer's phone once the template is approved.
    Locally the default stands; anywhere else the value must be a real origin."""
    assert _settings(monkeypatch, PUBLIC_WEB_URL="").public_web_url == "http://localhost:3000"
    for origin in ("", "http://localhost:3000", "http://127.0.0.1:3000"):
        with pytest.raises(ValueError, match="real origin"):
            _settings(monkeypatch, ENVIRONMENT="staging", WHATSAPP_PROVIDER="11za",
                      WHATSAPP_AUTH_TOKEN="x", PUBLIC_WEB_URL=origin)
    ok = _settings(monkeypatch, ENVIRONMENT="staging", WHATSAPP_PROVIDER="11za",
                   WHATSAPP_AUTH_TOKEN="x", PUBLIC_WEB_URL="https://crm.polysil.in/")
    assert ok.public_web_url == "https://crm.polysil.in"
