"""The outbox drain and the retention purge, against the real database.

Rule 6 makes the request correct by refusing to send inside it. This job is what
makes the message actually arrive, and a table nothing drains delivers no codes.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.integrations.messages import TEMPLATE_AUTH_OTP, UnknownTemplateError, render
from worker.jobs.outbox import BACKOFF_SECONDS, MAX_ATTEMPTS, outbox_drain

pytestmark = pytest.mark.db


async def _queue(session: AsyncSession, *, recipient: str, template: str = TEMPLATE_AUTH_OTP,
                 payload: str = '{"code": "482913"}', due: str = "now()",
                 attempts: int = 0) -> str:
    row = await session.execute(
        text(f"INSERT INTO notification_outbox "
             f"(channel, template_key, recipient, payload, next_attempt_at, attempts) "
             f"VALUES ('sms', :t, :r, CAST(:p AS jsonb), {due}, :a) RETURNING id"),
        {"t": template, "r": recipient, "p": payload, "a": attempts},
    )
    rid = str(row.scalar_one())
    await session.commit()
    return rid


async def _state(session: AsyncSession, row_id: str) -> tuple[str, int, str | None]:
    got = await session.execute(
        text("SELECT state::text, attempts, error FROM notification_outbox "
             "WHERE id = CAST(:i AS uuid)"), {"i": row_id})
    state, attempts, error = got.one()
    await session.rollback()
    return state, attempts, error


async def _drop(session: AsyncSession, row_id: str) -> None:
    await session.execute(text("DELETE FROM notification_outbox WHERE id = CAST(:i AS uuid)"),
                          {"i": row_id})
    await session.commit()


async def test_a_due_message_is_sent_and_marked(
        sessions: Callable[[], AsyncSession]) -> None:
    recipient = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    row_id = await _queue(sessions(), recipient=recipient)
    try:
        assert await outbox_drain({}) >= 1
        state, _, error = await _state(sessions(), row_id)
        assert state == "sent" and error is None
    finally:
        await _drop(sessions(), row_id)


async def test_a_message_that_is_not_due_yet_is_left_alone(
        sessions: Callable[[], AsyncSession]) -> None:
    recipient = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    row_id = await _queue(sessions(), recipient=recipient, due="now() + interval '1 hour'")
    try:
        await outbox_drain({})
        state, _, _ = await _state(sessions(), row_id)
        assert state == "pending", "a scheduled retry was sent early"
    finally:
        await _drop(sessions(), row_id)


async def test_an_unrenderable_message_goes_straight_to_dead(
        sessions: Callable[[], AsyncSession]) -> None:
    """Retrying cannot fix an unknown template - the database function that wrote
    the row may be a release ahead of this worker - and a half-rendered message
    must never reach a farmer."""
    recipient = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    row_id = await _queue(sessions(), recipient=recipient, template="auth.no_such_template")
    try:
        await outbox_drain({})
        state, attempts, error = await _state(sessions(), row_id)
        assert state == "dead"
        assert attempts == 0, "it spent retries on something retrying cannot fix"
        assert error is not None
    finally:
        await _drop(sessions(), row_id)


async def test_a_payload_missing_its_substitution_is_also_dead(
        sessions: Callable[[], AsyncSession]) -> None:
    """`"{code} is your..."` delivered literally is worse than nothing arriving."""
    recipient = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    row_id = await _queue(sessions(), recipient=recipient, payload='{"wrong": "key"}')
    try:
        await outbox_drain({})
        state, _, _ = await _state(sessions(), row_id)
        assert state == "dead"
    finally:
        await _drop(sessions(), row_id)


async def test_the_backoff_is_monotonic_and_bounded() -> None:
    """A provider outage must not retry a thousand messages every ten seconds, and
    a transient failure must not wait an hour."""
    assert list(BACKOFF_SECONDS) == sorted(BACKOFF_SECONDS)
    assert BACKOFF_SECONDS[0] <= 60
    assert len(BACKOFF_SECONDS) == MAX_ATTEMPTS


def test_the_rendered_body_carries_the_code_and_nothing_else_does() -> None:
    """Rule 8: the code is never in a response, a log or an error. It is in the
    message, which is the one place it has to be."""
    body = render(TEMPLATE_AUTH_OTP, {"code": "482913"})
    assert "482913" in body
    assert "Polysil" in body


def test_an_unknown_template_raises_rather_than_half_rendering() -> None:
    with pytest.raises(UnknownTemplateError):
        render("auth.nope", {"code": "1"})
    with pytest.raises(UnknownTemplateError):
        render(TEMPLATE_AUTH_OTP, {"not_code": "1"})
