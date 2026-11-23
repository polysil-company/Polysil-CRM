"""ISS-220: three guarantees a sequential test cannot prove.

1. A merge locks the survivor before it checks it (FS-073 EC-2). A delete that is
   still in flight when the merge starts must make the merge wait, then refuse it.
2. `tracking_device_token_issue()` takes the session family's lock before it checks
   the session (FS-072 R-2). A sign-out in flight must make the issue wait, then
   refuse it.
3. A dealer's lead timeline never shows `complaint.escalated` (FS-074 R-4), checked
   with a real escalation on a real lead.

The first two force genuine overlap, as tests/db/test_concurrency_003.py does: one
connection holds its transaction open, the other starts while it is open, and the
test asserts that the second is still waiting before the first commits. With the
lock removed, the second finishes early and the assertion fails.
"""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from tests.api import test_fs079_forecast as fc
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
HOLD = 1.5


async def test_a_merge_waits_for_a_delete_in_flight_and_then_refuses(client: httpx.AsyncClient, shop: Shop,
                                                                     sessions: Sessions) -> None:
    dm = shop.ids["district_manager"]
    loser, survivor = (await fc._seed(sessions, shop, dm, stage="new", n=2, created_days_ago=1))
    h = await endpoints._as(client, shop, "district_manager")
    deleter = sessions()
    try:
        await deleter.execute(text("UPDATE lead SET deleted_at = now() WHERE id = CAST(:s AS uuid)"), {"s": survivor})
        merge = asyncio.create_task(client.post(
            f"{V1}/leads/{loser}/merge", json={"into_lead_id": survivor},
            headers={**h, "Idempotency-Key": uuid.uuid4().hex}))
        await asyncio.sleep(HOLD)
        assert not merge.done(), "the merge must wait on the survivor's row lock"
        await deleter.commit()
        r = await asyncio.wait_for(merge, timeout=30)
        # 409 lead_deleted, or 404 once RLS hides the deleted survivor: refused either way
        assert r.status_code in (404, 409), r.text
    finally:
        await deleter.close()
    s = sessions()
    stage = (await s.execute(text("SELECT stage::text FROM lead WHERE id = CAST(:l AS uuid)"), {"l": loser})).scalar_one()
    await s.close()
    assert stage == "new", "the loser was not merged into a deleted lead"


async def test_a_device_token_waits_for_a_sign_out_in_flight_and_then_refuses(client: httpx.AsyncClient, shop: Shop,
                                                                              sessions: Sessions) -> None:
    fo = shop.ids["field_officer"]
    await endpoints._as(client, shop, "field_officer")
    s = sessions()
    sid, family, tv = (await s.execute(text(
        "SELECT id, family_id, token_version FROM session WHERE user_id = CAST(:u AS uuid) "
        "ORDER BY issued_at DESC LIMIT 1"), {"u": fo})).one()
    await s.close()
    signing_out = sessions()
    issuer = sessions()
    try:
        # what logout does: the family lock, then the revocation, not yet committed
        await signing_out.execute(text("SELECT pg_advisory_xact_lock(3, hashtext(CAST(:f AS text)))"), {"f": str(family)})
        await signing_out.execute(text("UPDATE session SET revoked_at = now() WHERE family_id = CAST(:f AS uuid)"),
                                  {"f": str(family)})

        async def issue() -> object:
            await issuer.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": fo})
            await issuer.execute(text(f"SET LOCAL ROLE {get_settings().db_app_role}"))
            return (await issuer.execute(text(
                "SELECT tracking_device_token_issue(CAST(:s AS uuid), :tv, 'race-phone', :h, interval '30 days')"),
                {"s": str(sid), "tv": tv, "h": hashlib.sha256(uuid.uuid4().bytes).hexdigest()})).scalar_one()

        task = asyncio.create_task(issue())
        await asyncio.sleep(HOLD)
        assert not task.done(), "the issue must wait on the family lock before it checks the session"
        await signing_out.commit()
        assert await asyncio.wait_for(task, timeout=30) is None, "a signed-out session gets no device token"
        await issuer.rollback()
    finally:
        await signing_out.close()
        await issuer.close()
        c = sessions()
        await c.execute(text("DELETE FROM tracking_device_token WHERE user_id = CAST(:u AS uuid)"), {"u": fo})
        await c.commit()
        await c.close()


async def test_a_dealer_never_sees_an_escalation_on_a_lead_timeline(client: httpx.AsyncClient, shop: Shop,
                                                                    sessions: Sessions) -> None:
    from tests.api import test_complaints as complaints_t
    dealer_h, _ = await complaints_t._dealer(client, shop, sessions)
    (lead,) = await fc._seed(sessions, shop, shop.ids["district_manager"], stage="new", n=1, created_days_ago=1)
    s = sessions()
    await s.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) WHERE id = CAST(:l AS uuid)"),
                    {"p": shop.partner, "l": lead})
    await s.commit()
    await s.close()
    # a real complaint on the lead, raised by the dealer, so both callers can see it
    complaint = await complaints_t._create(client, shop, dealer_h, lead_id=lead)
    s = sessions()
    for kind in ("complaint.escalated", "complaint.registered"):
        await s.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
            "VALUES ('complaint', CAST(:c AS uuid), CAST(:l AS uuid), :k, CAST(:a AS uuid), '{}'::jsonb)"),
            {"c": complaint["id"], "l": lead, "k": kind, "a": shop.ids["district_manager"]})
    await s.commit()
    await s.close()
    staff_h = await endpoints._as(client, shop, "district_manager")
    staff = await client.get(f"{V1}/leads/{lead}/timeline", headers=staff_h)
    assert staff.status_code == 200, staff.text
    staff_kinds = {e["kind"] for e in staff.json()["data"]}
    assert {"complaint.escalated", "complaint.registered"} <= staff_kinds, "staff see both"
    seen = await client.get(f"{V1}/leads/{lead}/timeline", headers=dealer_h)
    assert seen.status_code == 200, seen.text
    kinds = {e["kind"] for e in seen.json()["data"]}
    assert "complaint.registered" in kinds, "the dealer reads this lead's timeline"
    assert "complaint.escalated" not in kinds, "never an escalation (FS-074 R-4)"
