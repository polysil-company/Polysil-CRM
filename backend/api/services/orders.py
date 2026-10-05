"""Sales orders (FS-011): every transaction.

An order prices through the one pipeline (`pricing.price_document`), like a
quotation: every save and the submit re-resolve, and a difference from what was
shown is `409 rate_changed`, never a silent repricing (rule 1). Rates resolve at
the order's price date; the HSN, the GST slab and the seller registration at
today's date, because tax follows the date of supply (rule 3).

**The database owns every state change.** `app_role` may write only the columns a
draft edits (migration 013's column grants), so submit, cancel, delete, the
quotation claim and every approval and dispatch step are definer calls. This
module prices, checks what the service checks first, calls the definer, and maps
its refusal. Every mutation takes the order row first (rule 12); no path here
locks a lead (rule 15).

Nothing here makes a network call.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, scope_predicate
from api.config import Settings
from api.domain import orders as domain
from api.domain.identity import MobileError, normalise_mobile
from api.domain.pricing.types import PricedLine
from api.errors import (
    ApiError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailed,
)
from api.schemas import orders as sch
from api.schemas.leads import (
    OrgUnitRef,
    PageMeta,
    TerritoryRef,
    TimelineEvent,
    TimelinePage,
    UserRef,
)
from api.schemas.quotations import PdfLink, QuotationLineIn, Totals
from api.schemas.stock import WarehouseRef
from api.services import approval_view, people, pricing
from api.services import payments as payments_service
from api.services import stock as stock_service
from api.services.clock import IST, today_ist
from api.services.leads import _capped_total, _decode_cursor, _encode_cursor, _route
from api.services.pricing import LineSpec, PricedContext, _rate, _s
from api.services.quotations import _STORAGE_DOWN
from api.storage import Storage

log = structlog.get_logger(__name__)

_ORDERS = SPECS["sales_orders"]
_MAX_LIMIT = 100
_UUID = sa.Uuid()
_TS = sa.DateTime(timezone=True)
order_t = sa.table(
    "sales_order",
    sa.column("id", _UUID), sa.column("created_at", _TS), sa.column("status"),
    sa.column("order_type"), sa.column("lead_id", _UUID), sa.column("owner_user_id", _UUID),
    sa.column("owner_org_unit_id", _UUID), sa.column("territory_id", _UUID),
    sa.column("partner_id", _UUID), sa.column("deleted_at", _TS), sa.column("party_name"),
    sa.column("party_mobile"), sa.column("order_no"),
)

# The seller block is the master while draft and the row's snapshot once
# submitted, by status (FS-005 F-5). People and the lead are RLS-filtered LEFT
# JOINs: null when the caller cannot see them (FS-011 4).
_O_SELECT = """
SELECT o.*, o.status::text AS status_text, o.order_type::text AS type_text,
       o.payment_terms::text AS terms_text,
       l.inquiry_no AS lead_inquiry_no,
       cp.name AS partner_name, cp.partner_type::text AS partner_type,
       ow.full_name AS owner_name, ou.name AS owner_org_unit_name,
       t.name AS territory_name, t.level::text AS territory_level,
       pt.name AS pos_name, pt.level::text AS pos_level,
       CASE WHEN o.status = 'draft' THEN sg.gstin::text ELSE o.seller_gstin_no::text END AS s_gstin,
       CASE WHEN o.status = 'draft' THEN sg.legal_name ELSE o.seller_legal_name END AS s_name,
       CASE WHEN o.status = 'draft' THEN sg.address ELSE o.seller_address END AS s_address,
       CASE WHEN o.status = 'draft' THEN sst.code::text ELSE o.seller_state_code END AS s_state
  FROM sales_order o
  JOIN org_unit ou ON ou.id = o.owner_org_unit_id
  JOIN territory t ON t.id = o.territory_id
  JOIN territory pt ON pt.id = o.place_of_supply_territory_id
  LEFT JOIN lead l ON l.id = o.lead_id
  LEFT JOIN channel_partner cp ON cp.id = o.partner_id
  LEFT JOIN app_user ow ON ow.id = o.owner_user_id
  LEFT JOIN seller_gstin sg ON sg.id = o.seller_gstin_id
  LEFT JOIN territory sst ON sst.id = sg.state_territory_id
"""

# a line with what has left against it (live dispatches only)
_LINE_SELECT = """
SELECT l.*, COALESCE((SELECT sum(dl.qty) FROM dispatch_line dl
                        JOIN dispatch d ON d.id = dl.dispatch_id
                       WHERE dl.order_line_id = l.id AND d.voided_at IS NULL), 0) AS sent
  FROM order_line l WHERE l.sales_order_id = CAST(:o AS uuid) ORDER BY l.line_no
"""


# ── small helpers ────────────────────────────────────────────────────────────

def _iso(v: Any) -> str | None:
    return None if v is None else v.isoformat()


def _money(v: Any) -> str:
    return f"{Decimal(v):.2f}"


def _qty(v: Any) -> str:
    return f"{Decimal(v):.3f}"


def _sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _pg_text(exc: DBAPIError) -> str:
    return str(getattr(exc.orig, "args", [""])[0] or exc.orig)


def map_db_error(exc: DBAPIError) -> Exception:
    """A definer's or a trigger's refusal, as the API says it (FS-011 4). An
    unknown SQLSTATE is re-raised: a CHECK failing is a server bug and must show
    as a 500 (PR #10 review)."""
    code = _sqlstate(exc) or ""
    msg = _pg_text(exc)
    if code in ("40P01", "40001"):
        # a deadlock or serialization abort: nothing was written, the same request can be retried
        return ConflictError("Someone else changed this at the same moment. Try again.",
                             code="try_again")
    if code == "42501":
        if "self_approval" in msg:
            return ForbiddenError("You cannot decide on your own request.", code="self_approval")
        if "not_your_step" in msg:
            return ForbiddenError("This step is not yours to decide.", code="not_your_step")
        return ForbiddenError("Not permitted on this document.")
    if code == "23514" and ("submitted order cannot change" in msg or "cannot move from" in msg
                            or "lines of a submitted order" in msg):
        return ConflictError("Only a draft can be changed.", code="order_not_draft")
    if code in domain.SQLSTATE_TO_ERROR:
        status, api_code = domain.SQLSTATE_TO_ERROR[code]
        sentence = msg.split("\n", 1)[0]
        if status == 404:
            return NotFoundError("No such document.")
        if status == 409:
            return ConflictError(sentence, code=api_code)
        return ValidationFailed(sentence, code=api_code)
    return exc


async def _call(db: AsyncSession, sql: str, params: dict[str, Any]) -> Any:
    try:
        return (await db.execute(text(sql), params)).scalar_one_or_none()
    except DBAPIError as exc:
        raise map_db_error(exc) from exc


async def _emit(db: AsyncSession, *, order_id: Any, lead_id: Any, kind: str, actor_id: str,
                **payload: Any) -> None:
    """An order event: no money in any payload (FS-005 rule 17)."""
    name = (await db.execute(text(
        "SELECT full_name FROM app_user WHERE id = (SELECT app_current_user_id())"))
    ).scalar_one_or_none()
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('sales_order', CAST(:o AS uuid), CAST(:l AS uuid), :k, CAST(:me AS uuid), "
        "CAST(:p AS jsonb))"),
        {"o": str(order_id), "l": str(lead_id) if lead_id else None, "k": kind,
         "me": actor_id, "p": json.dumps({"actor_name": name or "", **payload})})


