"""Sales forecast and insights (FS-079). Live, scoped like the other reports.

The arithmetic is `api/domain/forecast.py` and `api/domain/insights.py`. Here are the
scoped queries that feed it. Two rules shape every query:

- **Uncast enums** (rule 13a). `stage` and `status` are compared to literal values,
  never through `CAST(... AS text)`, so the partial indexes of 034 and 081 apply.
  The literals come from fixed tuples in this module, never from input.
- **Dual enforcement** (ADR-047). Every table read carries its module's
  `scope_predicate` as well as RLS. A quotation the caller cannot see gives no
  value, and the lead falls back to its estimate (rule 10).
"""

# ruff: noqa: E501  (query construction)

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, scope_predicate
from api.domain import forecast as fc
from api.domain import insights as ins
from api.domain import reports as domain
from api.errors import ValidationFailed
from api.services import reports as rep
from api.services.clock import today_ist
from api.services.leads import _id_list, _under

_UUID = sa.Uuid
_TS = sa.DateTime(timezone=True)

L = sa.table("lead", sa.column("id", _UUID), sa.column("created_at", _TS), sa.column("stage"),
             sa.column("owner_user_id", _UUID), sa.column("territory_id", _UUID),
             sa.column("lead_source_id", _UUID), sa.column("deleted_at", _TS),
             sa.column("won_at", _TS), sa.column("lost_at", _TS), sa.column("lost_reason_id", _UUID),
             sa.column("lost_from_stage"), sa.column("merged_into_id", _UUID),
             sa.column("estimated_value", sa.Numeric), sa.column("inquiry_type"),
             sa.column("first_contacted_at", _TS), sa.column("owner_org_unit_id", _UUID),
             sa.column("assigned_partner_id", _UUID))
LM = L.alias("merged_lead")
Q = sa.table("quotation", sa.column("id", _UUID), sa.column("lead_id", _UUID), sa.column("status"),
             sa.column("total", sa.Numeric), sa.column("gross", sa.Numeric),
             sa.column("discount", sa.Numeric), sa.column("sent_at", _TS),
             sa.column("accepted_at", _TS), sa.column("rejected_at", _TS),
             sa.column("valid_until", sa.Date), sa.column("superseded_by_id", _UUID),
             sa.column("deleted_at", _TS), sa.column("sales_type"),
             sa.column("owner_user_id", _UUID), sa.column("owner_org_unit_id", _UUID),
             sa.column("territory_id", _UUID), sa.column("partner_id", _UUID))
AE = sa.table("activity_event", sa.column("lead_id", _UUID), sa.column("kind"),
              sa.column("payload", sa.JSON))

HISTORY_DEFAULT: Final = 180
GROUPS: Final = ("owner", "territory", "source")
_OPEN_SQL: Final = "lead.stage IN ('new', 'contacted', 'qualified', 'quoted', 'negotiation')"
_LIVE_Q_SQL: Final = "quotation.status IN ('sent', 'viewed', 'negotiation')"
_SALE_TYPES_SQL: Final = "quotation.sales_type IN ('commercial', 'industrial', 'export', 'subsidised')"


def _is(column_sql: str) -> Any:
    """A literal SQL condition from this module's constants (rule 13a)."""
    return sa.text(column_sql)


def _not_dealership() -> Any:
    # inquiry_type is not indexed by these queries, so a cast costs nothing here
    return sa.or_(L.c.inquiry_type.is_(None), sa.cast(L.c.inquiry_type, sa.Text) != "dealership")


def _lead_scope(caller: Caller) -> list[Any]:
    """The caller's leads, before any owner or territory filter (rule 1)."""
    return [scope_predicate(SPECS["leads"], caller, L), L.c.deleted_at.is_(None), _not_dealership()]


def _area(territories: list[str]) -> list[Any]:
    return [L.c.territory_id.in_(_under("territory_closure", *territories))] if territories else []


# ── the forecast ─────────────────────────────────────────────────────────────

