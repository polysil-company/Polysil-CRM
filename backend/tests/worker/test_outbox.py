"""The outbox drain and the retention purge, against the real database (FS-007
section 10, the worker row).

Rule 6 makes the request correct by refusing to send inside it. This job is what
makes the message actually arrive, and a table nothing drains delivers no codes.
Every provider here is a fake that answers what the test says; the real adapter
is tested against a fake transport in tests/integrations, and nothing in the
suite sends.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.integrations import cache
from api.integrations.messages import (
    TEMPLATE_AUTH_OTP,
    TEMPLATE_LEAD_ACK,
    TEMPLATE_ORDER_CONFIRMED,
    TEMPLATES,
    UnknownTemplateError,
    render,
)
from api.integrations.whatsapp.provider import OutboundMessage, Outcome, ProviderResult
from worker.jobs.outbox import (
    BACKOFF_SECONDS,
    MAX_ATTEMPTS,
    UNCERTAIN_PREFIX,
    _charge_after_error,
    outbox_drain,
    purge_expired_sessions,
)

pytestmark = pytest.mark.db

ACCEPTED = ProviderResult(Outcome.ACCEPTED, "fake-1")
TRANSIENT = ProviderResult(Outcome.TRANSIENT, None, "ReadTimeout")
UNCERTAIN = ProviderResult(Outcome.UNCERTAIN, None, "ReadTimeout")
REFUSED = ProviderResult(Outcome.REFUSED, None, "Something odd")
PERMANENT = ProviderResult(Outcome.PERMANENT, None, "Invalid phone number")


class FakeProvider:
    """Answers the given results in order (the last repeats). `gate` holds every
    send until the test releases it; `called` is set when a send starts."""

    def __init__(self, *results: ProviderResult, gate: asyncio.Event | None = None,
                 delay: float = 0.0) -> None:
        self.results = list(results) or [ACCEPTED]
        self.gate = gate
        self.delay = delay
        self.calls: list[OutboundMessage] = []
        self.called = asyncio.Event()

    async def send(self, msg: OutboundMessage) -> ProviderResult:
        self.calls.append(msg)
        self.called.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.gate is not None:
            await self.gate.wait()
        i = min(len(self.calls), len(self.results)) - 1
        return self.results[i]

    async def list_templates(self) -> list[dict[str, object]]:
        return []


def _mobile() -> str:
    return "9199" + f"{uuid.uuid4().int % 10**8:08d}"


@pytest.fixture(autouse=True)
async def _no_backlog(sessions: Callable[[], AsyncSession]) -> None:
    """The development database holds pending rows other tests and the API left,
    and a drain handles the oldest due row first. A test that counts provider
    calls, or gates a send and waits for it, must start from an empty due queue:
    whatever is due is handled by an accepting fake before the test queues its own
    rows (the old acknowledgements die of age without a send). Queueing first and
    draining after sent the test's own rows and hung the gated wait for three
    hours."""
    for _ in range(60):
        if await outbox_drain({"provider": FakeProvider(ACCEPTED)}) == 0:
            return


async def _queue(session: AsyncSession, *, recipient: str, template: str = TEMPLATE_AUTH_OTP,
                 payload: str = '{"code": "482913"}', due: str = "now()", attempts: int = 0,
                 channel: str = "whatsapp", age: timedelta | None = None,
                 state: str = "pending", sent_at: str = "NULL") -> str:
    created = "now()" if age is None else f"now() - interval '{int(age.total_seconds())} seconds'"
    row = await session.execute(
        text(f"INSERT INTO notification_outbox "
             f"(channel, template_key, recipient, payload, next_attempt_at, attempts, created_at, "
             f"state, sent_at) VALUES (CAST(:c AS notification_channel), :t, :r, "
             f"CAST(:p AS jsonb), "
             f"{due}, :a, {created}, CAST(:s AS notification_state), {sent_at}) RETURNING id"),
        {"c": channel, "t": template, "r": recipient, "p": payload, "a": attempts, "s": state},
    )
    rid = str(row.scalar_one())
    await session.commit()
    return rid


async def _state(session: AsyncSession, row_id: str) -> tuple[str, int, str | None, str, bool]:
    got = await session.execute(
        text("SELECT state::text, attempts, error, payload::text, "
             "next_attempt_at > now() + interval '30 seconds' "
             "FROM notification_outbox WHERE id = CAST(:i AS uuid)"), {"i": row_id})
    state, attempts, error, payload, later = got.one()
    await session.rollback()
    return state, attempts, error, payload, bool(later)


async def _drop(session: AsyncSession, *row_ids: str) -> None:
    for row_id in row_ids:
        await session.execute(text("DELETE FROM notification_outbox WHERE id = CAST(:i AS uuid)"),
                              {"i": row_id})
    await session.commit()


async def _drain_until(sessions: Callable[[], AsyncSession], row_id: str,
                       provider: FakeProvider | None = None,
                       ) -> tuple[str, int, str | None, str, bool]:
    """The drain takes the oldest due row first and a development database can
    hold a backlog, so drain until this row has left `pending`."""
    ctx: dict[str, object] = {"provider": provider} if provider else {}
    for _ in range(60):
        await outbox_drain(ctx)
        got = await _state(sessions(), row_id)
        if got[0] != "pending":
            return got
    return got


# ── the shape FS-001 left, still true ────────────────────────────────────────

async def test_a_due_message_is_sent_and_marked(sessions: Callable[[], AsyncSession]) -> None:
    """With the mock in a local box the payload stays: the outbox is the
    developer's phone (rule 12's stated exception)."""
    row_id = await _queue(sessions(), recipient=_mobile())
    try:
        state, _, error, payload, _ = await _drain_until(sessions, row_id)
        assert state == "sent" and error is None
        assert '"482913"' in payload
    finally:
        await _drop(sessions(), row_id)


async def test_a_message_that_is_not_due_yet_is_left_alone(
        sessions: Callable[[], AsyncSession]) -> None:
    row_id = await _queue(sessions(), recipient=_mobile(), due="now() + interval '1 hour'")
    try:
        await outbox_drain({})
        state, *_ = await _state(sessions(), row_id)
        assert state == "pending", "a scheduled retry was sent early"
    finally:
        await _drop(sessions(), row_id)


async def test_an_unrenderable_message_goes_straight_to_dead(
        sessions: Callable[[], AsyncSession]) -> None:
    """Retrying cannot fix an unknown template - the database function that wrote
    the row may be a release ahead of this worker - and a half-rendered message
    must never reach a farmer."""
    row_id = await _queue(sessions(), recipient=_mobile(), template="auth.no_such_template")
    try:
        state, attempts, error, payload, _ = await _drain_until(sessions, row_id)
        assert state == "dead" and error == "unknown template" and payload == "{}"
        assert attempts == 0, "it spent retries on something retrying cannot fix"
    finally:
        await _drop(sessions(), row_id)


async def test_a_payload_missing_its_substitution_is_also_dead(
        sessions: Callable[[], AsyncSession]) -> None:
    row_id = await _queue(sessions(), recipient=_mobile(), payload='{"wrong": "key"}')
    try:
        state, attempts, error, _, _ = await _drain_until(sessions, row_id)
        assert state == "dead" and attempts == 0 and error is not None and "missing" in error
    finally:
        await _drop(sessions(), row_id)


async def test_the_backoff_is_monotonic_and_bounded() -> None:
    assert list(BACKOFF_SECONDS) == sorted(BACKOFF_SECONDS)
    assert BACKOFF_SECONDS[0] <= 60
    assert len(BACKOFF_SECONDS) == MAX_ATTEMPTS


def test_the_rendered_body_carries_the_code_and_nothing_else_does() -> None:
    body = render(TEMPLATE_AUTH_OTP, {"code": "482913"})
    assert "482913" in body
    assert "Polysil" in body


def test_an_unknown_template_raises_rather_than_half_rendering() -> None:
    with pytest.raises(UnknownTemplateError):
        render("auth.nope", {"code": "1"})
    with pytest.raises(UnknownTemplateError):
        render(TEMPLATE_AUTH_OTP, {"not_code": "1"})


# ── FS-007: one row per transaction, the outcomes, the breaker ───────────────

async def test_one_row_per_transaction_so_a_later_failure_keeps_an_earlier_send(
        sessions: Callable[[], AsyncSession]) -> None:
    first = await _queue(sessions(), recipient=_mobile())
    second = await _queue(sessions(), recipient=_mobile())
    provider = FakeProvider(ACCEPTED, TRANSIENT)
    try:
        await cache.breaker_reset()
        got_first = await _drain_until(sessions, first, provider)
        got_second = await _state(sessions(), second)
        assert got_first[0] == "sent"
        state, attempts, error, _, later = got_second
        assert (state, attempts, error, later) == ("pending", 0, "ReadTimeout", True), got_second
    finally:
        await _drop(sessions(), first, second)
        await cache.breaker_reset()


# ── GAP-073: no answer after the request left ────────────────────────────────

ORDER_PAYLOAD = ('{"_template": "polysil_order_confirmed", "party_name": "P", '
                 '"order_no": "SO/GJ/2026-27/00011", "total": "2,858.32"}')


def test_only_the_codes_resend_an_uncertain_send() -> None:
    assert {k for k, v in TEMPLATES.items() if v.resend_uncertain} == {"auth.otp", "lead.verify"}


async def test_an_uncertain_order_message_is_sent_once_and_never_again(
        sessions: Callable[[], AsyncSession]) -> None:
    """The walk on 10 Oct: three copies of one order confirmation, each timeout a
    resend of a message 11za had delivered."""
    row = await _queue(sessions(), recipient=_mobile(), template=TEMPLATE_ORDER_CONFIRMED,
                       payload=ORDER_PAYLOAD)
    provider = FakeProvider(UNCERTAIN, ACCEPTED)
    try:
        await cache.breaker_reset()
        state, attempts, error, payload, _ = await _drain_until(sessions, row, provider)
        assert (state, attempts, payload) == ("dead", 0, "{}"), (state, attempts, payload)
        assert error == UNCERTAIN_PREFIX + "ReadTimeout"
        for _ in range(3):
            await outbox_drain({"provider": provider})
        assert [c.reference for c in provider.calls].count(row) == 1, provider.calls
    finally:
        await _drop(sessions(), row)
        await cache.breaker_reset()


async def test_an_uncertain_code_waits_a_minute_and_charges_nothing(
        sessions: Callable[[], AsyncSession]) -> None:
    row = await _queue(sessions(), recipient=_mobile())
    provider = FakeProvider(UNCERTAIN)
    try:
        await cache.breaker_reset()
        for _ in range(60):
            await outbox_drain({"provider": provider})
            if any(c.reference == row for c in provider.calls):
                break
        state, attempts, error, _, later = await _state(sessions(), row)
        assert (state, attempts, error, later) == ("pending", 0, "ReadTimeout", True)
    finally:
        await _drop(sessions(), row)
        await cache.breaker_reset()


async def test_the_claim_and_the_role_survive_an_await_inside_the_transaction(
        sessions: Callable[[], AsyncSession]) -> None:
    """The row UPDATE after the send runs under the system principal's policies;
    a lost claim would update zero rows and leave the row pending."""
    row_id = await _queue(sessions(), recipient=_mobile())
    try:
        state, *_ = await _drain_until(sessions, row_id, FakeProvider(ACCEPTED, delay=0.3))
        assert state == "sent"
    finally:
        await _drop(sessions(), row_id)


async def test_the_budget_stops_the_loop(sessions: Callable[[], AsyncSession],
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [await _queue(sessions(), recipient=_mobile()) for _ in range(3)]
    monkeypatch.setattr(get_settings(), "outbox_drain_budget", 0.05)
    try:
        # The delay is the provider's, not the database's. Asserting on how long a
        # round trip happens to take made this test say different things on
        # different machines: `== 1` against a tunnel 150 ms away, three of three
        # against a container on the same host. One send that outlasts the budget
        # makes the loop stop after exactly one claim wherever it runs, because
        # the budget is checked before each claim.
        handled = await outbox_drain({"provider": FakeProvider(ACCEPTED, delay=0.08)})
        # Not `== 1`. That encoded the development database being 150 ms away,
        # where one claim fills a fifty-millisecond budget; against a local
        # container two fit and the test failed for being fast. What the budget
        # promises is that it stops the loop before the work runs out.
        assert handled == 1, (
            f"the budget admitted {handled} of {len(rows)}; one send outlasts it, so the "
            f"loop should claim once and stop")
    finally:
        await _drop(sessions(), *rows)


@pytest.mark.parametrize(("template", "payload", "age"), [
    (TEMPLATE_AUTH_OTP, '{"code": "482913"}', timedelta(seconds=250)),
    (TEMPLATE_LEAD_ACK, '{"farmer_name": "F", "inquiry_no": "POL/GJ/2026-27/99999"}',
     timedelta(hours=25)),
])
async def test_a_row_too_old_for_its_template_is_dead_without_a_send(
        sessions: Callable[[], AsyncSession], template: str, payload: str, age: timedelta) -> None:
    row_id = await _queue(sessions(), recipient=_mobile(), template=template, payload=payload,
                          age=age)
    provider = FakeProvider(ACCEPTED)
    try:
        state, attempts, error, payload_after, _ = await _drain_until(sessions, row_id, provider)
        assert (state, attempts, error, payload_after) == ("dead", 0, "too old to send", "{}")
        assert all(c.reference != row_id for c in provider.calls)
    finally:
        await _drop(sessions(), row_id)


async def test_a_permanent_refusal_is_dead_at_once_and_a_fifth_refusal_too(
        sessions: Callable[[], AsyncSession]) -> None:
    permanent = await _queue(sessions(), recipient=_mobile())
    fifth: str | None = None
    try:
        got = await _drain_until(sessions, permanent, FakeProvider(PERMANENT))
        assert got[:3] == ("dead", 0, "Invalid phone number")
        # queued after the first has settled: a due row is handled by whatever
        # provider the drain in hand carries
        fifth = await _queue(sessions(), recipient=_mobile(), attempts=MAX_ATTEMPTS - 1)
        got = await _drain_until(sessions, fifth, FakeProvider(REFUSED))
        assert got[:3] == ("dead", MAX_ATTEMPTS - 1, "Something odd")
    finally:
        await _drop(sessions(), permanent, *([fifth] if fifth else []))


async def test_a_refusal_is_charged_on_the_backoff(sessions: Callable[[], AsyncSession]) -> None:
    row_id = await _queue(sessions(), recipient=_mobile())
    try:
        handled = await outbox_drain({"provider": FakeProvider(REFUSED)}, batch=1)
        assert handled == 1
        state, attempts, error, _, later = await _state(sessions(), row_id)
    finally:
        await _drop(sessions(), row_id)
    # charged once, and the next attempt is a minute out (the 60 s entry, not the 10 s)
    assert (state, attempts, error, later) == ("pending", 1, "Something odd", True)


async def test_a_channel_without_an_adapter_is_dead_uncharged(
        sessions: Callable[[], AsyncSession]) -> None:
    row_id = await _queue(sessions(), recipient=_mobile(), channel="sms")
    try:
        got = await _drain_until(sessions, row_id, FakeProvider(ACCEPTED))
        assert got[:3] == ("dead", 0, "no adapter for channel sms")
    finally:
        await _drop(sessions(), row_id)


async def test_three_transient_failures_open_the_breaker_and_charge_nothing(
        sessions: Callable[[], AsyncSession]) -> None:
    rows = [await _queue(sessions(), recipient=_mobile()) for _ in range(4)]
    provider = FakeProvider(TRANSIENT)
    try:
        await cache.breaker_reset()
        handled = 0
        for _ in range(60):
            handled += await outbox_drain({"provider": provider})
            if await cache.breaker_is_open():
                break
        assert await cache.breaker_is_open(), "three transient failures did not open it"
        assert await outbox_drain({"provider": provider}) == 0, "a drain ran with the breaker open"
        for row in rows:
            state, attempts, *_ = await _state(sessions(), row)
            assert (state, attempts) == ("pending", 0), row
        assert len(provider.calls) == 3
    finally:
        await _drop(sessions(), *rows)
        await cache.breaker_reset()


async def test_with_redis_unreachable_the_drain_still_sends(
        sessions: Callable[[], AsyncSession], monkeypatch: pytest.MonkeyPatch) -> None:
    row_id = await _queue(sessions(), recipient=_mobile())
    dead_redis = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2,
                                socket_timeout=0.2)
    monkeypatch.setattr(cache, "get_redis", lambda: dead_redis)
    try:
        state, *_ = await _drain_until(sessions, row_id, FakeProvider(ACCEPTED))
        assert state == "sent"
    finally:
        await _drop(sessions(), row_id)
        await dead_redis.aclose()


async def test_the_payload_is_cleared_outside_a_local_mock(
        sessions: Callable[[], AsyncSession], monkeypatch: pytest.MonkeyPatch) -> None:
    row_id = await _queue(sessions(), recipient=_mobile())
    monkeypatch.setattr(get_settings(), "environment", "staging")
    try:
        state, _, _, payload, _ = await _drain_until(sessions, row_id, FakeProvider(ACCEPTED))
        assert state == "sent" and payload == "{}"
    finally:
        await _drop(sessions(), row_id)


async def test_the_purge_removes_old_rows_that_are_not_pending(
        sessions: Callable[[], AsyncSession]) -> None:
    old_dead = await _queue(sessions(), recipient=_mobile(), state="dead", age=timedelta(days=91))
    old_pending = await _queue(sessions(), recipient=_mobile(), age=timedelta(days=91),
                               due="now() + interval '1 day'")
    try:
        await purge_expired_sessions({})
        left = (await sessions().execute(text(
            "SELECT count(*) FROM notification_outbox WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [old_dead, old_pending]})).scalar_one()
        assert left == 1
    finally:
        await _drop(sessions(), old_dead, old_pending)


# ── the acknowledgement: withdrawn, once a day, under a per-number lock ──────

async def _lead(sessions: Callable[[], AsyncSession], mobile: str) -> tuple[str, str]:
    s = sessions()
    owner, unit = (await s.execute(text(
        "SELECT id, org_unit_id FROM app_user WHERE user_type = 'staff' "
        "AND org_unit_id IS NOT NULL "
        "AND deleted_at IS NULL AND is_active ORDER BY created_at LIMIT 1"))).one()
    territory = (await s.execute(text(
        "SELECT id FROM territory WHERE deleted_at IS NULL ORDER BY created_at LIMIT 1"),
    )).scalar_one()
    no = "W8-" + uuid.uuid4().hex[:10]
    lead_id = str((await s.execute(text(
        "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
        "mobile, territory_id, owner_user_id, owner_org_unit_id) VALUES (:no, 'commercial', "
        "(SELECT id FROM mis_system WHERE code = 'drip'), "
        "(SELECT id FROM lead_source WHERE code = 'employee'), 'F', :m, :t, :u, :ou) RETURNING id"),
        {"no": no, "m": mobile, "t": territory, "u": owner, "ou": unit})).scalar_one())
    await s.commit()
    return lead_id, no


async def _drop_leads(sessions: Callable[[], AsyncSession], *lead_ids: str) -> None:
    s = sessions()
    await s.execute(text("DELETE FROM activity_event WHERE lead_id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": list(lead_ids)})
    await s.execute(text("DELETE FROM lead WHERE id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": list(lead_ids)})
    await s.commit()


def _ack(no: str) -> str:
    return '{"farmer_name": "F", "inquiry_no": "' + no + '"}'


async def test_an_acknowledgement_whose_lead_was_deleted_is_withdrawn(
        sessions: Callable[[], AsyncSession]) -> None:
    mobile = "+" + _mobile()
    lead_id, no = await _lead(sessions, mobile)
    s = sessions()
    await s.execute(text("UPDATE lead SET deleted_at = now() WHERE id = CAST(:i AS uuid)"),
                    {"i": lead_id})
    await s.commit()
    row_id = await _queue(sessions(), recipient=mobile, template=TEMPLATE_LEAD_ACK,
                          payload=_ack(no))
    provider = FakeProvider(ACCEPTED)
    try:
        got = await _drain_until(sessions, row_id, provider)
        assert got[:3] == ("dead", 0, "lead withdrawn")
        assert all(c.reference != row_id for c in provider.calls)
    finally:
        await _drop(sessions(), row_id)
        await _drop_leads(sessions, lead_id)


async def test_a_second_acknowledgement_inside_a_day_is_not_sent(
        sessions: Callable[[], AsyncSession]) -> None:
    mobile = "+" + _mobile()
    lead_id, no = await _lead(sessions, mobile)
    earlier = await _queue(sessions(), recipient=mobile, template=TEMPLATE_LEAD_ACK, payload="{}",
                           state="sent", sent_at="now() - interval '1 hour'")
    row_id = await _queue(sessions(), recipient=mobile, template=TEMPLATE_LEAD_ACK,
                          payload=_ack(no))
    try:
        got = await _drain_until(sessions, row_id, FakeProvider(ACCEPTED))
        assert got[:3] == ("dead", 0, "duplicate acknowledgement")
    finally:
        await _drop(sessions(), earlier, row_id)
        await _drop_leads(sessions, lead_id)


async def test_two_drains_holding_two_acknowledgements_for_one_number_send_once(
        sessions: Callable[[], AsyncSession]) -> None:
    """Cross-vendor C-3: the check-through-send runs under a per-number advisory
    lock, so the second drain waits and then finds the first's committed send."""
    mobile = "+" + _mobile()
    lead_a, no_a = await _lead(sessions, mobile)
    lead_b, no_b = await _lead(sessions, mobile)
    row_a = await _queue(sessions(), recipient=mobile, template=TEMPLATE_LEAD_ACK,
                         payload=_ack(no_a))
    row_b = await _queue(sessions(), recipient=mobile, template=TEMPLATE_LEAD_ACK,
                         payload=_ack(no_b))
    gate = asyncio.Event()
    provider = FakeProvider(ACCEPTED, gate=gate)

    async def release() -> None:
        await asyncio.wait_for(provider.called.wait(), 60)   # a mistake fails, never hangs
        await asyncio.sleep(1.5)   # the other drain reaches the lock and waits on it
        gate.set()

    try:
        await cache.breaker_reset()
        await asyncio.gather(outbox_drain({"provider": provider}, batch=1),
                             outbox_drain({"provider": provider}, batch=1), release())
        states = []
        for r in (row_a, row_b):
            state, _, error, _, _ = await _state(sessions(), r)
            states.append((state, error))
        assert sorted(states) == [("dead", "duplicate acknowledgement"), ("sent", None)], states
        assert len(provider.calls) == 1
    finally:
        await _drop(sessions(), row_a, row_b)
        await _drop_leads(sessions, lead_a, lead_b)


