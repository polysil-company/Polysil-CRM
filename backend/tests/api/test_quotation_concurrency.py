"""FS-005's mechanisms that only exist under concurrency (spec 10, the service
row; code review F-3): the lead-first lock order, and one outcome per race.

Every sequential test passes with `_lock_lead` removed from send, transition and
revise: two calls in one transaction never contend. Each test here forces real
overlap on two connections through the service functions, ordered with an Event
as the 007 suite does: the first call signals once it has returned with its
locks held, the second starts only then, and the first commits a little later.
So the second either queues on the lock and re-reads the committed state, or it
does not, and the assertion says which.

The rows are built through the API with the endpoint tests' fixtures; the races
run at the service layer, where the lock order lives.
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
from api.schemas.leads import LeadAssign
from api.schemas.quotations import SendRequest, TransitionRequest
from api.services import leads as leads_service
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

# How long the first connection keeps its transaction open after signalling: long
# enough that the second is provably inside its statement, waiting on the lock.
HOLD = 0.8

Work = Callable[[AsyncSession], Awaitable[Any]]


async def _as(s: AsyncSession, user_id: str) -> None:
    """What get_db does: the claim, then app_role, transaction-local."""
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})
    await enter_role(s, "app_role")


def _caller(who: Staff) -> Caller:
    return Caller(who.id, who.org_unit_id, None,
                  scopes={"leads": "global", "quotations": "global", "pricing": "global"},
                  deletes=frozenset({"quotations"}))


async def _call(s: AsyncSession, who: Staff, work: Work, *, after: asyncio.Event | None = None,
                ready: asyncio.Event | None = None, hold: float = 0.0) -> dict[str, Any]:
    """One service call on its own connection under `who`'s claim. `after` is
    waited on before it starts; `ready` is set once it has returned, with its
    locks held; the transaction stays open for `hold` before committing."""
    if after is not None:
        await after.wait()
    await _as(s, who.id)
    try:
        result = await work(s)
    except ApiError as exc:
        await s.rollback()
        if ready is not None:
            ready.set()
        return {"error": exc.code}
    except DBAPIError as exc:
        await s.rollback()
        if ready is not None:
            ready.set()
        return {"error": str(getattr(exc.orig, "sqlstate", "")) or type(exc.orig).__name__}
    if ready is not None:
        ready.set()
    await asyncio.sleep(hold)
    await s.commit()
    return {"ok": result}


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


def _assign_work(lead_id: str, who: Staff, to_user_id: str) -> Work:
    async def work(s: AsyncSession) -> Any:
        return await leads_service.assign_lead(s, _caller(who), lead_id,
                                               LeadAssign(owner_user_id=to_user_id))
    return work


@pytest_asyncio.fixture
async def colleague(sessions: Callable[[], AsyncSession], quoter: Staff) -> AsyncIterator[str]:
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


async def _row(sessions: Callable[[], AsyncSession], quotation_id: str) -> Any:
    s = sessions()
    row = (await s.execute(text(
        "SELECT q.status::text AS status, q.owner_user_id::text AS owner, q.quote_no, "
        "l.stage::text AS stage, (SELECT count(*) FROM quotation x WHERE x.quote_no = q.quote_no) "
        "AS numbered FROM quotation q JOIN lead l ON l.id = q.lead_id "
        "WHERE q.id = CAST(:q AS uuid)"), {"q": quotation_id})).one()
    await s.rollback()
    return row


async def test_a_send_and_a_reassignment_queue_when_the_send_is_first(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        colleague: str, sessions: Callable[[], AsyncSession]) -> None:
    """The send holds the lead (lead_lock_for_quotation) and then the draft. The
    reassignment's UPDATE on the lead queues behind it, and its trigger then
    re-scopes the quotation, sent by now, at depth 2."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    a, b = sessions(), sessions()
    ready = asyncio.Event()
    got = await asyncio.gather(
        _call(a, quoter, _send_work(q["id"], quoter), ready=ready, hold=HOLD),
        _call(b, quoter, _assign_work(q["lead"]["id"], quoter, colleague), after=ready),
    )
    assert all("ok" in g for g in got), got
    row = await _row(sessions, q["id"])
    assert (row.status, row.owner) == ("sent", colleague) and row.quote_no, row


async def test_a_send_and_a_reassignment_queue_when_the_reassignment_is_first(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        colleague: str, sessions: Callable[[], AsyncSession]) -> None:
    """The reassignment holds the lead and, through its trigger, the draft. The
    send's first call is the lead lock, so it queues there rather than taking
    the draft first and deadlocking (round 2 B-2)."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    a, b = sessions(), sessions()
    ready = asyncio.Event()
    got = await asyncio.gather(
        _call(a, quoter, _assign_work(q["lead"]["id"], quoter, colleague), ready=ready,
              hold=HOLD),
        _call(b, quoter, _send_work(q["id"], quoter), after=ready),
    )
    assert all("ok" in g for g in got), got
    row = await _row(sessions, q["id"])
    assert (row.status, row.owner) == ("sent", colleague) and row.quote_no, row


async def test_two_sends_of_one_draft_produce_one_number(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    """The second send re-reads the draft under the lock after the first commits,
    finds it sent, and is refused; one number is allocated, not two."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    a, b = sessions(), sessions()
    ready = asyncio.Event()
    got = await asyncio.gather(
        _call(a, quoter, _send_work(q["id"], quoter), ready=ready, hold=HOLD),
        _call(b, quoter, _send_work(q["id"], quoter), after=ready),
    )
    outcomes = sorted("ok" if "ok" in g else g["error"] for g in got)
    assert outcomes == ["ok", "quotation_not_draft"], got
    row = await _row(sessions, q["id"])
    assert (row.status, row.stage, int(row.numbered)) == ("sent", "quoted", 1), row


async def test_two_answers_to_one_quotation_keep_the_first(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    """Accept and reject at once: the second validates the transition from the
    status the first left, and an accepted quotation cannot become rejected."""
    h = await _auth(client, quoter)
    q = await _draft(client, h, qenv, catalogue)
    await _send(client, h, q["id"])
    a, b = sessions(), sessions()
    ready = asyncio.Event()
    got = await asyncio.gather(
        _call(a, quoter, _answer_work(q["id"], quoter, "accepted"), ready=ready, hold=HOLD),
        _call(b, quoter, _answer_work(q["id"], quoter, "rejected"), after=ready),
    )
    outcomes = sorted("ok" if "ok" in g else g["error"] for g in got)
    assert outcomes == ["invalid_transition", "ok"], got
    row = await _row(sessions, q["id"])
    assert (row.status, row.stage) == ("accepted", "won"), row


async def test_quotation_first_then_lead_deadlocks_which_the_lead_first_order_prevents(
        client: httpx.AsyncClient, quoter: Staff, qenv: QEnv, catalogue: Catalogue,
        colleague: str, sessions: Callable[[], AsyncSession]) -> None:
    """Round 2 B-2, held as an executed fact: the lead's scope trigger takes the
    quotations' locks after the lead's, so a service that took the quotation
    first would deadlock against any reassignment. A takes the quotation; B takes
    the lead and updates it, which waits on A's row; A asks for the lead. 40P01."""
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
            await a.rollback()
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
            await b.rollback()
            return str(getattr(exc.orig, "sqlstate", ""))
        await b.commit()
        return "ok"

    got = await asyncio.gather(quotation_then_lead(), lead_then_its_quotations())
    assert sorted(got) == ["40P01", "ok"], got
