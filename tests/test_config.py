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
