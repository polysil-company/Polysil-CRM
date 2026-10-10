# ruff: noqa: E501  (field descriptions and embedded SQL)

"""Warranty tracking (FS-046, migration 053). Dates come from SQL (`warranty_end`
is authoritative); the status is read against today in IST. Services never commit."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import warranty as domain
from api.domain.complaints import ist_today
from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import warranty as sch


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _iso(v: dt.date | None) -> str | None:
    return None if v is None else v.isoformat()


def _qty(v: Any) -> str:
    return str(Decimal(v).quantize(Decimal("0.001")))


async def terms(db: AsyncSession) -> list[sch.WarrantyTerm]:
    rows = (await db.execute(text(
        "SELECT t.*, c.code::text AS c_code, c.name AS c_name FROM warranty_term t "
        "LEFT JOIN product_category c ON c.id = t.product_category_id "
        "ORDER BY t.product_category_id IS NOT NULL, c.name, t.effective_from"))).all()
    return [sch.WarrantyTerm(
        id=str(r.id), months=r.months, effective_from=r.effective_from.isoformat(),
        effective_to=_iso(r.effective_to),
        product_category=(sch.CategoryRef(id=str(r.product_category_id), code=r.c_code, name=r.c_name)
                          if r.product_category_id else None)) for r in rows]


async def set_term(db: AsyncSession, body: sch.WarrantyTermIn) -> list[sch.WarrantyTerm]:
    try:
        async with db.begin_nested():
            await db.execute(text("SELECT warranty_term_set(CAST(:c AS uuid), :m, :f)"),
                             {"c": body.product_category_id, "m": body.months, "f": body.effective_from})
    except DBAPIError as exc:
        code = getattr(exc.orig, "sqlstate", None)
        # 23P01: an overlap the lock should prevent, e.g. a backdated row a migration
        # wrote (GAP-282) racing a set; a 409, never a 500 (code review F-1)
        if code in ("WRTEX", "23P01"):
            raise ConflictError("A term already starts that day.", code="term_exists") from exc
        if code == "WRTPA":
            raise ValidationFailed(fields={"effective_from": "from tomorrow on"}) from exc
        if code in ("WRTNC", "22P02"):
            raise ValidationFailed(fields={"product_category_id": "no such category"}) from exc
        if code == "42501":
            raise ForbiddenError("masters.edit is required.") from exc
        raise
    return await terms(db)


async def order_warranty(db: AsyncSession, order_id: str) -> sch.OrderWarranty:
    """Four statements whatever the line count (edge EC-15), each under the
    caller's RLS, as GET /orders/{id}."""
    order = (await db.execute(text(
        # GAP-279: a replacement's dispatch starts a full period; the tab names what it replaces
        "SELECT o.id, o.order_no::text AS order_no, o.order_type::text AS order_type, "
        "  (SELECT c.id FROM complaint_remedy r JOIN complaint c ON c.id = r.complaint_id "
        "    WHERE r.sales_order_id = o.id AND r.kind = 'replacement' ORDER BY r.chosen_at LIMIT 1) AS rc_id "
        "FROM sales_order o WHERE o.id = CAST(:o AS uuid) AND o.deleted_at IS NULL"),
        {"o": order_id})).one_or_none()
    if order is None:
        raise NotFoundError("No such order.")
    lines = (await db.execute(text(
        "SELECT id, product_id, description, qty FROM order_line "
        "WHERE sales_order_id = CAST(:o AS uuid) ORDER BY line_no"), {"o": order_id})).all()
    shipped = (await db.execute(text(
        "SELECT x.*, warranty_end(x.start_day, x.months) AS end_day FROM ("
        "  SELECT dl.order_line_id, ol.product_id, d.id AS dispatch_id, d.dispatch_no, dl.qty, d.dispatched_at, d.dc_date, "
        "    COALESCE(d.dc_date, (d.dispatched_at AT TIME ZONE 'Asia/Kolkata')::date) AS start_day, "
        "    warranty_months(ol.product_id, COALESCE(d.dc_date, (d.dispatched_at AT TIME ZONE 'Asia/Kolkata')::date)) AS months "
        "  FROM dispatch d JOIN dispatch_line dl ON dl.dispatch_id = d.id "
        "  JOIN order_line ol ON ol.id = dl.order_line_id "
        "  WHERE d.sales_order_id = CAST(:o AS uuid) AND d.voided_at IS NULL) x "
        "ORDER BY x.dispatched_at, x.dispatch_id"), {"o": order_id})).all()
    claims = (await db.execute(text(
        "SELECT c.id, c.complaint_no::text AS complaint_no, c.status::text AS status, cl.product_id, "
        "  cl.defective_qty, (c.first_submitted_at AT TIME ZONE 'Asia/Kolkata')::date AS raised_on "
        "FROM complaint c JOIN complaint_line cl ON cl.complaint_id = c.id "
        "WHERE (c.sales_order_id = CAST(:o AS uuid) OR c.id = CAST(:rc AS uuid)) "
        "  AND c.status::text NOT IN ('draft', 'cancelled') AND c.deleted_at IS NULL "
        "ORDER BY c.first_submitted_at, c.id"),
        {"o": order_id, "rc": str(order.rc_id) if order.rc_id else None})).all()

    today = ist_today(_now())
    # rule 10: one anchor per product, the latest-ending live dispatch across its lines.
    # GAP-276: no serials, so the unit a complaint is about is unknown
    anchor: dict[str, Any] = {}
    for s in shipped:
        key, best = str(s.product_id), anchor.get(str(s.product_id))
        if best is None or _later(s, best):
            anchor[key] = s
    out = []
    for ln in lines:
        mine = [s for s in shipped if s.order_line_id == ln.id]
        # the line's status from its own dispatches (code review F-3); claims compare with
        # the product's anchor, as the complaint page does
        own = None
        for s in mine:
            if own is None or _later(s, own):
                own = s
        a = anchor.get(str(ln.product_id))
        out.append(sch.WarrantyLine(
            order_line_id=str(ln.id),
            product=sch.WarrantyProduct(id=str(ln.product_id), description=ln.description),
            qty_ordered=_qty(ln.qty), qty_dispatched=_qty(sum((s.qty for s in mine), Decimal(0))),
            dispatches=[sch.WarrantyDispatch(
                dispatch_id=str(s.dispatch_id), dispatch_no=s.dispatch_no, qty=_qty(s.qty),
                start=s.start_day.isoformat(), start_basis="dc_date" if s.dc_date else "dispatched_at",
                end=_iso(s.end_day), months=s.months,
                status=domain.status_on(s.months, s.end_day, today)) for s in mine],
            status=domain.status_on(own.months, own.end_day, today) if own is not None else "not_dispatched",
            claims=[sch.Claim(
                complaint_id=str(c.id), complaint_no=c.complaint_no, status=c.status,
                raised_on=_iso(c.raised_on), defective_qty=_qty(c.defective_qty),
                warranty_status=(domain.claim_status(a.months, a.end_day, c.raised_on or today)
                                 if a is not None else "unknown"))
                for c in claims if c.product_id == ln.product_id]))
    return sch.OrderWarranty(
        order_id=str(order.id), order_no=order.order_no, order_type=order.order_type,
        replacement_for=(next((sch.ComplaintRef(complaint_id=str(c.id), complaint_no=c.complaint_no)
                               for c in claims if c.id == order.rc_id), None)
                         if order.rc_id else None),
        lines=out)


def _later(a: Any, b: Any) -> bool:
    """Rule 10's order, the same as complaint_warranty()'s ORDER BY: a dated end beats
    none (end DESC NULLS LAST), a later end wins, then the later start."""
    if a.end_day != b.end_day:
        if a.end_day is None or b.end_day is None:
            return b.end_day is None
        return bool(a.end_day > b.end_day)
    return bool(a.start_day > b.start_day)


async def complaint_lines(db: AsyncSession, complaint_id: str) -> dict[str, sch.LineWarranty]:
    """Each complaint line's warranty, keyed by line id, from the definer (edge EC-1).
    GAP-277: shown only; an expired line refuses nothing."""
    rows = (await db.execute(text("SELECT * FROM complaint_warranty(CAST(:c AS uuid))"),
                             {"c": complaint_id})).all()
    return {str(r.line_id): sch.LineWarranty(
        status=domain.claim_status(r.months, r.end_day, r.raised_on) if r.start_day else "unknown",
        start=_iso(r.start_day), end=_iso(r.end_day), months=r.months, basis=r.basis) for r in rows}
