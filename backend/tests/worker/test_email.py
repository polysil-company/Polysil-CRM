"""FS-078 against the real database: the definers in migration 082 and the email
jobs. The provider is the mock or a fake; nothing in the suite sends mail."""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.integrations import cache
from api.integrations.email.mock import MockEmailProvider
from api.integrations.email.provider import Email
from api.integrations.whatsapp.provider import Outcome, ProviderResult
from tests.api import test_order_endpoints as endpoints
from worker.jobs import email as job
from worker.jobs.outbox import claim_as_principal, outbox_drain

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


@pytest.fixture(autouse=True)
async def _clean_breakers() -> None:
    await cache.breaker_reset("email")
    await cache.breaker_reset("wa")


async def _notice(sessions: Sessions, user: str, *, minutes_ago: float, read: bool = False,
                  title: str = "Waits for your approval", resource: str | None = "lead") -> str:
    s = sessions()
    try:
        nid = str((await s.execute(text(
            "INSERT INTO notification (recipient_id, event_id, kind, title, resource_type, resource_id, created_at, read_at) "
            "VALUES (CAST(:u AS uuid), gen_random_uuid(), 'approval_waiting', :t, CAST(:rt AS text), "
            "  CASE WHEN CAST(:rt AS text) IS NULL THEN NULL ELSE gen_random_uuid() END, "
            "  now() - make_interval(secs => CAST(:m AS double precision) * 60), "
            "  CASE WHEN CAST(:r AS boolean) THEN now() END) RETURNING id"),
            {"u": user, "t": title, "rt": resource, "m": minutes_ago, "r": read})).scalar_one())
        await s.commit()
    finally:
        await s.close()
    return nid


async def _as_system(sessions: Sessions, sql: str, params: dict[str, Any] | None = None) -> list[Any]:
    s = sessions()
    try:
        async with s.begin():
            await claim_as_principal(s, get_settings())
            return list((await s.execute(text(sql), params or {})).all())
    finally:
        await s.close()


async def _collect(sessions: Sessions) -> None:
    # a large limit: the development database holds other tests' notices too
    await _as_system(sessions, "SELECT email_notice_collect(100000)")


async def _rows(sessions: Sessions, user: str, template: str = "email_notices") -> list[Any]:
    s = sessions()
    try:
        return list((await s.execute(text(
            "SELECT id, state::text AS state, error, payload FROM notification_outbox "
            "WHERE channel = 'email' AND recipient = :u AND template_key = :t ORDER BY created_at"),
            {"u": user, "t": template})).all())
    finally:
        await s.close()


async def _drop_rows(sessions: Sessions, user: str) -> None:
    s = sessions()
    await s.execute(text("DELETE FROM notification_outbox WHERE channel = 'email' AND recipient = :u"), {"u": user})
    await s.commit()
    await s.close()


async def _set(sessions: Sessions, sql: str, params: dict[str, Any]) -> None:
    s = sessions()
    await s.execute(text(sql), params)
    await s.commit()
    await s.close()


# ── the collector ────────────────────────────────────────────────────────────

