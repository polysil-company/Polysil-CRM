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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import LOCALHOST_ORIGIN, get_settings
from api.db.session import engine
from api.deps import assert_runtime_role
from api.errors import (
    ApiError,
    api_error_handler,
    internal_error_handler,
    validation_error_handler,
)
from api.redact import install_access_log_filter, redact_path
from api.routers import (
    auth,
    commission,
    complaints,
    dashboard,
    lead_qr,
    leads,
    marketing,
    masters,
    messages,
    notifications,
    orders,
    payments,
    pricing,
    products,
    public,
    quotations,
    reports,
    rewards,
    schemes,
    stock,
    subsidy,
    subsidy_applications,
    subsidy_follow_ups,
    targets,
    tasks,
    tracking,
    users,
)
from api.routers import campaigns as campaign_routes
from api.routers import customers as customer_routes
from api.routers import holidays as holiday_routes
from api.routers import settings as settings_routes
from api.upload_limit import BodyTooLarge, UploadLimit, body_too_large_handler

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
    # FS-038 rule 2: uvicorn's access log writes the webhook path, secret and all
    install_access_log_filter()

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

    # FS-015 rule 10: the attachment size cap, before the form is read. Added first,
    # so it sits innermost, next to the router: outside request_context (a
    # BaseHTTPMiddleware, which reads through its own task group) the raised
    # BodyTooLarge reached FastAPI wrapped and came back a 400 (executed).
    app.add_middleware(UploadLimit)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id,
                                               path=redact_path(request.url.path))
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
        # Read at request time, not from the instance this factory closed over.
        # The settings are an lru_cache, and a test that clears it leaves the app
        # holding an object nobody can reach any more - so this endpoint reported
        # a configuration that was no longer the live one, which is the one thing
        # it exists to do.
        live = get_settings()
        body: dict[str, object] = {
            "status": "ok",
            "environment": live.environment,
            "pre_auth_containment": bool(live.db_anon_role),
            "runtime_role": live.db_app_role,
        }
        # FS-007 rule 16: which provider this box talks to, outside production
        # only; the endpoint is unauthenticated and already says enough.
        if live.environment != "production":
            body["whatsapp"] = live.whatsapp_provider
        return JSONResponse(body)

    # ── the browser's permission to call us at all ───────────────────────────
    #
    # Only added when something is configured, so the default build has no CORS
    # surface and a same-origin or dev-server-proxied frontend never needs one.
    #
    # `allow_origin_regex` rather than a pinned port: a frontend developer's dev
    # server moves between 3000, 5173 and whatever is free, and pinning one means
    # asking them every time. Credentials forbid `*`, but a regex echoes back the
    # origin it matched, which is what the browser requires.
    #
    # **The cookie has to agree with this.** A cross-origin frontend also needs
    # `refresh_cookie_samesite = "none"`, or sign-in works and the session dies at
    # the first refresh (`_set_refresh_cookie`).
    origins = list(settings.cors_allow_origins)
    localhost = LOCALHOST_ORIGIN.pattern if settings.cors_allow_localhost else None
    if origins or localhost:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_origin_regex=localhost,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            # Named rather than "*", because with credentials the browser will not
            # accept a wildcard, and because Idempotency-Key is ours and would
            # otherwise be stripped from every mutation.
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
            max_age=600,
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
    app.add_exception_handler(BodyTooLarge, body_too_large_handler)

    # Base path is /api/v1. The version is in the path rather than a header so a
    # breaking change can run alongside its predecessor (ADR-028).
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(leads.router, prefix=API_PREFIX)
    app.include_router(leads.lookups, prefix=API_PREFIX)
    app.include_router(lead_qr.router, prefix=API_PREFIX)
    app.include_router(users.router, prefix=API_PREFIX)
    app.include_router(users.roles, prefix=API_PREFIX)
    app.include_router(masters.org_units, prefix=API_PREFIX)
    app.include_router(masters.territories, prefix=API_PREFIX)
    app.include_router(masters.partners, prefix=API_PREFIX)
    app.include_router(subsidy.router, prefix=API_PREFIX)
    app.include_router(products.router, prefix=API_PREFIX)
    app.include_router(products.tax_rates, prefix=API_PREFIX)
    app.include_router(pricing.price_lists, prefix=API_PREFIX)
    app.include_router(pricing.router, prefix=API_PREFIX)
    app.include_router(quotations.router, prefix=API_PREFIX)
    app.include_router(orders.router, prefix=API_PREFIX)
    app.include_router(orders.approvals, prefix=API_PREFIX)
    app.include_router(orders.dispatches, prefix=API_PREFIX)
    app.include_router(tasks.router, prefix=API_PREFIX)
    app.include_router(tasks.planner, prefix=API_PREFIX)
    app.include_router(tasks.minutes, prefix=API_PREFIX)
    app.include_router(complaints.router, prefix=API_PREFIX)
    app.include_router(complaints.policies, prefix=API_PREFIX)
    app.include_router(dashboard.router, prefix=API_PREFIX)
    app.include_router(notifications.router, prefix=API_PREFIX)
    app.include_router(messages.router, prefix=API_PREFIX)
    app.include_router(messages.directory, prefix=API_PREFIX)
    app.include_router(subsidy_applications.router, prefix=API_PREFIX)
    app.include_router(subsidy_applications.lookups, prefix=API_PREFIX)
    app.include_router(schemes.router, prefix=API_PREFIX)
    app.include_router(schemes.entitlements, prefix=API_PREFIX)
    app.include_router(rewards.rules, prefix=API_PREFIX)
    app.include_router(rewards.settings_router, prefix=API_PREFIX)
    app.include_router(rewards.gifts, prefix=API_PREFIX)
    app.include_router(rewards.router, prefix=API_PREFIX)
    app.include_router(rewards.order_points, prefix=API_PREFIX)
    app.include_router(commission.on_application, prefix=API_PREFIX)
    app.include_router(commission.router, prefix=API_PREFIX)
    app.include_router(commission.rates, prefix=API_PREFIX)
    app.include_router(marketing.materials, prefix=API_PREFIX)
    app.include_router(marketing.router, prefix=API_PREFIX)
    app.include_router(subsidy_follow_ups.reports, prefix=API_PREFIX)
    app.include_router(subsidy_follow_ups.masters, prefix=API_PREFIX)
    app.include_router(tracking.me, prefix=API_PREFIX)
    app.include_router(tracking.router, prefix=API_PREFIX)
    app.include_router(tracking.locations, prefix=API_PREFIX)
    app.include_router(tracking.visits, prefix=API_PREFIX)
    app.include_router(payments.router, prefix=API_PREFIX)
    app.include_router(payments.orders, prefix=API_PREFIX)
    app.include_router(payments.partners, prefix=API_PREFIX)
    app.include_router(stock.warehouses, prefix=API_PREFIX)
    app.include_router(stock.router, prefix=API_PREFIX)
    app.include_router(reports.router, prefix=API_PREFIX)
    app.include_router(reports.leads, prefix=API_PREFIX)
    app.include_router(targets.router, prefix=API_PREFIX)
    app.include_router(settings_routes.router, prefix=API_PREFIX)
    app.include_router(holiday_routes.router, prefix=API_PREFIX)
    app.include_router(campaign_routes.router, prefix=API_PREFIX)
    app.include_router(customer_routes.router, prefix=API_PREFIX)
    # The farmer's link and the website form: no session, definer functions on
    # app_anon (FS-005 4, FS-003a). Served under /api/v1, because a deployment's
    # proxy sends only /api/v1 to the API and the rest to the frontend: at the root
    # alone the customer's link was unreachable (demo walk D-2). The root mount
    # stays for links already sent and for the local storage adapter's file route,
    # out of the schema so the docs show one path.
    app.include_router(public.router, prefix=API_PREFIX)
    app.include_router(public.router, include_in_schema=False)

    return app


app = create_app()
