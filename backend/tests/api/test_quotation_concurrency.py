"""FS-005's mechanisms that only exist under concurrency (spec 10, the service
row; code review F-3; PR #10 review): the lead-first lock order, and one outcome
per race.

**The lock-order proof** holds the lead in another session, starts the service
call, and waits until PostgreSQL itself reports the call blocked (`pg_locks`,
not granted). Only then does it move the lead, whose scope trigger then updates
the lead's quotations. A service that locks the lead first holds nothing yet, so
the move goes through and the call follows. A service that locked the quotation
first would hold it while waiting on the lead, and the trigger would wait on it:
a deadlock, 40P01. Delete `_lock_lead` from send, transition or revise and the
matching case goes red. That is the point of these tests: the previous version
ordered its sessions so that neither shape could deadlock, and stayed green with
the lock removed.

**The races** assert that the second call really waited on the first
(`pg_locks` again), so a run where the calls happened not to overlap fails
instead of passing as a sequential run would.

Every session is rolled back and closed in a `finally`: an unexpected error must
fail the test, not leave a row lock that hangs the teardown.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.config import get_settings
from api.db.session import enter_role
from api.errors import ApiError
from api.schemas.quotations import ReviseRequest, SendRequest, TransitionRequest
from api.services import quotations as service
from tests.api import test_quotation_endpoints as endpoints
from tests.api.conftest import Catalogue, Staff, _auth

# the endpoint tests' fixtures and builders, so the rows here are built the same way
quoter = endpoints.quoter
qenv = endpoints.qenv
QEnv = endpoints.QEnv
_draft = endpoints._draft
_send = endpoints._send

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

# how long to wait for PostgreSQL to report a session blocked, through the tunnel
BLOCK_TIMEOUT = 15.0

Work = Callable[[AsyncSession], Awaitable[Any]]
Sessions = Callable[[], AsyncSession]


async def _as(s: AsyncSession, user_id: str) -> None:
    """What get_db does: the claim, then app_role, transaction-local."""
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})
    await enter_role(s, "app_role")


def _caller(who: Staff) -> Caller:
    return Caller(who.id, who.org_unit_id, None,
                  scopes={"leads": "global", "quotations": "global", "pricing": "global"},
                  deletes=frozenset({"quotations"}))


async def _blocked(sessions: Sessions, pid: int) -> bool:
    """True once the backend `pid` waits on a lock it has not been granted."""
    probe = sessions()
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + BLOCK_TIMEOUT
        while loop.time() < deadline:
            waiting = (await probe.execute(text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid = :p AND NOT granted)"),
                {"p": pid})).scalar_one()
            await probe.rollback()
            if waiting:
                return True
            await asyncio.sleep(0.1)
        return False
    finally:
        await probe.close()


async def _call(s: AsyncSession, who: Staff, work: Work, *,
                pid: asyncio.Future[int] | None = None,
                after: asyncio.Event | None = None,
                ready: asyncio.Event | None = None,
                before_commit: Callable[[], Awaitable[None]] | None = None) -> dict[str, Any]:
    """One service call on its own connection under `who`'s claim. `pid` receives
    the backend's pid before the call starts; `after` is waited on first; `ready`
    is set once the call has returned with its locks held; `before_commit` runs
    between the call and the commit. The session is always closed."""
    try:
        if after is not None:
            await after.wait()
        await _as(s, who.id)
        if pid is not None:
            pid.set_result(int((await s.execute(text("SELECT pg_backend_pid()"))).scalar_one()))
        try:
            result = await work(s)
        except ApiError as exc:
            return {"error": exc.code}
        except DBAPIError as exc:
            return {"error": str(getattr(exc.orig, "sqlstate", "")) or type(exc.orig).__name__}
        finally:
            if ready is not None:
                ready.set()
        if before_commit is not None:
            await before_commit()
        await s.commit()
        return {"ok": result}
    finally:
        await s.rollback()
        await s.close()


def _send_work(quotation_id: str, who: Staff) -> Work:
    settings = get_settings()

    async def work(s: AsyncSession) -> Any:
        return await service.send_quotation(s, _caller(who), quotation_id,
                                            SendRequest(channel="none"), settings)
    return work


def _answer_work(quotation_id: str, who: Staff, to: str) -> Work:
    settings = get_settings()

    async def work(s: AsyncSession) -> Any:
        return await service.transition_quotation(s, _caller(who), quotation_id,
                                                  TransitionRequest(to=to), settings)
    return work


def _revise_work(quotation_id: str, who: Staff) -> Work:
    settings = get_settings()

    async def work(s: AsyncSession) -> Any:
        return await service.revise_quotation(
            s, _caller(who), quotation_id,
            ReviseRequest(price_effective_date=endpoints.AS_OF), settings)
    return work


@pytest_asyncio.fixture
async def colleague(sessions: Sessions, quoter: Staff) -> AsyncIterator[str]:
    """Someone to reassign a lead to: the quoter's role and office. Its teardown
    hands the leads back first, because it may run before the territory's."""
    tag = uuid.uuid4().hex[:8]
    s = sessions()
    uid = str((await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Colleague', :r, :o) RETURNING id"),
        {"e": f"conc12_{tag}@polysil.in", "r": quoter.role_id,
         "o": quoter.org_unit_id})).scalar_one())
    await s.commit()
    await s.close()
    try:
        yield uid
    finally:
        c = sessions()
        # the lead's trigger carries the owner back onto its quotations (depth 2)
        await c.execute(text(
            "UPDATE lead SET owner_user_id = CAST(:q AS uuid) "
            "WHERE owner_user_id = CAST(:u AS uuid)"), {"q": quoter.id, "u": uid})
        await c.execute(text(
            "DELETE FROM activity_event WHERE entity_id = CAST(:u AS uuid) "
            "OR actor_id = CAST(:u AS uuid)"), {"u": uid})
        await c.execute(text("DELETE FROM app_user WHERE id = CAST(:u AS uuid)"), {"u": uid})
        await c.commit()
        await c.close()


