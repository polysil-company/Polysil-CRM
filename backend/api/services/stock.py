"""Stock (FS-023, ADR-046): warehouses, manual movements, the stock list,
availability, and the order form's per-line figure.

Manual movements are one definer call (`stock_record`, migration 032); dispatches
move stock by trigger. On hand and committed are derived on read. Services never
commit.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.errors import ApiError, ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import stock as sch
from api.schemas.leads import PageMeta, UserRef
from api.services.leads import _decode_cursor, _encode_cursor

# The SQLSTATEs migration 032 raises: (status, code)
SQLSTATE_TO_ERROR: dict[str, tuple[int, str]] = {
    "STKNG": (409, "negative_stock"),
    "STKWI": (409, "warehouse_inactive"),
    "STKPI": (409, "product_inactive"),
    "STKPR": (422, "qty_precision"),
    "STKNF": (404, "not_found"),
    "STKNW": (409, "no_default_warehouse"),
}


def _sqlstate(exc: DBAPIError) -> str:
    return str(getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None) or "")


def _message(exc: DBAPIError) -> str:
    raw = str(exc.orig).split("\n")[0]
    return raw.split(": ", 1)[-1] if ": " in raw else raw


def map_error(exc: DBAPIError) -> Exception:
    code = _sqlstate(exc)
    if code == "42501":
        return ForbiddenError("Not permitted.")
    if code == "22023":
        return ValidationFailed(_message(exc))
    if code in SQLSTATE_TO_ERROR:
        status, name = SQLSTATE_TO_ERROR[code]
        cls: type[ApiError] = {404: NotFoundError, 409: ConflictError}.get(status, ValidationFailed)
        return cls(_message(exc), code=name)
    return exc


def _qty(v: Decimal) -> str:
    return format(v.normalize(), "f") if v != 0 else "0"


async def may_view(db: AsyncSession) -> bool:
    return bool((await db.execute(text("SELECT app_has_permission('stock', 'view')"))).scalar_one())


# ── warehouses ──────────────────────────────────────────────────────────────

def _warehouse_out(r: Any) -> sch.Warehouse:
    return sch.Warehouse(id=str(r.id), code=str(r.code), name=r.name,
                         territory_id=None if r.territory_id is None else str(r.territory_id),
                         is_default=r.is_default, is_active=r.is_active)


async def list_warehouses(db: AsyncSession, include_inactive: bool) -> list[sch.Warehouse]:
    rows = (await db.execute(text(
        "SELECT * FROM warehouse WHERE (:all OR is_active) ORDER BY is_default DESC, code"),
        {"all": include_inactive})).all()
    return [_warehouse_out(r) for r in rows]


async def _write_warehouse(db: AsyncSession, sql: str, params: dict[str, Any]) -> Any:
    try:
        async with db.begin_nested():
            return (await db.execute(text(sql), params)).one()
    except DBAPIError as exc:
        if _sqlstate(exc) == "23505" and "uq_warehouse_default" in str(exc.orig):
            raise ConflictError("Another default was set at the same time; try again.",
                                code="default_warehouse") from exc
        if _sqlstate(exc) == "23505":
            raise ConflictError("That code is taken.", code="code_taken", fields={"code": "taken"}) from exc
        if _sqlstate(exc) == "23514":
            raise ConflictError("The default warehouse must be active.", code="default_warehouse") from exc
        raise


async def create_warehouse(db: AsyncSession, caller: Caller, body: sch.WarehouseIn) -> sch.Warehouse:
    if body.is_default and not body.is_active:
        raise ConflictError("The default warehouse must be active.", code="default_warehouse")
    if body.is_default:
        # one default move at a time (code review F-6)
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('warehouse_default', 0))"))
        await db.execute(text("UPDATE warehouse SET is_default = false, updated_by = CAST(:me AS uuid) WHERE is_default"),
                         {"me": caller.user_id})
    r = await _write_warehouse(db, (
        "INSERT INTO warehouse (code, name, territory_id, is_default, is_active, created_by, updated_by) "
        "VALUES (:c, :n, CAST(:t AS uuid), :d, :a, CAST(:me AS uuid), CAST(:me AS uuid)) RETURNING *"),
        {"c": body.code, "n": body.name, "t": body.territory_id, "d": body.is_default, "a": body.is_active,
         "me": caller.user_id})
    return _warehouse_out(r)


async def update_warehouse(db: AsyncSession, caller: Caller, warehouse_id: str,
                           body: sch.WarehousePatch) -> sch.Warehouse:
    cur = (await db.execute(text("SELECT * FROM warehouse WHERE id = CAST(:w AS uuid) FOR UPDATE"),
                            {"w": warehouse_id})).one_or_none()
    if cur is None:
        raise NotFoundError("No such warehouse.")
    fields = body.model_fields_set
    is_default = body.is_default if "is_default" in fields and body.is_default is not None else cur.is_default
    is_active = body.is_active if "is_active" in fields and body.is_active is not None else cur.is_active
    # the only default never goes away without another taking its place (review B-4)
    if cur.is_default and (not is_default or not is_active):
        raise ConflictError("Make another warehouse the default first.", code="default_warehouse")
    if is_default and not is_active:
        raise ConflictError("The default warehouse must be active.", code="default_warehouse")
    if is_default and not cur.is_default:
        # one default move at a time (code review F-6)
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('warehouse_default', 0))"))
        await db.execute(text("UPDATE warehouse SET is_default = false, updated_by = CAST(:me AS uuid) WHERE is_default"),
                         {"me": caller.user_id})
    r = await _write_warehouse(db, (
        "UPDATE warehouse SET code = :c, name = :n, territory_id = CAST(:t AS uuid), is_default = :d, is_active = :a, "
        "updated_by = CAST(:me AS uuid) WHERE id = CAST(:w AS uuid) RETURNING *"),
        {"c": body.code if "code" in fields and body.code else str(cur.code),
         "n": body.name if "name" in fields and body.name else cur.name,
         "t": body.territory_id if "territory_id" in fields else (None if cur.territory_id is None else str(cur.territory_id)),
         "d": is_default, "a": is_active, "me": caller.user_id, "w": warehouse_id})
    return _warehouse_out(r)


async def check_order_warehouse(db: AsyncSession, caller: Caller, warehouse_id: str | None) -> None:
    """An order's "Order to": staff only, an active warehouse (review edge case 8)."""
    if warehouse_id is None:
        return
    if caller.partner_id is not None or not await may_view(db):
        raise ValidationFailed(fields={"warehouse_id": "not yours to choose"})
    active = (await db.execute(text("SELECT is_active FROM warehouse WHERE id = CAST(:w AS uuid)"),
                               {"w": warehouse_id})).scalar_one_or_none()
    if not active:
        raise ValidationFailed(fields={"warehouse_id": "no such active warehouse"})