async def test_only_unread_notices_between_10_minutes_and_24_hours_are_queued(
        sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    try:
        due = [await _notice(sessions, fo, minutes_ago=m) for m in (11, 30, 23 * 60)]
        early = await _notice(sessions, fo, minutes_ago=5)
        stale = await _notice(sessions, fo, minutes_ago=25 * 60)
        read = await _notice(sessions, fo, minutes_ago=20, read=True)
        await _collect(sessions)
        rows = await _rows(sessions, fo)
        assert len(rows) == 1
        assert sorted(rows[0].payload["ids"]) == sorted(due) and rows[0].payload["total"] == 3
        s = sessions()
        queued = {str(r[0]): r[1] for r in (await s.execute(text(
            "SELECT id, email_queued_at IS NOT NULL FROM notification WHERE id = ANY(CAST(:i AS uuid[]))"),
            {"i": [*due, early, stale, read]})).all()}
        await s.close()
        assert all(queued[i] for i in due) and not any(queued[i] for i in (early, stale, read))
        await _collect(sessions)
        assert len(await _rows(sessions, fo)) == 1, "queued once, never again"
    finally:
        await _drop_rows(sessions, fo)


async def test_at_most_20_are_listed_but_every_one_is_queued(sessions: Sessions, shop: Shop) -> None:
    """EC-9: a burst makes one email, not several."""
    fo = shop.ids["field_officer"]
    try:
        for _ in range(23):
            await _notice(sessions, fo, minutes_ago=15)
        await _collect(sessions)
        (row,) = await _rows(sessions, fo)
        assert len(row.payload["ids"]) == 20 and row.payload["total"] == 23
        await _collect(sessions)
        assert len(await _rows(sessions, fo)) == 1
    finally:
        await _drop_rows(sessions, fo)


@pytest.mark.parametrize("change", [
    "UPDATE app_user SET email_notices = false WHERE id = CAST(:u AS uuid)",
    "UPDATE app_user SET is_active = false WHERE id = CAST(:u AS uuid)",
    "UPDATE app_user SET email = 'a@x.com,b@y.com' WHERE id = CAST(:u AS uuid)",
])
async def test_a_person_who_cannot_get_email_is_skipped(sessions: Sessions, shop: Shop, change: str) -> None:
    fo = shop.ids["field_officer"]
    try:
        await _notice(sessions, fo, minutes_ago=15)
        await _set(sessions, change, {"u": fo})
        await _collect(sessions)
        assert await _rows(sessions, fo) == []
    finally:
        await _set(sessions, "UPDATE app_user SET email_notices = true, is_active = true, email = :e "
                   "WHERE id = CAST(:u AS uuid)", {"u": fo, "e": shop.users["field_officer"]})
        await _drop_rows(sessions, fo)


async def test_a_locked_recipient_is_skipped_and_nothing_waits(sessions: Sessions, shop: Shop) -> None:
    """Plan review B-1: a business transaction that notifies the same person, still
    open, holds no lock the collector waits on; a collector holding the person's
    advisory lock makes the other skip them."""
    fo = shop.ids["field_officer"]
    holder = sessions()
    try:
        await _notice(sessions, fo, minutes_ago=15)
        await holder.execute(text(
            "INSERT INTO notification (recipient_id, event_id, kind, title) "
            "VALUES (CAST(:u AS uuid), gen_random_uuid(), 'approval_waiting', 'Open transaction')"), {"u": fo})
        await holder.execute(text("SELECT pg_advisory_xact_lock(10, hashtext(:u))"), {"u": fo})
        await asyncio.wait_for(_collect(sessions), timeout=10)
        assert await _rows(sessions, fo) == [], "skipped while another holds the person"
        await holder.rollback()
        await asyncio.wait_for(_collect(sessions), timeout=10)
        assert len(await _rows(sessions, fo)) == 1
    finally:
        await holder.close()
        await _drop_rows(sessions, fo)


@pytest.mark.parametrize("sql", [
    "SELECT email_notice_collect(1)",
    "SELECT * FROM email_notice_resolve(CAST(:u AS uuid), ARRAY[]::uuid[])",
    "SELECT email_morning_collect(NULL)",
    "SELECT * FROM email_morning_resolve(CAST(:u AS uuid))",
    "SELECT email_morning_sent_purge(CURRENT_DATE)",
])
async def test_only_the_system_principal_may_call_the_email_definers(sessions: Sessions, shop: Shop, sql: str) -> None:
    s = sessions()
    try:
        async with s.begin():
            await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                            {"u": shop.ids["district_manager"]})
            await s.execute(text(f"SET LOCAL ROLE {get_settings().db_app_role}"))
            with pytest.raises(DBAPIError) as caught:
                await s.execute(text(sql), {"u": shop.ids["district_manager"]})
            assert "42501" in str(caught.value) or "only the system principal" in str(caught.value)
    finally:
        await s.close()


async def test_the_definers_are_pinned_definers_and_not_public(sessions: Sessions) -> None:
    s = sessions()
    rows = (await s.execute(text(
        "SELECT p.proname, p.prosecdef, p.proconfig::text, has_function_privilege('public', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.proname IN ('email_notice_collect', 'email_notice_resolve', "
        "'email_morning_collect', 'email_morning_resolve', 'email_morning_sent_purge', 'me_email_preferences_set')"))).all()
    await s.close()
    assert len(rows) == 6
    for name, definer, config, public in rows:
        assert definer and "search_path=public, pg_temp" in config and not public, name


# ── at send ──────────────────────────────────────────────────────────────────

