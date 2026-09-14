"""The two things about the channel tree that only exist under concurrency.

Both were executed during the FS-002a edge-case pass before the migration was
written. The first is a hole the migration closes. The second is a property the
migration inherits and documents.

These commit, so they clean up after themselves.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, InternalError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.db

HOLD = 0.8
STAGGER = 0.25


@pytest_asyncio.fixture
async def tree(sessions: Callable[[], AsyncSession]) -> AsyncIterator[dict[str, str]]:
    """A committed territory and a root dealer, removed afterwards."""
    tag = uuid.uuid4().hex[:8]
    s = sessions()
    territory = (await s.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"conc4_{tag}"})).scalar_one()
    dealer = (await s.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'root dealer', :t, 'dealer') RETURNING id"),
        {"c": f"C4-{tag}", "t": territory})).scalar_one()
    await s.commit()
    ids = {"territory": str(territory), "dealer": str(dealer), "tag": tag}
    try:
        yield ids
    finally:
        c = sessions()
        # Deepest first: parent_id is ON DELETE RESTRICT.
        await c.execute(text(
            "DELETE FROM channel_partner WHERE parent_id = CAST(:d AS uuid)"), {"d": ids["dealer"]})
        await c.execute(text(
            "DELETE FROM channel_partner WHERE id = CAST(:d AS uuid)"), {"d": ids["dealer"]})
        await c.execute(text(
            "DELETE FROM org_unit WHERE name LIKE :n"), {"n": f"conc4_{tag}%"})
        await c.execute(text(
            "DELETE FROM territory WHERE id = CAST(:t AS uuid)"), {"t": ids["territory"]})
        await c.commit()


async def _hold(session: AsyncSession, sql: str, params: dict,
                held: asyncio.Event) -> None:
    """Run the statement, signal that its locks are held, then sit on them."""
    await session.execute(text(sql), params)
    held.set()
    await asyncio.sleep(HOLD)
    await session.commit()


async def _after(held: asyncio.Event, session: AsyncSession, sql: str,
                 params: dict) -> BaseException | None:
    """Start only once T1's statement has returned. A fixed stagger is not enough:
    through the tunnel one INSERT takes 350 to 500 ms on a fresh session, and a
    0.25 s stagger let T2 reach the server first (ISS-060)."""
    await held.wait()
    await asyncio.sleep(STAGGER)
    try:
        await session.execute(text(sql), params)
        await session.commit()
        return None
    except (IntegrityError, InternalError, OperationalError, DBAPIError) as ex:
        await session.rollback()
        return ex


async def test_a_child_insert_and_a_parent_retype_cannot_both_commit(
        sessions: Callable[[], AsyncSession], tree: dict[str, str]) -> None:
    """EC-5. Without the advisory lock in the type check, T1 reads 'dealer', T2 sees
    a root with no children, and both commit a sub_dealer under a distributor.

    With it, T2 blocks until T1 commits, then re-checks the children and refuses.
    Remove the PERFORM pg_advisory_xact_lock line from the trigger and this fails.
    """
    a, b = sessions(), sessions()
    held = asyncio.Event()
    _, err = await asyncio.gather(
        _hold(a,
              "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
              "price_tier) VALUES (:p, 'sub_dealer', :c, 'child', :t, 'sub_dealer')",
              {"p": tree["dealer"], "c": f"C4S-{tree['tag']}", "t": tree["territory"]}, held),
        _after(held, b,
               "UPDATE channel_partner SET partner_type = 'distributor', "
               "price_tier = 'distributor' WHERE id = :d",
               {"d": tree["dealer"]}),
    )
    assert err is not None and "would no longer fit" in str(err), err

    check = sessions()
    bad = (await check.execute(text(
        "SELECT count(*) FROM channel_partner c JOIN channel_partner p ON p.id = c.parent_id "
        "WHERE c.parent_id = :d AND c.partner_type = 'sub_dealer' "
        "AND p.partner_type = 'distributor'"), {"d": tree["dealer"]})).scalar_one()
    await check.rollback()
    assert bad == 0, "an illegal edge was stored"


async def test_writing_two_trees_in_opposite_orders_deadlocks_rather_than_hangs(
        sessions: Callable[[], AsyncSession], tree: dict[str, str]) -> None:
    """EC-10, ISS-054. Three trees share advisory lock class 2. A transaction that
    writes two of them must take them in the order territory, org_unit,
    channel_partner. This test documents what happens otherwise: one side gets
    40P01 from the deadlock detector, and neither side hangs.
    """
    tag = tree["tag"]
    a, b = sessions(), sessions()

    async def cross(s: AsyncSession, first: str, second: str) -> BaseException | None:
        try:
            await s.execute(text(first), {"t": tree["territory"], "n": f"conc4_{tag}"})
            await asyncio.sleep(STAGGER)
            await s.execute(text(second), {"t": tree["territory"], "n": f"conc4_{tag}"})
            await s.rollback()
            return None
        except (OperationalError, DBAPIError) as ex:
            await s.rollback()
            return ex

    partner = ("INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
               "VALUES ('distributor', :n || '-' || floor(random() * 1e9)::text, 'x', :t, "
               "'distributor')")
    org = "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n || '-org', 2, :t)"

    results = await asyncio.gather(cross(a, partner, org), cross(b, org, partner))
    errors = [r for r in results if r is not None]
    if not errors:
        # Both first statements did not land before either second one, so one side
        # took both locks in sequence. The property is not falsified, only unseen.
        pytest.skip("the two sessions did not overlap; nothing to assert this run")
    assert len(errors) == 1, f"expected exactly one deadlock victim, got {results}"
    assert "deadlock" in str(errors[0]).lower(), errors[0]


async def test_writing_two_trees_in_the_prescribed_order_never_deadlocks(
        sessions: Callable[[], AsyncSession], tree: dict[str, str]) -> None:
    """The positive half of ISS-054: territory, then org_unit, then channel_partner.
    Two sessions in that order serialise on each lock in turn and both commit."""
    tag = tree["tag"]

    async def ordered(s: AsyncSession, n: int) -> BaseException | None:
        try:
            await s.execute(text(
                "INSERT INTO territory (level, name) VALUES ('district', :n)"),
                {"n": f"conc4_{tag}-t{n}"})
            await asyncio.sleep(STAGGER)
            await s.execute(text(
                "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t)"),
                {"n": f"conc4_{tag}-o{n}", "t": tree["territory"]})
            await asyncio.sleep(STAGGER)
            await s.execute(text(
                "INSERT INTO channel_partner (partner_type, code, name, territory_id, "
                "price_tier) VALUES ('distributor', :c, 'x', :t, 'distributor')"),
                {"c": f"C4O-{tag}-{n}", "t": tree["territory"]})
            await s.rollback()
            return None
        except (OperationalError, DBAPIError) as ex:
            await s.rollback()
            return ex

    a, b = sessions(), sessions()
    results = await asyncio.gather(ordered(a, 1), ordered(b, 2))
    assert results == [None, None], results
