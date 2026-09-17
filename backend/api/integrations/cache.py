"""Redis: the OTP challenge, the burst limits, and the two replay caches.

**What lives here and what lives in Postgres is a security decision, not a
performance one** (FS-001 rule 7, section 5.2):

  * the **15-minute burst limits** are here, because losing the counter on a
    restart costs nothing;
  * the **24-hour per-phone cap** is *not* - it is the only bound on a brute-force
    campaign, so a restart must not clear it. It lives in `login_attempt` and is
    counted inside `auth_issue_otp_challenge`.

The two replay caches hold issued token bundles for ninety seconds. They are here
rather than in a table because a bundle contains a refresh token in plaintext,
which `session` stores only as a hash - a short-lived key in an ephemeral store is
a better home for that than a durable table that ends up in every backup.
"""

from __future__ import annotations

import json
from datetime import timedelta
from functools import lru_cache
from typing import Any

import structlog
from redis.asyncio import Redis

from api.config import get_settings

log = structlog.get_logger()


@lru_cache
def get_redis() -> Redis:
    settings = get_settings()
    # FS-007 section 5.1: a stalled Redis must fail open in the worker, and a
    # client with no socket timeouts waits forever. One second is generous on a
    # loopback connection.
    return Redis.from_url(str(settings.redis_url), decode_responses=True,
                          socket_connect_timeout=1.0, socket_timeout=1.0)


def _otp_key(mobile: str) -> str:
    return f"otp:{mobile}"


async def store_otp(mobile: str, code_hash: str, ttl: timedelta) -> None:
    """One challenge per number. A second request replaces the first rather than
    adding to it, so the attempt counter cannot be reset by asking again."""
    r = get_redis()
    key = _otp_key(mobile)
    await clear_guesses(mobile)
    async with r.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        pipe.hset(key, mapping={"hash": code_hash, "attempts": 0})
        pipe.expire(key, int(ttl.total_seconds()))
        await pipe.execute()


async def read_otp(mobile: str) -> dict[str, str] | None:
    got: dict[str, str] = await get_redis().hgetall(_otp_key(mobile))
    return got or None


async def count_attempt(mobile: str) -> int:
    """Returns the attempt count *after* this one.

    HINCRBY rather than read-modify-write: five simultaneous guesses must consume
    five attempts, not one.
    """
    return int(await get_redis().hincrby(_otp_key(mobile), "attempts", 1))


async def burn_otp(mobile: str) -> None:
    await get_redis().delete(_otp_key(mobile))


def _guess_key(mobile: str) -> str:
    return f"otp:guesses:{mobile}"


async def count_guess(mobile: str, window: timedelta) -> int:
    """Failed verifies per number, counted **independently of the challenge**.

    The per-challenge counter lives inside the challenge and dies with it, which
    leaves a hole: once a code has been verified and burned, a wrong guess finds no
    record at all and costs nothing, while the right one is still served from the
    replay cache for ninety seconds. Reproduced - sixty wrong guesses, none
    counted, then the correct code returned a session. That is unlimited
    brute-forcing of a live code inside the window, and the five-attempt limit
    never sees it.

    This counter is the bound. It survives the burn because it is keyed on the
    number rather than on the challenge.
    """
    r = get_redis()
    key = _guess_key(mobile)
    async with r.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, int(window.total_seconds()), nx=True)
        count, _ = await pipe.execute()
    return int(count)


async def guesses_so_far(mobile: str) -> int:
    raw = await get_redis().get(_guess_key(mobile))
    return int(raw) if raw else 0


async def clear_guesses(mobile: str) -> None:
    """A newly issued challenge starts a fresh budget, or five mistypes would lock
    a number out of every subsequent code too."""
    await get_redis().delete(_guess_key(mobile))


async def hit_rate_limit(bucket: str, limit: int, window: timedelta) -> bool:
    """True when this call is over the limit.

    A fixed window, not a sliding one. It is deliberately the loose choice: these
    bound a burst, and the control that actually bounds a campaign is the daily cap
    in Postgres. A sliding window here would cost more and protect nothing extra.
    """
    r = get_redis()
    async with r.pipeline(transaction=True) as pipe:
        pipe.incr(bucket)
        pipe.expire(bucket, int(window.total_seconds()), nx=True)
        count, _ = await pipe.execute()
    return int(count) > limit


async def cache_bundle(key: str, bundle: dict[str, Any], ttl: timedelta) -> None:
    """Used by both replay paths.

    **On the refresh path the caller must write this before `COMMIT`, while the
    claim's row lock is still held.** That ordering is the mechanism, not an
    implementation detail: a losing concurrent caller blocks on the row lock and
    therefore always wakes to a written cache. Move it after the commit and the
    two-tab race reopens (FS-001 section 8.2).
    """
    await get_redis().setex(key, int(ttl.total_seconds()), json.dumps(bundle))


async def read_bundle(key: str) -> dict[str, Any] | None:
    raw: str | None = await get_redis().get(key)
    if raw is None:
        return None
    try:
        loaded: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return loaded


# ── the outbox breaker (FS-007 rule 8) ───────────────────────────────────────
#
# Shared across workers and time-based, so an outage costs no message an
# attempt and the drain stops hammering a dead provider. Every failure here is
# the same decision: fail open. The OTP challenge itself lives in Redis, so
# sign-in is already down when Redis is; the acknowledgement path has no reason
# to stop.

BREAKER_COUNT = "wa:breaker:count"
BREAKER_OPEN = "wa:breaker:open"
BREAKER_WINDOW = timedelta(seconds=60)
BREAKER_THRESHOLD = 3


async def breaker_is_open() -> bool:
    try:
        return bool(await get_redis().exists(BREAKER_OPEN))
    except Exception as exc:
        log.warning("outbox.breaker_unavailable", kind=type(exc).__name__)
        return False


async def breaker_note_transient() -> bool:
    """One transient failure. Opens the breaker at the third inside one fixed
    window (hit_rate_limit is a fixed window) and says so. Called after the row's
    own UPDATE has committed, never before."""
    try:
        if await hit_rate_limit(BREAKER_COUNT, BREAKER_THRESHOLD - 1, BREAKER_WINDOW):
            await get_redis().setex(BREAKER_OPEN, int(BREAKER_WINDOW.total_seconds()), "1")
            return True
    except Exception as exc:
        log.warning("outbox.breaker_unavailable", kind=type(exc).__name__)
    return False


async def breaker_reset() -> None:
    try:
        await get_redis().delete(BREAKER_COUNT, BREAKER_OPEN)
    except Exception as exc:
        log.warning("outbox.breaker_unavailable", kind=type(exc).__name__)
