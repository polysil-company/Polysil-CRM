"""Team filters and the roster for the reports (FS-082).

A team is a person and everyone below them on the org chart (FS-080). The database
works out who manages whom in `reporting_lines()`; this module turns the report's
`team_of` and `roles` parameters into owner ids, and picks the people the
salesperson report lists with zeros. Services never commit.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import org_chart as chart
from api.errors import NotFoundError, ValidationFailed

MAX_ROLES = 10
# FS-080 rule 8: the relations a caller may name without users.view global
_OWN_LINE = frozenset({"self", "below"})


@dataclass(frozen=True)
class Team:
    team_of: str | None
    roles: list[str] | None
    owners: list[str]


async def lines(db: AsyncSession) -> list[chart.Person]:
    """The rows of `reporting_lines()` the caller may see, as domain people."""
    return [chart.Person(
        id=str(r.id), full_name=r.full_name, role_code=r.role_code, role_name=r.role_name,
        level=r.level, org_unit_id=str(r.org_unit_id), org_unit_name=r.org_unit_name,
        manager_ids=tuple(str(m) for m in r.manager_ids), relation=r.relation)
        for r in (await db.execute(text("SELECT * FROM reporting_lines()"))).all()]


async def _role_codes(db: AsyncSession, raw: str) -> list[str]:
    codes = sorted({c.strip().lower() for c in raw.split(",") if c.strip()})
    if not codes or len(codes) > MAX_ROLES:
        raise ValidationFailed(fields={"roles": f"1 to {MAX_ROLES} role codes"})
    known = {r[0] for r in (await db.execute(text(
        "SELECT lower(code::text) FROM role WHERE lower(code::text) = ANY(CAST(:c AS text[])) "
        "AND NOT is_portal AND deleted_at IS NULL"), {"c": codes})).all()}
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise ValidationFailed(fields={"roles": f"unknown: {', '.join(unknown)}"})
    return codes


async def resolve(db: AsyncSession, caller: Caller, *, team_of: str | None, roles: str | None,
                  owner_id: str | None) -> tuple[Team | None, list[chart.Person] | None]:
    """The team filter as owner ids, and the rows it was worked out from (so the
    roster need not call `reporting_lines()` again). (None, None) when unset."""
    if team_of is None and roles is None:
        return None, None
    field = "team_of" if team_of is not None else "roles"
    if caller.user_type != "staff":
        raise ValidationFailed(fields={field: "for staff"})
    if team_of is not None and owner_id is not None:
        raise ValidationFailed(fields={"team_of": "not with owner_id"})
    codes = await _role_codes(db, roles) if roles is not None else None
    rows = await lines(db)
    placed = [p for p in rows if p.relation != "unplaced"]
    subject: str | None = None
    if team_of is not None:
        subject = team_of.lower()
        found = next((p for p in placed if p.id == subject), None)
        is_global = caller.scopes.get("users") == "global"
        if found is None or (subject != caller.user_id and not is_global
                             and found.relation not in _OWN_LINE):
            raise NotFoundError("No such person in your reporting line.",
                                code="not_in_your_line", fields={"team_of": "not in your line"})
        ids = chart.team(rows, subject)
    else:
        # plan review S-3: the lead scope still applies, so every row may narrow
        ids = {p.id for p in placed}
    if codes is not None:
        ids = {p.id for p in placed if p.id in ids and (p.role_code or "").lower() in codes}
    return Team(team_of=subject, roles=codes, owners=sorted(ids)), rows


async def roster(db: AsyncSession, caller: Caller, *, rows: list[chart.Person] | None,
                 owners: list[str] | None, territories: list[str]) -> list[chart.Person]:
    """The people the salesperson report lists even with no activity (FS-082 B).

    Only people whose leads the caller's lead scope reaches, so a zero is never a
    figure the caller could not see (rule 3, EC-2)."""
    scope = caller.scopes.get("leads")
    if caller.user_type != "staff" or scope not in ("own", "org_subtree", "global"):
        return []
    if rows is None:
        rows = await lines(db)
    placed = [p for p in rows if p.relation != "unplaced"]
    if scope == "own":
        people = [p for p in placed if p.id == caller.user_id]
    elif scope == "global" and caller.scopes.get("users") == "global":
        people = placed
    else:
        mine = chart.team(rows, caller.user_id)
        people = [p for p in placed if p.id in mine]
    if owners is not None:
        keep = set(owners)
        people = [p for p in people if p.id in keep]
    if territories and people:
        # EC-8: a person's areas are their office's territory and their own
        # territories; one matches when it is in, under or above a filter territory
        # (the closure holds each territory as its own ancestor)
        hit = {str(r[0]) for r in (await db.execute(text("""
            WITH mine AS (
                SELECT ou.id AS person_id, o.territory_id
                  FROM unnest(CAST(:ids AS uuid[])) AS ou(id)
                  JOIN app_user au ON au.id = ou.id
                  JOIN org_unit o ON o.id = au.org_unit_id
                 WHERE o.territory_id IS NOT NULL
                UNION
                SELECT ut.user_id, ut.territory_id FROM user_territory ut
                 WHERE ut.user_id = ANY(CAST(:ids AS uuid[])) AND ut.deleted_at IS NULL)
            SELECT DISTINCT m.person_id FROM mine m
              JOIN territory_closure tc
                ON (tc.ancestor_id = ANY(CAST(:t AS uuid[])) AND tc.descendant_id = m.territory_id)
                OR (tc.descendant_id = ANY(CAST(:t AS uuid[])) AND tc.ancestor_id = m.territory_id)"""),
            {"ids": [p.id for p in people], "t": territories})).all()}
        people = [p for p in people if p.id in hit]
    return people