# ── movements ───────────────────────────────────────────────────────────────

async def record(db: AsyncSession, body: sch.MovementIn) -> sch.MovementsOut:
    lines = [{"product_id": ln.product_id, "qty": str(ln.qty)} for ln in body.lines]
    if len({ln["product_id"] for ln in lines}) != len(lines):
        raise ValidationFailed(fields={"lines": "one row per product"})
    try:
        async with db.begin_nested():
            out = (await db.execute(text(
                "SELECT stock_record(CAST(:w AS uuid), :k, :r, :n, CAST(:l AS jsonb))"),
                {"w": body.warehouse_id, "k": body.kind, "r": body.reference, "n": body.note,
                 "l": json.dumps(lines)})).scalar_one()
    except DBAPIError as exc:
        mapped = map_error(exc)
        if mapped is exc:
            raise
        raise mapped from exc
    return sch.MovementsOut(movements=[
        sch.MovementOut(id=str(m["id"]), product_id=str(m["product_id"]), qty=_qty(Decimal(str(m["qty"]))),
                        on_hand_after=_qty(Decimal(str(m["on_hand_after"])))) for m in out])


async def movements(db: AsyncSession, *, warehouse_id: str | None, product_id: str | None, limit: int,
                    cursor: str | None) -> sch.MovementPage:
    where: list[str] = ["TRUE"]
    params: dict[str, Any] = {"lim": limit + 1}
    if warehouse_id:
        where.append("m.warehouse_id = CAST(:w AS uuid)")
        params["w"] = warehouse_id
    if product_id:
        where.append("m.product_id = CAST(:p AS uuid)")
        params["p"] = product_id
    if cursor:
        at, mid = _decode_cursor(cursor)
        where.append("(m.created_at, m.id) < (:cat, CAST(:cid AS uuid))")
        params |= {"cat": at, "cid": mid}
    rows = (await db.execute(text(
        "SELECT m.*, m.kind::text AS kind_text, w.code AS w_code, w.name AS w_name, p.item_code, p.description, "
        "u.full_name, d.dispatch_no, o.order_no::text AS order_no FROM stock_movement m "
        "JOIN warehouse w ON w.id = m.warehouse_id JOIN product p ON p.id = m.product_id "
        "LEFT JOIN app_user u ON u.id = m.created_by "
        "LEFT JOIN dispatch_line dl ON dl.id = m.dispatch_line_id LEFT JOIN dispatch d ON d.id = dl.dispatch_id "
        "LEFT JOIN sales_order o ON o.id = d.sales_order_id "
        "WHERE " + " AND ".join(where) + " ORDER BY m.created_at DESC, m.id DESC LIMIT :lim"), params)).all()
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1].created_at, str(page[-1].id)) if len(rows) > limit else None
    return sch.MovementPage(data=[sch.LedgerMovement(
        id=str(r.id), warehouse=sch.WarehouseRef(id=str(r.warehouse_id), code=str(r.w_code), name=r.w_name),
        product=sch.StockProductRef(id=str(r.product_id), code=None if r.item_code is None else str(r.item_code),
                               name=str(r.description)),
        qty=_qty(r.qty), kind=r.kind_text, reference=r.reference, note=r.note, dispatch_no=r.dispatch_no,
        order=r.order_no, created_by=None if r.created_by is None else UserRef(id=str(r.created_by), full_name=r.full_name or ""),
        created_at=r.created_at.isoformat()) for r in page], meta=PageMeta(limit=limit, next_cursor=next_cursor))