# ── rule 1a, the worker's half ───────────────────────────────────────────────

async def test_a_code_skipped_in_flight_is_retired_on_its_retry(
        sessions: Callable[[], AsyncSession]) -> None:
    """Cross-vendor C-1. The definer skips a row the worker holds; that row's send
    then fails transiently and comes back for a retry. The worker retires it,
    because a newer code exists for the number, and only the newer code is sent."""
    mobile = _mobile()
    older = await _queue(sessions(), recipient=mobile, payload='{"code": "111111"}')
    gate = asyncio.Event()
    provider = FakeProvider(TRANSIENT, gate=gate)
    newer: str | None = None

    async def resend() -> None:
        nonlocal newer
        await asyncio.wait_for(provider.called.wait(), 60)   # a mistake fails, never hangs
        # what the definer does while the worker holds the older row
        newer = await _queue(sessions(), recipient=mobile, payload='{"code": "222222"}')
        gate.set()

    try:
        await cache.breaker_reset()
        await asyncio.gather(outbox_drain({"provider": provider}, batch=1), resend())
        assert newer is not None
        s = sessions()
        await s.execute(text("UPDATE notification_outbox SET next_attempt_at = now() "
                             "WHERE id = CAST(:i AS uuid)"), {"i": older})
        await s.commit()
        second = FakeProvider(ACCEPTED)
        got_older = await _drain_until(sessions, older, second)
        got_newer = await _drain_until(sessions, newer, second)
        assert got_older[:3] == ("dead", 0, "superseded")
        assert got_newer[0] == "sent"
        assert [c.payload["code"] for c in second.calls if c.recipient == mobile] == ["222222"]
    finally:
        await _drop(sessions(), older, *([newer] if newer else []))
        await cache.breaker_reset()