async def _history(db: AsyncSession, caller: Caller, lo: dt.datetime, hi: dt.datetime
                   ) -> tuple[dict[str, fc.Rate] | None, int | None]:
    """Rates and the median days to win, from leads won or lost in the window (rules
    1 to 7). Won leads' stages come from their events; lost leads' from
    `lost_from_stage`."""
    won_rows = (await db.execute(
        sa.select(L.c.id, L.c.created_at, L.c.won_at)
        .where(*_lead_scope(caller), _is("lead.stage = 'won'"), L.c.won_at >= lo, L.c.won_at < hi))).all()
    lost_rows = (await db.execute(
        sa.select(sa.cast(L.c.lost_from_stage, sa.Text).label("lost_from"), sa.func.count().label("n"))
        .where(*_lead_scope(caller), _is("lead.stage = 'lost'"), L.c.lost_at >= lo, L.c.lost_at < hi)
        .group_by(L.c.lost_from_stage))).all()
    targets: dict[str, set[str]] = defaultdict(set)
    ids = [r.id for r in won_rows]
    for start in range(0, len(ids), 5000):
        chunk = ids[start:start + 5000]
        for r in (await db.execute(
                sa.select(AE.c.lead_id, AE.c.payload["to"].as_string().label("to"))
                .where(_is("activity_event.kind = 'lead.stage_changed'"), AE.c.lead_id.in_(chunk)))).all():
            if r.to:
                targets[str(r.lead_id)].add(r.to)
    closed: list[tuple[bool, frozenset[str]]] = [
        (True, fc.stages_reached("won", None, targets.get(str(r.id), ()))) for r in won_rows]
    for r in lost_rows:
        closed.extend([(False, fc.stages_reached("lost", r.lost_from, ()))] * int(r.n))
    days = [(r.won_at - r.created_at).days for r in won_rows if r.won_at and r.created_at]
    return fc.win_rates(closed), fc.median_days(days)


def _month_expr(created: Any, median: int | None, today: dt.date) -> Any:
    """Rule 12 in SQL, the mirror of `forecast.expected_month`."""
    if median is None:
        return sa.literal(fc.LATER)
    months = fc.months(today)
    target = sa.func.greatest(created + sa.literal(median), sa.literal(today, sa.Date))
    key = sa.func.to_char(target, "YYYY-MM")
    return sa.case(
        ((sa.literal(today, sa.Date) - created) > fc.STALE_FACTOR * max(median, 1), sa.literal(fc.LATER)),
        (key.in_(months), key),
        else_=sa.literal(fc.LATER))


