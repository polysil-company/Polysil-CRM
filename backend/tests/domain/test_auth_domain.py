"""The pure logic. No database, no Redis, no app.

This layer exists so the classification precedence and the token handling can be
tested exhaustively in milliseconds. `domain/` never imports SQLAlchemy, which is
what makes that true (CLAUDE.md 4.1 rule 1).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api.domain.auth import (
    AccessClaims,
    RefreshFailure,
    classify_refresh_failure,
    constant_time_equals,
    decode_access_token,
    encode_access_token,
    generate_otp,
    hash_otp,
    hash_refresh_token,
    new_refresh_token,
    otp_replay_key,
    refresh_replay_key,
)

SECRET = "a" * 64
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


# ── tokens ───────────────────────────────────────────────────────────────────

def test_a_round_trip_preserves_the_claims() -> None:
    claims = AccessClaims(sub="u-1", sid="s-1", token_version=3)
    got = decode_access_token(encode_access_token(claims, SECRET, timedelta(minutes=15)), SECRET)
    assert got == claims


def test_a_token_signed_with_another_secret_is_not_accepted() -> None:
    token = encode_access_token(
        AccessClaims(sub="u", sid="s", token_version=0), SECRET, timedelta(minutes=15))
    assert decode_access_token(token, "b" * 64) is None


def test_an_expired_token_is_not_accepted() -> None:
    token = encode_access_token(
        AccessClaims(sub="u", sid="s", token_version=0), SECRET,
        timedelta(minutes=-1), now=NOW)
    assert decode_access_token(token, SECRET) is None


@pytest.mark.parametrize("junk", ["", "not-a-token", "a.b.c", "Bearer x"])
def test_junk_decodes_to_none_rather_than_raising(junk: str) -> None:
    """Every failure is the same 401. A caller that has to distinguish an expired
    token from a forged one will eventually tell an attacker which it was."""
    assert decode_access_token(junk, SECRET) is None


def test_a_token_missing_sid_is_treated_as_a_forgery() -> None:
    """`sid` is what AC-AUTH-11 needs: an access token issued for a session that
    has since been logged out must fail on next use, which requires the token to
    name its session. A token without one is unusable, and unusable is a 401 -
    not a KeyError inside the dependency."""
    import jwt

    token = jwt.encode({"sub": "u", "tv": 0, "exp": 9999999999}, SECRET, algorithm="HS256")
    assert decode_access_token(token, SECRET) is None


def test_the_token_carries_no_role_claim() -> None:
    """ISS-027. A role captured at sign-in is stale for up to fifteen minutes while
    RLS re-derives it every call, so `require()` asks the database and the token
    carries nothing anyone could authorize against by mistake."""
    import jwt

    token = encode_access_token(
        AccessClaims(sub="u", sid="s", token_version=0), SECRET, timedelta(minutes=15))
    payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert set(payload) == {"sub", "sid", "tv", "iat", "exp"}


# ── refresh tokens and OTPs ──────────────────────────────────────────────────

def test_refresh_tokens_are_unguessable_and_unique() -> None:
    tokens = {new_refresh_token() for _ in range(500)}
    assert len(tokens) == 500
    # 32 random bytes, base64url encoded. Not 32 characters.
    assert all(len(t) >= 43 for t in tokens)


def test_hashing_a_refresh_token_is_stable_and_one_way() -> None:
    token = new_refresh_token()
    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert token not in hash_refresh_token(token)


@pytest.mark.parametrize("length", [4, 6, 8])
def test_otp_is_the_requested_length_and_zero_padded(length: int) -> None:
    """`str(randbelow(10**6))` is five characters one time in ten. A code the user
    reads as five digits will not match a six-digit field."""
    codes = [generate_otp(length) for _ in range(300)]
    assert all(len(c) == length and c.isdigit() for c in codes)


def test_otp_covers_its_range() -> None:
    """A generator that never produces a leading zero has a tenth of the space it
    claims, and the daily-cap arithmetic in FS-001 assumes the whole of it."""
    assert any(c.startswith("0") for c in (generate_otp(6) for _ in range(400)))


def test_otp_comparison_is_constant_time() -> None:
    assert constant_time_equals(hash_otp("482913"), hash_otp("482913"))
    assert not constant_time_equals(hash_otp("482913"), hash_otp("482914"))


def test_replay_keys_are_keyed_not_merely_hashed() -> None:
    """FS-001 section 4: an unsalted hash of a known mobile plus a six-digit code
    is a 10**6 brute force for anyone who can read the cache."""
    a = otp_replay_key(SECRET, "919876543210", "482913")
    b = otp_replay_key("b" * 64, "919876543210", "482913")
    assert a != b, "the key made no difference, so this is a bare hash"
    assert a == otp_replay_key(SECRET, "919876543210", "482913")


def test_the_two_replay_namespaces_do_not_collide() -> None:
    """One Redis, two caches. A shared key would let an OTP bundle be returned to a
    refresh call."""
    assert otp_replay_key(SECRET, "x", "y") != refresh_replay_key(SECRET, "xy")


# ── classification precedence ────────────────────────────────────────────────

def _classify(**kw: object) -> RefreshFailure:
    base: dict = {"found": True, "used_at": None, "revoked_at": None,
                  "expires_at": NOW + timedelta(days=1), "now": NOW}
    return classify_refresh_failure(**{**base, **kw})


def test_an_unknown_token_is_invalid() -> None:
    assert _classify(found=False) is RefreshFailure.INVALID


def test_a_used_token_is_reuse() -> None:
    assert _classify(used_at=NOW) is RefreshFailure.REUSED


def test_a_revoked_token_is_revoked() -> None:
    assert _classify(revoked_at=NOW) is RefreshFailure.REVOKED


def test_an_expired_token_is_expired() -> None:
    assert _classify(expires_at=NOW - timedelta(seconds=1)) is RefreshFailure.EXPIRED


def test_expiry_is_inclusive_at_the_boundary() -> None:
    assert _classify(expires_at=NOW) is RefreshFailure.EXPIRED


def test_used_beats_revoked() -> None:
    """B-3, and the reason this is a function rather than an if-chain in a service.

    These states are not mutually exclusive. `used_at` is the only one carrying a
    security signal, so it is tested first - tested last, a stolen token replayed
    after the victim happened to log that session out would classify as
    `session_revoked` and never revoke the family, losing exactly the alarm
    ADR-025 calls the only cheap defence against a stolen token.
    """
    assert _classify(used_at=NOW, revoked_at=NOW) is RefreshFailure.REUSED


def test_used_beats_expired_and_revoked_together() -> None:
    assert _classify(
        used_at=NOW, revoked_at=NOW, expires_at=NOW - timedelta(days=1)
    ) is RefreshFailure.REUSED


def test_revoked_beats_expired() -> None:
    assert _classify(
        revoked_at=NOW, expires_at=NOW - timedelta(days=1)
    ) is RefreshFailure.REVOKED
