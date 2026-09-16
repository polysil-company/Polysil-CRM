"""App factory, middleware, router mounting.

Thin on purpose: routers parse and delegate, services own transactions, domain
owns logic. Nothing here knows a business rule.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.db.session import engine
from api.deps import assert_runtime_role
from api.errors import (
    ApiError,
    api_error_handler,
    internal_error_handler,
    validation_error_handler,
)
from api.routers import auth, leads, masters, users

log = structlog.get_logger()

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Rule 5. Outside local this raises and the process does not serve.
    await assert_runtime_role()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Polysil CRM API",
        version="0.1.0",
        # The OpenAPI schema is the contract with the frontend track (ADR-024), and
        # scripts/generate_api_docs.py reads it. Keep it reachable in every
        # environment the other track develops against.
        docs_url="/docs" if settings.environment != "production" else None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health", include_in_schema=False)
    async def health() -> JSONResponse:
        """Liveness only. It deliberately does not touch the database: a health
        check that opens a transaction turns a slow database into a restart loop.

        It does report whether pre-auth containment is active, because an unset
        db_anon_role is a weakness that is otherwise invisible (GAP-021).
        """
        return JSONResponse(
            {
                "status": "ok",
                "environment": settings.environment,
                "pre_auth_containment": bool(settings.db_anon_role),
                "runtime_role": settings.db_app_role,
            }
        )

    # Every ApiError becomes {"error": {"code", "message"}} (FS-001 section 4).
    # Registered for the base class so a new error type inherits the envelope
    # rather than having to remember it.
    app.add_exception_handler(ApiError, api_error_handler)
    # And schema validation, which FastAPI would otherwise answer with its own
    # {"detail": [...]} - a second error shape the frontend would have to handle
    # and which the generated ErrorResponse type does not describe.
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    # And everything else, so a 500 is the envelope too rather than Starlette's
    # plain-text default (ISS-072). The body carries no detail.
    app.add_exception_handler(Exception, internal_error_handler)

    # Base path is /api/v1. The version is in the path rather than a header so a
    # breaking change can run alongside its predecessor (ADR-028).
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(leads.router, prefix=API_PREFIX)
    app.include_router(leads.lookups, prefix=API_PREFIX)
    app.include_router(users.router, prefix=API_PREFIX)
    app.include_router(users.roles, prefix=API_PREFIX)
    app.include_router(masters.org_units, prefix=API_PREFIX)
    app.include_router(masters.territories, prefix=API_PREFIX)
    app.include_router(masters.partners, prefix=API_PREFIX)

    return app


app = create_app()
