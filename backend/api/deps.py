"""The two dependencies that own a transaction, and the gates built on them.

**This is the most important file in the backend** (`Proposed-Backend-Architecture.md`
section 5.2). One line in it - `set_config(..., true)` - is the difference between
correct authorization and every RLS policy silently evaluating as the wrong user.

Sessions are created here and in `worker/` and nowhere else (CLAUDE.md 4.1 rule 2).
`tests/test_scaffold.py` greps for violations and fails the build on one, because
the claim propagation below only works if exactly one place owns the boundary.

There are two dependencies and there will not be a third:

  * `get_db` - a request that carries an access token. Verifies it, opens one
    transaction, sets the claim inside that transaction, then switches into
    `app_role` so RLS applies to every statement the service issues.
  * `get_db_anon` - the four endpoints that *cannot* carry one: login, OTP verify,
    refresh and cookie-only logout (rule 25). Sets no claim at all, switches into
    `app_anon`, and reaches the database only through the eight `SECURITY DEFINER`
    functions.

The order inside `get_db` is load-bearing (FS-002 5.1): the claims lookup runs
first, as the owner, because under `app_role` a self-only policy on `app_user` would
return nothing for a caller whose claim is not yet set, and every request would 401.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

import structlog
from fastapi import Depends, Header, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.config import Settings, get_settings
from api.db.session import async_session_factory, enter_role
from api.domain.auth import AccessClaims, decode_access_token
from api.errors import (
    ApiError,
    ForbiddenError,
    PasswordChangeRequiredError,
    UnauthenticatedError,
)

log = structlog.get_logger()

# One statement, and the join predicate is load-bearing.
#
# An earlier revision of the spec wrote `JOIN session s ON s.id = :sid` with no
# u-to-s condition and no filter on u.id - a cross join returning every user for a
# valid session id. It is written here as it must actually run.
#
# deleted_at IS NULL is not in the spec's diagram and belongs here anyway: it is
# the same hole the cross-vendor review found on the refresh path (X-3), where an
# account hidden from both sign-in lookups kept working through a token it already
# held.
_CLAIMS_QUERY = text(
    """
    SELECT u.is_active, u.token_version, u.must_change_password
      FROM app_user u
      JOIN session s ON s.id = :sid AND s.user_id = u.id
     WHERE u.id = :sub
       AND u.deleted_at IS NULL
       AND s.revoked_at IS NULL
       AND s.expires_at > now()
    """
)


# The two routes a forced-change session may still reach: read who you are, and
# change the password. Refresh and logout take the anonymous dependency and never
# come through here, so the session keeps refreshing long enough to do it.
_PASSWORD_CHANGE_ALLOWED = frozenset({("GET", "/auth/me"), ("POST", "/auth/password")})
_API_PREFIX_RE = re.compile(r"^/api/v\d+")


def _password_change_allowed(request: Request) -> bool:
    """Compares the matched route's path template, not the URL: on this FastAPI
    (0.141.1) the path in `request.scope["route"]` is router-relative inside a
    dependency (`/auth/me`, executed); the prefix is stripped in case a later
    version reports it mounted."""
    route = request.scope.get("route")
    path = getattr(route, "path", None) or request.url.path
    path = _API_PREFIX_RE.sub("", path)
    return (request.method.upper(), path) in _PASSWORD_CHANGE_ALLOWED


def bearer_token(request: Request) -> str | None:
    """The Bearer token, or None. Public because /auth/logout needs to read a
    session id out of an access token without requiring a valid one."""
    header = request.headers.get("Authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """A transaction with the caller's identity set on it.

    Revocation applies on the *next request* rather than when a token happens to
    expire, which is what AC-AUTH-8 to 12 require - so this re-reads `app_user` and
    `session` every time rather than trusting the token's own claims.
    """
    settings = get_settings()
    token = bearer_token(request)
    if token is None:
        raise UnauthenticatedError()

    claims = decode_access_token(token, settings.jwt_secret.get_secret_value(),
                                 algorithm=settings.jwt_algorithm)
    if claims is None:
        raise UnauthenticatedError()

    async with async_session_factory() as session, session.begin():
        row = (
            await session.execute(_CLAIMS_QUERY, {"sid": claims.sid, "sub": claims.sub})
        ).one_or_none()

        # No row means the session is revoked, expired, belongs to someone else,
        # or the user is gone. All of them are the same 401.
        if row is None or not row.is_active or row.token_version != claims.token_version:
            raise UnauthenticatedError()

        # FS-006 rule 4: a temporary password is changed before anything else is
        # done. Enforced here, not by the client, and before require() so the
        # answer is password_change_required rather than insufficient_permission.
        if row.must_change_password and not _password_change_allowed(request):
            raise PasswordChangeRequiredError()

        # TRANSACTION-LOCAL. The third argument is the whole point: a plain SET
        # here leaks this user's identity onto whichever request next borrows this
        # pooled connection, and every policy after that evaluates as the wrong
        # person. Invisible under light load; catastrophic under real load. The
        # pooled-connection test asserts both halves of this.
        #
        # app.current_user_id is the ONLY claim set. An earlier design also set
        # app.current_role; nothing read it and ADR-038 forbids it, because a
        # second claim policies could be written against is a second source of
        # truth for a role that must only ever come from app_user.role_id.
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": claims.sub},
        )
        # After the claim, before the yield. Everything the service runs from here
        # is policy-filtered. Forgetting this line makes every policy decorative;
        # tests/db/test_role_switch.py asserts current_user inside the request.
        await enter_role(session, settings.db_app_role)
        request.state.claims = claims
        yield session


async def get_db_anon() -> AsyncIterator[AsyncSession]:
    """A transaction with no claim at all, for the four pre-auth endpoints.

    A connection with no claim must not be able to read `app_user` freely: it holds
    every password hash, and once `app_user` acquires RLS in FS-002 a NULL claim
    resolves every scope check to nothing and login silently returns zero rows for
    everyone. So this path reaches the database only through definer functions.

    `SET LOCAL ROLE`, and only when there is a role to switch to. `db_anon_role` is
    unset on the development box because `appuser` holds no CREATEROLE and is a
    member of no role - issuing it unconditionally would return 500 on every
    sign-in here (GAP-021). It is written as `set_config('role', ..., true)` rather
    than `SET LOCAL ROLE <name>` because a role name cannot be a bind parameter and
    this form takes one; `role` is an ordinary GUC and `true` makes it
    transaction-local, for exactly the reason the claim is.
    """
    settings = get_settings()
    async with async_session_factory() as session, session.begin():
        await enter_role(session, settings.db_anon_role)
        yield session


async def assert_runtime_role(settings: Settings | None = None) -> None:
    """Rule 5, at startup. Outside `local`, refuse to serve if the runtime role is
    unset, missing, or not granted to the login: a policy migration on a cluster
    without the role is one where every policy is bypassed, and a NOTICE in a log
    is not the way to say that (ISS-052). In `local` it is a warning, so a box
    without the role still starts.
    """
    settings = settings or get_settings()
    role = settings.db_app_role
    problem: str | None = None
    if not role:
        problem = "DB_APP_ROLE is unset; every transaction would run as the schema owner"
    else:
        async with async_session_factory() as session:
            exists = (await session.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r)"),
                {"r": role})).scalar_one()
            member = exists and (await session.execute(
                text("SELECT pg_has_role(current_user, CAST(:r AS name), 'MEMBER')"),
                {"r": role})).scalar_one()
        if not exists:
            problem = f"role {role!r} does not exist on this cluster"
        elif not member:
            problem = f"{role!r} exists but the login is not a member; SET ROLE would fail"
    if problem is None:
        return
    if settings.environment != "local":
        raise RuntimeError(f"refusing to start: {problem}. See FS-002 5.1 and GAP-028.")
    log.warning("runtime role not active", problem=problem)


async def get_claims(request: Request) -> AccessClaims:
    """The verified claims `get_db` put on the request.

    Depends on `get_db` so it cannot be used without the transaction that
    validated it - asking for claims alone would otherwise give a caller a
    plausible identity with nothing checked behind it.
    """
    claims: AccessClaims | None = getattr(request.state, "claims", None)
    if claims is None:
        raise UnauthenticatedError()
    return claims


# scope="function" is load-bearing, not a tidy default.
#
# A yield dependency defaults to request scope, and its exit code - which is where
# `session.begin()` COMMITs - then runs *after* the response has been handed to the
# client. Executed on FastAPI 0.141.1: the observed order was route returns,
# middleware sees the response, and only then the dependency exits. So a failed
# COMMIT could not change the answer: a sign-in would return 200 and a token for a
# session that was never persisted, and a logout would return 204 having revoked
# nothing.
#
# "function" ends the dependency after the path operation and BEFORE the response
# goes out, so a commit failure becomes a 500 rather than a lie.
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]
AnonSession = Annotated[AsyncSession, Depends(get_db_anon, scope="function")]
Claims = Annotated[AccessClaims, Depends(get_claims)]


def require(module: str, action: str) -> Callable[..., Coroutine[Any, Any, None]]:
    """Gate an endpoint on a permission, asking the database rather than the token.

    Rule 19, and ISS-027. The obvious implementation checks `claims.role`, which
    was captured at sign-in and is up to fifteen minutes stale, while RLS
    re-derives the role from `app_user.role_id` on every call - so the API would
    enforce the old role while the database had already switched, producing a 403
    on something the database would allow, or the reverse. `app_has_permission`
    runs inside the same transaction as the policies, so both paths read the same
    row at the same instant and cannot disagree.

    This is authorization for *whether*, not *which rows*. Scope is RLS's job and
    is never checked here.
    """

    async def dep(db: DbSession) -> None:
        allowed = await db.execute(
            text("SELECT app_has_permission(:m, :a)"), {"m": module, "a": action}
        )
        if not allowed.scalar_one():
            raise ForbiddenError()

    return dep


# ── who is calling, and what they may reach ──────────────────────────────────
#
# Stage 3 of FS-002 section 3, resolved once per request into the Caller that the
# service scope predicate and the parent lookups read (api/authz/predicate.py).
# Two reads, under the caller's own claim and app_role: the anchor row, which the
# app_user self policy admits, and the permission rows, which role_permission
# grants every authenticated caller.
#
#   scopes  -- module -> the scope of its *view* row, which is what app_scope()
#              resolves and what every branch is guarded on.
#   deletes -- the modules the caller may delete, which is also what lets them see
#              a soft-deleted row ({t}_res_deleted; FS-002 code review F-5).
#
# A module the caller holds no permission for is absent from both, and the
# predicate for it is the self row or false -- the service never issues an
# unscoped read (rule 2).
_ANCHOR_QUERY = text(
    "SELECT org_unit_id, partner_id FROM app_user WHERE id = (SELECT app_current_user_id())"
)
_PERMS_QUERY = text(
    "SELECT rp.module, rp.action::text AS action, rp.scope::text AS scope "
    "FROM role_permission rp JOIN app_user u ON u.role_id = rp.role_id "
    "WHERE u.id = (SELECT app_current_user_id())"
)


async def get_caller(db: DbSession, claims: Claims) -> Caller:
    anchor = (await db.execute(_ANCHOR_QUERY)).one()
    rows = (await db.execute(_PERMS_QUERY)).all()
    return Caller(
        user_id=claims.sub,
        org_unit_id=str(anchor.org_unit_id) if anchor.org_unit_id is not None else None,
        partner_id=str(anchor.partner_id) if anchor.partner_id is not None else None,
        scopes={r.module: r.scope for r in rows if r.action == "view"},
        deletes=frozenset(r.module for r in rows if r.action == "delete"),
    )


CallerDep = Annotated[Caller, Depends(get_caller)]


# ── the idempotency key, one per mutation ────────────────────────────────────
#
# Rule 5. Every POST, PATCH and DELETE carries an Idempotency-Key, so a mobile
# client that retries a request whose reply it never saw does not create the row
# twice. Missing is a 400 the client can fix, not a 422 about the body: the header
# is the fault, and it is read before the body is even looked at.
#
# This only *requires* the header. Reserving the record happens inside the route,
# after require() and body validation, so a 400 here, a 403 from require() and a
# schema 422 all store nothing and re-execute on a retry (FS-003 4, plan review
# B-5). api/idempotency.py owns the reserve-work-store algorithm.
async def idempotency_key(
    idempotency_key: Annotated[str | None, Header()] = None,
) -> str:
    if not idempotency_key or not idempotency_key.strip():
        raise ApiError(
            "An Idempotency-Key header is required on this request.",
            code="idempotency_key_required",
        )
    return idempotency_key.strip()


IdemKey = Annotated[str, Depends(idempotency_key)]