async def sales_forecast(db: AsyncSession, caller: Caller, *, group_by: str, territory_id: str | None,
                         owner_id: str | None, history_days: int, level: str) -> dict[str, Any]:
    rep._need(caller, "sales-forecast", "leads")
    if group_by not in GROUPS:
        raise ValidationFailed(fields={"group_by": "owner, territory or source"})
    if not 90 <= history_days <= 365:
        raise ValidationFailed(fields={"history_days": "between 90 and 365"})
    if level not in ("district", "taluka"):
        raise ValidationFailed(fields={"level": "district or taluka"})
    territories = _id_list(territory_id, "territory_id") if territory_id else []
    today = today_ist()
    hi = dt.datetime.combine(today + dt.timedelta(days=1), dt.time(0), tzinfo=domain.IST)
    lo = hi - dt.timedelta(days=history_days)
    rates, median = await _history(db, caller, lo, hi)

    # the value of each open lead: its newest live quotation, its merged leads' too
    # (rule 8), under the quotation scope as well as RLS (rule 10)
    has_q = rep._has(caller, "quotations")
    q_total: Any
    if has_q:
        merged = sa.select(LM.c.id).where(LM.c.merged_into_id == L.c.id).correlate(L)
        q_total = (sa.select(Q.c.total)
                   .where(sa.or_(Q.c.lead_id == L.c.id, Q.c.lead_id.in_(merged)),
                          Q.c.superseded_by_id.is_(None), Q.c.deleted_at.is_(None),
                          _is(_LIVE_Q_SQL), Q.c.total > 0, scope_predicate(SPECS["quotations"], caller, Q))
                   .order_by(Q.c.sent_at.desc().nulls_last(), Q.c.id.desc()).limit(1)
                   .correlate(L).scalar_subquery())
    else:
        q_total = sa.cast(sa.null(), sa.Numeric)
    estimate = sa.case((L.c.estimated_value > 0, L.c.estimated_value), else_=sa.cast(sa.null(), sa.Numeric))
    created_d = sa.cast(sa.func.timezone("Asia/Kolkata", L.c.created_at), sa.Date)

    if group_by == "territory":
        tc = sa.table("territory_closure", sa.column("ancestor_id", _UUID), sa.column("descendant_id", _UUID))
        tt = sa.table("territory", sa.column("id", _UUID), sa.column("level"))
        area = (sa.select(tc.c.descendant_id.label("leaf"), tc.c.ancestor_id.label("at"))
                .select_from(tc.join(tt, tt.c.id == tc.c.ancestor_id))
                .where(sa.cast(tt.c.level, sa.Text) == level).subquery())
        key: Any = area.c.at
        source: Any = L.outerjoin(area, area.c.leaf == L.c.territory_id)
    else:
        key = L.c.owner_user_id if group_by == "owner" else L.c.lead_source_id
        source = L
    # the quotation lookup runs once per lead, here; the value and its source are
    # worked out from its result one level up
    leads = (sa.select(key.label("k"), sa.cast(L.c.stage, sa.Text).label("stage"), q_total.label("qv"),
                       estimate.label("est"), created_d.label("created"))
             .select_from(source)
             .where(*_lead_scope(caller), _is(_OPEN_SQL), *_area(territories),
                    *([L.c.owner_user_id == owner_id] if owner_id else []))
             .subquery())
    base = sa.select(
        leads.c.k, leads.c.stage, leads.c.created,
        sa.func.coalesce(leads.c.qv, leads.c.est).label("v"),
        sa.case((leads.c.qv.isnot(None), sa.literal("quotation")),
                (leads.c.est.isnot(None), sa.literal("estimate")), else_=sa.cast(sa.null(), sa.Text)).label("by"),
    ).subquery()
    if rates is not None:
        weighted: Any = sa.case(
            *((base.c.stage == s, sa.func.round(base.c.v * sa.literal(r.won, sa.Numeric) / sa.literal(r.closed, sa.Numeric), 2))
              for s, r in rates.items()),
            else_=sa.null())
    else:
        weighted = sa.cast(sa.null(), sa.Numeric)
    month = _month_expr(base.c.created, median, today)
    rows = (await db.execute(
        sa.select(base.c.k, month.label("m"), sa.func.count().label("open"),
                  sa.func.count(base.c.v).label("with_value"), sa.func.sum(base.c.v).label("pipeline"),
                  sa.func.sum(weighted).label("weighted"),
                  sa.func.count().filter(base.c.by == "quotation").label("by_q"),
                  sa.func.count().filter(base.c.by == "estimate").label("by_e"))
        .group_by(base.c.k, month))).all()

    per: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "open": 0, "with_value": 0, "pipeline": Decimal(0), "weighted": Decimal(0),
        "by_month": defaultdict(Decimal), "q": 0, "e": 0})
    for r in rows:
        g = per[str(r.k) if r.k else ""]
        g["open"] += r.open
        g["with_value"] += r.with_value
        g["pipeline"] += r.pipeline or 0
        g["weighted"] += r.weighted or 0
        g["by_month"][r.m] += r.weighted or 0
        g["q"] += r.by_q
        g["e"] += r.by_e
    labels = await rep._labels(db, group_by, [k for k in per if k]) if per else {}
    keys = [*fc.months(today), fc.LATER]
    thin = rates is None

    def money(v: Decimal) -> str | None:
        return None if thin else rep._money(v)

    out = [{"key": {"id": k or None, "label": labels.get(k, "Above this level" if group_by == "territory" else "Unassigned")
                    if not k else labels.get(k, "")},
            "open": g["open"], "with_value": g["with_value"], "pipeline_value": rep._money(g["pipeline"]),
            "weighted_value": money(g["weighted"]),
            "by_month": {m: money(g["by_month"].get(m, Decimal(0))) for m in keys},
            "valued_by": {"quotation": g["q"], "estimate": g["e"]}}
           for k, g in sorted(per.items(), key=lambda kv: (-kv[1]["weighted"], -kv[1]["open"], kv[0]))]
    page, cut = rep._page(out)
    totals = {
        "open": sum(g["open"] for g in per.values()),
        "with_value": sum(g["with_value"] for g in per.values()),
        "pipeline_value": rep._money(sum((g["pipeline"] for g in per.values()), Decimal(0))),
        "weighted_value": money(sum((g["weighted"] for g in per.values()), Decimal(0))),
        "by_month": {m: money(sum((g["by_month"].get(m, Decimal(0)) for g in per.values()), Decimal(0)))
                     for m in keys},
        "valued_by": {"quotation": sum(g["q"] for g in per.values()),
                      "estimate": sum(g["e"] for g in per.values())},
    }
    return {
        "group_by": group_by, "months": fc.months(today), "rows": page, "truncated": cut,
        "row_count": len(out),
        "rates": [] if rates is None else [
            {"stage": s, "win_rate_pct": str(r.pct), "closed": r.own_closed, "low_confidence": r.low_confidence}
            for s, r in rates.items()],
        "median_days_to_win": median,
        "reason": "not_enough_history" if thin else None,
        "filters": {"history_days": history_days, "territory_id": territories or None, "owner_id": owner_id,
                    "level": level if group_by == "territory" else None, "as_of": today.isoformat(),
                    "rates_from": "your_whole_scope"},
        "totals": totals,
    }


