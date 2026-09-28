"""FS-014 over the API: tasks, the planner, the team view and meeting minutes.

The world is the order tests' shop: one office with a user per seeded role and a
dealer's portal user. The other-office negatives are migration 018's tests."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import tasks as domain
from api.schemas import tasks as sch
from api.services import tasks as service
from api.services.clock import today_ist
from tests.api import test_order_concurrency as conc
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import PASSWORD, V1, _key, _login

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]


async def _as(client: httpx.AsyncClient, shop: Shop, role: str) -> dict[str, str]:
    return await _login(client, shop.users[role], PASSWORD)


async def _lead(client: httpx.AsyncClient, shop: Shop, h: dict[str, str]) -> str:
    r = await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Kiritbhai Shah", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod"})
    assert r.status_code == 201, r.text
    return str(r.json()["data"]["id"])


async def _create(client: httpx.AsyncClient, h: dict[str, str], **body: object) -> httpx.Response:
    body = {"title": "Call the farmer", "task_type": "call",
            "due_at": (today_ist() + dt.timedelta(days=1)).isoformat(), **body}
    return await client.post(f"{V1}/tasks", json=body, headers={**h, **_key()})


async def _meeting_type(client: httpx.AsyncClient, h: dict[str, str]) -> str:
    r = await client.get(f"{V1}/lookups/meeting-types", headers=h)
    assert r.status_code == 200, r.text
    return str(next(m["id"] for m in r.json()["data"] if m["code"] == "survey_design"))


def _held(days_ago: int) -> str:
    """A meeting time with a zone, some days back at 10:00 IST."""
    day = today_ist() - dt.timedelta(days=days_ago)
    return dt.datetime.combine(day, dt.time(10), tzinfo=domain.IST).isoformat()


def _code(r: httpx.Response) -> str:
    return str(r.json()["error"]["code"])


# ── creating ─────────────────────────────────────────────────────────────────

async def test_a_date_alone_is_due_at_six_in_the_evening_ist(client: httpx.AsyncClient,
                                                             shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    day = today_ist() + dt.timedelta(days=2)
    r = await _create(client, h, due_at=day.isoformat())
    assert r.status_code == 201, r.text
    task = r.json()["data"]
    assert dt.datetime.fromisoformat(task["due_at"]) == domain.due_from_date(day)
    assert task["assigned_to"]["id"] == shop.ids["field_officer"]
    assert task["assigned_by"]["id"] == shop.ids["field_officer"]
    assert task["status"] == "open" and not task["overdue"]


async def test_a_naive_time_is_refused(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    r = await _create(client, h, due_at="2026-10-02T10:30:00")
    assert r.status_code == 422 and "due_at" in r.json()["error"]["fields"], r.text


async def test_the_same_key_twice_makes_one_task(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    key = _key()
    body = {"title": "Visit", "task_type": "visit", "due_at": today_ist().isoformat()}
    first = await client.post(f"{V1}/tasks", json=body, headers={**h, **key})
    again = await client.post(f"{V1}/tasks", json=body, headers={**h, **key})
    assert first.status_code == again.status_code == 201
    assert first.json()["data"]["id"] == again.json()["data"]["id"]


async def test_an_officer_assigns_only_to_themselves(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    r = await _create(client, h, assigned_to=shop.ids["district_manager"])
    assert r.status_code == 422 and _code(r) == "not_assignable", r.text
    picker = (await client.get(f"{V1}/tasks/assignees", headers=h)).json()["data"]
    assert [p["id"] for p in picker] == [shop.ids["field_officer"]]


async def test_a_manager_assigns_below_but_only_about_what_the_assignee_can_open(
        client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await _as(client, shop, "district_manager")
    officer = await _as(client, shop, "field_officer")
    theirs = await _lead(client, shop, officer)
    mine = await _lead(client, shop, dm)
    r = await _create(client, dm, assigned_to=shop.ids["field_officer"], lead_id=mine)
    assert r.status_code == 422 and _code(r) == "link_not_visible_to_assignee", r.text
    r = await _create(client, dm, assigned_to=shop.ids["field_officer"], lead_id=theirs)
    assert r.status_code == 201, r.text
    task = r.json()["data"]
    assert task["lead"]["id"] == theirs and not task["lead"]["hidden"]
    picker = {p["id"] for p in (await client.get(f"{V1}/tasks/assignees", headers=dm)).json()["data"]}
    assert shop.ids["field_officer"] in picker


async def test_a_meeting_on_a_lead_carries_its_type_and_only_a_meeting_shows_a_gift(
        client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    lead = await _lead(client, shop, h)
    r = await _create(client, h, task_type="meeting", lead_id=lead)
    assert r.status_code == 422 and "meeting_type_id" in r.json()["error"]["fields"], r.text
    r = await _create(client, h, task_type="call", meeting_type_id=await _meeting_type(client, h))
    assert r.status_code == 422 and "meeting_type_id" in r.json()["error"]["fields"], r.text
    r = await _create(client, h, task_type="meeting", lead_id=lead,
                      meeting_type_id=await _meeting_type(client, h))
    assert r.status_code == 201, r.text
    assert r.json()["data"]["meeting_type"]["code"] == "survey_design"
    call = (await _create(client, h)).json()["data"]
    r = await client.post(f"{V1}/tasks/{call['id']}/complete", headers={**h, **_key()},
                          json={"outcome": "Spoke", "gift_shown": True})
    assert r.status_code == 422 and "gift_shown" in r.json()["error"]["fields"], r.text


async def test_one_link_at_most(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    lead = await _lead(client, shop, h)
    r = await _create(client, h, lead_id=lead, partner_id=shop.partner)
    assert r.status_code == 422 and "lead_id" in r.json()["error"]["fields"], r.text


# ── the life of a task ───────────────────────────────────────────────────────

async def test_complete_reopen_and_cancel_follow_the_rules(client: httpx.AsyncClient,
                                                           shop: Shop) -> None:
    dm = await _as(client, shop, "district_manager")
    officer = await _as(client, shop, "field_officer")
    given = (await _create(client, dm, assigned_to=shop.ids["field_officer"])).json()["data"]
    r = await client.post(f"{V1}/tasks/{given['id']}/cancel", headers={**officer, **_key()},
                          json={"reason": "Not needed"})
    assert r.status_code == 403, "an officer cannot cancel a manager's task"
    r = await client.post(f"{V1}/tasks/{given['id']}/complete", headers={**officer, **_key()},
                          json={"outcome": "Spoke to the farmer"})
    assert r.status_code == 200, r.text
    done = r.json()["data"]
    assert done["status"] == "done" and done["completed_by"]["id"] == shop.ids["field_officer"]
    r = await client.post(f"{V1}/tasks/{given['id']}/complete", headers={**officer, **_key()},
                          json={"outcome": "Again"})
    assert r.status_code == 409 and _code(r) == "task_not_open"
    r = await client.post(f"{V1}/tasks/{given['id']}/reopen", headers={**officer, **_key()})
    assert r.status_code == 200 and r.json()["data"]["status"] == "open", r.text
    assert r.json()["data"]["outcome"] is None and r.json()["data"]["completed_at"] is None
    r = await client.post(f"{V1}/tasks/{given['id']}/cancel", headers={**dm, **_key()},
                          json={"reason": "Farmer travelling"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled", r.text
    r = await client.post(f"{V1}/tasks/{given['id']}/reopen", headers={**dm, **_key()})
    assert r.status_code == 409, "a cancelled task is not reopened"


async def test_reopen_closes_after_seven_days(client: httpx.AsyncClient, shop: Shop,
                                              sessions: Sessions) -> None:
    h = await _as(client, shop, "field_officer")
    task = (await _create(client, h)).json()["data"]
    await client.post(f"{V1}/tasks/{task['id']}/complete", headers={**h, **_key()},
                      json={"outcome": "Done"})
    s = sessions()
    try:
        await s.execute(text("UPDATE task SET completed_at = now() - interval '8 days' "
                             "WHERE id = CAST(:t AS uuid)"), {"t": task["id"]})
        await s.commit()
    finally:
        await s.close()
    r = await client.post(f"{V1}/tasks/{task['id']}/reopen", headers={**h, **_key()})
    assert r.status_code == 409 and _code(r) == "reopen_window_passed", r.text


async def test_a_reassign_rehomes_the_task_and_the_old_assignee_loses_it(
        client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await _as(client, shop, "district_manager")
    officer = await _as(client, shop, "field_officer")
    task = (await _create(client, dm)).json()["data"]
    r = await client.patch(f"{V1}/tasks/{task['id']}", headers={**dm, **_key()},
                           json={"assigned_to": shop.ids["field_officer"]})
    assert r.status_code == 200 and r.json()["data"]["assigned_to"]["id"] == shop.ids["field_officer"]
    assert (await client.get(f"{V1}/tasks/{task['id']}", headers=officer)).status_code == 200
    r = await client.patch(f"{V1}/tasks/{task['id']}", headers={**dm, **_key()},
                           json={"assigned_to": shop.ids["district_manager"]})
    assert r.status_code == 200
    assert (await client.get(f"{V1}/tasks/{task['id']}", headers=officer)).status_code == 404


async def test_a_dealer_has_no_tasks_and_no_minutes(client: httpx.AsyncClient, shop: Shop,
                                                    sessions: Sessions) -> None:
    """Even on a lead that is the dealer's own (RBAC 6.3: tasks and minutes are internal)."""
    officer = await _as(client, shop, "field_officer")
    lead = await _lead(client, shop, officer)
    task = (await _create(client, officer, lead_id=lead)).json()["data"]
    r = await client.post(f"{V1}/minutes", headers={**officer, **_key()}, json={
        "lead_id": lead, "held_at": dt.datetime.now(domain.IST).isoformat(), "notes": "Met"})
    assert r.status_code == 201, r.text
    # the positive case first: staff see both on the lead's timeline, so their
    # absence for the dealer below is the rule, not missing events
    staff_kinds = {e["kind"] for e in (await client.get(
        f"{V1}/leads/{lead}/timeline", headers=officer)).json()["data"]}
    assert "task.created" in staff_kinds and any(k.startswith("minutes.") for k in staff_kinds), staff_kinds
    s = sessions()
    mobile = str((await s.execute(text("SELECT mobile FROM app_user WHERE id = CAST(:u AS uuid)"),
                                  {"u": shop.ids["dealer"]})).scalar_one())
    await s.execute(text("UPDATE lead SET assigned_partner_id = CAST(:p AS uuid) "
                         "WHERE id = CAST(:l AS uuid)"), {"p": shop.partner, "l": lead})
    await s.commit()
    await s.close()
    e164 = mobile if mobile.startswith("+") else "+" + mobile
    try:
        await client.post(f"{V1}/auth/otp/request", json={"mobile": mobile})
        c = sessions()
        code = (await c.execute(text(
            "SELECT payload ->> 'code' FROM notification_outbox WHERE recipient = :m "
            "ORDER BY created_at DESC LIMIT 1"), {"m": mobile})).scalar_one()
        await c.close()
        r = await client.post(f"{V1}/auth/otp/verify", json={"mobile": mobile, "code": code})
        assert r.status_code == 200, r.text
        h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
        assert (await client.get(f"{V1}/leads/{lead}", headers=h)).status_code == 200,             "the lead is the dealer's to read"
        for path, params in (("/tasks", {}), (f"/tasks/{task['id']}", {}), ("/planner", {}),
                             ("/minutes", {"lead_id": lead})):
            r = await client.get(f"{V1}{path}", headers=h, params=params)
            assert r.status_code == 403, (path, r.text)
        r = await client.get(f"{V1}/leads/{lead}/timeline", headers=h)
        assert r.status_code == 200, r.text
        kinds = {e["kind"] for e in r.json()["data"]}
        assert not {k for k in kinds if k.startswith(("task.", "minutes."))}, kinds
    finally:
        c = sessions()
        for stmt in ("DELETE FROM notification_outbox WHERE recipient IN (:m, :raw)",
                     "DELETE FROM login_attempt WHERE identifier IN (:m, :raw)"):
            await c.execute(text(stmt), {"m": e164, "raw": mobile})
        await c.commit()
        await c.close()


