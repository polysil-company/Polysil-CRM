"""FS-080 over the API: GET /users/org-chart. The manager rule and the zero-row
callers are pinned in tests/db/test_migration_083.py; this covers the endpoint:
defaults, the company view, re-rooting, 404 against 403, and the shape."""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import PASSWORD, V1, _login
from tests.conftest import Dealer

pytestmark = pytest.mark.db

URL = f"{V1}/users/org-chart"
ROLES = {"md": (5, False, "global"), "sm": (3, False, "org_subtree"), "dm": (2, False, "org_subtree"),
         "fo": (1, False, None), "acct": (5, True, None)}
OFFICES = {"hq": None, "state": "hq", "dist": "state"}
PEOPLE = [("md", "md", "hq", "Meera"), ("acct", "acct", "hq", "Anil"), ("sm", "sm", "state", "Suresh"),
          ("dm1", "dm", "dist", "Asha"), ("dm2", "dm", "dist", "Bharat"),
          ("fo1", "fo", "dist", "Ravi"), ("fo2", "fo", "dist", "Kiran"), ("gone", "fo", "dist", "Gone")]


@dataclass
class Org:
    ids: dict[str, str]
    emails: dict[str, str]
    offices: dict[str, str]


@pytest_asyncio.fixture
async def org(sessions: Callable[[], AsyncSession]) -> AsyncIterator[Org]:
    tag = uuid.uuid4().hex[:8]
    s = sessions()
    roles, offices, ids, emails = {}, {}, {}, {}
    for key, (level, functional, scope) in ROLES.items():
        roles[key] = str((await s.execute(text(
            "INSERT INTO role (code, name, level, is_functional, is_portal) VALUES (:c, :n, :l, :f, false) RETURNING id"),
            {"c": f"t080_{key}_{tag}", "n": f"T {key}", "l": level, "f": functional})).scalar_one())
        if scope:
            await s.execute(text(
                "INSERT INTO role_permission (role_id, module, action, scope) "
                "VALUES (CAST(:r AS uuid), 'users', 'view', CAST(:s AS permission_scope))"),
                {"r": roles[key], "s": scope})
    for key, parent in OFFICES.items():
        offices[key] = str((await s.execute(text(
            "INSERT INTO org_unit (name, role_level, parent_id) VALUES (:n, 1, CAST(:p AS uuid)) RETURNING id"),
            {"n": f"t080 {key} {tag}", "p": offices[parent] if parent else None})).scalar_one())
    hashed = PasswordHasher().hash(PASSWORD)
    for key, role, office, name in PEOPLE:
        emails[key] = f"t080_{key}_{tag}@polysil.in"
        ids[key] = str((await s.execute(text(
            "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id, is_active) "
            "VALUES ('staff', :e, :p, :n, CAST(:r AS uuid), CAST(:o AS uuid), :a) RETURNING id"),
            {"e": emails[key], "p": hashed, "n": name, "r": roles[role], "o": offices[office],
             "a": key != "gone"})).scalar_one())
    await s.commit()
    try:
        yield Org(ids, emails, offices)
    finally:
        c = sessions()
        for uid in ids.values():
            await c.execute(text("DELETE FROM activity_event WHERE entity_id = CAST(:i AS uuid) OR actor_id = CAST(:i AS uuid)"), {"i": uid})
            await c.execute(text("DELETE FROM app_user WHERE id = CAST(:i AS uuid)"), {"i": uid})
        for email in emails.values():
            await c.execute(text("DELETE FROM login_attempt WHERE identifier = CAST(:i AS citext)"), {"i": email})
        for rid in roles.values():
            await c.execute(text("DELETE FROM role_permission WHERE role_id = CAST(:r AS uuid)"), {"r": rid})
            await c.execute(text("DELETE FROM role WHERE id = CAST(:r AS uuid)"), {"r": rid})
        for key in reversed(list(OFFICES)):
            await c.execute(text("DELETE FROM org_unit WHERE id = CAST(:o AS uuid)"), {"o": offices[key]})
        await c.commit()


async def _get(client: httpx.AsyncClient, org: Org, who: str, **params: str) -> httpx.Response:
    h = await _login(client, org.emails[who], PASSWORD)
    return await client.get(URL, headers=h, params=params)


