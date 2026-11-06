"""Holidays (FS-028, migration 048). The rules live in `holiday_add` and
`holiday_remove`; the service reads and maps their refusals."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import holidays as sch


def _refusal(exc: DBAPIError, *, removing: bool) -> Exception | None:
    state = str(getattr(exc.orig, "sqlstate", "") or "")
    if state == "42501":
        return ForbiddenError("Holidays are kept by those who edit the masters.")
    if state == "HOLPS":
        if removing:
            return ConflictError("A past holiday stays: it explains targets already set.",
                                 code="holiday_in_past")
        return ValidationFailed("A holiday must be after today.", code="holiday_in_past",
                                fields={"day": "today or earlier"})
    if state == "HOLSU":
        return ValidationFailed("Sunday is already closed.", code="holiday_sunday",
                                fields={"day": "a Sunday"})
    if state == "HOLEX":
        return ConflictError("That day is already a holiday.", code="holiday_exists")
    if state == "HOLNF":
        return NotFoundError("No such holiday.")
    if state == "22023":
        return ValidationFailed("Name the holiday in 1 to 80 characters.",
                                fields={"name": "invalid"})
    return None


async def _call(db: AsyncSession, sql: str, params: dict[str, Any], *, removing: bool) -> None:
    try:
        async with db.begin_nested():
            await db.execute(text(sql), params)
    except DBAPIError as exc:
        mapped = _refusal(exc, removing=removing)
        if mapped is None:
            raise
        raise mapped from exc


async def list_holidays(db: AsyncSession, year: int | None) -> list[sch.Holiday]:
    rows = (await db.execute(text(
        "SELECT day, name FROM holiday WHERE CAST(:y AS int) IS NULL "
        "OR extract(year FROM day) = CAST(:y AS int) ORDER BY day"), {"y": year})).all()
    return [sch.Holiday(day=r.day, name=r.name) for r in rows]


async def add_holiday(db: AsyncSession, body: sch.HolidayIn) -> sch.Holiday:
    await _call(db, "SELECT holiday_add(:d, :n)", {"d": body.day, "n": body.name}, removing=False)
    # as stored: the definer trims with btrim, which is not Python's strip (code review F-5)
    r = (await db.execute(text("SELECT day, name FROM holiday WHERE day = :d"),
                          {"d": body.day})).one()
    return sch.Holiday(day=r.day, name=r.name)


async def remove_holiday(db: AsyncSession, day: dt.date) -> None:
    await _call(db, "SELECT holiday_remove(:d)", {"d": day}, removing=True)
