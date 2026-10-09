"""The consumer portal (FS-044, migration 052). Every read is a definer keyed on
`portal_customer()`, so nothing here can name another farmer's rows; the service
only refuses the wrong caller and shapes the answer. Services never commit."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.config import get_settings
from api.domain import quotations as quote_domain
from api.errors import ForbiddenError
from api.schemas import portal as sch


async def _customer(db: AsyncSession, caller: Caller) -> str:
    if caller.user_type != "consumer":
        raise ForbiddenError("The portal is for farmers.", code="not_a_consumer")
    cid = (await db.execute(text("SELECT portal_customer()"))).scalar_one_or_none()
    if cid is None:
        raise ForbiddenError("The portal is switched off.", code="portal_off")
    return str(cid)


async def _json(db: AsyncSession, fn: str) -> Any:
    raw = (await db.execute(text(f"SELECT {fn}()"))).scalar_one()
    # parse_float: totals stay Decimal (rule 4, code review F-4)
    return json.loads(raw if isinstance(raw, str) else json.dumps(raw), parse_float=Decimal)


def _money(v: Any) -> str | None:
    return None if v is None else str(Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP))


async def me(db: AsyncSession, caller: Caller) -> sch.PortalMe:
    await _customer(db, caller)
    return sch.PortalMe(**await _json(db, "portal_me"))


async def set_consent(db: AsyncSession, caller: Caller, body: sch.PortalConsent) -> sch.PortalMe:
    await _customer(db, caller)
    try:
        await db.execute(text("SELECT portal_set_consent(:g)"), {"g": body.consent_given})
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "42501":
            raise ForbiddenError("The portal is switched off.", code="portal_off") from exc
        raise
    return await me(db, caller)


async def enquiries(db: AsyncSession, caller: Caller) -> list[sch.PortalEnquiry]:
    await _customer(db, caller)
    return [sch.PortalEnquiry(**x) for x in await _json(db, "portal_enquiries")]


async def quotations(db: AsyncSession, caller: Caller) -> list[sch.PortalQuotation]:
    await _customer(db, caller)
    base = get_settings().public_web_url
    out = []
    for x in await _json(db, "portal_quotations"):
        token = x.pop("share_token", None)
        out.append(sch.PortalQuotation(**{**x, "total": _money(x.get("total"))},
                                       link=quote_domain.share_url(base, token) if token else None))
    return out


async def orders(db: AsyncSession, caller: Caller) -> list[sch.PortalOrder]:
    await _customer(db, caller)
    return [sch.PortalOrder(**{**x, "total": _money(x.get("total"))})
            for x in await _json(db, "portal_orders")]


async def complaints(db: AsyncSession, caller: Caller) -> list[sch.PortalComplaint]:
    await _customer(db, caller)
    return [sch.PortalComplaint(**x) for x in await _json(db, "portal_complaints")]
