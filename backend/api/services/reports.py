"""Reports (FS-024, ADR-047): live aggregates under dual enforcement.

Every query on a ScopeSpec table carries the module's `scope_predicate` and
an explicit `deleted_at IS NULL` (ADR-039; review B-2); RLS is the floor beneath
it. Tables with hand-written policies and no ScopeSpec (`visit`, `dispatch`,
`dispatch_line`, `payment_allocation`, `complaint_remedy`, `subsidy_application`)
are read under RLS alone, joined to a scoped set where one exists (ISS-111). A figure
whose module the caller lacks is None, never 0; a report whose primary module is
missing is 403 (review B-1). Names come through `people_names()` and
`partner_names()` only. Services never commit.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, scope_predicate
from api.domain import leads as lead_domain
from api.domain import reports as domain
from api.errors import ForbiddenError, NotFoundError, ValidationFailed
from api.services import people
from api.services.clock import today_ist
from api.services.leads import _id_list, _under

_UUID = sa.Uuid
_TS = sa.DateTime(timezone=True)

L = sa.table("lead", sa.column("id", _UUID), sa.column("created_at", _TS), sa.column("stage"),
             sa.column("owner_user_id", _UUID), sa.column("owner_org_unit_id", _UUID),
             sa.column("territory_id", _UUID), sa.column("assigned_partner_id", _UUID),
             sa.column("lead_source_id", _UUID), sa.column("deleted_at", _TS), sa.column("won_at", _TS),
             sa.column("lost_at", _TS), sa.column("lost_reason_id", _UUID), sa.column("lost_from_stage"),
             sa.column("mobile"), sa.column("inquiry_no"), sa.column("merged_into_id", _UUID))
ORD = sa.table("sales_order", sa.column("id", _UUID), sa.column("status"), sa.column("order_type"),
             sa.column("total", sa.Numeric), sa.column("submitted_at", _TS), sa.column("owner_user_id", _UUID),
             sa.column("owner_org_unit_id", _UUID), sa.column("territory_id", _UUID),
             sa.column("partner_id", _UUID), sa.column("lead_id", _UUID), sa.column("deleted_at", _TS))
Q = sa.table("quotation", sa.column("id", _UUID), sa.column("quote_no"), sa.column("sent_at", _TS),
             sa.column("owner_user_id", _UUID), sa.column("owner_org_unit_id", _UUID),
             sa.column("territory_id", _UUID), sa.column("partner_id", _UUID), sa.column("lead_id", _UUID),
             sa.column("deleted_at", _TS))
T = sa.table("task", sa.column("id", _UUID), sa.column("lead_id", _UUID), sa.column("status"),
             sa.column("due_at", _TS), sa.column("assigned_to", _UUID), sa.column("owner_org_unit_id", _UUID),
             sa.column("completed_at", _TS), sa.column("partner_id", _UUID), sa.column("sales_order_id", _UUID))
C = sa.table("complaint", sa.column("id", _UUID), sa.column("status"), sa.column("severity"),
             sa.column("complaint_type_id", _UUID), sa.column("first_submitted_at", _TS),
             sa.column("resolved_at", _TS), sa.column("resolution_due_at", _TS),
             sa.column("response_due_at", _TS), sa.column("responded_at", _TS),
             sa.column("owner_user_id", _UUID), sa.column("owner_org_unit_id", _UUID),
             sa.column("partner_id", _UUID), sa.column("territory_id", _UUID), sa.column("lead_id", _UUID),
             sa.column("sales_order_id", _UUID), sa.column("deleted_at", _TS))
M = sa.table("complaint_remedy", sa.column("complaint_id", _UUID), sa.column("kind"), sa.column("status"),
             sa.column("amount", sa.Numeric))
P = sa.table("channel_partner", sa.column("id", _UUID), sa.column("parent_id", _UUID),
             sa.column("territory_id", _UUID), sa.column("deleted_at", _TS))

# rule 8 (GAP-226): orders that are sales
SALE_TYPES = ("commercial", "industrial", "export", "subsidised")
# the statuses an order is paid in (031 _PAYABLE)
PAYABLE = ("submitted", "approved", "partially_dispatched", "dispatched", "closed_short")
STAFF_ONLY = frozenset({"salesperson-performance", "follow-ups", "territory-performance"})


def _has(caller: Caller, module: str) -> bool:
    return module in caller.scopes


def _need(caller: Caller, report: str, *modules: str) -> None:
    if report in STAFF_ONLY and caller.partner_id is not None:
        raise ForbiddenError("This report is for staff.")
    missing = [m for m in modules if not _has(caller, m)]
    if missing:
        raise ForbiddenError(f"This report needs {', '.join(missing)}.")


class Filters:
    def __init__(self, *, start: dt.date | None, end: dt.date | None, territory_id: str | None,
                 owner_id: str | None) -> None:
        try:
            self.start, self.end = domain.window(start, end, today_ist())
        except ValueError as exc:
            raise ValidationFailed(fields={"from": str(exc)}) from exc
        self.lo, self.hi = domain.instants(self.start, self.end)
        self.territories = _id_list(territory_id, "territory_id") if territory_id else []
        self.owner_id = owner_id

    def area(self, column: Any) -> list[Any]:
        return [column.in_(_under("territory_closure", *self.territories))] if self.territories else []

    def owner(self, column: Any) -> list[Any]:
        return [column == self.owner_id] if self.owner_id else []

    def window(self, column: Any) -> list[Any]:
        return [column >= self.lo, column < self.hi]

    def out(self) -> dict[str, Any]:
        return {"from": self.start.isoformat(), "to": self.end.isoformat(),
                "territory_id": self.territories or None, "owner_id": self.owner_id}


def _leads(caller: Caller, f: Filters) -> list[Any]:
    return [scope_predicate(SPECS["leads"], caller, L), L.c.deleted_at.is_(None),
            sa.cast(L.c.stage, sa.Text) != "merged", *f.area(L.c.territory_id), *f.owner(L.c.owner_user_id)]


def _orders(caller: Caller, f: Filters) -> list[Any]:
    return [scope_predicate(SPECS["sales_orders"], caller, ORD), ORD.c.deleted_at.is_(None),
            sa.cast(ORD.c.order_type, sa.Text).in_(SALE_TYPES), sa.cast(ORD.c.status, sa.Text) != "cancelled",
            ORD.c.submitted_at.is_not(None), *f.area(ORD.c.territory_id), *f.owner(ORD.c.owner_user_id)]


def _live_lead() -> list[Any]:
    """A task counts unless its lead is deleted or merged (follow-ups and
    salesperson-performance agree, review 10)."""
    return [sa.or_(T.c.lead_id.is_(None),
                   sa.and_(L.c.deleted_at.is_(None), sa.cast(L.c.stage, sa.Text) != "merged"))]


def _money(v: Any) -> str:
    return str(Decimal(v or 0).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _page(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    return rows[:domain.ROW_CAP], len(rows) > domain.ROW_CAP


async def _user_names(db: AsyncSession, ids: Sequence[str]) -> dict[str, str]:
    """Through people_names(): the people on rows the caller can see (review B-1)."""
    names = await people.resolve_ids(db, user_ids=[i for i in ids if i])
    return dict(names.users)


async def _partner_names(db: AsyncSession, ids: Sequence[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = (await db.execute(text("SELECT id::text AS id, name FROM partner_names(CAST(:i AS uuid[]))"),
                             {"i": list(ids)})).all()
    direct = (await db.execute(text("SELECT id::text AS id, name::text AS name FROM channel_partner WHERE id = ANY(CAST(:i AS uuid[]))"),
                               {"i": list(ids)})).all()
    return {r.id: r.name for r in [*rows, *direct]}


# ── lead conversion ─────────────────────────────────────────────────────────

_ORD = {s: i for i, s in enumerate(lead_domain.STAGES)}


def _reached(stage: str, lost_from: str | None, k: str) -> bool:
    """A stage at or past k, or lost from a stage at or past k (review B-4). A won
    lead has passed every earlier stage (GAP-224)."""
    if stage == "won":
        return True
    if stage == "lost":
        return lost_from is not None and _ORD.get(lost_from, -1) >= _ORD[k]
    return stage in _ORD and _ORD[stage] >= _ORD[k] and stage not in ("merged", "dormant")


async def lead_conversion(db: AsyncSession, caller: Caller, f: Filters, group_by: str) -> dict[str, Any]:
    _need(caller, "lead-conversion", "leads")
    key = {"source": L.c.lead_source_id, "owner": L.c.owner_user_id, "territory": L.c.territory_id}.get(group_by)
    if key is None:
        raise ValidationFailed(fields={"group_by": "source, owner or territory"})
    rows = (await db.execute(sa.select(key.label("k"), sa.cast(L.c.stage, sa.Text).label("stage"),
                                       sa.cast(L.c.lost_from_stage, sa.Text).label("lost_from"),
                                       sa.func.count().label("n"))
                             .where(*_leads(caller, f), *f.window(L.c.created_at))
                             .group_by(key, L.c.stage, L.c.lost_from_stage))).all()
    groups: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        g = groups[str(r.k) if r.k else ""]
        g["leads"] += r.n
        for s in ("contacted", "qualified", "quoted"):
            if _reached(r.stage, r.lost_from, s):
                g[s] += r.n
        g["won"] += r.n if r.stage == "won" else 0
        g["lost"] += r.n if r.stage == "lost" else 0
    labels = await _labels(db, group_by, list(groups))
    out = [{"key": {"id": k or None, "label": labels.get(k, "Unassigned" if not k else "")},
            **{s: g[s] for s in ("leads", "contacted", "qualified", "quoted", "won", "lost")},
            "open": g["leads"] - g["won"] - g["lost"], "conversion_pct": str(domain.pct(g["won"], g["leads"]))}
           for k, g in sorted(groups.items(), key=lambda kv: -kv[1]["leads"])]
    total = sum(g["leads"] for g in groups.values())
    won = sum(g["won"] for g in groups.values())
    page, cut = _page(out)
    return {"group_by": group_by, "rows": page, "truncated": cut, "filters": f.out(),
            "totals": {"leads": total, "won": won, "conversion_pct": str(domain.pct(won, total))}}


async def _labels(db: AsyncSession, group_by: str, ids: list[str]) -> dict[str, str]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    if group_by == "owner":
        return await _user_names(db, ids)
    table = {"source": "lead_source", "territory": "territory", "reason": "won_lost_reason",
             "type": "complaint_type"}[group_by]
    rows = (await db.execute(text(f"SELECT id::text AS id, name FROM {table} WHERE id = ANY(CAST(:i AS uuid[]))"),
                             {"i": ids})).all()
    return {r.id: r.name for r in rows}


# ── lost leads ──────────────────────────────────────────────────────────────

async def lost_leads(db: AsyncSession, caller: Caller, f: Filters, group_by: str) -> dict[str, Any]:
    _need(caller, "lost-leads", "leads")
    key = {"reason": L.c.lost_reason_id, "owner": L.c.owner_user_id}.get(group_by)
    if key is None:
        raise ValidationFailed(fields={"group_by": "reason or owner"})
    rows = (await db.execute(sa.select(
        key.label("k"), sa.cast(L.c.lost_from_stage, sa.Text).label("from_stage"), sa.func.count().label("n"),
        sa.func.sum(sa.extract("epoch", L.c.lost_at - L.c.created_at) / 86400).label("days"))
        .where(*_leads(caller, f), sa.cast(L.c.stage, sa.Text) == "lost", *f.window(L.c.lost_at))
        .group_by(key, L.c.lost_from_stage))).all()
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "days": 0.0, "by_stage": defaultdict(int)})
    for r in rows:
        g = groups[str(r.k) if r.k else ""]
        g["count"] += r.n
        g["days"] += float(r.days or 0)
        g["by_stage"][r.from_stage or "unknown"] += r.n
    total = sum(g["count"] for g in groups.values())
    labels = await _labels(db, group_by, list(groups))
    out = [{"key": {"id": k or None, "label": labels.get(k, "Unassigned" if not k else "")},
            "count": g["count"], "share_pct": str(domain.pct(g["count"], total)),
            "avg_days_to_loss": f"{g['days'] / g['count']:.1f}" if g["count"] else None,
            "by_stage": dict(g["by_stage"])}
           for k, g in sorted(groups.items(), key=lambda kv: -kv[1]["count"])]
    page, cut = _page(out)
    return {"group_by": group_by, "rows": page, "truncated": cut, "filters": f.out(), "totals": {"lost": total}}


# ── salesperson performance ─────────────────────────────────────────────────

async def salesperson_performance(db: AsyncSession, caller: Caller, f: Filters) -> dict[str, Any]:
    _need(caller, "salesperson-performance", "leads")
    per: dict[str, dict[str, Any]] = defaultdict(dict)

    def put(rows: Sequence[Any], **cols: str) -> None:
        for r in rows:
            for out_name, attr in cols.items():
                per[str(r.k) if r.k else ""][out_name] = getattr(r, attr)

    put((await db.execute(sa.select(L.c.owner_user_id.label("k"), sa.func.count().label("n"))
                          .where(*_leads(caller, f), *f.window(L.c.created_at)).group_by(L.c.owner_user_id))).all(),
        leads_created="n")
    put((await db.execute(sa.select(L.c.owner_user_id.label("k"), sa.func.count().label("n"))
                          .where(*_leads(caller, f), sa.cast(L.c.stage, sa.Text) == "won", *f.window(L.c.won_at))
                          .group_by(L.c.owner_user_id))).all(), leads_won="n")
    has_q, has_o = _has(caller, "quotations"), _has(caller, "sales_orders")
    has_t, has_v = _has(caller, "tasks"), _has(caller, "tracking")
    if has_q:
        put((await db.execute(sa.select(Q.c.owner_user_id.label("k"), sa.func.count(sa.distinct(Q.c.quote_no)).label("n"))
                              .where(scope_predicate(SPECS["quotations"], caller, Q), Q.c.deleted_at.is_(None),
                                     *f.window(Q.c.sent_at), *f.area(Q.c.territory_id), *f.owner(Q.c.owner_user_id))
                              .group_by(Q.c.owner_user_id))).all(), quotations_sent="n")
    if has_o:
        put((await db.execute(sa.select(ORD.c.owner_user_id.label("k"), sa.func.count().label("n"),
                                        sa.func.sum(ORD.c.total).label("v"))
                              .where(*_orders(caller, f), *f.window(ORD.c.submitted_at))
                              .group_by(ORD.c.owner_user_id))).all(), orders="n", order_value="v")
    if has_t:
        put((await db.execute(sa.select(T.c.assigned_to.label("k"),
                                        sa.func.count().filter(sa.and_(sa.cast(T.c.status, sa.Text) == "done",
                                                                       T.c.completed_at >= f.lo, T.c.completed_at < f.hi)).label("done"),
                                        sa.func.count().filter(sa.and_(sa.cast(T.c.status, sa.Text) == "open",
                                                                       T.c.due_at < sa.func.now())).label("overdue"))
                              .select_from(T.outerjoin(L, L.c.id == T.c.lead_id))
                              .where(scope_predicate(SPECS["tasks"], caller, T), *_live_lead(), *f.owner(T.c.assigned_to),
                                     *f.area(L.c.territory_id))
                              .group_by(T.c.assigned_to))).all(), tasks_done="done", tasks_overdue="overdue")
    if has_v:
        # GAP-227: a visit has no territory, so the territory filter does not reach it
        put((await db.execute(text(
            "SELECT user_id AS k, count(*) AS n FROM visit WHERE checkin_at >= :lo AND checkin_at < :hi "
            "AND (CAST(:o AS uuid) IS NULL OR user_id = CAST(:o AS uuid)) GROUP BY user_id"),
            {"lo": f.lo, "hi": f.hi, "o": f.owner_id})).all(), visits="n")
    names = await _user_names(db, [k for k in per if k])
    out = []
    for k, v in sorted(per.items(), key=lambda kv: (-(kv[1].get("leads_created") or 0), names.get(kv[0], ""))):
        out.append({"user": {"id": k or None, "full_name": names.get(k, "Unassigned" if not k else "")},
                    "leads_created": v.get("leads_created", 0), "leads_won": v.get("leads_won", 0),
                    "quotations_sent": v.get("quotations_sent", 0) if has_q else None,
                    "orders": v.get("orders", 0) if has_o else None,
                    "order_value": _money(v.get("order_value")) if has_o else None,
                    "visits": v.get("visits", 0) if has_v else None,
                    "tasks_done": v.get("tasks_done", 0) if has_t else None,
                    "tasks_overdue": v.get("tasks_overdue", 0) if has_t else None})
    page, cut = _page(out)
    return {"rows": page, "truncated": cut, "filters": f.out(),
            "totals": {"leads_created": sum(r["leads_created"] for r in out),
                       "leads_won": sum(r["leads_won"] for r in out)}}


# ── follow-ups ──────────────────────────────────────────────────────────────

async def follow_ups(db: AsyncSession, caller: Caller, f: Filters) -> dict[str, Any]:
    _need(caller, "follow-ups", "tasks")
    now = dt.datetime.now(dt.UTC)
    rows = (await db.execute(sa.select(T.c.assigned_to, T.c.due_at)
                             .select_from(T.outerjoin(L, L.c.id == T.c.lead_id))
                             .where(scope_predicate(SPECS["tasks"], caller, T), sa.cast(T.c.status, sa.Text) == "open",
                                    T.c.due_at < domain.instants(today_ist(), today_ist())[1],
                                    *_live_lead(), *f.owner(T.c.assigned_to)))).all()
    buckets = ("due_today", *(b[0] for b in domain.AGEING))
    per: dict[str, dict[str, Any]] = defaultdict(lambda: dict.fromkeys(buckets, 0) | {"oldest_due_at": None})
    for r in rows:
        b = domain.ageing_bucket(r.due_at, now)
        if b is None:
            continue
        g = per[str(r.assigned_to)]
        g[b] += 1
        if g["oldest_due_at"] is None or r.due_at < g["oldest_due_at"]:
            g["oldest_due_at"] = r.due_at
    names = await _user_names(db, list(per))
    out = [{"user": {"id": k, "full_name": names.get(k, "")}, **{b: g[b] for b in buckets},
            "oldest_due_at": g["oldest_due_at"].isoformat() if g["oldest_due_at"] else None}
           for k, g in sorted(per.items(), key=lambda kv: kv[1]["oldest_due_at"] or now)]
    page, cut = _page(out)
    return {"rows": page, "truncated": cut, "filters": {"as_of": now.isoformat(), "owner_id": f.owner_id},
            "totals": {b: sum(r[b] for r in out) for b in buckets}}


# ── dealer performance ──────────────────────────────────────────────────────

async def dealer_performance(db: AsyncSession, caller: Caller, f: Filters) -> dict[str, Any]:
    _need(caller, "dealer-performance", "sales_orders", "partners")
    orders = (await db.execute(sa.select(ORD.c.partner_id.label("k"), sa.func.count().label("n"),
                                         sa.func.sum(ORD.c.total).label("v"))
                               .where(*_orders(caller, f), ORD.c.partner_id.is_not(None), *f.window(ORD.c.submitted_at))
                               .group_by(ORD.c.partner_id))).all()
    per: dict[str, dict[str, Any]] = defaultdict(dict)
    for r in orders:
        per[str(r.k)].update(orders=r.n, order_value=r.v)
    ids = list(per)
    if ids:
        # the value shipped in the window, on the scoped sale orders only (review B-2):
        # each line's total in proportion to the quantity sent
        scoped = [str(x) for x in (await db.execute(
            sa.select(ORD.c.id).where(*_orders(caller, f), ORD.c.partner_id.in_(ids)))).scalars().all()]
        sent = (await db.execute(text(
            "SELECT o.partner_id::text AS k, sum(dl.qty / NULLIF(l.qty, 0) * l.total) AS v "
            "FROM dispatch_line dl JOIN dispatch d ON d.id = dl.dispatch_id AND d.voided_at IS NULL "
            "JOIN order_line l ON l.id = dl.order_line_id JOIN sales_order o ON o.id = d.sales_order_id "
            "WHERE o.id = ANY(CAST(:o AS uuid[])) AND d.dispatched_at >= :lo AND d.dispatched_at < :hi "
            "GROUP BY o.partner_id"), {"o": scoped, "lo": f.lo, "hi": f.hi})).all()
        for r in sent:
            per[r.k]["dispatched_value"] = r.v
    has_l, has_p, has_c = _has(caller, "leads"), _has(caller, "payments"), _has(caller, "complaints")
    if has_l and ids:
        for r in (await db.execute(sa.select(L.c.assigned_partner_id.label("k"), sa.func.count().label("n"))
                                   .where(*_leads(caller, f), L.c.assigned_partner_id.in_(ids), *f.window(L.c.created_at))
                                   .group_by(L.c.assigned_partner_id))).all():
            per[str(r.k)]["leads_assigned"] = r.n
    if has_p and ids:
        # all-time positions (rule 9): the payable total of the dealer's live orders in
        # the caller's scope, and the receipts allocated to those same orders (review 1)
        payable = (await db.execute(sa.select(ORD.c.id, ORD.c.partner_id)
                                    .where(scope_predicate(SPECS["sales_orders"], caller, ORD), ORD.c.deleted_at.is_(None),
                                           sa.cast(ORD.c.status, sa.Text).in_(PAYABLE), ORD.c.partner_id.in_(ids)))).all()
        # one definition of owed and received: the payments position (total less
        # benefits, ADR-050), over the same scoped orders for both (review 1)
        for r in (await db.execute(text(
                "SELECT o.partner_id::text AS k, sum(p.payable) AS payable, sum(p.received) AS received "
                "FROM sales_order o CROSS JOIN LATERAL order_payment_position(o.id, :d) p "
                "WHERE o.id = ANY(CAST(:o AS uuid[])) GROUP BY o.partner_id"),
                {"o": [str(r.id) for r in payable], "d": today_ist()})).all():
            per[r.k].update(payable=r.payable, received=r.received)
    if has_c and ids:
        for r in (await db.execute(sa.select(C.c.partner_id.label("k"), sa.func.count().label("n"))
                                   .where(scope_predicate(SPECS["complaints"], caller, C), C.c.deleted_at.is_(None),
                                          C.c.partner_id.in_(ids), *f.window(C.c.first_submitted_at))
                                   .group_by(C.c.partner_id))).all():
            per[str(r.k)]["complaints"] = r.n
    names = await _partner_names(db, ids)
    out = [{"partner": {"id": k, "name": names.get(k, "")}, "orders": v.get("orders", 0),
            "order_value": _money(v.get("order_value")), "dispatched_value": _money(v.get("dispatched_value")),
            "leads_assigned": v.get("leads_assigned", 0) if has_l else None,
            "received": _money(v.get("received")) if has_p else None,
            "balance": _money(Decimal(v.get("payable") or 0) - Decimal(v.get("received") or 0)) if has_p else None,
            "complaints": v.get("complaints", 0) if has_c else None}
           for k, v in sorted(per.items(), key=lambda kv: -Decimal(kv[1].get("order_value") or 0))]
    page, cut = _page(out)
    return {"rows": page, "truncated": cut, "filters": f.out(),
            "totals": {"orders": sum(r["orders"] for r in out),
                       "order_value": _money(sum(Decimal(r["order_value"]) for r in out))}}


# ── territory performance ───────────────────────────────────────────────────

async def territory_performance(db: AsyncSession, caller: Caller, f: Filters, level: str) -> dict[str, Any]:
    _need(caller, "territory-performance", "leads")
    if level not in ("district", "taluka"):
        raise ValidationFailed(fields={"level": "district or taluka"})
    tc = sa.table("territory_closure", sa.column("ancestor_id", _UUID), sa.column("descendant_id", _UUID))
    tt = sa.table("territory", sa.column("id", _UUID), sa.column("level"), sa.column("name"))
    area = (sa.select(tc.c.descendant_id.label("leaf"), tc.c.ancestor_id.label("at"))
            .select_from(tc.join(tt, tt.c.id == tc.c.ancestor_id))
            .where(sa.cast(tt.c.level, sa.Text) == level).subquery())
    leads = (await db.execute(sa.select(area.c.at.label("k"), sa.func.count().label("n"),
                                        sa.func.count().filter(sa.cast(L.c.stage, sa.Text) == "won").label("won"))
                              .select_from(L.outerjoin(area, area.c.leaf == L.c.territory_id))
                              .where(*_leads(caller, f), *f.window(L.c.created_at)).group_by(area.c.at))).all()
    per: dict[str, dict[str, Any]] = defaultdict(dict)
    for r in leads:
        per[str(r.k)].update(leads=r.n, won=r.won)
    has_o = _has(caller, "sales_orders")
    if has_o:
        for r in (await db.execute(sa.select(area.c.at.label("k"), sa.func.count().label("n"), sa.func.sum(ORD.c.total).label("v"))
                                   .select_from(ORD.outerjoin(area, area.c.leaf == ORD.c.territory_id))
                                   .where(*_orders(caller, f), *f.window(ORD.c.submitted_at)).group_by(area.c.at))).all():
            per[str(r.k)].update(orders=r.n, order_value=r.v)
    labels = await _labels(db, "territory", [k for k in per if k != "None"])
    labels["None"] = "Above this level"
    out = [{"territory": {"id": None if k == "None" else k, "name": labels.get(k, "")}, "leads": v.get("leads", 0), "won": v.get("won", 0),
            "conversion_pct": str(domain.pct(v.get("won", 0), v.get("leads", 0))),
            "orders": v.get("orders", 0) if has_o else None,
            "order_value": _money(v.get("order_value")) if has_o else None}
           for k, v in sorted(per.items(), key=lambda kv: -(kv[1].get("leads") or 0))]
    page, cut = _page(out)
    return {"level": level, "rows": page, "truncated": cut, "filters": f.out(),
            "totals": {"leads": sum(r["leads"] for r in out), "won": sum(r["won"] for r in out)}}


# ── complaints ──────────────────────────────────────────────────────────────

async def complaints(db: AsyncSession, caller: Caller, f: Filters, group_by: str) -> dict[str, Any]:
    _need(caller, "complaints", "complaints")
    key = {"type": C.c.complaint_type_id, "status": sa.cast(C.c.status, sa.Text),
           "severity": sa.cast(C.c.severity, sa.Text)}.get(group_by)
    if key is None:
        raise ValidationFailed(fields={"group_by": "type, status or severity"})
    now = sa.func.now()
    where = [scope_predicate(SPECS["complaints"], caller, C), C.c.deleted_at.is_(None),
             sa.cast(C.c.status, sa.Text).notin_(("draft", "cancelled")), *f.window(C.c.first_submitted_at),
             *f.area(C.c.territory_id), *f.owner(C.c.owner_user_id)]
    rows = (await db.execute(sa.select(
        key.label("k"), sa.func.count().label("n"),
        sa.func.count().filter(C.c.resolved_at.is_not(None)).label("resolved"),
        sa.func.count().filter(sa.and_(C.c.resolved_at.is_not(None), C.c.resolved_at <= C.c.resolution_due_at)).label("in_sla"),
        sa.func.count().filter(sa.or_(C.c.responded_at > C.c.response_due_at,
                                      sa.and_(C.c.responded_at.is_(None), C.c.response_due_at < now))).label("breaches"))
        .where(*where).group_by(key))).all()
    ids = [str(r.k) for r in rows]
    labels = await _labels(db, "type", ids) if group_by == "type" else {i: i for i in ids}
    refunds = (await db.execute(sa.select(sa.func.count().label("n"), sa.func.coalesce(sa.func.sum(M.c.amount), 0).label("v"))
                                .select_from(M.join(C, C.c.id == M.c.complaint_id))
                                .where(sa.cast(M.c.kind, sa.Text) == "refund", sa.cast(M.c.status, sa.Text) == "completed",
                                       *where))).one()
    out = [{"key": {"id": str(r.k), "label": labels.get(str(r.k), str(r.k))}, "count": r.n, "resolved": r.resolved,
            "resolved_within_sla_pct": str(domain.pct(r.in_sla, r.resolved)), "response_breaches": r.breaches}
           for r in sorted(rows, key=lambda x: -x.n)]
    return {"group_by": group_by, "rows": out, "truncated": False, "filters": f.out(),
            "totals": {"count": sum(r["count"] for r in out), "resolved": sum(r["resolved"] for r in out),
                       "refunds": {"count": refunds.n, "amount": _money(refunds.v)}}}


# ── the 360° lead view ──────────────────────────────────────────────────────

async def lead_360(db: AsyncSession, caller: Caller, lead_id: str) -> dict[str, Any]:
    if not (await db.execute(text("SELECT lead_visible(CAST(:l AS uuid))"), {"l": lead_id})).scalar_one():
        raise NotFoundError("No such lead.")
    lead = (await db.execute(text(
        "SELECT id::text AS id, inquiry_no::text AS inquiry_no, farmer_name, mobile, stage::text AS stage "
        "FROM lead WHERE id = CAST(:l AS uuid)"), {"l": lead_id})).one()
    related = (await db.execute(sa.select(L.c.id, L.c.inquiry_no, sa.cast(L.c.stage, sa.Text).label("stage"))
                                .where(scope_predicate(SPECS["leads"], caller, L), L.c.deleted_at.is_(None),
                                       sa.cast(L.c.stage, sa.Text) != "merged", L.c.mobile == lead.mobile,
                                       L.c.id != lead_id).limit(20))).all()
    q = (await db.execute(text("SELECT count(DISTINCT quote_no) FROM quotation WHERE lead_id = CAST(:l AS uuid) AND deleted_at IS NULL"),
                          {"l": lead_id})).scalar_one() if _has(caller, "quotations") else None
    orders = None
    if _has(caller, "sales_orders"):
        orders = (await db.execute(text(
            "SELECT count(*) AS n, COALESCE(sum(total), 0) AS v FROM sales_order WHERE lead_id = CAST(:l AS uuid) "
            "AND deleted_at IS NULL AND status <> 'cancelled' AND submitted_at IS NOT NULL"), {"l": lead_id})).one()
    received = None
    if _has(caller, "payments"):
        received = (await db.execute(text(
            "SELECT COALESCE(sum(a.amount), 0) FROM payment_allocation a JOIN sales_order o ON o.id = a.sales_order_id "
            "WHERE o.lead_id = CAST(:l AS uuid) AND NOT a.voided"), {"l": lead_id})).scalar_one()
    complaints_n = (await db.execute(text("SELECT count(*) FROM complaint WHERE lead_id = CAST(:l AS uuid) AND deleted_at IS NULL"),
                                     {"l": lead_id})).scalar_one() if _has(caller, "complaints") else None
    visits = (await db.execute(text("SELECT count(*) FROM visit WHERE lead_id = CAST(:l AS uuid)"),
                               {"l": lead_id})).scalar_one() if _has(caller, "tracking") else None
    tasks = (await db.execute(text("SELECT count(*) FROM task WHERE lead_id = CAST(:l AS uuid) AND status = 'open'"),
                              {"l": lead_id})).scalar_one() if _has(caller, "tasks") else None
    subsidy = (await db.execute(text(
        "SELECT max(d.seq) FROM subsidy_application a JOIN subsidy_stage_def d ON d.id = a.current_stage_id "
        "WHERE a.lead_id = CAST(:l AS uuid)"),
        {"l": lead_id})).scalar_one() if _has(caller, "subsidy") else None
    return {"lead": dict(lead._mapping),
            "related_leads": [{"id": str(r.id), "inquiry_no": r.inquiry_no, "stage": r.stage, "relation": "same_mobile"}
                              for r in related],
            "summary": {"quotations": q, "orders": None if orders is None else orders.n,
                        "order_value": None if orders is None else _money(orders.v),
                        "received": None if received is None else _money(received),
                        "complaints": complaints_n, "visits": visits, "open_tasks": tasks, "subsidy_stage": subsidy}}
