"""Schemes (FS-031): the master, the order preview, standings and entitlements.

What an order gets or earns is not decided here. Migration 033's status trigger does
every benefit write, inside whichever definer moves the order, and the preview below
calls the same SQL functions, so the two cannot disagree (plan review B2). This
service owns the master and the reads.

Services never commit (rule 3): the dependency owns the transaction.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import schemes as domain
from api.errors import ConflictError, NotFoundError, ValidationFailed
from api.schemas import schemes as sch
from api.schemas.leads import PageMeta
from api.services.clock import today_ist
from api.services.leads import _decode_cursor, _encode_cursor
from api.services.orders import _sqlstate, map_db_error

_LIMIT = 100

_SELECT = """
SELECT s.id, s.code::text AS code, s.name, s.description, s.scheme_type::text AS scheme_type,
       s.metric::text AS metric, s.condition_min, s.condition_max,
       s.benefit_kind::text AS benefit_kind, s.benefit_value, s.benefit_cap, s.entitlement_days,
       s.period::text AS period, s.valid_from, s.valid_to, s.priority, s.stackable, s.is_active,
       s.created_at, scheme_used(s.id) AS used,
       coalesce((SELECT jsonb_agg(jsonb_build_object('type', t.target_type::text, 'id', t.target_id)
                                  ORDER BY t.target_type, t.target_id)
                   FROM scheme_target t WHERE t.scheme_id = s.id), '[]'::jsonb) AS targets
  FROM scheme s"""


def _num(v: Decimal | None) -> str | None:
    if v is None:
        return None
    return format(v.normalize(), "f") if v == v.to_integral_value() else format(v, "f")


def _money(v: Any) -> str:
    return format(Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _out(r: Any) -> sch.Scheme:
    today = today_ist()
    targets = r.targets if isinstance(r.targets, list) else json.loads(r.targets)
    return sch.Scheme(
        id=str(r.id), code=r.code, name=r.name, description=r.description,
        scheme_type=r.scheme_type,
        condition=sch.ConditionOut(metric=r.metric, min=_num(r.condition_min) or "0",
                                   max=_num(r.condition_max)),
        benefit=sch.BenefitOut(kind=r.benefit_kind, value=_num(r.benefit_value) or "0",
                               cap=_money(r.benefit_cap) if r.benefit_cap is not None else None,
                               entitlement_days=r.entitlement_days),
        period=r.period, valid_from=r.valid_from.isoformat(),
        valid_to=r.valid_to.isoformat() if r.valid_to else None, priority=r.priority,
        stackable=r.stackable, is_active=r.is_active,
        is_current=bool(r.is_active and r.valid_from <= today
                        and (r.valid_to is None or r.valid_to >= today)),
        used=bool(r.used), targets=[sch.Target(**t) for t in targets],
        created_at=r.created_at.isoformat())


def _terms(body: sch.SchemeCreate) -> domain.Terms:
    return domain.Terms(
        scheme_type=body.scheme_type, benefit_kind=body.benefit.kind,
        benefit_value=body.benefit.value, benefit_cap=body.benefit.cap,
        entitlement_days=body.benefit.entitlement_days, period=body.period,
        condition_min=body.condition.min, condition_max=body.condition.max,
        valid_from=body.valid_from, valid_to=body.valid_to)


async def _check_targets(db: AsyncSession, targets: list[sch.Target]) -> None:
    pairs = [(t.type, t.id) for t in targets]
    problems = domain.target_problems(pairs)
    tables = {"territory": "territory", "partner": "channel_partner", "product": "product",
              "product_category": "product_category"}
    for i, t in enumerate(targets):
        if f"targets[{i}].type" in problems or t.type == "partner_type":
            continue
        try:
            import uuid
            uuid.UUID(t.id)
        except ValueError:
            problems[f"targets[{i}].id"] = "Not an id."
            continue
        found = (await db.execute(text(
            f"SELECT 1 FROM {tables[t.type]} WHERE id = CAST(:i AS uuid)"), {"i": t.id})).first()
        if found is None:
            problems[f"targets[{i}].id"] = "No such record in your scope."
    if problems:
        raise ValidationFailed(fields=problems)


async def _event(db: AsyncSession, caller: Caller, scheme_id: str, kind: str,
                 **payload: Any) -> None:
    name = (await db.execute(text("SELECT full_name FROM app_user WHERE id = CAST(:u AS uuid)"),
                             {"u": caller.user_id})).scalar_one_or_none()
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload) "
        "VALUES ('scheme', CAST(:s AS uuid), :k, CAST(:u AS uuid), CAST(:p AS jsonb))"),
        {"s": scheme_id, "k": kind, "u": caller.user_id,
         "p": json.dumps({"actor_name": name or "", **payload})})


async def _write_targets(db: AsyncSession, scheme_id: str, targets: list[sch.Target]) -> None:
    for t in targets:
        await db.execute(text(
            "INSERT INTO scheme_target (scheme_id, target_type, target_id) "
            "VALUES (CAST(:s AS uuid), CAST(:t AS scheme_target_type), :i)"),
            {"s": scheme_id, "t": t.type, "i": t.id.lower() if t.type != "partner_type" else t.id})


def _db_error(exc: DBAPIError) -> Exception:
    if _sqlstate(exc) == domain.SQLSTATE_IN_USE:
        return ConflictError("This scheme has given benefits. Only its end date and active "
                             "flag can change; end it and create a new one.",
                             code="scheme_in_use")
    return map_db_error(exc)


async def get_scheme(db: AsyncSession, scheme_id: str) -> sch.Scheme:
    r = (await db.execute(text(_SELECT + " WHERE s.id = CAST(:s AS uuid)"),
                          {"s": scheme_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such scheme.")
    return _out(r)


async def create_scheme(db: AsyncSession, caller: Caller, body: sch.SchemeCreate) -> sch.Scheme:
    terms = _terms(body)
    problems = domain.problems(terms)
    if problems:
        raise ValidationFailed(fields=problems)
    await _check_targets(db, body.targets)
    try:
        async with db.begin_nested():
            scheme_id = str((await db.execute(text(
                "INSERT INTO scheme (code, name, description, scheme_type, metric, condition_min, "
                "condition_max, benefit_kind, benefit_value, benefit_cap, entitlement_days, period, "
                "valid_from, valid_to, priority, stackable, created_by, updated_by) VALUES "
                "(:code, :name, :descr, CAST(:t AS scheme_type), CAST(:m AS scheme_metric), :cmin, "
                ":cmax, CAST(:k AS scheme_benefit_kind), :v, :cap, :days, CAST(:per AS scheme_period), "
                ":vf, :vt, :pr, :st, CAST(:u AS uuid), CAST(:u AS uuid)) RETURNING id"),
                {"code": body.code, "name": body.name.strip(), "descr": body.description,
                 "t": body.scheme_type, "m": body.condition.metric, "cmin": body.condition.min,
                 "cmax": body.condition.max, "k": body.benefit.kind, "v": body.benefit.value,
                 "cap": body.benefit.cap, "days": domain.entitlement_days(terms),
                 "per": body.period, "vf": body.valid_from, "vt": body.valid_to,
                 "pr": body.priority, "st": body.stackable, "u": caller.user_id})).scalar_one())
    except IntegrityError as exc:
        if "scheme_code_key" in str(exc.orig):
            raise ConflictError("A scheme with this code exists.", code="code_taken",
                                fields={"code": "Already used."}) from exc
        raise
    await _write_targets(db, scheme_id, body.targets)
    await _event(db, caller, scheme_id, "scheme.created", code=body.code)
    return await get_scheme(db, scheme_id)


async def patch_scheme(db: AsyncSession, caller: Caller, scheme_id: str,
                       body: sch.SchemePatch) -> sch.Scheme:
    current = await get_scheme(db, scheme_id)
    sent = body.model_dump(exclude_unset=True)
    if current.used and set(sent) - {"valid_to", "is_active"}:
        raise ConflictError("This scheme has given benefits. Only its end date and active "
                            "flag can change; end it and create a new one.", code="scheme_in_use")
    merged = sch.SchemeCreate(
        code=current.code, name=body.name if body.name is not None else current.name,
        description=sent.get("description", current.description),
        scheme_type=body.scheme_type or current.scheme_type,
        condition=body.condition or sch.Condition(
            metric=current.condition.metric, min=Decimal(current.condition.min),
            max=Decimal(current.condition.max) if current.condition.max else None),
        benefit=body.benefit or sch.Benefit(
            kind=current.benefit.kind, value=Decimal(current.benefit.value),
            cap=Decimal(current.benefit.cap) if current.benefit.cap else None,
            entitlement_days=current.benefit.entitlement_days),
        period=sent.get("period", current.period),
        valid_from=body.valid_from or dt.date.fromisoformat(current.valid_from),
        valid_to=(sent["valid_to"] if "valid_to" in sent
                  else (dt.date.fromisoformat(current.valid_to) if current.valid_to else None)),
        priority=body.priority if body.priority is not None else current.priority,
        stackable=body.stackable if body.stackable is not None else current.stackable,
        targets=body.targets if body.targets is not None else current.targets)
    terms = _terms(merged)
    problems = domain.problems(terms)
    if problems:
        raise ValidationFailed(fields=problems)
    if body.targets is not None:
        await _check_targets(db, body.targets)
    is_active = body.is_active if body.is_active is not None else current.is_active
    try:
        async with db.begin_nested():
            await db.execute(text(
                "UPDATE scheme SET name = :name, description = :descr, "
                "scheme_type = CAST(:t AS scheme_type), metric = CAST(:m AS scheme_metric), "
                "condition_min = :cmin, condition_max = :cmax, "
                "benefit_kind = CAST(:k AS scheme_benefit_kind), benefit_value = :v, benefit_cap = :cap, "
                "entitlement_days = :days, period = CAST(:per AS scheme_period), valid_from = :vf, "
                "valid_to = :vt, priority = :pr, stackable = :st, is_active = :act, "
                "updated_by = CAST(:u AS uuid) WHERE id = CAST(:s AS uuid)"),
                {"name": merged.name.strip(), "descr": merged.description, "t": merged.scheme_type,
                 "m": merged.condition.metric, "cmin": merged.condition.min,
                 "cmax": merged.condition.max, "k": merged.benefit.kind,
                 "v": merged.benefit.value, "cap": merged.benefit.cap,
                 "days": domain.entitlement_days(terms), "per": merged.period,
                 "vf": merged.valid_from, "vt": merged.valid_to, "pr": merged.priority,
                 "st": merged.stackable, "act": is_active, "u": caller.user_id, "s": scheme_id})
            if body.targets is not None:
                await db.execute(text("DELETE FROM scheme_target WHERE scheme_id = CAST(:s AS uuid)"),
                                 {"s": scheme_id})
                await _write_targets(db, scheme_id, body.targets)
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    ended = (current.is_active and not is_active) or ("valid_to" in sent and sent["valid_to"])
    await _event(db, caller, scheme_id, "scheme.ended" if ended and current.used else "scheme.updated",
                 code=current.code)
    return await get_scheme(db, scheme_id)


async def list_schemes(db: AsyncSession, *, status: str | None = None,
                       scheme_type: str | None = None, q: str | None = None,
                       cursor: str | None = None, limit: int = 50) -> sch.SchemePage:
    limit = max(1, min(limit, _LIMIT))
    where = ["true"]
    params: dict[str, Any] = {"lim": limit + 1, "today": today_ist()}
    if status == "active":
        where.append("s.is_active")
    elif status == "inactive":
        where.append("NOT s.is_active")
    elif status == "current":
        where.append("s.is_active AND s.valid_from <= :today AND (s.valid_to IS NULL OR s.valid_to >= :today)")
    elif status is not None:
        raise ValidationFailed(fields={"status": "active, inactive or current."})
    if scheme_type:
        if scheme_type not in domain.TYPES:
            raise ValidationFailed(fields={"scheme_type": "Unknown scheme type."})
        where.append("s.scheme_type::text = :st")
        params["st"] = scheme_type
    if q:
        where.append("(s.code::text ILIKE :q OR s.name ILIKE :q)")
        params["q"] = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    if cursor:
        at, sid = _decode_cursor(cursor)
        where.append("(s.created_at, s.id) < (:at, CAST(:sid AS uuid))")
        params.update(at=at, sid=sid)
    rows = (await db.execute(text(_SELECT + " WHERE " + " AND ".join(where)
                                  + " ORDER BY s.created_at DESC, s.id DESC LIMIT :lim"), params)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].created_at, str(rows[-1].id))
    return sch.SchemePage(data=[_out(r) for r in rows],
                          meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def _refs(db: AsyncSession, ids: set[str]) -> dict[str, sch.SchemeRef]:
    if not ids:
        return {}
    # SECURITY: the scheme row may be hidden from a partner (a scheme that no longer
    # targets it); the benefit on its own order still names it, by code and name only
    rows = (await db.execute(text(
        "SELECT id, code::text AS code, name FROM scheme_names(CAST(:ids AS uuid[]))"),
        {"ids": list(ids)})).all()
    return {str(r.id): sch.SchemeRef(id=str(r.id), code=r.code, name=r.name) for r in rows}


async def order_preview(db: AsyncSession, order_id: str) -> sch.OrderSchemePreview:
    try:
        # as text, parsed with Decimal: never a float in between (PR 11 review)
        raw: Any = (await db.execute(text("SELECT scheme_order_preview(CAST(:o AS uuid))::text"),
                                {"o": order_id})).scalar_one()
    except DBAPIError as exc:
        raise map_db_error(exc) from exc
    data = json.loads(raw, parse_float=Decimal)
    ids = {d["scheme_id"] for key in ("discounts", "entitlements", "on_delivery") for d in data[key]}
    refs = await _refs(db, ids)
    discounts = [sch.PreviewDiscount(scheme=refs[d["scheme_id"]], basis=_money(d["basis"]),
                                     amount=_money(d["amount"])) for d in data["discounts"]]
    ents = [sch.PreviewEntitlement(entitlement_id=d["entitlement_id"], scheme=refs[d["scheme_id"]],
                                   amount=_money(d["amount"])) for d in data["entitlements"]]
    later = [sch.PreviewOnDelivery(
        scheme=refs[d["scheme_id"]],
        kind="points" if d["kind"] == "order_points" else "next_order_credit",
        points=d.get("points"), basis=_money(d["basis"])) for d in data["on_delivery"]]
    total = (sum((Decimal(x.amount) for x in discounts), Decimal("0"))
             + sum((Decimal(x.amount) for x in ents), Decimal("0")))
    return sch.OrderSchemePreview(discounts=discounts, entitlements=ents, on_delivery=later,
                                  total_benefit=_money(total), payable=_money(data["payable"]))


async def order_benefits(db: AsyncSession, order_id: str,
                         total: Decimal) -> tuple[list[sch.OrderBenefit], str]:
    rows = (await db.execute(text(
        # one submit writes several rows at one instant: the scheme's own order breaks the tie
        "SELECT b.id, b.kind, b.scheme_id, b.amount, b.status, b.applied_at FROM scheme_benefit b "
        "LEFT JOIN scheme_names(ARRAY(SELECT scheme_id FROM scheme_benefit WHERE sales_order_id = CAST(:o AS uuid) "
        "AND scheme_id IS NOT NULL)) n ON n.id = b.scheme_id "
        "WHERE b.sales_order_id = CAST(:o AS uuid) "
        "ORDER BY b.applied_at, b.kind, n.priority NULLS LAST, n.code, b.id"), {"o": order_id})).all()
    refs = await _refs(db, {str(r.scheme_id) for r in rows if r.scheme_id})
    out = [sch.OrderBenefit(id=str(r.id), kind=r.kind,
                            scheme=refs[str(r.scheme_id)] if r.scheme_id else None,
                            amount=_money(r.amount), status=r.status,
                            applied_at=r.applied_at.isoformat()) for r in rows]
    applied = sum((r.amount for r in rows if r.status == "applied"), Decimal("0"))
    return out, _money(total - applied)


async def standing(db: AsyncSession, caller: Caller, scheme_id: str,
                   partner_id: str | None) -> sch.Standing:
    current = await get_scheme(db, scheme_id)
    if current.scheme_type != "period":
        raise ValidationFailed("Only a period scheme has a standing.", code="not_a_period_scheme")
    who = caller.partner_id or partner_id
    if not who:
        raise ValidationFailed(fields={"partner_id": "Required."})
    if not (await db.execute(text("SELECT 1 FROM channel_partner WHERE id = CAST(:p AS uuid)"),
                             {"p": who})).first():
        raise NotFoundError("No such partner.")
    raw: Any = (await db.execute(text("SELECT scheme_standing(CAST(:s AS uuid), CAST(:p AS uuid), :d)::text"),
                            {"s": scheme_id, "p": who, "d": today_ist()})).scalar_one()
    if raw is None:
        raise NotFoundError("The scheme has not started.")
    d = json.loads(raw, parse_float=Decimal)
    return sch.Standing(period_start=d["period_start"], period_end=d["period_end"],
                        metric=d["metric"], achieved=_num(Decimal(str(d["achieved"]))) or "0",
                        min=_num(Decimal(str(d["min"]))) or "0",
                        max=_num(Decimal(str(d["max"]))) if d["max"] is not None else None,
                        qualifies=bool(d["qualifies"]))


async def list_entitlements(db: AsyncSession, *, partner_id: str | None = None,
                            status: str | None = None, cursor: str | None = None,
                            limit: int = 50) -> sch.EntitlementPage:
    limit = max(1, min(limit, _LIMIT))
    where = ["true"]
    params: dict[str, Any] = {"lim": limit + 1}
    if partner_id:
        where.append("e.partner_id = CAST(:p AS uuid)")
        params["p"] = partner_id
    if status:
        if status not in ("available", "consumed", "expired", "reversed"):
            raise ValidationFailed(fields={"status": "available, consumed, expired or reversed."})
        where.append("e.status = :st")
        params["st"] = status
    if cursor:
        at, eid = _decode_cursor(cursor)
        where.append("(e.earned_at, e.id) < (:at, CAST(:eid AS uuid))")
        params.update(at=at, eid=eid)
    rows = (await db.execute(text(
        "SELECT e.*, e.kind::text AS kind_text, c.name AS partner_name, "
        "so.order_no::text AS source_no, co.order_no::text AS consumed_no "
        "FROM scheme_entitlement e JOIN channel_partner c ON c.id = e.partner_id "
        "LEFT JOIN sales_order so ON so.id = e.source_order_id "
        "LEFT JOIN sales_order co ON co.id = e.consumed_order_id "
        "WHERE " + " AND ".join(where) + " ORDER BY e.earned_at DESC, e.id DESC LIMIT :lim"),
        params)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].earned_at, str(rows[-1].id))
    refs = await _refs(db, {str(r.scheme_id) for r in rows})
    return sch.EntitlementPage(data=[sch.Entitlement(
        id=str(r.id), scheme=refs[str(r.scheme_id)],
        partner=sch.PartnerRefLite(id=str(r.partner_id), name=r.partner_name),
        kind=r.kind_text, value=_num(r.value) or "0",
        cap=_money(r.cap) if r.cap is not None else None, status=r.status,
        earned_at=r.earned_at.isoformat(), expires_at=r.expires_at.isoformat(),
        source_order=(sch.OrderRefLite(id=str(r.source_order_id), order_no=r.source_no)
                      if r.source_order_id else None),
        period_start=r.period_start.isoformat() if r.period_start else None,
        period_end=r.period_end.isoformat() if r.period_end else None,
        consumed_order=(sch.OrderRefLite(id=str(r.consumed_order_id), order_no=r.consumed_no)
                        if r.consumed_order_id else None)) for r in rows],
        meta=PageMeta(limit=limit, next_cursor=next_cursor))
