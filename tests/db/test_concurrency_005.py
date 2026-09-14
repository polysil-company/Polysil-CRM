"""The deactivation cascade against a concurrent refresh (FS-002 10, concurrency).

auth_claim_refresh() locks the session row first and the user row FOR SHARE
second. The cascade's first version updated app_user first and session second,
and the two deadlocked (executed, code review F-3): whichever lost returned 500,
so an offboarding did not happen or a user was signed out mid-rotation. The
cascade now takes the same order, and this holds it.

Two sessions, ordered by an event rather than a sleep (ISS-060). Commits, so it
cleans up after itself.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.db

HOLD = 0.8


@pytest_asyncio.fixture
async def dealer_user(sessions: Callable[[], AsyncSession]) -> AsyncIterator[dict[str, str]]:
    """A committed root dealer, a portal role, one user, one live session."""
    tag = uuid.uuid4().hex[:8]
    s = sessions()
    territory = (await s.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"conc5_{tag}"})).scalar_one()
    dealer = (await s.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'x', :t, 'dealer') RETURNING id"),
        {"c": f"C5-{tag}", "t": territory})).scalar_one()
    role = (await s.execute(text(
        "INSERT INTO role (code, name, level, is_portal) VALUES (:c, 'Dealer', 2, true) "
        "RETURNING id"), {"c": f"conc5_{tag}"})).scalar_one()
    user = (await s.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "VALUES ('partner_user', :m, 'x', :r, :p) RETURNING id"),
        {"m": "9166" + tag, "r": role, "p": dealer})).scalar_one()
    token = uuid.uuid4().hex
    await s.execute(text(
        "SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
        "interval '30 days', 'ua', '10.0.0.1', 'otp')"),
        {"u": user, "h": token, "f": str(uuid.uuid4())})
    await s.commit()
    ids = {"dealer": str(dealer), "user": str(user), "token": token}
    try:
        yield ids
    finally:
        c = sessions()
        for stmt, params in (
            ("DELETE FROM activity_event WHERE entity_id = CAST(:u AS uuid) "
             "OR entity_id = CAST(:d AS uuid)", {"u": ids["user"], "d": ids["dealer"]}),
            ("DELETE FROM session WHERE user_id = CAST(:u AS uuid)", {"u": ids["user"]}),
            ("DELETE FROM app_user WHERE id = CAST(:u AS uuid)", {"u": ids["user"]}),
            ("DELETE FROM role WHERE id = CAST(:r AS uuid)", {"r": str(role)}),
            ("DELETE FROM channel_partner WHERE id = CAST(:d AS uuid)", {"d": ids["dealer"]}),
            ("DELETE FROM territory WHERE id = CAST(:t AS uuid)", {"t": str(territory)}),
        ):
            await c.execute(text(stmt), params)
        await c.commit()


async def _refresh_and_hold(s: AsyncSession, token: str, held: asyncio.Event,
                            started: asyncio.Event) -> bool:
    """auth_claim_refresh()'s two locks, taken by hand with a gap between them:
    the session row (UPDATE used_at), then the user row FOR SHARE. Calling the
    function itself takes both before any other session can act, and then the
    reversed cascade order merely waits instead of deadlocking (cross-vendor P2).
    The statements are the function's own, 003_identity.py auth_claim_refresh."""
    user_id = (await s.execute(text(
        "UPDATE session SET used_at = now() WHERE refresh_token_hash = :h "
        "AND used_at IS NULL RETURNING user_id"), {"h": token})).scalar_one()
    held.set()
    await started.wait()
    await asyncio.sleep(0.5)  # T2 is inside the trigger by now
    active = (await s.execute(text(
        "SELECT is_active FROM app_user WHERE id = :u AND deleted_at IS NULL FOR SHARE"),
        {"u": user_id})).scalar_one()
    await asyncio.sleep(HOLD)
    await s.commit()
    return active


async def _deactivate_after(held: asyncio.Event, started: asyncio.Event, s: AsyncSession,
                            dealer: str) -> BaseException | None:
    await held.wait()
    started.set()
    try:
        await s.execute(text("UPDATE channel_partner SET is_active = false WHERE id = :d"),
                        {"d": dealer})
        await s.commit()
        return None
    except Exception as ex:  # the whole point is to see which error
        await s.rollback()
        return ex


async def test_a_refresh_and_a_deactivation_serialise_rather_than_deadlock(
        sessions: Callable[[], AsyncSession], dealer_user: dict[str, str]) -> None:
    """T1 holds the session row and has not yet taken the user row. T2
    deactivates the dealer while T1 is between the two: its cascade must wait on
    the session row, so T1's FOR SHARE is free and both finish. With the cascade
    in user-first order T2 takes the user row, T1's FOR SHARE waits on T2, T2's
    session update waits on T1: 40P01. Executed both ways."""
    a, b = sessions(), sessions()
    held, started = asyncio.Event(), asyncio.Event()
    active, err = await asyncio.gather(
        _refresh_and_hold(a, dealer_user["token"], held, started),
        _deactivate_after(held, started, b, dealer_user["dealer"]),
    )
    assert active is True, "T1 read the user before the cascade committed"
    assert err is None, f"the cascade failed against a concurrent refresh: {err!r}"

    check = sessions()
    row = (await check.execute(text(
        "SELECT u.is_active, "
        "(SELECT count(*) FROM session s WHERE s.user_id = u.id AND s.revoked_at IS NULL) "
        "FROM app_user u WHERE u.id = CAST(:u AS uuid)"), {"u": dealer_user["user"]})).one()
    await check.rollback()
    assert row[0] is False and row[1] == 0, row
