"""The six /auth endpoints.

Thin on purpose: parse, delegate, shape the response. Every transaction belongs to
a dependency and every rule belongs to the service or the database.

**The docstrings below become prose in `docs/api/auth.md`** (CLAUDE.md 2.3), which
is what the frontend track builds against. They are written for that reader - what
the endpoint is *for* - rather than describing the code.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Cookie, Header, Request, Response, status
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.deps import AnonSession, Claims, DbSession, IdemKey, bearer_token
from api.domain.auth import decode_access_token
from api.errors import ForbiddenError, RefreshFailedError, error_response
from api.idempotency import redacted_digest, run_idempotent
from api.schemas.auth import (
    Envelope,
    ErrorResponse,
    LoginRequest,
    MeResponse,
    OtpRequestBody,
    OtpRequestResponse,
    OtpVerifyBody,
    OwnPasswordChange,
    TokenResponse,
)
from api.services import auth as service

router = APIRouter(prefix="/auth", tags=["auth"])

# The refresh token lives here and in no response body (rule 4).
REFRESH_COOKIE = "polysil_refresh"

# Declared on every route so the generated client has one error type. 422 is in
# here because validation now uses the same envelope rather than FastAPI's
# {"detail": [...]}.
_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in, or credentials rejected."},
    422: {"model": ErrorResponse, "description": "A field failed validation; see `fields`."},
}


def _set_refresh_cookie(response: Response, token: str) -> None:
    """httpOnly, Secure, SameSite=Lax, and scoped to the refresh path.

    `path` matters as much as the flags: scoped to `/api/v1/auth`, the browser
    does not attach a thirty-day credential to every ordinary API call, so an
    XSS-adjacent leak of request headers cannot pick it up in passing.

    `secure` follows the environment, because a cookie marked Secure is simply not
    stored over plain HTTP and local development would silently never authenticate.

    `samesite` follows configuration for a reason worth knowing: a `Lax` cookie is
    not attached to a cross-site background request, so a frontend on another
    origin signs in successfully and then loses the session at its first refresh,
    with nothing in any log to say why. Cross-site needs `None`, which needs
    `Secure`, which the settings refuse to combine with plain HTTP.
    """
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=int(settings.refresh_token_ttl.total_seconds()),
        httponly=True,
        secure=settings.environment != "local",
        samesite=settings.refresh_cookie_samesite,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


def _cross_site(request: Request) -> bool:
    """Whether this is a browser request from an origin that may not spend a cookie.

    CORS does not stop it. CORS decides whether a page may *read* a response; a
    simple POST is sent either way, and a cookie-authenticated endpoint has already
    acted by the time the browser discards the answer. With
    `refresh_cookie_samesite = "none"`, which a frontend on another origin needs,
    any site could therefore force a sign-out or rotate someone's session by
    submitting a form (cross-vendor review, September).

    A browser always sends `Origin` on a POST; curl and a mobile app send none. So
    an absent header is allowed and a present one has to be ours, same-origin
    included - the API's own pages call these endpoints too. The comparison is on
    the authority only, because with `--no-proxy-headers` the request's own scheme
    is the internal one and the browser's is the public one.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return False
    host = request.headers.get("host")
    if host and origin.partition("://")[2] == host:
        return False
    return not get_settings().origin_allowed(origin)


Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=1)
def _trusted_networks(peers: tuple[str, ...]) -> tuple[Network, ...]:
    """Parsed once. The settings validator has already refused anything unparseable."""
    return tuple(ipaddress.ip_network(p, strict=False) for p in peers)


def _is_trusted_peer(peer: str) -> bool:
    if peer == "localhost":
        return True
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(address in net for net in _trusted_networks(get_settings().trusted_proxy_peers))


def _client_ip(request: Request) -> str | None:
    """The caller's address, not the reverse proxy's.

    `request.client.host` is whoever opened the TCP connection, which behind a
    reverse proxy is the proxy. Taken literally, every rate-limit bucket in the
    system collapses into one and `login_attempt.ip` records the proxy on every row.

    The rightmost `X-Forwarded-For` entry is the one the trusted proxy appended -
    the address it actually saw - so it is the one to believe. Entries further
    left are supplied by the client and are not evidence of anything.

    **Trusted only from a peer named in `trusted_proxy_peers`**, and only for as
    many hops as `trusted_proxy_hops` allows. A header from any other peer is
    ignored outright, or anyone could pick their own rate-limit bucket.

    That list used to be loopback alone, which is right when the proxy runs on the
    host and wrong the moment it runs in a container: the peer is then 172.x, the
    header is ignored, and the collapse above happens silently while the endpoint
    still answers 202 (ISS-084).
    """
    peer = request.client.host if request.client else None
    hops = get_settings().trusted_proxy_hops
    if peer is None or hops <= 0 or not _is_trusted_peer(peer):
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer
    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not chain:
        return peer
    return chain[-min(hops, len(chain))]


