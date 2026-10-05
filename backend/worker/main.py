"""ARQ worker settings.

The worker sets claims too, so RLS applies to background jobs exactly as it does
to requests (Proposed-Backend-Architecture 5.2). A job that runs without a claim
sees nothing, which is the correct failure - silent zero-row updates are the one
outcome this must never produce.

FS-007: one HTTP client for the process's lifetime (rule 20), the provider built
on it once, and the template check at startup as an error log (rule 13). A
misconfigured provider never reaches here: `get_settings()` refuses it at import
(rule 11), the process exits, the container restarts and logs.
"""

from __future__ import annotations

import time
from typing import Any, ClassVar

import httpx
import structlog
from arq.connections import RedisSettings

from api.config import get_settings
from api.integrations.whatsapp import get_provider
from api.integrations.whatsapp.check import check_templates, unconfigured_templates
from api.storage import get_storage
from worker.jobs.leads import lead_dormancy
from worker.jobs.orders import order_render_due
from worker.jobs.outbox import outbox_drain, purge_expired_sessions
from worker.jobs.quotations import quotation_expire, quotation_render_due, renderer_available
from worker.jobs.schemes import scheme_nightly
from worker.schedules import CRON_JOBS

log = structlog.get_logger()


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(str(get_settings().redis_url))


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    ctx["http"] = httpx.AsyncClient(timeout=httpx.Timeout(settings.whatsapp_send_timeout))
    ctx["provider"] = get_provider(settings, ctx["http"])
    if settings.whatsapp_provider != "mock":
        try:
            problems = await check_templates(ctx["provider"], settings)
        except Exception as exc:
            log.error("whatsapp.template_check_failed", kind=type(exc).__name__)
        else:
            if problems:
                log.error("whatsapp.templates", problems=problems)
            else:
                log.info("whatsapp.templates_ok")
    unset = unconfigured_templates(settings)
    if unset:
        log.warning("whatsapp.templates_unconfigured", keys=unset)
    # FS-005: the cron hours are UTC arithmetic, and arq reads the process clock.
    tz = time.strftime("%Z")
    if time.timezone != 0 and settings.environment != "local":
        log.error("worker.timezone", tz=tz, offset=time.timezone,
                  hint="set TZ=UTC on the worker service; the nightly expiry would run "
                       "five and a half hours off")
    # And the renderer: probed and logged, never refused (edge case 20).
    problem = renderer_available() if settings.pdf_renderer == "weasyprint" else None
    if problem:
        log.error("quotation.renderer_unavailable", problem=problem)
    else:
        log.info("quotation.renderer_ok", renderer=settings.pdf_renderer)
    storage_problem = get_storage(settings).probe()
    if storage_problem:
        log.error("quotation.storage_unavailable", problem=storage_problem)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    client = ctx.get("http")
    if client is not None:
        await client.aclose()


class WorkerSettings:
    redis_settings = _redis_settings()
    functions: ClassVar[list] = [outbox_drain, purge_expired_sessions,
                                 quotation_render_due, quotation_expire, order_render_due,
                                 scheme_nightly, lead_dormancy]
    cron_jobs: ClassVar[list] = CRON_JOBS
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600
