"""FS-048 over the API: group chats on FS-019's conversations."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


@pytest_asyncio.fixture(autouse=True)
async def _groups(shop: Shop, sessions: Sessions) -> AsyncIterator[None]:
    """The shop's teardown deletes its people, and their member rows cascade, but
    the groups would stay: remove the groups its people were in, and their events."""
    yield
    s = sessions()
    ids = list(shop.ids.values())
    groups = ("(SELECT conversation_id FROM conversation_member WHERE user_id = ANY(CAST(:u AS uuid[])))")
    await s.execute(text(f"DELETE FROM activity_event WHERE entity_type = 'conversation' AND entity_id IN {groups}"), {"u": ids})
    await s.execute(text(f"DELETE FROM conversation WHERE kind = 'group' AND id IN {groups}"), {"u": ids})
    await s.execute(text("DELETE FROM conversation WHERE kind = 'group' AND NOT EXISTS "
                         "(SELECT 1 FROM conversation_member m WHERE m.conversation_id = conversation.id)"))
    await s.commit()
    await s.close()


async def _create(client: httpx.AsyncClient, h: dict[str, str], name: str, ids: list[str]) -> httpx.Response:
    return await client.post(f"{V1}/conversations/groups", headers={**h, **_key()},
                             json={"name": name, "member_ids": ids})


async def _send(client: httpx.AsyncClient, h: dict[str, str], cid: str, body: str) -> httpx.Response:
    return await client.post(f"{V1}/conversations/{cid}/messages", headers={**h, **_key()}, json={"body": body})


async def _row(client: httpx.AsyncClient, h: dict[str, str], cid: str) -> dict | None:
    r = await client.get(f"{V1}/conversations", headers=h)
    assert r.status_code == 200, r.text
    return next((c for c in r.json()["data"] if c["id"] == cid), None)


async def _remove(client: httpx.AsyncClient, h: dict[str, str], cid: str, uid: str) -> httpx.Response:
    return await client.delete(f"{V1}/conversations/{cid}/members/{uid}", headers={**h, **_key()})


async def _team(client: httpx.AsyncClient, shop: Shop) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    return (await endpoints._as(client, shop, "field_officer"), await endpoints._as(client, shop, "district_manager"),
            await endpoints._as(client, shop, "account_manager"), await endpoints._as(client, shop, "dispatch_manager"))


async def test_a_group_is_listed_for_its_members_from_creation_and_hidden_from_others(
        client: httpx.AsyncClient, shop: Shop) -> None:
    fo, dm, am, dp = await _team(client, shop)
    r = await _create(client, fo, "  Rajkot team  ", [shop.ids["district_manager"], shop.ids["account_manager"],
                                                     shop.ids["district_manager"], shop.ids["field_officer"]])
    assert r.status_code == 201, r.text
    g = r.json()["data"]
    assert g["kind"] == "group" and g["participant"] is None
    assert g["group"] == {"name": "Rajkot team", "member_count": 3, "manager_id": shop.ids["field_officer"], "i_manage": True}
    cid = g["id"]
    theirs = await _row(client, dm, cid)
    assert theirs is not None and theirs["last_message"] is None and theirs["group"]["i_manage"] is False, theirs
    assert await _row(client, dp, cid) is None, "not a member: not listed"
    for path in ("", "/members", "/messages"):
        assert (await client.get(f"{V1}/conversations/{cid}{path}", headers=dp)).status_code == 404, path
    members = (await client.get(f"{V1}/conversations/{cid}/members", headers=am)).json()["data"]
    assert [m["is_manager"] for m in members].count(True) == 1 and len(members) == 3
    # a direct conversation reads as before, plus its kind
    pair = (await client.post(f"{V1}/conversations", headers={**fo, **_key()},
                              json={"participant_id": shop.ids["dispatch_manager"]})).json()["data"]
    assert pair["kind"] == "direct" and pair["group"] is None and pair["participant"]["id"] == shop.ids["dispatch_manager"]


async def test_sending_unread_and_reading_in_a_group(client: httpx.AsyncClient, shop: Shop) -> None:
    fo, dm, am, _ = await _team(client, shop)
    cid = (await _create(client, fo, "Vadod visits", [shop.ids["district_manager"], shop.ids["account_manager"]])).json()["data"]["id"]
    first = (await _send(client, fo, cid, "Visit on Monday?")).json()["data"]
    assert (await _send(client, dm, cid, "Yes")).status_code == 201
    assert (await _row(client, fo, cid))["unread_count"] == 1
    assert (await _row(client, am, cid))["unread_count"] == 2
    r = await client.post(f"{V1}/conversations/{cid}/read", headers={**am, **_key()}, json={"up_to": first["id"]})
    assert r.status_code == 200, r.text
    assert (await _row(client, am, cid))["unread_count"] == 1
    page = (await client.get(f"{V1}/conversations/{cid}/messages", headers=am)).json()["data"]
    assert [m["body"] for m in page] == ["Visit on Monday?", "Yes"]


async def test_leaving_removing_and_coming_back(client: httpx.AsyncClient, shop: Shop) -> None:
    fo, dm, am, dp = await _team(client, shop)
    cid = (await _create(client, fo, "Dispatch desk", [shop.ids["district_manager"], shop.ids["account_manager"]])).json()["data"]["id"]
    assert (await _send(client, fo, cid, "one")).status_code == 201
    assert (await _remove(client, dm, cid, shop.ids["account_manager"])).status_code == 403, "only the manager removes"
    assert (await _remove(client, dp, cid, shop.ids["account_manager"])).status_code == 404, "a non-member learns nothing"
    assert (await _remove(client, fo, cid, shop.ids["account_manager"])).status_code == 204
    assert (await _remove(client, fo, cid, shop.ids["account_manager"])).status_code == 404, "already out"
    assert (await client.get(f"{V1}/conversations/{cid}/messages", headers=am)).status_code == 404
    assert (await _send(client, am, cid, "still here?")).status_code == 404
    assert (await _send(client, fo, cid, "two")).status_code == 201
    # any member adds back; the read mark is kept, so both messages are unread
    r = await client.post(f"{V1}/conversations/{cid}/members", headers={**dm, **_key()},
                          json={"user_ids": [shop.ids["account_manager"]]})
    assert r.status_code == 200, r.text
    assert sum(1 for m in r.json()["data"] if m["left_at"] is None) == 3
    assert (await _row(client, am, cid))["unread_count"] == 2
    page = (await client.get(f"{V1}/conversations/{cid}/messages", headers=am)).json()["data"]
    assert [m["body"] for m in page] == ["one", "two"], "back in: the whole history"


async def test_the_manager_leaving_hands_over_and_only_the_manager_renames(
        client: httpx.AsyncClient, shop: Shop) -> None:
    fo, dm, am, _ = await _team(client, shop)
    cid = (await _create(client, fo, "Hand-over", [shop.ids["district_manager"], shop.ids["account_manager"]])).json()["data"]["id"]
    r = await client.patch(f"{V1}/conversations/{cid}", headers={**dm, **_key()}, json={"name": "Mine"})
    assert r.status_code == 403, r.text
    assert (await _remove(client, fo, cid, shop.ids["field_officer"])).status_code == 204
    # members added together tie on added_at; the lower user id takes over (edge E-4)
    expected = min(shop.ids["district_manager"], shop.ids["account_manager"])
    heir = dm if expected == shop.ids["district_manager"] else am
    other = am if heir is dm else dm
    row = await _row(client, heir, cid)
    assert row["group"]["manager_id"] == expected and row["group"]["i_manage"] and row["group"]["member_count"] == 2
    r = await client.patch(f"{V1}/conversations/{cid}", headers={**heir, **_key()}, json={"name": "  New name "})
    assert r.status_code == 200 and r.json()["data"]["group"]["name"] == "New name", r.text
    assert (await client.patch(f"{V1}/conversations/{cid}", headers={**other, **_key()}, json={"name": "x"})).status_code == 403
    assert (await _row(client, fo, cid)) is None, "the old manager left"


async def test_an_inactive_manager_is_replaced_by_the_next_member(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Edge E-3: a manager who leaves the company never leaves the group; the next
    active member acts as manager, and the others can still write (rule 5)."""
    fo, dm, am, _ = await _team(client, shop)
    cid = (await _create(client, dm, "Acting", [shop.ids["field_officer"], shop.ids["account_manager"]])).json()["data"]["id"]

    async def _active(on: bool) -> None:
        s = sessions()
        await s.execute(text("UPDATE app_user SET is_active = :on WHERE id = CAST(:u AS uuid)"),
                        {"on": on, "u": shop.ids["district_manager"]})
        await s.commit()
        await s.close()

    await _active(False)
    try:
        expected = min(shop.ids["field_officer"], shop.ids["account_manager"])
        acting = fo if expected == shop.ids["field_officer"] else am
        row = await _row(client, acting, cid)
        assert row["group"]["manager_id"] == expected and row["group"]["i_manage"], row
        assert (await _send(client, acting, cid, "the manager has left the company")).status_code == 201
        # code review: a batch naming a member who has left the company ignores them
        r = await client.post(f"{V1}/conversations/{cid}/members", headers={**acting, **_key()},
                              json={"user_ids": [shop.ids["district_manager"]]})
        assert r.status_code == 200, r.text
    finally:
        await _active(True)


