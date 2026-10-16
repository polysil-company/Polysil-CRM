"""Field tracking's housekeeping (FS-021, review B-4).

- `tracking_auto_end`: ends a duty left open, by `api/domain/tracking.auto_end`
  (idle 30 minutes after the working day's end, or 14 hours). The rule lives in
  the domain, so the worker and its tests read one definition.
- `visit_auto_close`: closes a visit open for 12 hours.
- `location_point_purge`: deletes points past the policy's retention, in chunks.

Each reads and writes through a definer guarded on `app_is_system()`.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
from typing import Any

import structlog
from sqlalchemy import text

from api.config import get_settings
from api.db.session import async_session_factory
from api.domain import tracking as domain
from worker.jobs.outbox import enter_as_principal

log = structlog.get_logger()

PURGE_BATCH = 5000
PURGE_MAX_ROUNDS = 200


async def tracking_auto_end(ctx: dict[str, Any], *, now: dt.datetime | None = None,
                            only: frozenset[str] | None = None) -> int:
    """`only` narrows to some sessions: tests run a fake clock on a shared database
    and must not end anyone else's duty (code review F-7)."""
    now = now or dt.datetime.now(dt.UTC)
    settings = get_settings()
    ended = 0
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        policy = (await session.execute(text(
            "SELECT work_start, work_end, work_days FROM tracking_policy WHERE effective_from <= :n "
            "ORDER BY effective_from DESC LIMIT 1"), {"n": now})).one_or_none()
        if policy is None:
            return 0
        hours = domain.Hours(policy.work_start, policy.work_end, frozenset(int(d) for d in policy.work_days))
        for d in (await session.execute(text("SELECT * FROM tracking_open_duties()"))).all():
            if only is not None and str(d.id) not in only:
                continue
            end = domain.auto_end(d.started_at, d.last_point_at, now, hours)
            if end is not None and (await session.execute(text(
                    "SELECT tracking_auto_end(CAST(:i AS uuid), :e)"), {"i": str(d.id), "e": end})).scalar_one():
                ended += 1
    if ended:
        log.info("tracking.auto_end", ended=ended)
    return ended


async def visit_auto_close(ctx: dict[str, Any], *, now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.UTC)
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, get_settings())
        closed = int((await session.execute(text("SELECT visit_auto_close(:n)"), {"n": now})).scalar_one())
    if closed:
        log.info("tracking.visit_auto_close", closed=closed)
    return closed


async def location_point_purge(ctx: dict[str, Any]) -> int:
    """One transaction per chunk, so a large backlog never holds a long lock."""
    total = 0
    for _ in range(PURGE_MAX_ROUNDS):
        async with async_session_factory() as session, session.begin():
            await enter_as_principal(session, get_settings())
            n = int((await session.execute(text("SELECT location_point_purge(:b)"),
                                           {"b": PURGE_BATCH})).scalar_one())
        total += n
        if n < PURGE_BATCH:
            break
    if total:
        log.info("tracking.purge", deleted=total)
    return total
