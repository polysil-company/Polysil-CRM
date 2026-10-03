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


async def scheme_nightly(ctx: dict[str, Any]) -> dict[str, int]:
    settings = get_settings()
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        expired = int((await session.execute(
            text("SELECT scheme_entitlement_expire()"))).scalar_one())
        credited = int((await session.execute(
            text("SELECT scheme_period_evaluate(:today)"), {"today": today_ist()})).scalar_one())
        points = int((await session.execute(text("SELECT reward_points_expire()"))).scalar_one())
    if expired or credited or points:
        log.info("scheme.nightly", expired=expired, credited=credited, points_expired=points)
    return {"expired": expired, "credited": credited, "points_expired": points}
