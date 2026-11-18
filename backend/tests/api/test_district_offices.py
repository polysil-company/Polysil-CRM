"""FS-085 against Postgres: `apply` on synthetic states, the area rule in its three
readers, and the RLS reach of an area office, a district office and a region,
including the negative cases.

Each test builds its world inside one transaction as the owner, switches to the app
role as an administrator through `act_as` (the helper `get_db` uses), runs the
service, and rolls everything back. Nothing is left behind on the shared database.
"""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.config import get_settings
from api.db.session import act_as
from api.deps import caller_for
from api.domain import district_offices as do
from api.errors import ValidationFailed
from api.schemas.masters import OrgUnitCreate, OrgUnitPatch
from api.services import district_offices as service
from api.services import masters, setup_check, teams, users

Sessions = Callable[[], AsyncSession]
ROOT = get_settings().root_org_unit_id or ""
pytestmark = pytest.mark.db


@dataclass
class World:
    s: AsyncSession
    tag: str
    states: list[str] = field(default_factory=list)          # codes
    state_ids: dict[str, str] = field(default_factory=dict)
    districts: dict[tuple[str, str], str] = field(default_factory=dict)   # (code, name) -> id
    people: dict[str, str] = field(default_factory=dict)      # label -> user id
    admin: str = ""

    async def q(self, sql: str, **p: object) -> object:
        result = await self.s.execute(text(sql), p)
        return result.scalar() if result.returns_rows else None

    async def state(self, *names: str, lgd: dict[str, str] | None = None) -> str:
        code = "Q" + uuid.uuid4().hex[:4].upper()
        while await self.q("SELECT 1 FROM territory WHERE level = 'state' AND code = :c", c=code):
            code = "Q" + uuid.uuid4().hex[:4].upper()
        sid = str(await self.q("INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id",
                               n=f"fs085_{code}_{self.tag}", c=code))
        self.states.append(code)
        self.state_ids[code] = sid
        for n in names:
            self.districts[(code, n)] = str(await self.q(
                "INSERT INTO territory (level, name, parent_id, lgd_code) VALUES ('district', :n, CAST(:p AS uuid), :l) RETURNING id",
                n=n, p=sid, l=(lgd or {}).get(n)))
        return code

    async def person(self, label: str, role: str, office: str | None = None) -> str:
        uid = str(await self.q(
            "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
            "SELECT 'staff', :e, :n, r.id, CAST(:o AS uuid) FROM role r WHERE r.code = :c RETURNING id",
            e=f"fs085_{label}_{self.tag}@polysil.in", n=f"AAAA fs085 {label} {self.tag}", c=role,
            o=office or ROOT))
        self.people[label] = uid
        return uid

    async def lead(self, territory: str, office: str, owner: str | None) -> str:
        return str(await self.q(
            "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, mobile, "
            "territory_id, owner_org_unit_id, owner_user_id) VALUES (:no, 'commercial', "
            "(SELECT id FROM mis_system LIMIT 1), (SELECT id FROM lead_source LIMIT 1), 'Farmer', '+919000000001', "
            "CAST(:t AS uuid), CAST(:o AS uuid), CAST(:u AS uuid)) RETURNING id",
            no=f"FS085-{self.tag}-{uuid.uuid4().hex[:6]}", t=territory, o=office, u=owner))

    async def partner(self, territory: str) -> str:
        return str(await self.q(
            "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
            "VALUES ('dealer', :c, 'FS085 Dealer', CAST(:t AS uuid), 'dealer') RETURNING id",
            c=f"F85-{uuid.uuid4().hex[:8]}", t=territory))

    async def as_(self, label: str) -> Caller:
        uid = self.admin if label == "admin" else self.people[label]
        await act_as(self.s, uid, get_settings().db_app_role)
        return await caller_for(self.s, uid)

    def plan(self, groups: list[do.Group] | None = None, decisions: list[service.Decision] | None = None,
             extra: dict[str, list[str]] | None = None, all_districts: bool = False) -> service.Plan:
        listed = {st: [do.ListedDistrict(n) for (c, n) in self.districts if c == st] + [
            do.ListedDistrict(n) for n in (extra or {}).get(st, [])] for st in self.states}
        return service.Plan(tuple(self.states), listed, groups or [], decisions or [], all_districts)

    def move(self, label: str, role: str, office: str, current: str | None = None) -> service.Decision:
        return service.Decision(self.people[label], label, role, current or ROOT, office)

    async def office_of(self, label: str) -> str:
        return str(await self.q("SELECT o.name FROM app_user u JOIN org_unit o ON o.id = u.org_unit_id "
                                "WHERE u.id = CAST(:u AS uuid)", u=self.people[label]))

    async def office(self, name: str) -> tuple[str, str | None, str | None] | None:
        r = (await self.s.execute(text(
            "SELECT o.id, p.name AS parent, o.territory_id FROM org_unit o LEFT JOIN org_unit p ON p.id = o.parent_id "
            "WHERE o.name = :n AND o.deleted_at IS NULL"), {"n": name})).one_or_none()
        return (str(r.id), r.parent, str(r.territory_id) if r.territory_id else None) if r else None


