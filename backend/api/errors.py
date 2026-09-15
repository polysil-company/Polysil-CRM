"""The error envelope, and the exceptions that produce it.

Every failure response is `{"error": {"code", "message"}}` (FS-001 section 4). The
code is the contract and clients switch on it; the message is for a human and may
be reworded at any time.

Two of these are worth reading before adding a third:

  * `UnauthenticatedError` and `ForbiddenError` are different on purpose. 401 means "we do
    not know who you are"; 403 means "you cannot do this". A third case - valid,
    permitted, nothing in scope - is a **200 with an empty list**, not an error,
    and the UI must treat it differently from 403.
  * `InvalidCredentialsError` carries one message for a wrong password, an unknown
    email and an inactive account alike. Distinguishing them tells an attacker
    which addresses exist.
"""

from __future__ import annotations

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Base for anything that should reach the client as an error envelope."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "The request could not be processed."

    def __init__(self, message: str | None = None, *, code: str | None = None,
                 fields: dict[str, str] | None = None) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        # A handler-raised 422 or 409 carries the same field map that
        # validation_error_handler produces for a schema failure (FS-003 plan
        # review B-5). Without this only the schema path emitted `fields`, and the
        # generated ErrorResponse type promised a key nothing set.
        self.fields = fields
        super().__init__(self.message)

    def envelope(self) -> dict[str, object]:
        body: dict[str, object] = {"code": self.code, "message": self.message}
        if self.fields is not None:
            body["fields"] = self.fields
        return {"error": body}


class UnauthenticatedError(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"
    message = "Sign in to continue."


class InvalidCredentialsError(ApiError):
    """One message for a wrong password, an unknown email and an inactive account.

    The caller cannot tell them apart, and neither can a stopwatch: the service
    verifies against a dummy hash when no user is found, so the unknown-email path
    spends the same Argon2 work factor as the known one.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "invalid_credentials"
    message = "Email or password is incorrect."


class AccountLockedError(ApiError):
    status_code = status.HTTP_423_LOCKED
    code = "account_locked"
    message = "Too many attempts. Try again in 15 minutes."


class InvalidOtpError(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "invalid_otp"
    message = "That code is not valid. Request a new one."


class RefreshFailedError(ApiError):
    """One of the four codes in section 4's precedence table."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "invalid_refresh"
    message = "Your session has ended. Sign in again."


class ForbiddenError(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "insufficient_permission"
    message = "You do not have permission to do this."


class ValidationFailed(ApiError):
    """A field failed a business rule the schema could not catch: a mobile that is
    not Indian, a territory with no coded state, a parent out of scope. Same code
    and `fields` shape as a schema 422, so the frontend handles one thing."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"
    message = "Some fields need correcting."


class NotFoundError(ApiError):
    """The id is not in the caller's scope, which includes 'exists but hidden' -
    the two are one answer on purpose, so a 404 leaks no existence (FS-003 section 4)."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Not found."


class StageChangedError(ApiError):
    """The caller sent expected_stage and the row has moved on since they read it
    (FS-003 section 3). `fields.stage` carries the current stage."""

    status_code = status.HTTP_409_CONFLICT
    code = "stage_changed"
    message = "The lead has moved to a different stage since you loaded it."


class IdempotencyConflictError(ApiError):
    """Same key, different body. AC-IDEM-3. Replaying it would be worse than
    refusing: the caller believes one request happened and a different one did.

    409, not 422: a reused key with a changed payload is a conflict with a prior
    request, not a validation failure of this one. FS-001 shipped it as 422; FS-003
    corrects it to match AC-IDEM-3."""

    status_code = status.HTTP_409_CONFLICT
    code = "idempotency_key_reused"
    message = "This Idempotency-Key was already used for a different request."


class ServiceUnavailableError(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"
    message = "Temporarily unavailable. Try again shortly."


async def api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    err = exc if isinstance(exc, ApiError) else ApiError()
    return JSONResponse(status_code=err.status_code, content=err.envelope())


def error_response(err: ApiError) -> JSONResponse:
    """The same envelope as the handler, for a route that must **return** rather
    than raise.

    Raising unwinds through `get_db`'s `async with session.begin()`, which rolls
    the transaction back. That is right for a failure with nothing to persist and
    wrong for one that has already written something it must keep - a
    `login_attempt` row the lockout counts, or the family revocation that reuse
    detection performs. Those paths return this instead.
    """
    return JSONResponse(status_code=err.status_code, content=err.envelope())


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """A 422 in the same envelope as every other failure.

    FastAPI's default emits `{"detail": [...]}`, which is a second error shape the
    frontend has to handle and which the generated `ErrorResponse` type does not
    describe - so the contract said one thing and the API did another. The
    envelope is the contract (FS-001 section 4), so validation joins it.

    `fields` maps a dotted path to the reason. The loc tuple starts with `body` or
    `query`, which is noise to a form, so the first element is dropped.
    """
    fields: dict[str, str] = {}
    if isinstance(exc, RequestValidationError):
        for err in exc.errors():
            loc = [str(part) for part in err.get("loc", ())][1:]
            fields[".".join(loc) or "body"] = str(err.get("msg", "invalid"))

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": {
                "code": "validation_error",
                "message": "Some fields need correcting.",
                "fields": fields,
            }
        },
    )


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """A 500 in the same envelope as every other failure (ISS-072).

    Without this, an unhandled error (a DBAPIError, the 42501 a mid-mutation RLS
    refusal raises) reaches Starlette's default handler and the client gets plain
    text, which breaks the one-shape contract of FS-001 section 4. The body carries
    no detail on purpose: no SQLSTATE, no message, nothing an attacker can use. The
    traceback goes to the log with the request path; Starlette re-raises after the
    response is sent so the server log sees it too.
    """
    import structlog

    structlog.get_logger().error("unhandled error", path=request.url.path,
                                 error=type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "internal_error",
                           "message": "Something went wrong. Try again shortly."}},
    )
