"""Payments (FS-022, ADR-045): receipts, allocations, instalments, the order's
position and the dealer ledger.

Every write is one definer call (migration 031, review B-1); reads run under the
caller's RLS. A dealer never reads a remark or a void reason (question 15.14).
Services never commit.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import payments as domain
from api.errors import ApiError, ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import payments as sch
from api.schemas.leads import PageMeta, UserRef
from api.services.clock import today_ist
from api.services.leads import _decode_cursor, _encode_cursor


def _sqlstate(exc: DBAPIError) -> str:
    return str(getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None) or "")


def _message(exc: DBAPIError) -> str:
    raw = str(exc.orig).split("\n")[0]
    return raw.split(": ", 1)[-1] if ": " in raw else raw


def _map(exc: DBAPIError) -> Exception:
    code = _sqlstate(exc)
    if code == "42501":
        return ForbiddenError("Not permitted.")
    if code == "22023":
        return ValidationFailed(_message(exc))
    if code in domain.SQLSTATE_TO_ERROR:
        status, name = domain.SQLSTATE_TO_ERROR[code]
        cls: type[ApiError] = {404: NotFoundError, 409: ConflictError}.get(status, ValidationFailed)
        return cls(_message(exc), code=name)
    return exc


async def _call(db: AsyncSession, sql: str, params: dict[str, Any]) -> Any:
    try:
        async with db.begin_nested():
            return (await db.execute(text(sql), params)).scalar_one_or_none()
    except DBAPIError as exc:
        mapped = _map(exc)
        if mapped is exc:
            raise
        raise mapped from exc


def _money(v: Decimal) -> str:
    return f"{v:.2f}"


def _portal(caller: Caller) -> bool:
    return caller.partner_id is not None


# ── the order's position ────────────────────────────────────────────────────

async def position(db: AsyncSession, order_id: str) -> sch.OrderPayments | None:
    """Null for a caller without payments.view, as the definer answers."""
    today = today_ist()
    row = (await db.execute(text("SELECT * FROM order_payment_position(CAST(:o AS uuid), :d)"),
                            {"o": order_id, "d": today})).one_or_none()
    if row is None:
        return None
    payable, received, due = Decimal(row.payable), Decimal(row.received), Decimal(row.due)
    sched = (await db.execute(text(
        "SELECT seq, due_on, amount, note FROM payment_schedule WHERE sales_order_id = CAST(:o AS uuid) ORDER BY seq"),
        {"o": order_id})).all()
    instalments = [domain.Instalment(s.seq, s.due_on, s.amount) for s in sched]
    cover = domain.covered(instalments, received)
    receipts = (await db.execute(text(
        "SELECT p.id, p.received_on, p.mode::text AS mode, p.ref_no, a.amount, p.is_short_payment "
        "FROM payment_allocation a JOIN payment p ON p.id = a.payment_id "
        "WHERE a.sales_order_id = CAST(:o AS uuid) AND NOT a.voided ORDER BY p.received_on, p.id"),
        {"o": order_id})).all()
    overdue = domain.overdue_amount(due, received) if payable > 0 else domain.ZERO
    return sch.OrderPayments(
        payable=_money(payable), received=_money(received), balance=_money(domain.balance(payable, received)),
        status=domain.status(payable, received), overdue=overdue > 0, overdue_amount=_money(overdue),
        schedule=[sch.InstalmentOut(seq=s.seq, due_on=s.due_on.isoformat(), amount=_money(s.amount),
                                    note=s.note, covered=c) for s, c in zip(sched, cover, strict=True)],
        receipts=[sch.ReceiptOut(payment_id=str(r.id), received_on=r.received_on.isoformat(), mode=r.mode,
                                 ref_no=r.ref_no, amount=_money(r.amount), is_short_payment=r.is_short_payment)
                  for r in receipts])


async def statuses(db: AsyncSession, order_ids: list[str]) -> dict[str, str | None]:
    """The inbox's `payment_status`, one call per order; the inbox pages are short."""
    out: dict[str, str | None] = {}
    today = today_ist()
    for oid in order_ids:
        row = (await db.execute(text("SELECT * FROM order_payment_position(CAST(:o AS uuid), :d)"),
                                {"o": oid, "d": today})).one_or_none()
        out[oid] = None if row is None else domain.status(Decimal(row.payable), Decimal(row.received))
    return out


# ── receipts ────────────────────────────────────────────────────────────────

_P_SELECT = """SELECT p.*, p.mode::text AS mode_text,
       COALESCE(cp.name::text, payment_partner_name(p.partner_id),
                (SELECT n.name FROM partner_names(ARRAY[p.partner_id]) n)) AS partner_name, eu.full_name AS entered_name,
       vu.full_name AS voided_name,
       COALESCE((SELECT sum(a.amount) FROM payment_allocation a WHERE a.payment_id = p.id AND NOT a.voided), 0) AS allocated
  FROM payment p
  LEFT JOIN channel_partner cp ON cp.id = p.partner_id
  LEFT JOIN app_user eu ON eu.id = p.entered_by
  LEFT JOIN app_user vu ON vu.id = p.voided_by"""