@router.post(
    "/login",
    response_model=Envelope[TokenResponse],
    responses={**_ERRORS, 423: {"model": ErrorResponse, "description": "Locked."}},
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AnonSession,
    user_agent: Annotated[str | None, Header()] = None,
) -> Envelope[TokenResponse] | JSONResponse:
    """Sign in a staff user with an email address and password.

    Returns a short-lived access token in the body and sets a long-lived refresh
    token as an httpOnly cookie. Send the access token as
    `Authorization: Bearer <token>` on every other call, and call `/auth/refresh`
    when it is close to expiring.

    **A wrong password, an unknown address and a disabled account all return the
    same 401 `invalid_credentials`.** Do not try to distinguish them in the UI -
    the server deliberately does not, because doing so tells an attacker which
    addresses exist.

    Five failed attempts in fifteen minutes return **423 `account_locked`** for
    fifteen minutes. A successful sign-in clears the count.
    """
    result = await service.login(
        db, email=body.email, password=body.password,
        user_agent=user_agent, ip=_client_ip(request),
    )
    # Returned, not raised. An exception here would unwind through the
    # dependency's transaction and roll back the login_attempt row the lockout
    # counts - which is exactly what happened, and rule 5 silently did not exist.
    if isinstance(result, service.Failure):
        return error_response(result.error)
    bundle = result
    _set_refresh_cookie(response, bundle.refresh_token)
    return Envelope(data=TokenResponse(
        access_token=bundle.access_token, expires_in=bundle.expires_in))


@router.post(
    "/otp/request",
    response_model=Envelope[OtpRequestResponse],
    status_code=status.HTTP_202_ACCEPTED,
    responses={422: _ERRORS[422]},
)
async def request_otp(
    body: OtpRequestBody, request: Request, db: AnonSession
) -> Envelope[OtpRequestResponse]:
    """Send a one-time code to a dealer's or farmer's mobile number.

    **Always 202, always the same body.** It is identical whether the number is
    registered, unknown, disabled, or has already hit a limit. That is deliberate:
    a different response would let anyone test whether a given number is a
    registered dealer.

    So the UI cannot tell whether a code was actually sent, and should not try.
    Move to the code-entry screen and let the user request a resend if nothing
    arrives - `resend_after` says when to offer that, and it is longer than the
    code's own lifetime on purpose. Three resends a minute apart exhaust the
    per-number burst limit, after which the screen would keep saying "code sent"
    for another eleven minutes with nothing being sent.
    """
    settings = get_settings()
    await service.request_otp(db, mobile=body.mobile, ip=_client_ip(request))
    return Envelope(data=OtpRequestResponse(
        expires_in=int(settings.otp_ttl.total_seconds()),
        resend_after=int(settings.otp_ttl.total_seconds()),
    ))


@router.post("/otp/verify", response_model=Envelope[TokenResponse], responses=_ERRORS)
async def verify_otp(
    body: OtpVerifyBody,
    request: Request,
    response: Response,
    db: AnonSession,
    user_agent: Annotated[str | None, Header()] = None,
) -> Envelope[TokenResponse] | JSONResponse:
    """Exchange a mobile number and its one-time code for a session.

    Same response shape as `/auth/login`. Five wrong attempts burn the code and it
    has to be requested again.

    **Submitting the same correct code twice within ninety seconds is safe** and
    returns the identical session rather than an error. That exists for the case
    where the response is lost on a bad connection: without it, a field officer
    would be told a correct code was wrong, and the code would already be spent.
    """
    result = await service.verify_otp(
        db, mobile=body.mobile, code=body.code,
        user_agent=user_agent, ip=_client_ip(request),
    )
    if isinstance(result, service.Failure):
        return error_response(result.error)
    bundle = result
    _set_refresh_cookie(response, bundle.refresh_token)
    return Envelope(data=TokenResponse(
        access_token=bundle.access_token, expires_in=bundle.expires_in))


