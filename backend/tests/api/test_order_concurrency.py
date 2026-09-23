"""FS-011's mechanisms that only exist under concurrency (spec 10, the
concurrency row): the order-first lock order, and one outcome per race.

**The lock-order proof** holds the order row in another session, starts the
service call, and waits until PostgreSQL reports the call blocked (`pg_locks`,
not granted). Only then does the holder lock everything the call touches after
the order: its lines, its approval request and steps, its quotations and its
dispatch lines. A call that takes the order first holds none of those yet, so the
holder gets them, commits, and the call follows. A call that locked any of them
before the order would hold it while waiting on the holder, and the holder would
wait on it: a deadlock, 40P01.

**The races** assert that the second call really waited on the first
(`pg_locks` again), so a run where the calls happened not to overlap fails
instead of passing as a sequential run would.

Every session is rolled back and closed in a `finally`: an unexpected error must
fail the test, not leave a row lock that hangs the teardown.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.config import get_settings
from api.db.session import enter_role
from api.errors import ApiError
from api.schemas import orders as sch
from api.services import approvals as approval_service
from api.services import orders as service
from tests.api import test_order_endpoints as endpoints

shop = endpoints.shop
Shop = endpoints.Shop

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

# how long to wait for PostgreSQL to report a session blocked, through the tunnel
BLOCK_TIMEOUT = 15.0

Work = Callable[[AsyncSession], Awaitable[Any]]
Sessions = Callable[[], AsyncSession]

_SCOPES = {"sales_orders": "global", "leads": "global", "quotations": "global",
           "pricing": "global"}


async def _as(s: AsyncSession, user_id: str) -> None:
    """What get_db does: the claim, then app_role, transaction-local."""
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})
    await enter_role(s, "app_role")


def _caller(shop: Shop, role: str) -> Caller:
    return Caller(shop.ids[role], shop.office, None, scopes=_SCOPES)


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


async def _call(s: AsyncSession, user_id: str, work: Work, *,
                pid: asyncio.Future[int] | None = None,
                after: asyncio.Event | None = None,
                ready: asyncio.Event | None = None,
                before_commit: Callable[[], Awaitable[None]] | None = None) -> dict[str, Any]:
    """One service call on its own connection under the user's claim. `pid`
    receives the backend's pid before the call starts; `after` is waited on
    first; `ready` is set once the call has returned with its locks held;
    `before_commit` runs between the call and the commit."""
    try:
        if after is not None:
            await after.wait()
        await _as(s, user_id)
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


def _outcome(got: dict[str, Any]) -> str:
    return "ok" if "ok" in got else str(got["error"])


# ── the work each mutation does, through the service ─────────────────────────

def _patch(shop: Shop, order_id: str) -> Work:
    async def work(s: AsyncSession) -> Any:
        return await service.patch_order(s, _caller(shop, "field_officer"), order_id,
                                         sch.OrderPatch(delivery_address="Plot 4, Vadod"),
                                         get_settings())
    return work


def _put_lines(shop: Shop, order_id: str) -> Work:
    body = sch.OrderLinesReplace.model_validate(
        {"lines": [{"product_id": shop.product, "qty": "12", "discount_pct": "10"}]})

    async def work(s: AsyncSession) -> Any:
        return await service.replace_lines(s, _caller(shop, "field_officer"), order_id, body,
                                           get_settings())
    return work


def _submit(shop: Shop, order_id: str) -> Work:
    async def work(s: AsyncSession) -> Any:
        return await service.submit_order(s, _caller(shop, "field_officer"), order_id,
                                          sch.SubmitRequest(), get_settings())
    return work


def _cancel(shop: Shop, order_id: str) -> Work:
    async def work(s: AsyncSession) -> Any:
        return await service.cancel_order(s, _caller(shop, "field_officer"), order_id,
                                          sch.RemarkRequest(remark="Party withdrew"),
                                          get_settings())
    return work


def _decide(shop: Shop, role: str, step_id: str) -> Work:
    async def work(s: AsyncSession) -> Any:
        return await approval_service.decide(
            s, _caller(shop, role), step_id,
            sch.DecisionRequest(decision="approve", remark="Payment seen"))
    return work


def _dispatch(shop: Shop, order_id: str, line_id: str, qty: str) -> Work:
    body = sch.DispatchCreate.model_validate({
        "dispatched_at": dt.datetime.now(dt.UTC).isoformat(),
        "lines": [{"order_line_id": line_id, "qty": qty}]})

    async def work(s: AsyncSession) -> Any:
        return await service.record_dispatch(s, _caller(shop, "dispatch_manager"), order_id, body)
    return work


def _claim(shop: Shop, quotation_id: str) -> Work:
    body = sch.OrderCreate.model_validate({"quotation_ids": [quotation_id]})

    async def work(s: AsyncSession) -> Any:
        return await service.create_order(s, _caller(shop, "field_officer"), body,
                                          get_settings())
    return work


# ── building the order each case starts from, over the API ───────────────────

async def _draft(client: httpx.AsyncClient, shop: Shop) -> dict:
    h = await endpoints._as(client, shop, "field_officer")
    return await endpoints._create(client, h, endpoints._direct(shop))


async def _submitted(client: httpx.AsyncClient, shop: Shop) -> dict:
    h = await endpoints._as(client, shop, "field_officer")
    return await endpoints._submit(client, h, (await _draft(client, shop))["id"])


async def _approved(client: httpx.AsyncClient, shop: Shop) -> dict:
    return await endpoints._approve_all(client, shop, await _submitted(client, shop))


async def _status(sessions: Sessions, order_id: str) -> str:
    s = sessions()
    try:
        return str((await s.execute(text(
            "SELECT status::text FROM sales_order WHERE id = CAST(:o AS uuid)"),
            {"o": order_id})).scalar_one())
    finally:
        await s.rollback()
        await s.close()


# ── the lock order ───────────────────────────────────────────────────────────

# everything an FS-011 path locks after the order (spec 5, lock order)
_AFTER_THE_ORDER = (
    "SELECT 1 FROM order_line WHERE sales_order_id = CAST(:o AS uuid) FOR UPDATE",
    "SELECT 1 FROM approval_request WHERE doc_type = 'sales_order' "
    "AND entity_id = CAST(:o AS uuid) FOR UPDATE",
    "SELECT 1 FROM approval_step s JOIN approval_request q ON q.id = s.request_id "
    "WHERE q.doc_type = 'sales_order' AND q.entity_id = CAST(:o AS uuid) FOR UPDATE OF s",
    "SELECT 1 FROM quotation q JOIN order_quotation oq ON oq.quotation_id = q.id "
    "WHERE oq.sales_order_id = CAST(:o AS uuid) FOR UPDATE OF q",
    "SELECT 1 FROM dispatch_line dl JOIN dispatch d ON d.id = dl.dispatch_id "
    "WHERE d.sales_order_id = CAST(:o AS uuid) FOR UPDATE OF dl",
)


@pytest.mark.parametrize("mutation", ["patch", "put_lines", "submit", "decision", "cancel",
                                      "dispatch"])
async def test_the_mutation_takes_the_order_before_anything_under_it(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, mutation: str) -> None:
    """Spec 5's lock order. Another session holds the order; the mutation starts
    and PostgreSQL reports it blocked; the holder then locks the order's lines,
    request, steps, quotations and dispatch lines. Order first: both finish.
    Anything first: 40P01."""
    if mutation in ("patch", "put_lines", "submit"):
        order = await _draft(client, shop)
    elif mutation in ("decision", "cancel"):
        order = await _submitted(client, shop)
    else:
        order = await _approved(client, shop)
    oid = order["id"]
    user, work = {
        "patch": ("field_officer", lambda: _patch(shop, oid)),
        "put_lines": ("field_officer", lambda: _put_lines(shop, oid)),
        "submit": ("field_officer", lambda: _submit(shop, oid)),
        "cancel": ("field_officer", lambda: _cancel(shop, oid)),
        "decision": (order["approval"]["steps"][0]["role"] if order.get("approval") else "",
                     lambda: _decide(shop, order["approval"]["steps"][0]["role"],
                                     order["approval"]["steps"][0]["id"])),
        "dispatch": ("dispatch_manager",
                     lambda: _dispatch(shop, oid, order["lines"][0]["id"], "2")),
    }[mutation]

    holder = sessions()
    held: dict[str, str] = {}
    try:
        await holder.execute(text(
            "SELECT 1 FROM sales_order WHERE id = CAST(:o AS uuid) FOR UPDATE"), {"o": oid})
        pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        call = asyncio.create_task(_call(sessions(), shop.ids[user], work(), pid=pid))
        assert await _blocked(sessions, await pid), "the mutation never waited on the order"
        try:
            for stmt in _AFTER_THE_ORDER:
                await holder.execute(text(stmt), {"o": oid})
            await holder.commit()
            held["rest"] = "ok"
        except DBAPIError as exc:
            held["rest"] = str(getattr(exc.orig, "sqlstate", ""))
        got = await call
    finally:
        await holder.rollback()
        await holder.close()
    assert held["rest"] == "ok" and "ok" in got, (held, got)


async def test_a_step_locked_before_its_order_deadlocks_which_order_first_prevents(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """The hazard the test above guards against, held as an executed fact: A
    takes a step, B takes the order, then each asks for the other's row. 40P01.
    Without this, the proof above could pass because the holder's statements
    never contend with anything."""
    order = await _submitted(client, shop)
    oid, step = order["id"], order["approval"]["steps"][0]["id"]
    a, b = sessions(), sessions()
    a_has_step, b_has_order = asyncio.Event(), asyncio.Event()

    async def step_then_order() -> str:
        await a.execute(text("SELECT 1 FROM approval_step WHERE id = CAST(:s AS uuid) FOR UPDATE"),
                        {"s": step})
        a_has_step.set()
        await b_has_order.wait()
        try:
            await a.execute(text(
                "SELECT 1 FROM sales_order WHERE id = CAST(:o AS uuid) FOR UPDATE"), {"o": oid})
        except DBAPIError as exc:
            return str(getattr(exc.orig, "sqlstate", ""))
        await a.commit()
        return "ok"

    async def order_then_step() -> str:
        await a_has_step.wait()
        await b.execute(text("SELECT 1 FROM sales_order WHERE id = CAST(:o AS uuid) FOR UPDATE"),
                        {"o": oid})
        b_has_order.set()
        try:
            await b.execute(text(
                "SELECT 1 FROM approval_step WHERE id = CAST(:s AS uuid) FOR UPDATE"), {"s": step})
        except DBAPIError as exc:
            return str(getattr(exc.orig, "sqlstate", ""))
        await b.commit()
        return "ok"

    try:
        got = await asyncio.gather(step_then_order(), order_then_step())
    finally:
        for s in (a, b):
            await s.rollback()
            await s.close()
    assert sorted(got) == ["40P01", "ok"], got


# ── one outcome per race ─────────────────────────────────────────────────────

async def _race(sessions: Sessions, first: tuple[str, Work],
                second: tuple[str, Work]) -> tuple[list[dict[str, Any]], bool]:
    """`first` runs and holds its locks; `second` starts; `first` commits only
    once PostgreSQL reports `second` blocked. Returns both outcomes and whether
    the second really waited."""
    ready = asyncio.Event()
    second_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    waited: dict[str, bool] = {}

    async def hold_until_second_waits() -> None:
        waited["second"] = await _blocked(sessions, await second_pid)

    got = await asyncio.gather(
        _call(sessions(), first[0], first[1], ready=ready, before_commit=hold_until_second_waits),
        _call(sessions(), second[0], second[1], after=ready, pid=second_pid),
    )
    return list(got), waited.get("second", False)


async def test_two_orders_claiming_one_quotation_leave_it_on_one(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Rule 4: the second create waits on the first's claim, then finds the
    quotation on a live order."""
    h = await endpoints._as(client, shop, "field_officer")
    q = await endpoints._accepted_quotation(client, shop, h)
    me = shop.ids["field_officer"]
    got, waited = await _race(sessions, (me, _claim(shop, q["id"])), (me, _claim(shop, q["id"])))
    assert waited, "the second claim did not wait on the first: the race was not a race"
    assert sorted(_outcome(g) for g in got) == ["ok", "quotation_on_order"], got
    s = sessions()
    try:
        live = (await s.execute(text(
            "SELECT count(*) FROM order_quotation oq "
            "WHERE oq.quotation_id = CAST(:q AS uuid) AND oq.released_at IS NULL"),
            {"q": q["id"]})).scalar_one()
    finally:
        await s.rollback()
        await s.close()
    assert live == 1