async def _payment(db: AsyncSession, caller: Caller, payment_id: str) -> sch.Payment:
    r = (await db.execute(text(_P_SELECT + " WHERE p.id = CAST(:p AS uuid)"), {"p": payment_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such payment.")
    return await _payment_out(db, caller, r)


async def _payment_out(db: AsyncSession, caller: Caller, r: Any) -> sch.Payment:
    portal = _portal(caller)
    allocs = (await db.execute(text(
        "SELECT a.sales_order_id, a.amount, o.order_no::text AS order_no FROM payment_allocation a "
        "LEFT JOIN sales_order o ON o.id = a.sales_order_id "
        "WHERE a.payment_id = CAST(:p AS uuid) AND NOT a.voided ORDER BY a.created_at, a.id"),
        {"p": str(r.id)})).all()
    out = []
    for a in allocs:
        pos = None if a.order_no is None else await position(db, str(a.sales_order_id))
        out.append(sch.AllocationOut(sales_order=sch.OrderNo(id=str(a.sales_order_id), order_no=a.order_no),
                                     amount=_money(a.amount), order_balance=None if pos is None else pos.balance))
    voided = None
    if r.voided_at is not None:
        voided = sch.Voided(at=r.voided_at.isoformat(),
                            by=None if portal or r.voided_by is None else UserRef(id=str(r.voided_by), full_name=r.voided_name or ""),
                            reason=None if portal else r.void_reason)
    allocated = Decimal(r.allocated)
    return sch.Payment(
        id=str(r.id), partner=None if r.partner_id is None else sch.PartnerName(id=str(r.partner_id), name=r.partner_name or ""),
        mode=r.mode_text, ref_no=r.ref_no, received_on=r.received_on.isoformat(), amount=_money(r.amount),
        allocated=_money(allocated), unallocated=_money(r.amount - allocated if r.voided_at is None else Decimal(0)),
        is_short_payment=r.is_short_payment, remark=None if portal else r.remark,
        entered_by=None if portal else UserRef(id=str(r.entered_by), full_name=r.entered_name or ""),
        entered_at=r.created_at.isoformat(), voided=voided, allocations=out)


def _allocs(items: list[sch.AllocationIn]) -> str:
    seen: set[str] = set()
    for a in items:
        if a.sales_order_id in seen:
            raise ValidationFailed(fields={"allocations": "one row per order"})
        seen.add(a.sales_order_id)
    return json.dumps([{"sales_order_id": a.sales_order_id, "amount": str(a.amount)} for a in items])


async def record(db: AsyncSession, caller: Caller, body: sch.PaymentIn) -> sch.Payment:
    if body.received_on > today_ist() + dt.timedelta(days=1):
        raise ValidationFailed(fields={"received_on": "in the future"})
    payload = {"partner_id": body.partner_id, "mode": body.mode, "ref_no": body.ref_no,
               "received_on": body.received_on.isoformat(), "amount": str(body.amount),
               "is_short_payment": body.is_short_payment, "remark": body.remark,
               "allocations": json.loads(_allocs(body.allocations))}
    pid = await _call(db, "SELECT payment_record(CAST(:p AS jsonb))", {"p": json.dumps(payload)})
    return await _payment(db, caller, str(pid))


async def allocate(db: AsyncSession, caller: Caller, payment_id: str, body: sch.AllocateIn) -> sch.Payment:
    await _call(db, "SELECT payment_allocate(CAST(:p AS uuid), CAST(:a AS jsonb))",
                {"p": payment_id, "a": _allocs(body.allocations)})
    return await _payment(db, caller, payment_id)


async def void(db: AsyncSession, caller: Caller, payment_id: str, body: sch.VoidIn) -> sch.Payment:
    await _call(db, "SELECT payment_void(CAST(:p AS uuid), :r)", {"p": payment_id, "r": body.reason})
    return await _payment(db, caller, payment_id)


async def set_schedule(db: AsyncSession, caller: Caller, order_id: str, body: sch.ScheduleIn) -> sch.OrderPayments:
    rows = [{"due_on": i.due_on.isoformat(), "amount": str(i.amount), "note": i.note} for i in body.instalments]
    await _call(db, "SELECT order_payment_schedule_set(CAST(:o AS uuid), CAST(:r AS jsonb))",
                {"o": order_id, "r": json.dumps(rows)})
    out = await position(db, order_id)
    if out is None:
        raise NotFoundError("No such order.")
    return out


async def list_payments(db: AsyncSession, caller: Caller, *, partner_id: str | None, sales_order_id: str | None,
                        include_voided: bool, limit: int, cursor: str | None) -> sch.PaymentPage:
    where: list[str] = ["TRUE"]
    params: dict[str, Any] = {"lim": limit + 1}
    if partner_id:
        where.append("p.partner_id = CAST(:pt AS uuid)")
        params["pt"] = partner_id
    if sales_order_id:
        where.append("EXISTS (SELECT 1 FROM payment_allocation a WHERE a.payment_id = p.id AND a.sales_order_id = CAST(:o AS uuid))")
        params["o"] = sales_order_id
    if not include_voided:
        where.append("p.voided_at IS NULL")
    if cursor:
        at, pid = _decode_cursor(cursor)
        where.append("(p.created_at, p.id) < (:cat, CAST(:cid AS uuid))")
        params |= {"cat": at, "cid": pid}
    rows = (await db.execute(text(
        _P_SELECT + " WHERE " + " AND ".join(where) + " ORDER BY p.created_at DESC, p.id DESC LIMIT :lim"), params)).all()
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1].created_at, str(page[-1].id)) if len(rows) > limit else None
    return sch.PaymentPage(data=[await _payment_out(db, caller, r) for r in page],
                           meta=PageMeta(limit=limit, next_cursor=next_cursor))


# ── the dealer ledger ───────────────────────────────────────────────────────

async def ledger(db: AsyncSession, caller: Caller, partner_id: str, *, start: dt.date | None,
                 end: dt.date | None) -> sch.Ledger:
    """Orders debit on their approval date (IST) at their total, cancelled never
    (GAP-210); each applied scheme or reward benefit credits on its day (ADR-050);
    live receipts credit their full amount on received_on. Read under the
    caller's RLS: payments for the receipts, sales orders for the debits."""
    # the dealer as the caller reads it, or by name for Accounts (payment_partner_name)
    partner = (await db.execute(text(
        "SELECT CAST(:p AS uuid) AS id, COALESCE((SELECT name::text FROM channel_partner WHERE id = CAST(:p AS uuid)), "
        "payment_partner_name(CAST(:p AS uuid))) AS name"), {"p": partner_id})).one()
    scope = caller.scopes.get("payments")
    if scope not in ("global", "partner_subtree"):
        raise ForbiddenError("The ledger is for Accounts, admin, MD and the dealer itself.",
                             code="ledger_scope")
    if partner.name is None or not (await db.execute(text("SELECT app_has_permission('payments', 'view')"))).scalar_one():
        raise NotFoundError("No such dealer.")
    orders = (await db.execute(text(
        "SELECT o.id::text AS id, o.order_no::text AS order_no, o.total, "
        "(o.approved_at AT TIME ZONE 'Asia/Kolkata')::date AS on_day FROM sales_order o "
        "WHERE o.partner_id = CAST(:p AS uuid) AND o.approved_at IS NOT NULL AND o.status::text <> 'cancelled' "
        "AND o.deleted_at IS NULL"), {"p": partner_id})).all()
    benefits = (await db.execute(text(
        "SELECT b.id::text AS id, b.kind, b.amount, o.order_no::text AS order_no, "
        "(b.applied_at AT TIME ZONE 'Asia/Kolkata')::date AS on_day FROM scheme_benefit b "
        "JOIN sales_order o ON o.id = b.sales_order_id WHERE b.sales_order_id = ANY(CAST(:o AS uuid[])) "
        "AND b.status = 'applied'"), {"o": [o.id for o in orders]})).all() if orders else []
    receipts = (await db.execute(text(
        "SELECT p.id::text AS id, p.mode::text AS mode, p.ref_no, p.amount, p.received_on, "
        "COALESCE((SELECT sum(a.amount) FROM payment_allocation a WHERE a.payment_id = p.id AND NOT a.voided), 0) AS allocated "
        "FROM payment p WHERE p.partner_id = CAST(:p AS uuid) AND p.voided_at IS NULL"), {"p": partner_id})).all()
    entries = [domain.LedgerEntry(o.on_day, "order", o.order_no or "", o.total, None, o.id) for o in orders]
    entries += [domain.LedgerEntry(b.on_day, "benefit",
                                   f"{'Reward points' if b.kind == 'reward_redemption' else 'Scheme'} {b.order_no or ''}".strip(),
                                   None, b.amount, b.id) for b in benefits]
    entries += [domain.LedgerEntry(r.received_on, "receipt", f"{r.mode.upper()} {r.ref_no or ''}".strip(),
                                   None, r.amount, r.id) for r in receipts]
    opening, rows, closing = domain.ledger(entries, start=start, end=end)
    unallocated = sum((Decimal(r.amount) - Decimal(r.allocated) for r in receipts), Decimal(0))
    return sch.Ledger.model_validate({
        "partner": {"id": str(partner.id), "name": partner.name},
        "from": None if start is None else start.isoformat(), "to": None if end is None else end.isoformat(),
        "opening_balance": _money(opening),
        "rows": [{"on": x.entry.on.isoformat(), "kind": x.entry.kind, "ref": x.entry.ref,
                  "debit": None if x.entry.debit is None else _money(x.entry.debit),
                  "credit": None if x.entry.credit is None else _money(x.entry.credit),
                  "balance": _money(x.balance)} for x in rows],
        "closing_balance": _money(closing), "unallocated": _money(unallocated)})
