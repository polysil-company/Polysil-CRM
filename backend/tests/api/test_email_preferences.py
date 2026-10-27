"""FS-078 over the API: the two switches on `/auth/me` and `PUT /me/email-preferences`."""

# ruff: noqa: E501  (inline SQL and bodies)

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.services import auth as auth_service
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


def _key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def test_me_carries_the_switches_and_says_email_is_off_by_default(client: httpx.AsyncClient,
                                                                       shop: Shop) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    data = (await client.get(f"{V1}/auth/me", headers=h)).json()["data"]
    assert data["email_preferences"] == {"notices": True, "morning_summary": True}
    assert data["email_available"] is False, "EMAIL_PROVIDER is none on this box"


async def test_me_says_available_once_email_is_on(client: httpx.AsyncClient, shop: Shop,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    on = get_settings().model_copy(update={"email_provider": "mock"})
    monkeypatch.setattr(auth_service, "get_settings", lambda: on)
    h = await endpoints._as(client, shop, "field_officer")
    assert (await client.get(f"{V1}/auth/me", headers=h)).json()["data"]["email_available"] is True


async def test_a_user_turns_their_own_switches_off_once_per_key(client: httpx.AsyncClient, shop: Shop,
                                                                sessions: Sessions) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    key = _key()
    body = {"notices": False, "morning_summary": True}
    r = await client.put(f"{V1}/me/email-preferences", headers={**h, **key}, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == body
    again = await client.put(f"{V1}/me/email-preferences", headers={**h, **key}, json=body)
    assert again.status_code == 200 and again.json() == r.json(), "a replay answers the same"
    other = await client.put(f"{V1}/me/email-preferences", headers={**h, **key},
                             json={"notices": True, "morning_summary": True})
    assert other.status_code == 409, "the same key with another body"
    me = (await client.get(f"{V1}/auth/me", headers=h)).json()["data"]
    assert me["email_preferences"] == body
    s = sessions()
    events = (await s.execute(text(
        "SELECT count(*) FROM activity_event WHERE kind = 'user.email_preferences_changed' "
        "AND entity_id = CAST(:u AS uuid)"), {"u": shop.ids["field_officer"]})).scalar_one()
    manager = (await s.execute(text("SELECT email_notices FROM app_user WHERE id = CAST(:u AS uuid)"),
                               {"u": shop.ids["district_manager"]})).scalar_one()
    await s.close()
    assert events == 1, "one event, not one per replay"
    assert manager is True, "only the caller's own row changed"


async def test_both_fields_and_the_key_are_required(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "field_officer")
    r = await client.put(f"{V1}/me/email-preferences", headers={**h, **_key()}, json={"notices": False})
    assert r.status_code == 422
    r = await client.put(f"{V1}/me/email-preferences", headers=h,
                         json={"notices": False, "morning_summary": False})
    assert r.status_code == 400


async def test_a_partner_user_sets_their_own(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    from tests.api import test_complaints as complaints_t
    dealer, _ = await complaints_t._dealer(client, shop, sessions)
    r = await client.put(f"{V1}/me/email-preferences", headers={**dealer, **_key()},
                         json={"notices": True, "morning_summary": False})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"notices": True, "morning_summary": False}


async def test_the_definer_refuses_a_consumer_and_no_claim(sessions: Sessions) -> None:
    """EC-21, and the RLS row of section 9: the definer writes the caller's own row
    only, and a consumer has none it may write."""
    s = sessions()
    try:
        consumer = (await s.execute(text(
            "SELECT id FROM app_user WHERE user_type = 'consumer' LIMIT 1"))).scalar_one_or_none()
        await s.rollback()
        for who in ([str(consumer)] if consumer else []) + [""]:
            async with s.begin():
                await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": who})
                await s.execute(text(f"SET LOCAL ROLE {get_settings().db_app_role}"))
                with pytest.raises(DBAPIError, match=r"42501|not a staff|no caller"):
                    await s.execute(text("SELECT * FROM me_email_preferences_set(false, false)"))
    finally:
        await s.close()
