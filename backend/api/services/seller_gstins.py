"""Seller GSTINs and their LUTs (FS-042 rule 4).

A LUT is a master: effective-dated, never edited (CLAUDE.md 4.1 rule 10). It
writes `audit_row()`, not an `activity_event` (FS-010 rule 15). Overlaps are the
exclusion constraint's to refuse; a LUT a document carries is the definer's.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import seller_gstins as sch
from api.services.users import _pg_text, _sqlstate


def _fy(day: dt.date) -> int:
    return day.year if day.month >= 4 else day.year - 1


def _refusal(exc: DBAPIError) -> Exception:
    code, msg = _sqlstate(exc), _pg_text(exc)
    if code == "42501":
        return ForbiddenError("Not permitted.")
    if code == "LUTNF":
        return NotFoundError("No such LUT.")
    if code == "LUTUS":
        return ConflictError("A quotation or order carries this LUT, so it stays.",
                             code="lut_in_use")
    if code == "23P01":
        return ConflictError("Another LUT of this registration covers some of these dates.",
                             code="lut_overlap")
    if code == "23505" and "uq_seller_gstin_lut_arn" in msg:
        return ConflictError("This registration already has a LUT with that ARN.",
                             code="lut_duplicate")
    return exc


async def _call(db: AsyncSession, sql: str, params: dict[str, Any]) -> Any:
    try:
        async with db.begin_nested():
            return (await db.execute(text(sql), params)).scalar_one_or_none()
    except DBAPIError as exc:
        raise _refusal(exc) from exc


async def list_gstins(db: AsyncSession) -> list[sch.SellerGstin]:
    gstins = (await db.execute(text(
        "SELECT g.id::text AS id, g.gstin::text AS gstin, g.legal_name, "
        "t.code::text AS state_code, "
        "g.is_default, g.is_active FROM seller_gstin g "
        "JOIN territory t ON t.id = g.state_territory_id "
        "WHERE g.deleted_at IS NULL ORDER BY g.is_default DESC, g.gstin"))).all()
    luts = (await db.execute(text(
        "SELECT l.id::text AS id, l.seller_gstin_id::text AS gstin_id, l.arn, l.valid_from, "
        "l.valid_to, seller_gstin_lut_in_use(l.id) AS in_use "
        "FROM seller_gstin_lut l ORDER BY l.valid_from DESC"))).all()
    by_gstin: dict[str, list[sch.Lut]] = {}
    for r in luts:
        by_gstin.setdefault(r.gstin_id, []).append(sch.Lut(
            id=r.id, arn=r.arn, valid_from=r.valid_from, valid_to=r.valid_to, in_use=r.in_use))
    return [sch.SellerGstin(id=g.id, gstin=g.gstin, legal_name=g.legal_name,
                            state_code=g.state_code, is_default=g.is_default,
                            is_active=g.is_active, luts=by_gstin.get(g.id, []))
            for g in gstins]


async def add_lut(db: AsyncSession, gstin_id: str, body: sch.LutCreate) -> sch.Lut:
    if body.valid_to < body.valid_from or _fy(body.valid_from) != _fy(body.valid_to):
        raise ValidationFailed("A LUT covers part or all of one financial year, 1 April to "
                               "31 March.", code="lut_dates",
                               fields={"valid_to": "same financial year as valid_from"})
    found = (await db.execute(text(
        "SELECT 1 FROM seller_gstin WHERE id = CAST(:g AS uuid) AND deleted_at IS NULL"),
        {"g": gstin_id})).scalar_one_or_none()
    if found is None:
        raise NotFoundError("No such seller registration.")
    lut_id = await _call(db, (
        "INSERT INTO seller_gstin_lut (seller_gstin_id, arn, valid_from, valid_to, created_by) "
        "VALUES (CAST(:g AS uuid), :arn, :f, :t, app_current_user_id()) RETURNING id::text"),
        {"g": gstin_id, "arn": body.arn, "f": body.valid_from, "t": body.valid_to})
    return sch.Lut(id=lut_id, arn=body.arn, valid_from=body.valid_from, valid_to=body.valid_to,
                   in_use=False)


async def delete_lut(db: AsyncSession, gstin_id: str, lut_id: str) -> None:
    owner = (await db.execute(text(
        "SELECT seller_gstin_id::text FROM seller_gstin_lut WHERE id = CAST(:l AS uuid)"),
        {"l": lut_id})).scalar_one_or_none()
    if owner != gstin_id:
        raise NotFoundError("No such LUT.")
    await _call(db, "SELECT seller_gstin_lut_delete(CAST(:l AS uuid))", {"l": lut_id})