@pytest.mark.parametrize(("body", "field"), [
    ({"name": "", "member_ids": ["00000000-0000-4000-8000-000000000001"]}, "name"),
    ({"name": "a\x00b", "member_ids": ["00000000-0000-4000-8000-000000000001"]}, "name"),
    ({"name": "x" * 81, "member_ids": ["00000000-0000-4000-8000-000000000001"]}, "name"),
    ({"name": "ok", "member_ids": []}, "member_ids"),
])
async def test_a_bad_group_is_a_422(client: httpx.AsyncClient, shop: Shop, body: dict, field: str) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/conversations/groups", headers={**fo, **_key()}, json=body)
    assert r.status_code == 422, r.text


async def test_who_may_be_in_a_group(client: httpx.AsyncClient, shop: Shop) -> None:
    fo, _, _, _ = await _team(client, shop)
    for who in (shop.ids["dealer"], "26809c63-290b-5bd9-9d6a-a717dc0b32e3"):
        r = await _create(client, fo, "Nope", [shop.ids["district_manager"], who])
        assert r.status_code == 422 and "member_ids" in r.json()["error"]["fields"], r.text
    r = await _create(client, fo, "Only me", [shop.ids["field_officer"]])
    assert r.status_code == 422, "yourself alone is no group"
    pair = (await client.post(f"{V1}/conversations", headers={**fo, **_key()},
                              json={"participant_id": shop.ids["district_manager"]})).json()["data"]
    r = await client.patch(f"{V1}/conversations/{pair['id']}", headers={**fo, **_key()}, json={"name": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_a_group", r.text


async def test_a_dealer_has_no_groups(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    from tests.api import test_complaints as cmp
    dealer, mobile = await cmp._dealer(client, shop, sessions)
    try:
        r = await _create(client, dealer, "Dealers", [shop.ids["field_officer"]])
        assert r.status_code == 403, r.text
    finally:
        await cmp._forget(sessions, mobile)


async def test_a_member_reads_no_conversation_events(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    fo, _, _, _ = await _team(client, shop)
    cid = (await _create(client, fo, "Audit", [shop.ids["district_manager"]])).json()["data"]["id"]
    s = sessions()
    try:
        assert (await s.execute(text("SELECT count(*) FROM activity_event WHERE entity_id = CAST(:c AS uuid)"),
                                {"c": cid})).scalar_one() == 1, "the owner sees the audit row"
        await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": shop.ids["field_officer"]})
        await s.execute(text("SELECT set_config('role', 'app_role', true)"))
        assert (await s.execute(text("SELECT count(*) FROM activity_event WHERE entity_type = 'conversation'"))).scalar_one() == 0
        assert (await s.execute(text("SELECT count(*) FROM conversation_member WHERE conversation_id = CAST(:c AS uuid)"),
                                {"c": cid})).scalar_one() == 1, "own row only (edge E-1), and no policy error"
    finally:
        await s.rollback()
        await s.close()


async def test_two_adds_racing_at_49_cannot_pass_the_cap(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """ISS-130: group_add counts under the conversation's row lock. Two adds at 49
    members: the first fills the group, the second waits, then counts 50 and is refused."""
    fo, _, _, _ = await _team(client, shop)
    fo_id = shop.ids["field_officer"]
    cid = (await _create(client, fo, "Cap race", [shop.ids["district_manager"]])).json()["data"]["id"]
    owner = sessions()
    users = [str(u) for u in (await owner.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id, is_active) "
        "SELECT 'staff', 'cap-' || gen_random_uuid() || '@test.invalid', 'Cap ' || n, u.role_id, u.org_unit_id, true "
        "FROM generate_series(1, 49) n, app_user u WHERE u.id = CAST(:fo AS uuid) RETURNING id"),
        {"fo": fo_id})).scalars()]
    await owner.execute(text("INSERT INTO conversation_member (conversation_id, user_id, added_by) "
                             "SELECT CAST(:c AS uuid), x, CAST(:fo AS uuid) FROM unnest(CAST(:u AS uuid[])) x"),
                        {"c": cid, "fo": fo_id, "u": users[:47]})   # 2 + 47 = 49
    await owner.commit()

    async def _as_fo(s: AsyncSession) -> None:
        await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": fo_id})
        await s.execute(text("SELECT set_config('role', 'app_role', true)"))

    first, second = sessions(), sessions()
    try:
        await _as_fo(first)
        await first.execute(text("SELECT group_add(CAST(:c AS uuid), CAST(:u AS uuid[]))"), {"c": cid, "u": [users[47]]})
        await _as_fo(second)

        async def _add_now() -> None:
            await second.execute(text("SELECT group_add(CAST(:c AS uuid), CAST(:u AS uuid[]))"), {"c": cid, "u": [users[48]]})

        task = asyncio.create_task(_add_now())
        await asyncio.sleep(1.0)            # the second add now waits on the conversation's lock
        await first.commit()
        with pytest.raises(DBAPIError, match="at most 50"):
            await task
        await second.rollback()
        count = (await owner.execute(text("SELECT count(*) FROM conversation_member WHERE conversation_id = CAST(:c AS uuid) "
                                          "AND left_at IS NULL"), {"c": cid})).scalar_one()
        assert count == 50
    finally:
        await second.rollback()
        await second.close()
        await first.close()
        await owner.rollback()
        await owner.execute(text("DELETE FROM activity_event WHERE entity_type = 'conversation' AND entity_id = CAST(:c AS uuid)"), {"c": cid})
        await owner.execute(text("DELETE FROM conversation WHERE id = CAST(:c AS uuid)"), {"c": cid})
        await owner.execute(text("DELETE FROM app_user WHERE id = ANY(CAST(:u AS uuid[]))"), {"u": users})
        await owner.commit()
        await owner.close()


async def test_a_send_racing_a_leave_is_refused_not_slipped_in(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Plan review R-3: the insert policy's snapshot predates the stamp's lock. A
    leave that commits while the send waits must refuse the send."""
    fo, _, _, _ = await _team(client, shop)
    cid = (await _create(client, fo, "Race", [shop.ids["district_manager"]])).json()["data"]["id"]
    dm_id = shop.ids["district_manager"]

    async def _as_dm(s: AsyncSession) -> None:
        await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": dm_id})
        await s.execute(text("SELECT set_config('role', 'app_role', true)"))

    leaver, sender = sessions(), sessions()
    try:
        await _as_dm(leaver)
        await leaver.execute(text("SELECT group_leave(CAST(:c AS uuid), CAST(:u AS uuid))"), {"c": cid, "u": dm_id})
        await _as_dm(sender)
        await sender.execute(text("SELECT 1 FROM conversation WHERE id = CAST(:c AS uuid)"), {"c": cid})  # snapshot: still in

        async def _send_now() -> None:
            await sender.execute(text("INSERT INTO message (conversation_id, sender_id, body) "
                                      "VALUES (CAST(:c AS uuid), CAST(:u AS uuid), 'slipped in?')"), {"c": cid, "u": dm_id})

        task = asyncio.create_task(_send_now())
        await asyncio.sleep(1.0)            # the send now waits on the conversation's lock
        await leaver.commit()
        with pytest.raises(DBAPIError, match="not a member"):
            await task
    finally:
        await sender.rollback()
        await sender.close()
        await leaver.close()
