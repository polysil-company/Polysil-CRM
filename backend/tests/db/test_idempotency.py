"""api/idempotency.py against 16.14 through PgBouncer (AC-IDEM 1-13).

run_idempotent takes (db, ...), so it is driven here against a session that has the
caller's claim set and app_role entered, the same shape as the policy tests. The
concurrent case (IDEM-5) uses two committed sessions ordered by an event, because
one rolled-back transaction never contends with itself.

The store step is an UPDATE of the reserved row, which migration 006 grants and
policies; without it this file is 42501, which is the point of B-1.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from api.errors import ApiError, IdempotencyConflictError, NotFoundError
from api.idempotency import Outcome, payload_digest, run_idempotent
from tests.db.conftest import Fixtures, make_staff

pytestmark = [pytest.mark.db, pytest.mark.rls]

OK_BODY = {"data": {"ok": True}}


def test_the_digest_is_order_independent() -> None:
    assert payload_digest({"a": 1, "b": 2}) == payload_digest({"b": 2, "a": 1})
    assert payload_digest({"a": 1}) != payload_digest({"a": 2})


async def _as(db: AsyncSession, user_id: str) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id)})
    await enter_role(db, "app_role")


def _work(status: int = 201, body: dict | None = None, calls: list | None = None):
    async def work() -> tuple[int, dict]:
        if calls is not None:
            calls.append(1)
        return status, body if body is not None else OK_BODY
    return work


async def test_a_first_call_runs_the_work_and_stores_the_response(
        db: AsyncSession, ids: Fixtures) -> None:
    me = await make_staff(db, ids, email=ids.unique("i") + "@polysil.in")
    await _as(db, me)
    calls: list[int] = []
    out = await run_idempotent(db, key="k1", user_id=str(me), route="POST /leads",
                               payload_hash="h", work=_work(calls=calls))
    assert out == Outcome(201, OK_BODY, replayed=False)
    assert calls == [1]
    row = (await db.execute(text(
        "SELECT state, status_code FROM idempotency_record WHERE key='k1'"))).one()
    assert row.state == "done" and row.status_code == 201


async def test_the_same_key_and_payload_replays_without_rerunning(
        db: AsyncSession, ids: Fixtures) -> None:
    me = await make_staff(db, ids, email=ids.unique("i") + "@polysil.in")
    await _as(db, me)
    calls: list[int] = []
    first = await run_idempotent(db, key="k", user_id=str(me), route="r",
                                 payload_hash="h", work=_work(body={"data": 1}, calls=calls))
    second = await run_idempotent(db, key="k", user_id=str(me), route="r",
                                  payload_hash="h", work=_work(body={"data": 999}, calls=calls))
    assert first.replayed is False and second.replayed is True
    assert second.body == {"data": 1}          # the stored response, not the second work's
    assert calls == [1]                        # the work ran once


async def test_the_same_key_with_a_different_payload_conflicts(
        db: AsyncSession, ids: Fixtures) -> None:
    me = await make_staff(db, ids, email=ids.unique("i") + "@polysil.in")
    await _as(db, me)
    await run_idempotent(db, key="k", user_id=str(me), route="r",
                         payload_hash="h1", work=_work())
    with pytest.raises(IdempotencyConflictError):
        await run_idempotent(db, key="k", user_id=str(me), route="r",
                             payload_hash="h2", work=_work())


async def test_the_key_is_scoped_to_the_user(db: AsyncSession, ids: Fixtures) -> None:
    a = await make_staff(db, ids, email=ids.unique("a") + "@polysil.in")
    b = await make_staff(db, ids, email=ids.unique("b") + "@polysil.in")
    await _as(db, a)
    out_a = await run_idempotent(db, key="shared", user_id=str(a), route="r",
                                 payload_hash="h", work=_work())
    await _as(db, b)
    out_b = await run_idempotent(db, key="shared", user_id=str(b), route="r",
                                 payload_hash="h", work=_work())
    assert out_a.replayed is False and out_b.replayed is False   # different records


async def test_a_handler_4xx_is_stored_and_its_writes_roll_back(
        db: AsyncSession, ids: Fixtures) -> None:
    """IDEM-7, 11, 12: a 4xx is returned not raised, the record survives, and the
    business writes inside the savepoint are gone."""
    me = await make_staff(db, ids, email=ids.unique("i") + "@polysil.in")
    await _as(db, me)

    async def work() -> tuple[int, dict]:
        await db.execute(text(
            "INSERT INTO activity_event (entity_type, kind, actor_id) "
            "VALUES ('probe', 'idem.test', (SELECT app_current_user_id()))"))
        raise NotFoundError()

    out = await run_idempotent(db, key="k", user_id=str(me), route="r",
                               payload_hash="h", work=work)
    assert out.status_code == 404 and out.body["error"]["code"] == "not_found"
    assert not out.replayed
    stored = (await db.execute(text(
        "SELECT status_code FROM idempotency_record WHERE key='k'"))).scalar_one()
    assert stored == 404
    strays = (await db.execute(text(
        "SELECT count(*) FROM activity_event WHERE kind='idem.test'"))).scalar_one()
    assert strays == 0, "the savepoint did not roll the business write back"
    # and it replays the stored 404
    replay = await run_idempotent(db, key="k", user_id=str(me), route="r",
                                  payload_hash="h", work=work)
    assert replay.replayed and replay.status_code == 404


async def test_a_5xx_stores_nothing_so_a_retry_is_a_first_attempt(
        db: AsyncSession, ids: Fixtures) -> None:
    """IDEM-6, 13. A 5xx propagates; the reserved row rolls back with the request.
    Simulated here with a savepoint so the session stays usable after the raise."""
    me = await make_staff(db, ids, email=ids.unique("i") + "@polysil.in")
    await _as(db, me)

    class ServerError(ApiError):
        status_code = 500
        code = "server_error"

    async def work() -> tuple[int, dict]:
        raise ServerError()

    # begin_nested() stands in for get_db's request transaction: the 5xx
    # propagates out of it and it rolls back, taking the reserved row with it.
    with pytest.raises(ServerError):
        async with db.begin_nested():
            await run_idempotent(db, key="k5", user_id=str(me), route="r",
                                 payload_hash="h", work=work)
    n = (await db.execute(text(
        "SELECT count(*) FROM idempotency_record WHERE key='k5'"))).scalar_one()
    assert n == 0


@pytest_asyncio.fixture
async def committed_staff(sessions: Callable[[], AsyncSession]) -> AsyncIterator[dict[str, str]]:
    """A committed staff user, for the two-session concurrency test. Removed after."""
    tag = uuid.uuid4().hex[:8]
    s = sessions()
    terr = (await s.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"idem_{tag}"})).scalar_one()
    org = (await s.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"idem_{tag}", "t": terr})).scalar_one()
    role = (await s.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'x', 2) RETURNING id"),
        {"c": f"idem_{tag}"})).scalar_one()
    user = (await s.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', :r, :o) RETURNING id"),
        {"e": f"idem_{tag}@polysil.in", "r": role, "o": org})).scalar_one()
    await s.commit()
    ids_ = {"user": str(user), "role": str(role), "org": str(org), "terr": str(terr)}
    try:
        yield ids_
    finally:
        c = sessions()
        for stmt, param in (
            ("DELETE FROM idempotency_record WHERE user_id = CAST(:v AS uuid)", "user"),
            ("DELETE FROM app_user WHERE id = CAST(:v AS uuid)", "user"),
            ("DELETE FROM role WHERE id = CAST(:v AS uuid)", "role"),
            ("DELETE FROM org_unit WHERE id = CAST(:v AS uuid)", "org"),
            ("DELETE FROM territory WHERE id = CAST(:v AS uuid)", "terr"),
        ):
            await c.execute(text(stmt), {"v": ids_[param]})
        await c.commit()


async def test_two_concurrent_calls_run_the_work_once(
        sessions: Callable[[], AsyncSession], committed_staff: dict[str, str]) -> None:
    """IDEM-5: the loser blocks on the winner's uncommitted reserve, then reads the
    stored response rather than running the work a second time."""
    user = committed_staff["user"]
    ran: list[str] = []
    held = asyncio.Event()

    async def winner(s: AsyncSession) -> Outcome:
        await _as(s, user)

        async def work() -> tuple[int, dict]:
            ran.append("w")
            held.set()
            await asyncio.sleep(0.6)     # hold the reserve uncommitted
            return 201, {"data": "winner"}
        out = await run_idempotent(s, key="race", user_id=user, route="r",
                                   payload_hash="h", work=work)
        await s.commit()
        return out

    async def loser(s: AsyncSession) -> Outcome:
        await held.wait()
        await asyncio.sleep(0.05)
        await _as(s, user)

        async def work() -> tuple[int, dict]:
            ran.append("l")
            return 201, {"data": "loser"}
        out = await run_idempotent(s, key="race", user_id=user, route="r",
                                   payload_hash="h", work=work)
        await s.commit()
        return out

    a, b = sessions(), sessions()
    out_w, out_l = await asyncio.gather(winner(a), loser(b))
    assert ran == ["w"], f"the work ran more than once: {ran}"
    assert out_w.body == {"data": "winner"}
    assert out_l.replayed and out_l.body == {"data": "winner"}


async def test_refuses_a_session_with_pending_orm_state(db: AsyncSession, ids: Fixtures) -> None:
    """ISS-070 (FS-003 4, cross-vendor R-2): begin_nested() flushes pending ORM state
    first, so an object added before the call would land outside the savepoint and
    survive a replay or a business-4xx rollback. The helper refuses loudly."""
    import sqlalchemy as sa
    from sqlalchemy.orm import DeclarativeBase, mapped_column

    class _Base(DeclarativeBase):
        pass

    class _Pending(_Base):   # a throwaway mapping over an existing table; never flushed
        __tablename__ = "mis_system"
        id = mapped_column(sa.Uuid, primary_key=True)
        code = mapped_column(sa.String)
        name = mapped_column(sa.String)

    me = await make_staff(db, ids, email=ids.unique("clean") + "@polysil.in")
    await _as(db, me)
    db.add(_Pending(id=uuid.uuid4(), code="pending", name="pending"))
    try:
        with pytest.raises(RuntimeError, match="clean session"):
            await run_idempotent(db, key="k-dirty", user_id=str(me), route="r",
                                 payload_hash="h", work=_work())
    finally:
        db.expunge_all()
