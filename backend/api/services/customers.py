"""The customer record (FS-041, migration 050).

A customer is visible exactly when one of its leads is (customer_sel), and the page
lists only what the caller can see on it: its leads, their quotations and orders,
each under its own policies. The timeline is each visible lead's own timeline,
merged, so every per-lead hiding rule holds. Services never commit."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.errors import ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import customers as sch
from api.schemas.leads import PageMeta, TerritoryRef
from api.services import leads as lead_service
from api.services.leads import _decode_cursor, _encode_cursor, _id_list

_MAX = 100

_SELECT = """
SELECT c.id::text AS id, c.customer_type, c.name, c.mobile, c.email::text AS email,
       c.territory_id, t.name AS territory_name, t.level::text AS territory_level, c.village,
       c.address, c.survey_no, c.consent_given_at, c.consent_channel, c.created_at, c.updated_at
  FROM customer c
  LEFT JOIN territory t ON t.id = c.territory_id"""


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _out(r: Any, lead_count: int) -> sch.Customer:
    return sch.Customer(
        id=r.id, customer_type=r.customer_type, name=r.name, mobile=r.mobile, email=r.email,
        territory=(TerritoryRef(id=str(r.territory_id), name=r.territory_name, level=r.territory_level)
                   if r.territory_id else None),
        village=r.village, address=r.address, survey_no=r.survey_no,
        consent_given_at=_iso(r.consent_given_at), consent_channel=r.consent_channel,
        lead_count=lead_count, created_at=r.created_at.isoformat(), updated_at=r.updated_at.isoformat())


async def _lead_counts(db: AsyncSession, ids: list[str]) -> dict[str, int]:
    """One aggregate over the visible leads (edge case 21)."""
    if not ids:
        return {}
    rows = (await db.execute(text(
        "SELECT customer_id::text AS k, count(*) AS n FROM lead "
        "WHERE customer_id = ANY(CAST(:i AS uuid[])) AND deleted_at IS NULL AND stage <> 'merged' "
        "GROUP BY customer_id"), {"i": ids})).all()
    return {r.k: int(r.n) for r in rows}


async def list_customers(db: AsyncSession, caller: Caller, *, q: str | None = None,
                         territory_id: str | None = None, limit: int = 50,
                         cursor: str | None = None) -> sch.CustomerPage:
    """Newest first by (created_at, id). RLS shows a customer with a visible lead; the
    area filter goes through those leads, as lead_count does (edge case 11)."""
    limit = max(1, min(limit, _MAX))
    where: list[str] = ["true"]
    params: dict[str, Any] = {"lim": limit + 1}
    if q:
        q = q.strip()
        if len(q) < 3:
            raise ValidationFailed(fields={"q": "at least 3 characters"})
        digits = re.sub(r"\D", "", q)
        where.append("(strpos(lower(c.name), lower(:q)) > 0"
                     + (" OR strpos(c.mobile, :d) > 0)" if len(digits) >= 3 else ")"))
        params |= {"q": q, "d": digits}
    if territory_id:
        where.append("EXISTS (SELECT 1 FROM lead l WHERE l.customer_id = c.id AND l.deleted_at IS NULL "
                     "AND l.territory_id IN (SELECT descendant_id FROM territory_closure "
                     "WHERE ancestor_id = ANY(CAST(:areas AS uuid[]))))")
        params["areas"] = _id_list(territory_id, "territory_id")
    if cursor:
        at, cid = _decode_cursor(cursor)
        where.append("(c.created_at, c.id) < (:cat, CAST(:cid AS uuid))")
        params |= {"cat": at, "cid": cid}
    rows = (await db.execute(text(
        _SELECT + " WHERE " + " AND ".join(where) + " ORDER BY c.created_at DESC, c.id DESC LIMIT :lim"),
        params)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
    counts = await _lead_counts(db, [r.id for r in rows])
    return sch.CustomerPage(data=[_out(r, counts.get(r.id, 0)) for r in rows],
                            meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def _row(db: AsyncSession, customer_id: str) -> Any:
    r = (await db.execute(text(_SELECT + " WHERE c.id = CAST(:i AS uuid)"), {"i": customer_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such customer.")
    return r


async def get_customer(db: AsyncSession, caller: Caller, customer_id: str) -> sch.CustomerDetail:
    r = await _row(db, customer_id)
    leads = (await db.execute(text(
        "SELECT l.id::text AS id, l.inquiry_no::text AS inquiry_no, l.stage::text AS stage, "
        "src.code::text AS source, cmp.name::text AS campaign_name, l.created_at "
        "FROM lead l JOIN lead_source src ON src.id = l.lead_source_id "
        "LEFT JOIN campaign cmp ON cmp.id = l.campaign_id "
        "WHERE l.customer_id = CAST(:i AS uuid) AND l.deleted_at IS NULL "
        "ORDER BY l.created_at DESC, l.id DESC LIMIT 100"), {"i": customer_id})).all()
    ids = [x.id for x in leads]
    quotes = (await db.execute(text(
        "SELECT id::text AS id, quote_no::text AS quote_no, status::text AS status, total, "
        "lead_id::text AS lead_id, sent_at FROM quotation "
        "WHERE lead_id = ANY(CAST(:l AS uuid[])) AND deleted_at IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT 100"), {"l": ids})).all()
    orders = (await db.execute(text(
        "SELECT id::text AS id, order_no::text AS order_no, status::text AS status, total, "
        "lead_id::text AS lead_id, submitted_at FROM sales_order "
        "WHERE lead_id = ANY(CAST(:l AS uuid[])) AND deleted_at IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT 100"), {"l": ids})).all()
    counts = await _lead_counts(db, [r.id])
    base = _out(r, counts.get(r.id, 0))
    return sch.CustomerDetail(
        **base.model_dump(),
        leads=[sch.CustomerLead(id=x.id, inquiry_no=x.inquiry_no, stage=x.stage, source=x.source,
                                campaign_name=x.campaign_name, created_at=x.created_at.isoformat())
               for x in leads],
        quotations=[sch.CustomerQuotation(id=x.id, quote_no=x.quote_no, status=x.status,
                                          total=str(x.total), lead_id=x.lead_id, sent_at=_iso(x.sent_at))
                    for x in quotes],
        orders=[sch.CustomerOrder(id=x.id, order_no=x.order_no, status=x.status, total=str(x.total),
                                  lead_id=x.lead_id, submitted_at=_iso(x.submitted_at))
                for x in orders])


async def timeline(db: AsyncSession, caller: Caller, customer_id: str, *, limit: int = 50,
                   cursor: str | None = None) -> sch.CustomerTimeline:
    """Each visible lead's own timeline (its filters and hiding rules), merged with the
    customer's own events, newest first by (occurred_at, id). An event folded into two
    leads by a merge appears once (edge case 10)."""
    limit = max(1, min(limit, _MAX))
    await _row(db, customer_id)
    # live leads first, so an event folded into a survivor carries the survivor's label;
    # capped like the page (plan review note 4)
    leads = (await db.execute(text(
        "SELECT id::text AS id, inquiry_no::text AS inquiry_no FROM lead "
        "WHERE customer_id = CAST(:i AS uuid) AND deleted_at IS NULL "
        "ORDER BY (stage = 'merged'), created_at, id LIMIT 100"), {"i": customer_id})).all()
    seen: dict[str, tuple[datetime, sch.CustomerTimelineEvent]] = {}
    more = False
    for lead in leads:
        page = await lead_service.timeline(db, caller, lead.id, limit=limit, cursor=cursor)
        # a source cut short means more history, even when the merged page is exactly full
        # (plan review B-1)
        more = more or page.meta.next_cursor is not None
        for e in page.data:
            if e.id not in seen:
                seen[e.id] = (datetime.fromisoformat(e.occurred_at), sch.CustomerTimelineEvent(
                    **e.model_dump(), lead_id=lead.id, inquiry_no=lead.inquiry_no))
    where = ""
    params: dict[str, Any] = {"i": customer_id, "lim": limit + 1}
    if cursor:
        at, eid = _decode_cursor(cursor)
        where = " AND (occurred_at, id) < (:bat, CAST(:bid AS uuid))"
        params |= {"bat": at, "bid": eid}
    own = (await db.execute(text(
        "SELECT id::text AS id, kind, occurred_at, payload FROM activity_event "
        "WHERE entity_type = 'customer' AND customer_id = CAST(:i AS uuid)" + where +
        " ORDER BY occurred_at DESC, id DESC LIMIT :lim"), params)).all()
    more = more or len(own) > limit
    for o in own[:limit]:
        payload = o.payload if isinstance(o.payload, dict) else json.loads(o.payload or "{}")
        seen.setdefault(o.id, (o.occurred_at, sch.CustomerTimelineEvent(
            id=o.id, kind=o.kind, occurred_at=o.occurred_at.isoformat(), payload=payload)))
    ordered = sorted(seen.values(), key=lambda kv: (kv[0], kv[1].id), reverse=True)
    page_rows = ordered[:limit]
    next_cursor = (_encode_cursor(page_rows[-1][0], page_rows[-1][1].id)
                   if page_rows and (more or len(ordered) > limit) else None)
    return sch.CustomerTimeline(data=[e for _, e in page_rows],
                                meta=PageMeta(limit=limit, next_cursor=next_cursor))


_FIELDS = ("customer_type", "name", "email", "territory_id", "village", "address", "survey_no")
_REQUIRED = frozenset({"customer_type", "name"})


async def patch_customer(db: AsyncSession, caller: Caller, customer_id: str,
                         body: sch.CustomerPatch) -> sch.CustomerDetail:
    if caller.partner_id is not None:
        raise ForbiddenError("Customers are edited by staff.")
    fields = body.model_fields_set
    if not fields:
        raise ValidationFailed(fields={"body": "nothing to change"})
    for f in fields & _REQUIRED:
        if getattr(body, f) is None:
            raise ValidationFailed(fields={f: "cannot be cleared"})
    if "consent_given" in fields and body.consent_given is None:
        raise ValidationFailed(fields={"consent_given": "true or false"})
    if "consent_channel" in fields and body.consent_given is not True:
        raise ValidationFailed(fields={"consent_channel": "only with consent_given: true"})
    if body.consent_given is True and body.consent_channel is None:
        raise ValidationFailed(fields={"consent_channel": "required with consent_given: true"})
    await _row(db, customer_id)
    row = (await db.execute(text(
        "SELECT customer_type, name, email::text AS email, territory_id::text AS territory_id, village, "
        "address, survey_no, consent_given_at, consent_channel FROM customer "
        "WHERE id = CAST(:i AS uuid) FOR UPDATE"), {"i": customer_id})).one_or_none()
    if row is None:      # visible, but the UPDATE policy refuses: leads.edit is missing
        raise ForbiddenError("Editing a customer needs leads.edit.")
    old = {f: getattr(row, f) for f in _FIELDS}
    new = {**old, **{f: getattr(body, f) for f in fields if f in _FIELDS}}
    changed: dict[str, Any] = {f: new[f] for f in _FIELDS if new[f] != old[f]}
    before_after = {f: {"from": old[f], "to": v} for f, v in changed.items()}
    if "territory_id" in changed and new["territory_id"] is not None:
        live = (await db.execute(text(
            "SELECT 1 FROM territory WHERE id = CAST(:t AS uuid) AND deleted_at IS NULL"),
            {"t": new["territory_id"]})).first()
        if live is None:     # the FK would answer 500 (code review F-1)
            raise ValidationFailed(fields={"territory_id": "not found"})
        await lead_service.check_lead_territory(db, new["territory_id"])
    consent_sql = ""
    consent: dict[str, Any] = {}
    if body.consent_given is True and row.consent_channel != body.consent_channel:
        consent_sql = ", consent_given_at = now(), consent_channel = :ch"
        consent = {"consent": {"from": row.consent_channel, "to": body.consent_channel,
                               "was_given_at": _iso(row.consent_given_at)}}
    elif body.consent_given is False and row.consent_given_at is not None:
        consent_sql = ", consent_given_at = NULL, consent_channel = NULL"
        consent = {"consent": {"from": row.consent_channel, "to": None,
                               "was_given_at": _iso(row.consent_given_at)}}
    if not changed and not consent:
        return await get_customer(db, caller, customer_id)
    await db.execute(text(
        "UPDATE customer SET customer_type = :customer_type, name = :name, email = :email, "
        "territory_id = CAST(:territory_id AS uuid), village = :village, address = :address, "
        "survey_no = :survey_no, updated_by = CAST(:me AS uuid)" + consent_sql +
        " WHERE id = CAST(:i AS uuid)"),
        {**new, "ch": body.consent_channel, "me": caller.user_id, "i": customer_id})
    # CLAUDE.md 4.1 rule 7; customer events carry customer_id only, never lead_id
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, customer_id, kind, actor_id, payload) "
        "VALUES ('customer', CAST(:i AS uuid), CAST(:i AS uuid), 'customer.updated', CAST(:me AS uuid), "
        "CAST(:p AS jsonb) || jsonb_build_object('actor_name', "
        "coalesce((SELECT full_name FROM app_user WHERE id = CAST(:me AS uuid)), '')))"),
        {"i": customer_id, "me": caller.user_id,
         "p": json.dumps({"name": new["name"], "changed": before_after, **consent})})
    return await get_customer(db, caller, customer_id)
