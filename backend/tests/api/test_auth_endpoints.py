"""The six /auth endpoints, against the real app and the real database.

Nothing is stubbed. The cookie flags, the status codes, the error envelope and -
most of all - the transaction boundary are all outside the service functions, and
the transaction boundary is where the worst defect in this feature lived.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.integrations import cache
from api.routers.auth import REFRESH_COOKIE
from tests.api.conftest import Dealer, Staff

pytestmark = pytest.mark.db

V1 = "/api/v1"


async def _login(client: httpx.AsyncClient, staff: Staff, password: str | None = None):
    return await client.post(
        f"{V1}/auth/login",
        json={"email": staff.email, "password": password or staff.password},
    )


async def _attempts(session: AsyncSession, identifier: str, kind: str) -> int:
    got = await session.execute(
        text("SELECT count(*) FROM login_attempt WHERE identifier = CAST(:i AS citext) "
             "AND kind = CAST(:k AS login_kind)"),
        {"i": identifier, "k": kind})
    n = got.scalar_one()
    await session.rollback()
    return int(n)


# ── login ────────────────────────────────────────────────────────────────────

async def test_login_returns_a_token_and_sets_the_cookie(
        client: httpx.AsyncClient, staff: Staff) -> None:
    r = await _login(client, staff)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["token_type"] == "Bearer" and body["expires_in"] == 900
    assert REFRESH_COOKIE in r.cookies

    # The refresh token is never in the body. It is a thirty-day credential and
    # anything that can read a response body can read it there.
    assert "refresh" not in r.text.lower()


async def test_the_refresh_cookie_is_httponly_and_path_scoped(
        client: httpx.AsyncClient, staff: Staff) -> None:
    """Scoped to /api/v1/auth so a thirty-day credential is not attached to every
    ordinary API call."""
    r = await _login(client, staff)
    raw = r.headers["set-cookie"].lower()
    assert "httponly" in raw
    assert "samesite=lax" in raw
    assert "path=/api/v1/auth" in raw


@pytest.mark.parametrize("case", ["wrong_password", "unknown_email"])
async def test_login_gives_one_message_for_wrong_and_unknown(
        client: httpx.AsyncClient, staff: Staff, case: str) -> None:
    """Distinguishing them tells an attacker which addresses exist."""
    if case == "wrong_password":
        r = await _login(client, staff, password="not it")
    else:
        # A fresh address every run. A fixed one accumulates login_attempt rows
        # across runs and eventually locks itself out, and the test then fails
        # with 423 for reasons that have nothing to do with what it asserts -
        # the lockout counts an identifier, not an account, so an address that
        # was never registered can still be locked.
        unknown = f"nobody_{uuid.uuid4().hex[:12]}@polysil.in"
        r = await client.post(f"{V1}/auth/login", json={"email": unknown, "password": "x"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


async def test_an_inactive_account_is_also_invalid_credentials(
        client: httpx.AsyncClient, staff: Staff, sessions: Callable[[], AsyncSession]) -> None:
    s = sessions()
    await s.execute(text("UPDATE app_user SET is_active = false WHERE id = CAST(:i AS uuid)"),
                    {"i": staff.id})
    await s.commit()

    r = await _login(client, staff)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials", "disabled accounts are announced"


async def test_a_failed_login_leaves_a_row_behind(
        client: httpx.AsyncClient, staff: Staff, sessions: Callable[[], AsyncSession]) -> None:
    """**The regression that matters most in this file.**

    The service used to raise on a rejected sign-in. The exception unwound through
    the dependency's `async with session.begin()`, which rolled the transaction
    back - taking the `login_attempt` row with it. The count never rose above
    zero, so the five-failure lockout did not exist and password guessing was
    unlimited. Every unit test still passed; only counting the rows found it.
    """
    before = await _attempts(sessions(), staff.email, "password")
    await _login(client, staff, password="not it")
    after = await _attempts(sessions(), staff.email, "password")
    assert after == before + 1, "the failed attempt was rolled back with the response"


async def test_five_failures_lock_the_account(
        client: httpx.AsyncClient, staff: Staff) -> None:
    for _ in range(5):
        r = await _login(client, staff, password="not it")
        assert r.status_code == 401

    r = await _login(client, staff, password="not it")
    assert r.status_code == 423
    assert r.json()["error"]["code"] == "account_locked"

    # And the correct password does not get through a lock either.
    assert (await _login(client, staff)).status_code == 423


async def test_four_failures_do_not_lock(client: httpx.AsyncClient, staff: Staff) -> None:
    for _ in range(4):
        await _login(client, staff, password="not it")
    assert (await _login(client, staff)).status_code == 200


# ── me ───────────────────────────────────────────────────────────────────────

async def test_me_returns_what_the_navigation_needs(
        client: httpx.AsyncClient, staff: Staff) -> None:
    token = (await _login(client, staff)).json()["data"]["access_token"]
    r = await client.get(f"{V1}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    me = r.json()["data"]
    assert me["id"] == staff.id
    assert me["user_type"] == "staff"
    assert me["role"]["name"] == "District Manager"
    assert me["org_unit"]["id"] == staff.org_unit_id
    assert me["partner"] is None, "a staff user must never carry a partner"
    # Enum order, not alphabetical: view, create, edit, approve, delete. That is
    # the order a permissions UI reads in, and it is what array_agg ORDER BY on
    # the enum column gives.
    assert me["permissions"] == [
        {"module": "leads", "actions": ["view", "create", "edit"], "scope": "org_subtree"}
    ]


async def test_a_dealer_carries_a_partner_and_no_org_unit(
        client: httpx.AsyncClient, dealer: Dealer, sessions: Callable[[], AsyncSession]) -> None:
    """The app shell renders one or the other, never both - which is what the
    tightened CHECK on `app_user` makes true rather than hoped for."""
    token = await _otp_sign_in(client, dealer, sessions)
    r = await client.get(f"{V1}/auth/me", headers={"Authorization": f"Bearer {token}"})
    me = r.json()["data"]
    assert me["user_type"] == "partner_user"
    assert me["partner"] is not None and me["org_unit"] is None


@pytest.mark.parametrize("header", [None, "Bearer garbage", "Basic abc", "garbage"])
async def test_me_without_a_valid_token_is_401(
        client: httpx.AsyncClient, header: str | None) -> None:
    headers = {"Authorization": header} if header else {}
    r = await client.get(f"{V1}/auth/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


async def test_a_token_for_another_session_is_rejected(
        client: httpx.AsyncClient, staff: Staff) -> None:
    """AC-AUTH-11. The token names its session, and `get_db` joins on it - a token
    whose session was logged out fails on next use rather than at expiry."""
    token = (await _login(client, staff)).json()["data"]["access_token"]
    await client.post(f"{V1}/auth/logout", headers={"Authorization": f"Bearer {token}"})
    r = await client.get(f"{V1}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_bumping_token_version_ends_every_session(
        client: httpx.AsyncClient, staff: Staff, sessions: Callable[[], AsyncSession]) -> None:
    """The blunt revocation lever, for offboarding. It applies on the next request
    rather than at token expiry (AC-AUTH-8 to 12)."""
    token = (await _login(client, staff)).json()["data"]["access_token"]
    assert (await client.get(f"{V1}/auth/me",
                             headers={"Authorization": f"Bearer {token}"})).status_code == 200

    s = sessions()
    await s.execute(text("UPDATE app_user SET token_version = token_version + 1 "
                         "WHERE id = CAST(:i AS uuid)"), {"i": staff.id})
    await s.commit()

    r = await client.get(f"{V1}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ── refresh ──────────────────────────────────────────────────────────────────

async def test_refresh_rotates_and_keeps_working(
        client: httpx.AsyncClient, staff: Staff) -> None:
    first = (await _login(client, staff)).cookies[REFRESH_COOKIE]

    r = await client.post(f"{V1}/auth/refresh")
    assert r.status_code == 200
    second = r.cookies[REFRESH_COOKIE]
    assert second != first, "the refresh token did not rotate"

    token = r.json()["data"]["access_token"]
    assert (await client.get(f"{V1}/auth/me",
                             headers={"Authorization": f"Bearer {token}"})).status_code == 200


async def test_refresh_without_a_cookie_is_401(client: httpx.AsyncClient) -> None:
    r = await client.post(f"{V1}/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_refresh"


async def test_replaying_a_refresh_inside_the_window_returns_the_same_bundle(
        client: httpx.AsyncClient, staff: Staff) -> None:
    """EC-14 and section 8.2. A lost response on a slow connection makes the client
    retry with a now-used token; without the window that revokes the whole family
    for a dropped packet."""
    await _login(client, staff)
    used = client.cookies[REFRESH_COOKIE]

    first = await client.post(f"{V1}/auth/refresh")
    # Re-present the *same* token, as a retry would.
    client.cookies.set(REFRESH_COOKIE, used, path="/api/v1/auth")
    second = await client.post(f"{V1}/auth/refresh")

    assert second.status_code == 200
    assert second.json()["data"]["access_token"] == first.json()["data"]["access_token"]


async def test_reuse_outside_the_window_revokes_the_whole_family(
        client: httpx.AsyncClient, staff: Staff, sessions: Callable[[], AsyncSession]) -> None:
    """ADR-025: presenting a used refresh token is a stolen-token signal, and
    revoking the family is the only cheap defence against one.

    The replay cache is deleted rather than waited out - ninety seconds of sleep in
    a test suite is ninety seconds every run, and the expiry itself is Redis's
    behaviour, not ours.
    """
    from api.config import get_settings
    from api.domain.auth import hash_refresh_token, refresh_replay_key

    await _login(client, staff)
    used = client.cookies[REFRESH_COOKIE]
    await client.post(f"{V1}/auth/refresh")

    secret = get_settings().jwt_secret.get_secret_value()
    await cache.get_redis().delete(refresh_replay_key(secret, hash_refresh_token(used)))

    client.cookies.set(REFRESH_COOKIE, used, path="/api/v1/auth")
    r = await client.post(f"{V1}/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "refresh_reused"

    s = sessions()
    live = (await s.execute(
        text("SELECT count(*) FROM session WHERE user_id = CAST(:u AS uuid) "
             "AND revoked_at IS NULL"), {"u": staff.id})).scalar_one()
    await s.rollback()
    assert live == 0, "reuse was detected and revoked nothing"


async def test_the_family_revocation_survives_the_response(
        client: httpx.AsyncClient, staff: Staff, sessions: Callable[[], AsyncSession]) -> None:
    """The same transaction-boundary defect as the lockout, with more at stake.

    Raising to signal the 401 rolled back the revocation that had just been
    performed - so reuse detection fired, answered `refresh_reused`, and left
    every session in the family live. Asserted by reading the rows back on a
    different connection.
    """
    from api.config import get_settings
    from api.domain.auth import hash_refresh_token, refresh_replay_key

    await _login(client, staff)
    used = client.cookies[REFRESH_COOKIE]
    await client.post(f"{V1}/auth/refresh")
    secret = get_settings().jwt_secret.get_secret_value()
    await cache.get_redis().delete(refresh_replay_key(secret, hash_refresh_token(used)))

    client.cookies.set(REFRESH_COOKIE, used, path="/api/v1/auth")
    await client.post(f"{V1}/auth/refresh")

    s = sessions()
    revoked = (await s.execute(
        text("SELECT count(*) FROM session WHERE user_id = CAST(:u AS uuid) "
             "AND revoked_at IS NOT NULL"), {"u": staff.id})).scalar_one()
    events = (await s.execute(
        text("SELECT count(*) FROM activity_event WHERE entity_id = CAST(:u AS uuid) "
             "AND kind = 'auth.family_revoked'"), {"u": staff.id})).scalar_one()
    await s.rollback()
    assert revoked >= 2 and events == 1


# ── logout ───────────────────────────────────────────────────────────────────

async def test_logout_with_a_bearer_token(client: httpx.AsyncClient, staff: Staff) -> None:
    token = (await _login(client, staff)).json()["data"]["access_token"]
    r = await client.post(f"{V1}/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204


async def test_logout_with_only_the_cookie(client: httpx.AsyncClient, staff: Staff) -> None:
    """The common case: the access token expired while the tab sat open, so the
    button would fail exactly when it is most likely to be pressed."""
    await _login(client, staff)
    r = await client.post(f"{V1}/auth/logout")
    assert r.status_code == 204
    assert (await client.post(f"{V1}/auth/refresh")).status_code == 401


async def test_logout_with_neither_credential_is_still_204(
        client: httpx.AsyncClient) -> None:
    """EC-17. `auth_revoke_sessions` raises on two null ids by contract, and the
    natural implementation falls through into that call - turning a 204 this
    endpoint promises into a 500."""
    r = await client.post(f"{V1}/auth/logout")
    assert r.status_code == 204


async def test_logout_with_both_credentials_revokes_once(
        client: httpx.AsyncClient, staff: Staff,
        sessions: Callable[[], AsyncSession]) -> None:
    """EC-18, and it is the ordinary shape rather than a rare one: any tab signed
    out before its access token expired presents both. Deriving both ids would hand
    the database two, and it refuses that.

    The status code alone is too weak an assertion here - it only catches the case
    where the contract guard fires and turns the 204 into a 500. The row counts are
    what pin "revokes once, through p_session_id".
    """
    token = (await _login(client, staff)).json()["data"]["access_token"]
    r = await client.post(f"{V1}/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204

    s = sessions()
    revoked = (await s.execute(
        text("SELECT count(*) FROM session WHERE user_id = CAST(:u AS uuid) "
             "AND revoked_at IS NOT NULL"), {"u": staff.id})).scalar_one()
    events = (await s.execute(
        text("SELECT count(*) FROM activity_event WHERE entity_id = CAST(:u AS uuid) "
             "AND kind = 'auth.signed_out'"), {"u": staff.id})).scalar_one()
    family = (await s.execute(
        text("SELECT count(*) FROM activity_event WHERE entity_id = CAST(:u AS uuid) "
             "AND kind = 'auth.family_revoked'"), {"u": staff.id})).scalar_one()
    await s.rollback()
    assert revoked == 1, "one session was signed out, not one"
    assert events == 1, "one sign-out, one timeline row"
    assert family == 0, "a single logout revoked a whole family"


async def test_logging_out_one_session_leaves_the_others(
        client: httpx.AsyncClient, staff: Staff) -> None:
    """`session.revoked_at` is the precise lever: signing out of a phone must leave
    the desktop signed in."""
    desktop = (await _login(client, staff)).json()["data"]["access_token"]
    async with httpx.AsyncClient(transport=client._transport, base_url="http://test") as phone:
        phone_token = (await _login(phone, staff)).json()["data"]["access_token"]
        await phone.post(f"{V1}/auth/logout", headers={"Authorization": f"Bearer {phone_token}"})

    assert (await client.get(f"{V1}/auth/me",
                             headers={"Authorization": f"Bearer {desktop}"})).status_code == 200


async def test_a_redis_failure_during_rotation_aborts_it(
        client: httpx.AsyncClient, staff: Staff, sessions: Callable[[], AsyncSession],
        monkeypatch: pytest.MonkeyPatch) -> None:
    """§8.2, and §10 names this test. Failing open here is the tempting change.

    The bundle cache is what a losing concurrent caller wakes to, so a rotation
    that commits without one reopens the two-tab race as a family revocation. The
    rotation therefore aborts rather than proceeding: the exception propagates, the
    dependency rolls back, and no session is ever committed whose bundle could not
    be cached.

    Written as a regression against the plausible-sounding refactor - wrapping the
    cache write in `try/except: pass` "to make refresh more resilient" - which
    would silently undo it and break no other test.
    """
    await _login(client, staff)
    before = await _session_count(sessions(), staff.id)

    async def boom(*_: object, **__: object) -> None:
        raise ConnectionError("redis is gone")

    monkeypatch.setattr(cache, "cache_bundle", boom)

    with pytest.raises(ConnectionError):
        await client.post(f"{V1}/auth/refresh")

    assert await _session_count(sessions(), staff.id) == before, (
        "a rotation committed a session whose bundle was never cached"
    )

    claimed = await _used_count(sessions(), staff.id)
    assert claimed == 0, "the claim was not rolled back with the rotation"


async def _session_count(session: AsyncSession, user_id: str) -> int:
    got = await session.execute(
        text("SELECT count(*) FROM session WHERE user_id = CAST(:u AS uuid)"),
        {"u": user_id})
    n = int(got.scalar_one())
    await session.rollback()
    return n


async def _used_count(session: AsyncSession, user_id: str) -> int:
    got = await session.execute(
        text("SELECT count(*) FROM session WHERE user_id = CAST(:u AS uuid) "
             "AND used_at IS NOT NULL"), {"u": user_id})
    n = int(got.scalar_one())
    await session.rollback()
    return n


# ── OTP ──────────────────────────────────────────────────────────────────────

async def _read_code(sessions: Callable[[], AsyncSession], mobile: str) -> str:
    s = sessions()
    got = await s.execute(
        text("SELECT payload ->> 'code' FROM notification_outbox WHERE recipient = :m "
             "ORDER BY created_at DESC LIMIT 1"), {"m": mobile})
    code = got.scalar_one()
    await s.rollback()
    return str(code)


async def _otp_sign_in(client: httpx.AsyncClient, dealer: Dealer,
                       sessions: Callable[[], AsyncSession]) -> str:
    await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    code = await _read_code(sessions, dealer.mobile)
    r = await client.post(f"{V1}/auth/otp/verify",
                          json={"mobile": dealer.mobile, "code": code})
    return str(r.json()["data"]["access_token"])


@pytest.mark.parametrize("mobile", ["919999000011", "918888000022"])
async def test_otp_request_is_identical_for_an_unknown_number(
        client: httpx.AsyncClient, mobile: str) -> None:
    """Always 202, always the same body. A different response for an unknown number
    turns this into a "is this dealer registered" oracle."""
    r = await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
    assert r.status_code == 202
    assert r.json()["data"] == {"sent": True, "expires_in": 300, "resend_after": 300}


async def test_otp_request_for_a_known_number_looks_the_same(
        client: httpx.AsyncClient, dealer: Dealer) -> None:
    r = await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    assert r.status_code == 202
    assert r.json()["data"] == {"sent": True, "expires_in": 300, "resend_after": 300}


async def test_no_message_is_queued_for_an_unknown_number(
        client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]) -> None:
    """The response is identical; what happens behind it is not."""
    mobile = "917777" + uuid.uuid4().hex[:6]
    await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
    s = sessions()
    queued = (await s.execute(
        text("SELECT count(*) FROM notification_outbox WHERE recipient = :m"),
        {"m": mobile})).scalar_one()
    await s.rollback()
    assert queued == 0


async def test_the_code_reaches_the_outbox_and_never_the_response(
        client: httpx.AsyncClient, dealer: Dealer,
        sessions: Callable[[], AsyncSession]) -> None:
    """Rule 6: outbound messages go to the outbox, never sent inside a request.
    Rule 8: the code is never in a response, a log or an error."""
    r = await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    code = await _read_code(sessions, dealer.mobile)
    assert code.isdigit() and len(code) == 6
    assert code not in r.text


async def test_otp_verify_signs_the_dealer_in(
        client: httpx.AsyncClient, dealer: Dealer,
        sessions: Callable[[], AsyncSession]) -> None:
    token = await _otp_sign_in(client, dealer, sessions)
    assert (await client.get(f"{V1}/auth/me",
                             headers={"Authorization": f"Bearer {token}"})).status_code == 200


async def test_a_wrong_code_is_rejected_and_recorded(
        client: httpx.AsyncClient, dealer: Dealer,
        sessions: Callable[[], AsyncSession]) -> None:
    """The failure row must survive the response, for the same reason the password
    one must - and rule 12 keeps it out of the password lockout."""
    await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    before = await _attempts(sessions(), dealer.mobile, "otp")

    r = await client.post(f"{V1}/auth/otp/verify",
                          json={"mobile": dealer.mobile, "code": "000000"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_otp"
    assert await _attempts(sessions(), dealer.mobile, "otp") == before + 1


async def test_five_wrong_codes_burn_the_challenge(
        client: httpx.AsyncClient, dealer: Dealer,
        sessions: Callable[[], AsyncSession]) -> None:
    await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    code = await _read_code(sessions, dealer.mobile)

    for _ in range(5):
        await client.post(f"{V1}/auth/otp/verify",
                          json={"mobile": dealer.mobile, "code": "000000"})

    # Even the correct code is gone now, which is what "burned" means.
    r = await client.post(f"{V1}/auth/otp/verify",
                          json={"mobile": dealer.mobile, "code": code})
    assert r.status_code == 401


async def test_replaying_a_correct_code_returns_the_same_session(
        client: httpx.AsyncClient, dealer: Dealer,
        sessions: Callable[[], AsyncSession]) -> None:
    """EC-14. Without this a lost 200 tells a field officer their correct code was
    wrong, and the code is already burned so re-entering it cannot work. The pair
    costs one attempt, not two."""
    await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    code = await _read_code(sessions, dealer.mobile)

    first = await client.post(f"{V1}/auth/otp/verify",
                              json={"mobile": dealer.mobile, "code": code})
    second = await client.post(f"{V1}/auth/otp/verify",
                               json={"mobile": dealer.mobile, "code": code})
    assert second.status_code == 200
    assert second.json()["data"]["access_token"] == first.json()["data"]["access_token"]


async def test_a_staff_number_is_not_reachable_through_the_otp_door(
        client: httpx.AsyncClient, staff: Staff,
        sessions: Callable[[], AsyncSession]) -> None:
    """Round 3's B-5, end to end. The CHECK permits a mobile on staff - a field
    officer's number is legitimately useful - so the door is closed at the lookup.
    Otherwise this is a second, weaker way into every password account: no
    password, no argon2, and no lockout."""
    mobile = "9196" + uuid.uuid4().hex[:8]
    s = sessions()
    await s.execute(text("UPDATE app_user SET mobile = :m WHERE id = CAST(:i AS uuid)"),
                    {"m": mobile, "i": staff.id})
    await s.commit()

    await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
    queued = sessions()
    rows = (await queued.execute(
        text("SELECT count(*) FROM notification_outbox WHERE recipient = :m"),
        {"m": mobile})).scalar_one()
    await queued.rollback()
    assert rows == 0, "a staff number was sent an OTP"


async def test_guesses_are_bounded_after_the_code_is_burned(
        client: httpx.AsyncClient, dealer: Dealer,
        sessions: Callable[[], AsyncSession]) -> None:
    """The cross-vendor review's P1-1, and the hole was wide.

    Once a code is verified the challenge is burned, so a wrong guess finds no
    record and costs nothing - while the correct one is still served from the
    replay cache for ninety seconds. Reproduced at sixty wrong guesses followed by
    a successful one, with the five-attempt limit never involved: unlimited
    brute-forcing of a live code inside the window.

    The budget is keyed on the number rather than the challenge, so it survives the
    burn.
    """
    await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    code = await _read_code(sessions, dealer.mobile)
    assert (await client.post(f"{V1}/auth/otp/verify",
                              json={"mobile": dealer.mobile, "code": code})).status_code == 200

    for i in range(10):
        wrong = f"{(int(code) + i + 1) % 10**6:06d}"
        await client.post(f"{V1}/auth/otp/verify",
                          json={"mobile": dealer.mobile, "code": wrong})

    # Past the budget, even the correct code is refused - the replay window is not
    # a free brute-force window.
    r = await client.post(f"{V1}/auth/otp/verify",
                          json={"mobile": dealer.mobile, "code": code})
    assert r.status_code == 401, "the replay cache served a code after the budget ran out"


async def test_a_legitimate_replay_still_works_within_the_budget(
        client: httpx.AsyncClient, dealer: Dealer,
        sessions: Callable[[], AsyncSession]) -> None:
    """The budget must not break EC-14. A couple of mistypes then the right code,
    presented twice, is the ordinary flow on a bad connection."""
    await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    code = await _read_code(sessions, dealer.mobile)

    for i in range(2):
        await client.post(f"{V1}/auth/otp/verify",
                          json={"mobile": dealer.mobile, "code": f"{i:06d}"})

    first = await client.post(f"{V1}/auth/otp/verify",
                              json={"mobile": dealer.mobile, "code": code})
    second = await client.post(f"{V1}/auth/otp/verify",
                               json={"mobile": dealer.mobile, "code": code})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["access_token"] == second.json()["data"]["access_token"]


async def test_a_new_code_restores_the_budget(
        client: httpx.AsyncClient, dealer: Dealer,
        sessions: Callable[[], AsyncSession]) -> None:
    """Otherwise five mistypes would lock a number out of every future code too,
    which is a denial of service built out of a security control."""
    await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    for i in range(6):
        await client.post(f"{V1}/auth/otp/verify",
                          json={"mobile": dealer.mobile, "code": f"{i:06d}"})

    await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    code = await _read_code(sessions, dealer.mobile)
    r = await client.post(f"{V1}/auth/otp/verify",
                          json={"mobile": dealer.mobile, "code": code})
    assert r.status_code == 200, "a fresh code inherited the previous budget"


async def test_two_simultaneous_correct_codes_yield_one_session(
        client: httpx.AsyncClient, dealer: Dealer,
        sessions: Callable[[], AsyncSession]) -> None:
    """P1-2. Both submissions passed every check and both minted - one code, two
    credentials, and the spec says the replayer shares the one session.

    auth_lookup_by_mobile now takes a per-number transaction lock, so the loser
    blocks there, wakes after the winner commits, and re-reads the replay cache.
    """
    await client.post(f"{V1}/auth/otp/request", json={"mobile": dealer.mobile})
    code = await _read_code(sessions, dealer.mobile)

    async def submit() -> httpx.Response:
        return await client.post(f"{V1}/auth/otp/verify",
                                 json={"mobile": dealer.mobile, "code": code})

    first, second = await asyncio.gather(submit(), submit())
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["access_token"] == second.json()["data"]["access_token"], (
        "one code minted two different sessions"
    )

    s = sessions()
    minted = (await s.execute(
        text("SELECT count(*) FROM session WHERE user_id = CAST(:u AS uuid)"),
        {"u": dealer.id})).scalar_one()
    await s.rollback()
    assert minted == 1, f"{minted} sessions from one code"


async def test_a_password_keeps_its_whitespace(
        client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]) -> None:
    """Stripping whitespace off a password changes the password. The user types the
    right thing and is told it is wrong, permanently."""
    from argon2 import PasswordHasher

    spaced = "  spaces matter  "
    tag = uuid.uuid4().hex[:10]
    email = f"spaced_{tag}@polysil.in"

    setup = sessions()
    terr = (await setup.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"sp_{tag}"})).scalar_one()
    org = (await setup.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) "
        "RETURNING id"), {"n": f"sp_{tag}", "t": terr})).scalar_one()
    role = (await setup.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'DM', 2) RETURNING id"),
        {"c": f"sp_{tag}"})).scalar_one()
    uid = (await setup.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, "
        "org_unit_id) VALUES ('staff', :e, :p, 'Spaced', :r, :o) RETURNING id"),
        {"e": email, "p": PasswordHasher().hash(spaced), "r": role, "o": org})).scalar_one()
    await setup.commit()

    try:
        r = await client.post(f"{V1}/auth/login", json={"email": email, "password": spaced})
        assert r.status_code == 200, "the password was trimmed before hashing"

        # The email is still trimmed, which is what citext and a copy-paste need.
        r2 = await client.post(f"{V1}/auth/login",
                               json={"email": f"  {email}  ", "password": spaced})
        assert r2.status_code == 200
    finally:
        c = sessions()
        for stmt, params in (
            ("DELETE FROM activity_event WHERE entity_id = CAST(:i AS uuid)", {"i": str(uid)}),
            ("DELETE FROM login_attempt WHERE identifier = CAST(:i AS citext)", {"i": email}),
            ("DELETE FROM app_user WHERE id = CAST(:i AS uuid)", {"i": str(uid)}),
            ("DELETE FROM role WHERE id = CAST(:i AS uuid)", {"i": str(role)}),
            ("DELETE FROM org_unit WHERE id = CAST(:i AS uuid)", {"i": str(org)}),
            ("DELETE FROM territory WHERE id = CAST(:i AS uuid)", {"i": str(terr)}),
        ):
            await c.execute(text(stmt), params)
        await c.commit()


# ── validation ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mobile", ["", "abc", "12345", "0" + "9" * 11, "+" * 3])
async def test_a_malformed_mobile_is_refused(
        client: httpx.AsyncClient, mobile: str) -> None:
    r = await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
    assert r.status_code == 422


async def test_a_plus_prefixed_mobile_is_normalised(client: httpx.AsyncClient) -> None:
    """Clients send E.164 with and without the plus. Storing both shapes would make
    one number two accounts."""
    r = await client.post(f"{V1}/auth/otp/request", json={"mobile": "+919876543210"})
    assert r.status_code == 202
