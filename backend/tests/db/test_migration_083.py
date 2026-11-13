"""083: reporting_lines() (FS-080). Who manages whom, and what each caller sees.

Every test builds its own office tree under a fresh root, with its own roles, in
the `db` fixture's transaction, and is rolled back. People elsewhere in the
database have no edges into a fresh root, so non-global callers see only this
tree; a global caller sees everyone, so its assertions filter by this tree's ids.
"""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import importlib.util
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role

VERSIONS = Path(__file__).resolve().parents[2] / "api" / "db" / "migrations" / "versions"
SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"
INTAKE_USER_ID = "3f962ae5-f0d3-5583-91b5-5cea037139fc"
SYSTEM_ORG_ID = "a1c3b0dd-6f0c-5f0e-8c1c-1b4f2f6a9e51"

pytestmark = [pytest.mark.db]


@dataclass
class World:
    tag: str
    offices: dict[str, str] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    people: dict[str, str] = field(default_factory=dict)

    def name(self, pid: str) -> str:
        return next(k for k, v in self.people.items() if v == pid)


# role key -> (level, functional)
ROLES = {"fo": (1, False), "dm": (2, False), "sm": (3, False), "rm": (4, False),
         "admin": (5, False), "md": (5, False), "acct": (5, True), "sc": (3, True),
         "support": (2, True)}

# office -> parent
OFFICES = {"hq": None, "region": "hq", "state": "region", "dist_a": "state", "field_a": "dist_a",
           "dist_b": "state", "dist_c": "state", "hq_child": "hq"}

# person key -> (role, office); names sort as listed within a role, except the two
# DMs in dist_a, whose ids are made to sort against their names (EC-3)
PEOPLE = [
    ("md", "md", "hq"), ("admin", "admin", "hq"), ("acct", "acct", "hq"),
    ("rm", "rm", "region"), ("sm", "sm", "state"), ("sc", "sc", "state"),
    ("dma1", "dm", "dist_a"), ("dma2", "dm", "dist_a"),
    ("fo1", "fo", "field_a"), ("fo2", "fo", "field_a"),
    ("dmb", "dm", "dist_b"), ("fob", "fo", "dist_b"),
    ("foc", "fo", "dist_c"), ("dmc_gone", "dm", "dist_c"),
    ("md_child", "md", "hq_child"), ("fo_child", "fo", "hq_child"),
    ("sm_in_b", "sm", "dist_b"),
    ("support", "support", "dist_a"),
]
NAMES = {"dma1": "Asha", "dma2": "Bharat"}


async def _world(db: AsyncSession) -> World:
    w = World(uuid.uuid4().hex[:8])
    for key, (level, functional) in ROLES.items():
        w.roles[key] = str((await db.execute(text(
            "INSERT INTO role (code, name, level, is_functional, is_portal) "
            "VALUES (:c, :n, :l, :f, false) RETURNING id"),
            {"c": f"t083_{key}_{w.tag}", "n": f"T {key}", "l": level, "f": functional})).scalar_one())
    for key, parent in OFFICES.items():
        w.offices[key] = str((await db.execute(text(
            "INSERT INTO org_unit (name, role_level, parent_id) VALUES (:n, 1, CAST(:p AS uuid)) RETURNING id"),
            {"n": f"t083 {key} {w.tag}", "p": w.offices[parent] if parent else None})).scalar_one())
    ids = sorted(str(uuid.uuid4()) for _ in PEOPLE)
    # Asha gets the larger id, Bharat the smaller: the order must follow the names
    order = {k: i for i, (k, _r, _o) in enumerate(PEOPLE)}
    pick = {k: ids[order[k]] for k, _r, _o in PEOPLE}
    pick["dma1"], pick["dma2"] = max(pick["dma1"], pick["dma2"]), min(pick["dma1"], pick["dma2"])
    for key, role, office in PEOPLE:
        w.people[key] = pick[key]
        await db.execute(text(
            "INSERT INTO app_user (id, user_type, email, full_name, role_id, org_unit_id) "
            "VALUES (CAST(:i AS uuid), 'staff', :e, :n, CAST(:r AS uuid), CAST(:o AS uuid))"),
            {"i": pick[key], "e": f"t083_{key}_{w.tag}@polysil.in", "n": NAMES.get(key, key),
             "r": w.roles[role], "o": w.offices[office]})
    # a district manager who left: inactive, so foc's line skips to the state manager
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = CAST(:i AS uuid)"),
                     {"i": w.people["dmc_gone"]})
    for module, scope in (("users", "global"),):
        for role in ("admin", "md"):
            await db.execute(text(
                "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
                "(CAST(:r AS uuid), :m, 'view', CAST(:s AS permission_scope))"),
                {"r": w.roles[role], "m": module, "s": scope})
    await db.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(CAST(:r AS uuid), 'users', 'view', 'org_subtree')"), {"r": w.roles["rm"]})
    return w


