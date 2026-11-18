"""FS-007 at the API layer (section 10, the API row).

The 202 names the channel and stays byte-identical whatever the number; a
verification that read the challenge before a resend replaced it is refused, and
the new code then signs in (rule 1b); /health names the provider outside
production and not in it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.integrations import cache
from tests.api.conftest import V1, Admin, _auth, _create

pytestmark = pytest.mark.db


def _mobile() -> str:
    return "9198" + f"{uuid.uuid4().int % 10**8:08d}"


async def _partner_user(client: httpx.AsyncClient, admin: Admin) -> str:
    """A fresh partner user with its own number, so the burst limit and the
    supersede rule of every other test's number stay out of this one."""
    h = await _auth(client, admin.user)
    mobile = _mobile()
    await _create(client, h, {"user_type": "partner_user", "full_name": "Kiran Delivery",
                              "mobile": mobile, "partner_id": admin.dealer_id})
    return mobile


async def _pending_code(sessions: Callable[[], AsyncSession], mobile: str) -> str:
    s = sessions()
    code = (await s.execute(text(
        "SELECT payload ->> 'code' FROM notification_outbox WHERE recipient = :m "
        "AND template_key = 'auth.otp' AND state = 'pending' ORDER BY created_at DESC LIMIT 1"),
        {"m": mobile})).scalar_one()
    await s.rollback()
    return str(code)


async def _rows(sessions: Callable[[], AsyncSession], mobile: str) -> list[tuple[str, str | None]]:
    s = sessions()
    rows = (await s.execute(text(
        "SELECT state::text, error FROM notification_outbox WHERE recipient = :m "
        "AND template_key = 'auth.otp' ORDER BY created_at"), {"m": mobile})).all()
    await s.rollback()
    return [tuple(r) for r in rows]  # type: ignore[misc]


async def test_the_202_names_the_channel_and_is_identical_for_any_number(
        client: httpx.AsyncClient, admin: Admin) -> None:
    known = await _partner_user(client, admin)
    unknown = _mobile()
    bodies = []
    for mobile in (known, unknown, known, known, known, known):
        r = await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
        assert r.status_code == 202
        bodies.append(r.content)
    # a known number, an unknown one, and a known one past its burst limit
    assert len(set(bodies)) == 1, bodies
    assert b'"channel":"whatsapp"' in bodies[0]


async def test_a_code_read_before_a_resend_no_longer_signs_in(
        client: httpx.AsyncClient, admin: Admin, sessions: Callable[[], AsyncSession],
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Cross-vendor C-2, reproduced then closed. The first challenge read matches
    the older code; a resend lands before the number's lock is taken; the re-read
    under the lock sees the newer challenge and refuses. The newer code signs in."""
    mobile = await _partner_user(client, admin)
    r = await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
    assert r.status_code == 202
    older = await _pending_code(sessions, mobile)

    real_read = cache.read_otp
    state: dict[str, Any] = {"resent": False}

    async def read_then_resend(m: str) -> dict[str, str] | None:
        record = await real_read(m)
        if m == mobile and not state["resent"]:
            state["resent"] = True
            # the resend, between the first match and the lock
            r2 = await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
            assert r2.status_code == 202
        return record

    monkeypatch.setattr(cache, "read_otp", read_then_resend)
    r = await client.post(f"{V1}/auth/otp/verify", json={"mobile": mobile, "code": older})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_otp", r.text
    assert state["resent"] is True
    monkeypatch.setattr(cache, "read_otp", real_read)

    assert await _rows(sessions, mobile) == [("dead", "superseded"), ("pending", None)]
    newer = await _pending_code(sessions, mobile)
    assert newer != older
    r = await client.post(f"{V1}/auth/otp/verify", json={"mobile": mobile, "code": newer})
    assert r.status_code == 200 and "access_token" in r.json()["data"], r.text


async def test_health_names_the_provider_outside_production_only(
        client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["whatsapp"] == "mock"
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    r = await client.get("/health")
    assert r.status_code == 200 and "whatsapp" not in r.json()
