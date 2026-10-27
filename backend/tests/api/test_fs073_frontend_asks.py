# ruff: noqa: E501  (SQL inline)

"""FS-073 over the API: restoring a deleted lead (BE-033), the deleted lead read
only, and the dashboard's overdue card counting tasks on leads only (BE-036).
BE-035's empty basket is in test_quotation_endpoints.py and test_gst_choice_freight.py."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api import test_leads_endpoints as le
from tests.api.conftest import Staff

pytestmark = pytest.mark.db

env = le.env
Env = le.Env
V1 = le.V1
Sessions = Callable[[], AsyncSession]


async def _grant_delete(sessions: Sessions, staff: Staff) -> None:
    """The fixture role has view, create and edit; the teardown removes its rows."""
    s = sessions()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) "
        "VALUES (:r, 'leads', 'delete', 'org_subtree')"), {"r": staff.role_id})
    await s.commit()
    await s.close()


async def _delete(client: httpx.AsyncClient, h: dict[str, str], lid: str) -> None:
    r = await client.delete(f"{V1}/leads/{lid}", headers={**h, **le._key()})
    assert r.status_code == 204, r.text


async def _restore(client: httpx.AsyncClient, h: dict[str, str], lid: str) -> httpx.Response:
    return await client.post(f"{V1}/leads/{lid}/restore", headers={**h, **le._key()})


async def _link_state(sessions: Sessions, a: str, b: str) -> str:
    s = sessions()
    state = (await s.execute(text(
        "SELECT state::text FROM lead_duplicate_link WHERE lead_a_id = LEAST(CAST(:a AS uuid), CAST(:b AS uuid)) "
        "AND lead_b_id = GREATEST(CAST(:a AS uuid), CAST(:b AS uuid))"), {"a": a, "b": b})).scalar_one()
    await s.close()
    return str(state)


# ── restore ─────────────────────────────────────────────────────────────────

async def test_restore_needs_delete(client: httpx.AsyncClient, staff: Staff, env: Env) -> None:
    h = await le._auth(client, staff)
    lid = await le._make(client, h, env)
    r = await _restore(client, h, lid)
    assert r.status_code == 403, r.text


async def test_restore_brings_it_back_with_its_pairs(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions: Sessions) -> None:
    """EC-1: the pair the delete closed reopens; a pair dismissed by hand stays so."""
    await _grant_delete(sessions, staff)
    h = await le._auth(client, staff)
    m = le._mobile()
    a = await le._make(client, h, env, mobile=m, farmer_name="Restore First")
    b = await le._make(client, h, env, mobile=m, farmer_name="Restore Second")
    c = await le._make(client, h, env, mobile=m, farmer_name="Restore Third")
    q = (await client.get(f"{V1}/leads/duplicates", headers=h)).json()["data"]
    by_hand = next(p for p in q if {p["lead_a"]["id"], p["lead_b"]["id"]} == {a, c})
    assert (await client.post(f"{V1}/leads/duplicates/{by_hand['link_id']}/dismiss",
                              headers={**h, **le._key()})).status_code == 200

    await _delete(client, h, a)
    assert await _link_state(sessions, a, b) == "dismissed"
    gone = (await client.get(f"{V1}/leads/{a}", headers=h)).json()["data"]
    assert gone["deleted_at"] and gone["deleted_by"] == {"id": staff.id, "full_name": gone["deleted_by"]["full_name"]}
    listed = (await client.get(f"{V1}/leads", headers=h, params={"deleted": "true"})).json()["data"]
    row = next(x for x in listed if x["id"] == a)
    assert row["deleted_at"] and row["deleted_by"]["id"] == staff.id

    r = await _restore(client, h, a)
    assert r.status_code == 200, r.text
    back = r.json()["data"]
    assert back["deleted_at"] is None and back["deleted_by"] is None
    assert await _link_state(sessions, a, b) == "pending"
    assert await _link_state(sessions, a, c) == "dismissed"
    kinds = [e["kind"] for e in (await client.get(f"{V1}/leads/{a}/timeline", headers=h)).json()["data"]]
    assert kinds.count("lead.restored") == 1

    # a live lead comes back unchanged, with no second event
    assert (await _restore(client, h, a)).status_code == 200
    kinds = [e["kind"] for e in (await client.get(f"{V1}/leads/{a}/timeline", headers=h)).json()["data"]]
    assert kinds.count("lead.restored") == 1


async def test_restore_out_of_scope_is_404(client: httpx.AsyncClient, staff: Staff, env: Env,
                                           sessions: Sessions) -> None:
    await _grant_delete(sessions, staff)
    h = await le._auth(client, staff)
    r = await _restore(client, h, "00000000-0000-4000-8000-000000000001")
    assert r.status_code == 404, r.text


async def test_a_merged_lead_restored_flags_nothing(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions: Sessions) -> None:
    """EC-4: a merged lead's pairs could only be dismissed."""
    await _grant_delete(sessions, staff)
    h = await le._auth(client, staff)
    m = le._mobile()
    loser = await le._make(client, h, env, mobile=m)
    survivor = await le._make(client, h, env, mobile=m)
    r = await client.post(f"{V1}/leads/{loser}/merge", json={"into_lead_id": survivor},
                          headers={**h, **le._key()})
    assert r.status_code == 200, r.text
    await _delete(client, h, loser)
    await le._make(client, h, env, mobile=m)          # a newcomer that looks like it
    s = sessions()
    before = (await s.execute(text(
        "SELECT count(*) FROM lead_duplicate_link WHERE lead_a_id = CAST(:l AS uuid) OR lead_b_id = CAST(:l AS uuid)"),
        {"l": loser})).scalar_one()
    await s.close()
    r = await _restore(client, h, loser)
    assert r.status_code == 200 and r.json()["data"]["stage"] == "merged", r.text
    s = sessions()
    after = (await s.execute(text(
        "SELECT count(*) FROM lead_duplicate_link WHERE (lead_a_id = CAST(:l AS uuid) OR lead_b_id = CAST(:l AS uuid)) "
        "AND state = 'pending'"), {"l": loser})).scalar_one()
    total = (await s.execute(text(
        "SELECT count(*) FROM lead_duplicate_link WHERE lead_a_id = CAST(:l AS uuid) OR lead_b_id = CAST(:l AS uuid)"),
        {"l": loser})).scalar_one()
    await s.close()
    assert after == 0 and total == before