@pytest.fixture
async def world(sessions: Sessions):  # type: ignore[no-untyped-def]
    s = sessions()
    tx = await s.begin()
    w = World(s, uuid.uuid4().hex[:6])
    w.admin = str(await w.q(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "SELECT 'staff', :e, 'FS085 Admin', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'admin_sales' RETURNING id",
        e=f"fs085_admin_{w.tag}@polysil.in", o=ROOT))
    try:
        yield w
    finally:
        await tx.rollback()
        await s.close()


def area(code: str, *members: str, name: str | None = None) -> do.Group:
    return do.Group("area", name or do.area_name(code, members), code, members, "x")


def made(report: service.Report) -> dict[str, int]:
    return {k: v for k, v in report.counts.items() if k != "people already in place"}


# ── districts (rules 1 to 3) ─────────────────────────────────────────────────

async def test_districts_only_adds_the_missing_ones_with_their_code_and_reruns_clean(world: World) -> None:
    st = await world.state("Kutch", "Rajkot")
    plan = world.plan()
    plan.listed[st] = [do.ListedDistrict("Kachchh", "449"), do.ListedDistrict("Rajkot", "457"),
                       do.ListedDistrict("Morbi", "673")]
    # GJ's aliases apply to GJ only: borrow them for this synthetic state
    do.ALIASES[st] = do.ALIASES["GJ"]
    try:
        caller = await world.as_("admin")
        first = await service.apply(world.s, caller, plan)
        assert made(first) == {"districts created": 1, "state offices created": 1}, first.counts
        assert await world.q("SELECT lgd_code FROM territory WHERE name = 'Morbi' AND parent_id = CAST(:p AS uuid)",
                             p=world.state_ids[st]) == "673"
        assert await world.q("SELECT count(*) FROM territory WHERE parent_id = CAST(:p AS uuid)",
                             p=world.state_ids[st]) == 3, "Kutch was matched, not duplicated"
        assert any("by alias" in line for line in first.lines), first.lines
        assert made(await service.apply(world.s, caller, plan)) == {}, "rule 9"
        # no sheet: a state office, and no district office at all (rule 5)
        assert await world.q("SELECT count(*) FROM org_unit WHERE territory_id IN "
                             "(SELECT id FROM territory WHERE parent_id = CAST(:p AS uuid))",
                             p=world.state_ids[st]) == 0
    finally:
        do.ALIASES.pop(st, None)


async def test_a_matching_problem_stops_the_run_before_any_write(world: World) -> None:
    st = await world.state("Surendranagar", "Surendranagara")
    plan = world.plan()
    plan.listed[st] = [do.ListedDistrict("Surendranagr")]
    caller = await world.as_("admin")
    with pytest.raises(service.PlanError, match="add an alias"):
        await service.apply(world.s, caller, plan)
    assert await world.q("SELECT count(*) FROM org_unit WHERE territory_id = CAST(:t AS uuid)",
                         t=world.state_ids[st]) == 0


