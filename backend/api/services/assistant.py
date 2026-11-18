"""The in-app assistant (FS-045): the actions a caller holds, and the records they can
open. Every record query carries the module's scope predicate, with RLS beneath it
(ADR-039, plan review B-1), never a deleted row and never a merged lead. Services
never commit."""

# ruff: noqa: E501  (column lists)

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, scope_predicate
from api.domain import assistant as domain
from api.errors import ValidationFailed
from api.schemas import assistant as sch

_UUID = sa.Uuid
_TS = sa.DateTime(timezone=True)
_SCOPE_COLS = ("owner_user_id", "owner_org_unit_id", "territory_id", "partner_id")

L = sa.table("lead", sa.column("id", _UUID), sa.column("inquiry_no"), sa.column("farmer_name"),
             sa.column("mobile"), sa.column("stage"), sa.column("customer_id", _UUID),
             sa.column("deleted_at", _TS), sa.column("owner_user_id", _UUID),
             sa.column("owner_org_unit_id", _UUID), sa.column("territory_id", _UUID),
             sa.column("assigned_partner_id", _UUID), sa.column("created_at", _TS))
Q = sa.table("quotation", sa.column("id", _UUID), sa.column("quote_no"), sa.column("version"),
             sa.column("status"), sa.column("superseded_by_id", _UUID), sa.column("deleted_at", _TS),
             *(sa.column(c, _UUID) for c in _SCOPE_COLS), sa.column("lead_id", _UUID))
ORD = sa.table("sales_order", sa.column("id", _UUID), sa.column("order_no"), sa.column("status"),
             sa.column("deleted_at", _TS), *(sa.column(c, _UUID) for c in _SCOPE_COLS),
             sa.column("lead_id", _UUID))
C = sa.table("complaint", sa.column("id", _UUID), sa.column("complaint_no"), sa.column("status"),
             sa.column("deleted_at", _TS), sa.column("owner_user_id", _UUID),
             sa.column("owner_org_unit_id", _UUID), sa.column("partner_id", _UUID),
             sa.column("lead_id", _UUID), sa.column("sales_order_id", _UUID))

PER_KIND = 5

_DOCS: tuple[tuple[str, Any, Any, sch.RecordKind, domain.Screen], ...] = (
    ("quotations", Q, Q.c.quote_no, "quotation", "quotations.detail"),
    ("sales_orders", ORD, ORD.c.order_no, "sales_order", "orders.detail"),
    ("complaints", C, C.c.complaint_no, "complaint", "complaints.detail"),
)


def _esc(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _number_match(col: Any, q: str) -> Any:
    """A document number by prefix, or a bare serial by its tail (edge case 10)."""
    conds = []
    if domain.looks_like_document(q):
        conds.append(sa.cast(col, sa.Text).ilike(_esc(q.strip()) + "%"))
    s = domain.serial(q)
    if s:
        conds.append(sa.cast(col, sa.Text).ilike("%/" + s))
    return sa.or_(*conds) if conds else None


def _actions(caller: Caller, q: str | None, limit: int) -> list[sch.AssistantAction]:
    held = set(caller.permissions)
    return [sch.AssistantAction(key=a.key, title=a.title, hint=a.hint, screen=a.screen, module=a.module)
            for a in domain.match(q, held, limit=limit, staff=caller.partner_id is None)]


async def search(db: AsyncSession, caller: Caller, q: str | None, *, limit: int = 8) -> sch.AssistantAnswer:
    q = (q or "").strip()
    if domain.has_control(q):
        raise ValidationFailed(fields={"q": "control characters are not allowed"})
    actions = _actions(caller, q, limit)
    if len(q) < 3:          # records only from 3 characters (edge case 15)
        return sch.AssistantAnswer(actions=actions, records=[])
    records: list[sch.AssistantRecord] = []
    scopes = caller.scopes

    if "leads" in scopes:
        conds = []
        num = _number_match(L.c.inquiry_no, q)
        if num is not None:
            conds.append(num)
        digits = domain.mobile_digits(q)
        if digits:
            conds.append(L.c.mobile.like("%" + digits + "%"))
        name = domain.name_text(q)
        if name and not digits:
            conds.append(L.c.farmer_name.ilike("%" + _esc(name) + "%"))
        if conds:
            rows = (await db.execute(sa.select(L.c.id, L.c.inquiry_no, L.c.farmer_name, L.c.customer_id)
                                     .where(scope_predicate(SPECS["leads"], caller, L), L.c.deleted_at.is_(None),
                                            sa.cast(L.c.stage, sa.Text) != "merged", sa.or_(*conds))
                                     .order_by(L.c.created_at.desc()).limit(PER_KIND))).all()
            records += [sch.AssistantRecord(kind="lead", id=str(r.id), label=f"{r.inquiry_no} · {r.farmer_name}",
                                            screen="leads.detail") for r in rows]
            # customers come from the matched leads (edge case 9): seen through them
            ids = list(dict.fromkeys(str(r.customer_id) for r in rows if r.customer_id))[:PER_KIND]
            if ids:
                cust = (await db.execute(text(
                    "SELECT id::text AS id, name, mobile FROM customer WHERE id = ANY(CAST(:i AS uuid[]))"),
                    {"i": ids})).all()
                records += [sch.AssistantRecord(kind="customer", id=c.id, label=f"{c.name} · {c.mobile}",
                                                screen="customers.detail") for c in cust]

    for module, table, col, kind, screen in _DOCS:
        if module not in scopes:
            continue
        num = _number_match(col, q)
        if num is None:
            continue
        where = [scope_predicate(SPECS[module], caller, table), table.c.deleted_at.is_(None), num]
        if kind == "quotation":
            # one row per number: the current version, a sent one before a draft revision
            stmt = (sa.select(Q.c.id, Q.c.quote_no.label("no"), Q.c.status, Q.c.version)
                    .where(*where, Q.c.superseded_by_id.is_(None))
                    .ext(distinct_on(Q.c.quote_no))
                    .order_by(Q.c.quote_no, sa.cast(Q.c.status, sa.Text) == "draft", Q.c.version.desc())
                    .limit(PER_KIND))
            versions = (await db.execute(stmt)).all()
            records += [sch.AssistantRecord(kind=kind, id=str(r.id), label=f"{r.no} v{r.version} · {r.status}",
                                            screen=screen) for r in versions]
        else:
            docs = (await db.execute(sa.select(table.c.id, col.label("no"), table.c.status)
                                     .where(*where).order_by(col.desc()).limit(PER_KIND))).all()
            records += [sch.AssistantRecord(kind=kind, id=str(r.id), label=f"{r.no} · {r.status}", screen=screen)
                        for r in docs]
    return sch.AssistantAnswer(actions=actions, records=records)


def catalogue(caller: Caller) -> list[sch.AssistantAction]:
    return [sch.AssistantAction(key=a.key, title=a.title, hint=a.hint, screen=a.screen, module=a.module)
            for a in domain.allowed(set(caller.permissions), staff=caller.partner_id is None)]
