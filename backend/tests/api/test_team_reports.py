"""FS-082 over the API: the team filters on the reports, the salesperson roster,
the office-area guard on the user form, and the setup check."""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.errors import ValidationFailed
from api.services import teams
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key
from tests.api.test_lead_extras import _lead

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]

R = f"{V1}/reports"


def _rows(r: httpx.Response) -> list[dict]:
    assert r.status_code == 200, r.text
    return list(r.json()["data"]["rows"])


def _by_user(rows: list[dict]) -> dict[str | None, dict]:
    return {row["user"]["id"]: row for row in rows}


# ── the roster (B) ───────────────────────────────────────────────────────────

@pytest.mark.db
async def test_an_idle_officer_is_listed_with_zeros_for_their_manager(client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-2 / rule 3: the District Manager sees their Field Officer though the officer
    did nothing in the window, with role and office."""
    dm = await endpoints._as(client, shop, "district_manager")
    rows = _by_user(_rows(await client.get(f"{R}/salesperson-performance", headers=dm)))
    fo = rows[shop.ids["field_officer"]]
    assert fo["leads_created"] == 0 and fo["leads_won"] == 0, fo
    assert fo["role"]["code"] == "field_officer" and fo["office"]["id"] == shop.office, fo
    assert shop.ids["district_manager"] in rows
    # code review F-3: nobody above the DM gets a row of zeros the DM cannot see
    for above in ("state_manager", "regional_manager", "admin_sales", "md_ceo"):
        assert shop.ids[above] not in rows, above


@pytest.mark.db
async def test_a_field_officer_sees_only_their_own_row(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    rows = _rows(await client.get(f"{R}/salesperson-performance", headers=fo))
    assert [r["user"]["id"] for r in rows] == [shop.ids["field_officer"]]


@pytest.mark.db
async def test_the_area_filter_narrows_the_roster(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """EC-8: the officer's office covers the shop district; another state's district drops them."""
    s = sessions()
    elsewhere = str((await s.execute(text(
        "SELECT id FROM territory WHERE level = 'district' AND parent_id <> CAST(:st AS uuid) AND deleted_at IS NULL LIMIT 1"),
        {"st": shop.state})).scalar_one())
    await s.close()
    dm = await endpoints._as(client, shop, "district_manager")
    here = _by_user(_rows(await client.get(f"{R}/salesperson-performance", headers=dm, params={"territory_id": shop.state})))
    assert shop.ids["field_officer"] in here, "the state is above the officer's district"
    there = _by_user(_rows(await client.get(f"{R}/salesperson-performance", headers=dm, params={"territory_id": elsewhere})))
    assert shop.ids["field_officer"] not in there


@pytest.mark.db
async def test_owner_id_narrows_the_roster(client: httpx.AsyncClient, shop: Shop) -> None:
    """EC-3: one person asked for, one row back."""
    admin = await endpoints._as(client, shop, "admin_sales")
    rows = _rows(await client.get(f"{R}/salesperson-performance", headers=admin,
                                  params={"owner_id": shop.ids["field_officer"]}))
    assert [r["user"]["id"] for r in rows] == [shop.ids["field_officer"]]


@pytest.mark.db
async def test_roles_and_owner_id_narrow_together(client: httpx.AsyncClient, shop: Shop) -> None:
    """Code review F-2: a Field Officer is not a District Manager, so nothing."""
    fo = await endpoints._as(client, shop, "field_officer")
    await _lead(client, shop, fo)
    admin = await endpoints._as(client, shop, "admin_sales")
    params = {"owner_id": shop.ids["field_officer"], "roles": "district_manager"}
    for name in ("salesperson-performance", "lead-conversion"):
        assert _rows(await client.get(f"{R}/{name}", headers=admin, params=params)) == [], name
    params["roles"] = "field_officer"
    rows = _rows(await client.get(f"{R}/salesperson-performance", headers=admin, params=params))
    assert [r["user"]["id"] for r in rows] == [shop.ids["field_officer"]]


# ── the team filters (A) ─────────────────────────────────────────────────────

@pytest.mark.db
async def test_team_of_keeps_the_team_and_drops_everyone_else(client: httpx.AsyncClient, shop: Shop) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    await _lead(client, shop, fo)
    admin = await endpoints._as(client, shop, "admin_sales")
    params = {"group_by": "owner", "team_of": shop.ids["district_manager"]}
    r = await client.get(f"{R}/lead-conversion", headers=admin, params=params)
    owners = {row["key"]["id"] for row in _rows(r)}
    assert shop.ids["field_officer"] in owners
    assert owners <= {shop.ids["field_officer"], shop.ids["district_manager"]}, owners
    assert r.json()["data"]["filters"]["team_of"] == shop.ids["district_manager"]
    rows = _by_user(_rows(await client.get(f"{R}/salesperson-performance", headers=admin,
                                           params={"team_of": shop.ids["district_manager"]})))
    assert set(rows) == {shop.ids["field_officer"], shop.ids["district_manager"]}
    assert rows[shop.ids["field_officer"]]["leads_created"] >= 1


@pytest.mark.db
async def test_roles_narrow_to_one_designation(client: httpx.AsyncClient, shop: Shop) -> None:
    admin = await endpoints._as(client, shop, "admin_sales")
    r = await client.get(f"{R}/salesperson-performance", headers=admin,
                         params={"team_of": shop.ids["state_manager"], "roles": "field_officer"})
    rows = _rows(r)
    assert [row["user"]["id"] for row in rows] == [shop.ids["field_officer"]]
    assert r.json()["data"]["filters"]["roles"] == ["field_officer"]


@pytest.mark.db
async def test_an_empty_team_is_an_empty_report_not_everyone(client: httpx.AsyncClient, shop: Shop) -> None:
    """S-1: no field officer is a district manager, so nothing matches."""
    fo = await endpoints._as(client, shop, "field_officer")
    await _lead(client, shop, fo)
    admin = await endpoints._as(client, shop, "admin_sales")
    params = {"team_of": shop.ids["field_officer"], "roles": "district_manager"}
    for name in ("salesperson-performance", "lead-conversion", "follow-ups", "lost-leads", "territory-performance",
                 "campaign-performance"):
        r = await client.get(f"{R}/{name}", headers=admin, params=params)
        assert _rows(r) == [], name
        assert r.json()["data"]["filters"]["team_of"] == shop.ids["field_officer"], name
    r = await client.get(f"{R}/sales-forecast", headers=admin, params=params)
    assert r.status_code == 200 and r.json()["data"]["rows"] == [], r.text
    assert r.json()["data"]["filters"]["roles"] == ["district_manager"]


@pytest.mark.db
async def test_team_of_outside_your_line_is_404(client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    r = await client.get(f"{R}/salesperson-performance", headers=dm, params={"team_of": shop.ids["admin_sales"]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_in_your_line", r.text
    r = await client.get(f"{R}/salesperson-performance", headers=dm, params={"team_of": shop.ids["field_officer"]})
    assert r.status_code == 200


@pytest.mark.db
async def test_bad_team_filters_are_422(client: httpx.AsyncClient, shop: Shop) -> None:
    admin = await endpoints._as(client, shop, "admin_sales")
    for params, field in (({"team_of": shop.ids["field_officer"], "owner_id": shop.ids["field_officer"]}, "team_of"),
                          ({"roles": "no_such_role"}, "roles"), ({"roles": "dealer"}, "roles"),
                          ({"roles": ",".join(f"r{i}" for i in range(11))}, "roles")):
        r = await client.get(f"{R}/lead-conversion", headers=admin, params=params)
        assert r.status_code == 422 and field in r.json()["error"]["fields"], (params, r.text)


def test_complaints_take_no_team_filter() -> None:
    """EC-5: a complaint's owner is its handler, so the filter is not offered."""
    from api.main import app
    params = {p["name"] for p in app.openapi()["paths"][f"{R}/complaints"]["get"]["parameters"]}
    assert "team_of" not in params and "roles" not in params


@pytest.mark.db
async def test_the_export_carries_role_and_office(client: httpx.AsyncClient, shop: Shop) -> None:
    dm = await endpoints._as(client, shop, "district_manager")
    r = await client.get(f"{R}/salesperson-performance", headers=dm, params={"format": "csv"})
    assert r.status_code == 200, r.text
    text_ = r.content.decode("utf-8-sig")
    assert "Role" in text_ and "Office" in text_ and "Field Officer" in text_


async def test_a_partner_cannot_send_team_filters() -> None:
    """EC-12: refused before any database read."""
    caller = Caller(user_id=str(uuid.uuid4()), org_unit_id=None, partner_id=str(uuid.uuid4()),
                    scopes={"leads": "partner_subtree"}, user_type="partner_user")
    for kw in ({"team_of": str(uuid.uuid4()), "roles": None}, {"team_of": None, "roles": "field_officer"}):
        with pytest.raises(ValidationFailed):
            await teams.resolve(None, caller, owner_id=None, **kw)  # type: ignore[arg-type]


# ── the office-area guard (C) ────────────────────────────────────────────────

async def _bare_office(sessions: Sessions) -> str:
    s = sessions()
    oid = str((await s.execute(text(
        "INSERT INTO org_unit (name, role_level) VALUES (:n, 1) RETURNING id"),
        {"n": f"t082 bare {uuid.uuid4().hex[:8]}"})).scalar_one())
    await s.commit()
    await s.close()
    return oid


async def _drop(sessions: Sessions, *, users: list[str], offices: list[str]) -> None:
    s = sessions()
    for uid in users:
        for stmt in ("DELETE FROM idempotency_record WHERE user_id = CAST(:i AS uuid)",
                     "DELETE FROM activity_event WHERE entity_id = CAST(:i AS uuid) OR actor_id = CAST(:i AS uuid)",
                     "DELETE FROM user_territory WHERE user_id = CAST(:i AS uuid)",
                     "DELETE FROM app_user WHERE id = CAST(:i AS uuid)"):
            await s.execute(text(stmt), {"i": uid})
    for oid in offices:
        await s.execute(text("DELETE FROM org_unit WHERE id = CAST(:i AS uuid)"), {"i": oid})
    await s.commit()
    await s.close()


def _new(role: str, office: str) -> dict[str, object]:
    return {"user_type": "staff", "email": f"t082_{uuid.uuid4().hex[:8]}@polysil.in", "full_name": "Test Person",
            "role": role, "org_unit_id": office, "password": "a long enough password 82"}


@pytest.mark.db
async def test_field_staff_cannot_be_created_into_an_office_with_no_area(client: httpx.AsyncClient, shop: Shop,
                                                                         sessions: Sessions) -> None:
    bare = await _bare_office(sessions)
    made: list[str] = []
    try:
        admin = await endpoints._as(client, shop, "admin_sales")
        for role, name in (("field_officer", "Field Officer"), ("district_manager", "District Manager")):
            r = await client.post(f"{V1}/users", headers={**admin, **_key()}, json=_new(role, bare))
            assert r.status_code == 422 and r.json()["error"]["code"] == "office_has_no_area", r.text
            assert name in r.json()["error"]["message"] and "org_unit_id" in r.json()["error"]["fields"]
        for role, office in (("account_manager", bare), ("field_officer", shop.office)):
            r = await client.post(f"{V1}/users", headers={**admin, **_key()}, json=_new(role, office))
            assert r.status_code == 201, r.text
            made.append(r.json()["data"]["id"])
    finally:
        await _drop(sessions, users=made, offices=[bare])


@pytest.mark.db
async def test_a_misplaced_officer_can_be_corrected_and_moved(client: httpx.AsyncClient, shop: Shop,
                                                              sessions: Sessions) -> None:
    """S-4 / EC-7: the check runs on a change, so a name fix with the same role and
    office still saves; a role change at HQ is refused; the move out is allowed."""
    bare = await _bare_office(sessions)
    s = sessions()
    uid = str((await s.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, 'Misplaced', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'field_officer' RETURNING id"),
        {"e": f"t082_mis_{uuid.uuid4().hex[:8]}@polysil.in", "o": bare})).scalar_one())
    await s.commit()
    await s.close()
    try:
        admin = await endpoints._as(client, shop, "admin_sales")
        url = f"{V1}/users/{uid}"
        r = await client.patch(url, headers={**admin, **_key()},
                               json={"full_name": "Misplaced Fixed", "role": "field_officer", "org_unit_id": bare})
        assert r.status_code == 200, r.text
        r = await client.patch(url, headers={**admin, **_key()}, json={"role": "district_manager"})
        assert r.status_code == 422 and "role" in r.json()["error"]["fields"], r.text
        r = await client.patch(url, headers={**admin, **_key()},
                               json={"role": "district_manager", "org_unit_id": shop.office})
        assert r.status_code == 200, r.text
    finally:
        await _drop(sessions, users=[uid], offices=[bare])