def _names(people: list[dict]) -> list[str]:
    return [p["full_name"] for p in people]


async def test_the_default_is_yourself_even_for_a_global_caller(client: httpx.AsyncClient, org: Org) -> None:
    r = await _get(client, org, "md")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["subject"]["id"] == org.ids["md"] and d["managers"] == []
    assert _names(d["people"]) == ["Suresh", "Asha", "Bharat", "Kiran", "Ravi"]
    assert d["totals"]["people"] == 5 and d["unplaced"] == []


async def test_a_district_manager_sees_the_chain_their_team_and_the_co_manager(client: httpx.AsyncClient, org: Org) -> None:
    r = await _get(client, org, "dm1")
    d = r.json()["data"]
    assert d["subject"] == {"id": org.ids["dm1"], "full_name": "Asha", "level": 2,
                            "role": d["subject"]["role"], "org_unit": {"id": org.offices["dist"], "name": d["subject"]["org_unit"]["name"]}}
    assert [[p["full_name"] for p in step] for step in d["managers"]] == [["Suresh"], ["Meera"]]
    assert _names(d["people"]) == ["Kiran", "Ravi"]
    ravi = d["people"][1]
    assert ravi["manager_ids"] == [org.ids["dm1"], org.ids["dm2"]], "sorted by name"
    assert (ravi["direct_reports"], ravi["team_size"]) == (0, 0)
    assert _names(d["co_managers"]) == ["Bharat"]
    assert d["totals"]["by_role"][0]["count"] == 2
    assert "email" not in d["subject"] and "mobile" not in ravi


async def test_a_field_officer_sees_managers_and_no_team(client: httpx.AsyncClient, org: Org) -> None:
    d = (await _get(client, org, "fo1")).json()["data"]
    assert [[p["full_name"] for p in step] for step in d["managers"]] == [["Asha", "Bharat"], ["Suresh"], ["Meera"]]
    assert d["people"] == [] and d["co_managers"] == [] and d["totals"] == {"people": 0, "by_role": []}


async def test_re_rooting_below_works_and_a_peer_or_a_leaver_is_404(client: httpx.AsyncClient, org: Org) -> None:
    r = await _get(client, org, "sm", user_id=org.ids["dm1"])
    assert r.status_code == 200 and r.json()["data"]["subject"]["full_name"] == "Asha"
    assert (await _get(client, org, "dm1", user_id=org.ids["dm2"])).status_code == 404, "a peer"
    assert (await _get(client, org, "dm1", user_id=org.ids["sm"])).status_code == 404, "above is not re-rootable"
    assert (await _get(client, org, "md", user_id=org.ids["gone"])).status_code == 404, "deactivated"
    assert (await _get(client, org, "md", user_id=str(uuid.uuid4()))).status_code == 404
    # global may open anyone, including someone outside their own line
    r = await _get(client, org, "md", user_id=org.ids["acct"])
    assert r.status_code == 200 and r.json()["data"]["managers"] == []


async def test_the_company_view_needs_global(client: httpx.AsyncClient, org: Org) -> None:
    r = await _get(client, org, "md", view="company")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["subject"] is None and d["managers"] == []
    mine = {p["id"]: p for p in d["people"] if p["id"] in org.ids.values()}
    assert mine[org.ids["md"]]["manager_ids"] == [] and mine[org.ids["acct"]]["manager_ids"] == []
    assert mine[org.ids["md"]]["team_size"] == 5
    assert d["totals"]["people"] == len(d["people"])
    refused = await _get(client, org, "sm", view="company")
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "insufficient_permission"


async def test_view_with_user_id_and_a_bad_view_are_422(client: httpx.AsyncClient, org: Org) -> None:
    assert (await _get(client, org, "md", view="company", user_id=org.ids["sm"])).status_code == 422
    assert (await _get(client, org, "md", view="everyone")).status_code == 422
    assert (await _get(client, org, "md", user_id="not-a-uuid")).status_code == 422


async def test_a_partner_user_is_refused(client: httpx.AsyncClient, dealer: Dealer,
                                         sessions: Callable[[], AsyncSession]) -> None:
    from tests.api.test_auth_endpoints import _otp_sign_in
    token = await _otp_sign_in(client, dealer, sessions)
    r = await client.get(URL, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "insufficient_permission"
