"""Drain `notification_outbox`, and purge what has aged out.

Rule 6 says outbound messages go to the outbox and are never sent inside a
request. That makes the request correct and delivers nothing on its own - a table
nothing drains delivers no codes, which is why FS-001 carries this job rather than
leaving it to the notifications module (GAP-022).

**This is the second place in the system that opens a transaction**, and the only
one outside `api/deps.py` (rule 2). It runs as the system principal (FS-002 5.6):
the claim and the role are set per transaction, because nothing survives a commit
through PgBouncer, and the principal's row is re-validated once per drain.

FS-007 shaped the drain around a real provider:

* **one row per transaction** (rule 7): claim with `LIMIT 1 FOR UPDATE SKIP
  LOCKED`, send, mark, commit, for as long as the drain's budget lasts. Fifty
  locks from one statement do not survive the first commit, so that shape and a
  per-row commit cannot coexist (plan review B-2). A crash resends at most one
  message.
* **a transient failure charges nothing** (rule 8): the row is rescheduled a
  minute out with `attempts` unchanged, and the third inside a window opens a
  shared breaker that every drain honours. Only the provider's refusal of a
  specific message spends one of its five attempts.
* **every template has a maximum age** (rule 4), a code's row is retired when a
  newer code exists (rule 1a), an acknowledgement is withdrawn with its lead and
  sent once a day per number under a per-number lock (rules 10a, 10b), and a
  channel with no adapter is dead on claim (rule 14). None of those spends an
  attempt or a message.
* **the payload is cleared when a row leaves `pending`** (rule 12), except in a
  local box with the mock provider, where the outbox is the developer's phone.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import Settings, get_settings
from api.db.session import async_session_factory, enter_role
from api.integrations import cache
from api.integrations.messages import (
    TEMPLATE_AUTH_OTP,
    TEMPLATE_LEAD_ACK,
    TEMPLATE_LEAD_VERIFY,
    TEMPLATES,
    UnknownTemplateError,
    max_age,
    template_values,
)
from api.integrations.whatsapp import get_provider
from api.integrations.whatsapp.provider import MessageProvider, OutboundMessage, Outcome

log = structlog.get_logger()

# Exponential, capped. A provider outage should not retry a thousand messages
# every ten seconds, and a transient failure should not wait an hour. Indexed by
# the attempt about to be scheduled (attempts + 1), so the charged waits are 60 s,
# 300 s, 1800 s and 3600 s and the fifth refusal is dead (FS-007 section 3).
BACKOFF_SECONDS: tuple[int, ...] = (10, 60, 300, 1800, 3600)
MAX_ATTEMPTS = len(BACKOFF_SECONDS)

# Rule 8: an uncharged reschedule, and the breaker's window is the same minute.
TRANSIENT_DELAY = timedelta(seconds=60)
# Rule 17: more dead rows than this in one drain is an error log.
DEAD_BURST = 10
# Rule 10b: the acknowledgement's per-number lock. 1 is the OTP by number, 2 a
# closure tree, 3 a session family, 4 the handover and the administrator floor.
ACK_LOCK_NAMESPACE = 5

# FOR UPDATE SKIP LOCKED is what lets more than one worker run without two of them
# sending the same message. The partial index on (next_attempt_at) WHERE
# state = 'pending' is what makes this a lookup rather than a scan.
_CLAIM_ONE = text(
    """
    SELECT id, channel::text AS channel, template_key, recipient, payload, attempts,
           created_at, EXTRACT(EPOCH FROM (now() - created_at)) AS age_seconds
      FROM notification_outbox
     WHERE state = 'pending'
       AND next_attempt_at <= now()
     ORDER BY next_attempt_at
     LIMIT 1
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


async def assert_principal(session: AsyncSession, settings: Settings) -> None:
    """Re-validate the principal as the owner. Raises rather than proceeding with
    an unusable claim."""
    ok = (await session.execute(_PRINCIPAL, {"id": settings.system_user_id})).scalar_one_or_none()
    if not ok:
        raise PrincipalUnavailableError(
            f"system principal {settings.system_user_id} is missing, inactive or deleted; "
            "run migration 005 or scripts/seed_demo.py")


async def claim_as_principal(session: AsyncSession, settings: Settings) -> None:
    """What get_db does: the claim, then app_role, transaction-local."""
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": settings.system_user_id},
    )
    await enter_role(session, settings.db_app_role)


async def enter_as_principal(session: AsyncSession, settings: Settings) -> None:
    """FS-002 5.6, in the same order as get_db: re-validate, claim, switch."""
    await assert_principal(session, settings)
    await claim_as_principal(session, settings)