@router.post("/refresh", response_model=Envelope[TokenResponse], responses=_ERRORS)
async def refresh(
    request: Request,
    response: Response,
    db: AnonSession,
    user_agent: Annotated[str | None, Header()] = None,
    polysil_refresh: Annotated[str | None, Cookie()] = None,
) -> Envelope[TokenResponse] | JSONResponse:
    """Exchange the refresh cookie for a new access token, and rotate the cookie.

    Takes no body and no `Authorization` header - the cookie is the credential.
    Call it before the access token expires rather than after a 401, so a user
    never loses work mid-action.

    **Four different 401 codes, and the client treats all four the same way: sign
    in again.** They are distinct so a support call can tell them apart.

    | code | what happened |
    |---|---|
    | `refresh_reused` | this token had already been used. Every session in
      the family is now revoked, because a reused token is what a stolen one
      looks like |
    | `session_revoked` | signed out, deactivated, or signed out everywhere |
    | `refresh_expired` | older than thirty days |
    | `invalid_refresh` | no such token |

    Retrying the same call within ninety seconds is safe and returns the identical
    tokens rather than triggering the reuse alarm - that window exists so a lost
    response on a slow connection does not sign the user out of everything.
    """
    if _cross_site(request):
        return error_response(ForbiddenError(
            "This origin may not use a cookie credential.", code="origin_not_allowed"))
    if polysil_refresh is None:
        # Nothing has been written, so raising here is safe - but returning keeps
        # one shape for every failure on this endpoint.
        return error_response(RefreshFailedError())

    result = await service.refresh(
        db, refresh_token=polysil_refresh,
        user_agent=user_agent, ip=_client_ip(request),
    )
    # Same reason as login, with more at stake: reuse detection revokes the whole
    # family before answering, and raising would roll that revocation back - so a
    # stolen token would trip the alarm and revoke nothing (ADR-025 inverted).
    if isinstance(result, service.Failure):
        return error_response(result.error)
    bundle = result
    _set_refresh_cookie(response, bundle.refresh_token)
    return Envelope(data=TokenResponse(
        access_token=bundle.access_token, expires_in=bundle.expires_in))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AnonSession,
    polysil_refresh: Annotated[str | None, Cookie()] = None,
) -> None:
    """Sign out of this session. Other devices stay signed in.

    **Always 204**, including when nothing was signed in. It accepts either
    credential: a `Bearer` token names the session directly, and the refresh cookie
    identifies it when the access token has already expired - which is the usual
    case for a tab left open for an hour. Send whichever you have; sending both is
    fine, and the Bearer token wins.

    The one exception to always-204 is a browser request carrying an `Origin` that
    is not allowed, which is `403 origin_not_allowed`. Your own origin is allowed,
    so you will not see it; a site trying to sign your users out will.

    To sign out everywhere, an administrator bumps the user's token version; that
    is not exposed here.
    """
    if _cross_site(request):
        raise ForbiddenError("This origin may not use a cookie credential.",
                             code="origin_not_allowed")

    # Bearer wins whenever it is present, even alongside a cookie - which is the
    # ordinary shape, not a rare one. Deriving both would hand the database two
    # ids, and it refuses that by contract (EC-18).
    session_id: str | None = None
    token = bearer_token(request)
    if token is not None:
        settings = get_settings()
        claims = decode_access_token(token, settings.jwt_secret.get_secret_value(),
                                     algorithm=settings.jwt_algorithm)
        if claims is not None:
            session_id = claims.sid

    await service.logout(db, session_id=session_id, refresh_token=polysil_refresh)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=Envelope[MeResponse], responses=_ERRORS)
async def me(db: DbSession, claims: Claims) -> Envelope[MeResponse]:
    """Who the signed-in user is, and what to render for them.

    Call this once after signing in and keep it for the session. It carries the
    role, the org unit or the channel partner, and the permission list the
    navigation is built from.

    > **`permissions` is for rendering, never for security.** Hiding a button is a
    > courtesy. An endpoint the UI forgets to hide still returns 403, and a row
    > outside the user's scope is invisible whatever the UI does. Build the screens
    > against it; do not rely on it as a guarantee.

    Read it again after anything that could change a user's access rather than
    caching it indefinitely - it is deliberately not in the access token, because a
    role baked into a token goes stale while the database has already moved on.
    """
    return Envelope(data=await service.me(db, user_id=claims.sub))


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_ERRORS,
               400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
               409: {"model": ErrorResponse,
                     "description": "An administrator reset the password meanwhile, or the "
                                    "key was used for a different body."}},
)
async def change_password(
    body: OwnPasswordChange, db: DbSession, claims: Claims, idem: IdemKey,
) -> Response:
    """Change your own password. Staff only; a partner user signs in by OTP.

    The new password must be at least 12 characters. On success every session
    including this one is signed out, so sign in again with the new password. This
    is the one call, besides `GET /auth/me`, that works while a temporary password
    is in force (`must_change_password` on `/auth/me`).

    `409 password_changed_meanwhile` means an administrator reset the password
    while you were changing it; sign in with the password they gave you.
    **`Idempotency-Key` is required.**
    """
    payload_hash = redacted_digest(body.model_dump(mode="json"),
                                   ["current_password", "new_password"])

    async def work() -> tuple[int, dict]:
        await service.change_own_password(
            db, current_password=body.current_password, new_password=body.new_password)
        return status.HTTP_204_NO_CONTENT, {}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="POST /api/v1/auth/password",
        payload_hash=payload_hash, work=work)
    if outcome.status_code == status.HTTP_204_NO_CONTENT:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
