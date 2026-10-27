"""Email notices (FS-078): collect, the morning summary, and the email drain.

Separate from `outbox_drain` on purpose:

* it claims only `channel = 'email'`, notice rows before summary rows, each on its
  own partial index (plan review SF-1);
* its breaker and drain lock have their own Redis keys (`email:*`), so an SMTP
  outage never pauses sign-in codes (EC-13);
* its own maximum ages: a notice row 24 hours, a summary until 12:00 IST that day
  (EC-6);
* the address and the notices are resolved at send, never frozen at queue time
  (EC-1, EC-3). "already read", "recipient no longer eligible" and "email off" end
  a row dead without counting toward the dead-burst alert (plan review SF-3).

Under `EMAIL_PROVIDER=none` nothing is collected, and the drain ends any pending
email row "email off" so no payload waits forever (EC-14, EC-15).
"""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import datetime as dt
import secrets
import time
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import Settings, get_settings
from api.db.session import async_session_factory
from api.integrations import cache
from api.integrations.email import get_email_provider
from api.integrations.email import render as email_render
from api.integrations.email.provider import Email, EmailProvider, parse_address
from api.integrations.whatsapp.provider import Outcome
from worker.jobs.outbox import (
    DEAD_BURST,
    TRANSIENT_DELAY,
    UNCERTAIN_PREFIX,
    _charge_after_error,
    _dead,
    _retry,
    assert_principal,
    claim_as_principal,
    enter_as_principal,
)

log = structlog.get_logger()

IST = ZoneInfo("Asia/Kolkata")
PREFIX = "email"
TEMPLATE_NOTICES = "email_notices"
TEMPLATE_MORNING = "email_morning"
COLLECT_LIMIT = 50
NOTICE_MAX_AGE = timedelta(hours=24)
MORNING_UNTIL = dt.time(12, 0)
# the cron fires 07:30 to 11:20 IST; only 08:00 to 11:00 counts (SF-7)
MORNING_FROM, MORNING_LAST = dt.time(8, 0), dt.time(11, 0)
# ends a row dead, but is an answer, not a failure (plan review SF-3)
NOT_FAILURES = frozenset({"already read", "recipient no longer eligible", "email off"})

_CLAIM = text(
    """
    SELECT id, template_key, recipient, payload, attempts,
           EXTRACT(EPOCH FROM (now() - created_at)) AS age_seconds, now() AS db_now
      FROM notification_outbox
     WHERE state = 'pending' AND channel = 'email' AND template_key = :k
       AND next_attempt_at <= now()
     ORDER BY next_attempt_at
     LIMIT 1
       FOR UPDATE SKIP LOCKED
    """
)


def _now() -> dt.datetime:
    return dt.datetime.now(IST)


def _provider(ctx: dict[str, Any], settings: Settings) -> EmailProvider | None:
    if "email_provider" in ctx:
        provider: EmailProvider | None = ctx["email_provider"]
        return provider
    return get_email_provider(settings)


async def email_collect(ctx: dict[str, Any]) -> int:
    """Every five minutes: unread notices 10 minutes to 24 hours old become one
    outbox row per person. The definer does the choosing and the locking (B-2)."""
    settings = get_settings()
    if _provider(ctx, settings) is None:
        return 0
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        n = int((await session.execute(text("SELECT email_notice_collect(:n)"),
                                       {"n": COLLECT_LIMIT})).scalar_one())
    if n:
        log.info("email.collected", rows=n)
    return n


async def email_morning(ctx: dict[str, Any], *, day: dt.date | None = None) -> int:
    """The morning summary. Runs every 10 minutes from 08:00 to 11:00 IST, Monday to
    Saturday; the keyed table makes every run after the first a no-op (SF-7)."""
    settings = get_settings()
    if _provider(ctx, settings) is None:
        return 0
    if day is None and not MORNING_FROM <= _now().astimezone(IST).time() <= MORNING_LAST:
        return 0
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        n = int((await session.execute(text("SELECT email_morning_collect(CAST(:d AS date))"),
                                       {"d": day})).scalar_one())
    if n:
        log.info("email.morning_collected", rows=n)
    return n


async def email_drain(ctx: dict[str, Any], *, batch: int | None = None) -> int:
    """Send due email rows, one per transaction, until the budget runs out. The
    unbounded (cron) call holds the email drain lock; a bounded call skips it."""
    if batch is not None:
        return await _drain(ctx, batch=batch)
    settings = get_settings()
    ttl = timedelta(seconds=settings.outbox_drain_budget + settings.smtp_send_deadline + 15)
    token = secrets.token_hex(8)
    if not await cache.drain_lock_take(token, ttl, PREFIX):
        log.info("email.drain_skipped")
        return 0
    try:
        return await _drain(ctx, batch=None)
    finally:
        await cache.drain_lock_release(token, PREFIX)


async def _switch_off(settings: Settings) -> int:
    """`none`: every pending email row ends "email off" (EC-14)."""
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        n = len((await session.execute(text(
            "UPDATE notification_outbox SET state = 'dead', error = 'email off', payload = '{}'::jsonb "
            "WHERE state = 'pending' AND channel = 'email' RETURNING id"))).all())
    if n:
        log.info("email.switched_off", rows=n)
    return int(n)


