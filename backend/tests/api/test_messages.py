"""FS-019 over the API: one-to-one staff conversations, unread counts, paging,
the lead link, and who may not take part."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_complaints as cmp
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _open(client: httpx.AsyncClient, h: dict[str, str], who: str) -> httpx.Response:
    return await client.post(f"{V1}/conversations", headers={**h, **_key()}, json={"participant_id": who})


async def _send(client: httpx.AsyncClient, h: dict[str, str], cid: str, body: str, **extra: object) -> httpx.Response:
    return await client.post(f"{V1}/conversations/{cid}/messages", headers={**h, **_key()},
                             json={"body": body, **extra})


async def _inbox(client: httpx.AsyncClient, h: dict[str, str]) -> dict:
    r = await client.get(f"{V1}/conversations", headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_one_conversation_per_pair_from_either_side(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    dm = await endpoints._as(client, shop, "district_manager")
    first = await _open(client, fo, shop.ids["district_manager"])
    assert first.status_code == 201, first.text
    again = await _open(client, dm, shop.ids["field_officer"])
    assert again.status_code == 200 and again.json()["data"]["id"] == first.json()["data"]["id"]
    assert again.json()["data"]["participant"]["id"] == shop.ids["field_officer"]
    assert first.json()["data"]["participant"]["role_name"], "the officer sees the manager's role"


@pytest.mark.parametrize("who", ["self", "dealer", "system", "nobody"])
async def test_not_someone_you_can_message(client: httpx.AsyncClient, shop: Shop, who: str) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    target = {"self": shop.ids["field_officer"], "dealer": shop.ids["dealer"],
              "system": "26809c63-290b-5bd9-9d6a-a717dc0b32e3", "nobody": str(uuid.uuid4())}[who]
    r = await _open(client, fo, target)
    assert r.status_code == 422 and "participant_id" in r.json()["error"]["fields"], r.text


async def test_send_unread_read_and_the_senders_own_mark(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    dm = await endpoints._as(client, shop, "district_manager")
    cid = (await _open(client, fo, shop.ids["district_manager"])).json()["data"]["id"]
    first = (await _send(client, fo, cid, "Can you visit Vadod?")).json()["data"]
    await _send(client, fo, cid, "  Tomorrow is fine.  ")
    mine = await _inbox(client, fo)
    row = next(c for c in mine["data"] if c["id"] == cid)
    assert row["unread_count"] == 0, "sending marks it read for the sender"
    assert row["last_message"]["body"] == "Tomorrow is fine.", "trimmed"
    theirs = await _inbox(client, dm)
    assert next(c for c in theirs["data"] if c["id"] == cid)["unread_count"] == 2
    r = await client.post(f"{V1}/conversations/{cid}/read", headers={**dm, **_key()}, json={"up_to": first["id"]})
    assert r.status_code == 200, r.text
    assert next(c for c in (await _inbox(client, dm))["data"] if c["id"] == cid)["unread_count"] == 1, \
        "read only up to what the screen showed (review B-2)"
    r = await client.post(f"{V1}/conversations/{cid}/read", headers={**dm, **_key()}, json={})
    assert next(c for c in (await _inbox(client, dm))["data"] if c["id"] == cid)["unread_count"] == 0
    r = await client.post(f"{V1}/conversations/{cid}/read", headers={**dm, **_key()}, json={"up_to": first["id"]})
    assert next(c for c in (await _inbox(client, dm))["data"] if c["id"] == cid)["unread_count"] == 0, \
        "a mark never moves backwards"


async def test_pages_read_oldest_first_and_go_back(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    cid = (await _open(client, fo, shop.ids["district_manager"])).json()["data"]["id"]
    for i in range(5):
        assert (await _send(client, fo, cid, f"m{i}")).status_code == 201
    page = (await client.get(f"{V1}/conversations/{cid}/messages", headers=fo, params={"limit": 2})).json()
    assert [m["body"] for m in page["data"]] == ["m3", "m4"]
    older = (await client.get(f"{V1}/conversations/{cid}/messages", headers=fo,
                              params={"limit": 2, "cursor": page["meta"]["next_cursor"]})).json()
    assert [m["body"] for m in older["data"]] == ["m1", "m2"]


@pytest.mark.parametrize("body", ["", "   ", "x" * 2001])
async def test_a_body_is_1_to_2000_characters(client: httpx.AsyncClient, shop: Shop, body: str) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    cid = (await _open(client, fo, shop.ids["district_manager"])).json()["data"]["id"]
    assert (await _send(client, fo, cid, body)).status_code == 422


async def test_a_lead_link_only_to_a_lead_the_sender_sees(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    dm = await endpoints._as(client, shop, "district_manager")
    mine = (await client.post(f"{V1}/leads", headers={**fo, **_key()}, json={
        "farmer_name": "Chat Farmer", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip"})).json()["data"]
    theirs = (await client.post(f"{V1}/leads", headers={**dm, **_key()}, json={
        "farmer_name": "Other Farmer", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip"})).json()["data"]
    cid = (await _open(client, fo, shop.ids["district_manager"])).json()["data"]["id"]
    r = await _send(client, fo, cid, "Please see this", resource={"type": "lead", "id": mine["id"]})
    assert r.status_code == 201 and r.json()["data"]["resource"]["label"] == mine["inquiry_no"], r.text
    r = await _send(client, fo, cid, "And this", resource={"type": "lead", "id": theirs["id"]})
    assert r.status_code == 422 and "resource" in r.json()["error"]["fields"], "not a lead the officer sees"


async def test_a_third_person_sees_and_writes_nothing(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    cid = (await _open(client, fo, shop.ids["district_manager"])).json()["data"]["id"]
    await _send(client, fo, cid, "Private")
    other = await endpoints._as(client, shop, "state_manager")
    assert (await client.get(f"{V1}/conversations/{cid}/messages", headers=other)).status_code == 404
    assert (await _send(client, other, cid, "Hello")).status_code == 404
    assert (await client.post(f"{V1}/conversations/{cid}/read", headers={**other, **_key()}, json={})).status_code == 404
    assert cid not in {c["id"] for c in (await _inbox(client, other))["data"]}


async def test_a_departed_colleague_keeps_the_history_but_takes_no_messages(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    cid = (await _open(client, fo, shop.ids["state_manager"])).json()["data"]["id"]
    await _send(client, fo, cid, "Before you go")
    s = sessions()
    await s.execute(text("UPDATE app_user SET is_active = false WHERE id = CAST(:u AS uuid)"), {"u": shop.ids["state_manager"]})
    await s.commit()
    try:
        row = next(c for c in (await _inbox(client, fo))["data"] if c["id"] == cid)
        assert row["participant"]["is_active"] is False and row["participant"]["full_name"]
        r = await _send(client, fo, cid, "Still there?")
        assert r.status_code == 422 and r.json()["error"]["code"] == "participant_inactive", r.text
    finally:
        await s.execute(text("UPDATE app_user SET is_active = true WHERE id = CAST(:u AS uuid)"), {"u": shop.ids["state_manager"]})
        await s.commit()
        await s.close()


async def test_the_directory_is_staff_but_you(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    people = (await client.get(f"{V1}/staff-directory", headers=fo, params={"limit": 100})).json()["data"]
    ids = {p["id"] for p in people}
    assert shop.ids["field_officer"] not in ids and shop.ids["dealer"] not in ids
    dm_name = next(p for p in people if p["id"] == shop.ids["district_manager"])["full_name"]
    hit = (await client.get(f"{V1}/staff-directory", headers=fo, params={"q": dm_name[:4]})).json()["data"]
    assert shop.ids["district_manager"] in {p["id"] for p in hit}


async def test_a_dealer_has_no_messages(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    dealer, mobile = await cmp._dealer(client, shop, sessions)
    try:
        assert (await client.get(f"{V1}/conversations", headers=dealer)).status_code == 403
        assert (await client.get(f"{V1}/staff-directory", headers=dealer)).status_code == 403
        assert (await _open(client, dealer, shop.ids["field_officer"])).status_code == 403
    finally:
        await cmp._forget(sessions, mobile)


# ── code review F-1: the lock, proved under contention ───────────────────────

_INS = ("INSERT INTO message (conversation_id, sender_id, body) "
        "VALUES (CAST(:c AS uuid), app_current_user_id(), :b) RETURNING id, created_at")


def _sending(cid: str, body: str) -> Any:
    async def work(s: AsyncSession) -> Any:
        return (await s.execute(text(_INS), {"c": cid, "b": body})).one()
    return work


async def test_two_sends_at_once_are_stamped_in_commit_order(client: httpx.AsyncClient, shop: Shop,
                                                              sessions: Sessions) -> None:
    """Without the row lock in message_stamp() the second commit could carry the
    earlier time, and last_message_at would move backwards (review B-2)."""
    from tests.api import test_order_concurrency as conc
    fo = await endpoints._as(client, shop, "field_officer")
    cid = (await _open(client, fo, shop.ids["district_manager"])).json()["data"]["id"]
    got, waited = await conc._race(sessions, (shop.ids["field_officer"], _sending(cid, "first")),
                                   (shop.ids["district_manager"], _sending(cid, "second")))
    assert waited, "the second send did not wait on the first: the race was not a race"
    first, second = got[0]["ok"], got[1]["ok"]
    assert second.created_at > first.created_at
    s = sessions()
    try:
        last = (await s.execute(text("SELECT last_message_at FROM conversation WHERE id = CAST(:c AS uuid)"),
                                {"c": cid})).scalar_one()
    finally:
        await s.rollback()
        await s.close()
    assert last == second.created_at


async def test_a_read_racing_a_send_leaves_the_new_message_unread(client: httpx.AsyncClient, shop: Shop,
                                                                  sessions: Sessions) -> None:
    """The reader marks up to what they saw; a message committing meanwhile stays unread."""
    from tests.api import test_order_concurrency as conc
    fo = await endpoints._as(client, shop, "field_officer")
    dm = await endpoints._as(client, shop, "district_manager")
    cid = (await _open(client, fo, shop.ids["district_manager"])).json()["data"]["id"]
    seen = (await _send(client, fo, cid, "seen")).json()["data"]

    async def read(s: AsyncSession) -> Any:
        return (await s.execute(text("SELECT conversation_mark_read(CAST(:c AS uuid), CAST(:u AS uuid))"),
                                {"c": cid, "u": seen["id"]})).scalar_one()

    got, waited = await conc._race(sessions, (shop.ids["field_officer"], _sending(cid, "late")),
                                   (shop.ids["district_manager"], read))
    assert waited and got[1]["ok"] is True, got
    row = next(c for c in (await _inbox(client, dm))["data"] if c["id"] == cid)
    assert row["unread_count"] == 1, "the late message is not read unseen"


async def test_a_nul_character_is_a_422_not_a_500(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-3."""
    fo = await endpoints._as(client, shop, "field_officer")
    cid = (await _open(client, fo, shop.ids["district_manager"])).json()["data"]["id"]
    r = await _send(client, fo, cid, "a\u0000b")
    assert r.status_code == 422, r.text