async def test_resolve_drops_what_was_read_and_refuses_the_ineligible(sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    a = await _notice(sessions, fo, minutes_ago=15)
    b = await _notice(sessions, fo, minutes_ago=15, read=True)
    got = await _as_system(sessions, "SELECT * FROM email_notice_resolve(CAST(:u AS uuid), CAST(:i AS uuid[]))",
                           {"u": fo, "i": [a, b]})
    assert [str(r.notice_id) for r in got] == [a] and got[0].email == shop.users["field_officer"]
    await _set(sessions, "UPDATE notification SET read_at = now() WHERE id = CAST(:a AS uuid)", {"a": a})
    got = await _as_system(sessions, "SELECT * FROM email_notice_resolve(CAST(:u AS uuid), CAST(:i AS uuid[]))",
                           {"u": fo, "i": [a, b]})
    assert len(got) == 1 and got[0].notice_id is None, "eligible, nothing left: already read"
    await _set(sessions, "UPDATE app_user SET email_notices = false WHERE id = CAST(:u AS uuid)", {"u": fo})
    try:
        assert await _as_system(sessions, "SELECT * FROM email_notice_resolve(CAST(:u AS uuid), CAST(:i AS uuid[]))",
                                {"u": fo, "i": [a]}) == []
    finally:
        await _set(sessions, "UPDATE app_user SET email_notices = true WHERE id = CAST(:u AS uuid)", {"u": fo})


# ── the morning summary ──────────────────────────────────────────────────────

def _weekday_after(day: dt.date, isodow: int) -> dt.date:
    return day + dt.timedelta(days=(isodow - day.isoweekday()) % 7)


async def _task(sessions: Sessions, shop: Shop, user: str, due: dt.datetime, status: str = "open") -> None:
    await _set(sessions,
               "INSERT INTO task (title, task_type, status, due_at, assigned_to, assigned_by, owner_org_unit_id, "
               "  completed_at, completed_by, outcome, cancel_reason) "
               "VALUES ('Call back', 'call', CAST(:st AS task_status), :d, CAST(:u AS uuid), CAST(:u AS uuid), "
               "  CAST(:o AS uuid), CASE WHEN CAST(:st AS text) = 'done' THEN now() END, "
               "  CASE WHEN CAST(:st AS text) = 'done' THEN CAST(:u AS uuid) END, "
               "  CASE WHEN CAST(:st AS text) = 'done' THEN 'ok' END, NULL)",
               {"st": status, "d": due, "u": user, "o": shop.office})


async def test_the_morning_summary_counts_by_ist_day_once_and_never_on_sunday(sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    # a Wednesday far ahead, so no other test's tasks fall on it as "today"
    day = _weekday_after(dt.date.today() + dt.timedelta(days=400), 3)
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=IST)
    try:
        await _task(sessions, shop, fo, start + dt.timedelta(minutes=1))            # due today, 00:01 IST
        await _task(sessions, shop, fo, start + dt.timedelta(hours=23, minutes=59))  # due today
        await _task(sessions, shop, fo, start - dt.timedelta(minutes=1))            # overdue, 23:59 the day before
        await _task(sessions, shop, fo, start + dt.timedelta(days=1))               # tomorrow: not counted
        await _task(sessions, shop, fo, start - dt.timedelta(days=2), status="done")
        await _as_system(sessions, "SELECT email_morning_collect(CAST(:d AS date))", {"d": day})
        (row,) = await _rows(sessions, fo, "email_morning")
        assert row.payload == {"day": day.isoformat(), "due_today": 2, "overdue": 1}
        await _as_system(sessions, "SELECT email_morning_collect(CAST(:d AS date))", {"d": day})
        assert len(await _rows(sessions, fo, "email_morning")) == 1, "once a day (EC-11)"
        sunday = _weekday_after(day, 7)
        (n,) = await _as_system(sessions, "SELECT email_morning_collect(CAST(:d AS date))", {"d": sunday})
        assert n[0] == 0
    finally:
        await _drop_rows(sessions, fo)
        await _set(sessions, "DELETE FROM email_morning_sent WHERE user_id = CAST(:u AS uuid)", {"u": fo})


async def test_no_summary_on_a_holiday_or_with_the_switch_off(sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    day = _weekday_after(dt.date.today() + dt.timedelta(days=500), 2)
    try:
        await _task(sessions, shop, fo, dt.datetime.combine(day, dt.time(10), tzinfo=IST))
        await _set(sessions, "INSERT INTO holiday (day, name, created_by) VALUES (:d, 'Closed', CAST(:u AS uuid))",
                   {"d": day, "u": fo})
        await _as_system(sessions, "SELECT email_morning_collect(CAST(:d AS date))", {"d": day})
        assert await _rows(sessions, fo, "email_morning") == []
        await _set(sessions, "DELETE FROM holiday WHERE day = :d", {"d": day})
        await _set(sessions, "UPDATE app_user SET email_morning = false WHERE id = CAST(:u AS uuid)", {"u": fo})
        await _as_system(sessions, "SELECT email_morning_collect(CAST(:d AS date))", {"d": day})
        assert await _rows(sessions, fo, "email_morning") == []
    finally:
        await _set(sessions, "DELETE FROM holiday WHERE day = :d", {"d": day})
        await _set(sessions, "UPDATE app_user SET email_morning = true WHERE id = CAST(:u AS uuid)", {"u": fo})
        await _drop_rows(sessions, fo)


# ── the jobs ─────────────────────────────────────────────────────────────────

class FakeEmail:
    def __init__(self, *results: ProviderResult) -> None:
        self.results = list(results) or [ProviderResult(Outcome.ACCEPTED, "fake")]
        self.sent: list[Email] = []

    async def send(self, msg: Email) -> ProviderResult:
        self.sent.append(msg)
        return self.results[min(len(self.sent), len(self.results)) - 1]


async def _drain_until(sessions: Sessions, user: str, ctx: dict[str, Any],
                       template: str = "email_notices") -> Any:
    for _ in range(60):
        await job.email_drain(ctx, batch=500)
        rows = await _rows(sessions, user, template)
        if rows and rows[-1].state != "pending":
            return rows[-1]
    return (await _rows(sessions, user, template))[-1]


async def test_none_collects_nothing_and_ends_pending_email_rows(sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    try:
        await _notice(sessions, fo, minutes_ago=15)
        assert await job.email_collect({"email_provider": None}) == 0
        assert await _rows(sessions, fo) == []
        await _set(sessions, "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
                   "VALUES ('email', 'email_notices', :u, '{\"ids\": []}')", {"u": fo})
        await job.email_drain({"email_provider": None}, batch=10)
        (row,) = await _rows(sessions, fo)
        assert row.state == "dead" and row.error == "email off" and row.payload == {}
    finally:
        await _drop_rows(sessions, fo)


async def test_collect_then_drain_sends_one_email_listing_three_notices(sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    provider = MockEmailProvider()
    try:
        for t in ("First <b>", "Second", "Third"):
            await _notice(sessions, fo, minutes_ago=15, title=t)
        await job.email_collect({"email_provider": provider})
        row = await _drain_until(sessions, fo, {"email_provider": provider})
        assert row.state == "sent" and row.payload == {}, "the payload goes once sent"
        (mail,) = [m for m in provider.sent if m.reference == str(row.id)]
        assert mail.to == shop.users["field_officer"] and mail.subject == "3 updates in Polysil CRM"
        assert "First &lt;b&gt;" in mail.html and "<b>" not in mail.html.replace("<body", ""), "escaped"
        assert mail.text.count("/leads/") == 3
    finally:
        await _drop_rows(sessions, fo)


async def test_a_notice_read_before_the_send_is_never_emailed(sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    provider = FakeEmail()
    try:
        nid = await _notice(sessions, fo, minutes_ago=15)
        await job.email_collect({"email_provider": provider})
        await _set(sessions, "UPDATE notification SET read_at = now() WHERE id = CAST(:i AS uuid)", {"i": nid})
        row = await _drain_until(sessions, fo, {"email_provider": provider})
        assert row.state == "dead" and row.error == "already read"
        assert not [m for m in provider.sent if m.reference == str(row.id)]
    finally:
        await _drop_rows(sessions, fo)


async def test_an_uncertain_send_is_never_repeated(sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    mine = shop.users["field_officer"]

    class UncertainForMe(FakeEmail):
        """Other tests' rows drain first; only this person's send gets no answer."""

        async def send(self, msg: Email) -> ProviderResult:
            self.sent.append(msg)
            if msg.to == mine:
                return ProviderResult(Outcome.UNCERTAIN, None, "no answer")
            return ProviderResult(Outcome.ACCEPTED, "fake")

    provider = UncertainForMe()
    try:
        await _notice(sessions, fo, minutes_ago=15)
        await job.email_collect({"email_provider": provider})
        row = await _drain_until(sessions, fo, {"email_provider": provider})
        assert row.state == "dead" and row.error.startswith("no answer in time, may have arrived")
        assert len([m for m in provider.sent if m.to == mine]) == 1, "sent once, never again"
    finally:
        await _drop_rows(sessions, fo)
        await cache.breaker_reset("email")


async def test_the_whatsapp_drain_leaves_email_rows_and_the_email_breaker_never_stops_it(
        sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]

    class Accepting:
        async def send(self, msg: Any) -> ProviderResult:
            return ProviderResult(Outcome.ACCEPTED, "wa")

        async def list_templates(self) -> list[dict[str, object]]:
            return []

    try:
        await _set(sessions, "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
                   "VALUES ('email', 'email_notices', :u, '{\"ids\": []}')", {"u": fo})
        mobile = "9198" + f"{uuid.uuid4().int % 10**8:08d}"
        s = sessions()
        wa = str((await s.execute(text(
            "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
            "VALUES ('whatsapp', 'auth.otp', :m, '{\"code\": \"123456\"}') RETURNING id"), {"m": mobile})).scalar_one())
        await s.commit()
        await s.close()
        # the email breaker open: WhatsApp still drains
        await cache.get_redis().setex("email:breaker:open", 60, "1")
        for _ in range(60):
            await outbox_drain({"provider": Accepting()}, batch=500)
            s = sessions()
            state = (await s.execute(text("SELECT state::text FROM notification_outbox WHERE id = CAST(:i AS uuid)"),
                                     {"i": wa})).scalar_one()
            await s.close()
            if state != "pending":
                break
        assert state == "sent"
        (row,) = await _rows(sessions, fo)
        assert row.state == "pending", "outbox_drain never claims email"
        assert await job.email_drain({"email_provider": FakeEmail()}, batch=10) == 0, "its own breaker"
    finally:
        await cache.breaker_reset("email")
        await _drop_rows(sessions, fo)
        await _set(sessions, "DELETE FROM notification_outbox WHERE id = CAST(:i AS uuid)", {"i": wa})


async def test_the_morning_job_twice_in_a_day_sends_once(sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    day = _weekday_after(dt.date.today() + dt.timedelta(days=600), 4)
    provider = FakeEmail()
    try:
        await _task(sessions, shop, fo, dt.datetime.combine(day, dt.time(9), tzinfo=IST))
        await job.email_morning({"email_provider": provider}, day=day)
        await job.email_morning({"email_provider": provider}, day=day)
        assert len(await _rows(sessions, fo, "email_morning")) == 1
    finally:
        await _drop_rows(sessions, fo)
        await _set(sessions, "DELETE FROM email_morning_sent WHERE user_id = CAST(:u AS uuid)", {"u": fo})


# ── code review of FS-078: the send-time checks and the clock ────────────────

ADDRESSES = ["ravi@polysil.in", "r.k+crm@mail.polysil.co.in", "a@x.com,b@y.com", "Ravi <r@x.com>",
             "रवि@polysil.in", "r@x", "r @x.com", "@x.com", "r@@x.com", "r@x.com\nBcc: e@y.com",
             "o'brien@x.in", "a@b-c.io"]


def _migration() -> Any:
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "api/db/migrations/versions/082_email_notices.py"
    spec = importlib.util.spec_from_file_location("mig_082_email", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_the_database_and_the_sender_agree_on_what_an_address_is(sessions: Sessions) -> None:
    """Code review F-4: an address the database calls eligible and the sender
    refuses would make a dead row on every run, with the switch hidden."""
    from api.integrations.email.provider import ADDRESS_RE, parse_address
    pattern = _migration().ADDRESS_RE
    assert pattern == ADDRESS_RE
    s = sessions()
    try:
        for a in ADDRESSES:
            sql = (await s.execute(text("SELECT CAST(:a AS text) ~ CAST(:re AS text)"),
                                   {"a": a, "re": pattern})).scalar_one()
            assert bool(sql) == (parse_address(a) == a), a
    finally:
        await s.close()


async def test_a_notice_row_past_24_hours_is_never_sent(sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    provider = FakeEmail()
    try:
        await _notice(sessions, fo, minutes_ago=15)
        await job.email_collect({"email_provider": provider})
        await _set(sessions, "UPDATE notification_outbox SET created_at = now() - interval '25 hours' "
                   "WHERE channel = 'email' AND recipient = :u", {"u": fo})
        row = await _drain_until(sessions, fo, {"email_provider": provider})
        assert row.state == "dead" and row.error == "too old to send"
        assert not [m for m in provider.sent if m.reference == str(row.id)]
    finally:
        await _drop_rows(sessions, fo)


async def test_a_notice_itself_past_24_hours_is_dropped_at_send(sessions: Sessions, shop: Shop) -> None:
    """Code review F-5: rule 2 counts from the notice, not from the row."""
    fo = shop.ids["field_officer"]
    old = await _notice(sessions, fo, minutes_ago=25 * 60)
    got = await _as_system(sessions, "SELECT * FROM email_notice_resolve(CAST(:u AS uuid), CAST(:i AS uuid[]))",
                           {"u": fo, "i": [old]})
    assert len(got) == 1 and got[0].notice_id is None


async def test_a_summary_row_after_noon_is_never_sent(sessions: Sessions, shop: Shop) -> None:
    fo = shop.ids["field_officer"]
    yesterday = (dt.datetime.now(IST) - dt.timedelta(days=1)).date()
    try:
        await _set(sessions, "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
                   "VALUES ('email', 'email_morning', :u, CAST(:p AS jsonb))",
                   {"u": fo, "p": '{"day": "' + yesterday.isoformat() + '", "due_today": 1, "overdue": 0}'})
        row = await _drain_until(sessions, fo, {"email_provider": FakeEmail()}, "email_morning")
        assert row.state == "dead" and row.error == "too old to send"
    finally:
        await _drop_rows(sessions, fo)


async def test_a_partner_closed_after_queueing_gets_no_email(sessions: Sessions, shop: Shop) -> None:
    dealer = shop.ids["dealer"]
    address = f"dealer_{uuid.uuid4().hex[:8]}@polysil.in"
    provider = FakeEmail()
    await _set(sessions, "UPDATE app_user SET email = :e WHERE id = CAST(:u AS uuid)", {"e": address, "u": dealer})
    try:
        await _notice(sessions, dealer, minutes_ago=15)
        await job.email_collect({"email_provider": provider})
        assert len(await _rows(sessions, dealer)) == 1, "an open dealer is eligible"
        await _set(sessions, "UPDATE channel_partner SET is_active = false WHERE id = CAST(:p AS uuid)",
                   {"p": shop.partner})
        row = await _drain_until(sessions, dealer, {"email_provider": provider})
        assert row.state == "dead" and row.error == "recipient no longer eligible"
        assert not [m for m in provider.sent if m.to == address]
    finally:
        await _set(sessions, "UPDATE channel_partner SET is_active = true WHERE id = CAST(:p AS uuid)",
                   {"p": shop.partner})
        await _set(sessions, "UPDATE app_user SET email = NULL WHERE id = CAST(:u AS uuid)", {"u": dealer})
        await _drop_rows(sessions, dealer)


@pytest.mark.parametrize(("hhmm", "runs"), [((7, 50), False), ((8, 0), True), ((10, 59), True), ((11, 10), False)])
async def test_the_morning_job_keeps_to_8_to_11_ist(monkeypatch: pytest.MonkeyPatch, hhmm: tuple[int, int],
                                                    runs: bool) -> None:
    called: list[bool] = []

    class Session:
        async def __aenter__(self) -> Any:
            called.append(True)
            raise RuntimeError("stop here")

        async def __aexit__(self, *a: Any) -> None: ...

    monkeypatch.setattr(job, "_now", lambda: dt.datetime(2026, 10, 28, *hhmm, tzinfo=IST))
    monkeypatch.setattr(job, "async_session_factory", Session)
    if runs:
        with pytest.raises(RuntimeError, match="stop here"):
            await job.email_morning({"email_provider": FakeEmail()})
    else:
        assert await job.email_morning({"email_provider": FakeEmail()}) == 0
    assert bool(called) == runs


async def test_eleven_read_notices_are_answers_not_a_dead_burst(sessions: Sessions, shop: Shop,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """Code review F-3, plan review SF-3."""
    fo = shop.ids["field_officer"]
    errors: list[str] = []
    real = job.log

    class Log:
        def __getattr__(self, name: str) -> Any:
            return getattr(real, name)

        def error(self, event: str, **kw: Any) -> None:
            errors.append(event)

    monkeypatch.setattr(job, "log", Log())
    try:
        for _ in range(11):
            await _set(sessions, "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
                       "VALUES ('email', 'email_notices', :u, CAST(:p AS jsonb))",
                       {"u": fo, "p": '{"ids": [], "total": 0}'})
        await job.email_drain({"email_provider": FakeEmail()}, batch=5000)
        rows = await _rows(sessions, fo)
        assert len(rows) == 11 and all(r.error == "already read" for r in rows)
        assert "email.dead_burst" not in errors
    finally:
        await _drop_rows(sessions, fo)
