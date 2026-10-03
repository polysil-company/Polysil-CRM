# ruff: noqa: E501  (embedded SQL)

"""Marketing material (FS-034): the catalogue and orders. Order writes are definers in
migration 038; the catalogue is written here under `marketing_material.edit`. Services
never commit."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import marketing as sch
from api.schemas.leads import PageMeta
from api.services.clock import today_ist
from api.services.leads import _covering_org_unit, _decode_cursor, _encode_cursor
from api.services.orders import _pg_text, _sqlstate

_LIMIT = 100
_ACTIONS = ("approve", "reject", "cancel", "dispatch")


def _db_error(exc: DBAPIError) -> Exception:
    code = _sqlstate(exc) or ""
    msg = _pg_text(exc).split("\n", 1)[0]
    if code == "MKTNF":
        return NotFoundError("No such order.")
    if code == "MKTSC":
        return ConflictError(msg, code="status_changed")
    if code == "MKTIN":
        return ValidationFailed(msg, code="material_inactive")
    if code == "MKTVL":
        return ValidationFailed(msg)
    if code == "APRRM":
        return ValidationFailed("A remark is required.", code="remark_required")
    if code == "42501":
        reason = msg if msg in ("own_order", "not_your_approval") else None
        return ForbiddenError("Not permitted on this order.", code=reason) if reason else ForbiddenError()
    return exc


def _m(v: Any) -> str:
    return format(Decimal(v).quantize(Decimal("0.01")), "f")


def _pct(v: Any) -> str:
    """Two places, or three when the stored share needs them (33.333): the display must
    not hide what the lines compute with (code review F-7)."""
    d = Decimal(v)
    two = d.quantize(Decimal("0.01"))
    return format(two if two == d else d.quantize(Decimal("0.001")), "f")


# ── the catalogue ────────────────────────────────────────────────────────────

_MAT_SELECT = """
SELECT m.*, m.code::text AS code_text, p.price, p.company_share_pct, coalesce(p.is_provisional, false) AS prov
  FROM marketing_material m
  LEFT JOIN marketing_material_price p ON p.material_id = m.id
       AND daterange(p.effective_from, p.effective_to, '[)') @> CAST(:today AS date)"""


def _mat(r: Any) -> sch.Material:
    return sch.Material(id=str(r.id), code=r.code_text, name=r.name, description=r.description, unit=r.unit,
                        price=_m(r.price) if r.price is not None else None,
                        company_share_pct=_pct(r.company_share_pct) if r.company_share_pct is not None else None,
                        is_active=r.is_active, is_provisional=bool(r.prov))


async def list_materials(db: AsyncSession, active: bool | None) -> list[sch.Material]:
    where = "" if active is None else " WHERE m.is_active = :a"
    rows = (await db.execute(text(_MAT_SELECT + where + " ORDER BY m.name"),
                             {"today": today_ist(), "a": active})).all()
    return [_mat(r) for r in rows]


async def get_material(db: AsyncSession, material_id: str) -> sch.Material:
    r = (await db.execute(text(_MAT_SELECT + " WHERE m.id = CAST(:i AS uuid)"),
                          {"today": today_ist(), "i": material_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such item.")
    return _mat(r)


async def create_material(db: AsyncSession, caller: Caller, body: sch.MaterialCreate) -> sch.Material:
    try:
        async with db.begin_nested():
            mid: Any = (await db.execute(text(
                "INSERT INTO marketing_material (code, name, description, unit, created_by, updated_by) "
                "VALUES (:c, :n, :d, :u, CAST(:me AS uuid), CAST(:me AS uuid)) RETURNING id"),
                {"c": body.code, "n": body.name.strip(), "d": body.description, "u": body.unit.strip(),
                 "me": caller.user_id})).scalar_one()
    except IntegrityError as exc:
        raise ConflictError("An item with this code exists.", code="code_taken",
                            fields={"code": "Already used."}) from exc
    await db.execute(text(
        "INSERT INTO marketing_material_price (material_id, price, company_share_pct, effective_from, created_by) "
        "VALUES (CAST(:m AS uuid), :p, :c, :d, CAST(:me AS uuid))"),
        {"m": str(mid), "p": body.price, "c": body.company_share_pct, "d": today_ist(), "me": caller.user_id})
    return await get_material(db, str(mid))


async def patch_material(db: AsyncSession, caller: Caller, material_id: str,
                         body: sch.MaterialPatch) -> sch.Material:
    current = await get_material(db, material_id)
    sent = body.model_dump(exclude_unset=True)
    item = {k: v for k, v in sent.items() if k in ("name", "description", "unit", "is_active")}
    if item:
        sets = ", ".join(f"{k} = :{k}" for k in item)
        await db.execute(text(f"UPDATE marketing_material SET {sets}, updated_by = CAST(:me AS uuid) "
                              "WHERE id = CAST(:i AS uuid)"), {**item, "me": caller.user_id, "i": material_id})
    if "price" in sent or "company_share_pct" in sent:
        price = sent.get("price") if sent.get("price") is not None else Decimal(current.price or "0")
        pct = (sent.get("company_share_pct") if sent.get("company_share_pct") is not None
               else Decimal(current.company_share_pct or "50"))
        today = today_ist()
        # rule 10: the row in force ends today and a new one starts. A row that started today
        # and no order has used is replaced instead, so a typo on the day an item is added can
        # be corrected (code review F-1); once an order uses it, the next change waits a day.
        await db.execute(text(
            "DELETE FROM marketing_material_price WHERE material_id = CAST(:m AS uuid) AND effective_from = :d"),
            {"m": material_id, "d": today})
        try:
            async with db.begin_nested():
                await db.execute(text(
                    "UPDATE marketing_material_price SET effective_to = :d WHERE material_id = CAST(:m AS uuid) "
                    "AND effective_from < :d AND (effective_to IS NULL OR effective_to > :d)"),
                    {"m": material_id, "d": today})
                await db.execute(text(
                    "INSERT INTO marketing_material_price (material_id, price, company_share_pct, effective_from, created_by) "
                    "VALUES (CAST(:m AS uuid), :p, :c, :d, CAST(:me AS uuid))"),
                    {"m": material_id, "p": price, "c": pct, "d": today, "me": caller.user_id})
        except DBAPIError as exc:
            raise ConflictError("An order already uses today's price; change it again tomorrow.",
                                code="price_changed_today") from exc
    return await get_material(db, material_id)


# ── orders ───────────────────────────────────────────────────────────────────

_SELECT = """
SELECT o.*, o.order_no::text AS no_text, p.name AS partner_name, ru.full_name AS requester_name,
       ou.name AS office_name, du.full_name AS decider_name, xu.full_name AS dispatcher_name
  FROM marketing_order o
  LEFT JOIN channel_partner p ON p.id = o.partner_id
  LEFT JOIN app_user ru ON ru.id = o.requested_by
  LEFT JOIN org_unit ou ON ou.id = o.owner_org_unit_id
  LEFT JOIN app_user du ON du.id = o.decided_by
  LEFT JOIN app_user xu ON xu.id = o.dispatched_by"""


def _totals(r: Any) -> sch.Totals:
    return sch.Totals(value=_m(r.value), company_share=_m(r.company_share), dealer_share=_m(r.dealer_share))


def _summary(r: Any) -> sch.MarketingOrderSummary:
    return sch.MarketingOrderSummary(
        id=str(r.id), order_no=r.no_text, status=r.status,
        partner=sch.Ref(id=str(r.partner_id), name=r.partner_name) if r.partner_id else None,
        requested_by=sch.Ref(id=str(r.requested_by), name=r.requester_name),
        office=sch.Ref(id=str(r.owner_org_unit_id), name=r.office_name), totals=_totals(r),
        is_provisional=r.is_provisional, created_at=r.created_at.isoformat())


async def get_order(db: AsyncSession, caller: Caller, order_id: str) -> sch.MarketingOrder:
    r = (await db.execute(text(_SELECT + " WHERE o.id = CAST(:i AS uuid)"), {"i": order_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such order.")
    lines = (await db.execute(text(
        "SELECT * FROM marketing_order_line WHERE order_id = CAST(:i AS uuid) ORDER BY line_no"), {"i": order_id})).all()
    can = {a: (await db.execute(text("SELECT marketing_order_refusal(CAST(:i AS uuid), :a)"),
                                {"i": order_id, "a": a})).scalar_one() is None for a in _ACTIONS}
    portal = caller.partner_id is not None
    decision = None
    if r.decided_at is not None and r.status in ("approved", "rejected", "dispatched", "cancelled"):
        decision = sch.DecisionOut(
            status="rejected" if r.status == "rejected" else "approved",
            by=None if portal else sch.Ref(id=str(r.decided_by), name=r.decider_name),
            at=r.decided_at.isoformat(), remark=r.decision_remark)
    dispatch = (sch.DispatchOut(dispatched_on=r.dispatched_on.isoformat(), reference=r.dispatch_reference,
                                by=None if portal else sch.Ref(id=str(r.dispatched_by), name=r.dispatcher_name))
                if r.dispatched_on else None)
    s = _summary(r)
    return sch.MarketingOrder(
        **s.model_dump(exclude={"partner", "requested_by", "office", "totals"}),
        partner=s.partner, requested_by=s.requested_by, office=s.office, totals=s.totals,
        lines=[sch.Line(id=str(x.id), material=sch.MaterialRef(id=str(x.material_id), code=x.code, name=x.name),
                        unit=x.unit, qty=x.qty, price=_m(x.price), value=_m(x.value),
                        company_share_pct=_pct(x.company_share_pct), company_share=_m(x.company_share),
                        dealer_share=_m(x.dealer_share)) for x in lines],
        remark=r.remark, decision=decision, dispatch=dispatch, cancel_remark=r.cancel_remark,
        can=sch.Can(**can))


async def create_order(db: AsyncSession, caller: Caller, body: sch.OrderCreate) -> sch.MarketingOrder:
    partner_id = caller.partner_id or body.partner_id
    territory = None
    if partner_id:
        territory = (await db.execute(text("SELECT territory_id FROM channel_partner WHERE id = CAST(:p AS uuid)"),
                                      {"p": partner_id})).scalar_one_or_none()
        if territory is None:
            raise ValidationFailed(fields={"partner_id": "No such partner in your scope."})
    # rule 6: a dealer's own order goes to the office over its territory (the lead routing rule);
    # a staff order to the requester's own office, whoever it is for (code review F-5)
    if caller.partner_id:
        office = await _covering_org_unit(db, str(territory))
    elif caller.org_unit_id:
        office = caller.org_unit_id
    elif territory is not None:
        office = await _covering_org_unit(db, str(territory))
    else:
        raise ValidationFailed(fields={"partner_id": "Required for a user with no office."})
    seen: set[str] = set()
    for i, line in enumerate(body.lines):
        if line.material_id in seen:
            raise ValidationFailed(fields={f"lines[{i}].material_id": "Listed twice."})
        seen.add(line.material_id)
    try:
        async with db.begin_nested():
            oid: Any = (await db.execute(text(
                "SELECT marketing_order_create(CAST(:p AS uuid), CAST(:o AS uuid), CAST(:l AS jsonb), :r)"),
                {"p": partner_id, "o": office, "l": json.dumps([x.model_dump() for x in body.lines]),
                 "r": body.remark})).scalar_one()
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return await get_order(db, caller, str(oid))


async def act(db: AsyncSession, caller: Caller, order_id: str, action: str, remark: str | None = None,
              dispatched_on: Any = None, reference: str | None = None) -> sch.MarketingOrder:
    try:
        async with db.begin_nested():
            await db.execute(text("SELECT marketing_order_act(CAST(:i AS uuid), :a, :r, :d, :ref)"),
                             {"i": order_id, "a": action, "r": remark, "d": dispatched_on, "ref": reference})
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return await get_order(db, caller, order_id)


async def list_orders(db: AsyncSession, caller: Caller, *, status: str | None = None,
                      partner_id: str | None = None, awaiting: str | None = None, mine: bool = False,
                      cursor: str | None = None, limit: int = 50) -> sch.MarketingOrderPage:
    limit = max(1, min(limit, _LIMIT))
    where = ["true"]
    params: dict[str, Any] = {"lim": limit + 1}
    if status:
        where.append("o.status = ANY(CAST(:st AS text[]))")
        params["st"] = [s.strip() for s in status.split(",") if s.strip()]
    if partner_id:
        where.append("o.partner_id = CAST(:p AS uuid)")
        params["p"] = partner_id
    if mine:
        where.append("o.requested_by = CAST(:me AS uuid)")
        params["me"] = caller.user_id
    if awaiting == "me":
        where.append("o.status = 'submitted' AND marketing_order_refusal(o.id, 'approve') IS NULL")
    if cursor:
        at, oid = _decode_cursor(cursor)
        where.append("(o.created_at, o.id) < (:at, CAST(:oid AS uuid))")
        params.update(at=at, oid=oid)
    rows = (await db.execute(text(_SELECT + " WHERE " + " AND ".join(where)
                                  + " ORDER BY o.created_at DESC, o.id DESC LIMIT :lim"), params)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].created_at, str(rows[-1].id))
    return sch.MarketingOrderPage(data=[_summary(r) for r in rows],
                                  meta=PageMeta(limit=limit, next_cursor=next_cursor))
