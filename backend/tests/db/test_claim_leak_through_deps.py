"""The claim leak, through the real dependency.

`test_claim_scoping.py` proves PostgreSQL's semantics: a claim set with
`set_config(..., true)` does not outlive its transaction, and one set with `false`
does. That is necessary and it is **not sufficient**, which the cross-vendor review
pointed out — those tests set the claim themselves with a hard-coded `true`, so
changing `api/deps.py` to `false` leaves every one of them passing. The test that
was supposed to justify the whole spec could not detect the bug it exists for.

This one drives the real `get_db` and `get_db_anon` over a pooled connection. It
fails if the `true` in `deps.py` becomes `false` — which is the only property worth
asserting here, and it has been mutation-checked.

`get_db_anon` is what makes it detectable. It sets **no** claim at all, so whatever
it sees is whatever the previous request left behind. An authenticated request
followed by an anonymous one on the same backend is exactly the production failure
shape, and under a session-scoped claim the anonymous request reads the previous
user's identity.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import AnonSession, DbSession
from api.domain.auth import AccessClaims, encode_access_token
from tests.conftest import Staff

pytestmark = [pytest.mark.db, pytest.mark.rls]

# 007 binds a session to the token_version the credential was verified against
# (FS-006 rule 6). The fixtures mint with the row's own, read in the same statement.
_V = ", (SELECT token_version FROM app_user WHERE id = CAST(:u AS uuid)))"


# Enough round trips that PgBouncer hands at least one anonymous request a backend
# an authenticated request has already used. One pass would be a coin toss.
ROUNDS = 12


def _probe_app() -> FastAPI:
    """Two routes over the real dependencies, and nothing else.

    Built here rather than mounted on the production app so the endpoints cannot
    reach a deployment, while `get_db` and `get_db_anon` are the genuine ones.
    """
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(db: DbSession) -> dict[str, str | None]:
        seen = (await db.execute(text("SELECT app_current_user_id()"))).scalar_one()
        return {"claim": str(seen) if seen else None}

    @app.get("/anon")
    async def anon(db: AnonSession) -> dict[str, str | None]:
        seen = (await db.execute(text("SELECT app_current_user_id()"))).scalar_one()
        return {"claim": str(seen) if seen else None}

    return app


@pytest_asyncio.fixture
async def probe() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_probe_app()), base_url="http://probe"
    ) as c:
        yield c


async def _token(staff: Staff, sessions: Callable[[], AsyncSession]) -> str:
    """A real session row and a token that names it, so `get_db`'s join succeeds."""
    from api.config import get_settings

    s = sessions()
    row = (await s.execute(
        text("SELECT session_id, token_version FROM auth_create_session("
             "CAST(:u AS uuid), :h, CAST(:f AS uuid), interval '30 days', "
             "'probe', '10.0.0.1', 'password'" + _V),
        {"u": staff.id, "h": uuid.uuid4().hex, "f": str(uuid.uuid4())})).one()
    await s.commit()

    settings = get_settings()
    return encode_access_token(
        AccessClaims(sub=staff.id, sid=str(row.session_id),
                     token_version=int(row.token_version)),
        settings.jwt_secret.get_secret_value(),
        settings.access_token_ttl,
        algorithm=settings.jwt_algorithm,
    )


async def test_an_authenticated_request_sees_its_own_claim(
        probe: httpx.AsyncClient, staff: Staff,
        sessions: Callable[[], AsyncSession]) -> None:
    """The positive half. Without it, a dependency that set no claim at all would
    pass the leak test below for the wrong reason."""
    token = await _token(staff, sessions)
    r = await probe.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["claim"] == staff.id


async def test_the_claim_never_leaks_into_the_next_request(
        probe: httpx.AsyncClient, staff: Staff,
        sessions: Callable[[], AsyncSession]) -> None:
    """**The test the whole spec exists for, driven through `deps.py`.**

    Authenticated request, then an anonymous one, repeatedly. The anonymous route
    sets no claim, so if the previous request's identity survived on the pooled
    connection it reads it back. Under `set_config(..., true)` it must see nothing,
    every single time.

    Mutation-checked: changing the `true` in `get_db` to `false` makes this fail.
    """
    token = await _token(staff, sessions)
    leaked: list[str] = []

    for _ in range(ROUNDS):
        mine = await probe.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert mine.json()["claim"] == staff.id

        after = await probe.get("/anon")
        assert after.status_code == 200
        if after.json()["claim"] is not None:
            leaked.append(after.json()["claim"])

    assert leaked == [], (
        f"the claim outlived its request {len(leaked)} times out of {ROUNDS} - "
        "every RLS policy on that connection evaluated as the wrong user"
    )


async def test_two_users_in_sequence_never_see_each_other(
        probe: httpx.AsyncClient, staff: Staff,
        sessions: Callable[[], AsyncSession]) -> None:
    """The same property stated the way it will actually be violated: two people,
    one connection, one after the other."""
    first = await _token(staff, sessions)

    other = sessions()
    tag = uuid.uuid4().hex[:10]
    second_user = (await other.execute(
        text("INSERT INTO app_user (user_type, email, password_hash, full_name, "
             "role_id, org_unit_id) VALUES ('staff', :e, 'x', 'Second', :r, :o) "
             "RETURNING id"),
        {"e": f"second_{tag}@polysil.in", "r": staff.role_id,
         "o": staff.org_unit_id})).scalar_one()
    await other.commit()

    try:
        second_staff = Staff(str(second_user), f"second_{tag}@polysil.in", "",
                             staff.org_unit_id, staff.role_id)
        second = await _token(second_staff, sessions)

        for _ in range(ROUNDS):
            a = await probe.get("/whoami", headers={"Authorization": f"Bearer {first}"})
            b = await probe.get("/whoami", headers={"Authorization": f"Bearer {second}"})
            assert a.json()["claim"] == staff.id
            assert b.json()["claim"] == str(second_user)
    finally:
        cleanup = sessions()
        await cleanup.execute(
            text("DELETE FROM activity_event WHERE entity_id = CAST(:i AS uuid)"),
            {"i": str(second_user)})
        await cleanup.execute(
            text("DELETE FROM app_user WHERE id = CAST(:i AS uuid)"),
            {"i": str(second_user)})
        await cleanup.commit()
