"""The approval engine's API side (FS-011 4): the queue, a chain, a decision, and
the thresholds.

Every decision goes through `record_decision()`, a definer that takes the actor
from the claim and re-checks what a policy would (RBAC 5.2c); this module never
writes an approval row. The queue is `approval_queue()`, counted as the owner with
the caller's eligibility applied, because a manager's queue reads requests their
own RLS may not show.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.errors import NotFoundError, ValidationFailed
from api.schemas import orders as sch
from api.schemas.leads import PageMeta, TerritoryRef
from api.services import orders as order_service
from api.services import people
from api.services.leads import _decode_cursor, _encode_cursor

_MAX_LIMIT = 100


def _iso(v: Any) -> str | None:
    return None if v is None else v.isoformat()


_TOTAL_CEILING = 1000


async def queue(db: AsyncSession, caller: Caller, *, include_below: bool = False,
                limit: int = 50, cursor: str | None = None,
                include_total: bool = False) -> sch.QueuePage:
    limit = max(1, min(limit, _MAX_LIMIT))
    before_at, before_id = (None, None)
    if cursor:
        before_at, before_id = _decode_cursor(cursor)
    rows = (await db.execute(text(
        "SELECT * FROM approval_queue(CAST(:bat AS timestamptz), CAST(:bid AS uuid), "
        ":lim, :below)"),
        {"bat": before_at, "bid": before_id, "lim": limit + 1, "below": include_below})).all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.waiting_since, str(last.step_id))
        rows = rows[:limit]
    total, capped = None, False
    if include_total:
        # the badge: the same queue, counted to a ceiling (ISS-097 is its cost)
        counted = len((await db.execute(text(
            "SELECT 1 FROM approval_queue(NULL, NULL, :lim, :below)"),
            {"lim": _TOTAL_CEILING + 1, "below": include_below})).all())
        total, capped = min(counted, _TOTAL_CEILING), counted > _TOTAL_CEILING
    if not rows:
        return sch.QueuePage(data=[], meta=PageMeta(limit=limit, next_cursor=None,
                                                    total=total, total_capped=capped))
    # the approver can see every order in their queue (approval_refusal() checks
    # order_visible()), so the documents read under their own RLS
    docs = {str(d.id): d for d in (await db.execute(text(
        "SELECT o.id, o.order_no::text AS order_no, o.party_name, o.total, o.is_provisional, "
        "o.created_by, u.full_name, o.submitted_at, o.created_at FROM sales_order o "
        "LEFT JOIN app_user u ON u.id = o.created_by WHERE o.id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": [str(r.entity_id) for r in rows]})).all()}
    names = await people.resolve(db, list(docs.values()), [("created_by", "full_name")])
    data = []
    for r in rows:
        d = docs.get(str(r.entity_id))
        if d is None:
            continue
        data.append(sch.QueueRow(
            step_id=str(r.step_id), seq=r.seq, role=r.role_code, stalled=r.stalled,
            doc_type=r.doc_type,
            document=sch.QueueDocument(
                id=str(d.id), number=d.order_no, party_name=d.party_name,
                total=f"{d.total:.2f}", is_provisional=d.is_provisional,
                raised_by=names.user(d.created_by, d.full_name),
                raised_at=(d.submitted_at or d.created_at).isoformat()),
            waiting_since=r.waiting_since.isoformat()))
    return sch.QueuePage(data=data, meta=PageMeta(limit=limit, next_cursor=next_cursor,
                                                  total=total, total_capped=capped))


async def get_request(db: AsyncSession, caller: Caller, request_id: str) -> sch.Approval:
    row = (await db.execute(text(
        "SELECT entity_id FROM approval_request WHERE id = CAST(:r AS uuid)"),
        {"r": request_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such approval.")
    # the order's visibility decides, as it does for the order itself
    await order_service.get_order(db, caller, str(row.entity_id))
    approval, _ = await order_service._approval(db, str(row.entity_id),
                                                caller.partner_id is not None, request_id)
    if approval is None:
        raise NotFoundError("No such approval.")
    return approval


async def decide(db: AsyncSession, caller: Caller, step_id: str,
                 body: sch.DecisionRequest) -> sch.Order:
    entity = (await db.execute(text(
        "SELECT q.entity_id FROM approval_step s JOIN approval_request q ON q.id = s.request_id "
        "WHERE s.id = CAST(:s AS uuid)"), {"s": step_id})).scalar_one_or_none()
    if entity is None:
        raise NotFoundError("No such approval step.")
    try:
        await db.execute(text("SELECT record_decision(CAST(:s AS uuid), :d, :r)"),
                         {"s": step_id, "d": body.decision, "r": body.remark})
    except DBAPIError as exc:
        raise order_service.map_db_error(exc) from exc
    return await order_service.get_order(db, caller, str(entity))


async def thresholds(db: AsyncSession) -> list[sch.Threshold]:
    rows = (await db.execute(text(
        "SELECT t.doc_type, r.code::text AS role, t.territory_id, tt.name, "
        "tt.level::text AS level, "
        "t.max_amount FROM approval_threshold t JOIN role r ON r.id = t.role_id "
        "LEFT JOIN territory tt ON tt.id = t.territory_id WHERE t.deleted_at IS NULL "
        "ORDER BY t.doc_type, r.level, tt.name NULLS FIRST"))).all()
    return [sch.Threshold(
        doc_type=r.doc_type, role=r.role,
        territory=(TerritoryRef(id=str(r.territory_id), name=r.name, level=r.level)
                   if r.territory_id else None),
        max_amount=f"{r.max_amount:.2f}" if r.max_amount is not None else None) for r in rows]


_LEVEL = {"district_manager": 2, "state_manager": 3, "regional_manager": 4}


async def put_threshold(db: AsyncSession, caller: Caller, body: sch.ThresholdPut
                        ) -> list[sch.Threshold]:
    """Replace one row (ADR-033, audited). Within one (doc_type, territory) group a
    higher level's ceiling stays above a lower one's (plan review R-13)."""
    group = {r.role: r.max_amount for r in (await db.execute(text(
        "SELECT r.code::text AS role, t.max_amount FROM approval_threshold t "
        "JOIN role r ON r.id = t.role_id WHERE t.doc_type = :d "
        "AND t.territory_id IS NOT DISTINCT FROM CAST(:t AS uuid) AND t.deleted_at IS NULL"),
        {"d": body.doc_type, "t": body.territory_id})).all()}
    group[body.role] = body.max_amount
    ordered = sorted(((_LEVEL[r], a) for r, a in group.items() if r in _LEVEL))
    ceilings = [a for _, a in ordered if a is not None]
    if ceilings != sorted(ceilings) or len(set(ceilings)) != len(ceilings):
        raise ValidationFailed("A higher manager's limit must be above a lower one's.",
                               code="thresholds_not_increasing",
                               fields={"max_amount": "not above the level below"})
    await db.execute(text(
        "INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount, created_by, "
        "updated_by) SELECT :d, r.id, CAST(:t AS uuid), :a, CAST(:me AS uuid), CAST(:me AS uuid) "
        "FROM role r WHERE r.code = :role "
        "ON CONFLICT (doc_type, role_id, territory_id) "
        "DO UPDATE SET max_amount = EXCLUDED.max_amount, "
        "updated_by = EXCLUDED.updated_by"),
        {"d": body.doc_type, "t": body.territory_id, "a": body.max_amount, "me": caller.user_id,
         "role": body.role})
    return await thresholds(db)
