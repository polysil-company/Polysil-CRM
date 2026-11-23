"""FS-085: apply a placement plan through the services the admin screens use.

One call, one transaction, owned by the caller (`scripts/load_district_offices.py`):

1. **Check** everything that can be checked before a write: district matching
   (rule 2), duplicate offices (rules 4 and 5), the approved groups (rules 6 and 7)
   and every Decision (rule 18). Any problem raises `PlanError` with nothing
   written.
2. **Write** districts, state offices, regions, areas and the district offices
   someone needs, through `masters.create_territory`, `create_org_unit` and
   `patch_org_unit`, so each write carries its activity event.
3. **Move** each approved person through `users.patch_user`, one savepoint each,
   so one refusal does not hide the next (plan review S-1).
4. **Re-home** unowned open leads left at Polysil HQ (rule 24).
5. **Report** what a reader must know before committing (rules 20 to 22).

Any refusal in 3 raises `PlanError` after every person was tried; the caller
rolls back. Services never commit (CLAUDE.md 4.1 rule 3).
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.config import get_settings
from api.domain import district_offices as do
from api.errors import ApiError
from api.schemas.masters import OrgUnitCreate, OrgUnitPatch, TerritoryCreate
from api.schemas.users import UserPatch
from api.services import leads as leads_service
from api.services import masters, users

LEAD_TRIGGER = "trg_app_user_lead_office"     # 084
OPEN_LEAD = ("l.deleted_at IS NULL AND l.merged_into_id IS NULL "
             "AND l.stage::text NOT IN ('won', 'lost', 'merged')")


@dataclass(frozen=True)
class Decision:
    """One approved People row: move this person to the office named."""

    user_id: str
    full_name: str
    role_code: str
    current_office_id: str
    office_name: str


@dataclass
class Plan:
    states: tuple[str, ...]
    listed: dict[str, list[do.ListedDistrict]]
    groups: list[do.Group] = field(default_factory=list)       # approved only
    decisions: list[Decision] = field(default_factory=list)
    all_districts: bool = False


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)

    def note(self, line: str) -> None:
        self.lines.append(line)


class PlanError(Exception):
    """The plan cannot be applied as it stands. `problems` says why, every one."""

    def __init__(self, problems: list[str], report: Report | None = None) -> None:
        self.problems = problems
        self.report = report or Report()
        super().__init__("; ".join(problems))


@dataclass
class _District:
    state: str
    name: str                       # the database's spelling where one exists
    territory_id: str | None        # None until created
    lgd_code: str = ""


@dataclass
class _Office:
    id: str
    name: str
    parent_id: str | None
    territory_id: str | None
    role_level: int


def _why(exc: Exception) -> str:
    if isinstance(exc, ApiError):
        fields = f" {json.dumps(exc.fields, sort_keys=True)}" if exc.fields else ""
        return f"{exc.message}{fields}"
    if isinstance(exc, DBAPIError):
        orig = getattr(exc, "orig", None)
        return f"database refused: {str(orig or exc).splitlines()[0]}"
    return str(exc)


async def check_actor(db: AsyncSession, caller: Caller) -> None:
    """What `get_db` and the routers check for a request (plan review S-8): active
    staff, `masters.edit` and `users.edit`, and users at global scope."""
    row = (await db.execute(text(
        "SELECT user_type::text AS user_type, is_active, deleted_at FROM app_user "
        "WHERE id = CAST(:u AS uuid)"), {"u": caller.user_id})).one_or_none()
    problems = []
    if row is None or row.deleted_at is not None or not row.is_active or row.user_type != "staff":
        problems.append("the acting person must be an active staff member")
    for module in ("masters", "users"):
        if (module, "edit") not in caller.permissions:
            problems.append(f"the acting person needs {module}.edit")
    if caller.scopes.get("users") != "global":
        problems.append("the acting person needs users at global scope")
    if problems:
        raise PlanError(problems)


async def _offices(db: AsyncSession) -> list[_Office]:
    rows = (await db.execute(text(
        "SELECT id, name, parent_id, territory_id, role_level FROM org_unit "
        "WHERE deleted_at IS NULL"))).all()
    return [_Office(str(r.id), r.name, str(r.parent_id) if r.parent_id else None,
                    str(r.territory_id) if r.territory_id else None, int(r.role_level)) for r in rows]


async def apply(db: AsyncSession, caller: Caller, plan: Plan) -> Report:
    """Rules 1 to 24. Raises `PlanError`; the caller rolls back on it."""
    settings = get_settings()
    root = settings.root_org_unit_id
    if not root:
        raise PlanError(["no root office is configured (ROOT_ORG_UNIT_ID)"])
    service_accounts = {settings.system_user_id, settings.intake_user_id}
    report = Report()
    problems: list[str] = []
    await db.execute(text("SELECT set_config('lock_timeout', '5s', true)"))   # rule 18, EC-12

    if plan.decisions and not (await db.execute(text(
            "SELECT 1 FROM pg_trigger WHERE tgname = :t AND NOT tgisinternal"),
            {"t": LEAD_TRIGGER})).first():
        raise PlanError([f"this database has no {LEAD_TRIGGER} (migration 084): leads would "
                           "stay behind. Deploy first (rule 19)."])

    # ── 1. check ─────────────────────────────────────────────────────────────
    state_ids: dict[str, str | None] = {}
    districts: dict[str, list[_District]] = {}
    # state -> canonical spelling -> district; None where two districts share one
    lookup: dict[str, dict[str, _District | None]] = defaultdict(dict)

    def remember(st: str, spelling: str, d: _District) -> None:
        key = do.canonical(st, spelling)
        lookup[st][key] = d if lookup[st].get(key, d) is d else None
    for st in plan.states:
        states_found = (await db.execute(text(
            "SELECT id FROM territory WHERE level = 'state' AND deleted_at IS NULL "
            "AND (upper(code::text) = :c OR lower(name) = lower(:n))"),
            {"c": st, "n": do.STATE_NAMES.get(st, st)})).all()
        if len(states_found) > 1:
            problems.append(f"{st}: {len(states_found)} states match by code or name")
        state_ids[st] = str(states_found[0].id) if states_found else None
        held = [do.HeldDistrict(str(r.id), r.name, r.lgd_code) for r in (await db.execute(text(
            "SELECT id, name, lgd_code FROM territory WHERE level = 'district' "
            "AND deleted_at IS NULL AND parent_id = CAST(:p AS uuid)"),
            {"p": state_ids[st]})).all()] if state_ids[st] else []
        result = do.match_districts(st, plan.listed.get(st, []), held)
        problems.extend(result.problems)
        districts[st] = []
        for m in result.matches:
            d = _District(st, m.existing.name if m.existing else m.listed.name,
                          m.existing.id if m.existing else None, m.listed.lgd_code)
            districts[st].append(d)
            remember(st, d.name, d)
            remember(st, m.listed.name, d)
        for h in result.unlisted:
            kept = _District(st, h.name, h.id, h.lgd_code or "")
            districts[st].append(kept)
            remember(st, kept.name, kept)
        by_how = Counter(m.how for m in result.matches)
        report.note(f"{st}: districts {len(result.matches)} listed; "
                    + ", ".join(f"{n} by {how}" for how, n in sorted(by_how.items())))
        for m in result.matches:
            if m.how == "close":
                report.note(f"  {st} {m.listed.name!r} matched {m.existing.name!r} by spelling "
                            f"({m.score})" if m.existing else "")
            elif m.existing is None:
                report.note(f"  {st} {m.listed.name!r} is new; nearest {m.nearest!r} "
                            f"({m.nearest_score})")
        for h in result.unlisted:
            report.note(f"  {st} {h.name!r} is not on the list: left alone, no office (rule 3)")

    def find(st: str, name: str) -> _District | None:
        """A district by either spelling: the database's or the list's."""
        return lookup.get(st, {}).get(do.canonical(st, name))

    offices = await _offices(db)
    on_territory: dict[str, list[_Office]] = defaultdict(list)
    for o in offices:
        if o.territory_id:
            on_territory[o.territory_id].append(o)
    # rule 4: the state office is the level-3 office on the state's territory. Another
    # level there (a region an admin gave the state's territory) sits beside it. With
    # no level-3 office, a single office of another level serves (plan review S-7).
    chosen: dict[str, _Office] = {}
    for st, tid in state_ids.items():
        if not tid:
            continue
        on_state = on_territory[tid]
        level3 = [o for o in on_state if o.role_level == 3]
        pick = level3 if level3 else on_state
        if len(pick) > 1:
            problems.append(f"{st}: {len(pick)} open offices could be the state office "
                            f"({', '.join(o.name for o in pick)}); keep one")
        elif pick:
            chosen[st] = pick[0]

    # the groups (rules 6 and 7)
    area_of: dict[tuple[str, str], do.Group] = {}
    region_of: dict[str, do.Group] = {}
    for g in plan.groups:
        if g.kind == "area":
            if g.state not in plan.states:
                problems.append(f"area {g.name!r}: state {g.state!r} is not loaded")
                continue
            for member in g.members:
                md = find(g.state, member)
                if md is None:
                    problems.append(f"area {g.name!r}: no single district {member!r} in {g.state}")
                    continue
                key = (g.state, md.name)
                if key in area_of:
                    problems.append(f"{md.name} ({g.state}) is in two areas: "
                                    f"{area_of[key].name!r} and {g.name!r}")
                area_of[key] = g
        elif g.kind == "region":
            for st in g.members:
                if st not in plan.states:
                    problems.append(f"region {g.name!r}: state {st!r} is not loaded")
                elif st in region_of:
                    problems.append(f"{st} is in two regions: {region_of[st].name!r} and {g.name!r}")
                else:
                    region_of[st] = g
        else:
            problems.append(f"group {g.name!r}: kind must be area or region")

    # the decisions (rule 18)
    spellings: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for st in plan.states:
        for row in plan.listed.get(st, []):            # the list's own spelling too
            d2 = find(st, row.name)
            if d2 is not None:
                spellings[st].append((row.name, d2.name))
    names = do.catalogue(plan.states, {st: [d.name for d in districts[st]] for st in plan.states},
                         plan.groups, spellings)
    by_name: dict[str, list[_Office]] = defaultdict(list)
    for o in offices:
        by_name[o.name.casefold()].append(o)
    by_id = {o.id: o for o in offices}
    closed_on = {str(r[0]) for r in (await db.execute(text(
        "SELECT DISTINCT territory_id FROM org_unit WHERE deleted_at IS NOT NULL "
        "AND territory_id IS NOT NULL"))).all()}

    def existing_area(g: do.Group) -> bool:
        so = chosen.get(g.state)
        return so is not None and any(o.parent_id == so.id for o in by_name.get(g.name.casefold(), []))

    def already_there(live: _Office | None, target: do.Office | _Office) -> bool:
        """The person already sits in the office the Decision names (rule 9: a rerun
        of the same workbook is a no-op, not a stale-sheet refusal; code review F-2)."""
        if live is None:
            return False
        if isinstance(target, _Office):
            return live.id == target.id
        if target.kind == "hq":
            return live.id == root
        if target.kind == "state":
            return target.state in chosen and live.id == chosen[target.state].id
        if target.kind == "district":
            d = find(target.state, target.district)
            return d is not None and d.territory_id is not None and live.territory_id == d.territory_id
        return live.name.casefold() == target.name.casefold()

    targets: dict[str, do.Office | _Office] = {}
    in_place: set[str] = set()
    needed: set[tuple[str, str]] = set()
    movers = {r.user_id for r in plan.decisions}
    people = {str(r.id): r for r in (await db.execute(text(
        "SELECT u.id, lower(r.code::text) AS role_code, u.org_unit_id, u.is_active, u.deleted_at, "
        "u.user_type::text AS user_type FROM app_user u JOIN role r ON r.id = u.role_id "
        "WHERE u.id = ANY(CAST(:ids AS uuid[]))"), {"ids": sorted(movers)})).all()}
    for dec in plan.decisions:
        who = f"{dec.full_name} ({dec.user_id})"
        p = people.get(dec.user_id)
        if dec.user_id == caller.user_id:
            problems.append(f"{who}: the acting person cannot move themselves; use another admin")
            continue
        if p is None or p.deleted_at is not None or dec.user_id in service_accounts:
            problems.append(f"{who}: no such person")
            continue
        if not p.is_active or p.user_type != "staff":
            problems.append(f"{who}: not active staff")
            continue
        if p.role_code != dec.role_code.lower():
            problems.append(f"{who}: the sheet says {dec.role_code}, the database says {p.role_code}")
        target: do.Office | _Office | None = names.get(dec.office_name.casefold())
        if target is None:
            hits = by_name.get(dec.office_name.casefold(), [])
            if len(hits) != 1:
                problems.append(f"{who}: {'no' if not hits else 'more than one'} office named "
                                f"{dec.office_name!r}")
                continue
            target = hits[0]
        if already_there(by_id.get(str(p.org_unit_id)), target):
            in_place.add(dec.user_id)
            continue
        if str(p.org_unit_id) != dec.current_office_id:
            problems.append(f"{who}: has moved since the sheet was made; make a new sheet (EC-5)")
        if isinstance(target, do.Office):
            if target.kind == "district":
                needed.add((target.state, target.district))
            if p.role_code == do.FIELD_OFFICER and target.kind in ("hq", "area", "region"):
                problems.append(f"{who}: a Field Officer needs an office with its own area, "
                                f"not {target.name!r} (rule 10)")
        targets[dec.user_id] = target

    # an area's districts need offices only while the area is being made: once it
    # exists the admin owns it, and a district office they closed stays closed
    # (rules 6, 8 and 9; code review F-3)
    for key, g in area_of.items():
        nd = find(*key)
        if existing_area(g) or (nd is not None and nd.territory_id in closed_on
                                and not on_territory.get(nd.territory_id)):
            continue
        needed.add(key)
    if plan.all_districts:
        needed |= {(st, d.name) for st in plan.states for d in districts[st]}
    for st, name in sorted(needed):
        nd = find(st, name)
        if nd is not None and nd.territory_id and len(on_territory[nd.territory_id]) > 1:
            problems.append(f"{name} ({st}): {len(on_territory[nd.territory_id])} open offices on "
                            "this district; close or merge one first (ISS-240)")

    if problems:
        raise PlanError(problems, report)

    # ── 2. write ─────────────────────────────────────────────────────────────
    try:
        for st in plan.states:
            if state_ids[st] is None:
                t = await masters.create_territory(db, caller, TerritoryCreate.model_validate(
                    {"name": do.STATE_NAMES.get(st, st), "level": "state", "code": st}))
                state_ids[st] = t.id
                report.counts["states created"] += 1
            for d in districts[st]:
                if d.territory_id is None:
                    t = await masters.create_territory(db, caller, TerritoryCreate.model_validate(
                        {"name": d.name, "level": "district", "parent_id": state_ids[st],
                         "lgd_code": d.lgd_code or None}))
                    d.territory_id = t.id
                    report.counts["districts created"] += 1

        state_office: dict[str, _Office] = {}
        for st in plan.states:
            tid = state_ids[st]
            assert tid is not None
            if st in chosen:
                state_office[st] = chosen[st]
                continue
            made = await masters.create_org_unit(db, caller, OrgUnitCreate.model_validate(
                {"name": do.state_office_name(st), "role_level": 3, "parent_id": root,
                 "territory_id": tid}))
            state_office[st] = _Office(made.id, made.name, root, tid, 3)
            report.counts["state offices created"] += 1

        group_ids: dict[str, str] = {}
        for g in (g for g in plan.groups if g.kind == "region"):
            movable = [state_office[st] for st in g.members if state_office[st].parent_id == root]
            named = [o for o in by_name.get(g.name.casefold(), []) if o.parent_id == root]
            if named:
                group_ids[g.name.casefold()] = named[0].id
            elif movable:
                made = await masters.create_org_unit(db, caller, OrgUnitCreate.model_validate(
                    {"name": g.name, "role_level": 4, "parent_id": root}))
                group_ids[g.name.casefold()] = made.id
                report.counts["regional offices created"] += 1
            else:
                report.note(f"region {g.name!r}: its states are already placed elsewhere; left alone")
                continue
            for o in movable:
                await masters.patch_org_unit(db, caller, o.id, OrgUnitPatch.model_validate({"parent_id": group_ids[g.name.casefold()]}))
                o.parent_id = group_ids[g.name.casefold()]
                report.counts["state offices moved into a region"] += 1

        def office_on(st: str, name: str) -> _Office | None:
            d = find(st, name)
            if d is None or d.territory_id is None:
                return None
            hits = on_territory.get(d.territory_id, [])
            return hits[0] if hits else None

        for g in (g for g in plan.groups if g.kind == "area"):
            so = state_office[g.state]
            members = [m for m in g.members if find(g.state, m) is not None]
            existing_members = [o for o in (office_on(g.state, m) for m in members) if o]
            movable = [o for o in existing_members if o.parent_id == so.id]
            new = [m for m in members if office_on(g.state, m) is None]
            named = [o for o in by_name.get(g.name.casefold(), []) if o.parent_id == so.id]
            if named:
                # it exists, so the admin owns its membership: a district they took out
                # is not pulled back in (rule 6; code review F-3)
                group_ids[g.name.casefold()] = named[0].id
                continue
            if movable or new:
                made = await masters.create_org_unit(db, caller, OrgUnitCreate.model_validate(
                    {"name": g.name, "role_level": 2, "parent_id": so.id}))
                group_ids[g.name.casefold()] = made.id
                report.counts["area offices created"] += 1
            else:
                report.note(f"area {g.name!r}: its districts are already placed elsewhere; left alone")
                continue
            for o in movable:
                await masters.patch_org_unit(db, caller, o.id, OrgUnitPatch.model_validate({"parent_id": group_ids[g.name.casefold()]}))
                o.parent_id = group_ids[g.name.casefold()]
                report.counts["district offices moved into an area"] += 1

        for st, name in sorted(needed):
            if office_on(st, name) is not None:
                continue
            nd = find(st, name)
            assert nd is not None and nd.territory_id is not None
            g_area = area_of.get((st, nd.name))
            parent = (group_ids.get(g_area.name.casefold()) if g_area else None) or state_office[st].id
            made = await masters.create_org_unit(db, caller, OrgUnitCreate.model_validate(
                {"name": do.district_office_name(st, nd.name), "role_level": 2,
                 "parent_id": parent, "territory_id": nd.territory_id}))
            on_territory[nd.territory_id].append(_Office(made.id, made.name, parent, nd.territory_id, 2))
            report.counts["district offices created"] += 1
    except (ApiError, DBAPIError) as exc:
        raise PlanError([f"writing the offices: {_why(exc)}"], report) from exc

    # ── 3. move ──────────────────────────────────────────────────────────────
    refusals: list[str] = []
    left: set[str] = set()
    for dec in plan.decisions:
        who = f"{dec.full_name} ({dec.user_id})"
        if dec.user_id in in_place:
            report.counts["people already in place"] += 1
            continue
        target = targets[dec.user_id]
        if isinstance(target, _Office):
            office_id, own_territory = target.id, target.territory_id
        elif target.kind == "hq":
            office_id, own_territory = root, None
        elif target.kind == "state":
            office_id, own_territory = state_office[target.state].id, state_ids[target.state]
        elif target.kind == "district":
            placed = office_on(target.state, target.district)
            assert placed is not None
            office_id, own_territory = placed.id, placed.territory_id
        else:
            office_id, own_territory = group_ids.get(target.name.casefold(), ""), None
            if not office_id:
                refusals.append(f"{who}: {target.name!r} was not created (its members are placed elsewhere)")
                continue
        if dec.role_code.lower() == do.FIELD_OFFICER and own_territory is None:
            refusals.append(f"{who}: a Field Officer needs an office with its own area (rule 10)")
            continue
        if office_id == dec.current_office_id:
            report.counts["people already in place"] += 1
            continue
        try:
            stay = 0
            async with db.begin_nested():
                if own_territory is None:
                    stay = (await db.execute(text(
                        f"SELECT count(*) FROM lead l WHERE l.owner_user_id = CAST(:u AS uuid) AND {OPEN_LEAD}"),
                        {"u": dec.user_id})).scalar_one()
                await users.patch_user(db, caller, dec.user_id, UserPatch.model_validate({"org_unit_id": office_id}))
            if stay:
                report.note(f"{who}: {stay} open lead(s) stay at their office (rule 20, GAP-582)")
            left.add(dec.current_office_id)
            report.counts["people moved"] += 1
        except (ApiError, DBAPIError) as exc:
            refusals.append(f"{who}: {_why(exc)}")

    if refusals:
        raise PlanError(refusals, report)

    if plan.decisions:
        try:
            await _rehome_unowned(db, caller, root, report)
            await _report_after(db, plan, root, left, report)
        except DBAPIError as exc:   # a lock timeout here is a refusal, not a traceback
            raise PlanError([f"re-homing unowned leads: {_why(exc)}"], report) from exc
    return report


async def _rehome_unowned(db: AsyncSession, caller: Caller, root: str, report: Report) -> None:
    """Rule 24: unowned open leads at Polysil HQ go to the office covering their
    territory, one `lead.rehomed` each, as 084 writes it. Quotations follow (012)."""
    name = (await db.execute(text("SELECT full_name FROM app_user WHERE id = CAST(:u AS uuid)"),
                             {"u": caller.user_id})).scalar_one_or_none() or ""
    rows = (await db.execute(text(
        f"SELECT l.id, l.territory_id FROM lead l WHERE l.owner_user_id IS NULL "
        f"AND l.owner_org_unit_id = CAST(:root AS uuid) AND l.territory_id IS NOT NULL AND {OPEN_LEAD} "
        "FOR UPDATE"), {"root": root})).all()
    for r in rows:
        covering = await leads_service._covering_org_unit(db, str(r.territory_id))
        if covering == root:
            continue
        await db.execute(text(
            "UPDATE lead SET owner_org_unit_id = CAST(:o AS uuid), updated_by = CAST(:me AS uuid) "
            "WHERE id = CAST(:id AS uuid)"), {"o": covering, "me": caller.user_id, "id": str(r.id)})
        await db.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
            "VALUES ('lead', CAST(:id AS uuid), CAST(:id AS uuid), 'lead.rehomed', CAST(:me AS uuid), "
            "CAST(:p AS jsonb))"),
            {"id": str(r.id), "me": caller.user_id,
             "p": json.dumps({"actor_name": name, "owner_org_unit_id": covering,
                              "previous_org_unit_id": root})})
        report.counts["unowned leads re-homed"] += 1


async def _report_after(db: AsyncSession, plan: Plan, root: str, left: set[str],
                        report: Report) -> None:
    """Rules 21 and 22, and plan review note 1: what the operator must know."""
    if left:
        for r in (await db.execute(text("""
            SELECT ar.doc_type, ro.name AS role, count(*) AS n
              FROM approval_request ar
              JOIN approval_step s ON s.request_id = ar.id AND s.decision IS NULL
              JOIN role ro ON ro.id = s.approver_role_id
             WHERE ar.status = 'pending'
               AND CAST(:left AS uuid[]) && ARRAY(
                   SELECT owner_org_unit_id FROM sales_order WHERE id = ar.entity_id AND ar.doc_type = 'sales_order'
                   UNION ALL SELECT owner_org_unit_id FROM quotation WHERE id = ar.entity_id AND ar.doc_type = 'quotation'
                   UNION ALL SELECT owner_org_unit_id FROM complaint WHERE id = ar.entity_id AND ar.doc_type = 'complaint')
             GROUP BY 1, 2 ORDER BY 1, 2"""), {"left": sorted(left)})).all():
            report.note(f"pending approval: {r.n} {r.doc_type} step(s) for a {r.role} on documents "
                        "at an office people left (rule 21, GAP-557)")
    for r in (await db.execute(text(f"""
        SELECT coalesce(d.name, '(no district)') AS district, count(*) AS n FROM lead l
          LEFT JOIN LATERAL (SELECT a.name FROM territory_closure tc JOIN territory a ON a.id = tc.ancestor_id
                              WHERE tc.descendant_id = l.territory_id AND a.level = 'district' LIMIT 1) d ON true
         WHERE l.owner_org_unit_id = CAST(:root AS uuid) AND l.owner_user_id IS NOT NULL AND {OPEN_LEAD}
         GROUP BY 1 ORDER BY 1"""), {"root": root})).all():
        report.note(f"{r.n} open lead(s) in {r.district} stay at Polysil HQ with an owner who stays there")
    for r in (await db.execute(text("""
        SELECT st.code::text AS st, count(*) AS n FROM territory d JOIN territory st ON st.id = d.parent_id
         WHERE d.level = 'district' AND d.deleted_at IS NULL AND upper(st.code::text) = ANY(CAST(:s AS text[]))
           AND EXISTS (SELECT 1 FROM channel_partner p JOIN territory_closure tc ON tc.descendant_id = p.territory_id
                        WHERE tc.ancestor_id = d.id AND p.deleted_at IS NULL)
           AND NOT EXISTS (SELECT 1 FROM app_user u JOIN role r ON r.id = u.role_id
                             JOIN org_unit o ON o.id = u.org_unit_id AND o.deleted_at IS NULL
                             JOIN territory_closure tc ON tc.ancestor_id = o.territory_id AND tc.descendant_id = d.id
                            WHERE lower(r.code::text) = 'field_officer' AND u.is_active AND u.deleted_at IS NULL)
         GROUP BY 1 ORDER BY 1"""), {"s": list(plan.states)})).all():
        report.note(f"{r.st}: {r.n} district(s) with dealers have no Field Officer; their new leads "
                    "go unassigned to the covering office (rule 22)")
