"""The three mechanisms in migration 003 that only exist under concurrency.

FS-001 section 10 asks for these by name: "two concurrent requests at nine issued
do not both succeed", "two literally simultaneous calls produce one lineage", "two
concurrent calls with the same p_family_id produce one auth.family_revoked row,
not two".

**Every other test in this suite would pass with the locks removed.** Two calls in
one transaction never contend, so a sequential test proves the counting logic and
nothing about the serialisation. That is the defect shape this feature has
produced six times already: a mechanism reasoned about and never executed.

Each test forces genuine overlap rather than hoping for it. The first connection
holds its transaction open past the call; the second starts while it is still
open, so the second either blocks on the lock or does not - and if it does not,
the assertion fails. Deterministic in both directions.

These commit, so they clean up after themselves rather than relying on a rollback.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

# 007 binds a session to the token_version the credential was verified against
# (FS-006 rule 6). The fixtures mint with the row's own, read in the same statement.
_V = ", (SELECT token_version FROM app_user WHERE id = CAST(:u AS uuid)))"


# Long enough that the second connection is provably inside its call while the
# first still holds the lock, short enough not to slow the suite.
HOLD = 0.6
STAGGER = 0.15


@dataclass
class Actor:
    user_id: str
    mobile: str


@pytest_asyncio.fixture
async def actor(sessions: Callable[[], AsyncSession]) -> AsyncIterator[Actor]:
    """A committed partner user, visible to every connection, removed afterwards."""
    tag = uuid.uuid4().hex[:10]
    mobile = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    s = sessions()
    territory = (await s.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"conc_{tag}"})).scalar_one()
    role = (await s.execute(text(
        "INSERT INTO role (code, name, level, is_portal) "
        "VALUES (:c, 'Dealer', 2, true) RETURNING id"),
        {"c": f"conc_dealer_{tag}"})).scalar_one()
    partner = (await s.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'Concurrency Dealer', :t, 'dealer') RETURNING id"),
        {"c": f"CONC-{tag}", "t": territory})).scalar_one()
    user = (await s.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "VALUES ('partner_user', :m, 'Concurrency', :r, :p) RETURNING id"),
        {"m": mobile, "r": role, "p": partner})).scalar_one()
    await s.commit()

    try:
        yield Actor(str(user), mobile)
    finally:
        c = sessions()
        for stmt in (
            "DELETE FROM login_attempt WHERE identifier = CAST(:m AS citext)",
            "DELETE FROM notification_outbox WHERE recipient = :m",
            "DELETE FROM activity_event WHERE entity_id = CAST(:u AS uuid)",
            "DELETE FROM app_user WHERE id = CAST(:u AS uuid)",
            "DELETE FROM role WHERE id = CAST(:r AS uuid)",
            "DELETE FROM channel_partner WHERE id = CAST(:p AS uuid)",
            "DELETE FROM territory WHERE id = CAST(:t AS uuid)",
        ):
            await c.execute(text(stmt),
                            {"m": mobile, "u": str(user), "r": str(role),
                             "p": str(partner), "t": str(territory)})
        await c.commit()
        # audit_log rows stay. They are append-only with no delete path, which is
        # the design (Proposed-Schema.md section 15), and they name rows that no
        # longer exist on purpose.


async def _hold_then_commit(session: AsyncSession, sql: str, params: dict) -> object:
    """Run one statement and keep the transaction open past it."""
    result = (await session.execute(text(sql), params)).scalar_one()
    await asyncio.sleep(HOLD)
    await session.commit()
    return result


async def _after(delay: float, session: AsyncSession, sql: str, params: dict) -> object:
    """Start inside the first transaction's window, then run and commit."""
    await asyncio.sleep(delay)
    result = (await session.execute(text(sql), params)).scalar_one()
    await session.commit()
    return result


async def test_two_concurrent_otp_requests_cannot_both_pass_the_cap(
        sessions: Callable[[], AsyncSession], actor: Actor) -> None:
    """R6-3. Section 5.1 claimed the single composite function made the cap check
    and the issue record atomic. It does not - one function is one round trip, not
    one lock - so both callers read the same count and a cap of three admits four.

    pg_advisory_xact_lock is what actually serialises them. Remove it and this test
    fails while every sequential OTP test still passes.
    """
    call = "SELECT auth_issue_otp_challenge(:m, '10.0.0.1', :c, 3)"

    first = sessions()
    for _ in range(2):
        assert (await first.execute(text(call),
                                    {"m": actor.mobile, "c": "111111"})).scalar_one() is True
    await first.commit()

    a, b = sessions(), sessions()
    got = await asyncio.gather(
        _hold_then_commit(a, call, {"m": actor.mobile, "c": "222222"}),
        _after(STAGGER, b, call, {"m": actor.mobile, "c": "333333"}),
    )
    assert sorted(got, key=bool) == [False, True], f"cap of 3 admitted {sum(got) + 2}"

    check = sessions()
    issued = (await check.execute(text(
        "SELECT count(*) FROM login_attempt WHERE identifier = CAST(:m AS citext) "
        "AND kind = 'otp_issue'"), {"m": actor.mobile})).scalar_one()
    sent = (await check.execute(text(
        "SELECT count(*) FROM notification_outbox WHERE recipient = :m"),
        {"m": actor.mobile})).scalar_one()
    await check.rollback()
    assert issued == 3 and sent == 3, f"{issued} issued, {sent} sent, cap is 3"


