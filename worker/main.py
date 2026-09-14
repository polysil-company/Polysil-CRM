"""ARQ worker settings.

The worker sets claims too, so RLS applies to background jobs exactly as it does
to requests (Proposed-Backend-Architecture 5.2). A job that runs without a claim
sees nothing, which is the correct failure - silent zero-row updates are the one
outcome this must never produce.
"""

from __future__ import annotations

from typing import ClassVar

from arq.connections import RedisSettings

from api.config import get_settings
from worker.jobs.outbox import outbox_drain, purge_expired_sessions
from worker.schedules import CRON_JOBS


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(str(get_settings().redis_url))


class WorkerSettings:
    redis_settings = _redis_settings()
    functions: ClassVar[list] = [outbox_drain, purge_expired_sessions]
    cron_jobs: ClassVar[list] = CRON_JOBS
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600
