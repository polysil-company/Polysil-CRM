"""The sign-in dashboard's overview (FS-017): four figures, the pipeline by stage,
leads by source and the next follow-ups, all in the caller's own scope.

The lead scope is the lead list's own predicate, so the dashboard and the list
agree about which leads count. Live aggregates, not materialised views (GAP-159).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import leads as lead_domain
from api.domain import tasks as task_domain
from api.domain.dashboard import delta_percent, money, one_place, rate
from api.schemas.dashboard import (
    DashboardOverview,
    FollowUp,
    Kpi,
    Kpis,
    Period,
    PipelineStage,
    SourceCount,
)
from api.schemas.leads import UserRef
from api.services import leads as leads_service
from api.services import people
from api.services.clock import today_ist

# rule 3 (GAP-158): the stages whose value is the pipeline
OPEN_STAGES = ("new", "contacted", "qualified", "quoted", "negotiation")
FOLLOW_UPS = 10
_BUCKET_DAYS = {7: 1, 30: 5, 90: 15}

lead_t = leads_service.lead_t
_TS = sa.DateTime(timezone=True)
task_t = sa.table("task", sa.column("id"), sa.column("lead_id"), sa.column("status"),
                  sa.column("due_at", _TS), sa.column("assigned_to"))


async def overview(db: AsyncSession, caller: Caller, days: int) -> DashboardOverview:
    today = today_ist()   # one "today" for every figure (rule 1)
    start = today - dt.timedelta(days=days - 1)
    prev_start = start - dt.timedelta(days=days)
    width = _BUCKET_DAYS[days]
    buckets = days // width
    # the list's own scope and filters, less the soft-deleted leads a deleter may
    # read in the list (rule 6, review B-2)
    where = [*await leads_service._lead_filters(db, caller), lead_t.c.deleted_at.is_(None)]

    # Q1: both periods at once, by IST day, source and whether won now
    ist_day = sa.cast(sa.func.timezone("Asia/Kolkata", lead_t.c.created_at), sa.Date)
    won = sa.cast(lead_t.c.stage, sa.Text) == "won"
    rows = (await db.execute(
        sa.select(ist_day.label("day"), lead_t.c.lead_source_id.label("source_id"),
                  won.label("won"), sa.func.count().label("n"))
        .where(sa.and_(*where,
                       lead_t.c.created_at >= task_domain.day_bounds(prev_start)[0],
                       lead_t.c.created_at < task_domain.day_bounds(today)[1]))
        .group_by(ist_day, lead_t.c.lead_source_id, won))).all()

    counts = [0] * buckets
    wins = [0] * buckets
    prev_n = prev_won = 0
    by_source: dict[str, int] = {}
    for r in rows:
        if r.day < start:
            prev_n += r.n
            prev_won += r.n if r.won else 0
            continue
        b = (r.day - start).days // width
        counts[b] += r.n
        wins[b] += r.n if r.won else 0
        by_source[str(r.source_id)] = by_source.get(str(r.source_id), 0) + r.n
    new_n, new_won = sum(counts), sum(wins)

    # Q2: the pipeline now
    stage = sa.cast(lead_t.c.stage, sa.Text)
    staged = {r.stage: r for r in (await db.execute(
        sa.select(stage.label("stage"), sa.func.count().label("n"),
                  sa.func.sum(lead_t.c.estimated_value).label("v"))
        .where(sa.and_(*where)).group_by(stage))).all()}
    pipeline = [PipelineStage(stage=s, count=staged[s].n if s in staged else 0,  # type: ignore[arg-type]
                              value=money(staged[s].v if s in staged else None))
                for s in lead_domain.STAGES if s != "merged"]
    open_value = sum((staged[s].v or Decimal(0) for s in OPEN_STAGES if s in staged), Decimal(0))

    # Q3: overdue now, the same figure as GET /leads/stats (review B-1)
    _, overdue = await leads_service.follow_ups(db, caller, where, today)

    sources = [SourceCount(source=r.code, name=r.name, count=by_source.get(str(r.id), 0))
               for r in (await db.execute(text(
                   "SELECT id, code::text AS code, name FROM lead_source WHERE deleted_at IS NULL "
                   "ORDER BY sort_order, name"))).all()]

    kpis = Kpis(
        pipeline_value=Kpi(value=money(open_value), delta_percent=None, trend=[]),
        new_leads=Kpi(value=str(new_n),
                      delta_percent=delta_percent(Decimal(new_n), Decimal(prev_n)),
                      trend=[str(c) for c in counts]),
        conversion_rate=Kpi(
            value=one_place(rate(new_won, new_n)),
            delta_percent=delta_percent(rate(new_won, new_n), rate(prev_won, prev_n)),
            trend=[one_place(rate(w, c)) for w, c in zip(wins, counts, strict=True)]),
        overdue_follow_ups=Kpi(value=None if overdue is None else str(overdue),
                               delta_percent=None, trend=[]),
    )
    return DashboardOverview(
        period_label=f"Last {days} days",
        period=Period(start=start.isoformat(), end=today.isoformat()),
        kpis=kpis, pipeline=pipeline, sources=sources,
        follow_ups=await _next_follow_ups(db, caller, where, today))


async def _next_follow_ups(db: AsyncSession, caller: Caller, where: list[Any],
                           today: dt.date) -> list[FollowUp]:
    """Q4: the earliest-due open tasks on leads the caller sees, where the caller
    sees the task too (rule 4). From the start of the overdue window, so an
    ancient forgotten task cannot hold every slot (review B-1)."""
    if "tasks" not in caller.scopes:
        return []
    window = task_domain.overdue_window(today, today)
    assert window is not None
    today_start = task_domain.day_bounds(today)[0]
    leads = sa.select(lead_t.c.id).where(sa.and_(*where))
    tasks = (await db.execute(
        sa.select(task_t.c.id, task_t.c.lead_id, task_t.c.due_at, task_t.c.assigned_to)
        .where(sa.cast(task_t.c.status, sa.Text) == "open", task_t.c.due_at >= window[0],
               task_t.c.lead_id.in_(leads.scalar_subquery()))
        .order_by(task_t.c.due_at, task_t.c.id).limit(FOLLOW_UPS))).all()
    if not tasks:
        return []
    lead_ids = sorted({str(t.lead_id) for t in tasks})
    about = {str(r.id): r for r in (await db.execute(text(
        "SELECT l.id, l.farmer_name, "
        "       (SELECT t.name FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id "
        "         WHERE tc.descendant_id = l.territory_id AND t.level = 'district' "
        "         ORDER BY tc.depth LIMIT 1) AS district "
        "  FROM lead l WHERE l.id = ANY(CAST(:ids AS uuid[]))"), {"ids": lead_ids})).all()}
    names = await people.resolve_ids(db, {str(t.assigned_to) for t in tasks if t.assigned_to})
    out: list[FollowUp] = []
    for t in tasks:
        lead = about.get(str(t.lead_id))
        if lead is None:
            continue
        who = str(t.assigned_to) if t.assigned_to else None
        out.append(FollowUp(
            task_id=str(t.id), lead_id=str(t.lead_id), farmer_name=lead.farmer_name,
            district=lead.district, due_at=t.due_at.isoformat(),
            assigned_to=UserRef(id=who, full_name=names.users.get(who) or "") if who else None,
            overdue=t.due_at < today_start))
    return out