# ── a deleted lead is read only ─────────────────────────────────────────────

async def test_every_change_to_a_deleted_lead_is_409(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions: Sessions) -> None:
    """EC-8: the check comes before the stage checks, so even a stale expected
    stage answers lead_deleted, and nothing changes."""
    await _grant_delete(sessions, staff)
    h = await le._auth(client, staff)
    lid = await le._make(client, h, env)
    await _delete(client, h, lid)
    calls = [
        ("POST", f"/leads/{lid}/notes", {"note": "still here?"}),
        ("PATCH", f"/leads/{lid}", {}),
        ("PATCH", f"/leads/{lid}", {"village": "Vadod"}),
        ("POST", f"/leads/{lid}/transition", {"to_stage": "contacted", "expected_stage": "won"}),
        ("POST", f"/leads/{lid}/reopen", {}),
        ("POST", f"/leads/{lid}/assign", {"owner_user_id": None}),        # code review F-5
    ]
    for method, path, body in calls:
        r = await client.request(method, f"{V1}{path}", json=body, headers={**h, **le._key()})
        assert r.status_code == 409 and r.json()["error"]["code"] == "lead_deleted", (path, r.text)
    got = (await client.get(f"{V1}/leads/{lid}", headers=h)).json()["data"]
    assert got["stage"] == "new" and got["village"] is None and got["owner"]["id"] == staff.id


async def test_merging_into_or_from_a_deleted_lead_is_409(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions: Sessions) -> None:
    """EC-2."""
    await _grant_delete(sessions, staff)
    h = await le._auth(client, staff)
    m = le._mobile()
    live = await le._make(client, h, env, mobile=m)
    gone = await le._make(client, h, env, mobile=m)
    await _delete(client, h, gone)
    for loser, survivor in ((live, gone), (gone, live)):
        r = await client.post(f"{V1}/leads/{loser}/merge", json={"into_lead_id": survivor},
                              headers={**h, **le._key()})
        assert r.status_code == 409 and r.json()["error"]["code"] == "lead_deleted", r.text
    assert (await client.get(f"{V1}/leads/{live}", headers=h)).json()["data"]["stage"] == "new"


async def test_a_pair_whose_leads_were_both_deleted_reopens_when_both_are_back(
        client: httpx.AsyncClient, staff: Staff, env: Env, sessions: Sessions) -> None:
    """Plan review R-1: closed by the first delete, so the second lead's own delete
    time never matches it. Any lead.deleted at the pair's resolved_at does."""
    await _grant_delete(sessions, staff)
    h = await le._auth(client, staff)
    m = le._mobile()
    x = await le._make(client, h, env, mobile=m)
    y = await le._make(client, h, env, mobile=m)
    await _delete(client, h, y)
    await _delete(client, h, x)
    assert (await _restore(client, h, y)).status_code == 200
    assert await _link_state(sessions, x, y) == "dismissed"      # x is still deleted
    r = await _restore(client, h, x)
    assert r.status_code == 200, r.text
    assert await _link_state(sessions, x, y) == "pending"
    events = (await client.get(f"{V1}/leads/{x}/timeline", headers=h)).json()["data"]
    restored = next(e for e in events if e["kind"] == "lead.restored")
    assert restored["payload"]["duplicates_reopened"][0]["lead_id"] == y
