"""The schemes' and rewards' nightly run (FS-031, FS-032): expire credits past their
date, credit the period schemes whose month or quarter has ended, then expire reward
points past theirs.

Both functions are definers in migration 033 that refuse anyone but the system
principal. The date is today_ist() passed in: current_date is UTC on this box.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text

from api.config import get_settings
from api.db.session import async_session_factory
from api.services.clock import today_ist
from worker.jobs.outbox import enter_as_principal

log = structlog.get_logger(__name__)


async def _step(sql: str, params: dict[str, Any] | None = None) -> int:
    """One definer in its own transaction: a failure in one step rolls back only that
    step, and the others still run tonight (PR 11 review)."""
    settings = get_settings()
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        return int((await session.execute(text(sql), params or {})).scalar_one())


async def scheme_nightly(ctx: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, sql, params in (
            ("expired", "SELECT scheme_entitlement_expire()", None),
            ("credited", "SELECT scheme_period_evaluate(:today)", {"today": today_ist()}),
            ("points_expired", "SELECT reward_points_expire()", None)):
        try:
            out[key] = await _step(sql, params)
        except Exception:
            # logged and skipped: the next night retries it, the other steps are unaffected
            log.exception("scheme.nightly_step_failed", step=key)
            out[key] = 0
    if any(out.values()):
        log.info("scheme.nightly", **out)
    return out