# ── the whole placement ──────────────────────────────────────────────────────

async def test_a_placement_builds_the_tree_moves_people_and_their_leads(world: World) -> None:
    st = await world.state("Alpha", "Beta", "Gamma")
    alpha, gamma = world.districts[(st, "Alpha")], world.districts[(st, "Gamma")]
    await world.person("dm", "district_manager")
    await world.person("fo", "field_officer")
    fo_lead = await world.lead(gamma, ROOT, world.people["fo"])
    dm_lead = await world.lead(alpha, ROOT, world.people["dm"])
    loose = await world.lead(alpha, ROOT, None)
    g = area(st, "Alpha", "Beta")
    plan = world.plan([g], [world.move("dm", "district_manager", g.name),
                            world.move("fo", "field_officer", do.district_office_name(st, "Gamma"))])
    caller = await world.as_("admin")
    report = await service.apply(world.s, caller, plan)

    assert made(report) == {"state offices created": 1, "area offices created": 1,
                            "district offices created": 3, "people moved": 2,
                            "unowned leads re-homed": 1}, report.counts
    state_office = do.state_office_name(st)
    assert (await world.office(state_office))[1] == "Polysil HQ"  # type: ignore[index]
    assert (await world.office(g.name))[1:] == (state_office, None)  # type: ignore[index]
    for d in ("Alpha", "Beta"):
        assert (await world.office(do.district_office_name(st, d)))[1] == g.name  # type: ignore[index]
    assert (await world.office(do.district_office_name(st, "Gamma")))[1] == state_office  # type: ignore[index]
    assert await world.office_of("dm") == g.name
    assert await world.office_of("fo") == do.district_office_name(st, "Gamma")

    async def lead_office(lead: str) -> str:
        return str(await world.q("SELECT o.name FROM lead l JOIN org_unit o ON o.id = l.owner_org_unit_id "
                                 "WHERE l.id = CAST(:l AS uuid)", l=lead))
    assert await lead_office(fo_lead) == do.district_office_name(st, "Gamma"), "084 into a district office"
    assert await lead_office(dm_lead) == "Polysil HQ", "rule 20: an area office has no own territory"
    assert any("1 open lead(s) stay" in line for line in report.lines), report.lines
    assert await lead_office(loose) == do.district_office_name(st, "Alpha"), "rule 24"
    assert await world.q("SELECT count(*) FROM activity_event WHERE entity_id = CAST(:l AS uuid) "
                         "AND kind = 'lead.rehomed' AND actor_id = CAST(:a AS uuid)", l=loose, a=world.admin) == 1
    assert await world.q("SELECT count(*) FROM activity_event WHERE kind = 'org_unit.created' "
                         "AND actor_id = CAST(:a AS uuid)", a=world.admin) == 5, "one event per office"

    # rule 9: the identical workbook again writes nothing. Its current_office_id is
    # now stale, but the person already sits where it puts them (code review F-2)
    again = await service.apply(world.s, caller, plan)
    assert made(again) == {} and again.counts["people already in place"] == 2, again.counts


