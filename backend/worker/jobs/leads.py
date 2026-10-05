"""The nightly dormant-lead sweep (FS-035): an open lead with no activity for
`dormant_after_days` moves to dormant.

`lead_dormant_sweep()` is a definer in migration 040 that refuses anyone but the
system principal. It takes `now()` from the database's clock through the parameter
so a test can hand it any moment; the cut-off is a duration, so the IST day does
not matter here.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text

from api.config import get_settings
from api.db.session import async_session_factory
from worker.jobs.outbox import enter_as_principal

log = structlog.get_logger(__name__)

# Bounds one transaction; the rest go the next night (FS-035 rule 8).
SWEEP_LIMIT = 2000


async def lead_dormancy(ctx: dict[str, Any]) -> dict[str, int]:
    settings = get_settings()
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        swept = int((await session.execute(
            text("SELECT lead_dormant_sweep(now(), :n)"), {"n": SWEEP_LIMIT})).scalar_one())
    if swept:
        log.info("lead.dormancy", swept=swept)
    return {"swept": swept}