async def _lines(db: AsyncSession, who: str | None) -> dict[str, Any]:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": who or ""})
    await enter_role(db, "app_role")
    rows = (await db.execute(text("SELECT * FROM reporting_lines()"))).all()
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    return {str(r.id): r for r in rows}


def _managers(w: World, rows: dict[str, Any], key: str) -> list[str]:
    return [w.name(str(m)) for m in rows[w.people[key]].manager_ids]


async def test_managers_are_the_nearest_office_then_the_lowest_level_above(db: AsyncSession) -> None:
    w = await _world(db)
    rows = await _lines(db, w.people["admin"])
    assert _managers(w, rows, "fo1") == ["dma1", "dma2"], "two DMs in the parent office both manage, by name"
    assert _managers(w, rows, "dma1") == ["sm"]
    assert _managers(w, rows, "sm") == ["rm"]
    assert sorted(_managers(w, rows, "rm")) == ["admin", "md"], "rule 4: both at head office"
    assert _managers(w, rows, "md") == [] and _managers(w, rows, "admin") == []
    # rule 3 and EC: the inactive DM is skipped and never appears
    assert _managers(w, rows, "foc") == ["sm"]
    assert w.people["dmc_gone"] not in rows
    # rule 5: functional roles manage nobody; the level-5 one is a root (GAP-554)
    assert _managers(w, rows, "acct") == []
    assert _managers(w, rows, "sc") == ["rm"]
    assert _managers(w, rows, "support") == ["sm"], "a level-2 functional role in a district office skips its DMs (same level)"
    # EC-13: a State Manager anchored in a district office catches that district
    assert _managers(w, rows, "dmb") == ["sm_in_b"] and _managers(w, rows, "fob") == ["dmb"]
    # EC-14: an MD in a child office of HQ manages that office first
    assert _managers(w, rows, "fo_child") == ["md_child"]


async def test_a_field_officer_sees_the_chain_and_not_a_peer(db: AsyncSession) -> None:
    w = await _world(db)
    rows = await _lines(db, w.people["fo1"])
    got = {w.name(i): r.relation for i, r in rows.items()}
    assert got == {"fo1": "self", "dma1": "above", "dma2": "above", "sm": "above", "rm": "above",
                   "admin": "above", "md": "above"}
    assert "fo2" not in got, "EC-1: a peer in the same office is not below"


async def test_a_district_manager_sees_their_team_and_the_co_manager(db: AsyncSession) -> None:
    w = await _world(db)
    rows = await _lines(db, w.people["dma1"])
    got = {w.name(i): r.relation for i, r in rows.items()}
    assert got["fo1"] == "below" and got["fo2"] == "below"
    assert got["dma2"] == "co_manager", "EC-2: shares fo1 and fo2, so it must resolve"
    assert "dmb" not in got and "fob" not in got and "support" not in got


async def test_global_is_the_view_permission_at_global_scope_only(db: AsyncSession) -> None:
    w = await _world(db)
    mine = set(w.people.values())
    rm = await _lines(db, w.people["rm"])
    assert {r.relation for r in rm.values()} <= {"self", "above", "below"}, "EC-8: org scope gets no other rows"
    assert w.people["acct"] not in rm
    admin = await _lines(db, w.people["admin"])
    assert mine - {w.people["dmc_gone"]} <= set(admin)
    assert admin[w.people["acct"]].relation == "other"


