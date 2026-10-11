"""Campaigns (FS-040, migration 049).

Every staff user reads the list; RLS refuses a partner user and the write policies
follow RBAC 6.2. Cost is cut here for a caller without campaigns.view (rule 1,
GAP-250). Lead counts and the summary are over the leads the caller can see.
Services never commit."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import campaigns as sch
from api.schemas.leads import TerritoryRef
from api.services import reports
from api.services.reports import _money

_SELECT = """
SELECT c.id::text AS id, c.name::text AS name, c.type, c.territory_id, t.name AS territory_name,
       t.level::text AS territory_level, c.start_date, c.end_date, c.cost_planned, c.cost_actual,
       c.description, c.is_active, c.created_at, c.updated_at
  FROM campaign c
  LEFT JOIN territory t ON t.id = c.territory_id"""

_NAME_TAKEN = "Another campaign has this name."


def _staff(caller: Caller) -> None:
    if caller.partner_id is not None:
        raise ForbiddenError("Campaigns are for staff.")


def _blank() -> reports.Filters:
    return reports.Filters(start=None, end=None, territory_id=None, owner_id=None)


async def _lead_counts(db: AsyncSession, caller: Caller, ids: list[str]) -> dict[str, int]:
    if not ids:
        return {}
    per = await reports.campaign_figures(db, caller, _blank(), windowed=False, ids=ids, sales=False)
    return {k: int(v["leads"]) for k, v in per.items()}


def _out(r: Any, caller: Caller, lead_count: int, summary: sch.CampaignSummary | None = None) -> sch.Campaign:
    see_cost = "campaigns" in caller.scopes
    return sch.Campaign(
        id=r.id, name=r.name, type=r.type,
        territory=(TerritoryRef(id=str(r.territory_id), name=r.territory_name, level=r.territory_level)
                   if r.territory_id else None),
        start_date=r.start_date.isoformat(), end_date=r.end_date.isoformat() if r.end_date else None,
        cost_planned=_money(r.cost_planned) if see_cost else None,
        cost_actual=_money(r.cost_actual) if see_cost and r.cost_actual is not None else None,
        description=r.description, is_active=r.is_active, lead_count=lead_count,
        created_at=r.created_at.isoformat(), updated_at=r.updated_at.isoformat(), summary=summary)


async def list_campaigns(db: AsyncSession, caller: Caller, *, active: bool | None = None,
                         type_: str | None = None, q: str | None = None) -> list[sch.Campaign]:
    """Newest start first, then name; at most 500."""
    _staff(caller)
    rows = (await db.execute(text(
        _SELECT + " WHERE (CAST(:a AS boolean) IS NULL OR c.is_active = CAST(:a AS boolean))"
        " AND (CAST(:ty AS text) IS NULL OR c.type = CAST(:ty AS text))"
        " AND (CAST(:q AS text) IS NULL OR strpos(lower(c.name::text), lower(CAST(:q AS text))) > 0)"
        " ORDER BY c.start_date DESC, c.name LIMIT 500"),
        {"a": active, "ty": type_, "q": q or None})).all()
    counts = await _lead_counts(db, caller, [r.id for r in rows])
    return [_out(r, caller, counts.get(r.id, 0)) for r in rows]


async def get_campaign(db: AsyncSession, caller: Caller, campaign_id: str) -> sch.Campaign:
    _staff(caller)
    r = (await db.execute(text(_SELECT + " WHERE c.id = CAST(:i AS uuid)"), {"i": campaign_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such campaign.")
    f = await _blank().load_sale_mode(db)
    g = (await reports.campaign_figures(db, caller, f, windowed=False, ids=[r.id])).get(r.id) or {}
    leads, won, lost = int(g.get("leads", 0)), int(g.get("won", 0)), int(g.get("lost", 0))
    cost = reports.campaign_cost(r.cost_planned, r.cost_actual) if "campaigns" in caller.scopes else None
    summary = sch.CampaignSummary(
        leads=leads, won=won, lost=lost, open=leads - won - lost,
        sales_value=_money(g.get("sales_value")) if "sales_orders" in caller.scopes else None,
        cost_per_lead=reports.per_unit(cost, leads), cost_per_won=reports.per_unit(cost, won))
    return _out(r, caller, leads, summary)


async def _check_territory(db: AsyncSession, territory_id: str | None) -> None:
    if territory_id is None:
        return
    seen = (await db.execute(text(
        "SELECT 1 FROM territory WHERE id = CAST(:t AS uuid) AND deleted_at IS NULL"),
        {"t": territory_id})).first()
    if seen is None:
        raise ValidationFailed(fields={"territory_id": "not found"})


async def _name_free(db: AsyncSession, name: str, *, other_than: str | None = None) -> None:
    taken = (await db.execute(text(
        "SELECT 1 FROM campaign WHERE name = CAST(:n AS citext) "
        "AND (CAST(:i AS uuid) IS NULL OR id <> CAST(:i AS uuid))"), {"n": name, "i": other_than})).first()
    if taken:
        raise ConflictError(_NAME_TAKEN, code="campaign_name_taken", fields={"name": "taken"})


async def _event(db: AsyncSession, caller: Caller, campaign_id: str, kind: str, payload: dict[str, Any]) -> None:
    # CLAUDE.md 4.1 rule 7, in the same transaction; read through the campaign's own
    # visibility (activity.py ENTITY_BY_ID)
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload) "
        "VALUES ('campaign', CAST(:i AS uuid), :k, CAST(:me AS uuid), "
        "CAST(:p AS jsonb) || jsonb_build_object('actor_name', "
        "coalesce((SELECT full_name FROM app_user WHERE id = CAST(:me AS uuid)), '')))"),
        {"i": campaign_id, "k": kind, "me": caller.user_id, "p": json.dumps(payload)})


def _jsonable(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v is not None and not isinstance(v, (bool, int, str)) else v)


async def create_campaign(db: AsyncSession, caller: Caller, body: sch.CampaignCreate) -> sch.Campaign:
    _staff(caller)
    if body.end_date is not None and body.end_date < body.start_date:
        raise ValidationFailed(fields={"end_date": "before start_date"})
    await _check_territory(db, body.territory_id)
    await _name_free(db, body.name)
    try:
        async with db.begin_nested():
            new_id = (await db.execute(text(
                "INSERT INTO campaign (name, type, territory_id, start_date, end_date, cost_planned, "
                "cost_actual, description, created_by, updated_by) VALUES (:n, :ty, CAST(:t AS uuid), "
                ":sd, :ed, :cp, :ca, :d, CAST(:me AS uuid), CAST(:me AS uuid)) RETURNING id::text"),
                {"n": body.name, "ty": body.type, "t": body.territory_id, "sd": body.start_date,
                 "ed": body.end_date, "cp": body.cost_planned, "ca": body.cost_actual,
                 "d": body.description, "me": caller.user_id})).scalar_one()
    except IntegrityError as exc:
        if "uq_campaign_name" in str(exc.orig):
            raise ConflictError(_NAME_TAKEN, code="campaign_name_taken", fields={"name": "taken"}) from exc
        raise
    await _event(db, caller, new_id, "campaign.created", {"name": body.name, "type": body.type})
    return await get_campaign(db, caller, new_id)


_COST = frozenset({"cost_planned", "cost_actual"})
_PATCH_REQUIRED = frozenset({"name", "type", "start_date", "cost_planned", "is_active"})
_COLUMNS = ("name", "type", "territory_id", "start_date", "end_date", "cost_planned", "cost_actual",
            "description", "is_active")


async def patch_campaign(db: AsyncSession, caller: Caller, campaign_id: str,
                         body: sch.CampaignPatch) -> sch.Campaign:
    _staff(caller)
    fields = body.model_fields_set
    if not fields:
        raise ValidationFailed(fields={"body": "nothing to change"})
    for f in fields & _PATCH_REQUIRED:
        if getattr(body, f) is None:
            raise ValidationFailed(fields={f: "cannot be cleared"})
    row = (await db.execute(text(
        "SELECT name::text AS name, type, territory_id::text AS territory_id, start_date, end_date, "
        "cost_planned, cost_actual, description, is_active FROM campaign "
        "WHERE id = CAST(:i AS uuid) FOR UPDATE"), {"i": campaign_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such campaign.")
    old = {c: getattr(row, c) for c in _COLUMNS}
    new = {**old, **{f: getattr(body, f) for f in fields}}
    changed = {c: new[c] for c in _COLUMNS if c in fields and new[c] != old[c]}
    if not changed:
        return await get_campaign(db, caller, campaign_id)
    if new["end_date"] is not None and new["end_date"] < new["start_date"]:
        raise ValidationFailed(fields={"end_date": "before start_date"})
    if "territory_id" in changed:
        await _check_territory(db, new["territory_id"])
    if "name" in changed:
        await _name_free(db, new["name"], other_than=campaign_id)
    try:
        async with db.begin_nested():
            result = await db.execute(text(
                "UPDATE campaign SET name = :name, type = :type, territory_id = CAST(:territory_id AS uuid), "
                "start_date = :start_date, end_date = :end_date, cost_planned = :cost_planned, "
                "cost_actual = :cost_actual, description = :description, is_active = :is_active, "
                "updated_by = CAST(:me AS uuid) WHERE id = CAST(:i AS uuid)"),
                {**new, "me": caller.user_id, "i": campaign_id})
    except IntegrityError as exc:
        if "uq_campaign_name" in str(exc.orig):
            raise ConflictError(_NAME_TAKEN, code="campaign_name_taken", fields={"name": "taken"}) from exc
        raise
    if getattr(result, "rowcount", 1) == 0:     # visible but not editable: the UPDATE policy
        raise ForbiddenError("Editing campaigns needs campaigns.edit.")
    # cost is for campaigns.view, and every staff user reads campaign events: name the
    # field, never the figure (edge case 3)
    await _event(db, caller, campaign_id, "campaign.updated",
                 {"name": new["name"], "changed": {k: (None if k in _COST else _jsonable(v))
                                                    for k, v in changed.items()}})
    return await get_campaign(db, caller, campaign_id)


async def delete_campaign(db: AsyncSession, caller: Caller, campaign_id: str) -> None:
    _staff(caller)
    row = (await db.execute(text(
        "SELECT name::text AS name FROM campaign WHERE id = CAST(:i AS uuid) FOR UPDATE"),
        {"i": campaign_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such campaign.")
    # leads and QR codes the caller cannot see count too (definer); switch it off instead
    if (await db.execute(text("SELECT campaign_in_use(CAST(:i AS uuid))"), {"i": campaign_id})).scalar_one():
        raise ConflictError("Leads or QR codes name this campaign, counting deleted and merged "
                            "leads. Switch it off instead.", code="campaign_in_use")
    # the event first: activity_event_sel resolves through the campaign row, and the
    # audit row keeps the deleted campaign
    await _event(db, caller, campaign_id, "campaign.deleted", {"name": row.name})
    try:
        async with db.begin_nested():
            result = await db.execute(text("DELETE FROM campaign WHERE id = CAST(:i AS uuid)"), {"i": campaign_id})
    except IntegrityError as exc:       # a lead named it after the check
        raise ConflictError("Leads or QR codes name this campaign. Switch it off instead.",
                            code="campaign_in_use") from exc
    if getattr(result, "rowcount", 1) == 0:
        raise ForbiddenError("Deleting campaigns needs campaigns.delete.")