async def test_two_dispatches_racing_one_line_never_ship_more_than_was_ordered(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Edge case 9: ten ordered, two dispatches of six. The second waits on the
    order, then counts the first's six and is refused."""
    order = await _approved(client, shop)
    line = order["lines"][0]["id"]
    who = shop.ids["dispatch_manager"]
    got, waited = await _race(sessions, (who, _dispatch(shop, order["id"], line, "6")),
                              (who, _dispatch(shop, order["id"], line, "6")))
    assert waited, "the second dispatch did not wait on the first"
    assert sorted(_outcome(g) for g in got) == ["ok", "over_open_quantity"], got
    s = sessions()
    try:
        sent = (await s.execute(text(
            "SELECT coalesce(sum(dl.qty), 0) FROM dispatch_line dl JOIN dispatch d "
            "ON d.id = dl.dispatch_id WHERE dl.order_line_id = CAST(:l AS uuid) "
            "AND d.voided_at IS NULL"), {"l": line})).scalar_one()
    finally:
        await s.rollback()
        await s.close()
    assert sent == 6


async def test_a_decision_that_loses_to_a_cancel_is_refused_as_closed(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Spec 5, apply_approval_outcome: the decision waits on the cancel's order
    lock, then finds the request closed. It never approves a cancelled order."""
    order = await _submitted(client, shop)
    step = order["approval"]["steps"][0]
    got, waited = await _race(
        sessions, (shop.ids["field_officer"], _cancel(shop, order["id"])),
        (shop.ids[step["role"]], _decide(shop, step["role"], step["id"])))
    assert waited, "the decision did not wait on the cancel"
    assert [_outcome(g) for g in got] == ["ok", "request_closed"], got
    assert await _status(sessions, order["id"]) == "cancelled"