async def test_two_concurrent_claims_on_one_token_yield_one_winner(
        sessions: Callable[[], AsyncSession], actor: Actor) -> None:
    """Section 8.2's mechanism, executed. The losing UPDATE does not read zero rows
    - it blocks on the winner's row lock and wakes after the winner commits, which
    is why the overlapping case recovers the same way the sequential one does.

    Section 8.2a records the trace this asserts.
    """
    token = uuid.uuid4().hex
    setup = sessions()
    await setup.execute(
        text("SELECT auth_create_session(CAST(:u AS uuid), :h, :f, interval '30 days', "
             "'ua', '10.0.0.1', 'otp'" + _V),
        {"u": actor.user_id, "h": token, "f": str(uuid.uuid4())})
    await setup.commit()

    call = "SELECT outcome FROM auth_claim_refresh(:h)"
    a, b = sessions(), sessions()
    got = await asyncio.gather(
        _hold_then_commit(a, call, {"h": token}),
        _after(STAGGER, b, call, {"h": token}),
    )
    assert sorted(got) == ["claimed", "not_claimed"], got

    check = sessions()
    used = (await check.execute(text(
        "SELECT used_at IS NOT NULL FROM session WHERE refresh_token_hash = :h"),
        {"h": token})).scalar_one()
    await check.rollback()
    assert used is True, "the winner's claim did not commit"


async def test_two_concurrent_family_revocations_emit_one_event(
        sessions: Callable[[], AsyncSession], actor: Actor) -> None:
    """EC-20. An attacker replays right after the legitimate rotation, so both
    requests classify as reused and both call auth_revoke_sessions within
    milliseconds. The UPDATE ... WHERE revoked_at IS NULL RETURNING idiom is what
    makes "one event" true under that, not only in sequence: the loser matches zero
    rows and emits nothing.
    """
    family = str(uuid.uuid4())
    setup = sessions()
    for _ in range(3):
        await setup.execute(
            text("SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
                 "interval '30 days', 'ua', '10.0.0.1', NULL" + _V),
            {"u": actor.user_id, "h": uuid.uuid4().hex, "f": family})
    await setup.commit()

    call = "SELECT auth_revoke_sessions(NULL, CAST(:f AS uuid))"
    a, b = sessions(), sessions()
    got = await asyncio.gather(
        _hold_then_commit(a, call, {"f": family}),
        _after(STAGGER, b, call, {"f": family}),
    )
    assert sorted(got) == [0, 3], f"the family was revoked {got} times"

    check = sessions()
    events = (await check.execute(text(
        "SELECT count(*) FROM activity_event WHERE entity_id = CAST(:u AS uuid) "
        "AND kind = 'auth.family_revoked'"), {"u": actor.user_id})).scalar_one()
    alive = (await check.execute(text(
        "SELECT count(*) FROM session WHERE family_id = CAST(:f AS uuid) "
        "AND revoked_at IS NULL"), {"f": family})).scalar_one()
    await check.rollback()
    assert events == 1, f"{events} timeline rows for one revocation"
    assert alive == 0


# ── the three the cross-vendor review found ──────────────────────────────────

async def test_a_revocation_racing_a_rotation_leaves_nothing_live(
        sessions: Callable[[], AsyncSession], actor: Actor) -> None:
    """X-1. Reuse detection revoked a family while a rotation was in flight, and
    the successor minted meanwhile survived.

    The revocation blocked on the predecessor's row lock, woke after the rotation
    committed, and its UPDATE's snapshot never included the new row - so a family
    reported as revoked still held one live refresh token, which is precisely the
    thing ADR-025 calls the only cheap defence against a stolen one.

    The family-scoped advisory lock is what fixes it: rotation holds it from the
    claim through the insert to COMMIT, so the revocation starts after rather than
    during. Remove it and the successor survives again.
    """
    family = str(uuid.uuid4())
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    setup = sessions()
    await setup.execute(
        text("SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
             "interval '30 days', 'ua', '10.0.0.1', 'password'" + _V),
        {"u": actor.user_id, "h": first, "f": family})
    await setup.commit()

    rotator, revoker = sessions(), sessions()

    async def rotate() -> None:
        await rotator.execute(text("SELECT outcome FROM auth_claim_refresh(:h)"), {"h": first})
        await asyncio.sleep(HOLD)
        await rotator.execute(
            text("SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
                 "interval '30 days', 'ua', '10.0.0.1', NULL" + _V),
            {"u": actor.user_id, "h": second, "f": family})
        await rotator.commit()

    async def revoke() -> None:
        await asyncio.sleep(STAGGER)
        await revoker.execute(text("SELECT auth_revoke_sessions(NULL, CAST(:f AS uuid))"),
                              {"f": family})
        await revoker.commit()

    await asyncio.gather(rotate(), revoke())

    check = sessions()
    live = (await check.execute(text(
        "SELECT count(*) FROM session WHERE family_id = CAST(:f AS uuid) "
        "AND revoked_at IS NULL"), {"f": family})).scalar_one()
    await check.rollback()
    assert live == 0, "a refresh token survived the revocation of its own family"