# ── the planner and the team ─────────────────────────────────────────────────

async def test_the_planner_splits_due_and_overdue_by_the_ist_day(client: httpx.AsyncClient,
                                                                 shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    today = today_ist()
    late = (await _create(client, h, due_at=(today - dt.timedelta(days=3)).isoformat())).json()["data"]
    now = (await _create(client, h, due_at=today.isoformat())).json()["data"]
    later = (await _create(client, h, due_at=(today + dt.timedelta(days=4)).isoformat())).json()["data"]
    # the date is given: a run crossing midnight IST must not compare two days
    day = (await client.get(f"{V1}/planner", headers=h,
                            params={"date": today.isoformat()})).json()["data"]
    assert day["date"] == today.isoformat()
    assert now["id"] in {t["id"] for t in day["due"]}
    assert late["id"] in {t["id"] for t in day["overdue"]}
    assert late["id"] not in {t["id"] for t in day["due"]}
    assert later["id"] not in {t["id"] for t in day["due"] + day["overdue"]}
    future = (await client.get(f"{V1}/planner", headers=h,
                               params={"date": (today + dt.timedelta(days=4)).isoformat()})).json()["data"]
    assert [(t["id"], t["due_at"]) for t in future["due"]] == [(later["id"], later["due_at"])], future
    assert future["overdue"] == []
    listed = (await client.get(f"{V1}/tasks", headers=h, params={"overdue": "true"})).json()["data"]
    # today's task is overdue too once 18:00 IST has passed
    assert listed[0]["id"] == late["id"] and all(t["overdue"] for t in listed)
    assert later["id"] not in {t["id"] for t in listed}


async def test_the_team_view_is_for_managers_and_lists_everyone(client: httpx.AsyncClient,
                                                                shop: Shop) -> None:
    officer = await _as(client, shop, "field_officer")
    dm = await _as(client, shop, "district_manager")
    assert (await client.get(f"{V1}/planner/team", headers=officer)).status_code == 403
    await _create(client, dm, assigned_to=shop.ids["field_officer"], due_at=today_ist().isoformat())
    rows = (await client.get(f"{V1}/planner/team", headers=dm)).json()["data"]
    by_id = {r["user"]["id"]: r for r in rows}
    assert by_id[shop.ids["field_officer"]]["due_today"] == 1
    r = await client.get(f"{V1}/planner", headers=dm, params={"user_id": shop.ids["field_officer"]})
    assert r.status_code == 200 and len(r.json()["data"]["due"]) == 1
    r = await client.get(f"{V1}/planner", headers=officer, params={"user_id": shop.ids["district_manager"]})
    assert r.status_code == 404, "an officer cannot read a manager's day"


# ── minutes ──────────────────────────────────────────────────────────────────

async def test_minutes_are_all_or_nothing(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    lead = await _lead(client, shop, h)
    r = await client.post(f"{V1}/minutes", headers={**h, **_key()}, json={
        "lead_id": lead, "held_at": dt.datetime.now(domain.IST).isoformat(), "notes": "Met",
        "action_items": [
            {"title": "Send the drawing", "due_at": today_ist().isoformat()},
            {"title": "Manager to call", "due_at": today_ist().isoformat(),
             "assigned_to": shop.ids["district_manager"]}]})
    assert r.status_code == 422 and _code(r) == "not_assignable", r.text
    assert "action_items[1].assigned_to" in r.json()["error"]["fields"]
    listed = await client.get(f"{V1}/minutes", headers=h, params={"lead_id": lead})
    assert listed.json()["data"] == []
    tasks = await client.get(f"{V1}/tasks", headers=h, params={"lead_id": lead})
    assert tasks.json()["data"] == [], "the first action item went back with the rest"


async def test_minutes_complete_their_meeting_and_raise_the_action_items(
        client: httpx.AsyncClient, shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    lead = await _lead(client, shop, h)
    meeting = (await _create(client, h, task_type="meeting", lead_id=lead,
                             meeting_type_id=await _meeting_type(client, h))).json()["data"]
    r = await client.post(f"{V1}/minutes", headers={**h, **_key()}, json={
        "lead_id": lead, "task_id": meeting["id"], "held_at": dt.datetime.now(domain.IST).isoformat(),
        "attendees": ["Kiritbhai Shah", "  ", "Pravinbhai"], "notes": "Walked the field",
        "action_items": [{"title": "Send the drawing", "due_at": today_ist().isoformat()}]})
    assert r.status_code == 201, r.text
    minutes = r.json()["data"]
    assert minutes["attendees"] == ["Kiritbhai Shah", "Pravinbhai"]
    [item] = minutes["action_items"]
    assert item["minutes_id"] == minutes["id"] and item["lead"]["id"] == lead
    done = (await client.get(f"{V1}/tasks/{meeting['id']}", headers=h)).json()["data"]
    assert done["status"] == "done" and done["outcome"] == domain.MINUTES_OUTCOME
    other = await _lead(client, shop, h)
    r = await client.post(f"{V1}/minutes", headers={**h, **_key()}, json={
        "lead_id": other, "task_id": meeting["id"], "held_at": dt.datetime.now(domain.IST).isoformat(),
        "notes": "Wrong lead"})
    assert r.status_code == 422 and _code(r) == "task_link_mismatch", r.text


# ── people leaving ───────────────────────────────────────────────────────────

async def test_a_leaver_with_open_tasks_is_handed_over_before_leaving(
        client: httpx.AsyncClient, shop: Shop) -> None:
    officer = await _as(client, shop, "field_officer")
    admin = await _as(client, shop, "admin_sales")
    task = (await _create(client, officer)).json()["data"]
    leaver = shop.ids["field_officer"]
    r = await client.patch(f"{V1}/users/{leaver}", headers={**admin, **_key()},
                           json={"is_active": False})
    assert r.status_code == 422 and "is_active" in r.json()["error"]["fields"], r.text
    r = await client.delete(f"{V1}/users/{leaver}", headers={**admin, **_key()})
    assert r.status_code == 422 and "open_tasks" in r.json()["error"]["fields"], r.text
    r = await client.post(f"{V1}/users/{leaver}/handover", headers={**admin, **_key()},
                          json={"to_user_id": shop.ids["district_manager"], "deactivate": True})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["tasks_moved"] == 1 and r.json()["data"]["deactivated"]
    moved = (await client.get(f"{V1}/tasks/{task['id']}", headers=admin)).json()["data"]
    assert moved["assigned_to"]["id"] == shop.ids["district_manager"]


# ── EC-4: two people act on one task at once ─────────────────────────────────

def _complete(shop: Shop, task_id: str) -> conc.Work:
    async def work(s: AsyncSession) -> object:
        caller = Caller(shop.ids["field_officer"], shop.office, None, scopes={"tasks": "own"})
        return await service.complete_task(s, caller, task_id, sch.TaskComplete(outcome="Spoke"))
    return work


def _cancel(shop: Shop, task_id: str) -> conc.Work:
    async def work(s: AsyncSession) -> object:
        caller = Caller(shop.ids["district_manager"], shop.office, None,
                        scopes={"tasks": "org_subtree"})
        return await service.cancel_task(s, caller, task_id, sch.TaskCancel(reason="Not needed"))
    return work


@pytest.mark.parametrize("complete_first", [True, False])
async def test_complete_and_cancel_at_once_leave_one_outcome(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, complete_first: bool) -> None:
    dm = await _as(client, shop, "district_manager")
    task = (await _create(client, dm, assigned_to=shop.ids["field_officer"])).json()["data"]
    complete = (shop.ids["field_officer"], _complete(shop, task["id"]))
    cancel = (shop.ids["district_manager"], _cancel(shop, task["id"]))
    got, waited = await conc._race(sessions, *((complete, cancel) if complete_first
                                               else (cancel, complete)))
    assert waited, "the second did not wait on the first: the race was not a race"
    assert [conc._outcome(g) for g in got] == ["ok", "task_not_open"], got
    final = (await client.get(f"{V1}/tasks/{task['id']}", headers=dm)).json()["data"]
    assert final["status"] == ("done" if complete_first else "cancelled")


# ── code review ──────────────────────────────────────────────────────────────

async def test_the_links_have_the_contracts_shape(client: httpx.AsyncClient, shop: Shop) -> None:
    """F-1: share/docs/21 promises these keys; the first build sent label and detail."""
    h = await _as(client, shop, "field_officer")
    lead = await _lead(client, shop, h)
    on_lead = (await _create(client, h, lead_id=lead)).json()["data"]
    assert set(on_lead["lead"]) == {"id", "hidden", "inquiry_no", "farmer_name"}
    assert on_lead["lead"]["inquiry_no"] and on_lead["lead"]["farmer_name"] == "Kiritbhai Shah"
    on_dealer = (await _create(client, h, partner_id=shop.partner)).json()["data"]
    assert on_dealer["partner"] == {"id": shop.partner, "hidden": False, "name": "Shah Irrigation",
                                    "partner_type": "dealer"}


async def test_the_assigner_cannot_reopen_for_a_deactivated_assignee(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """F-2: reopening asks the directory, which lists active people only."""
    dm = await _as(client, shop, "district_manager")
    officer = await _as(client, shop, "field_officer")
    admin = await _as(client, shop, "admin_sales")
    task = (await _create(client, dm, assigned_to=shop.ids["field_officer"])).json()["data"]
    await client.post(f"{V1}/tasks/{task['id']}/complete", headers={**officer, **_key()},
                      json={"outcome": "Done"})
    r = await client.patch(f"{V1}/users/{shop.ids['field_officer']}", headers={**admin, **_key()},
                           json={"is_active": False})
    assert r.status_code == 200, r.text
    r = await client.post(f"{V1}/tasks/{task['id']}/reopen", headers={**dm, **_key()})
    assert r.status_code == 409 and _code(r) == "assignee_inactive", r.text


async def test_minutes_refuse_a_time_without_a_zone(client: httpx.AsyncClient, shop: Shop) -> None:
    """F-3: a naive held_at was stored in whichever zone the server ran in."""
    h = await _as(client, shop, "field_officer")
    lead = await _lead(client, shop, h)
    r = await client.post(f"{V1}/minutes", headers={**h, **_key()}, json={
        "lead_id": lead, "held_at": "2026-10-02T15:00:00", "notes": "Met"})
    assert r.status_code == 422 and "held_at" in str(r.json()["error"]["fields"]), r.text


async def test_a_manager_cannot_cancel_what_their_superior_gave_them(
        client: httpx.AsyncClient, shop: Shop) -> None:
    """F-7: only an own-scoped assignee was refused; a District Manager got through."""
    admin = await _as(client, shop, "admin_sales")
    dm = await _as(client, shop, "district_manager")
    task = (await _create(client, admin, assigned_to=shop.ids["district_manager"])).json()["data"]
    r = await client.post(f"{V1}/tasks/{task['id']}/cancel", headers={**dm, **_key()},
                          json={"reason": "Busy"})
    assert r.status_code == 403, r.text
    mine = (await _create(client, dm)).json()["data"]
    r = await client.post(f"{V1}/tasks/{mine['id']}/cancel", headers={**dm, **_key()},
                          json={"reason": "Busy"})
    assert r.status_code == 200, "your own task is yours to cancel"


async def test_a_team_cursor_with_a_bad_id_is_a_422(client: httpx.AsyncClient, shop: Shop) -> None:
    """F-9: it decoded, then the cast failed as a 500."""
    import base64
    dm = await _as(client, shop, "district_manager")
    cursor = base64.urlsafe_b64encode(b"Asha\x1fnot-a-uuid").decode()
    r = await client.get(f"{V1}/planner/team", headers=dm, params={"cursor": cursor})
    assert r.status_code == 422, r.text
    r = await client.get(f"{V1}/planner/team", headers=dm,
                         params={"org_unit_id": str(uuid.uuid4())})
    assert r.status_code == 404, "an office outside your reach"


async def test_many_minutes_keep_their_own_action_items(client: httpx.AsyncClient,
                                                        shop: Shop) -> None:
    """F-10: the list is built in three statements; the items must not cross over."""
    h = await _as(client, shop, "field_officer")
    lead = await _lead(client, shop, h)
    for n in (1, 2):
        r = await client.post(f"{V1}/minutes", headers={**h, **_key()}, json={
            "lead_id": lead, "held_at": _held(3 - n), "notes": f"Meeting {n}",
            "action_items": [{"title": f"Item {n}.{i}", "due_at": today_ist().isoformat()}
                             for i in range(n)]})
        assert r.status_code == 201, r.text
    listed = (await client.get(f"{V1}/minutes", headers=h, params={"lead_id": lead})).json()["data"]
    assert [m["notes"] for m in listed] == ["Meeting 2", "Meeting 1"], "newest first"
    # grouping is the point; items due at the same time have no set order
    assert [sorted(i["title"] for i in m["action_items"]) for m in listed] == [
        ["Item 2.0", "Item 2.1"], ["Item 1.0"]]


async def test_a_refusal_names_the_field_it_is_about(client: httpx.AsyncClient, shop: Shop) -> None:
    """F-11: every refusal came back on lead_id."""
    h = await _as(client, shop, "field_officer")
    r = await _create(client, h, partner_id=str(uuid.uuid4()))
    assert r.status_code == 422 and set(r.json()["error"]["fields"]) == {"partner_id"}, r.text
    r = await _create(client, h, sales_order_id=str(uuid.uuid4()))
    assert r.status_code == 422 and set(r.json()["error"]["fields"]) == {"sales_order_id"}, r.text


async def test_the_branches_the_review_found_untested(client: httpx.AsyncClient,
                                                      shop: Shop) -> None:
    h = await _as(client, shop, "field_officer")
    lead = await _lead(client, shop, h)
    task = (await _create(client, h)).json()["data"]
    r = await client.patch(f"{V1}/tasks/{task['id']}", headers={**h, **_key()},
                           json={"title": "Call again", "expected_status": "done"})
    assert r.status_code == 409 and _code(r) == "status_changed", r.text
    far = (today_ist() + dt.timedelta(days=800)).isoformat()
    r = await _create(client, h, due_at=far)
    assert r.status_code == 422 and "due_at" in r.json()["error"]["fields"], r.text
    meeting = (await _create(client, h, task_type="meeting", lead_id=lead,
                             meeting_type_id=await _meeting_type(client, h))).json()["data"]
    r = await client.post(f"{V1}/tasks/{meeting['id']}/complete", headers={**h, **_key()},
                          json={"outcome": "Showed the kit", "gift_shown": True})
    assert r.status_code == 200 and r.json()["data"]["gift_shown"] is True, r.text
    cancelled = (await _create(client, h, task_type="meeting", lead_id=lead,
                               meeting_type_id=await _meeting_type(client, h))).json()["data"]
    await client.post(f"{V1}/tasks/{cancelled['id']}/cancel", headers={**h, **_key()},
                      json={"reason": "Farmer away"})
    r = await client.post(f"{V1}/minutes", headers={**h, **_key()}, json={
        "lead_id": lead, "task_id": cancelled["id"], "held_at": _held(1),
        "notes": "Met anyway"})
    assert r.status_code == 409 and _code(r) == "task_not_open", r.text
    r = await client.post(f"{V1}/minutes", headers={**h, **_key()}, json={
        "partner_id": shop.partner, "held_at": _held(1), "notes": "Dealer meet",
        "action_items": [{"title": "Send the rate card", "due_at": today_ist().isoformat()}]})
    assert r.status_code == 201, r.text
    minutes = r.json()["data"]
    assert minutes["partner"]["partner_type"] == "dealer"
    assert minutes["action_items"][0]["partner"]["id"] == shop.partner



# ── cross-vendor review (astra) ──────────────────────────────────────────────

async def test_a_reopened_task_follows_its_assignee_to_the_new_office(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Astra P1, reproduced: the office-move trigger moves open tasks only, so a done
    task reopened after a move stayed in the old office."""
    h = await _as(client, shop, "field_officer")
    task = (await _create(client, h)).json()["data"]
    await client.post(f"{V1}/tasks/{task['id']}/complete", headers={**h, **_key()}, json={"outcome": "Done"})
    s = sessions()
    new_office = str((await s.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, CAST(:t AS uuid)) RETURNING id"),
        {"n": f"astra office {uuid.uuid4().hex[:6]}", "t": shop.district})).scalar_one())
    await s.execute(text("UPDATE app_user SET org_unit_id = CAST(:o AS uuid) WHERE id = CAST(:u AS uuid)"),
                    {"o": new_office, "u": shop.ids["field_officer"]})
    await s.commit()
    await s.close()
    try:
        h = await _as(client, shop, "field_officer")          # the claim carries the new office
        r = await client.post(f"{V1}/tasks/{task['id']}/reopen", headers={**h, **_key()})
        assert r.status_code == 200, r.text
        c = sessions()
        office = (await c.execute(text("SELECT owner_org_unit_id::text FROM task WHERE id = CAST(:t AS uuid)"),
                                  {"t": task["id"]})).scalar_one()
        await c.close()
        assert office == new_office
    finally:
        c = sessions()
        await c.execute(text("UPDATE app_user SET org_unit_id = CAST(:o AS uuid) WHERE id = CAST(:u AS uuid)"),
                        {"o": shop.office, "u": shop.ids["field_officer"]})
        await c.execute(text("UPDATE task SET owner_org_unit_id = CAST(:o AS uuid) WHERE owner_org_unit_id = CAST(:n AS uuid)"),
                        {"o": shop.office, "n": new_office})
        await c.execute(text("DELETE FROM org_unit WHERE id = CAST(:n AS uuid)"), {"n": new_office})
        await c.commit()
        await c.close()


async def test_minutes_complete_only_a_meeting(client: httpx.AsyncClient, shop: Shop) -> None:
    """Astra P2, reproduced: a call on the same lead was completed as 'Minutes recorded'."""
    h = await _as(client, shop, "field_officer")
    lead = await _lead(client, shop, h)
    call = (await _create(client, h, lead_id=lead)).json()["data"]
    r = await client.post(f"{V1}/minutes", headers={**h, **_key()}, json={
        "lead_id": lead, "task_id": call["id"], "held_at": _held(1), "notes": "Met"})
    assert r.status_code == 422 and _code(r) == "task_not_a_meeting", r.text
    still = (await client.get(f"{V1}/tasks/{call['id']}", headers=h)).json()["data"]
    assert still["status"] == "open"


async def test_a_merged_lead_takes_no_new_tasks_or_minutes(client: httpx.AsyncClient,
                                                           shop: Shop) -> None:
    """PR 25 review: the merge moves tasks once, so a task added to the loser
    afterwards (a stale screen, an offline sync) sat on a hidden lead for good."""
    officer = await _as(client, shop, "field_officer")
    survivor = await _lead(client, shop, officer)
    loser = await _lead(client, shop, officer)
    r = await client.post(f"{V1}/leads/{loser}/merge", json={"into_lead_id": survivor},
                          headers={**officer, **_key()})
    assert r.status_code == 200, r.text
    r = await _create(client, officer, lead_id=loser)
    assert r.status_code == 422 and _code(r) == "lead_merged", r.text
    assert "lead_id" in r.json()["error"]["fields"]
    r = await client.post(f"{V1}/minutes", headers={**officer, **_key()}, json={
        "lead_id": loser, "held_at": _held(0), "notes": "Met"})
    assert r.status_code == 422 and _code(r) == "lead_merged", r.text
    # the survivor still takes both
    assert (await _create(client, officer, lead_id=survivor)).status_code == 201
    r = await client.post(f"{V1}/minutes", headers={**officer, **_key()}, json={
        "lead_id": survivor, "held_at": _held(0), "notes": "Met"})
    assert r.status_code == 201, r.text


async def test_a_list_cursor_with_a_bad_id_is_a_422(client: httpx.AsyncClient, shop: Shop) -> None:
    """PR 25 review: F-9 fixed the team cursor only; the shared decoder let a bad id
    reach CAST(... AS uuid) on the task and complaint lists."""
    import base64
    h = await _as(client, shop, "field_officer")
    cursor = base64.urlsafe_b64encode(b"2026-08-01T00:00:00+00:00|not-a-uuid").decode()
    for path in ("/tasks", "/complaints", "/leads"):
        r = await client.get(f"{V1}{path}", headers=h, params={"cursor": cursor})
        assert r.status_code == 422 and "cursor" in r.json()["error"]["fields"], (path, r.text)
