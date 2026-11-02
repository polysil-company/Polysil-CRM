"""The org chart (FS-080): who reports to whom, read through `reporting_lines()`.

The database works out the managers and decides what the caller may see; the
domain builds the picture; this module checks the subject and shapes the answer.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import org_chart as domain
from api.errors import ForbiddenError, NotFoundError
from api.schemas import users as sch
from api.schemas.leads import OrgUnitRef

# relations the caller may re-root on without users.view global (rule 8)
_OWN_LINE = frozenset({"self", "below"})


async def org_chart(db: AsyncSession, caller: Caller, *, user_id: str | None,
                    company: bool) -> sch.OrgChart:
    if caller.user_type != "staff":
        raise ForbiddenError("The org chart is for staff.")
    is_global = caller.scopes.get("users") == "global"
    if company and not is_global:
        raise ForbiddenError("The company view needs users.view at global scope.")

    rows = [domain.Person(
        id=str(r.id), full_name=r.full_name, role_code=r.role_code, role_name=r.role_name,
        level=r.level, org_unit_id=str(r.org_unit_id), org_unit_name=r.org_unit_name,
        manager_ids=tuple(str(m) for m in r.manager_ids), relation=r.relation)
        for r in (await db.execute(text("SELECT * FROM reporting_lines()"))).all()]
    by_id = {p.id: p for p in rows}

    subject_id: str | None = None
    if not company:
        # ids come back lower case; the path pattern also admits upper (code review F-5)
        subject_id = (user_id or caller.user_id).lower()
        found = by_id.get(subject_id)
        # the caller's own row is always there for active staff; anyone else must be
        # in the caller's line below them, or the caller must be global (rule 8)
        if found is None or (subject_id != caller.user_id and not is_global
                             and found.relation not in _OWN_LINE):
            raise NotFoundError("No such person in your reporting line.")

    chart = domain.build(rows, subject_id)
    return sch.OrgChart(
        subject=_person(chart.subject) if chart.subject else None,
        managers=[[_person(p) for p in step] for step in chart.managers],
        people=[sch.OrgChartNode(**_person(n.person).model_dump(),
                                 manager_ids=list(n.person.manager_ids),
                                 direct_reports=n.direct_reports, team_size=n.team_size)
                for n in chart.people],
        co_managers=[_person(p) for p in chart.co_managers],
        totals=sch.OrgChartTotals(
            people=len(chart.people),
            by_role=[sch.RoleCount(role=sch.RoleRef(code=code, name=name), count=n)
                     for code, name, n in chart.by_role]),
        unplaced=[_person(p) for p in chart.unplaced])


def _person(p: domain.Person) -> sch.OrgChartPerson:
    return sch.OrgChartPerson(
        id=p.id, full_name=p.full_name,
        role=sch.RoleRef(code=p.role_code or "", name=p.role_name or ""),
        level=p.level or 0,
        org_unit=OrgUnitRef(id=p.org_unit_id or "", name=p.org_unit_name or ""))