# ── insights ─────────────────────────────────────────────────────────────────

async def insights(db: AsyncSession, caller: Caller, f: rep.Filters) -> dict[str, Any]:
    rep._need(caller, "insights", "leads")
    days = (f.end - f.start).days + 1
    prev_end = f.start - dt.timedelta(days=1)
    prev_start = prev_end - dt.timedelta(days=days - 1)
    plo, _ = domain.instants(prev_start, prev_end)
    lo, hi = f.lo, f.hi
    lead_where = [*_lead_scope(caller), *_area(f.territories),
                  *([L.c.owner_user_id == f.owner_id] if f.owner_id else [])]
    now_p = L.c.lost_at >= lo
    rows_out: list[dict[str, Any]] = []

    # losses, both periods in one scan (rule 14)
    lost = (await db.execute(
        sa.select(L.c.lost_reason_id.label("reason"), sa.cast(L.c.lost_from_stage, sa.Text).label("stage"),
                  sa.func.count().filter(now_p).label("cur"), sa.func.count().filter(sa.not_(now_p)).label("prev"))
        .where(*lead_where, _is("lead.stage = 'lost'"), L.c.lost_at >= plo, L.c.lost_at < hi)
        .group_by(L.c.lost_reason_id, L.c.lost_from_stage))).all()
    by_reason_cur: dict[str, int] = defaultdict(int)
    by_reason_prev: dict[str, int] = defaultdict(int)
    by_stage_cur: dict[str, int] = defaultdict(int)
    by_stage_prev: dict[str, int] = defaultdict(int)
    for r in lost:
        reason = str(r.reason) if r.reason else ""
        stage = r.stage or "unknown"
        by_reason_cur[reason] += r.cur
        by_reason_prev[reason] += r.prev
        by_stage_cur[stage] += r.cur
        by_stage_prev[stage] += r.prev
    reason_labels = await rep._labels(db, "reason", [k for k in by_reason_cur if k])
    for row in (ins.lost_reason_rising(by_reason_cur, by_reason_prev, reason_labels),
                ins.drop_off_stage(by_stage_cur, by_stage_prev)):
        if row:
            rows_out.append(row)

    # sources: leads created in the period, and how many are won
    src = (await db.execute(
        sa.select(L.c.lead_source_id.label("k"), sa.func.count().label("n"),
                  sa.func.count().filter(_is("lead.stage = 'won'")).label("won"))
        .where(*lead_where, _is("lead.stage <> 'merged'"), L.c.created_at >= lo, L.c.created_at < hi)
        .group_by(L.c.lead_source_id))).all()
    sources = {str(r.k): (int(r.n), int(r.won)) for r in src if r.k}
    row = ins.source_best_worst(sources, await rep._labels(db, "source", list(sources)) if sources else {})
    if row:
        rows_out.append(row)

    # quotations: by the decision date, the latest version of each chain (rule 15)
    if rep._has(caller, "quotations"):
        q_where = [scope_predicate(SPECS["quotations"], caller, Q), Q.c.deleted_at.is_(None),
                   Q.c.superseded_by_id.is_(None),
                   *([Q.c.territory_id.in_(_under("territory_closure", *f.territories))] if f.territories else []),
                   *([Q.c.owner_user_id == f.owner_id] if f.owner_id else [])]
        acc_now, acc_prev = Q.c.accepted_at >= lo, Q.c.accepted_at < lo
        rej_now, rej_prev = Q.c.rejected_at >= lo, Q.c.rejected_at < lo
        decided = sa.or_(sa.and_(Q.c.accepted_at >= plo, Q.c.accepted_at < hi),
                         sa.and_(Q.c.rejected_at >= plo, Q.c.rejected_at < hi))
        a = (await db.execute(
            sa.select(sa.func.count().filter(acc_now).label("ca"), sa.func.count().filter(rej_now).label("cr"),
                      sa.func.count().filter(acc_prev).label("pa"), sa.func.count().filter(rej_prev).label("pr"))
            .where(*q_where, decided))).one()
        expired = (await db.execute(
            sa.select(sa.func.count()).where(*q_where, _is("quotation.status = 'expired'"),
                                             Q.c.valid_until >= f.start, Q.c.valid_until <= f.end))).scalar_one()
        row = ins.quotation_answers((a.ca, a.cr, int(expired)), (a.pa, a.pr, 0), days)
        if row:
            rows_out.append(row)
        above = Q.c.discount > Q.c.gross * Decimal("0.05")
        band = (await db.execute(
            sa.select(sa.func.count().filter(above, acc_now).label("aa"),
                      sa.func.count().filter(above).label("an"),
                      sa.func.count().filter(sa.not_(above), acc_now).label("ba"),
                      sa.func.count().filter(sa.not_(above)).label("bn"))
            .where(*q_where, _is(_SALE_TYPES_SQL), Q.c.gross > 0,
                   sa.or_(sa.and_(Q.c.accepted_at >= lo, Q.c.accepted_at < hi),
                          sa.and_(Q.c.rejected_at >= lo, Q.c.rejected_at < hi))))).one()
        row = ins.quotation_discount((band.aa, band.an), (band.ba, band.bn))
        if row:
            rows_out.append(row)

    # first contact: leads created in the period (rule 17)
    hours_expr = sa.extract("epoch", L.c.first_contacted_at - L.c.created_at) / 3600
    waited_expr = sa.or_(
        sa.and_(L.c.first_contacted_at.isnot(None), hours_expr > ins.WAIT_HOURS),
        sa.and_(L.c.first_contacted_at.is_(None),
                L.c.created_at < sa.func.now() - sa.text(f"interval '{ins.WAIT_HOURS} hours'")))
    contact = (await db.execute(
        sa.select(hours_expr.label("h"), waited_expr.label("w"))
        .where(*lead_where, _is("lead.stage <> 'merged'"), L.c.created_at >= lo, L.c.created_at < hi))).all()
    hours = [float(r.h) for r in contact if r.h is not None and r.h >= 0]
    row = ins.first_contact_speed(hours, sum(1 for r in contact if r.w))
    if row:
        rows_out.append(row)

    return {"rows": rows_out, "truncated": False, "row_count": len(rows_out),
            "filters": {**f.out(), "previous_from": prev_start.isoformat(), "previous_to": prev_end.isoformat()}}
