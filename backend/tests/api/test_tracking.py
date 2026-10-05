"""FS-021 over the API: config, consent, duty, location batches, visits, the team
map, a day's route and the view log. The sibling-office negatives are in
tests/db/test_migration_030.py, where two offices exist."""

# ruff: noqa: E501  (request bodies inline)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import tracking as domain
from tests.api import test_complaints as complaints_t
from tests.api import test_notifications as notif
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
DEVICE = "test-device-0001"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest_asyncio.fixture(autouse=True)
async def _forget_tracking(shop: Shop, sessions: Sessions) -> AsyncIterator[None]:
    """Torn down before `shop`, which deletes its leads and users: the tracking rows
    reference both."""
    yield
    people = list(shop.ids.values())
    s = sessions()
    try:
        for stmt in (
            "DELETE FROM tracking_view_log WHERE viewer_id = ANY(CAST(:p AS uuid[])) OR subject_user_id = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM visit_photo WHERE visit_id IN (SELECT id FROM visit WHERE user_id = ANY(CAST(:p AS uuid[])))",
            "DELETE FROM activity_event WHERE entity_id IN (SELECT id FROM visit WHERE user_id = ANY(CAST(:p AS uuid[])))",
            "DELETE FROM visit WHERE user_id = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM location_point WHERE user_id = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM tracking_latest WHERE user_id = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM duty_session WHERE user_id = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM tracking_consent WHERE user_id = ANY(CAST(:p AS uuid[]))",
        ):
            await s.execute(text(stmt), {"p": people})
        await s.commit()
    finally:
        await s.close()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


async def _post(client: httpx.AsyncClient, h: dict[str, str], path: str, body: dict[str, Any]) -> httpx.Response:
    return await client.post(f"{V1}{path}", headers={**h, **_key()}, json=body)


async def _consent(client: httpx.AsyncClient, h: dict[str, str], accepted: bool = True) -> None:
    cfg = (await client.get(f"{V1}/me/tracking-config", headers=h)).json()["data"]
    r = await _post(client, h, "/tracking/consent", {"version": cfg["consent"]["required_version"], "accepted": accepted})
    assert r.status_code == 201, r.text


async def _on_duty(client: httpx.AsyncClient, h: dict[str, str]) -> str:
    await _consent(client, h)
    r = await _post(client, h, "/tracking/duty/start", {
        "id": str(uuid.uuid4()), "device_id": DEVICE, "at": (_now() - dt.timedelta(hours=1)).isoformat(),
        "lat": 23.0225, "lng": 72.5714, "accuracy_m": 10})
    assert r.status_code in (200, 201), r.text
    return str(r.json()["data"]["id"])


def _pt(duty: str, minutes_ago: float, **over: Any) -> dict[str, Any]:
    p = {"id": str(uuid.uuid4()), "duty_id": duty, "recorded_at": (_now() - dt.timedelta(minutes=minutes_ago)).isoformat(),
         "lat": 23.0225 + minutes_ago / 10_000, "lng": 72.5714, "accuracy_m": 8, "battery_pct": 70}
    p.update(over)
    return p


async def _batch(client: httpx.AsyncClient, h: dict[str, str], points: list[dict[str, Any]],
                 sent_at: dt.datetime | None = None) -> httpx.Response:
    return await _post(client, h, "/locations/batch", {
        "device_id": DEVICE, "sent_at": (sent_at or _now()).isoformat(), "points": points})


# ── config, consent, duty ───────────────────────────────────────────────────