async def test_an_admins_rename_and_rearrangement_survive_a_rerun(world: World) -> None:
    """EC-1: the loader moves an office only out of its default position."""
    st = await world.state("Alpha", "Beta")
    g = area(st, "Alpha", "Beta")
    caller = await world.as_("admin")
    await service.apply(world.s, caller, world.plan([g]))
    area_id = (await world.office(g.name))[0]  # type: ignore[index]
    await masters.patch_org_unit(world.s, caller, area_id, OrgUnitPatch.model_validate({"name": "North, renamed"}))
    other = await masters.create_org_unit(world.s, caller, OrgUnitCreate.model_validate(
        {"name": "Elsewhere", "role_level": 2,
         "parent_id": (await world.office(do.state_office_name(st)))[0]}))  # type: ignore[index]
    beta = (await world.office(do.district_office_name(st, "Beta")))[0]  # type: ignore[index]
    await masters.patch_org_unit(world.s, caller, beta, OrgUnitPatch.model_validate({"parent_id": other.id}))
    again = await service.apply(world.s, caller, world.plan([g]))
    assert made(again) == {}, again.counts
    assert await world.office(g.name) is None, "no second area under the old name"
    assert (await world.office(do.district_office_name(st, "Beta")))[1] == "Elsewhere"  # type: ignore[index]
    assert (await world.office(do.district_office_name(st, "Alpha")))[1] == "North, renamed"  # type: ignore[index]


async def test_a_district_office_closed_or_taken_out_of_an_area_stays_so(world: World) -> None:
    """EC-1 and rule 8, code review F-3: once the area exists the admin owns it. A
    district office closed inside it is not re-created, and one put back directly
    under the state office is not pulled back into the area."""
    st = await world.state("Alpha", "Beta", "Gamma")
    g = area(st, "Alpha", "Beta", "Gamma")
    caller = await world.as_("admin")
    await service.apply(world.s, caller, world.plan([g]))
    so = (await world.office(do.state_office_name(st)))[0]  # type: ignore[index]
    await masters.close_org_unit(world.s, caller, (await world.office(do.district_office_name(st, "Beta")))[0])  # type: ignore[index]
    gamma = (await world.office(do.district_office_name(st, "Gamma")))[0]  # type: ignore[index]
    await masters.patch_org_unit(world.s, caller, gamma, OrgUnitPatch.model_validate({"parent_id": so}))
    again = await service.apply(world.s, caller, world.plan([g]))
    assert made(again) == {}, again.counts
    assert await world.office(do.district_office_name(st, "Beta")) is None, "the closed office stays closed"
    assert (await world.office(do.district_office_name(st, "Gamma")))[1] == do.state_office_name(st)  # type: ignore[index]


async def test_a_region_takes_its_states_and_only_from_under_hq(world: World) -> None:
    a, b = await world.state("A1"), await world.state("B1")
    region = do.Group("region", do.region_name([a, b]), "", (a, b), "x")
    caller = await world.as_("admin")
    report = await service.apply(world.s, caller, world.plan([region]))
    assert report.counts["regional offices created"] == 1
    assert report.counts["state offices moved into a region"] == 2
    for st in (a, b):
        assert (await world.office(do.state_office_name(st)))[1] == region.name  # type: ignore[index]
    assert made(await service.apply(world.s, caller, world.plan([region]))) == {}


@pytest.mark.parametrize("case", ["fo_to_area", "stale", "role", "two_areas", "actor", "two_offices"])
async def test_refusals_write_nothing(world: World, case: str) -> None:
    st = await world.state("Alpha", "Beta")
    await world.person("fo", "field_officer")
    g = area(st, "Alpha", "Beta")
    groups, decisions = [g], []
    if case == "fo_to_area":
        decisions = [world.move("fo", "field_officer", g.name)]
    elif case == "stale":
        decisions = [world.move("fo", "field_officer", do.district_office_name(st, "Alpha"),
                                current=str(uuid.uuid4()))]
    elif case == "role":
        decisions = [world.move("fo", "district_manager", do.district_office_name(st, "Alpha"))]
    elif case == "two_areas":
        groups = [g, area(st, "Beta", name="Second Area")]
    elif case == "actor":
        decisions = [service.Decision(world.admin, "admin", "admin_sales", ROOT, do.HQ_NAME)]
    else:
        await world.q("INSERT INTO org_unit (name, role_level, territory_id) VALUES "
                      "('dup a', 2, CAST(:t AS uuid)), ('dup b', 2, CAST(:t AS uuid))",
                      t=world.districts[(st, "Alpha")])
    caller = await world.as_("admin")
    before = await world.q("SELECT count(*) FROM org_unit")
    with pytest.raises(service.PlanError) as err:
        await service.apply(world.s, caller, world.plan(groups, decisions))
    assert await world.q("SELECT count(*) FROM org_unit") == before, "nothing written"
    expected = {"fo_to_area": "Field Officer needs", "stale": "has moved since", "role": "the sheet says",
                "two_areas": "two areas", "actor": "cannot move themselves", "two_offices": "open offices"}
    assert any(expected[case] in p for p in err.value.problems), err.value.problems


