"""Ratings (FS-043, migration 051).

Who may rate, and what, is `rating_record()`'s to decide; reads go through the
order's and the complaint's own policies. The dealer rating is `dealer_rating()`:
one gate, then the same figures for every reader. Services never commit.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import ratings as sch
from api.schemas.leads import PageMeta
from api.services import people
from api.services.leads import _decode_cursor, _encode_cursor
from api.services.users import _pg_text, _sqlstate


def _refusal(exc: DBAPIError, *, card: bool = False) -> Exception:
    code, msg = _sqlstate(exc), _pg_text(exc)
    if code == "42501":
        if card:
            return ForbiddenError("The dealer rating is for staff who see payments.",
                                  code="rating_not_permitted")
        return ForbiddenError("Not permitted to rate this.")
    if code == "RTGNF":
        return NotFoundError("No such document.")
    if code == "RTGNY":
        return ForbiddenError("A dealer rates its own orders and complaints.",
                              code="not_your_order")
    if code == "RTGNR":
        return ValidationFailed(msg.split("\n", 1)[0] + ".", code="not_rateable")
    if code == "RTGPS":
        return ValidationFailed("That product has not shipped on this order.",
                                code="product_not_shipped", fields={"product_id": "not shipped"})
    if code == "RTGEX":
        return ConflictError("This has been rated already.", code="rating_exists")
    if code in ("RTGSC", "RTGCM", "RTGTG"):
        return ValidationFailed(fields={"rating": msg.split("\n", 1)[0]})
    return exc


_SELECT = """
SELECT r.id::text AS id, r.target, r.score, r.comment, r.rated_by, r.entered_by,
       r.partner_id, r.lead_id, l.inquiry_no::text AS inquiry_no,
       r.sales_order_id, o.order_no::text AS order_no, o.status::text AS order_status,
       r.complaint_id, c.complaint_no::text AS complaint_no, c.status::text AS complaint_status,
       r.product_id, p.description::text AS product_name, r.created_at
  FROM rating r
  LEFT JOIN lead l ON l.id = r.lead_id
  LEFT JOIN sales_order o ON o.id = r.sales_order_id
  LEFT JOIN complaint c ON c.id = r.complaint_id
  LEFT JOIN product p ON p.id = r.product_id