async def test_config_says_who_tracks(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    cfg = (await client.get(f"{V1}/me/tracking-config", headers=fo)).json()["data"]
    assert cfg["tracking_allowed"] is True and cfg["max_batch_points"] == 500
    assert cfg["working_hours"]["days"] == [1, 2, 3, 4, 5, 6] and cfg["consent"]["text"]
    accounts = await endpoints._as(client, shop, "account_manager")
    assert (await client.get(f"{V1}/me/tracking-config", headers=accounts)).json()["data"]["tracking_allowed"] is False
    dealer, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        assert (await client.get(f"{V1}/me/tracking-config", headers=dealer)).status_code == 403
    finally:
        await complaints_t._forget(sessions, mobile)


async def test_duty_needs_consent_and_a_second_start_returns_the_open_one(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    body = {"id": str(uuid.uuid4()), "device_id": DEVICE, "at": _now().isoformat(), "lat": 23.0, "lng": 72.5}
    r = await _post(client, fo, "/tracking/duty/start", body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "consent_required", r.text
    await _consent(client, fo)
    r = await _post(client, fo, "/tracking/duty/start", body)
    assert r.status_code == 201, r.text
    first = r.json()["data"]["id"]
    r = await _post(client, fo, "/tracking/duty/start", {**body, "id": str(uuid.uuid4())})
    assert r.status_code == 200 and r.json()["data"]["id"] == first, "a reinstall adopts the open session"
    cfg = (await client.get(f"{V1}/me/tracking-config", headers=fo)).json()["data"]
    assert cfg["on_duty"]["id"] == first
    end = {"id": first, "at": _now().isoformat(), "lat": 23.01, "lng": 72.51}
    r = await _post(client, fo, "/tracking/duty/end", end)
    assert r.status_code == 200 and r.json()["data"]["end_reason"] == "user", r.text
    assert (await _post(client, fo, "/tracking/duty/end", end)).status_code == 200, "ending twice is settled"
    dm = await endpoints._as(client, shop, "district_manager")
    r = await _post(client, dm, "/tracking/duty/end", end)
    assert r.status_code == 404 and r.json()["error"]["code"] == "duty_not_found", "a manager ends nobody's duty"


# ── batches ─────────────────────────────────────────────────────────────────

async def test_a_batch_accepts_dedupes_and_rejects_with_reasons(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    duty = await _on_duty(client, fo)
    good = [_pt(duty, m) for m in (30, 20, 10)]
    early = _pt(duty, 120)                      # before the duty started
    unknown = _pt(str(uuid.uuid4()), 5)
    broken = _pt(duty, 4, lat=0.0, lng=0.0)
    r = await _batch(client, fo, [*good, early, unknown, broken])
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["accepted"] == 3 and d["duplicates"] == 0
    assert {x["id"]: x["reason"] for x in d["rejected"]} == {
        early["id"]: "off_duty", unknown["id"]: "unknown_duty", broken["id"]: "bad_coordinates"}
    assert d["duty"]["id"] == duty and d["duty"]["ended_at"] is None
    again = await _batch(client, fo, [*good[:2], _pt(duty, 1)])
    assert again.json()["data"] == {"accepted": 1, "duplicates": 2, "rejected": [],
                                    "duty": {"id": duty, "ended_at": None, "end_reason": None}}


async def test_a_phone_clock_ten_minutes_fast_is_corrected_not_refused(client: httpx.AsyncClient, shop: Shop,
                                                                       sessions: Sessions) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    duty = await _on_duty(client, fo)
    fast = dt.timedelta(minutes=10)
    p = _pt(duty, 0, recorded_at=(_now() + fast).isoformat())
    r = await _batch(client, fo, [p], sent_at=_now() + fast)
    assert r.json()["data"]["accepted"] == 1, r.text
    s = sessions()
    try:
        skew = (await s.execute(text("SELECT clock_skew_s FROM location_point WHERE id = CAST(:p AS uuid)"),
                                {"p": p["id"]})).scalar_one()
    finally:
        await s.close()
    assert -660 < skew < -540
    r = await _batch(client, fo, [_pt(duty, 1)], sent_at=_now() + dt.timedelta(days=2))
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_clock"


async def test_an_oversized_batch_is_refused_whole(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    duty = await _on_duty(client, fo)
    r = await _batch(client, fo, [_pt(duty, 1) for _ in range(501)])
    assert r.status_code == 422 and r.json()["error"]["code"] == "batch_too_large"


async def test_another_users_point_id_is_refused_not_counted_a_duplicate(client: httpx.AsyncClient, shop: Shop) -> None:
    """Review B-6: ON CONFLICT DO NOTHING under RLS would have lost it silently."""
    fo = await endpoints._as(client, shop, "field_officer")
    dm = await endpoints._as(client, shop, "district_manager")
    mine = _pt(await _on_duty(client, fo), 5)
    assert (await _batch(client, fo, [mine])).json()["data"]["accepted"] == 1
    theirs = _pt(await _on_duty(client, dm), 4, id=mine["id"])
    d = (await _batch(client, dm, [theirs])).json()["data"]
    assert d["duplicates"] == 0 and d["rejected"] == [{"id": mine["id"], "reason": "id_in_use"}]


async def test_withdrawing_consent_ends_duty_and_drains_the_queue(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    duty = await _on_duty(client, fo)
    await _consent(client, fo, accepted=False)
    r = await _batch(client, fo, [_pt(duty, 3), _pt(duty, 2)])
    d = r.json()["data"]
    assert r.status_code == 200 and d["accepted"] == 0
    assert {x["reason"] for x in d["rejected"]} == {"consent_withdrawn"}
    assert d["duty"]["end_reason"] == "consent_withdrawn", "the app flips its toggle off"


# ── visits ──────────────────────────────────────────────────────────────────

async def test_a_visit_checks_in_refuses_a_second_and_checks_out(client: httpx.AsyncClient, shop: Shop,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    await _consent(client, fo)
    lead = await notif._lead(client, shop, fo)
    body = {"id": str(uuid.uuid4()), "lead_id": lead["id"], "at": _now().isoformat(), "lat": 23.02, "lng": 72.57,
            "accuracy_m": 9}
    r = await _post(client, fo, "/visits", body)
    assert r.status_code == 201 and r.json()["data"]["lead"]["id"] == lead["id"], r.text
    vid = r.json()["data"]["id"]
    assert (await _post(client, fo, "/visits", body)).status_code == 200, "the same id again"
    r = await _post(client, fo, "/visits", {**body, "id": str(uuid.uuid4())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "visit_open"
    assert r.json()["error"]["fields"]["visit_id"] == vid
    storage = complaints_t._Counting()
    monkeypatch.setattr("api.routers.tracking.get_storage", lambda *a, **k: storage)
    r = await client.post(f"{V1}/visits/{vid}/photos", headers={**fo, **_key()},
                          files={"file": ("farm.png", PNG, "image/png")})
    assert r.status_code == 201 and storage.puts == 1, r.text
    r = await _post(client, fo, f"/visits/{vid}/check-out", {
        "at": (_now() + dt.timedelta(minutes=1)).isoformat(), "lat": 23.02, "lng": 72.57, "outcome": "met",
        "note": "Wants a quote"})
    assert r.status_code == 200 and r.json()["data"]["outcome"] == "met" and r.json()["data"]["photo_count"] == 1
    r = await _post(client, fo, f"/visits/{vid}/check-out", {"at": _now().isoformat(), "lat": 1, "lng": 1, "outcome": "met"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "visit_closed"
    timeline = (await client.get(f"{V1}/leads/{lead['id']}/timeline", headers=fo)).json()["data"]
    assert {"visit.checked_in", "visit.checked_out"} <= {e["kind"] for e in timeline}


async def test_a_visit_needs_somewhere_and_a_task_of_ones_own(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    await _consent(client, fo)
    base = {"at": _now().isoformat(), "lat": 23.02, "lng": 72.57}
    r = await _post(client, fo, "/visits", {"id": str(uuid.uuid4()), **base})
    assert r.status_code == 422, r.text
    r = await _post(client, fo, "/visits", {"id": str(uuid.uuid4()), "task_id": str(uuid.uuid4()),
                                            "place_name": "Mandi", **base})
    assert r.status_code == 404, r.text


# ── the map, the route, the log ─────────────────────────────────────────────

async def test_the_manager_sees_the_team_and_every_look_is_logged(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    duty = await _on_duty(client, fo)
    # a ten-minute dwell, then a drive: one stop
    pts = [_pt(duty, 25 - m, lat=23.0300, lng=72.5800) for m in range(0, 12)]
    pts += [_pt(duty, 12 - m, lat=23.0300 + 0.01 * (m + 1), lng=72.5800) for m in range(5)]
    assert (await _batch(client, fo, pts)).json()["data"]["accepted"] == len(pts)
    dm = await endpoints._as(client, shop, "district_manager")
    team = (await client.get(f"{V1}/tracking/team/latest", headers=dm)).json()["data"]
    me = next(m for m in team if m["user"]["id"] == shop.ids["field_officer"])
    assert me["on_duty"] and me["lat"] is not None and me["stale"] is False
    today = dt.datetime.now(domain.IST).date().isoformat()
    r = await client.get(f"{V1}/tracking/users/{shop.ids['field_officer']}/route", headers=dm, params={"date": today})
    assert r.status_code == 200, r.text
    route = r.json()["data"]
    assert route["point_count"] >= len(pts) and float(route["distance_km"]) > 4
    assert len(route["stops"]) >= 1 and route["stops"][0]["minutes"] >= 10
    own = await client.get(f"{V1}/tracking/users/{shop.ids['field_officer']}/route", headers=fo, params={"date": today})
    assert own.status_code == 200
    admin = await endpoints._as(client, shop, "admin_sales")
    log = (await client.get(f"{V1}/tracking/view-log", headers=admin,
                            params={"subject_user_id": shop.ids["field_officer"]})).json()["data"]
    viewers = {(x["viewer"]["id"], x["what"]) for x in log}
    assert (shop.ids["district_manager"], "route") in viewers
    assert (shop.ids["field_officer"], "route") not in viewers, "one's own route is not logged"
    assert (await client.get(f"{V1}/tracking/view-log", headers=dm)).json()["data"] == [], \
        "a manager writes the log but does not read it"


async def test_who_may_not_track(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    accounts = await endpoints._as(client, shop, "account_manager")
    assert (await client.get(f"{V1}/tracking/team/latest", headers=accounts)).status_code == 403
    today = dt.datetime.now(domain.IST).date().isoformat()
    dealer, mobile = await complaints_t._dealer(client, shop, sessions)
    try:
        r = await client.get(f"{V1}/tracking/users/{shop.ids['field_officer']}/route", headers=dealer, params={"date": today})
        assert r.status_code == 403
    finally:
        await complaints_t._forget(sessions, mobile)
    fo = await endpoints._as(client, shop, "field_officer")
    r = await client.get(f"{V1}/tracking/users/{shop.ids['district_manager']}/route", headers=fo, params={"date": today})
    assert r.status_code == 404, "an officer's team is themselves"
    policy = {"effective_from": (_now() + dt.timedelta(days=1)).isoformat(), "interval_seconds": 120,
              "distance_filter_m": 50, "work_start": "09:00", "work_end": "19:00", "work_days": [1, 2, 3, 4, 5, 6],
              "retention_days": 90, "visit_photo_required": False, "consent_version": "v1", "consent_text": "x"}
    r = await client.put(f"{V1}/tracking/policy", headers={**fo, **_key()}, json=policy)
    assert r.status_code == 403, r.text


async def test_a_fast_phone_starts_duty_on_the_server_clock(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-1: the start is corrected as the points are, so the first point
    after it is on duty."""
    fo = await endpoints._as(client, shop, "field_officer")
    await _consent(client, fo)
    fast = dt.timedelta(minutes=10)
    r = await _post(client, fo, "/tracking/duty/start", {
        "id": str(uuid.uuid4()), "device_id": DEVICE, "at": (_now() + fast).isoformat(),
        "sent_at": (_now() + fast).isoformat(), "lat": 23.02, "lng": 72.57})
    assert r.status_code == 201, r.text
    duty = r.json()["data"]["id"]
    p = _pt(duty, 0, recorded_at=(_now() + fast + dt.timedelta(minutes=1)).isoformat())
    d = (await _batch(client, fo, [p], sent_at=_now() + fast + dt.timedelta(minutes=1))).json()["data"]
    assert d["accepted"] == 1, d


async def test_a_mixed_batch_sorts_mine_theirs_and_new(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-4: the per-row fallback with more than one row."""
    fo = await endpoints._as(client, shop, "field_officer")
    dm = await endpoints._as(client, shop, "district_manager")
    theirs = _pt(await _on_duty(client, fo), 6)
    assert (await _batch(client, fo, [theirs])).json()["data"]["accepted"] == 1
    duty = await _on_duty(client, dm)
    mine = _pt(duty, 5)
    assert (await _batch(client, dm, [mine])).json()["data"]["accepted"] == 1
    fresh = _pt(duty, 4)
    d = (await _batch(client, dm, [mine, {**_pt(duty, 3), "id": theirs["id"]}, fresh])).json()["data"]
    assert d["accepted"] == 1 and d["duplicates"] == 1
    assert d["rejected"] == [{"id": theirs["id"], "reason": "id_in_use"}]


async def test_photos_stop_at_three_and_after_a_day(client: httpx.AsyncClient, shop: Shop, sessions: Sessions,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    await _consent(client, fo)
    r = await _post(client, fo, "/visits", {"id": str(uuid.uuid4()), "place_name": "Mandi", "at": _now().isoformat(),
                                             "lat": 23.02, "lng": 72.57})
    vid = r.json()["data"]["id"]
    storage = complaints_t._Counting()
    monkeypatch.setattr("api.routers.tracking.get_storage", lambda *a, **k: storage)
    for i in range(3):
        r = await client.post(f"{V1}/visits/{vid}/photos", headers={**fo, **_key()},
                              files={"file": (f"p{i}.png", PNG + bytes([i]), "image/png")})
        assert r.status_code == 201, r.text
    r = await client.post(f"{V1}/visits/{vid}/photos", headers={**fo, **_key()},
                          files={"file": ("p4.png", PNG + b"\x09", "image/png")})
    assert r.status_code == 409 and r.json()["error"]["code"] == "photo_limit"
    assert storage.puts == 3, "a refused photo costs no object (F-5)"
    s = sessions()
    try:
        await s.execute(text("UPDATE visit SET checkin_at = now() - interval '25 hours' WHERE id = CAST(:v AS uuid)"), {"v": vid})
        await s.execute(text("DELETE FROM visit_photo WHERE visit_id = CAST(:v AS uuid)"), {"v": vid})
        await s.commit()
    finally:
        await s.close()
    r = await client.post(f"{V1}/visits/{vid}/photos", headers={**fo, **_key()},
                          files={"file": ("late.png", PNG + b"\x0a", "image/png")})
    assert r.status_code == 409 and r.json()["error"]["code"] == "photo_window_closed"


async def test_the_team_map_and_another_persons_visits_are_logged(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-4: the team row and the visit reads."""
    fo = await endpoints._as(client, shop, "field_officer")
    await _consent(client, fo)
    r = await _post(client, fo, "/visits", {"id": str(uuid.uuid4()), "place_name": "Mandi", "at": _now().isoformat(),
                                             "lat": 23.02, "lng": 72.57})
    vid = r.json()["data"]["id"]
    dm = await endpoints._as(client, shop, "district_manager")
    assert (await client.get(f"{V1}/tracking/team/latest", headers=dm)).status_code == 200
    assert (await client.get(f"{V1}/visits/{vid}", headers=dm)).status_code == 200
    assert (await client.get(f"{V1}/visits", headers=fo, params={"user_id": "me"})).status_code == 200
    admin = await endpoints._as(client, shop, "admin_sales")
    log = (await client.get(f"{V1}/tracking/view-log", headers=admin, params={"limit": 100})).json()["data"]
    mine = [(x["what"], (x["subject"] or {}).get("id")) for x in log if x["viewer"]["id"] == shop.ids["district_manager"]]
    assert ("team", None) in mine and ("visits", shop.ids["field_officer"]) in mine
    assert not [x for x in log if x["viewer"]["id"] == shop.ids["field_officer"]], "one's own visits are not logged"