async def test_a_token_version_bump_during_rotation_still_kills_the_successor(
        sessions: Callable[[], AsyncSession], actor: Actor) -> None:
    """X-2. An offboarding landing between the claim and the successor's creation
    was defeated: the claim validated version 0, the bump committed, and
    auth_create_session then re-read and stamped version 1 onto the new session -
    so the session the bump existed to kill refreshed cleanly forever after.

    FOR SHARE on the user row is what fixes it. The bump waits for the rotation to
    commit, the successor keeps the version that was validated, and the bump then
    invalidates it on its next use.
    """
    family = str(uuid.uuid4())
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    setup = sessions()
    await setup.execute(text("UPDATE app_user SET token_version = 0 WHERE id = CAST(:u AS uuid)"),
                        {"u": actor.user_id})
    await setup.execute(
        text("SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
             "interval '30 days', 'ua', '10.0.0.1', 'password'" + _V),
        {"u": actor.user_id, "h": first, "f": family})
    await setup.commit()

    rotator, admin = sessions(), sessions()

    async def rotate() -> None:
        await rotator.execute(text("SELECT outcome FROM auth_claim_refresh(:h)"), {"h": first})
        await asyncio.sleep(HOLD)
        await rotator.execute(
            text("SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
                 "interval '30 days', 'ua', '10.0.0.1', NULL" + _V),
            {"u": actor.user_id, "h": second, "f": family})
        await rotator.commit()

    async def offboard() -> None:
        await asyncio.sleep(STAGGER)
        await admin.execute(text(
            "UPDATE app_user SET token_version = token_version + 1 WHERE id = CAST(:u AS uuid)"),
            {"u": actor.user_id})
        await admin.commit()

    await asyncio.gather(rotate(), offboard())

    check = sessions()
    outcome = (await check.execute(text("SELECT outcome FROM auth_claim_refresh(:h)"),
                                   {"h": second})).scalar_one()
    await check.commit()
    assert outcome == "session_revoked", "the offboarding lost the race and the session lived"


async def test_two_concurrent_moves_cannot_form_a_cycle(
        sessions: Callable[[], AsyncSession]) -> None:
    """X-4. Each cycle check read the pre-move closure, so both passed and both
    committed: A under B and B under A, with no error raised. The closure then held
    only self and depth-one rows while the parent pointers formed a loop, so
    hierarchy traversal and closure-based authorization disagreed permanently.

    One transaction-scoped lock per tree, taken before anything reads the closure.
    """
    tag = uuid.uuid4().hex[:10]
    setup = sessions()
    await setup.execute(text("INSERT INTO org_unit (name, role_level) VALUES (:a, 1), (:b, 1)"),
                        {"a": f"A{tag}", "b": f"B{tag}"})
    await setup.commit()
    got = (await (sessions()).execute(text(
        "SELECT id, name FROM org_unit WHERE name IN (:a, :b) ORDER BY name"),
        {"a": f"A{tag}", "b": f"B{tag}"})).all()
    node_a, node_b = got[0][0], got[1][0]

    one, two = sessions(), sessions()
    refused: list[str] = []

    async def move(session: AsyncSession, child: str, parent: str, delay: float) -> None:
        await asyncio.sleep(delay)
        try:
            await session.execute(text("UPDATE org_unit SET parent_id = :p WHERE id = :c"),
                                  {"p": parent, "c": child})
            await asyncio.sleep(HOLD)
            await session.commit()
        except DBAPIError as exc:
            refused.append(str(exc)[:80])
            await session.rollback()

    try:
        await asyncio.gather(move(one, node_a, node_b, 0.0),
                             move(two, node_b, node_a, STAGGER))

        check = sessions()
        parents = dict((await check.execute(text(
            "SELECT id, parent_id FROM org_unit WHERE id IN (:a, :b)"),
            {"a": node_a, "b": node_b})).all())
        await check.rollback()
        assert parents != {node_a: node_b, node_b: node_a}, "a cycle committed"
        assert refused, "the second move should have been refused, not silently allowed"
    finally:
        cleanup = sessions()
        await cleanup.execute(text("UPDATE org_unit SET parent_id = NULL WHERE id IN (:a, :b)"),
                              {"a": node_a, "b": node_b})
        await cleanup.execute(text("DELETE FROM org_unit WHERE id IN (:a, :b)"),
                              {"a": node_a, "b": node_b})
        await cleanup.commit()