async def outbox_drain(ctx: dict[str, Any], *, batch: int | None = None) -> int:
    """Send every message that is due, one row per transaction, until the budget
    runs out. Returns how many rows were handled.

    `batch` bounds the rows for a caller that wants fewer (tests); the budget is
    the bound in production.
    """
    settings = get_settings()
    provider: MessageProvider = ctx.get("provider") or get_provider(settings, ctx.get("http"))

    if await cache.breaker_is_open():
        log.info("outbox.breaker_open")
        return 0

    async with async_session_factory() as session:
        await assert_principal(session, settings)

    started = time.monotonic()
    handled = dead = 0
    while (time.monotonic() - started) < settings.outbox_drain_budget \
            and (batch is None or handled < batch):
        if handled and await cache.breaker_is_open():
            break
        outcome: str | None = None
        row_id: Any = None
        try:
            async with async_session_factory() as session, session.begin():
                await claim_as_principal(session, settings)
                row = (await session.execute(_CLAIM_ONE)).one_or_none()
                if row is not None:
                    handled += 1
                    row_id = row.id
                    outcome = await _handle(session, row, provider, settings)
        except Exception as exc:
            # One row never stops the drain. Its transaction rolled back, so it
            # would be the next claim again and again (code review F-3, executed:
            # a raising provider left every later row pending, tick after tick).
            # Charged, in its own transaction, then on to the next row.
            log.error("outbox.row_failed", kind=type(exc).__name__, row=str(row_id))
            if row_id is None:
                raise
            await _charge_after_error(row_id, type(exc).__name__, settings)
            outcome = "retry"
        if outcome is None:
            break
        if outcome == "dead":
            dead += 1
        # After the commit only, so a Redis failure never loses a send result.
        if outcome == "transient" and await cache.breaker_note_transient():
            log.error("outbox.breaker_opened", handled=handled)
            break

    if dead > DEAD_BURST:
        log.error("outbox.dead_burst", dead=dead, handled=handled)
    if handled:
        log.info("outbox.drained", handled=handled, dead=dead)
    return handled


async def _handle(session: AsyncSession, row: Any, provider: MessageProvider,
                  settings: Settings) -> str:
    """One claimed row. Returns sent, dead, transient or retry."""
    key: str = row.template_key
    payload: dict[str, object] = dict(row.payload)

    if key not in TEMPLATES:
        # A row the worker cannot render is dead on arrival: the database function
        # that wrote it may be a release ahead of this worker. Retrying cannot
        # help, and it never delivers a half-rendered message to a farmer.
        await _dead(session, row.id, "unknown template")
        log.error("outbox.unknown_template", template=key)
        return "dead"
    if row.channel != "whatsapp":
        await _dead(session, row.id, f"no adapter for channel {row.channel}")
        return "dead"

    limit = max_age(key, settings)
    # The age is the database's arithmetic (code review F-6): every other time in
    # the drain is the database clock, and a minute of skew between this box and
    # the database would kill every code or send them expired, silently.
    if limit is not None and float(row.age_seconds) > limit.total_seconds():
        await _dead(session, row.id, "too old to send")
        return "dead"

    if key in (TEMPLATE_AUTH_OTP, TEMPLATE_LEAD_VERIFY):
        # only the newest code of its kind can arrive (FS-007 rule 1a, FS-003a EC-5)
        newer = (await session.execute(text(
            "SELECT EXISTS (SELECT 1 FROM notification_outbox o WHERE o.template_key = :k "
            "AND o.recipient = :r AND o.created_at > :c AND o.id <> :i)"),
            {"k": key, "r": row.recipient, "c": row.created_at, "i": row.id})).scalar_one()
        if newer:
            await _dead(session, row.id, "superseded")
            return "dead"

    if key == TEMPLATE_LEAD_ACK:
        await session.execute(text("SELECT pg_advisory_xact_lock(:ns, hashtext(:r))"),
                              {"ns": ACK_LOCK_NAMESPACE, "r": row.recipient})
        withdrawn = (await session.execute(
            text("SELECT outbox_lead_withdrawn(CAST(:n AS citext))"),
            {"n": str(payload.get("inquiry_no", ""))})).scalar_one()
        if withdrawn:
            await _dead(session, row.id, "lead withdrawn")
            return "dead"
        duplicate = (await session.execute(text(
            "SELECT EXISTS (SELECT 1 FROM notification_outbox o WHERE o.template_key = 'lead_ack' "
            "AND o.recipient = :r AND o.state = 'sent' "
            "AND o.sent_at > now() - interval '24 hours' AND o.id <> :i)"),
            {"r": row.recipient, "i": row.id})).scalar_one()
        if duplicate:
            await _dead(session, row.id, "duplicate acknowledgement")
            return "dead"

    try:
        template_values(key, payload)
    except UnknownTemplateError as exc:
        await _dead(session, row.id, f"unrenderable: {exc}")
        return "dead"

    result = await provider.send(OutboundMessage(
        channel=row.channel, recipient=row.recipient, template_key=key,
        payload=payload, reference=str(row.id)))

    if result.outcome is Outcome.ACCEPTED:
        keep = settings.environment == "local" and settings.whatsapp_provider == "mock"
        await session.execute(
            text("UPDATE notification_outbox SET state = 'sent', sent_at = now(), "
                 "provider_msg_id = :p, error = NULL, "
                 "payload = CASE WHEN :keep THEN payload ELSE '{}'::jsonb END WHERE id = :i"),
            {"p": result.provider_msg_id, "keep": keep, "i": row.id},
        )
        return "sent"
    if result.outcome is Outcome.TRANSIENT:
        # GAP-073: a timeout after the provider accepted is resent once the breaker
        # clears; at-least-once, as FS-001 chose for the code.
        await session.execute(
            text("UPDATE notification_outbox SET error = :e, "
                 "next_attempt_at = now() + make_interval(secs => :s) WHERE id = :i"),
            {"e": result.error, "s": TRANSIENT_DELAY.total_seconds(), "i": row.id},
        )
        return "transient"
    if result.outcome is Outcome.PERMANENT:
        await _dead(session, row.id, result.error or "refused")
        return "dead"
    return await _retry(session, row.id, row.attempts, result.error or "refused")