async def _row(sessions: Sessions, quotation_id: str) -> Any:
    s = sessions()
    try:
        return (await s.execute(text(
            "SELECT q.status::text AS status, q.owner_user_id::text AS owner, q.quote_no, "
            "l.stage::text AS stage, "
            "(SELECT count(*) FROM quotation x WHERE x.quote_no = q.quote_no) AS numbered "
            "FROM quotation q JOIN lead l ON l.id = q.lead_id "
            "WHERE q.id = CAST(:q AS uuid)"), {"q": quotation_id})).one()
    finally:
        await s.rollback()
        await s.close()


# ── the lock order ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("mutation", ["send", "accept", "revise"])
async def test_the_mutation_waits_on_the_lead_before_it_locks_a_quotation(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        colleague: str, sessions: Sessions, mutation: str) -> None:
    """Round 2 B-2 and code review F-3. Another session holds the lead; the
    mutation starts and PostgreSQL reports it blocked; the other session then
    moves the lead, and the scope trigger updates this quotation. Lead first:
    both succeed. Quotation first: 40P01."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    if mutation != "send":
        await _send(client, h, q["id"])
    work = {"send": _send_work(q["id"], quoter),
            "accept": _answer_work(q["id"], quoter, "accepted"),
            "revise": _revise_work(q["id"], quoter)}[mutation]

    holder = sessions()
    moved: dict[str, str] = {}
    try:
        await holder.execute(text("SELECT 1 FROM lead WHERE id = CAST(:l AS uuid) FOR UPDATE"),
                             {"l": q["lead"]["id"]})
        pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        call = asyncio.create_task(_call(sessions(), quoter, work, pid=pid))
        assert await _blocked(sessions, await pid), "the mutation never waited on the lead"
        try:
            await holder.execute(text(
                "UPDATE lead SET owner_user_id = CAST(:u AS uuid) WHERE id = CAST(:l AS uuid)"),
                {"u": colleague, "l": q["lead"]["id"]})
            await holder.commit()
            moved["lead"] = "ok"
        except DBAPIError as exc:
            moved["lead"] = str(getattr(exc.orig, "sqlstate", ""))
        got = await call
    finally:
        await holder.rollback()
        await holder.close()
    assert moved["lead"] == "ok" and "ok" in got, (moved, got)
    row = await _row(sessions, q["id"])
    assert row.owner == colleague, "the lead's move reached the quotation"


async def test_quotation_first_then_lead_deadlocks_which_the_lead_first_order_prevents(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        colleague: str, sessions: Sessions) -> None:
    """The hazard the test above guards against, held as an executed fact in raw
    SQL: A takes the quotation; B takes the lead and updates it, which waits on
    A's row through the scope trigger; A asks for the lead. 40P01."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    lead_id, quotation_id = q["lead"]["id"], q["id"]
    a, b = sessions(), sessions()
    a_has_quotation, b_has_lead = asyncio.Event(), asyncio.Event()

    async def quotation_then_lead() -> str:
        await a.execute(text("SELECT 1 FROM quotation WHERE id = CAST(:q AS uuid) FOR UPDATE"),
                        {"q": quotation_id})
        a_has_quotation.set()
        await b_has_lead.wait()
        try:
            await a.execute(text("SELECT 1 FROM lead WHERE id = CAST(:l AS uuid) FOR UPDATE"),
                            {"l": lead_id})
        except DBAPIError as exc:
            return str(getattr(exc.orig, "sqlstate", ""))
        await a.commit()
        return "ok"

    async def lead_then_its_quotations() -> str:
        await a_has_quotation.wait()
        await b.execute(text("SELECT 1 FROM lead WHERE id = CAST(:l AS uuid) FOR UPDATE"),
                        {"l": lead_id})
        b_has_lead.set()
        try:
            await b.execute(text(
                "UPDATE lead SET owner_user_id = CAST(:u AS uuid) WHERE id = CAST(:l AS uuid)"),
                {"u": colleague, "l": lead_id})
        except DBAPIError as exc:
            return str(getattr(exc.orig, "sqlstate", ""))
        await b.commit()
        return "ok"

    try:
        got = await asyncio.gather(quotation_then_lead(), lead_then_its_quotations())
    finally:
        for s in (a, b):
            await s.rollback()
            await s.close()
    assert sorted(got) == ["40P01", "ok"], got