# ── the stock list and availability ─────────────────────────────────────────

async def stock_list(db: AsyncSession, *, warehouse_id: str | None, product_id: str | None, short_only: bool,
                     limit: int, cursor: str | None) -> sch.StockPage:
    """Every (warehouse, product) with a movement. The cursor is an offset: the list
    is small (warehouses times products moved) and has no natural time order."""
    where: list[str] = ["TRUE"]
    try:
        offset = int(cursor) if cursor else 0
    except ValueError as exc:
        raise ValidationFailed(fields={"cursor": "malformed cursor"}) from exc
    params: dict[str, Any] = {"lim": limit + 1, "off": max(offset, 0)}
    if warehouse_id:
        where.append("x.warehouse_id = CAST(:w AS uuid)")
        params["w"] = warehouse_id
    if product_id:
        where.append("x.product_id = CAST(:p AS uuid)")
        params["p"] = product_id
    rows = (await db.execute(text(
        "WITH x AS (SELECT DISTINCT warehouse_id, product_id FROM stock_movement), "
        "y AS (SELECT x.warehouse_id, x.product_id, w.code AS w_code, w.name AS w_name, p.item_code, p.description, "
        "u.code AS uom, stock_on_hand(x.warehouse_id, x.product_id) AS on_hand, "
        "stock_committed(x.warehouse_id, x.product_id) AS committed "
        "FROM x JOIN warehouse w ON w.id = x.warehouse_id JOIN product p ON p.id = x.product_id "
        "JOIN uom u ON u.id = p.uom_id WHERE " + " AND ".join(where) + ") "
        "SELECT * FROM y WHERE (NOT :short OR on_hand - committed < 0) "
        "ORDER BY w_code, description, product_id LIMIT :lim OFFSET :off"),
        {**params, "short": short_only})).all()
    page = rows[:limit]
    next_cursor = str(params["off"] + limit) if len(rows) > limit else None
    return sch.StockPage(data=[sch.StockRow(
        warehouse=sch.WarehouseRef(id=str(r.warehouse_id), code=str(r.w_code), name=r.w_name),
        product=sch.StockProductRef(id=str(r.product_id), code=None if r.item_code is None else str(r.item_code),
                               name=str(r.description)),
        on_hand=_qty(Decimal(r.on_hand)), committed=_qty(Decimal(r.committed)),
        available=_qty(Decimal(r.on_hand) - Decimal(r.committed)), uom=str(r.uom)) for r in page],
        meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def _resolve(db: AsyncSession, warehouse_id: str | None) -> str:
    wid = warehouse_id or (await db.execute(text("SELECT stock_default_warehouse()"))).scalar_one_or_none()
    if wid is None:
        raise ConflictError("There is no default warehouse.", code="no_default_warehouse")
    return str(wid)


async def availability(db: AsyncSession, warehouse_id: str | None, product_ids: list[str]) -> sch.Availability:
    wid = await _resolve(db, warehouse_id)
    if (await db.execute(text("SELECT 1 FROM warehouse WHERE id = CAST(:w AS uuid)"), {"w": wid})).first() is None:
        raise NotFoundError("No such warehouse.")
    rows = (await db.execute(text(
        "SELECT p, stock_on_hand(CAST(:w AS uuid), p) AS on_hand, stock_committed(CAST(:w AS uuid), p) AS committed "
        "FROM unnest(CAST(:ps AS uuid[])) AS p"), {"w": wid, "ps": product_ids})).all()
    return sch.Availability(warehouse_id=wid, items=[
        sch.AvailabilityItem(product_id=str(r.p), on_hand=_qty(Decimal(r.on_hand)),
                             available=_qty(Decimal(r.on_hand) - Decimal(r.committed))) for r in rows])


async def order_lines(db: AsyncSession, warehouse_id: str | None,
                      lines: list[tuple[str, str, Decimal]], *, committed: bool) -> dict[str, sch.LineStock]:
    """Per order line (id, product, open qty): the warehouse's availability. Once the
    order is committed (submitted onwards) availability already holds this order, so
    the line is short when it is below zero; a draft's line is short when availability
    is below what it needs (code review F-3). Empty without stock.view."""
    if not lines or not await may_view(db):
        return {}
    wid = warehouse_id or (await db.execute(text("SELECT stock_default_warehouse()"))).scalar_one_or_none()
    if wid is None:
        return {}
    avail = {str(i.product_id): Decimal(i.available) for i in (await availability(db, str(wid), sorted({p for _, p, _ in lines}))).items}
    return {lid: sch.LineStock(available=_qty(avail[pid]), short=(avail[pid] < 0 if committed else avail[pid] < need))
            for lid, pid, need in lines}
