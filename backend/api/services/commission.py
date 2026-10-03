# ruff: noqa: E501  (embedded SQL)

"""Dealer commission and TOD (FS-033). Every write is a definer in migration 037;
this service maps its refusals and shapes the reads. Services never commit."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import commission as sch
from api.schemas.leads import PageMeta
from api.services.leads import _decode_cursor, _encode_cursor
from api.services.orders import _pg_text, _sqlstate

_LIMIT = 100
_ERRORS: dict[str, tuple[int, str]] = {
    "COMNC": (409, "not_closed"), "COMNP": (422, "no_partner"), "COMNR": (422, "no_rate"),
    "COMEX": (409, "commission_exists"), "COMSC": (409, "status_changed"),
    "COMVL": (422, "validation_error"), "APRRM": (422, "remark_required"),
}


def _db_error(exc: DBAPIError) -> Exception:
    code = _sqlstate(exc) or ""
    msg = _pg_text(exc).split("\n", 1)[0]
    if code in ("COMNF", "SAPNF"):
        return NotFoundError("No such commission or application.")
    if code == "42501":
        if "self_approval" in msg:
            return ForbiddenError("You cannot decide on a commission you recorded.", code="own_decision")
        return ForbiddenError("Not permitted.")
    if code in _ERRORS:
        status, api_code = _ERRORS[code]
        if status == 409:
            return ConflictError(msg, code=api_code)
        return ValidationFailed(msg, code=api_code)
    return exc


async def _call(db: AsyncSession, sql: str, params: dict[str, Any]) -> Any:
    try:
        async with db.begin_nested():
            return (await db.execute(text(sql), params)).scalar_one_or_none()
    except DBAPIError as exc:
        raise _db_error(exc) from exc


def _m(v: Any) -> str | None:
    return None if v is None else format(Decimal(v).quantize(Decimal("0.01")), "f")


def _p(v: Any) -> str:
    return format(Decimal(v).normalize(), "f")


async def preview(db: AsyncSession, app_id: str) -> sch.Preview:
    raw: Any = await _call(db, "SELECT commission_preview(CAST(:a AS uuid))", {"a": app_id})
    d = raw if isinstance(raw, dict) else json.loads(raw)
    name = (await db.execute(text("SELECT name FROM channel_partner WHERE id = CAST(:p AS uuid)"),
                             {"p": d["partner_id"]})).scalar_one_or_none()
    return sch.Preview(partner=sch.Ref(id=d["partner_id"], name=name),
                       cost_excl_gst=_m(d["cost_excl_gst"]) or "0.00", a_plus_b=_m(d.get("a_plus_b")),
                       installation=_m(d["installation"]) or "0.00",
                       commission_pct=_p(d["commission_pct"]) if d.get("commission_pct") is not None else None,
                       tod_pct=_p(d["tod_pct"]) if d.get("tod_pct") is not None else None,
                       rate_id=d.get("rate_id"))


_SELECT = """
SELECT c.*, a.application_no::text AS application_no, a.reg_no::text AS reg_no,
       p.name AS partner_name, ru.full_name AS recorder_name, du.full_name AS decider_name
  FROM dealer_commission c
  JOIN subsidy_application a ON a.id = c.application_id
  LEFT JOIN channel_partner p ON p.id = c.partner_id
  LEFT JOIN app_user ru ON ru.id = c.recorded_by
  LEFT JOIN app_user du ON du.id = c.decided_by"""


def _out(r: Any) -> sch.Commission:
    return sch.Commission(
        id=str(r.id), application=sch.AppRef(id=str(r.application_id), application_no=r.application_no,
                                              reg_no=r.reg_no),
        partner=sch.Ref(id=str(r.partner_id), name=r.partner_name), status=r.status,
        cost_excl_gst=_m(r.cost_excl_gst) or "0.00", a_plus_b=_m(r.a_plus_b),
        gi_fitting=_m(r.gi_fitting) or "0.00", pvc_hdpe_fitting=_m(r.pvc_hdpe_fitting) or "0.00",
        installation=_m(r.installation) or "0.00", commission_base=_m(r.commission_base) or "0.00",
        commission_pct=_p(r.commission_pct), commission_amount=_m(r.commission_amount) or "0.00",
        tod_base=_m(r.tod_base) or "0.00", tod_pct=_p(r.tod_pct), tod_amount=_m(r.tod_amount) or "0.00",
        total=_m(r.total) or "0.00", remark=r.remark,
        recorded_by=sch.Ref(id=str(r.recorded_by), name=r.recorder_name), recorded_at=r.recorded_at.isoformat(),
        decided_by=sch.Ref(id=str(r.decided_by), name=r.decider_name) if r.decided_by else None,
        decided_at=r.decided_at.isoformat() if r.decided_at else None, decision_remark=r.decision_remark,
        paid_on=r.paid_on.isoformat() if r.paid_on else None, payment_reference=r.payment_reference)


async def get(db: AsyncSession, commission_id: str) -> sch.Commission:
    r = (await db.execute(text(_SELECT + " WHERE c.id = CAST(:i AS uuid)"), {"i": commission_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such commission.")
    return _out(r)


async def live_for(db: AsyncSession, app_id: str) -> sch.Commission:
    r = (await db.execute(text(_SELECT + " WHERE c.application_id = CAST(:a AS uuid) AND c.status <> 'cancelled'"),
                          {"a": app_id})).one_or_none()
    if r is None:
        raise NotFoundError("No commission recorded.")
    return _out(r)


async def record(db: AsyncSession, app_id: str, body: sch.CommissionIn) -> sch.Commission:
    installation = body.installation
    if installation is None:
        installation = Decimal((await preview(db, app_id)).installation)
    cid = await _call(db, "SELECT commission_record(CAST(:a AS uuid), :gi, :pvc, :inst, :tod, :r)",
                      {"a": app_id, "gi": body.gi_fitting, "pvc": body.pvc_hdpe_fitting, "inst": installation,
                       "tod": body.tod_base, "r": body.remark})
    return await get(db, str(cid))


async def decide(db: AsyncSession, commission_id: str, action: str, remark: str | None = None,
                 paid_on: Any = None, reference: str | None = None) -> sch.Commission:
    await get(db, commission_id)
    await _call(db, "SELECT commission_decide(CAST(:i AS uuid), :a, :r, :d, :ref)",
                {"i": commission_id, "a": action, "r": remark, "d": paid_on, "ref": reference})
    return await get(db, commission_id)


async def list_commissions(db: AsyncSession, *, status: str | None = None, partner_id: str | None = None,
                           paid_from: str | None = None, paid_to: str | None = None,
                           cursor: str | None = None, limit: int = 50) -> sch.CommissionPage:
    limit = max(1, min(limit, _LIMIT))
    where = ["true"]
    params: dict[str, Any] = {"lim": limit + 1}
    if status:
        where.append("c.status = ANY(CAST(:st AS text[]))")
        params["st"] = [s.strip() for s in status.split(",") if s.strip()]
    if partner_id:
        where.append("c.partner_id = CAST(:p AS uuid)")
        params["p"] = partner_id
    if paid_from:
        where.append("c.paid_on >= CAST(:pf AS date)")
        params["pf"] = paid_from
    if paid_to:
        where.append("c.paid_on <= CAST(:pt AS date)")
        params["pt"] = paid_to
    if cursor:
        at, cid = _decode_cursor(cursor)
        where.append("(c.recorded_at, c.id) < (:at, CAST(:cid AS uuid))")
        params.update(at=at, cid=cid)
    try:
        rows = (await db.execute(text(_SELECT + " WHERE " + " AND ".join(where)
                                      + " ORDER BY c.recorded_at DESC, c.id DESC LIMIT :lim"), params)).all()
    except DBAPIError as exc:
        raise ValidationFailed(fields={"paid_from": "ISO dates."}) from exc
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].recorded_at, str(rows[-1].id))
    return sch.CommissionPage(data=[_out(r) for r in rows], meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def list_rates(db: AsyncSession, scheme: str) -> list[sch.Rate]:
    rows = (await db.execute(text(
        "SELECT r.*, s.code::text AS scheme_code, p.name AS partner_name FROM commission_rate r "
        "JOIN subsidy_scheme s ON s.id = r.scheme_id LEFT JOIN channel_partner p ON p.id = r.partner_id "
        "WHERE s.code = :s ORDER BY r.effective_from DESC, r.created_at DESC"), {"s": scheme})).all()
    return [sch.Rate(id=str(r.id), scheme=r.scheme_code, system_type=r.system_type, partner_type=r.partner_type,
                     partner=sch.Ref(id=str(r.partner_id), name=r.partner_name) if r.partner_id else None,
                     commission_pct=_p(r.commission_pct), tod_pct=_p(r.tod_pct),
                     effective_from=r.effective_from.isoformat()) for r in rows]


async def add_rate(db: AsyncSession, user_id: str, body: sch.RateIn) -> sch.Rate:
    sid = (await db.execute(text("SELECT id FROM subsidy_scheme WHERE code = :s"), {"s": body.scheme})).scalar_one_or_none()
    if sid is None:
        raise ValidationFailed(fields={"scheme": "Unknown scheme."})
    if body.partner_id and (await db.execute(text("SELECT 1 FROM channel_partner WHERE id = CAST(:p AS uuid)"),
                                             {"p": body.partner_id})).first() is None:
        raise ValidationFailed(fields={"partner_id": "No such partner in your scope."})
    try:
        async with db.begin_nested():
            rid = (await db.execute(text(
                "INSERT INTO commission_rate (scheme_id, system_type, partner_type, partner_id, commission_pct, "
                "tod_pct, effective_from, created_by) VALUES (CAST(:s AS uuid), :st, :pt, CAST(:p AS uuid), :c, :t, "
                ":f, CAST(:u AS uuid)) RETURNING id"),
                {"s": str(sid), "st": body.system_type, "pt": body.partner_type, "p": body.partner_id,
                 "c": body.commission_pct, "t": body.tod_pct, "f": body.effective_from, "u": user_id})).scalar_one()
    except IntegrityError as exc:
        raise ConflictError("A rate for the same scope starts that day.", code="rate_exists") from exc
    return next(r for r in await list_rates(db, body.scheme) if r.id == str(rid))