"""


def _out(r: Any, names: people.Names, *, portal: bool) -> sch.Rating:
    # rule 14: a dealer reads a customer's rating as the score only (GAP-375)
    hide = portal and r.rated_by == "customer"
    return sch.Rating(
        id=r.id, target=r.target, score=r.score, comment=None if hide else r.comment,
        rated_by=r.rated_by, entered_by=None if hide else names.user(r.entered_by, None),
        partner=names.partner(r.partner_id, None, None),
        lead=sch.RatingLead(id=str(r.lead_id), inquiry_no=r.inquiry_no) if r.lead_id else None,
        order=(sch.RatingDoc(id=str(r.sales_order_id), number=r.order_no,
                             status=r.order_status or "") if r.sales_order_id else None),
        complaint=(sch.RatingDoc(id=str(r.complaint_id), number=r.complaint_no,
                              status=r.complaint_status or "") if r.complaint_id else None),
        product=(sch.RatingProduct(id=str(r.product_id), description=r.product_name or "")
                 if r.product_id else None),
        created_at=r.created_at.isoformat())


def _not_staff(caller: Caller) -> bool:
    """A consumer has no partner either (FS-044), so `partner_id is None` is not
    "staff" (code review F-6)."""
    return caller.user_type != "staff"


async def _names(db: AsyncSession, rows: list[Any]) -> people.Names:
    return await people.resolve_ids(db, {str(r.entered_by) for r in rows},
                                    {str(r.partner_id) for r in rows if r.partner_id})


async def record(db: AsyncSession, caller: Caller, body: sch.RatingCreate) -> sch.Rating:
    try:
        async with db.begin_nested():
            rating_id: Any = (await db.execute(text(
                "SELECT rating_record(:t, CAST(:o AS uuid), CAST(:c AS uuid), "
                "CAST(:p AS uuid), :s, :m)"),
                {"t": body.target, "o": body.sales_order_id, "c": body.complaint_id,
                 "p": body.product_id, "s": body.score, "m": body.comment})).scalar_one()
    except DBAPIError as exc:
        raise _refusal(exc) from exc
    row = (await db.execute(text(_SELECT + " WHERE r.id = CAST(:i AS uuid)"),
                            {"i": str(rating_id)})).one()
    return _out(row, await _names(db, [row]), portal=_not_staff(caller))


async def list_ratings(db: AsyncSession, caller: Caller, *, target: str | None = None,
                       partner_id: str | None = None, product_id: str | None = None,
                       lead_id: str | None = None, sales_order_id: str | None = None,
                       complaint_id: str | None = None, start: dt.date | None = None,
                       end: dt.date | None = None, max_score: int | None = None,
                       limit: int = 50, cursor: str | None = None) -> sch.RatingPage:
    where = ["true"]
    params: dict[str, Any] = {"lim": limit + 1}
    for col, val in (("r.target", target), ("r.partner_id", partner_id),
                     ("r.product_id", product_id), ("r.sales_order_id", sales_order_id),
                     ("r.complaint_id", complaint_id)):
        if val is not None:
            key = col.split(".")[1]
            where.append(f"{col} = CAST(:{key} AS {'text' if key == 'target' else 'uuid'})")
            params[key] = val
    if lead_id:
        # a lead merged into this one keeps its ratings under its own id (edge 19)
        where.append("(r.lead_id = CAST(:lead AS uuid) OR r.lead_id IN "
                     "(SELECT id FROM lead WHERE merged_into_id = CAST(:lead AS uuid)))")
        params["lead"] = lead_id
    if start:
        where.append("(r.created_at AT TIME ZONE 'Asia/Kolkata')::date >= :start")
        params["start"] = start
    if end:
        where.append("(r.created_at AT TIME ZONE 'Asia/Kolkata')::date <= :end")
        params["end"] = end
    if max_score:
        where.append("r.score <= :maxs")
        params["maxs"] = max_score
    if cursor:
        at, rid = _decode_cursor(cursor)
        where.append("(r.created_at, r.id) < (:cat, CAST(:cid AS uuid))")
        params.update(cat=at, cid=rid)
    rows = list((await db.execute(text(
        _SELECT + f" WHERE {' AND '.join(where)} ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"),
        params)).all())
    more = len(rows) > limit
    rows = rows[:limit]
    names = await _names(db, rows)
    portal = _not_staff(caller)
    return sch.RatingPage(
        data=[_out(r, names, portal=portal) for r in rows],
        meta=PageMeta(limit=limit, next_cursor=_encode_cursor(rows[-1].created_at, rows[-1].id)
                      if more and rows else None))


async def summary(db: AsyncSession, *, group_by: str, start: dt.date | None = None,
                  end: dt.date | None = None) -> list[sch.SummaryRow]:
    col = {"partner": "r.partner_id::text", "product": "r.product_id::text",
           "target": "r.target"}[group_by]
    where = [f"{col} IS NOT NULL"]
    params: dict[str, Any] = {}
    if start:
        where.append("(r.created_at AT TIME ZONE 'Asia/Kolkata')::date >= :start")
        params["start"] = start
    if end:
        where.append("(r.created_at AT TIME ZONE 'Asia/Kolkata')::date <= :end")
        params["end"] = end
    rows = (await db.execute(text(
        f"SELECT {col} AS k, count(*) AS n, round(avg(r.score), 2) AS a, "
        f"count(*) FILTER (WHERE r.score <= 2) AS low FROM rating r "
        f"WHERE {' AND '.join(where)} GROUP BY 1 ORDER BY 3, 2 DESC"), params)).all()
    names: dict[str, str] = {}
    if group_by == "partner" and rows:
        found = await people.resolve_ids(db, (), [r.k for r in rows])
        names = {k: v[0] for k, v in found.partners.items()}
    elif group_by == "product" and rows:
        # a product deleted after it was rated still names itself (edge 12)
        names = {str(r.id): r.d for r in (await db.execute(text(
            "SELECT id, description::text AS d FROM product WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [r.k for r in rows]})).all()}
    return [sch.SummaryRow(key=sch.SummaryKey(id=r.k, name=names.get(r.k, r.k)), count=r.n,
                           average=f"{Decimal(r.a):.2f}", low=r.low) for r in rows]


async def dealer_rating(db: AsyncSession, partner_id: str) -> sch.DealerRating:
    try:
        async with db.begin_nested():
            r = (await db.execute(text("SELECT * FROM dealer_rating(CAST(:p AS uuid))"),
                                  {"p": partner_id})).one()
    except DBAPIError as exc:
        raise _refusal(exc, card=True) from exc

    def one(v: Any) -> str | None:
        return None if v is None else f"{Decimal(v):.1f}"

    return sch.DealerRating(
        partner_id=partner_id, on=r.on_day.isoformat(), window_days=r.window_days,
        orders=r.orders, paid_orders=r.paid_orders, payment_days=one(r.payment_days),
        payment_score=r.payment_score, order_value=f"{Decimal(r.order_value):.2f}",
        value_score=r.value_score, rating=one(r.rating),
        feedback=sch.Feedback(count=r.feedback_count,
                              average=None if r.feedback_average is None
                              else f"{Decimal(r.feedback_average):.2f}"))
