"""The setup check (FS-082 D): what is set up wrong, in plain words, for an admin.

Read-only. Each check is a count, the first items and why it matters. ISS-233 is
the case it exists for: thirty field staff in an office with no area, accepted by
the user form without a word. Services never commit.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.config import get_settings
from api.domain import identity
from api.errors import ForbiddenError
from api.schemas import users as sch
from api.services import teams
from api.services.users import area_office_sql

ITEMS = 100
TOP_LEVEL = 5   # Admin-Sales and MD/CEO; nobody above them to report to


def _check(code: str, title: str, why: str, items: list[sch.SetupItem]) -> sch.SetupCheck:
    ordered = sorted(items, key=lambda i: (i.name, i.id))
    return sch.SetupCheck(code=code, title=title, why=why, count=len(ordered), items=ordered[:ITEMS])


def _people(rows: Any) -> list[sch.SetupItem]:
    return [sch.SetupItem(id=str(r.id), name=r.full_name, detail=f"{r.role_name} · {r.office}")
            for r in rows]


async def setup_check(db: AsyncSession, caller: Caller) -> sch.SetupReport:
    if not (caller.user_type == "staff" and caller.scopes.get("users") == "global"
            and ("users", "edit") in caller.permissions):
        raise ForbiddenError("The setup check needs users.edit at global scope.")

    staff_where = ("u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL "
                   "AND u.id <> ALL(CAST(:np AS uuid[])) AND NOT r.is_portal")
    settings = get_settings()
    np = [settings.system_user_id, settings.intake_user_id]
    checks: list[sch.SetupCheck] = []

    rows = (await db.execute(text(f"""
        SELECT u.id, u.full_name, r.name AS role_name, o.name AS office
          FROM app_user u JOIN role r ON r.id = u.role_id JOIN org_unit o ON o.id = u.org_unit_id
          LEFT JOIN territory t ON t.id = o.territory_id AND t.deleted_at IS NULL
         WHERE {staff_where} AND lower(r.code::text) = ANY(CAST(:roles AS text[]))
           AND t.id IS NULL AND o.id <> CAST(:sys AS uuid)
           -- FS-085 rule 10: a District Manager in an area office is placed
           AND NOT (lower(r.code::text) = ANY(CAST(:area_roles AS text[])) AND {area_office_sql('o')})"""),
        {"np": np, "roles": sorted(identity.AREA_ROLES), "sys": identity.SYSTEM_ORG_UNIT_ID,
         "area_roles": sorted(identity.AREA_OFFICE_ROLES)})).all()
    checks.append(_check(
        "staff_without_area", "Field staff in an office that covers no area",
        "They see dealers only in the districts assigned to them on the user form, and none "
        "if they have none, so they may not be able to assign one to a lead or pick one on an "
        "order. A manager there sees everything under that office, not just their area.",
        _people(rows)))

    # the same rule as the user form (users._role_needs_territory)
    rows = (await db.execute(text(f"""
        SELECT u.id, u.full_name, r.name AS role_name, o.name AS office
          FROM app_user u JOIN role r ON r.id = u.role_id JOIN org_unit o ON o.id = u.org_unit_id
         WHERE {staff_where}
           AND EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id = r.id
                        AND rp.action = 'view' AND rp.scope = 'territory' AND rp.deleted_at IS NULL)
           AND NOT EXISTS (SELECT 1 FROM user_territory ut WHERE ut.user_id = u.id AND ut.deleted_at IS NULL)"""),
        {"np": np})).all()
    checks.append(_check(
        "staff_without_territories", "Staff whose role works by area but who have no area",
        "Their role reads some screens by area. With no area they see nothing there.",
        _people(rows)))

    lines = await teams.lines(db)
    by_id = {p.id: p for p in lines}
    functional = {r[0] for r in (await db.execute(text(
        "SELECT lower(code::text) FROM role WHERE is_functional AND deleted_at IS NULL"))).all()}
    skipping: list[sch.SetupItem] = []
    for p in lines:
        if (p.relation == "unplaced" or (p.role_code or "").lower() in functional
                or (p.level or 0) >= TOP_LEVEL):
            continue
        bosses = [by_id[m] for m in p.manager_ids if m in by_id]
        if not bosses:
            skipping.append(sch.SetupItem(id=p.id, name=p.full_name,
                                          detail=f"{p.role_name} · {p.org_unit_name} · reports to nobody"))
            continue
        nearest = min(b.level or 0 for b in bosses)
        if nearest > (p.level or 0) + 1:
            names = ", ".join(sorted({b.role_name or "" for b in bosses if b.level == nearest}))
            skipping.append(sch.SetupItem(id=p.id, name=p.full_name,
                                          detail=f"{p.role_name} · {p.org_unit_name} · reports to {names}"))
    # GAP-559: "one level up" is the assumed shape of the chain
    checks.append(_check(
        "staff_skipping_a_level", "Staff with no manager one level above them",
        "Usually a district or state with nobody in the role above. Their work goes "
        "straight to someone more senior, and the org chart and approvals skip a level.",
        skipping))

    checks.append(_check(
        "unplaced_staff", "Staff on the System office",
        "They are outside every team, so no manager sees them in reports or the org chart.",
        [sch.SetupItem(id=p.id, name=p.full_name, detail=p.role_name or "")
         for p in lines if p.relation == "unplaced"]))

    if caller.scopes.get("partners") == "global":
        rows = (await db.execute(text(
            "SELECT id, name, partner_type::text AS ptype FROM channel_partner "
            "WHERE is_active AND deleted_at IS NULL AND territory_id IS NULL"))).all()
        checks.append(_check(
            "partners_without_area", "Partners with no area",
            "Only head-office staff can see them. Nobody in the field can assign them a lead.",
            [sch.SetupItem(id=str(r.id), name=r.name, detail=r.ptype.replace("_", " "))
             for r in rows]))

    return sch.SetupReport(ok=all(c.count == 0 for c in checks), checks=checks)