async def _charge_after_error(row_id: Any, error: str, settings: Settings) -> None:
    """The row whose handling raised: its own transaction, the same charge a
    refusal takes, dead at the fifth. Only while the row is still pending: the
    failed transaction's lock is gone, another drain may have sent the row
    meanwhile, and a charge by id alone would turn a sent row dead (cross-vendor
    review of the code, P2, reproduced)."""
    async with async_session_factory() as session, session.begin():
        await claim_as_principal(session, settings)
        await session.execute(
            text("UPDATE notification_outbox SET attempts = attempts + 1, error = :e, "
                 "state = CASE WHEN attempts + 1 >= :m THEN 'dead' ELSE state END, "
                 "payload = CASE WHEN attempts + 1 >= :m THEN '{}'::jsonb ELSE payload END, "
                 "next_attempt_at = now() + make_interval(secs => :s) "
                 "WHERE id = :i AND state = 'pending'"),
            {"e": error[:500], "m": MAX_ATTEMPTS, "s": BACKOFF_SECONDS[1], "i": row_id},
        )


async def _retry(session: Any, row_id: Any, attempts: int, error: str) -> str:
    nxt = attempts + 1
    if nxt >= MAX_ATTEMPTS:
        await _dead(session, row_id, error)
        return "dead"
    await session.execute(
        text("UPDATE notification_outbox SET attempts = :a, error = :e, "
             "next_attempt_at = now() + make_interval(secs => :s) WHERE id = :i"),
        {"a": nxt, "e": error, "s": BACKOFF_SECONDS[nxt], "i": row_id},
    )
    return "retry"


async def _dead(session: Any, row_id: Any, error: str) -> None:
    """`dead` rather than deleted. A message that never arrived is a support
    question, and the row is the only evidence of what was attempted. The payload
    goes: a code or a farmer's name has no business outliving the attempt."""
    await session.execute(
        text("UPDATE notification_outbox SET state = 'dead', error = :e, "
             "payload = '{}'::jsonb WHERE id = :i"),
        {"e": error[:500], "i": row_id},
    )


async def purge_expired_sessions(ctx: dict[str, Any]) -> int:
    """EC-15. `session` and `login_attempt` hold IP addresses against named
    identifiers, which is personal data under DPDP, and every other table in this
    system already has a retention answer.

    Both halves of `session` are covered - revoked and expired - which is why
    there are two partial indexes rather than one: an index predicated on
    `revoked_at IS NULL` excludes exactly the revoked rows it would need to find.

    FS-007 rule 12 adds the outbox: rows that are not pending, past the retention.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        sessions = (await session.execute(
            text("DELETE FROM session WHERE (revoked_at IS NOT NULL AND revoked_at < :cut) "
                 "OR (revoked_at IS NULL AND expires_at < :cut)"),
            {"cut": now - settings.session_retention},
        )).rowcount
        attempts = (await session.execute(
            text("DELETE FROM login_attempt WHERE attempted_at < :cut"),
            {"cut": now - settings.login_attempt_retention},
        )).rowcount
        idem = (await session.execute(
            text("DELETE FROM idempotency_record WHERE created_at < :cut"),
            {"cut": now - settings.idempotency_retention},
        )).rowcount
        outbox = (await session.execute(
            text("DELETE FROM notification_outbox WHERE state <> 'pending' "
                 "AND created_at < :cut"),
            {"cut": now - settings.outbox_retention},
        )).rowcount
        # FS-003a: the public form's codes hold a mobile and an address; a definer
        # deletes them, because no policy admits either role to the table
        codes = (await session.execute(
            text("SELECT lead_intake_purge(:cut)"),
            {"cut": now - settings.public_lead_code_retention},
        )).scalar_one()

    log.info("retention.purged", sessions=sessions, attempts=attempts, idempotency=idem,
             outbox=outbox, lead_codes=codes)
    return int(sessions) + int(attempts) + int(idem) + int(outbox) + int(codes)