# ── code review F-3 and F-6 ──────────────────────────────────────────────────

class RaisingProvider:
    """Breaks the port's contract once, then accepts."""

    def __init__(self) -> None:
        self.calls = 0

    async def send(self, msg: OutboundMessage) -> ProviderResult:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("a provider that breaks its contract")
        return ACCEPTED

    async def list_templates(self) -> list[dict[str, object]]:
        return []


async def test_a_row_whose_send_raises_does_not_stop_the_drain(
        sessions: Callable[[], AsyncSession]) -> None:
    """Code review F-3, executed: one raising send left every later row pending,
    tick after tick, because the failed row rolled back to the head of the queue.
    Now it is charged in its own transaction and the drain goes on."""
    first = await _queue(sessions(), recipient=_mobile())
    second = await _queue(sessions(), recipient=_mobile())
    provider = RaisingProvider()
    try:
        handled = await outbox_drain({"provider": provider}, batch=2)
        assert handled == 2 and provider.calls == 2
        state, attempts, error, _, later = await _state(sessions(), first)
        assert (state, attempts, error, later) == ("pending", 1, "RuntimeError", True)
        assert (await _state(sessions(), second))[0] == "sent"
    finally:
        await _drop(sessions(), first, second)


async def test_the_age_is_the_databases_arithmetic(sessions: Callable[[], AsyncSession]) -> None:
    """Code review F-6: the limit for a code is its TTL less a minute (240 s), and
    the row's age is measured where created_at was stamped. A row 235 s old is
    still sent; one 250 s old is dead (the test above)."""
    row_id = await _queue(sessions(), recipient=_mobile(), age=timedelta(seconds=235))
    try:
        state, *_ = await _drain_until(sessions, row_id, FakeProvider(ACCEPTED))
        assert state == "sent"
    finally:
        await _drop(sessions(), row_id)


async def test_the_charge_after_an_error_leaves_a_sent_row_alone(
        sessions: Callable[[], AsyncSession]) -> None:
    """Cross-vendor P2: the failed transaction's lock is gone before the charge
    runs, so another drain may have sent the row; a charge by id alone turned a
    sent row dead at the fifth attempt."""
    row_id = await _queue(sessions(), recipient=_mobile(), state="sent",
                          sent_at="now()", attempts=MAX_ATTEMPTS - 1)
    try:
        await _charge_after_error(row_id, "RuntimeError", get_settings())
        state, attempts, error, _, _ = await _state(sessions(), row_id)
        assert (state, attempts, error) == ("sent", MAX_ATTEMPTS - 1, None)
    finally:
        await _drop(sessions(), row_id)
