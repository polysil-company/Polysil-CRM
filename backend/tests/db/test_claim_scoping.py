"""The pooled-connection claim test. **This is the one that justifies FS-001.**

A plain `SET` instead of `set_config(..., true)` passes every other test in this
suite and fails only these. That is the whole reason the spec exists, the reason
`deps.py` is the only place a session is opened, and the reason development runs
through PgBouncer in transaction mode rather than against a direct connection.

The failure it guards against is not a crash. Under a plain `SET`, request A's
identity stays on the connection, request B borrows that connection, and every RLS
policy in the system evaluates B's query as A. Invisible under light load, because
a connection is rarely reused between two different users while anyone is
watching. Catastrophic under the seasonal peaks this system is sized for.

Both halves are asserted. The negative one - that `set_config(..., false)` really
does leak - is what proves the positive one is testing something.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.db, pytest.mark.rls]

CLAIM = "app.current_user_id"


async def _read_claim(session: AsyncSession) -> str:
    got = await session.execute(text(f"SELECT coalesce(current_setting('{CLAIM}', true), '')"))
    value = got.scalar_one()
    await session.commit()
    return str(value)


async def test_a_transaction_local_claim_does_not_survive_its_transaction(
        sessions: Callable[[], AsyncSession]) -> None:
    """RLS-13. The claim is gone the moment the transaction ends."""
    who = str(uuid.uuid4())
    first = sessions()
    await first.execute(text(f"SELECT set_config('{CLAIM}', :u, true)"), {"u": who})
    inside = (await first.execute(
        text(f"SELECT current_setting('{CLAIM}', true)"))).scalar_one()
    assert inside == who, "the claim was not set inside its own transaction"
    await first.commit()

    assert await _read_claim(first) == "", "the claim outlived its transaction"


async def test_a_session_scoped_claim_leaks_and_that_is_the_bug(
        sessions: Callable[[], AsyncSession]) -> None:
    """The negative half, and it is not decoration.

    Without it, the test above passes on a connection that simply never carried a
    claim, and would keep passing if `set_config` stopped working entirely. This
    asserts that the difference between `true` and `false` is observable here -
    which is the same as asserting that the test above is measuring something.
    """
    who = str(uuid.uuid4())
    s = sessions()
    # false = session-scoped, which is what a plain SET does.
    await s.execute(text(f"SELECT set_config('{CLAIM}', :u, false)"), {"u": who})
    await s.commit()

    leaked = await _read_claim(s)
    assert leaked == who, (
        "set_config(..., false) did not leak, so this suite cannot tell a "
        "transaction-local claim from a session-scoped one"
    )
    # Leave nothing behind for whoever borrows this connection next.
    await s.execute(text(f"SELECT set_config('{CLAIM}', '', false)"))
    await s.commit()


async def test_two_users_over_one_pooled_connection_never_see_each_other(
        sessions: Callable[[], AsyncSession]) -> None:
    """The shape the production failure would take.

    Two identities used one after another on the same pooled connection, exactly
    as two sequential requests would. Each transaction must resolve to its own
    user and to nothing in between.
    """
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    s = sessions()

    for who in (a, b, a):
        await s.execute(text(f"SELECT set_config('{CLAIM}', :u, true)"), {"u": who})
        seen = (await s.execute(text("SELECT app_current_user_id()"))).scalar_one()
        assert str(seen) == who
        await s.commit()

        # Between requests the connection carries no identity at all. A helper
        # that resolved to the previous user here is the whole failure mode.
        between = (await s.execute(text("SELECT app_current_user_id()"))).scalar_one()
        assert between is None, f"the connection still resolved to {between} between requests"
        await s.commit()
