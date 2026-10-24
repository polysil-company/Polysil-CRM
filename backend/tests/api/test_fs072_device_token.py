# ruff: noqa: E501  (request bodies inline)

"""FS-072 (BE-032) over the API: the tracking app's device token. Issued with an
access token, good on three routes only, and dead with the session family it came
from. The section 8 edge cases are named on each test."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api import deps
from api.main import app
from api.routers.auth import REFRESH_COOKIE
from tests.api import test_order_endpoints as endpoints
from tests.api import test_tracking as trk
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
_forget_tracking = trk._forget_tracking
DEVICE = trk.DEVICE



def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _issue(client: httpx.AsyncClient, h: dict[str, str], device: str = DEVICE,
                 key: dict[str, str] | None = None) -> httpx.Response:
    return await client.post(f"{V1}/tracking/device-token", headers={**h, **(key or _key())},
                             json={"device_id": device})


async def _token(client: httpx.AsyncClient, h: dict[str, str], device: str = DEVICE) -> dict[str, Any]:
    r = await _issue(client, h, device)
    assert r.status_code == 201, r.text
    return dict(r.json()["data"])


async def _batch_status(client: httpx.AsyncClient, token: str, duty: str, device: str = DEVICE) -> int:
    r = await client.post(f"{V1}/locations/batch", headers={**_bearer(token), **_key()}, json={
        "device_id": device, "sent_at": trk._now().isoformat(), "points": [trk._pt(duty, 1)]})
    return r.status_code


async def _config_status(client: httpx.AsyncClient, token: str) -> int:
    return (await client.get(f"{V1}/me/tracking-config", headers=_bearer(token))).status_code


# ── the three routes, and nothing else ──────────────────────────────────────

async def test_the_token_works_on_the_three_routes(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    duty = await trk._on_duty(client, fo)
    t = await _token(client, fo)
    assert t["token"].startswith("pdt_") and len(t["token"]) == 47
    assert t["user_id"] == shop.ids["field_officer"] and t["device_id"] == DEVICE and t["expires_at"]
    assert await _config_status(client, t["token"]) == 200
    assert await _batch_status(client, t["token"], duty) == 200
    r = await client.post(f"{V1}/tracking/duty/end", headers={**_bearer(t["token"]), **_key()},
                          json={"id": duty, "at": trk._now().isoformat()})
    assert r.status_code == 200 and r.json()["data"]["ended_at"], r.text


@pytest.mark.parametrize(("method", "path"), [
    ("GET", "/auth/me"), ("GET", "/leads"), ("GET", "/tracking/policy"), ("GET", "/tracking/team/latest"),
    ("POST", "/tracking/consent"), ("POST", "/tracking/duty/start"), ("POST", "/tracking/device-token"),
    ("POST", "/visits"),
])
async def test_every_other_signed_in_route_refuses_it(client: httpx.AsyncClient, shop: Shop,
                                                      method: str, path: str) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    t = await _token(client, fo)
    r = await client.request(method, f"{V1}{path}", headers={**_bearer(t["token"]), **_key()}, json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "device_token_not_allowed", (path, r.text)


def test_the_allowlist_names_routes_that_exist() -> None:
    """EC-8: a renamed route must not leave the allowlist pointing at nothing."""
    live = {(m.upper(), deps._API_PREFIX_RE.sub("", path))
            for path, ops in app.openapi()["paths"].items() for m in ops}
    assert live >= deps._DEVICE_TOKEN_ALLOWED


async def test_an_unknown_token_is_401_never_403(client: httpx.AsyncClient) -> None:
    fake = "pdt_" + "x" * 43
    assert (await client.get(f"{V1}/leads", headers=_bearer(fake))).status_code == 401
    assert await _config_status(client, fake) == 401


# ── what kills it ───────────────────────────────────────────────────────────

async def test_a_second_token_for_the_device_replaces_the_first(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    first = await _token(client, fo)
    second = await _token(client, fo)
    assert await _config_status(client, first["token"]) == 401
    assert await _config_status(client, second["token"]) == 200


async def test_a_refresh_keeps_it_and_a_sign_out_ends_it(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    t = await _token(client, fo)
    r = await client.post(f"{V1}/auth/refresh")
    assert r.status_code == 200, r.text
    assert await _config_status(client, t["token"]) == 200
    # EC-3: sign out with the access token from before the refresh; its session is
    # already used, and the tokens of the family still go
    assert (await client.post(f"{V1}/auth/logout", headers=fo)).status_code == 204
    assert await _config_status(client, t["token"]) == 401


async def test_a_sign_out_by_cookie_alone_ends_it(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    t = await _token(client, fo)
    assert (await client.post(f"{V1}/auth/logout")).status_code == 204
    assert await _config_status(client, t["token"]) == 401


async def test_logout_with_only_the_device_token_signs_nothing_out(client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-13: it is not an access token; logout finds no session in it."""
    fo = await endpoints._as(client, shop, "field_officer")
    t = await _token(client, fo)
    client.cookies.clear()
    assert (await client.post(f"{V1}/auth/logout", headers=_bearer(t["token"]))).status_code == 204
    assert await _config_status(client, t["token"]) == 200