async def _lock(db: AsyncSession, order_id: str) -> Any:
    """The order row, locked, as the caller sees it (rule 12)."""
    row = (await db.execute(text(
        "SELECT id, status::text AS status, lead_id, partner_id, place_of_supply_territory_id, "
        "seller_gstin_id, price_effective_date, territory_id, owner_org_unit_id, total, order_no "
        "FROM sales_order WHERE id = CAST(:o AS uuid) AND deleted_at IS NULL FOR UPDATE"),
        {"o": order_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such order.")
    return row


def _expect(row: Any, expected: str | None) -> None:
    if expected and expected != row.status:
        raise ConflictError(f"The order is now {row.status}.", code="status_changed",
                            fields={"status": row.status})


def _must_be_draft(row: Any) -> None:
    if row.status != "draft":
        raise ConflictError("Only a draft can be changed.", code="order_not_draft",
                            fields={"status": row.status})


def _check_type(order_type: str) -> None:
    if order_type not in domain.TYPES_ACCEPTED:
        raise ValidationFailed(f"{order_type} orders are not built yet: "
                               f"{domain.TYPE_BLOCKED_ON[order_type]}.",
                               code="order_type_unsupported", fields={"order_type": order_type})


def _party_values(p: sch.OrderParty) -> dict[str, Any]:
    try:
        mobile = normalise_mobile(p.mobile) if p.mobile else None
    except MobileError as exc:   # a 422 on the field, never a 500 (PR 11 review)
        raise ValidationFailed(fields={"party.mobile": str(exc)}) from exc
    return {"pn": p.name, "pm": mobile,
            "pa": p.address, "pg": p.gstin.upper() if p.gstin else None}


async def _linked_quotations(db: AsyncSession, order_id: str) -> list[str]:
    return [str(r[0]) for r in (await db.execute(text(
        "SELECT quotation_id FROM order_quotation WHERE sales_order_id = CAST(:o AS uuid) "
        "AND released_at IS NULL"), {"o": order_id})).all()]


# ── pricing ──────────────────────────────────────────────────────────────────

async def _price(db: AsyncSession, *, partner_id: str | None, pos: str, seller: str | None,
                 as_of: dt.date | None, specs: list[LineSpec], existing: bool,
                 submitting: bool = False) -> PricedContext:
    """Rates at the price date, tax at today (rule 3)."""
    try:
        return await pricing.price_document(
            db, partner_id=partner_id, place_of_supply_territory_id=pos, seller_gstin_id=seller,
            as_of=as_of, lines=specs, existing=existing, tax_as_of=today_ist())
    except ValidationFailed as exc:
        if exc.fields and "as_of" in exc.fields:
            exc.fields = {("price_effective_date" if k == "as_of" else k): v
                          for k, v in exc.fields.items()}
        raise
    except NotFoundError as exc:
        # the seller registration no longer in force today (plan review R-1)
        if submitting or seller is not None:
            raise ValidationFailed("The seller registration on this order is no longer in force.",
                                   code="seller_registration_ended",
                                   fields={"seller_gstin_id": seller or ""}) from exc
        raise


def _compare_preview(lines: list[QuotationLineIn], ctx: PricedContext) -> None:
    fields: dict[str, str] = {}
    for i, (ln, p) in enumerate(zip(lines, ctx.document.lines, strict=True)):
        if ln.price_list_item_id and ln.price_list_item_id != p.rate.price_list_item_id:
            fields[f"lines[{i}].rate"] = f"now {_s(p.rate.rate)}"
        if ln.gst_rate_id and ln.gst_rate_id != p.tax.gst_rate_id:
            fields[f"lines[{i}].gst_slab"] = f"now {_rate(p.tax.slab)}"
    if fields:
        raise ConflictError("Prices or tax changed since the preview. Review the new figures "
                            "and save again.", code="rate_changed", fields=fields)


_MONEY = ("gross", "discount", "taxable", "cgst", "sgst", "igst", "total")


def _compare_stored(stored: list[Any], ctx: PricedContext) -> None:
    """At submit: the stored lines against a fresh resolution, ids and every
    printed figure (FS-005 9.7 A-1)."""
    fields: dict[str, str] = {}
    for i, (row, p) in enumerate(zip(stored, ctx.document.lines, strict=True)):
        if str(row.price_list_item_id) != p.rate.price_list_item_id:
            fields[f"lines[{i}].rate"] = f"{_s(row.rate)} -> {_s(p.rate.rate)}"
        if str(row.gst_rate_id) != p.tax.gst_rate_id:
            fields[f"lines[{i}].gst_slab"] = f"{_rate(row.gst_slab)} -> {_rate(p.tax.slab)}"
        moved = [f for f in _MONEY if Decimal(getattr(row, f)) != getattr(p.money, f)]
        if moved:
            fields[f"lines[{i}].tax"] = ", ".join(
                f"{f} {_s(getattr(row, f))} -> {_s(getattr(p.money, f))}" for f in moved)
    if fields:
        raise ConflictError("Prices or tax changed since this order was saved. Review the new "
                            "figures and save again.", code="rate_changed", fields=fields)


def _line_row(order_id: str, n: int, p: PricedLine, snap: Any | None,
              source: str | None) -> dict[str, Any]:
    steps = list(p.money.steps) + [None] * (3 - len(p.money.steps))
    s1, s2, s3 = steps[:3]
    zero = Decimal("0")
    return {
        "o": order_id, "n": n, "product": p.product.id,
        "desc": snap.description if snap is not None else p.product.description,
        "hsn": snap.hsn_code if snap is not None else p.tax.hsn_code,
        "uom": snap.uom if snap is not None else p.product.uom_code,
        "dec": p.product.uom_decimals, "qty": p.qty, "rate": p.rate.rate,
        "pl": p.rate.price_list.id, "pli": p.rate.price_list_item_id, "gr": p.tax.gst_rate_id,
        "gross": p.money.gross,
        "d1p": s1.pct if s1 else zero, "d1a": s1.amount if s1 else zero,
        "a1": s1.after if s1 else p.money.gross,
        "d2p": s2.pct if s2 else zero, "d2a": s2.amount if s2 else zero,
        "a2": s2.after if s2 else (s1.after if s1 else p.money.gross),
        "d3p": s3.pct if s3 else zero, "d3a": s3.amount if s3 else zero,
        "disc": p.money.discount, "taxable": p.money.taxable, "slab": p.tax.slab,
        "cr": p.money.cgst_rate, "sr": p.money.sgst_rate, "ir": p.money.igst_rate,
        "cgst": p.money.cgst, "sgst": p.money.sgst, "igst": p.money.igst, "total": p.money.total,
        "prov": list(p.provisional_fields), "src": source,
    }


_LINE_INSERT = text("""
    INSERT INTO order_line (sales_order_id, line_no, product_id, description, hsn_code, uom,
        uom_decimals, qty, rate, price_list_id, price_list_item_id, gst_rate_id, gross,
        discount_pct, discount1_amt, after_discount1, discount2_pct, discount2_amt,
        after_discount2, discount3_pct, discount3_amt, discount, taxable, gst_slab,
        cgst_rate, sgst_rate, igst_rate, cgst, sgst, igst, total, provisional_fields,
        source_quotation_line_id)
    VALUES (CAST(:o AS uuid), :n, CAST(:product AS uuid), :desc, :hsn, :uom, :dec, :qty, :rate,
        CAST(:pl AS uuid), CAST(:pli AS uuid), CAST(:gr AS uuid), :gross,
        :d1p, :d1a, :a1, :d2p, :d2a, :a2, :d3p, :d3a, :disc, :taxable, :slab,
        :cr, :sr, :ir, :cgst, :sgst, :igst, :total, CAST(:prov AS text[]),
        CAST(:src AS uuid))
""")


async def _write_lines(db: AsyncSession, order_id: str, ctx: PricedContext,
                       snaps: list[Any] | None = None, sources: list[str | None] | None = None
                       ) -> None:
    try:
        await db.execute(text("DELETE FROM order_line WHERE sales_order_id = CAST(:o AS uuid)"),
                         {"o": order_id})
        for i, p in enumerate(ctx.document.lines):
            await db.execute(_LINE_INSERT, _line_row(
                order_id, i + 1, p, snaps[i] if snaps else None,
                sources[i] if sources else None))
    except DBAPIError as exc:
        raise map_db_error(exc) from exc


async def _write_figures(db: AsyncSession, order_id: str, ctx: PricedContext,
                         caller: Caller) -> None:
    t = ctx.document.totals
    lists = {p.rate.price_list.id for p in ctx.document.lines}
    try:
        await db.execute(text("""
            UPDATE sales_order SET seller_gstin_id = CAST(:sg AS uuid),
                place_of_supply_state_id = CAST(:ps AS uuid), intra_state = :intra,
                price_effective_date = :day, price_list_id = CAST(:pl AS uuid),
                gross = :gross, discount = :disc, taxable = :taxable, cgst = :cgst, sgst = :sgst,
                igst = :igst, total = :total, is_provisional = :prov, updated_by = CAST(:me AS uuid)
            WHERE id = CAST(:o AS uuid)"""),
            {"sg": ctx.seller_gstin_id, "ps": ctx.place_of_supply_state_id,
             "intra": ctx.intra_state, "day": ctx.as_of,
             "pl": next(iter(lists)) if len(lists) == 1 else None,
             "gross": t.gross, "disc": t.discount, "taxable": t.taxable, "cgst": t.cgst,
             "sgst": t.sgst, "igst": t.igst, "total": t.total,
             "prov": any(p.provisional_fields for p in ctx.document.lines),
             "me": caller.user_id, "o": order_id})
    except DBAPIError as exc:
        raise map_db_error(exc) from exc


def _specs(rows: list[Any]) -> list[LineSpec]:
    return [LineSpec(product_id=str(r.product_id), qty=Decimal(r.qty),
                     discounts=(Decimal(r.discount_pct), Decimal(r.discount2_pct),
                                Decimal(r.discount3_pct))) for r in rows]


async def _stored(db: AsyncSession, order_id: str) -> list[Any]:
    return list((await db.execute(text(
        "SELECT * FROM order_line WHERE sales_order_id = CAST(:o AS uuid) ORDER BY line_no"),
        {"o": order_id})).all())


# ── reads ────────────────────────────────────────────────────────────────────

def _is_portal(caller: Caller) -> bool:
    return caller.partner_id is not None


async def _approval(db: AsyncSession, order_id: str, portal: bool,
                    request_id: str | None = None) -> tuple[sch.Approval | None, Any]:
    """The named request of the order, or its latest."""
    return await approval_view.load(db, "sales_order", order_id, portal, request_id)


async def _dispatches(db: AsyncSession, order_id: str, portal: bool = False
                      ) -> list[sch.Dispatch]:
    rows = (await db.execute(text(
        "SELECT d.*, u.full_name, o.order_no::text AS order_no, o.party_name, "
        "w.code::text AS w_code, w.name AS w_name FROM dispatch d "
        "JOIN sales_order o ON o.id = d.sales_order_id "
        "LEFT JOIN warehouse w ON w.id = d.warehouse_id "
        "LEFT JOIN app_user u ON u.id = d.dispatched_by "
        "WHERE d.sales_order_id = CAST(:o AS uuid) ORDER BY d.created_at, d.dispatch_no"),
        {"o": order_id})).all()
    return await _with_lines(db, rows, portal)


async def _with_lines(db: AsyncSession, rows: Sequence[Any], portal: bool) -> list[sch.Dispatch]:
    if not rows:
        return []
    lines = (await db.execute(text(
        "SELECT dl.dispatch_id, dl.order_line_id, dl.qty, l.line_no FROM dispatch_line dl "
        "JOIN order_line l ON l.id = dl.order_line_id "
        "WHERE dl.dispatch_id = ANY(CAST(:ids AS uuid[])) ORDER BY l.line_no"),
        {"ids": [str(r.id) for r in rows]})).all()
    by_dispatch: dict[str, list[sch.DispatchLineOut]] = {}
    for ln in lines:
        by_dispatch.setdefault(str(ln.dispatch_id), []).append(sch.DispatchLineOut(
            order_line_id=str(ln.order_line_id), line_no=ln.line_no, qty=_qty(ln.qty)))
    names = (people.Names() if portal
             else await people.resolve(db, rows, [("dispatched_by", "full_name")]))
    return [_dispatch_out(r, by_dispatch.get(str(r.id), []), portal, names) for r in rows]


def _dispatch_out(r: Any, lines: list[sch.DispatchLineOut], portal: bool = False,
                  names: people.Names | None = None) -> sch.Dispatch:
    """A partner sees what shipped and when, not who recorded it or why a dispatch
    was voided (question 15.14)."""
    return sch.Dispatch(
        id=str(r.id),
        order=sch.DispatchOrderRef(id=str(r.sales_order_id), order_no=r.order_no,
                                   party_name=r.party_name),
        dispatch_no=r.dispatch_no, dc_no=r.dc_no, dc_date=_iso(r.dc_date),
        invoice_no=r.invoice_no, invoice_date=_iso(r.invoice_date),
        dispatched_at=r.dispatched_at.isoformat(), transporter=r.transporter,
        vehicle_no=r.vehicle_no,
        dispatched_by=(None if portal
                       else (names or people.Names()).user(r.dispatched_by, r.full_name)),
        voided_at=_iso(r.voided_at), void_remark=None if portal else r.void_remark,
        # a dealer sees no warehouse (FS-023 B-1); a staff reader without stock.view
        # gets null from the join, which warehouse RLS hides
        warehouse=(None if portal or getattr(r, "w_code", None) is None
                   else WarehouseRef(id=str(r.warehouse_id), code=r.w_code, name=r.w_name)),
        lines=lines)


def _line_out(r: Any) -> sch.OrderLine:
    sent = Decimal(r.sent)
    return sch.OrderLine(
        id=str(r.id), line_no=r.line_no, product_id=str(r.product_id), description=r.description,
        hsn_code=r.hsn_code, uom=r.uom, uom_decimals=r.uom_decimals, qty=_qty(r.qty),
        rate=_money(r.rate), gross=_money(r.gross), discount_pct=_qty(r.discount_pct),
        discount1_amt=_money(r.discount1_amt), after_discount1=_money(r.after_discount1),
        discount2_pct=_qty(r.discount2_pct), discount2_amt=_money(r.discount2_amt),
        after_discount2=_money(r.after_discount2), discount3_pct=_qty(r.discount3_pct),
        discount3_amt=_money(r.discount3_amt), discount=_money(r.discount),
        taxable=_money(r.taxable), gst_slab=_qty(r.gst_slab), cgst_rate=_qty(r.cgst_rate),
        sgst_rate=_qty(r.sgst_rate), igst_rate=_qty(r.igst_rate), cgst=_money(r.cgst),
        sgst=_money(r.sgst), igst=_money(r.igst), total=_money(r.total),
        provisional_fields=list(r.provisional_fields or []), qty_dispatched=_qty(sent),
        qty_short=_qty(r.qty_short),
        qty_open=_qty(domain.open_quantity(Decimal(r.qty), sent, Decimal(r.qty_short))))


def _totals(r: Any) -> Totals:
    return Totals(gross=_money(r.gross), discount=_money(r.discount), taxable=_money(r.taxable),
                  cgst=_money(r.cgst), sgst=_money(r.sgst), igst=_money(r.igst),
                  total=_money(r.total))


def _warnings(r: Any, lines: list[sch.OrderLine]) -> list[str]:
    out = []
    provisional = sum(1 for ln in lines if ln.provisional_fields)
    if provisional:
        out.append(f"provisional_pricing: {provisional} of {len(lines)} lines use a stand-in "
                   f"rate or tax slab that the client has not confirmed.")
    return out


async def get_order(db: AsyncSession, caller: Caller, order_id: str) -> sch.Order:
    r = (await db.execute(text(_O_SELECT + " WHERE o.id = CAST(:o AS uuid)"),
                          {"o": order_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such order.")
    portal = _is_portal(caller)
    line_rows = (await db.execute(text(_LINE_SELECT), {"o": order_id})).all()
    lines = [_line_out(x) for x in line_rows]
    warehouse = None
    if not portal and r.status_text not in ("dispatched", "closed_short", "cancelled"):
        open_lines = [(str(x.id), str(x.product_id), Decimal(x.qty) - Decimal(x.sent))
                      for x in line_rows if Decimal(x.qty) - Decimal(x.sent) > 0]
        wid = None if r.warehouse_id is None else str(r.warehouse_id)
        stock = await stock_service.order_lines(db, wid, open_lines,
                                                committed=r.status_text != "draft")
        for ln in lines:
            ln.stock = stock.get(ln.id)
    if not portal and r.warehouse_id is not None:
        w = (await db.execute(text(
            "SELECT code::text AS code, name FROM warehouse WHERE id = CAST(:w AS uuid)"),
            {"w": str(r.warehouse_id)})).one_or_none()
        warehouse = (None if w is None
                     else WarehouseRef(id=str(r.warehouse_id), code=w.code, name=w.name))
    quotations = [sch.QuotationRef(id=str(q.id), quote_no=q.quote_no, version=q.version)
                  for q in (await db.execute(text(
                      "SELECT q.id, q.quote_no::text AS quote_no, q.version "
                      "FROM order_quotation oq "
                      "JOIN quotation q ON q.id = oq.quotation_id "
                      "WHERE oq.sales_order_id = CAST(:o AS uuid) AND oq.released_at IS NULL "
                      "ORDER BY q.quote_no, q.version"), {"o": order_id})).all()]
    approval, raw = await _approval(db, order_id, portal)
    last_rejection = None
    if r.status_text == "draft" and raw is not None and raw[0].status == "rejected":
        rej = next((s for s in raw[1] if s.decision == "reject"), None)
        if rej is not None:
            last_rejection = sch.LastRejection(
                remark=domain.PORTAL_REMARK if portal else (rej.remark or ""),
                role=rej.role, at=rej.decided_at.isoformat())
    seller = (sch.OrderSeller(gstin=r.s_gstin, legal_name=r.s_name, address=r.s_address,
                              state_code=r.s_state) if r.s_gstin else None)
    names = await people.resolve(db, [r], [("owner_user_id", "owner_name")],
                                 [("partner_id", "partner_name")])
    partner = names.partner(r.partner_id, r.partner_name, r.partner_type)
    complaint = None
    if r.type_text == "replacement":
        c = (await db.execute(text("SELECT * FROM order_complaint(CAST(:o AS uuid))"),
                              {"o": order_id})).one_or_none()
        complaint = sch.OrderComplaintRef(id=str(c.id), complaint_no=c.complaint_no) if c else None
    from api.services import schemes as scheme_service  # schemes imports this module
    totals = _totals(r)
    benefits, payable = await scheme_service.order_benefits(db, order_id, Decimal(totals.total))
    return sch.Order(
        benefits=benefits, payable=payable,
        id=str(r.id), order_no=r.order_no, complaint=complaint, status=r.status_text,
        order_type=r.type_text,
        party=sch.OrderParty(name=r.party_name, mobile=r.party_mobile, address=r.party_address,
                             gstin=r.party_gstin),
        partner=partner,
        lead=(sch.OrderLeadRef(id=str(r.lead_id), inquiry_no=r.lead_inquiry_no)
              if r.lead_id and r.lead_inquiry_no else None),
        quotations=quotations,
        owner=names.user(r.owner_user_id, r.owner_name),
        owner_org_unit=OrgUnitRef(id=str(r.owner_org_unit_id), name=r.owner_org_unit_name),
        territory=TerritoryRef(id=str(r.territory_id), name=r.territory_name,
                               level=r.territory_level),
        delivery_address=r.delivery_address, payment_terms=r.terms_text, seller=seller,
        place_of_supply=TerritoryRef(id=str(r.place_of_supply_territory_id), name=r.pos_name,
                                     level=r.pos_level),
        intra_state=r.intra_state, price_effective_date=r.price_effective_date.isoformat(),
        tax_date=_iso(r.tax_date), is_provisional=r.is_provisional, lines=lines,
        totals=totals, approval=approval, last_rejection=last_rejection,
        dispatches=await _dispatches(db, order_id, portal), warnings=_warnings(r, lines),
        pdf_state=("pending" if r.pdf_state == "rendering" else r.pdf_state or "none"),
        pdf_error=None if portal else r.pdf_error,
        confirmation=(await db.execute(text(
            "SELECT payload->>'confirmation' FROM activity_event WHERE entity_type = 'sales_order' "
            "AND entity_id = CAST(:o AS uuid) AND kind = 'order.approved' "
            "ORDER BY occurred_at DESC LIMIT 1"), {"o": order_id})).scalar_one_or_none(),
        remarks=r.remarks, submitted_at=_iso(r.submitted_at), approved_at=_iso(r.approved_at),
        cancelled_at=_iso(r.cancelled_at),
        # a partner reads its own cancel reason, never a staff one (question 15.14)
        cancel_remark=(r.cancel_remark if not portal or str(r.updated_by) == caller.user_id
                       else None),
        closed_at=_iso(r.closed_at), close_remark=None if portal else r.close_remark,
        warehouse=warehouse,
        payments=await payments_service.position(db, order_id),
        created_at=r.created_at.isoformat())


def _parse_date(value: str, field: str) -> dt.datetime:
    try:
        return dt.datetime.combine(dt.date.fromisoformat(value), dt.time.min, tzinfo=IST)
    except ValueError as exc:
        raise ValidationFailed(fields={field: "not an ISO date"}) from exc


def _order_filters(caller: Caller, *, status: str | None = None,
                   order_type: str | None = None, partner_id: str | None = None,
                   lead_id: str | None = None, owner: str | None = None, q: str | None = None,
                   created_from: str | None = None, created_to: str | None = None,
                   quotation_id: str | None = None) -> list[Any]:
    """The scope and every filter of the order list, shared with the counts."""
    where: list[Any] = [scope_predicate(_ORDERS, caller, order_t)]
    if status:
        # a comma list, like the lead list's stage: "open" is several statuses
        wanted = [x.strip() for x in status.split(",") if x.strip()]
        where.append(sa.cast(order_t.c.status, sa.Text).in_(wanted) if wanted else sa.true())
    if order_type:
        where.append(sa.cast(order_t.c.order_type, sa.Text) == order_type)
    if partner_id:
        where.append(order_t.c.partner_id == partner_id)
    if lead_id:
        where.append(order_t.c.lead_id == lead_id)
    if quotation_id:
        # every order the quotation was ever on, a released link included: a cancelled
        # order shows why the quotation is free again (BE-019)
        where.append(sa.exists(
            sa.select(sa.literal(1)).select_from(_oq_t)
            .where(_oq_t.c.sales_order_id == order_t.c.id, _oq_t.c.quotation_id == quotation_id)))
    if owner == "me":
        where.append(order_t.c.owner_user_id == caller.user_id)
    elif owner:
        where.append(order_t.c.owner_user_id == owner)
    if created_from:
        where.append(order_t.c.created_at >= _parse_date(created_from, "from"))
    if created_to:
        where.append(order_t.c.created_at < _parse_date(created_to, "to") + dt.timedelta(days=1))
    if q:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{esc}%"
        where.append(sa.or_(sa.cast(order_t.c.order_no, sa.Text).ilike(like),
                            order_t.c.party_name.ilike(like), order_t.c.party_mobile.ilike(like)))
    return where


_oq_t = sa.table("order_quotation", sa.column("sales_order_id", sa.Uuid),
                 sa.column("quotation_id", sa.Uuid))

_STATUSES = ("draft", "submitted", "approved", "partially_dispatched", "dispatched",
             "closed_short", "cancelled")
_step_t = sa.table("approval_step", sa.column("request_id", sa.Uuid),
                   sa.column("approver_role_id", sa.Uuid), sa.column("decision"),
                   sa.column("seq", sa.Integer))
_request_t = sa.table("approval_request", sa.column("id", sa.Uuid), sa.column("doc_type"),
                      sa.column("entity_id", sa.Uuid), sa.column("status"))
_role_t = sa.table("role", sa.column("id", sa.Uuid), sa.column("code"))


async def order_stats(db: AsyncSession, caller: Caller, **filters: str | None) -> sch.OrderStats:
    """Counts for the order board (API review B2): every status, and the submitted
    orders by the role whose step is next."""
    where = _order_filters(caller, **filters)
    status = sa.cast(order_t.c.status, sa.Text)
    by_status = dict.fromkeys(_STATUSES, 0)
    for r in (await db.execute(sa.select(status.label("s"), sa.func.count().label("n"))
                               .select_from(order_t).where(sa.and_(*where))
                               .group_by(status))).all():
        by_status[r.s] = r.n
    # the next undecided step of each pending request on a submitted order in scope
    first = (sa.select(_step_t.c.request_id, sa.func.min(_step_t.c.seq).label("seq"))
             .where(_step_t.c.decision.is_(None)).group_by(_step_t.c.request_id).subquery())
    submitted = sa.select(order_t.c.id).where(sa.and_(*where, status == "submitted"))
    waiting = (await db.execute(
        sa.select(sa.cast(_role_t.c.code, sa.Text).label("role"), sa.func.count().label("n"))
        .select_from(_request_t
                     .join(first, first.c.request_id == _request_t.c.id)
                     .join(_step_t, sa.and_(_step_t.c.request_id == first.c.request_id,
                                            _step_t.c.seq == first.c.seq))
                     .join(_role_t, _role_t.c.id == _step_t.c.approver_role_id))
        .where(_request_t.c.doc_type == "sales_order",
               sa.cast(_request_t.c.status, sa.Text) == "pending",
               _request_t.c.entity_id.in_(submitted))
        .group_by(_role_t.c.code))).all()
    return sch.OrderStats(total=sum(by_status.values()), by_status=by_status,
                          waiting_on={r.role: r.n for r in waiting})


async def list_orders(db: AsyncSession, caller: Caller, *, status: str | None = None,
                      order_type: str | None = None, partner_id: str | None = None,
                      lead_id: str | None = None, owner: str | None = None, q: str | None = None,
                      created_from: str | None = None, created_to: str | None = None,
                      limit: int = 25, cursor: str | None = None,
                      include_total: bool = False,
                      quotation_id: str | None = None) -> sch.OrderPage:
    limit = max(1, min(limit, _MAX_LIMIT))
    where = _order_filters(caller, status=status, order_type=order_type,
                           partner_id=partner_id, lead_id=lead_id, owner=owner, q=q,
                           created_from=created_from, created_to=created_to,
                           quotation_id=quotation_id)
    filters = list(where)
    if cursor:
        c_ts, c_id = _decode_cursor(cursor)
        where.append(sa.or_(order_t.c.created_at < c_ts,
                            sa.and_(order_t.c.created_at == c_ts, order_t.c.id < c_id)))
    total, capped = (await _capped_total(db, order_t, filters)
                     if include_total else (None, False))
    page = (await db.execute(sa.select(order_t.c.id, order_t.c.created_at)
                             .where(sa.and_(*where))
                             .order_by(order_t.c.created_at.desc(), order_t.c.id.desc())
                             .limit(limit + 1))).all()
    next_cursor = None
    if len(page) > limit:
        last = page[limit - 1]
        next_cursor = _encode_cursor(last.created_at, str(last.id))
        page = page[:limit]
    ids = [str(r.id) for r in page]
    if not ids:
        return sch.OrderPage(data=[], meta=PageMeta(limit=limit, next_cursor=None, total=total,
                                                    total_capped=capped))
    rows = (await db.execute(text(_O_SELECT + " WHERE o.id = ANY(CAST(:ids AS uuid[]))"),
                             {"ids": ids})).all()
    extra = {str(x.id): x for x in (await db.execute(text("""
        SELECT o.id,
               (SELECT COALESCE(sum(l.qty), 0) FROM order_line l WHERE l.sales_order_id = o.id)
                 AS ordered,
               (SELECT COALESCE(sum(dl.qty), 0) FROM dispatch_line dl
                  JOIN dispatch d ON d.id = dl.dispatch_id AND d.voided_at IS NULL
                 WHERE d.sales_order_id = o.id) AS sent,
               (SELECT r.code::text FROM approval_request q
                  JOIN approval_step s ON s.request_id = q.id AND s.decision IS NULL
                  JOIN role r ON r.id = s.approver_role_id
                 WHERE q.doc_type = 'sales_order' AND q.entity_id = o.id AND q.status = 'pending'
                 ORDER BY s.seq LIMIT 1) AS waiting
          FROM sales_order o WHERE o.id = ANY(CAST(:ids AS uuid[]))"""), {"ids": ids})).all()}
    by_id = {str(r.id): r for r in rows}
    names = await people.resolve(db, rows, [("owner_user_id", "owner_name")],
                                 [("partner_id", "partner_name")])
    data = []
    for i in ids:
        r = by_id.get(i)
        if r is None:
            continue
        x = extra[i]
        data.append(sch.OrderSummary(
            id=i, order_no=r.order_no, status=r.status_text, order_type=r.type_text,
            party_name=r.party_name,
            partner=names.partner(r.partner_id, r.partner_name, r.partner_type),
            owner=names.user(r.owner_user_id, r.owner_name),
            totals=_totals(r), is_provisional=r.is_provisional,
            dispatched_pct=domain.dispatched_pct(Decimal(x.ordered), Decimal(x.sent)),
            approval_waiting_on=x.waiting, submitted_at=_iso(r.submitted_at),
            created_at=r.created_at.isoformat()))
    return sch.OrderPage(data=data, meta=PageMeta(limit=limit, next_cursor=next_cursor,
                                                  total=total, total_capped=capped))


async def timeline(db: AsyncSession, caller: Caller, order_id: str, *, limit: int = 100,
                   cursor: str | None = None) -> TimelinePage:
    """The order's events. An approval event's payload is {seq, role, decision}
    (B-5); staff also get the step's remark and decider, joined here by the
    decision's own timestamp, which is its event's (both are the transaction's
    now()). A dealer gets neither."""
    limit = max(1, min(limit, _MAX_LIMIT))
    if not (await db.execute(text("SELECT order_visible(CAST(:o AS uuid))"),
                             {"o": order_id})).scalar_one():
        raise NotFoundError("No such order.")
    portal = _is_portal(caller)
    before_at, before_id = (None, None)
    if cursor:
        before_at, before_id = _decode_cursor(cursor)
    rows = (await db.execute(text(
        "SELECT e.id, e.kind, e.occurred_at, e.actor_id, e.payload, s.remark, u.full_name "
        "FROM activity_event e "
        "LEFT JOIN LATERAL (SELECT st.remark FROM approval_step st "
        "     JOIN approval_request q ON q.id = st.request_id "
        "     WHERE q.doc_type = 'sales_order' AND q.entity_id = e.entity_id "
        "     AND st.decided_at = e.occurred_at AND st.seq = (e.payload ->> 'seq')::int "
        "     LIMIT 1) s ON e.kind = 'approval.decided' "
        "LEFT JOIN app_user u ON u.id = e.actor_id "
        "WHERE e.entity_type = 'sales_order' AND e.entity_id = CAST(:o AS uuid) "
        "AND (CAST(:bat AS timestamptz) IS NULL OR (e.occurred_at, e.id) < "
        "(CAST(:bat AS timestamptz), CAST(:bid AS uuid))) "
        "ORDER BY e.occurred_at DESC, e.id DESC LIMIT :lim"),
        {"o": order_id, "bat": before_at, "bid": before_id, "lim": limit + 1})).all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.occurred_at, str(last.id))
        rows = rows[:limit]
    names = await people.resolve(db, rows, [("actor_id", "full_name")])
    events = []
    for r in rows:
        payload = json.loads(r.payload) if isinstance(r.payload, str) else dict(r.payload or {})
        approval = r.kind.startswith("approval.")
        if approval and not portal and r.remark:
            payload["remark"] = r.remark
        name = (payload.pop("actor_name", None) or r.full_name
                or names.users.get(str(r.actor_id)) or "")
        hidden = portal and domain.actor_hidden_from_partner(r.kind)
        actor = (UserRef(id=str(r.actor_id), full_name=name)
                 if r.actor_id is not None and not hidden else None)
        events.append(TimelineEvent(id=str(r.id), kind=r.kind,
                                    occurred_at=r.occurred_at.isoformat(), actor=actor,
                                    payload=payload))
    return TimelinePage(data=events, meta=PageMeta(limit=limit, next_cursor=next_cursor))


# ── create ───────────────────────────────────────────────────────────────────

async def _from_quotations(db: AsyncSession, caller: Caller, body: sch.OrderCreate
                           ) -> dict[str, Any]:
    ids = list(dict.fromkeys(body.quotation_ids))
    rows = (await db.execute(text(
        "SELECT q.id, q.status::text AS status, q.lead_id, q.partner_id, q.superseded_by_id, "
        "q.place_of_supply_territory_id, q.seller_gstin_id, q.price_effective_date, "
        "q.owner_user_id, q.owner_org_unit_id, q.territory_id, q.party_name, q.party_mobile, "
        "q.party_address, q.party_gstin::text AS party_gstin, q.quote_no::text AS quote_no "
        "FROM quotation q WHERE q.id = ANY(CAST(:ids AS uuid[])) AND q.deleted_at IS NULL"),
        {"ids": ids})).all()
    if len(rows) != len(ids):
        raise NotFoundError("No such quotation.")
    for r in rows:
        if r.status != "accepted" or r.superseded_by_id is not None:
            raise ValidationFailed(f"Quotation {r.quote_no} is {r.status}; only an accepted, "
                                   f"current quotation is ordered.",
                                   code="quotation_not_accepted",
                                   fields={"quotation_ids": str(r.id)})
    for field in domain.PARTY_FIELDS_FROM_QUOTATIONS:
        if len({getattr(r, field) for r in rows}) > 1:
            raise ValidationFailed(f"The quotations differ on {field}.",
                                   code="quotations_disagree", fields={field: "differs"})
    first = rows[0]
    given = {"partner_id": body.partner_id if body.partner_given else None,
             "place_of_supply_territory_id": body.place_of_supply_territory_id,
             "seller_gstin_id": body.seller_gstin_id,
             "price_effective_date": body.price_effective_date}
    for field, value in given.items():
        if value is None and not (field == "partner_id" and body.partner_given):
            continue
        ours = getattr(first, field)
        if (str(value) if value is not None else None) != (str(ours) if ours is not None else None):
            raise ValidationFailed(f"An order from quotations takes {field} from them.",
                                   code="quotations_disagree",
                                   fields={field: "fixed by the quotations"})
    leads = {str(r.lead_id) for r in rows}
    if body.lead_id and body.lead_id not in leads:
        raise ValidationFailed("An order from quotations takes its lead from them.",
                               code="quotations_disagree",
                               fields={"lead_id": "fixed by the quotations"})
    single = len(leads) == 1
    partner = str(first.partner_id) if first.partner_id else None
    if not single and partner is None:
        raise ValidationFailed("An order across several leads is a dealer's consolidated order "
                               "and needs a partner.", code="partner_required",
                               fields={"partner_id": "required for several leads"})
    lead_id = next(iter(leads)) if single else None
    if lead_id and not (await db.execute(text("SELECT lead_visible(CAST(:l AS uuid))"),
                                         {"l": lead_id})).scalar_one():
        raise ValidationFailed("You cannot see the quotations' lead.", code="lead_not_visible",
                               fields={"lead_id": lead_id})
    if single:
        party = {"pn": first.party_name, "pm": first.party_mobile, "pa": first.party_address,
                 "pg": first.party_gstin}
        owner = str(first.owner_user_id) if first.owner_user_id else None
    else:
        p = (await db.execute(text(
            "SELECT name, mobile, address, gstin::text AS gstin FROM channel_partner "
            "WHERE id = CAST(:p AS uuid)"), {"p": partner})).one_or_none()
        if p is None:
            # The dealer is the buyer of record, so its details go on the order. A
            # caller who prices with the dealer only through a document (FS-020
            # rule 2) cannot read them: a manager or the dealer places this one.
            raise ValidationFailed(
                "A consolidated order is placed by the dealer or a manager who can see "
                "the dealer.", code="partner_not_readable",
                fields={"partner_id": "outside your area"})
        party = {"pn": p.name, "pm": p.mobile, "pa": p.address, "pg": p.gstin}
        owner = caller.user_id if not _is_portal(caller) else (await db.execute(text(
            "SELECT lead_auto_owner(CAST(:t AS uuid))"), {"t": str(first.territory_id)})
        ).scalar_one_or_none()
        owner = str(owner) if owner else None
    lines = (await db.execute(text(
        "SELECT l.* FROM quotation_line l JOIN quotation q ON q.id = l.quotation_id "
        "WHERE l.quotation_id = ANY(CAST(:ids AS uuid[])) "
        "ORDER BY q.quote_no, q.version, l.line_no"),
        {"ids": ids})).all()
    return {"ids": ids, "lead": lead_id, "partner": partner, "party": party, "owner": owner,
            "office": str(first.owner_org_unit_id), "territory": str(first.territory_id),
            "pos": str(first.place_of_supply_territory_id),
            "seller": str(first.seller_gstin_id), "day": first.price_effective_date,
            "lines": list(lines)}


def _repriced(source: list[Any], ctx: PricedContext) -> list[str]:
    out = []
    for i, (row, p) in enumerate(zip(source, ctx.document.lines, strict=True)):
        if Decimal(row.rate) != p.rate.rate or Decimal(row.gst_slab) != p.tax.slab \
                or Decimal(row.total) != p.money.total:
            out.append(f"repriced: line {i + 1} changed from its quotation "
                       f"(total {_s(row.total)} -> {_s(p.money.total)}).")
    return out


async def create_order(db: AsyncSession, caller: Caller, body: sch.OrderCreate,
                       settings: Settings) -> sch.Order:
    _check_type(body.order_type)
    if body.quotation_ids and body.lines:
        raise ValidationFailed("Order from quotations or type lines in, not both.",
                               fields={"lines": "not with quotation_ids"})
    if _is_portal(caller) and body.partner_given and body.partner_id is None:
        raise ValidationFailed("A dealer's order is its own.", code="partner_required",
                               fields={"partner_id": "required"})
    await stock_service.check_order_warehouse(db, caller, body.warehouse_id)
    warnings: list[str] = []
    sources: list[str | None] | None = None
    snaps: list[Any] | None = None
    if body.quotation_ids:
        src = await _from_quotations(db, caller, body)
        ctx = await _price(db, partner_id=src["partner"], pos=src["pos"], seller=src["seller"],
                           as_of=src["day"], specs=_specs(src["lines"]), existing=True)
        warnings += _repriced(src["lines"], ctx)
        sources = [str(r.id) for r in src["lines"]]
        snaps = src["lines"]
        lead_id, partner, party = src["lead"], src["partner"], src["party"]
        owner, office, territory, pos = src["owner"], src["office"], src["territory"], src["pos"]
    else:
        if body.party is None:
            raise ValidationFailed("A direct order needs its party.", fields={"party": "required"})
        lead = None
        if body.lead_id:
            lead = (await db.execute(text(
                "SELECT id, stage::text AS stage, territory_id, merged_into_id, owner_user_id "
                "FROM lead WHERE id = CAST(:l AS uuid) AND deleted_at IS NULL"),
                {"l": body.lead_id})).one_or_none()
            if lead is None:
                raise ValidationFailed("You cannot see that lead.", code="lead_not_visible",
                                       fields={"lead_id": body.lead_id})
            if lead.stage not in domain.LEAD_STAGES_ORDERABLE or lead.merged_into_id:
                raise ValidationFailed(f"The lead is {lead.stage}.", code="lead_not_open",
                                       fields={"lead_stage": lead.stage})
        pos = body.place_of_supply_territory_id or (str(lead.territory_id) if lead else None)
        if pos is None:
            raise ValidationFailed("Where are the goods going?",
                                   fields={"place_of_supply_territory_id": "required"})
        territory = str(lead.territory_id) if lead else pos
        owner, office, _ = await _route(db, caller, territory)
        if _is_portal(caller) and lead is not None and lead.owner_user_id:
            owner = str(lead.owner_user_id)
        partner = (body.partner_id if body.partner_given else
                   (caller.partner_id if _is_portal(caller) else None))
        lead_id = body.lead_id
        party = _party_values(body.party)
        ctx = await _price(db, partner_id=partner, pos=pos, seller=body.seller_gstin_id,
                           as_of=body.price_effective_date,
                           specs=[LineSpec(product_id=ln.product_id, qty=ln.qty,
                                           discounts=ln.discounts) for ln in body.lines],
                           existing=False)
        _compare_preview(body.lines, ctx)
    try:
        order_id = str((await db.execute(text("""
            INSERT INTO sales_order (order_type, lead_id, partner_id, party_name, party_mobile,
                party_address, party_gstin, delivery_address, owner_user_id, owner_org_unit_id,
                territory_id, seller_gstin_id, place_of_supply_territory_id,
                place_of_supply_state_id, intra_state, price_effective_date, payment_terms,
                remarks, created_by, updated_by, warehouse_id)
            VALUES (CAST(:ty AS order_type), CAST(:lead AS uuid), CAST(:p AS uuid), :pn, :pm,
                :pa, :pg, :da, CAST(:ou AS uuid), CAST(:oou AS uuid), CAST(:terr AS uuid),
                CAST(:sg AS uuid), CAST(:pos AS uuid), CAST(:ps AS uuid), :intra, :day,
                CAST(:pt AS order_payment_terms), :rem, CAST(:me AS uuid), CAST(:me AS uuid),
                CAST(:wh AS uuid))
            RETURNING id"""),
            {"ty": body.order_type, "lead": lead_id, "p": ctx.partner_id if partner else None,
             **party, "da": body.delivery_address, "ou": owner, "oou": office,
             "terr": territory, "sg": ctx.seller_gstin_id, "pos": pos,
             "ps": ctx.place_of_supply_state_id, "intra": ctx.intra_state, "day": ctx.as_of,
             "pt": body.payment_terms, "rem": body.remarks, "me": caller.user_id,
             "wh": body.warehouse_id})).scalar_one())
    except DBAPIError as exc:
        raise map_db_error(exc) from exc
    await _write_lines(db, order_id, ctx, snaps, sources)
    await _write_figures(db, order_id, ctx, caller)
    if body.quotation_ids:
        await _call(db, "SELECT order_quotations_claim(CAST(:o AS uuid), CAST(:ids AS uuid[]))",
                    {"o": order_id, "ids": list(dict.fromkeys(body.quotation_ids))})
    await _emit(db, order_id=order_id, lead_id=lead_id, kind="order.created",
                actor_id=caller.user_id, lines=len(ctx.document.lines),
                quotations=len(body.quotation_ids))
    out = await get_order(db, caller, order_id)
    out.warnings += [w for w in ctx.document.warnings if w not in out.warnings] + warnings
    return out


# ── draft edits ──────────────────────────────────────────────────────────────

async def patch_order(db: AsyncSession, caller: Caller, order_id: str, body: sch.OrderPatch,
                      settings: Settings) -> sch.Order:
    row = await _lock(db, order_id)
    _expect(row, body.expected_status)
    _must_be_draft(row)
    if body.order_type:
        _check_type(body.order_type)
    linked = await _linked_quotations(db, order_id)
    partner = (body.partner_id if body.partner_given else
               (str(row.partner_id) if row.partner_id else None))
    pos = body.place_of_supply_territory_id or str(row.place_of_supply_territory_id)
    seller = body.seller_gstin_id or str(row.seller_gstin_id)
    day = body.price_effective_date or row.price_effective_date
    if linked:
        fixed = {"partner_id": (partner, row.partner_id),
                 "place_of_supply_territory_id": (pos, row.place_of_supply_territory_id),
                 "seller_gstin_id": (seller, row.seller_gstin_id),
                 "price_effective_date": (day, row.price_effective_date)}
        for field, (new, old) in fixed.items():
            if (str(new) if new is not None else None) != (str(old) if old is not None else None):
                raise ValidationFailed(f"An order from quotations takes {field} from them.",
                                       code="quotations_disagree",
                                       fields={field: "fixed by the quotations"})
    if _is_portal(caller) and body.partner_given and body.partner_id is None:
        raise ValidationFailed("A dealer's order is its own.", code="partner_required",
                               fields={"partner_id": "required"})
    await stock_service.check_order_warehouse(db, caller, body.warehouse_id)
    stored = await _stored(db, order_id)
    ctx = await _price(db, partner_id=partner, pos=pos, seller=seller, as_of=day,
                       specs=_specs(stored), existing=True)
    sets: dict[str, Any] = {}
    if body.order_type:
        sets["order_type"] = body.order_type
    if body.party is not None:
        sets.update(_party_values(body.party))
    if "delivery_address" in body.model_fields_set:
        sets["da"] = body.delivery_address
    if body.payment_terms:
        sets["pt"] = body.payment_terms
    if "remarks" in body.model_fields_set:
        sets["rem"] = body.remarks
    if "warehouse_id" in body.model_fields_set:
        sets["wh"] = body.warehouse_id
    columns = {"order_type": "order_type = CAST(:order_type AS order_type)",
               "pn": "party_name = :pn", "pm": "party_mobile = :pm", "pa": "party_address = :pa",
               "pg": "party_gstin = :pg", "da": "delivery_address = :da",
               "pt": "payment_terms = CAST(:pt AS order_payment_terms)", "rem": "remarks = :rem",
               "wh": "warehouse_id = CAST(:wh AS uuid)"}
    assignments = [columns[k] for k in sets] + [
        "partner_id = CAST(:p AS uuid)", "place_of_supply_territory_id = CAST(:pos AS uuid)",
        "updated_by = CAST(:me AS uuid)"]
    if not row.lead_id and pos != str(row.place_of_supply_territory_id):
        assignments.append("territory_id = CAST(:pos AS uuid)")
    try:
        await db.execute(text(f"UPDATE sales_order SET {', '.join(assignments)} "
                              f"WHERE id = CAST(:o AS uuid)"),
                         {**sets, "p": partner, "pos": pos, "me": caller.user_id, "o": order_id})
    except DBAPIError as exc:
        raise map_db_error(exc) from exc
    await _write_lines(db, order_id, ctx, stored,
                       [str(r.source_quotation_line_id) if r.source_quotation_line_id else None
                        for r in stored])
    await _write_figures(db, order_id, ctx, caller)
    await _emit(db, order_id=order_id, lead_id=row.lead_id, kind="order.updated",
                actor_id=caller.user_id, fields=sorted(body.model_fields_set - {"expected_status"}))
    out = await get_order(db, caller, order_id)
    out.warnings += [w for w in ctx.document.warnings if w not in out.warnings]
    return out


async def replace_lines(db: AsyncSession, caller: Caller, order_id: str,
                        body: sch.OrderLinesReplace, settings: Settings) -> sch.Order:
    row = await _lock(db, order_id)
    _expect(row, body.expected_status)
    _must_be_draft(row)
    ctx = await _price(db, partner_id=str(row.partner_id) if row.partner_id else None,
                       pos=str(row.place_of_supply_territory_id), seller=str(row.seller_gstin_id),
                       as_of=row.price_effective_date,
                       specs=[LineSpec(product_id=ln.product_id, qty=ln.qty,
                                       discounts=ln.discounts) for ln in body.lines],
                       existing=False)
    _compare_preview(body.lines, ctx)
    await _write_lines(db, order_id, ctx)
    await _write_figures(db, order_id, ctx, caller)
    await _emit(db, order_id=order_id, lead_id=row.lead_id, kind="order.lines_replaced",
                actor_id=caller.user_id, lines=len(body.lines))
    out = await get_order(db, caller, order_id)
    out.warnings += [w for w in ctx.document.warnings if w not in out.warnings]
    return out


# ── submit, cancel, delete ───────────────────────────────────────────────────

async def submit_order(db: AsyncSession, caller: Caller, order_id: str,
                       body: sch.SubmitRequest, settings: Settings) -> sch.Order:
    row = await _lock(db, order_id)
    _expect(row, body.expected_status)
    _must_be_draft(row)
    stored = await _stored(db, order_id)
    if not stored:
        raise ValidationFailed("Add at least one line before submitting.", code="no_lines",
                               fields={"lines": "empty"})
    ctx = await _price(db, partner_id=str(row.partner_id) if row.partner_id else None,
                       pos=str(row.place_of_supply_territory_id), seller=str(row.seller_gstin_id),
                       as_of=row.price_effective_date, specs=_specs(stored), existing=True,
                       submitting=True)
    _compare_stored(stored, ctx)
    if ctx.document.totals.total <= 0:
        raise ValidationFailed("An order worth nothing cannot be approved.", code="zero_total",
                               fields={"total": "0.00"})
    if row.lead_id:
        # read without a lock: a lead lost at this moment is a race the submit
        # accepts, because people still review the order (FS-011 4)
        lead = (await db.execute(text(
            "SELECT stage::text AS stage, merged_into_id FROM lead WHERE id = CAST(:l AS uuid)"),
            {"l": str(row.lead_id)})).one_or_none()
        if lead is None or lead.stage not in domain.LEAD_STAGES_ORDERABLE or lead.merged_into_id:
            raise ValidationFailed("The order's lead is no longer open.", code="lead_not_open",
                                   fields={"lead_stage": lead.stage if lead else "unknown"})
    request = await _call(db, "SELECT order_submit(CAST(:o AS uuid))", {"o": order_id})
    await _emit(db, order_id=order_id, lead_id=row.lead_id, kind="order.submitted",
                actor_id=caller.user_id, request=str(request))
    return await get_order(db, caller, order_id)


async def cancel_order(db: AsyncSession, caller: Caller, order_id: str,
                       body: sch.RemarkRequest, settings: Settings) -> sch.Order:
    await _call(db, "SELECT order_cancel(CAST(:o AS uuid), :r, :e)",
                {"o": order_id, "r": body.remark, "e": body.expected_status})
    return await get_order(db, caller, order_id)


async def delete_order(db: AsyncSession, caller: Caller, order_id: str) -> None:
    await _call(db, "SELECT order_delete(CAST(:o AS uuid))", {"o": order_id})


# ── dispatch ─────────────────────────────────────────────────────────────────

async def record_dispatch(db: AsyncSession, caller: Caller, order_id: str,
                          body: sch.DispatchCreate) -> sch.Dispatch:
    problems = domain.dispatch_line_problems([ln.order_line_id for ln in body.lines])
    if problems:
        raise ValidationFailed("Check the dispatch lines.",
                               code="no_lines" if "lines" in problems else "duplicate_line",
                               fields=problems)
    sent_at = body.dispatched_at if body.dispatched_at.tzinfo else body.dispatched_at.replace(
        tzinfo=IST)
    if sent_at.astimezone(IST).date() > today_ist():
        raise ValidationFailed("Goods cannot have left in the future.",
                               fields={"dispatched_at": "in the future"})
    payload = {
        "dc_no": body.dc_no, "dc_date": _iso(body.dc_date), "invoice_no": body.invoice_no,
        "invoice_date": _iso(body.invoice_date), "dispatched_at": sent_at.isoformat(),
        "transporter": body.transporter, "vehicle_no": body.vehicle_no,
        "warehouse_id": body.warehouse_id,
        "lines": [{"order_line_id": ln.order_line_id, "qty": str(ln.qty)} for ln in body.lines],
    }
    dispatch_id = await _call(db, "SELECT dispatch_record(CAST(:o AS uuid), CAST(:p AS jsonb))",
                              {"o": order_id, "p": json.dumps(payload)})
    warnings = []
    if body.invoice_date and body.dc_date and body.invoice_date < body.dc_date:
        warnings.append("invoice_before_dc: the invoice date is before the DC date.")
    if body.invoice_no:
        repeats: int = (await db.execute(text(
            "SELECT count(*) FROM dispatch WHERE invoice_no = :i AND id <> CAST(:d AS uuid) "
            "AND voided_at IS NULL"), {"i": body.invoice_no, "d": str(dispatch_id)})).scalar_one()
        if repeats:
            warnings.append("duplicate_invoice_no: this invoice number is on another dispatch.")
    out = next(d for d in await _dispatches(db, order_id) if d.id == str(dispatch_id))
    out.warnings = warnings
    return out


async def void_dispatch(db: AsyncSession, caller: Caller, dispatch_id: str,
                        body: sch.RemarkRequest) -> sch.Order:
    order_id = (await db.execute(text(
        "SELECT sales_order_id FROM dispatch WHERE id = CAST(:d AS uuid)"),
        {"d": dispatch_id})).scalar_one_or_none()
    if order_id is None:
        raise NotFoundError("No such dispatch.")
    await _call(db, "SELECT dispatch_void(CAST(:d AS uuid), :r)",
                {"d": dispatch_id, "r": body.remark})
    return await get_order(db, caller, str(order_id))


async def close_short(db: AsyncSession, caller: Caller, order_id: str,
                      body: sch.RemarkRequest) -> sch.Order:
    await _call(db, "SELECT order_close_short(CAST(:o AS uuid), :r)",
                {"o": order_id, "r": body.remark})
    return await get_order(db, caller, order_id)


async def order_dispatches(db: AsyncSession, caller: Caller, order_id: str
                          ) -> list[sch.Dispatch]:
    if not (await db.execute(text("SELECT order_visible(CAST(:o AS uuid))"),
                             {"o": order_id})).scalar_one():
        raise NotFoundError("No such order.")
    return await _dispatches(db, order_id, _is_portal(caller))


async def list_dispatches(db: AsyncSession, caller: Caller, *, order_id: str | None = None,
                          partner_id: str | None = None, created_from: str | None = None,
                          created_to: str | None = None, limit: int = 50,
                          cursor: str | None = None) -> sch.DispatchPage:
    limit = max(1, min(limit, _MAX_LIMIT))
    before_at, before_id = (None, None)
    if cursor:
        before_at, before_id = _decode_cursor(cursor)
    rows = (await db.execute(text(
        "SELECT d.*, u.full_name, o.order_no::text AS order_no, o.party_name, "
        "w.code::text AS w_code, w.name AS w_name "
        "FROM dispatch d JOIN sales_order o ON o.id = d.sales_order_id "
        "LEFT JOIN warehouse w ON w.id = d.warehouse_id "
        "LEFT JOIN app_user u ON u.id = d.dispatched_by "
        "WHERE (CAST(:o AS uuid) IS NULL OR d.sales_order_id = CAST(:o AS uuid)) "
        "AND (CAST(:p AS uuid) IS NULL OR o.partner_id = CAST(:p AS uuid)) "
        "AND (CAST(:f AS timestamptz) IS NULL OR d.dispatched_at >= CAST(:f AS timestamptz)) "
        "AND (CAST(:t AS timestamptz) IS NULL OR d.dispatched_at < CAST(:t AS timestamptz)) "
        "AND (CAST(:bat AS timestamptz) IS NULL OR (d.created_at, d.id) < "
        "(CAST(:bat AS timestamptz), CAST(:bid AS uuid))) "
        "ORDER BY d.created_at DESC, d.id DESC LIMIT :lim"),
        {"o": order_id, "p": partner_id,
         "f": _parse_date(created_from, "from") if created_from else None,
         "t": (_parse_date(created_to, "to") + dt.timedelta(days=1)) if created_to else None,
         "bat": before_at, "bid": before_id, "lim": limit + 1})).all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.created_at, str(last.id))
        rows = rows[:limit]
    out = await _with_lines(db, list(rows), _is_portal(caller))
    return sch.DispatchPage(data=out, meta=PageMeta(limit=limit, next_cursor=next_cursor))


__all__ = ["ApiError", "cancel_order", "close_short", "create_order", "delete_order",
           "get_order", "list_dispatches", "list_orders", "map_db_error", "order_dispatches",
           "patch_order", "record_dispatch", "replace_lines", "submit_order", "timeline",
           "void_dispatch"]


# ── the order PDF (FS-012) ───────────────────────────────────────────────────

async def pdf_link(db: AsyncSession, caller: Caller, order_id: str, storage: Storage) -> PdfLink:
    """A ten-minute link to the approved order's PDF. The row is read under RLS, so
    an order out of scope is a 404 like any other."""
    row = (await db.execute(text(
        "SELECT order_no::text AS order_no, status::text AS status, pdf_state, pdf_key, pdf_error "
        "FROM sales_order WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"),
        {"id": order_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such order.")
    if row.status == "cancelled":
        # rule 8: the PDF is the approved order, and this one no longer stands
        raise ConflictError("The order was cancelled; its PDF is withdrawn.",
                            code="order_cancelled")
    if row.pdf_state is None:
        raise NotFoundError("No PDF: the order is not approved yet.")
    if row.pdf_state == "failed":
        raise ConflictError("The PDF could not be produced.", code="pdf_failed",
                            fields={} if _is_portal(caller) else {"pdf_error": row.pdf_error or ""})
    if row.pdf_state != "ready":
        raise ConflictError("The PDF is being prepared; try again in a few seconds.",
                            code="pdf_pending")
    filename = domain.pdf_filename(row.order_no)
    try:
        url, expires = storage.presign_get(row.pdf_key, filename=filename)
    except RuntimeError as exc:
        log.warning("order.storage_unavailable", reason=str(exc))
        raise ConflictError(_STORAGE_DOWN, code="storage_unavailable") from exc
    return PdfLink(url=url, expires_at=expires.isoformat(), filename=filename)
