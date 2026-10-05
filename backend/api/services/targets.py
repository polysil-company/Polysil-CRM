"""Targets (FS-025): set monthly targets for people below you; read achievement live.

Targets are append-only rows (CLAUDE.md 4.1 rule 10). "Below me" is in my subtree,
not me, and a lower role level; global scope may set anyone (review B-1). Names
come from `app_user` under RLS (review B-4). Achievement reuses the reports'
scoped counting (FS-024). Services never commit.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import reports as report_domain
from api.domain import targets as domain
from api.errors import ForbiddenError, NotFoundError, ValidationFailed
from api.services import reports
from api.services.clock import today_ist

_MY_LEVEL = "(SELECT r2.level FROM app_user me JOIN role r2 ON r2.id = me.role_id WHERE me.id = CAST(:me AS uuid))"
_SUBTREE = "(SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))"


def _month(raw: str) -> dt.date:
    try:
        return domain.parse_month(raw)
    except ValueError as exc:
        raise ValidationFailed(fields={"month": "YYYY-MM"}) from exc


def _fmt(metric: str, v: Any) -> Any:
    if v is None:
        return None
    return f"{Decimal(v):.2f}" if metric == "order_value" else int(v)


async def _current(db: AsyncSession, user_id: str, month: dt.date) -> dict[str, Decimal]:
    rows = (await db.execute(text(
        "SELECT DISTINCT ON (metric) metric, value FROM sales_target WHERE user_id = CAST(:u AS uuid) AND month = :m "
        "ORDER BY metric, effective_from DESC, id DESC"), {"u": user_id, "m": month})).all()
    return {r.metric: Decimal(r.value) for r in rows}


async def get_targets(db: AsyncSession, caller: Caller, user_id: str, month_raw: str) -> dict[str, Any]:
    month = _month(month_raw)
    person = (await db.execute(text("SELECT id::text AS id, full_name FROM app_user WHERE id = CAST(:u AS uuid)"),
                               {"u": user_id})).one_or_none()
    if person is None:
        raise NotFoundError("No such person.")
    current = await _current(db, user_id, month)
    # GAP-228: the setter's name is blank for a reader without users.view
    history = (await db.execute(text(
        "SELECT t.metric, t.value, t.effective_from, t.created_by::text AS by, u.full_name AS by_name FROM sales_target t "
        "LEFT JOIN app_user u ON u.id = t.created_by WHERE t.user_id = CAST(:u AS uuid) AND t.month = :m "
        "ORDER BY t.effective_from DESC, t.id DESC"), {"u": user_id, "m": month})).all()
    return {"user": {"id": person.id, "full_name": person.full_name}, "month": month_raw,
            "targets": {m: _fmt(m, current.get(m)) for m in domain.METRICS},
            "history": [{"metric": h.metric, "value": _fmt(h.metric, h.value),
                         "set_by": {"id": h.by, "full_name": h.by_name or ""}, "set_at": h.effective_from.isoformat()}
                        for h in history]}


async def set_targets(db: AsyncSession, caller: Caller, user_id: str, month_raw: str,
                      targets: dict[str, Decimal]) -> dict[str, Any]:
    month = _month(month_raw)
    scope = caller.scopes.get("targets")
    problem = domain.month_problem(month, today_ist(), global_scope=scope == "global")
    if problem == "month_closed":
        raise ValidationFailed("Targets for a past month are closed.", code="month_closed", fields={"month": "past"})
    if problem:
        raise ValidationFailed(fields={"month": problem})
    bad = {m: p for m, v in targets.items() if (p := domain.value_problem(m, v))}
    if bad or not targets:
        raise ValidationFailed(fields=bad or {"targets": "at least one metric"})
    person = (await db.execute(text(
        "SELECT u.id, u.org_unit_id, u.is_active, r.level, (u.user_type = 'staff' AND EXISTS ("
        "SELECT 1 FROM role_permission rp WHERE rp.role_id = u.role_id AND rp.module = 'targets' AND rp.action = 'view' "
        "AND rp.deleted_at IS NULL AND rp.scope <> 'global')) AS carries, "
        f"(u.org_unit_id IN {_SUBTREE}) AS in_subtree, "
        "(SELECT r2.level FROM app_user me JOIN role r2 ON r2.id = me.role_id WHERE me.id = CAST(:me AS uuid)) AS my_level "
        "FROM app_user u JOIN role r ON r.id = u.role_id WHERE u.id = CAST(:u AS uuid) AND u.deleted_at IS NULL"),
        {"u": user_id, "me": caller.user_id})).one_or_none()
    if person is None:
        raise NotFoundError("No such person.")
    # review B-1: below me in office and rank; global may set anyone
    if scope != "global" and (str(person.id) == caller.user_id or not person.in_subtree
                              or person.my_level is None or person.level >= person.my_level):
        raise ForbiddenError("Set targets only for people below you.", code="not_your_team")
    if not person.is_active:
        raise ValidationFailed("This person is deactivated.", code="user_inactive")
    if not person.carries:
        # review 8: a target nobody would ever see in achievement
        raise ValidationFailed("This person does not carry targets.", code="no_targets")
    before = await _current(db, user_id, month)
    for metric, value in sorted(targets.items()):
        await db.execute(text(
            "INSERT INTO sales_target (user_id, org_unit_id, month, metric, value, created_by) "
            "VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :m, :k, :v, CAST(:me AS uuid))"),
            {"u": user_id, "o": None if person.org_unit_id is None else str(person.org_unit_id), "m": month,
             "k": metric, "v": value, "me": caller.user_id})
        # rule 7: on the person, read through activity_event_sel's app_user arm
        await db.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload) "
            "VALUES ('app_user', CAST(:u AS uuid), 'target.set', CAST(:me AS uuid), CAST(:p AS jsonb))"),
            {"u": user_id, "me": caller.user_id,
             "p": json.dumps({"month": month_raw, "metric": metric, "value": str(value),
                              "previous": None if metric not in before else str(before[metric])})})
    return await get_targets(db, caller, user_id, month_raw)


async def achievement(db: AsyncSession, caller: Caller, month_raw: str, user_id: str | None) -> dict[str, Any]:
    month = _month(month_raw)
    scope = caller.scopes.get("targets")
    if scope is None:
        raise ForbiddenError("No targets permission.")
    # the people: the caller and everyone below them in office and rank (the same
    # test set_targets uses), with or without a target. People whose targets role is
    # global carry none and are never listed, the caller included (review 7).
    where = {"own": "u.id = CAST(:me AS uuid)",
             "org_subtree": f"(u.id = CAST(:me AS uuid) OR (u.org_unit_id IN {_SUBTREE} AND r.level < {_MY_LEVEL}))",
             "global": "TRUE"}[scope]
    people = (await db.execute(text(
        "SELECT u.id::text AS id, u.full_name FROM app_user u JOIN role r ON r.id = u.role_id "
        f"WHERE {where} AND u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL "
        "AND EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id = u.role_id AND rp.module = 'targets' "
        "AND rp.action = 'view' AND rp.deleted_at IS NULL AND rp.scope <> 'global') "
        "AND (CAST(:only AS uuid) IS NULL OR u.id = CAST(:only AS uuid)) ORDER BY u.full_name LIMIT 500"),
        {"me": caller.user_id, "only": user_id})).all()
    ids = [p.id for p in people]
    targets: dict[str, dict[str, Decimal]] = {i: {} for i in ids}
    if ids:
        for r in (await db.execute(text(
                "SELECT DISTINCT ON (user_id, metric) user_id::text AS u, metric, value FROM sales_target "
                "WHERE user_id = ANY(CAST(:i AS uuid[])) AND month = :m ORDER BY user_id, metric, effective_from DESC, id DESC"),
                {"i": ids, "m": month})).all():
            targets[r.u][r.metric] = Decimal(r.value)
    achieved = await _achieved(db, caller, month, ids)
    rows, totals_t, totals_a = [], dict.fromkeys(domain.METRICS, Decimal(0)), dict.fromkeys(domain.METRICS, Decimal(0))
    null_metrics: set[str] = set()
    for p in people:
        metrics = {}
        for m in domain.METRICS:
            t = targets[p.id].get(m)
            got = achieved[m]
            a = None if got is None else got.get(p.id, Decimal(0))
            if a is None:
                null_metrics.add(m)
            else:
                totals_a[m] += a
            totals_t[m] += t or Decimal(0)
            metrics[m] = {"target": _fmt(m, t), "achieved": _fmt(m, a),
                          "pct": None if not t or a is None else str(report_domain.pct(a, t))}
        rows.append({"user": {"id": p.id, "full_name": p.full_name}, "metrics": metrics})
    totals = {m: {"target": _fmt(m, totals_t[m]),
                  "achieved": None if m in null_metrics else _fmt(m, totals_a[m]),
                  "pct": None if m in null_metrics or not totals_t[m] else str(report_domain.pct(totals_a[m], totals_t[m]))}
              for m in domain.METRICS}
    return {"month": month_raw, "as_of": dt.datetime.now(dt.UTC).isoformat(), "rows": rows, "totals": totals}


async def _achieved(db: AsyncSession, caller: Caller, month: dt.date, ids: list[str]) -> dict[str, dict[str, Decimal] | None]:
    """The reports' counting for the month, per person; None for a module the caller lacks."""
    f = reports.Filters(start=month, end=domain.month_end(month), territory_id=None, owner_id=None)
    out: dict[str, dict[str, Decimal] | None] = dict.fromkeys(domain.METRICS)
    if not ids:
        return {m: {} for m in domain.METRICS}
    if "sales_orders" in caller.scopes:
        rows = (await db.execute(sa.select(reports.ORD.c.owner_user_id, sa.func.count(), sa.func.sum(reports.ORD.c.total))
                                 .where(*reports._orders(caller, f), *f.window(reports.ORD.c.submitted_at),
                                        reports.ORD.c.owner_user_id.in_(ids))
                                 .group_by(reports.ORD.c.owner_user_id))).all()
        out["orders"] = {str(r[0]): Decimal(r[1]) for r in rows}
        out["order_value"] = {str(r[0]): Decimal(r[2] or 0) for r in rows}
    if "leads" in caller.scopes:
        rows = (await db.execute(sa.select(reports.L.c.owner_user_id, sa.func.count())
                                 .where(*reports._leads(caller, f), sa.cast(reports.L.c.stage, sa.Text) == "won",
                                        *f.window(reports.L.c.won_at), reports.L.c.owner_user_id.in_(ids))
                                 .group_by(reports.L.c.owner_user_id))).all()
        out["leads_won"] = {str(r[0]): Decimal(r[1]) for r in rows}
    if "tracking" in caller.scopes:
        rows = (await db.execute(text(
            "SELECT user_id::text, count(*) FROM visit WHERE checkin_at >= :lo AND checkin_at < :hi "
            "AND user_id = ANY(CAST(:i AS uuid[])) GROUP BY user_id"), {"lo": f.lo, "hi": f.hi, "i": ids})).all()
        out["visits"] = {r[0]: Decimal(r[1]) for r in rows}
    return out