async def test_reuse_detection_ends_it(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    from api.config import get_settings
    from api.domain.auth import hash_refresh_token, refresh_replay_key
    from api.integrations import cache

    fo = await endpoints._as(client, shop, "field_officer")
    t = await _token(client, fo)
    used = client.cookies[REFRESH_COOKIE]
    assert (await client.post(f"{V1}/auth/refresh")).status_code == 200
    await cache.get_redis().delete(refresh_replay_key(get_settings().jwt_secret.get_secret_value(),
                                                      hash_refresh_token(used)))
    client.cookies.set(REFRESH_COOKIE, used, path="/api/v1/auth")
    r = await client.post(f"{V1}/auth/refresh")
    assert r.json()["error"]["code"] == "refresh_reused", r.text
    assert await _config_status(client, t["token"]) == 401


@pytest.mark.parametrize("change", [
    "UPDATE app_user SET token_version = token_version + 1 WHERE id = CAST(:u AS uuid)",
    "UPDATE session SET revoked_at = now() WHERE user_id = CAST(:u AS uuid) AND revoked_at IS NULL",
    "UPDATE app_user SET is_active = false WHERE id = CAST(:u AS uuid)",
])
async def test_a_version_bump_sign_out_everywhere_or_deactivation_ends_it(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, change: str) -> None:
    """EC-5 and section 3 rule 5: the stored version against the live one."""
    fo = await endpoints._as(client, shop, "field_officer")
    t = await _token(client, fo)
    s = sessions()
    await s.execute(text(change), {"u": shop.ids["field_officer"]})
    await s.commit()
    await s.close()
    assert await _config_status(client, t["token"]) == 401


async def test_an_expired_token_is_401(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    t = await _token(client, fo)
    s = sessions()
    await s.execute(text("UPDATE tracking_device_token SET expires_at = now() - interval '1 second' "
                         "WHERE user_id = CAST(:u AS uuid)"), {"u": shop.ids["field_officer"]})
    await s.commit()
    await s.close()
    assert await _config_status(client, t["token"]) == 401


async def test_a_temporary_password_answers_password_change_required(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    t = await _token(client, fo)
    s = sessions()
    await s.execute(text("UPDATE app_user SET must_change_password = true WHERE id = CAST(:u AS uuid)"),
                    {"u": shop.ids["field_officer"]})
    await s.commit()
    await s.close()
    r = await client.get(f"{V1}/me/tracking-config", headers=_bearer(t["token"]))
    assert r.status_code == 403 and r.json()["error"]["code"] == "password_change_required", r.text


async def test_a_role_without_tracking_cannot_issue(client: httpx.AsyncClient, shop: Shop) -> None:
    accounts = await endpoints._as(client, shop, "account_manager")
    r = await _issue(client, accounts)
    assert r.status_code == 403 and r.json()["error"]["code"] == "insufficient_permission", r.text


# ── devices ─────────────────────────────────────────────────────────────────

async def test_one_person_per_device_and_three_devices_per_person(client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-4 and EC-12."""
    fo = await endpoints._as(client, shop, "field_officer")
    mine = await _token(client, fo)
    dm = await endpoints._as(client, shop, "district_manager")
    theirs = await _token(client, dm)
    assert await _config_status(client, mine["token"]) == 401
    assert await _config_status(client, theirs["token"]) == 200

    tokens = [await _token(client, dm, f"phone-{n:04d}-x") for n in range(3)]
    assert await _config_status(client, theirs["token"]) == 401          # the oldest of four went
    for t in tokens:
        assert await _config_status(client, t["token"]) == 200


async def test_a_batch_must_name_the_tokens_device(client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-11."""
    fo = await endpoints._as(client, shop, "field_officer")
    duty = await trk._on_duty(client, fo)
    t = await _token(client, fo)
    r = await client.post(f"{V1}/locations/batch", headers={**_bearer(t["token"]), **_key()}, json={
        "device_id": "another-device-01", "sent_at": trk._now().isoformat(), "points": [trk._pt(duty, 1)]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "device_mismatch", r.text


# ── the token is never stored ───────────────────────────────────────────────

async def test_a_replay_is_409_and_no_token_is_stored(client: httpx.AsyncClient, shop: Shop,
                                                       sessions: Sessions) -> None:
    """EC-1 and EC-14: the idempotency record and the event hold no token."""
    fo = await endpoints._as(client, shop, "field_officer")
    key = _key()
    first = await _issue(client, fo, key=key)
    assert first.status_code == 201, first.text
    again = await _issue(client, fo, key=key)
    assert again.status_code == 409 and again.json()["error"]["code"] == "idempotency_replay_unavailable"
    assert "pdt_" not in again.text
    assert await _config_status(client, first.json()["data"]["token"]) == 200
    s = sessions()
    leaked = (await s.execute(text(
        "SELECT (SELECT count(*) FROM idempotency_record WHERE response_json::text LIKE '%pdt\\_%') "
        "     + (SELECT count(*) FROM activity_event WHERE payload::text LIKE '%pdt\\_%')"))).scalar_one()
    event = (await s.execute(text(
        "SELECT payload FROM activity_event WHERE entity_type = 'app_user' AND entity_id = CAST(:u AS uuid) "
        "AND kind = 'tracking.device_token_issued' ORDER BY occurred_at DESC LIMIT 1"),
        {"u": shop.ids["field_officer"]})).scalar_one()
    await s.close()
    assert leaked == 0 and event == {"device_id": DEVICE}


# ── the database ────────────────────────────────────────────────────────────

async def test_who_may_call_the_functions(sessions: Sessions) -> None:
    """R-5: resolve is the owner's alone; forget is reachable from logout."""
    s = sessions()
    rows = (await s.execute(text(
        "SELECT has_function_privilege(r, f, 'EXECUTE') FROM (VALUES "
        "('app_role', 'tracking_device_token_resolve(text)'), ('app_anon', 'tracking_device_token_resolve(text)'), "
        "('public', 'tracking_device_token_resolve(text)'), ('app_anon', 'tracking_device_token_forget(uuid)'), "
        "('app_role', 'tracking_device_token_issue(uuid, integer, text, text, interval)'), "
        "('app_anon', 'tracking_device_token_issue(uuid, integer, text, text, interval)')) v(r, f) "
        "WHERE r = 'public' OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)"))).scalars().all()
    privs = (await s.execute(text(
        "SELECT has_table_privilege('app_role', 'tracking_device_token', p) "
        "FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) p"))).scalars().all()
    await s.close()
    assert rows == [False, False, False, True, True, False]
    assert not any(privs)


async def test_the_purge_takes_expired_tokens(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """EC-2: through the worker's own job, as app_role, without aborting the rest."""
    from worker.jobs.outbox import purge_expired_sessions

    fo = await endpoints._as(client, shop, "field_officer")
    await _token(client, fo)
    s = sessions()
    await s.execute(text("UPDATE tracking_device_token SET expires_at = now() - interval '1 minute' "
                         "WHERE user_id = CAST(:u AS uuid)"), {"u": shop.ids["field_officer"]})
    await s.commit()
    await purge_expired_sessions({})
    left = (await s.execute(text("SELECT count(*) FROM tracking_device_token WHERE user_id = CAST(:u AS uuid)"),
                            {"u": shop.ids["field_officer"]})).scalar_one()
    await s.close()
    assert left == 0


async def test_an_issue_with_a_stale_version_writes_nothing(client: httpx.AsyncClient, shop: Shop,
                                                            sessions: Sessions) -> None:
    """EC-5: the version is the access token's claim, checked under the lock."""
    await endpoints._as(client, shop, "field_officer")
    s = sessions()
    sid, tv = (await s.execute(text(
        "SELECT s.id, u.token_version FROM session s JOIN app_user u ON u.id = s.user_id "
        "WHERE s.user_id = CAST(:u AS uuid) AND s.revoked_at IS NULL ORDER BY s.issued_at DESC LIMIT 1"),
        {"u": shop.ids["field_officer"]})).one()
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": shop.ids["field_officer"]})
    got = (await s.execute(text(
        "SELECT tracking_device_token_issue(:s, :tv, 'stale-device-01', :h, interval '1 day')"),
        {"s": sid, "tv": tv - 1, "h": uuid.uuid4().hex * 2})).scalar_one()
    await s.rollback()
    await s.close()
    assert got is None
