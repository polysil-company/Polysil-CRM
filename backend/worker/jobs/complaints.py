"""The complaint escalation sweep (FS-028): an open complaint past its response or
resolution target, not yet escalated, gets one `complaint.escalated` event, and
the bell trigger tells the owner and the managers at that stage.

`complaint_escalate_due()` is a definer in migration 048 that refuses anyone but
the system principal and does nothing while the setting is `off`. It takes the
database's clock through the parameter so a test can hand it any moment.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text

from api.config import get_settings
from api.db.session import async_session_factory
from worker.jobs.outbox import enter_as_principal

log = structlog.get_logger(__name__)

# Bounds one transaction; the rest go five minutes later, oldest first.
SWEEP_LIMIT = 200


async def complaint_escalation(ctx: dict[str, Any]) -> dict[str, int]:
    settings = get_settings()
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        escalated = int((await session.execute(
            text("SELECT complaint_escalate_due(now(), :n)"), {"n": SWEEP_LIMIT})).scalar_one())
    if escalated:
        log.info("complaint.escalation", escalated=escalated)
    return {"escalated": escalated}