async def _drain(ctx: dict[str, Any], *, batch: int | None) -> int:
    settings = get_settings()
    provider = _provider(ctx, settings)
    if provider is None:
        return await _switch_off(settings)
    if await cache.breaker_is_open(PREFIX):
        log.info("email.breaker_open")
        return 0
    async with async_session_factory() as session:
        await assert_principal(session, settings)

    started = time.monotonic()
    handled = dead = 0
    while (time.monotonic() - started) < settings.outbox_drain_budget \
            and (batch is None or handled < batch):
        if handled and await cache.breaker_is_open(PREFIX):
            break
        outcome: str | None = None
        row_id: Any = None
        try:
            async with async_session_factory() as session, session.begin():
                await claim_as_principal(session, settings)
                row = None
                # notices first: they are time-sensitive, the summary is not (EC-28)
                for key in (TEMPLATE_NOTICES, TEMPLATE_MORNING):
                    row = (await session.execute(_CLAIM, {"k": key})).one_or_none()
                    if row is not None:
                        break
                if row is not None:
                    handled += 1
                    row_id = row.id
                    outcome = await _handle(session, row, provider, settings)
        except Exception as exc:
            log.error("email.row_failed", kind=type(exc).__name__, row=str(row_id))
            if row_id is None:
                raise
            await _charge_after_error(row_id, type(exc).__name__, settings)
            outcome = "retry"
        if outcome is None:
            break
        if outcome in ("dead", "uncertain"):
            dead += 1
        if outcome in ("transient", "uncertain") and await cache.breaker_note_transient(PREFIX):
            log.error("email.breaker_opened", handled=handled)
            break

    if dead > DEAD_BURST:
        log.error("email.dead_burst", dead=dead, handled=handled)
    if handled:
        log.info("email.drained", handled=handled, dead=dead)
    return handled


async def _answer(session: AsyncSession, row_id: Any, reason: str) -> str:
    """A row that ends without a send, and is not a failure (plan review SF-3)."""
    assert reason in NOT_FAILURES, reason
    await _dead(session, row_id, reason)
    return "answered"


async def _handle(session: AsyncSession, row: Any, provider: EmailProvider,
                  settings: Settings) -> str:
    payload: dict[str, Any] = dict(row.payload)
    base = settings.public_web_url
    if row.template_key == TEMPLATE_NOTICES:
        if float(row.age_seconds) > NOTICE_MAX_AGE.total_seconds():
            await _dead(session, row.id, "too old to send")
            return "dead"
        ids = [str(x) for x in payload.get("ids") or []]
        found = (await session.execute(
            text("SELECT * FROM email_notice_resolve(CAST(:u AS uuid), CAST(:ids AS uuid[]))"),
            {"u": row.recipient, "ids": ids})).all()
        if not found:
            return await _answer(session, row.id, "recipient no longer eligible")
        unread = [r for r in found if r.notice_id is not None]
        if not unread:
            return await _answer(session, row.id, "already read")
        first = found[0]
        # the queued notices that were never listed still count (EC-9)
        total = len(unread) + max(int(payload.get("total") or len(ids)) - len(ids), 0)
        content = email_render.notices(
            base, first.full_name, first.user_type,
            [email_render.Notice(r.title, r.created_at, r.resource_type,
                                 str(r.resource_id) if r.resource_id else None) for r in unread],
            total)
        address, name = first.email, first.full_name
    elif row.template_key == TEMPLATE_MORNING:
        day = dt.date.fromisoformat(str(payload.get("day")))
        if row.db_now.astimezone(IST) >= dt.datetime.combine(day, MORNING_UNTIL, tzinfo=IST):
            await _dead(session, row.id, "too old to send")
            return "dead"
        found = (await session.execute(
            text("SELECT * FROM email_morning_resolve(CAST(:u AS uuid))"),
            {"u": row.recipient})).all()
        if not found:
            return await _answer(session, row.id, "recipient no longer eligible")
        first = found[0]
        content = email_render.morning(base, first.full_name, first.user_type,
                                       int(payload.get("due_today") or 0),
                                       int(payload.get("overdue") or 0))
        address, name = first.email, first.full_name
    else:
        await _dead(session, row.id, "unknown template")
        log.error("email.unknown_template", template=row.template_key)
        return "dead"

    to = parse_address(address)
    if to is None:
        await _dead(session, row.id, "not one email address")
        return "dead"
    result = await provider.send(Email(to=to, to_name=name, subject=content.subject,
                                       text=content.text, html=content.html,
                                       reference=str(row.id)))
    if result.outcome is Outcome.ACCEPTED:
        keep = settings.environment == "local" and settings.email_provider == "mock"
        await session.execute(
            text("UPDATE notification_outbox SET state = 'sent', sent_at = now(), "
                 "provider_msg_id = :p, error = NULL, "
                 "payload = CASE WHEN :keep THEN payload ELSE '{}'::jsonb END WHERE id = :i"),
            {"p": result.provider_msg_id, "keep": keep, "i": row.id})
        return "sent"
    if result.outcome is Outcome.UNCERTAIN:
        # never resent: it may have arrived (EC-16)
        await _dead(session, row.id, f"{UNCERTAIN_PREFIX}{result.error}")
        return "uncertain"
    if result.outcome is Outcome.TRANSIENT:
        await session.execute(
            text("UPDATE notification_outbox SET error = :e, "
                 "next_attempt_at = now() + make_interval(secs => :s) WHERE id = :i"),
            {"e": result.error, "s": TRANSIENT_DELAY.total_seconds(), "i": row.id})
        return "transient"
    if result.outcome is Outcome.PERMANENT:
        await _dead(session, row.id, result.error or "refused")
        return "dead"
    return await _retry(session, row.id, row.attempts, result.error or "refused")