async def test_a_database_error_in_one_move_refuses_only_that_one(world: World) -> None:
    """S-1, code review F-1: a database error (here 23505 from a trigger) aborts the
    transaction unless each move has its own savepoint. With it, exactly one refusal
    names the first person, and the caller's rollback leaves nothing behind. Without
    the savepoint the second move also reports 'current transaction is aborted', and
    this test fails."""
    st = await world.state("Alpha")
    await world.person("dm1", "district_manager")
    await world.person("dm2", "district_manager")
    fn = f"fs085_fail_{world.tag}"
    await world.q(f"""CREATE FUNCTION {fn}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'test duplicate'; END $$""")
    await world.q(f"""CREATE TRIGGER {fn} BEFORE UPDATE ON app_user FOR EACH ROW
        WHEN (OLD.id = '{world.people["dm1"]}'::uuid) EXECUTE FUNCTION {fn}()""")
    offices_before = await world.q("SELECT count(*) FROM org_unit")
    caller = await world.as_("admin")
    plan = world.plan([], [world.move("dm1", "district_manager", do.district_office_name(st, "Alpha")),
                           world.move("dm2", "district_manager", do.district_office_name(st, "Alpha"))])
    await world.s.execute(text("SAVEPOINT caller"))
    with pytest.raises(service.PlanError) as err:
        await service.apply(world.s, caller, plan)
    assert len(err.value.problems) == 1, err.value.problems
    assert world.people["dm1"] in err.value.problems[0] and "test duplicate" in err.value.problems[0]
    await world.s.execute(text("ROLLBACK TO SAVEPOINT caller"))      # the loader rolls back on PlanError
    await world.q("SELECT set_config('role', 'none', true)")
    assert await world.q("SELECT count(*) FROM org_unit") == offices_before, "rolled back"
    assert await world.office_of("dm2") == do.HQ_NAME, "the valid move is undone with the rest"


async def test_every_refusal_from_the_service_is_listed(world: World) -> None:
    """S-1: two DMs sent to HQ both fail the guard inside patch_user; both are listed."""
    st = await world.state("Alpha")
    for label in ("dm1", "dm2"):
        await world.person(label, "district_manager",
                           office=None)
    caller = await world.as_("admin")
    plan = world.plan([], [world.move("dm1", "district_manager", do.HQ_NAME),
                           world.move("dm2", "district_manager", do.HQ_NAME)])
    # both already at HQ would be skipped; start them at the state office instead
    await service.apply(world.s, caller, world.plan())
    so = (await world.office(do.state_office_name(st)))[0]  # type: ignore[index]
    await world.q("SELECT set_config('role', 'none', true)")   # back to the owner for the setup
    await world.q("UPDATE app_user SET org_unit_id = CAST(:o AS uuid) WHERE id = ANY(CAST(:ids AS uuid[]))",
                  o=so, ids=[world.people["dm1"], world.people["dm2"]])
    caller = await world.as_("admin")
    plan.decisions = [service.Decision(d.user_id, d.full_name, d.role_code, so, d.office_name) for d in plan.decisions]
    with pytest.raises(service.PlanError) as err:
        await service.apply(world.s, caller, plan)
    assert len(err.value.problems) == 2 and all("covers none" in p for p in err.value.problems), err.value.problems