# ── the setup check (D) ──────────────────────────────────────────────────────

@pytest.mark.db
async def test_the_setup_check_finds_a_misplaced_officer(client: httpx.AsyncClient, shop: Shop,
                                                        sessions: Sessions) -> None:
    bare = await _bare_office(sessions)
    s = sessions()
    uid = str((await s.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, 'AAA Misplaced 082', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'field_officer' RETURNING id"),
        {"e": f"t082_chk_{uuid.uuid4().hex[:8]}@polysil.in", "o": bare})).scalar_one())
    # a State Co-ordinator reads by area and holds none (code review F-4)
    sc = str((await s.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, 'AAA Coordinator 082', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'state_coordinator' RETURNING id"),
        {"e": f"t082_sc_{uuid.uuid4().hex[:8]}@polysil.in", "o": shop.office})).scalar_one())
    await s.commit()
    await s.close()
    try:
        admin = await endpoints._as(client, shop, "admin_sales")
        r = await client.get(f"{V1}/users/setup-check", headers=admin)
        assert r.status_code == 200, r.text
        checks = {c["code"]: c for c in r.json()["data"]["checks"]}
        assert list(checks) == ["staff_without_area", "staff_without_territories", "staff_skipping_a_level",
                                "unplaced_staff", "partners_without_area"]
        area = checks["staff_without_area"]
        assert area["count"] >= 1 and len(area["items"]) <= 100
        assert uid in {i["id"] for i in area["items"]}, "sorted by name, AAA comes first"
        # alone in a root office with no area: nobody above them
        skip = {i["id"]: i for i in checks["staff_skipping_a_level"]["items"]}
        assert uid in skip and skip[uid]["detail"].endswith("reports to nobody"), skip.get(uid)
        assert sc in {i["id"] for i in checks["staff_without_territories"]["items"]}
        assert r.json()["data"]["ok"] is False
        from api.config import get_settings
        principals = {get_settings().system_user_id, get_settings().intake_user_id}
        assert not principals & {i["id"] for i in checks["unplaced_staff"]["items"]}, "EC-10"
        dm = await endpoints._as(client, shop, "district_manager")
        r = await client.get(f"{V1}/users/setup-check", headers=dm)
        assert r.status_code == 403, r.text
    finally:
        await _drop(sessions, users=[uid, sc], offices=[bare])