async def test_the_system_office_is_unplaced_and_manages_nobody(db: AsyncSession) -> None:
    w = await _world(db)
    await db.execute(text("UPDATE app_user SET org_unit_id = CAST(:o AS uuid) WHERE id = CAST(:i AS uuid)"),
                     {"o": SYSTEM_ORG_ID, "i": w.people["md"]})
    rows = await _lines(db, w.people["admin"])
    assert rows[w.people["md"]].relation == "unplaced"
    assert _managers(w, rows, "rm") == ["admin"]
    # code review F-4: a non-global caller never gets unplaced rows...
    assert w.people["md"] not in await _lines(db, w.people["fo1"])
    # ...and an unplaced caller still gets their own row, which the default view needs
    own = await _lines(db, w.people["md"])
    assert own[w.people["md"]].relation == "unplaced" and own[w.people["md"]].manager_ids == []


async def test_service_accounts_and_deleted_people_are_never_rows(db: AsyncSession) -> None:
    """Rule 1 as rows, not only as callers (code review F-3): the two service accounts
    are active staff on the System office and would otherwise top the unplaced list."""
    w = await _world(db)
    await db.execute(text("UPDATE app_user SET deleted_at = now() WHERE id = CAST(:i AS uuid)"),
                     {"i": w.people["fo2"]})
    rows = await _lines(db, w.people["admin"])
    assert SYSTEM_USER_ID not in rows and INTAKE_USER_ID not in rows
    assert w.people["fo2"] not in rows
    assert _managers(w, rows, "fo1") == ["dma1", "dma2"]


async def test_a_locked_out_manager_still_manages(db: AsyncSession) -> None:
    """EC-16: a lockout is failed sign-ins, not a state of the person (code review F-2)."""
    w = await _world(db)
    email = f"t083_dma1_{w.tag}@polysil.in"
    await db.execute(text(
        "INSERT INTO login_attempt (identifier, succeeded, kind) "
        "SELECT CAST(:e AS citext), false, 'password' FROM generate_series(1, 20)"), {"e": email})
    rows = await _lines(db, w.people["fo1"])
    assert _managers(w, rows, "fo1") == ["dma1", "dma2"]
    assert rows[w.people["dma1"]].relation == "above"


async def test_three_thousand_staff_answer_quickly(db: AsyncSession) -> None:
    """EC-18 at the database (code review F-1): every call works out every person's
    managers, so a field officer's own chart pays for the whole company."""
    import time
    w = await _world(db)
    # 5 regions x 6 states x 10 districts, a DM and 9 field officers in each district
    await db.execute(text("""
        WITH r AS (
          INSERT INTO org_unit (name, role_level, parent_id)
          SELECT 't083 r' || g || ' ' || :t, 1, CAST(:hq AS uuid) FROM generate_series(1, 5) g RETURNING id),
        s AS (
          INSERT INTO org_unit (name, role_level, parent_id)
          SELECT 't083 s ' || g || ' ' || :t, 1, r.id FROM r, generate_series(1, 6) g RETURNING id),
        d AS (
          INSERT INTO org_unit (name, role_level, parent_id)
          SELECT 't083 d ' || g || ' ' || :t, 1, s.id FROM s, generate_series(1, 10) g RETURNING id),
        dm AS (
          INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id)
          SELECT 'staff', 't083_bulk_dm_' || d.id || '@polysil.in', 'DM', CAST(:dm AS uuid), d.id FROM d RETURNING 1)
        INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id)
        SELECT 'staff', 't083_bulk_fo_' || d.id || '_' || g || '@polysil.in', 'FO ' || g, CAST(:fo AS uuid), d.id
          FROM d, generate_series(1, 9) g"""),
        {"t": w.tag, "hq": w.offices["hq"], "dm": w.roles["dm"], "fo": w.roles["fo"]})
    # CI's fresh database has no statistics on these rows yet, and its planner chose
    # nested loops: 4 s and 6 s there, under 1 s here. Forbid hash and merge joins so
    # the function must be fast on the worst plan, not only the lucky one.
    await db.execute(text("SET LOCAL enable_hashjoin = off"))
    await db.execute(text("SET LOCAL enable_mergejoin = off"))
    # and no Material node over a nested loop's inner side: CI's second run (no
    # statistics) re-ran the admin's per-office managers once per person, 26 s
    await db.execute(text("SET LOCAL enable_material = off"))
    # a non-global Regional Manager over one bulk region: the biggest walk below
    rm_bulk = str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, 'RM bulk', CAST(:r AS uuid), o.id FROM org_unit o "
        "WHERE o.name = 't083 r1 ' || :t RETURNING id"),
        {"e": f"t083_rm_bulk_{w.tag}@polysil.in", "r": w.roles["rm"], "t": w.tag})).scalar_one())
    w.people["rm_bulk"] = rm_bulk
    timings = {}
    for who in ("fo1", "admin", "rm_bulk"):
        start = time.perf_counter()
        rows = await _lines(db, w.people[who])
        timings[who] = time.perf_counter() - start
        assert rows
    assert sum(r.relation == "below" for r in rows.values()) == 6 * 10 * 10, "the RM's region: 60 districts of 10"
    # the worst plan, forced; was 3.5 s, 6 s and more before the per-office slots
    assert timings["fo1"] < 1.5 and timings["admin"] < 2.0 and timings["rm_bulk"] < 2.5, timings


