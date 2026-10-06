"""Company settings (FS-036, migration 041). The rule for each value lives on its
row and is enforced by `app_setting_check()`; `app_setting_set()` is the one
writer and records each change. The service reads and maps errors only."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import ForbiddenError, ValidationFailed
from api.schemas import settings as sch


def _out(r: Any) -> sch.Setting:
    # jsonb read as text and parsed here: the driver's own decoding is not relied on
    return sch.Setting(key=r.key, kind=r.kind, value=json.loads(r.value),
                       allowed=json.loads(r.allowed) if r.allowed is not None else None,
                       min=int(r.min) if r.min is not None else None,
                       max=int(r.max) if r.max is not None else None,
                       description=r.description, updated_at=r.updated_at.isoformat())


async def list_settings(db: AsyncSession) -> list[sch.Setting]:
    rows = (await db.execute(text(
        "SELECT key::text AS key, kind, value::text AS value, allowed::text AS allowed, min, max, "
        "description, updated_at "
        "FROM app_setting ORDER BY key"))).all()
    return [_out(r) for r in rows]


async def patch_settings(db: AsyncSession, body: sch.SettingsPatch) -> list[sch.Setting]:
    """All or nothing: a bad value anywhere refuses the whole patch, because the
    caller's transaction rolls back on the error raised here."""
    known = {r for (r,) in (await db.execute(text("SELECT key::text FROM app_setting"))).all()}
    bad: dict[str, str] = {k: "unknown setting" for k in body.values if k not in known}
    if bad:
        raise ValidationFailed(fields=bad)
    for key, value in body.values.items():
        try:
            async with db.begin_nested():
                await db.execute(text("SELECT app_setting_set(:k, CAST(:v AS jsonb))"),
                                 {"k": key, "v": json.dumps(value)})
        except DBAPIError as exc:
            state = str(getattr(exc.orig, "sqlstate", "") or "")
            if state == "42501":
                raise ForbiddenError("Changing settings needs masters.edit.") from exc
            if state == "SETVL":
                message = str(exc.orig).split("\n")[0].split(": ", 1)[-1]
                bad[key] = message.split(": ", 1)[-1] if ": " in message else message
                continue
            raise
    if bad:
        raise ValidationFailed(fields=bad)
    return await list_settings(db)
