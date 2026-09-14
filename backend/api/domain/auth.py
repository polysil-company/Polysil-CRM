"""Authentication logic that needs no database and no I/O.

`domain/` never imports SQLAlchemy (CLAUDE.md 4.1 rule 1). Everything here is a
pure function over plain types, which is what lets the classification precedence
and the token arithmetic be tested exhaustively without a server.

Secrets arrive as parameters rather than being read from Settings, so a test can
pin them and nothing here depends on process configuration.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final

import jwt

# 256 bits, per ADR-025. token_urlsafe(32) is 32 random bytes, not 32 characters.
REFRESH_TOKEN_BYTES: Final = 32


class RefreshFailure(StrEnum):
    """The four 401 codes /auth/refresh can return (FS-001 section 4).

    The client treats all four identically - sign in again. They are distinct so
    that a support call and a log line can tell them apart.
    """

    REUSED = "refresh_reused"
    REVOKED = "session_revoked"
    EXPIRED = "refresh_expired"
    INVALID = "invalid_refresh"


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """What an access token carries, and nothing more.

    `sid` is not optional and its absence was ISS-033: `get_db` joins on it, and
    AC-AUTH-11 requires that a token issued for a logged-out session is rejected on
    next use, which means the token has to name its session.

    **There is no `role` claim, and that is a decision rather than an omission.**
    `Proposed-Backend-Architecture.md` section 6.2 lists one, and ISS-027 records
    what it costs: a role captured at sign-in is up to fifteen minutes stale while
    RLS re-derives it from `app_user.role_id` on every call, so the API would
    enforce the old role while the database had already switched. Rule 19 makes
    `require()` ask the database instead, ADR-038 forbids a second claim, and a
    claim nothing may read is a claim that will eventually be read by mistake.

    Everything the client needs for rendering - role, org unit, partner,
    permissions - comes from `GET /auth/me`, which runs authenticated and can
    therefore read those tables. The pre-auth path that mints this token cannot.
    """

    sub: str
    sid: str
    token_version: int


def new_refresh_token() -> str:
    """256 bits of server-generated randomness.

    Hashed with SHA-256 rather than Argon2 (rule 3). A work factor buys nothing
    against a value with no guessable structure, and one Argon2 verification per
    refresh would be a denial-of-service surface on the busiest authenticated path.
    """
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_otp(length: int) -> str:
    """A uniformly random numeric code, zero-padded.

    `secrets.randbelow` rather than `random`: this is a credential, and the
    difference is not visible in the output.
    """
    return str(secrets.randbelow(10**length)).zfill(length)


def constant_time_equals(a: str, b: str) -> bool:
    """For comparing a submitted OTP against the stored one."""
    return hmac.compare_digest(a, b)


def hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def otp_replay_key(server_secret: str, mobile: str, code: str) -> str:
    """FS-001 section 4: HMAC, not a bare hash.

    An unsalted hash of a known mobile plus a six-digit code is a 10**6 brute force
    for anyone who can read the cache. The HMAC key is what makes the cache useless
    to a reader who does not hold it.
    """
    return _hmac(server_secret, f"otp:{mobile}:{code}")


def refresh_replay_key(server_secret: str, presented_token_hash: str) -> str:
    """The 90-second bundle cache from section 8.2, keyed by HMAC for the same
    reason as the OTP one."""
    return _hmac(server_secret, f"refresh:{presented_token_hash}")


def _hmac(key: str, message: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def encode_access_token(
    claims: AccessClaims, secret: str, ttl: timedelta, *,
    algorithm: str = "HS256", now: datetime | None = None
) -> str:
    issued = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": claims.sub,
        "sid": claims.sid,
        "tv": claims.token_version,
        "iat": int(issued.timestamp()),
        "exp": int((issued + ttl).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(
    token: str, secret: str, *, algorithm: str = "HS256"
) -> AccessClaims | None:
    """None for anything that does not verify, rather than six exception types.

    A caller that has to distinguish an expired token from a forged one is a caller
    that will eventually tell an attacker which it was. Every failure here is the
    same 401 `unauthenticated`.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.PyJWTError:
        return None
    try:
        return AccessClaims(
            sub=str(payload["sub"]),
            sid=str(payload["sid"]),
            token_version=int(payload["tv"]),
        )
    except (KeyError, TypeError, ValueError):
        # A token that verifies but is missing sid or tv is not usable, and is
        # treated exactly like a forgery rather than crashing the dependency.
        return None


def classify_refresh_failure(
    *,
    found: bool,
    used_at: datetime | None,
    revoked_at: datetime | None,
    expires_at: datetime | None,
    now: datetime,
) -> RefreshFailure:
    """FS-001 section 4's precedence table. **The order is load-bearing.**

    These states are not mutually exclusive - a session can be used *and* revoked
    *and* expired at once. `used_at` is the only one carrying a security signal, so
    it is tested first. Tested last, a stolen token replayed after the victim
    happened to log that session out would match `revoked_at`, return
    `session_revoked`, and never revoke the family - losing exactly the alarm
    ADR-025 calls "the only cheap defence". That is B-3, and it is why this is a
    pure function with its own tests rather than an `if` chain in a service.
    """
    if not found:
        return RefreshFailure.INVALID
    if used_at is not None:
        return RefreshFailure.REUSED
    if revoked_at is not None:
        return RefreshFailure.REVOKED
    if expires_at is not None and expires_at <= now:
        return RefreshFailure.EXPIRED
    # Every reachable state is covered above. A row that is unused, unrevoked and
    # unexpired would have been claimed by step 2, so arriving here means the claim
    # failed for a reason this function cannot see - treat it as unusable rather
    # than inventing a fifth code.
    return RefreshFailure.INVALID