@pytest.mark.parametrize("who", ["none", "inactive", "deleted", "system", "intake"])
async def test_no_rows_for_anyone_but_an_active_staff_person(db: AsyncSession, who: str) -> None:
    w = await _world(db)
    caller: str | None = {"none": None, "system": SYSTEM_USER_ID, "intake": INTAKE_USER_ID}.get(who)
    if who in ("inactive", "deleted"):
        caller = w.people["admin"]
        column = "is_active = false" if who == "inactive" else "deleted_at = now()"
        await db.execute(text(f"UPDATE app_user SET {column} WHERE id = CAST(:i AS uuid)"), {"i": caller})
    assert await _lines(db, caller) == {}


async def test_no_rows_for_a_partner_user(db: AsyncSession) -> None:
    tag = uuid.uuid4().hex[:8]
    territory = (await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"), {"n": f"t083_{tag}"})).scalar_one()
    role = (await db.execute(text(
        "INSERT INTO role (code, name, level, is_portal) VALUES (:c, 'Dealer', 2, true) RETURNING id"),
        {"c": f"t083_dl_{tag}"})).scalar_one()
    partner = (await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'T083 Dealer', :t, 'dealer') RETURNING id"),
        {"c": f"T083-{tag}", "t": territory})).scalar_one()
    user = (await db.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "VALUES ('partner_user', :m, 'Bhavesh Shah', :r, :p) RETURNING id"),
        {"m": "9197" + f"{uuid.uuid4().int % 10**8:08d}", "r": role, "p": partner})).scalar_one()
    assert await _lines(db, str(user)) == {}


async def test_no_rows_for_a_consumer(db: AsyncSession) -> None:
    uid = (await db.execute(text(
        "SELECT id FROM app_user WHERE user_type = 'consumer' AND is_active AND deleted_at IS NULL "
        "LIMIT 1"))).scalar_one_or_none()
    if uid is None:
        # the same `user_type = 'staff'` test refuses a consumer as a partner user
        pytest.skip("no active consumer in this database")
    assert await _lines(db, str(uid)) == {}


async def test_execute_is_not_granted_to_public(db: AsyncSession) -> None:
    acl = (await db.execute(text(
        "SELECT proacl::text FROM pg_proc WHERE proname = 'reporting_lines'"))).scalar_one()
    assert "app_role=X" in acl
    assert not any(entry.startswith("=") for entry in acl.strip("{}").split(","))


class _Op:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str) -> None:
        self.sql.append(sql)


async def test_the_migration_round_trips(db: AsyncSession) -> None:
    spec = importlib.util.spec_from_file_location("m083", VERSIONS / "083_reporting_lines.py")
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    conn = await db.connection()
    for step in ("downgrade", "upgrade"):
        op = _Op()
        m.op = op
        getattr(m, step)()
        for sql in op.sql:
            await conn.exec_driver_sql(sql)
        exists = (await db.execute(text("SELECT count(*) FROM pg_proc WHERE proname = 'reporting_lines'"))).scalar_one()
        assert exists == (1 if step == "upgrade" else 0)