async def test_no_084_trigger_refuses_a_sheet(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    await world.state("Alpha")
    await world.person("fo", "field_officer")
    monkeypatch.setattr(service, "LEAD_TRIGGER", "trg_does_not_exist")
    caller = await world.as_("admin")
    with pytest.raises(service.PlanError, match="084"):
        await service.apply(world.s, caller, world.plan([], [world.move("fo", "field_officer", do.HQ_NAME)]))


async def test_the_actor_must_be_an_administrator(world: World) -> None:
    await world.person("fo", "field_officer")
    with pytest.raises(service.PlanError, match=r"masters.edit"):
        await service.check_actor(world.s, await world.as_("fo"))


# ── rule 10 in its three readers ─────────────────────────────────────────────

@pytest.mark.parametrize("role,where,placed", [
    ("district_manager", "district", True), ("district_manager", "area", True),
    ("district_manager", "hq", False), ("district_manager", "region", False),
    ("district_manager", "over_state", False),
    # excluded only by role_level <= 2: no state-level territory below it (code review F-7)
    ("district_manager", "level3_over_district", False),
    ("field_officer", "district", True), ("field_officer", "area", False),
    ("field_officer", "hq", False),
])
async def test_the_guard_the_setup_check_and_the_team_filter_agree(
        world: World, role: str, where: str, placed: bool) -> None:
    st = await world.state("Alpha", "Beta")
    g = area(st, "Alpha")
    region = do.Group("region", do.region_name([st]), "", (st,), "x")
    caller = await world.as_("admin")
    await service.apply(world.s, caller, world.plan([g, region], all_districts=True))
    over_state = await masters.create_org_unit(world.s, caller, OrgUnitCreate.model_validate(
        {"name": f"over {world.tag}", "role_level": 2, "parent_id": ROOT}))
    await masters.patch_org_unit(world.s, caller, (await world.office(region.name))[0],  # type: ignore[index]
                                 OrgUnitPatch.model_validate({"parent_id": over_state.id}))
    level3 = await masters.create_org_unit(world.s, caller, OrgUnitCreate.model_validate(
        {"name": f"level3 {world.tag}", "role_level": 3,
         "parent_id": (await world.office(do.state_office_name(st)))[0]}))  # type: ignore[index]
    await masters.patch_org_unit(world.s, caller, (await world.office(do.district_office_name(st, "Beta")))[0],  # type: ignore[index]
                                 OrgUnitPatch.model_validate({"parent_id": level3.id}))
    office = {"district": (await world.office(do.district_office_name(st, "Alpha")))[0],  # type: ignore[index]
              "area": (await world.office(g.name))[0], "hq": ROOT,  # type: ignore[index]
              "region": (await world.office(region.name))[0], "over_state": over_state.id,  # type: ignore[index]
              "level3_over_district": level3.id}[where]
    role_id = str(await world.q("SELECT id FROM role WHERE code = :c", c=role))
    try:
        await users._office_has_area(world.s, role_id, office, "org_unit_id")
        guard = True
    except ValidationFailed:
        guard = False
    assert guard is placed
    await world.q("SELECT set_config('role', 'none', true)")
    await world.person("x", role, office=office)
    report = await setup_check.setup_check(world.s, await world.as_("admin"))
    flagged = world.people["x"] in {i.id for c in report.checks if c.code == "staff_without_area" for i in c.items}
    assert flagged is not placed
    # the team filter: an office's own district, or the districts under an area office
    covered = world.districts[(st, "Beta" if where == "level3_over_district" else "Alpha")]
    found = await teams.roster(world.s, await world.as_("admin"), rows=None,
                               owners=[world.people["x"]], territories=[covered])
    assert bool(found) is placed


async def test_the_team_filter_finds_a_dm_in_an_area_office(world: World) -> None:
    st = await world.state("Alpha", "Beta", "Gamma")
    g = area(st, "Alpha", "Beta")
    await world.person("dm", "district_manager")
    caller = await world.as_("admin")
    await service.apply(world.s, caller, world.plan([g], [world.move("dm", "district_manager", g.name)]))
    found = await teams.roster(world.s, caller, rows=None, owners=[world.people["dm"]],
                               territories=[world.districts[(st, "Beta")]])
    assert [p.id for p in found] == [world.people["dm"]]
    away = await teams.roster(world.s, caller, rows=None, owners=[world.people["dm"]],
                              territories=[world.districts[(st, "Gamma")]])
    assert away == [], "Gamma is not under the area"


# ── RLS: what an area office, a district office and a region reach ───────────

async def _seen(w: World, label: str, ids: list[str]) -> set[str]:
    await w.as_(label)
    rows = (await w.s.execute(text("SELECT id::text FROM channel_partner WHERE id = ANY(CAST(:i AS uuid[]))"),
                              {"i": ids})).all()
    return {r[0] for r in rows}


@pytest.mark.rls
async def test_dealer_reach_of_area_district_and_region_offices(world: World) -> None:
    st = await world.state("Alpha", "Beta", "Gamma")
    other = await world.state("Delta")
    third = await world.state("Epsilon")
    p = {k: await world.partner(world.districts[key]) for k, key in
         (("alpha", (st, "Alpha")), ("beta", (st, "Beta")), ("gamma", (st, "Gamma")),
          ("delta", (other, "Delta")), ("epsilon", (third, "Epsilon")))}
    for label, role in (("dm", "district_manager"), ("fo", "field_officer"), ("rm", "regional_manager")):
        await world.person(label, role)
    g = area(st, "Alpha", "Beta")
    region = do.Group("region", do.region_name([st, other]), "", (st, other), "x")
    plan = world.plan([g, region], [world.move("dm", "district_manager", g.name),
                                    world.move("fo", "field_officer", do.district_office_name(st, "Gamma")),
                                    world.move("rm", "regional_manager", region.name)])
    plan.listed[other] = [do.ListedDistrict("Delta")]
    await service.apply(world.s, await world.as_("admin"), plan)
    ids = list(p.values())
    assert await _seen(world, "dm", ids) == {p["alpha"], p["beta"]}, "the area's districts, not Gamma"
    assert await _seen(world, "fo", ids) == {p["gamma"]}, "one district office, not the next"
    assert await _seen(world, "rm", ids) == {p["alpha"], p["beta"], p["gamma"], p["delta"]}, \
        "both states of the region (a state office covers its whole state), never a third"


async def test_a_region_on_the_state_territory_sits_beside_the_state_office(world: World) -> None:
    """Rule 4: the level-3 office is the state office; a region an admin gave the
    state's territory is not a second one. Two level-3 offices stop the run."""
    st = await world.state("Alpha")
    tid = world.state_ids[st]
    await world.q("INSERT INTO org_unit (name, role_level, parent_id, territory_id) VALUES "
                  "(:r, 4, CAST(:root AS uuid), CAST(:t AS uuid))", r=f"West {world.tag}", root=ROOT, t=tid)
    await world.q("INSERT INTO org_unit (name, role_level, parent_id, territory_id) VALUES "
                  "(:s, 3, CAST(:root AS uuid), CAST(:t AS uuid))", s=f"Own state {world.tag}", root=ROOT, t=tid)
    caller = await world.as_("admin")
    report = await service.apply(world.s, caller, world.plan([area(st, "Alpha")]))
    assert "state offices created" not in report.counts
    assert (await world.office(do.area_name(st, ["Alpha"])))[1] == f"Own state {world.tag}"  # type: ignore[index]
    await world.q("SELECT set_config('role', 'none', true)")
    await world.q("INSERT INTO org_unit (name, role_level, parent_id, territory_id) VALUES "
                  "(:s, 3, CAST(:root AS uuid), CAST(:t AS uuid))", s=f"Second {world.tag}", root=ROOT, t=tid)
    with pytest.raises(service.PlanError, match="could be the state office"):
        await service.apply(world.s, await world.as_("admin"), world.plan())
