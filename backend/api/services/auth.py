"""Sign-in, rotation, revocation. The transactions, not the HTTP.

**Services never commit** (CLAUDE.md 4.1 rule 3). The dependency in `api/deps.py`
owns the boundary, which is what lets a refresh roll back cleanly when Redis is
unreachable, and what makes "the same transaction" in rule 7 structural rather
than a convention.

The four pre-auth operations reach the database **only** through the eight
`SECURITY DEFINER` functions (rule 25). There is no bare table access on this
path: `app_user` holds every password hash, and a connection with no claim must
not be able to read it. `me()` is the exception and is not pre-auth - it runs on
`get_db` with a claim set and reads its own tables.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.domain import identity
from api.domain.auth import (
    AccessClaims,
    RefreshFailure,
    classify_refresh_failure,
    constant_time_equals,
    encode_access_token,
    generate_otp,
    hash_otp,
    hash_refresh_token,
    new_refresh_token,
    otp_replay_key,
    refresh_replay_key,
)
from api.errors import (
    AccountLockedError,
    ApiError,
    InvalidCredentialsError,
    InvalidOtpError,
    PasswordChangedMeanwhileError,
    RefreshFailedError,
    ValidationFailed,
)
from api.integrations import cache
from api.schemas.auth import MeResponse, ModulePermission, OrgUnitRef, PartnerRef, RoleRef

_hasher = PasswordHasher()

# Verified against when no user matches, so the unknown-email path spends the same
# work factor as the known one. Without it "one message for both" is still an
# oracle, just one measured with a stopwatch instead of read off the response.
_DUMMY_HASH: Final = _hasher.hash("a password that matches nothing")


@dataclass(frozen=True, slots=True)
class Failure:
    """A rejected sign-in, returned rather than raised. **This is not style.**

    `get_db_anon` owns the transaction, and an exception unwinding through its
    `async with session.begin()` rolls that transaction back - discarding whatever
    the rejection had already written. Two things depend on surviving a rejection:

      * the `login_attempt` row the five-failure lockout counts. Raised instead of
        returned, every failure was rolled back, the count never rose above zero,
        and **rule 5 did not exist** - six wrong passwords in a row all returned
        401 and left no trace. Caught by running it, not by reading it.
      * the family revocation reuse detection performs. Rolled back, a stolen
        refresh token revokes nothing, which inverts ADR-025.

    So every failure that has already written something returns one of these, and
    the router turns it into the same envelope the exception handler would.
    """

    error: ApiError


@dataclass(frozen=True, slots=True)
class Bundle:
    """What a successful sign-in or rotation issues.

    The refresh token is plaintext here and nowhere else durable - `session` stores
    only its SHA-256. The router turns it into an httpOnly cookie and it is never
    serialised into a response body.
    """

    access_token: str
    refresh_token: str
    expires_in: int
    session_id: str
    user_id: str

    def as_cache_entry(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_in": self.expires_in,
            "session_id": self.session_id,
            "user_id": self.user_id,
        }

    @classmethod
    def from_cache_entry(cls, entry: dict[str, Any]) -> Bundle:
        return cls(
            access_token=str(entry["access_token"]),
            refresh_token=str(entry["refresh_token"]),
            expires_in=int(entry["expires_in"]),
            session_id=str(entry["session_id"]),
            user_id=str(entry["user_id"]),
        )


def hash_password(password: str) -> str:
    """Argon2id, the one hasher. Callers run it in a worker thread: it is slow on
    purpose and inline it stalls the event loop for every other request."""
    return _hasher.hash(password)


def _verify_password(stored: str, password: str) -> bool:
    try:
        _hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError):
        return False
    return True


async def _record(db: AsyncSession, identifier: str, ip: str | None,
                  succeeded: bool, kind: str) -> None:
    await db.execute(
        text("SELECT auth_record_attempt(CAST(:i AS citext), CAST(:ip AS inet), :s, "
             "CAST(:k AS login_kind))"),
        {"i": identifier, "ip": ip, "s": succeeded, "k": kind},
    )


async def _mint(db: AsyncSession, *, user_id: str, family_id: str | None,
                user_agent: str | None, ip: str | None,
                door: str | None, token_version: int) -> Bundle | None:
    """One place issues a session, so the token and the row cannot disagree.

    `door` is `'password'` or `'otp'` for a sign-in and `None` for a rotation -
    the function emits the `activity_event` for the first two and nothing for the
    third, because a rotation is not a sign-in (rule 7, section 5).

    `token_version` is the one the credential was verified against: the lookup
    row's for a sign-in, the claim's for a rotation. The function mints only if
    the row still carries it, so a password change or a revoke that lands
    between verification and minting produces no session (FS-006 rule 6,
    ISS-077).
    """
    settings = get_settings()
    refresh = new_refresh_token()
    family = family_id or str(uuid4())

    row = (
        await db.execute(
            text("SELECT session_id, expires_at, token_version FROM auth_create_session("
                 "CAST(:u AS uuid), :h, CAST(:f AS uuid), :ttl, :ua, CAST(:ip AS inet), :d, :v)"),
            {
                "u": user_id,
                "h": hash_refresh_token(refresh),
                "f": family,
                "ttl": settings.refresh_token_ttl,
                "ua": user_agent,
                "ip": ip,
                "d": door,
                "v": token_version,
            },
        )
    ).one_or_none()

    # Zero rows means the user is gone, soft-deleted or deactivated. Every caller
    # checks first, so this is the fail-closed path for one that forgot rather
    # than an expected outcome.
    if row is None:
        return None

    access = encode_access_token(
        AccessClaims(
            sub=user_id, sid=str(row.session_id), token_version=int(row.token_version)
        ),
        settings.jwt_secret.get_secret_value(),
        settings.access_token_ttl,
        algorithm=settings.jwt_algorithm,
    )
    return Bundle(
        access_token=access,
        refresh_token=refresh,
        expires_in=int(settings.access_token_ttl.total_seconds()),
        session_id=str(row.session_id),
        user_id=user_id,
    )


# ── password ─────────────────────────────────────────────────────────────────

async def login(db: AsyncSession, *, email: str, password: str,
                user_agent: str | None, ip: str | None) -> Bundle | Failure:
    settings = get_settings()
    row = (
        await db.execute(
            text("SELECT * FROM auth_lookup_staff(CAST(:e AS citext), :n, :l)"),
            {
                "e": email,
                "n": settings.login_max_failures,
                "l": settings.login_lockout,
            },
        )
    ).one()

    # Locked is checked before the Argon2 work, deliberately. It is the one state
    # the attacker already knows about - they caused it - so there is nothing to
    # leak, and verifying anyway would turn a locked account into a CPU
    # denial-of-service lever.
    if row.locked_until is not None and row.locked_until > datetime.now(UTC):
        await _record(db, email, ip, False, "password")
        return Failure(AccountLockedError())

    # Always spend the work factor, before branching on anything else about the
    # account. `auth_lookup_staff` returns one row of nulls for an unknown address
    # precisely so this path is uniform.
    # In a worker thread. Argon2 is deliberately slow - that is the point - and run
    # inline it blocks the whole event loop for its duration, so every other
    # request on that worker stops. Measured: ten verifications delayed an
    # unrelated 5 ms timer by roughly 600 ms. Unknown addresses pay the same cost
    # by design (the dummy hash), which makes login a free way to stall the API if
    # it runs inline.
    stored = row.password_hash or _DUMMY_HASH
    verified = await asyncio.to_thread(_verify_password, stored, password)

    if row.user_id is None or not verified or not row.is_active:
        # An inactive account is invalid_credentials, not a distinct code. Saying
        # "this account is disabled" confirms the address exists.
        await _record(db, email, ip, False, "password")
        return Failure(InvalidCredentialsError())

    # Mint FIRST, then record the success. The other order writes a successful
    # login_attempt row for a sign-in that produced no session - and that is not
    # only audit noise. Rule 5's window starts at
    # greatest(last successful password attempt, now() - lockout), so a spurious
    # success RESETS THE LOCKOUT and hands a guesser their budget back.
    #
    # It is reachable: the eligibility read above and auth_create_session's own
    # check are separate statements in one READ COMMITTED transaction, so a
    # deactivation committing between them is visible to the second and not the
    # first. verify_otp already had this order; login did not.
    minted = await _mint(db, user_id=str(row.user_id), family_id=None,
                         user_agent=user_agent, ip=ip, door="password",
                         token_version=int(row.token_version))
    if minted is None:
        await _record(db, email, ip, False, "password")
        return Failure(InvalidCredentialsError())

    await _record(db, email, ip, True, "password")
    return minted


# ── OTP ──────────────────────────────────────────────────────────────────────

async def request_otp(db: AsyncSession, *, mobile: str, ip: str | None) -> None:
    """Never raises for a limit, an unknown number or an inactive account.

    The endpoint answers 202 either way (section 4). A 429 would tell an attacker
    which numbers are worth continuing with, which is the same oracle a different
    body would be.
    """
    settings = get_settings()

    # The 15-minute burst limits live in Redis, where losing the counter on a
    # restart costs nothing. The 24-hour cap does not - it is the only bound on a
    # campaign and it is counted inside the definer function, in Postgres.
    if await cache.hit_rate_limit(
        f"otp:burst:{mobile}", settings.otp_per_phone_per_15min,
        timedelta(minutes=15),
    ):
        return
    if ip and await cache.hit_rate_limit(
        f"otp:ip:{ip}", settings.otp_per_ip_per_hour,
        timedelta(hours=1),
    ):
        return

    code = generate_otp(settings.otp_length)
    issued = (
        await db.execute(
            text("SELECT auth_issue_otp_challenge(:m, CAST(:ip AS inet), :c, :cap)"),
            {"m": mobile, "ip": ip, "c": code, "cap": settings.otp_per_phone_per_day},
        )
    ).scalar_one()

    # False covers capped, unknown and inactive alike, and the caller cannot tell
    # which. Only store the challenge when a message is actually queued, or a
    # number nobody can reach would still accept a guessed code.
    if issued:
        await cache.store_otp(mobile, hash_otp(code), settings.otp_ttl)


async def verify_otp(db: AsyncSession, *, mobile: str, code: str,
                     user_agent: str | None, ip: str | None) -> Bundle | Failure:
    settings = get_settings()
    secret = settings.jwt_secret.get_secret_value()
    replay = otp_replay_key(secret, mobile, code)

    budget = settings.otp_ttl + settings.otp_replay_window

    # The budget is checked first, before the cache and before the challenge.
    #
    # It is keyed on the number rather than on the challenge, because the
    # per-challenge counter dies with the challenge. Once a code has been verified
    # and burned, a wrong guess finds no record and costs nothing, while the right
    # one is still served from the replay cache for ninety seconds - sixty wrong
    # guesses and then a correct one, reproduced, with the five-attempt limit never
    # involved. Issuing a new challenge clears it (store_otp).
    if await cache.guesses_so_far(mobile) >= settings.otp_max_attempts:
        await _record(db, mobile, ip, False, "otp")
        return Failure(InvalidOtpError())

    # Then the replay cache. A lost 200 on a flaky connection otherwise tells a
    # field officer their correct code was wrong, and the code is already burned so
    # re-entering it cannot work (EC-14). The pair costs one attempt, not two.
    cached = await cache.read_bundle(replay)
    if cached is not None:
        replayed = Bundle.from_cache_entry(cached)
        if await _session_is_real(db, replayed):
            return replayed
        # Published before COMMIT and the COMMIT did not happen. Fall through and
        # mint properly rather than hand out tokens for a session that never was.

    record = await cache.read_otp(mobile)
    if record is None:
        await _spend_guess(db, mobile, ip, budget)
        return Failure(InvalidOtpError())

    attempts = await cache.count_attempt(mobile)
    if attempts > settings.otp_max_attempts:
        await cache.burn_otp(mobile)
        await _spend_guess(db, mobile, ip, budget)
        return Failure(InvalidOtpError())

    if not _matches(record.get("hash", ""), code):
        await _spend_guess(db, mobile, ip, budget)
        return Failure(InvalidOtpError())

    # auth_lookup_by_mobile takes a per-number transaction lock, so two correct
    # submissions arriving together serialise here instead of both minting - which
    # they did, producing two sessions from one code. The loser wakes after the
    # winner commits and finds the cache written, which is the same
    # blocked-then-re-read shape section 8.2 uses for refresh.
    user = (
        await db.execute(text("SELECT * FROM auth_lookup_by_mobile(:m)"), {"m": mobile})
    ).one_or_none()

    cached = await cache.read_bundle(replay)
    if cached is not None:
        shared = Bundle.from_cache_entry(cached)
        if await _session_is_real(db, shared):
            return shared

    if user is None or not user.is_active:
        await _spend_guess(db, mobile, ip, budget)
        return Failure(InvalidOtpError())

    bundle = await _mint(db, user_id=str(user.user_id), family_id=None,
                         user_agent=user_agent, ip=ip, door="otp",
                         token_version=int(user.token_version))
    if bundle is None:
        await _record(db, mobile, ip, False, "otp")
        return Failure(InvalidOtpError())

    # The success row is what the daily cap counts from, which is what makes
    # "a successful sign-in resets it" a mechanism rather than an assertion.
    await _record(db, mobile, ip, True, "otp")
    await cache.burn_otp(mobile)
    await cache.cache_bundle(replay, bundle.as_cache_entry(), settings.otp_replay_window)
    return bundle


async def _spend_guess(db: AsyncSession, mobile: str, ip: str | None,
                       window: timedelta) -> None:
    """One rejected guess: counted in Redis for the bound, recorded in Postgres for
    the audit trail. Rule 12 keeps the Postgres row out of the password lockout."""
    await cache.count_guess(mobile, window)
    await _record(db, mobile, ip, False, "otp")


async def _session_is_real(db: AsyncSession, bundle: Bundle) -> bool:
    """Did the transaction that published this bundle actually commit?

    The cache write happens **before** COMMIT deliberately - that ordering is what
    makes an overlapping loser wake to a written entry (section 8.2). The cost is
    that a rollback afterwards leaves the entry behind, and a retry inside the
    window would otherwise be handed tokens for a session that never existed.

    One definer call settles it, and a cache hit is still the fast path.
    """
    row = (
        await db.execute(
            text("SELECT session_id FROM auth_classify_refresh(:h)"),
            {"h": hash_refresh_token(bundle.refresh_token)},
        )
    ).one_or_none()
    return row is not None


def _matches(stored_hash: str, code: str) -> bool:
    return constant_time_equals(stored_hash, hash_otp(code))


# ── refresh ──────────────────────────────────────────────────────────────────

async def refresh(db: AsyncSession, *, refresh_token: str,
                  user_agent: str | None, ip: str | None) -> Bundle | Failure:
    """Three steps, in this order, and the order is the mechanism (section 4)."""
    settings = get_settings()
    secret = settings.jwt_secret.get_secret_value()
    presented = hash_refresh_token(refresh_token)
    replay = refresh_replay_key(secret, presented)

    # 1. Replay cache. A hit inside 90 seconds returns the cached bundle unchanged
    #    and creates nothing.
    cached = await cache.read_bundle(replay)
    if cached is not None:
        replayed = Bundle.from_cache_entry(cached)
        if await _session_is_real(db, replayed):
            return replayed
        # Published before COMMIT, and the COMMIT did not happen. Fall through.

    # 2 and 3. The conditional claim and the user re-check, in one definer call.
    #    Refresh carries no Authorization header, so it never runs the claims
    #    dependency - every check that dependency performs is repeated in there, or
    #    offboarding does not reach the one endpoint that mints tokens without a
    #    token (EC-3).
    claim = (
        await db.execute(text("SELECT * FROM auth_claim_refresh(:h)"), {"h": presented})
    ).one()

    if claim.outcome == "claimed":
        bundle = await _mint(db, user_id=str(claim.user_id),
                             family_id=str(claim.family_id),
                             user_agent=user_agent, ip=ip, door=None,
                             token_version=int(claim.token_version))
        if bundle is None:
            return Failure(RefreshFailedError(code=RefreshFailure.REVOKED.value))
        # BEFORE the commit, while the claim's row lock is still held. That
        # ordering is not incidental - it is what makes an overlapping loser wake
        # to a written cache instead of classifying as reuse. Move it after the
        # commit and the two-tab race reopens (section 8.2). The dependency
        # commits after this function returns, so "before" is structural here.
        #
        # A Redis failure therefore aborts the rotation: the exception propagates,
        # the transaction rolls back, and no rotation is ever committed whose
        # bundle could not be cached. Failing open would silently reopen EC-6.
        await cache.cache_bundle(replay, bundle.as_cache_entry(), settings.refresh_grace)
        return bundle

    if claim.outcome == "session_revoked":
        # Step 3 rejected it: deactivated, soft-deleted, or token_version moved.
        # used_at rolled back inside the function, so the client's retry does not
        # classify as reuse and kill the family.
        return Failure(RefreshFailedError(code=RefreshFailure.REVOKED.value))

    return await _classify(db, presented=presented, replay=replay)


async def _classify(db: AsyncSession, *, presented: str,
                    replay: str) -> Bundle | Failure:
    """The claim matched nothing. Work out why, and revoke the family if reused."""
    row = (
        await db.execute(text("SELECT * FROM auth_classify_refresh(:h)"), {"h": presented})
    ).one_or_none()

    failure = classify_refresh_failure(
        found=row is not None,
        used_at=row.used_at if row else None,
        revoked_at=row.revoked_at if row else None,
        expires_at=row.expires_at if row else None,
        now=datetime.now(UTC),
    )

    if failure is RefreshFailure.REUSED:
        # Re-read the cache HERE, because step 1's miss may simply have been
        # early: two genuinely simultaneous presentations both read it before
        # either had written it. The loser blocks on the winner's row lock, so it
        # always wakes after the write. This re-read is what turns the two-tab
        # race from a family revocation into a shared bundle.
        cached = await cache.read_bundle(replay)
        if cached is not None:
            shared = Bundle.from_cache_entry(cached)
            if await _session_is_real(db, shared):
                return shared

        if row is not None:
            await db.execute(
                text("SELECT auth_revoke_sessions(NULL, CAST(:f AS uuid))"),
                {"f": str(row.family_id)},
            )

    return Failure(RefreshFailedError(code=failure.value))


# ── logout ───────────────────────────────────────────────────────────────────

async def logout(db: AsyncSession, *, session_id: str | None,
                 refresh_token: str | None) -> None:
    """Idempotent, and never an error.

    A signed-out client has nothing to learn from one, and the button is most
    likely to be pressed exactly when the access token has already expired.
    """
    target = session_id
    if target is None and refresh_token is not None:
        row = (
            await db.execute(
                text("SELECT session_id FROM auth_classify_refresh(:h)"),
                {"h": hash_refresh_token(refresh_token)},
            )
        ).one_or_none()
        target = str(row.session_id) if row is not None else None

    # Neither credential resolved to a session. Return without calling the
    # function: it raises on two nulls by contract, and that guard must stay
    # unreachable from here or a 204 becomes a 500 (EC-17).
    if target is None:
        return

    await db.execute(
        text("SELECT auth_revoke_sessions(CAST(:s AS uuid), NULL)"), {"s": target}
    )


# ── /auth/me ─────────────────────────────────────────────────────────────────

_ME_QUERY = text(
    """
    SELECT u.id, u.full_name, u.user_type::text AS user_type,
           r.code AS role_code, r.name AS role_name,
           o.id AS org_id, o.name AS org_name,
           u.partner_id, u.must_change_password
      FROM app_user u
      LEFT JOIN role r     ON r.id = u.role_id
      LEFT JOIN org_unit o ON o.id = u.org_unit_id
     WHERE u.id = :uid
    """
)

_PERMISSIONS_QUERY = text(
    """
    SELECT rp.module,
           array_agg(rp.action::text ORDER BY rp.action) AS actions,
           max(rp.scope::text) FILTER (WHERE rp.action = 'view') AS scope
      FROM role_permission rp
      JOIN app_user u ON u.role_id = rp.role_id
     WHERE u.id = :uid
     GROUP BY rp.module
     ORDER BY rp.module
    """
)


async def me(db: AsyncSession, *, user_id: str) -> MeResponse:
    """Everything the client needs to render, in two queries.

    The access token carries none of this on purpose - a role captured at sign-in
    goes stale while RLS re-derives it every call (ISS-027). This runs
    authenticated, so it reads the current rows.
    """
    row = (await db.execute(_ME_QUERY, {"uid": user_id})).one()
    perms = (await db.execute(_PERMISSIONS_QUERY, {"uid": user_id})).all()

    return MeResponse(
        id=str(row.id),
        full_name=row.full_name,
        user_type=row.user_type,
        role=RoleRef(code=row.role_code, name=row.role_name) if row.role_code else None,
        org_unit=OrgUnitRef(id=str(row.org_id), name=row.org_name) if row.org_id else None,
        partner=PartnerRef(id=str(row.partner_id)) if row.partner_id else None,
        must_change_password=bool(row.must_change_password),
        permissions=[
            ModulePermission(module=p.module, actions=list(p.actions), scope=p.scope)
            for p in perms
        ],
    )


# ── own password (FS-006 4) ──────────────────────────────────────────────────

async def change_own_password(db: AsyncSession, *, current_password: str,
                              new_password: str) -> None:
    """A signed-in staff member changes their own password.

    The current password is verified here against the caller's own row, which the
    self policy admits. The write is `auth_set_own_password()`: a compare-and-set
    on the hash just verified, so an administrator's reset that lands in between
    wins and the caller learns it as a 409 (rule 6). The definer revokes every
    session, this one included, after the set; the client signs in again.
    """
    row = (await db.execute(text(
        "SELECT password_hash, user_type::text AS user_type FROM app_user "
        "WHERE id = (SELECT app_current_user_id())"))).one_or_none()
    if row is None or row.user_type != "staff" or row.password_hash is None:
        raise ValidationFailed(
            fields={"current_password": "this account signs in by OTP and has no password"})
    if not await asyncio.to_thread(_verify_password, row.password_hash, current_password):
        raise ValidationFailed(fields={"current_password": "wrong"})
    problem = identity.password_problem(new_password)
    if problem:
        raise ValidationFailed(fields={"new_password": problem})
    new_hash = await asyncio.to_thread(hash_password, new_password)
    changed = (await db.execute(
        text("SELECT auth_set_own_password(:expected, :new)"),
        {"expected": row.password_hash, "new": new_hash})).scalar_one()
    if not changed:
        raise PasswordChangedMeanwhileError()
