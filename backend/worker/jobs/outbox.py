"""Drain `notification_outbox`, and purge what has aged out.

Rule 6 says outbound messages go to the outbox and are never sent inside a
request. That makes the request correct and delivers nothing on its own - a table
nothing drains delivers no codes, which is why FS-001 carries this job rather than
leaving it to the notifications module (GAP-022).

**This is the second place in the system that opens a transaction**, and the only
one outside `api/deps.py` (rule 2). It sets no user claim, because there is no
user. That is correct today and will not be once RLS lands in FS-002: a job
running with no claim will see nothing and quietly update zero rows, which is the
one outcome this must never produce. It needs a system principal by then, and
GAP-026 carries it rather than leaving it to be discovered.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import Settings, get_settings
from api.db.session import async_session_factory, enter_role
from api.integrations.messages import UnknownTemplateError, render

log = structlog.get_logger()

# Exponential, capped. A provider outage should not retry a thousand messages
# every ten seconds, and a transient failure should not wait an hour.
BACKOFF_SECONDS: tuple[int, ...] = (10, 60, 300, 1800, 3600)
MAX_ATTEMPTS = len(BACKOFF_SECONDS)

# FOR UPDATE SKIP LOCKED is what lets more than one worker run without two of them
# sending the same message. The partial index on (next_attempt_at) WHERE
# state = 'pending' is what makes this a lookup rather than a scan.
_CLAIM_DUE = text(
    """
    SELECT id, channel::text AS channel, template_key, recipient, payload, attempts
      FROM notification_outbox
     WHERE state = 'pending'
       AND next_attempt_at <= now()
     ORDER BY next_attempt_at
     LIMIT :batch
       FOR UPDATE SKIP LOCKED
    """
)


class PrincipalUnavailableError(RuntimeError):
    """The system principal's row is inactive or gone. A job that proceeded with it
    would run every statement against a claim that filters to nothing and report a
    clean zero (GAP-026's exact failure, one layer down: FS-002a EC-9)."""


_PRINCIPAL = text(
    "SELECT is_active AND deleted_at IS NULL FROM app_user WHERE id = CAST(:id AS uuid)"
)


async def enter_as_principal(session: AsyncSession, settings: Settings) -> None:
    """FS-002 5.6, in the same order as get_db: re-validate the principal as the
    owner, set the claim, then switch into app_role. Raises rather than proceeding
    with an unusable claim."""
    ok = (await session.execute(_PRINCIPAL, {"id": settings.system_user_id})).scalar_one_or_none()
    if not ok:
        raise PrincipalUnavailableError(
            f"system principal {settings.system_user_id} is missing, inactive or deleted; "
            "run migration 005 or scripts/seed_demo.py")
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": settings.system_user_id},
    )
    await enter_role(session, settings.db_app_role)


async def outbox_drain(ctx: dict[str, Any], *, batch: int = 50) -> int:
    """Send every message that is due. Returns how many were handled.

    One transaction for the whole batch, so a crash mid-batch redelivers rather
    than losing. That is at-least-once, deliberately: for an OTP a duplicate SMS
    is a nuisance and a lost one is a support call.
    """
    settings = get_settings()
    handled = 0

    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        rows = (await session.execute(_CLAIM_DUE, {"batch": batch})).all()

        for row in rows:
            handled += 1
            try:
                body = render(row.template_key, dict(row.payload))
            except UnknownTemplateError:
                # A row the worker cannot render is dead on arrival: the database
                # function that wrote it may be a release ahead of this worker.
                # Retrying cannot help, so it goes straight to dead rather than
                # spending five attempts, and it never delivers a half-rendered
                # message to a farmer.
                await _dead(session, row.id, "unknown template")
                log.error("outbox.unknown_template", template=row.template_key)
                continue

            try:
                provider_id = await _send(row.channel, row.recipient, body, settings)
            except Exception as exc:  # any provider error is a retry, not a crash
                await _retry(session, row.id, row.attempts, str(exc)[:500])
                continue

            await session.execute(
                text("UPDATE notification_outbox SET state = 'sent', sent_at = now(), "
                     "provider_msg_id = :p, error = NULL WHERE id = :i"),
                {"p": provider_id, "i": row.id},
            )

    if handled:
        log.info("outbox.drained", handled=handled)
    return handled


async def _send(channel: str, recipient: str, body: str, settings: Any) -> str:
    """The provider seam.

    **The body is never logged.** It contains the OTP, and rule 8 puts the code
    out of responses, logs and errors alike - a mock provider that prints it would
    put every code into the container logs, which is the cheapest possible way to
    break that rule.
    """
    if settings.sms_provider == "mock" and settings.whatsapp_provider == "mock":
        log.info("outbox.mock_send", channel=channel, recipient=_mask(recipient),
                 chars=len(body))
        return f"mock-{datetime.now(UTC).timestamp():.0f}"

    # 11za for WhatsApp and MSG91 for SMS are Phase 2 adapters
    # (Build-Plan.md section 3). Until one exists, a non-mock configuration must
    # fail loudly rather than silently drop messages that a request already
    # promised to send.
    raise NotImplementedError(f"no adapter for channel {channel}")


def _mask(recipient: str) -> str:
    """Enough to correlate a delivery failure, not enough to be a phone list."""
    return f"{recipient[:4]}…{recipient[-2:]}" if len(recipient) > 6 else "…"


async def _retry(session: Any, row_id: Any, attempts: int, error: str) -> None:
    nxt = attempts + 1
    if nxt >= MAX_ATTEMPTS:
        await _dead(session, row_id, error)
        return
    await session.execute(
        text("UPDATE notification_outbox SET attempts = :a, error = :e, "
             "next_attempt_at = now() + make_interval(secs => :s) WHERE id = :i"),
        {"a": nxt, "e": error, "s": BACKOFF_SECONDS[nxt], "i": row_id},
    )


async def _dead(session: Any, row_id: Any, error: str) -> None:
    """`dead` rather than deleted. A message that never arrived is a support
    question, and the row is the only evidence of what was attempted."""
    await session.execute(
        text("UPDATE notification_outbox SET state = 'dead', error = :e WHERE id = :i"),
        {"e": error, "i": row_id},
    )


async def purge_expired_sessions(ctx: dict[str, Any]) -> int:
    """EC-15. `session` and `login_attempt` hold IP addresses against named
    identifiers, which is personal data under DPDP, and every other table in this
    system already has a retention answer.

    Both halves of `session` are covered - revoked and expired - which is why
    there are two partial indexes rather than one: an index predicated on
    `revoked_at IS NULL` excludes exactly the revoked rows it would need to find.
    """
    settings = get_settings()
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        sessions = (await session.execute(
            text("DELETE FROM session WHERE (revoked_at IS NOT NULL AND revoked_at < :cut) "
                 "OR (revoked_at IS NULL AND expires_at < :cut)"),
            {"cut": datetime.now(UTC) - settings.session_retention},
        )).rowcount
        attempts = (await session.execute(
            text("DELETE FROM login_attempt WHERE attempted_at < :cut"),
            {"cut": datetime.now(UTC) - settings.login_attempt_retention},
        )).rowcount
        idem = (await session.execute(
            text("DELETE FROM idempotency_record WHERE created_at < :cut"),
            {"cut": datetime.now(UTC) - settings.idempotency_retention},
        )).rowcount

    log.info("retention.purged", sessions=sessions, attempts=attempts, idempotency=idem)
    return int(sessions) + int(attempts) + int(idem)