# ── one outcome per race ─────────────────────────────────────────────────────

async def _race(sessions: Sessions, who: Staff, first: Work,
                second: Work) -> tuple[list[dict[str, Any]], bool]:
    """`first` runs and holds its locks; `second` starts; `first` commits only
    once PostgreSQL reports `second` blocked. Returns both outcomes and whether
    the second really waited."""
    ready = asyncio.Event()
    second_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    waited: dict[str, bool] = {}

    async def hold_until_second_waits() -> None:
        waited["second"] = await _blocked(sessions, await second_pid)

    got = await asyncio.gather(
        _call(sessions(), who, first, ready=ready, before_commit=hold_until_second_waits),
        _call(sessions(), who, second, after=ready, pid=second_pid),
    )
    return list(got), waited.get("second", False)


async def test_two_sends_of_one_draft_produce_one_number(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Sessions) -> None:
    """The second send waits, then re-reads the draft under the lock, finds it
    sent, and is refused; one number is allocated, not two."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    got, waited = await _race(sessions, quoter, _send_work(q["id"], quoter),
                              _send_work(q["id"], quoter))
    assert waited, "the second send did not wait on the first: the race was not a race"
    outcomes = sorted("ok" if "ok" in g else g["error"] for g in got)
    assert outcomes == ["ok", "quotation_not_draft"], got
    row = await _row(sessions, q["id"])
    assert (row.status, row.stage, int(row.numbered)) == ("sent", "quoted", 1), row


async def test_two_answers_to_one_quotation_keep_the_first(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Sessions) -> None:
    """Accept and reject at once: the second waits, then validates the transition
    from the status the first left, and an accepted quotation cannot become
    rejected."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    await _send(client, h, q["id"])
    got, waited = await _race(sessions, quoter, _answer_work(q["id"], quoter, "accepted"),
                              _answer_work(q["id"], quoter, "rejected"))
    assert waited, "the second answer did not wait on the first"
    outcomes = sorted("ok" if "ok" in g else g["error"] for g in got)
    assert outcomes == ["invalid_transition", "ok"], got
    row = await _row(sessions, q["id"])
    assert (row.status, row.stage) == ("accepted", "won"), row
