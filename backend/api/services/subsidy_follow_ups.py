# ruff: noqa: E501  (embedded SQL)

"""Subsidy follow-ups (FS-009a): the ageing view, the stage and supply reports, and
masters revisions. Every read is under the caller's own policies; revisions write
under `masters.edit` (009's grants), and 011's triggers refuse any edit but closing a
row. Services never commit."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import subsidy_ageing as domain
from api.errors import ConflictError, ValidationFailed
from api.schemas import subsidy_follow_ups as sch
from api.schemas.leads import PageMeta
from api.services import subsidy as engine
from api.services.clock import today_ist
from api.services.leads import _decode_cursor, _encode_cursor

_LIMIT = 100


def _m(v: Any) -> str:
    return format(Decimal(v or 0).quantize(Decimal("0.01")), "f")


# ── ageing ───────────────────────────────────────────────────────────────────

async def ageing(db: AsyncSession, *, status: str | None = None, stage: str | None = None,
                 q: str | None = None, cursor: str | None = None, limit: int = 50) -> sch.AgePage:
    limit = max(1, min(limit, _LIMIT))
    where = ["true"]
    params: dict[str, Any] = {"lim": limit + 1, "keys": list(domain.FIELDS)}
    if status:
        where.append("a.status::text = :st")
        params["st"] = status
    if stage:
        where.append("d.code = :sg")
        params["sg"] = stage
    if q:
        where.append("(a.application_no ILIKE :q OR a.reg_no ILIKE :q OR a.farmer_name ILIKE :q)")
        params["q"] = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    if cursor:
        at, aid = _decode_cursor(cursor)
        where.append("(a.created_at, a.id) < (:at, CAST(:aid AS uuid))")
        params.update(at=at, aid=aid)
    rows = (await db.execute(text(
        "SELECT a.id, a.application_no::text AS no, a.reg_no::text AS reg, a.farmer_name, a.status::text AS status, "
        "a.full_fp_received_on, a.created_at, d.name AS stage, "
        # the day it was cancelled, in IST, from its own event: updated_at moves on any later write
        "(SELECT (max(ev.occurred_at) AT TIME ZONE 'Asia/Kolkata')::date FROM activity_event ev "
        "  WHERE ev.entity_type = 'subsidy_application' AND ev.entity_id = a.id AND ev.kind = 'subsidy.cancelled') "
        "  AS cancelled_on, "
        "(SELECT t.name FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id "
        "  WHERE tc.descendant_id = a.territory_id AND t.level = 'district' LIMIT 1) AS district "
        "FROM subsidy_application a JOIN subsidy_stage_def d ON d.id = a.current_stage_id "
        f"WHERE {' AND '.join(where)} ORDER BY a.created_at DESC, a.id DESC LIMIT :lim"), params)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].created_at, str(rows[-1].id))
    dates: dict[str, dict[str, dt.date | None]] = {}
    if rows:
        # the latest entry carrying each field (FS-009's rule), for the whole page at once
        for r in (await db.execute(text(
                # the latest entry carrying the field wins, even when it cleared it (code review F-3)
                "SELECT DISTINCT ON (e.application_id, v.field_key) e.application_id, v.field_key, v.value_date "
                "FROM subsidy_stage_value v JOIN subsidy_stage_entry e ON e.id = v.entry_id "
                "WHERE e.application_id = ANY(CAST(:ids AS uuid[])) AND v.field_key = ANY(CAST(:keys AS text[])) "
                "ORDER BY e.application_id, v.field_key, e.entered_at DESC, e.id DESC"),
                {"ids": [str(r.id) for r in rows], "keys": list(domain.FIELDS)})).all():
            if r.value_date is not None:
                dates.setdefault(str(r.application_id), {})[r.field_key] = r.value_date
    today = today_ist()
    out = []
    for r in rows:
        stopped = r.cancelled_on if r.status == "cancelled" else None
        figures = domain.ageing(dates.get(str(r.id), {}), r.full_fp_received_on, stopped, today)
        out.append(sch.AgeRow(
            application=sch.AgeRef(id=str(r.id), application_no=r.no, reg_no=r.reg, farmer_name=r.farmer_name,
                                   status=r.status, stage=r.stage, district=r.district),
            **{name: sch.AgeFigure(days=f.days, running=f.running,
                                   since=f.start.isoformat() if f.start else None,
                                   until=f.end.isoformat() if f.end else None)
               for name, f in figures.items()}))
    return sch.AgePage(data=out, meta=PageMeta(limit=limit, next_cursor=next_cursor))


# ── reports ──────────────────────────────────────────────────────────────────

async def stage_report(db: AsyncSession, status: str | None = "open") -> sch.StagePage:
    rows = (await db.execute(text(
        "SELECT d.seq, d.code, COALESCE(min(d.name) FILTER (WHERE s.code = 'GGRC'), min(d.name)) AS name, count(a.id) AS n, sum(a.total_cost) AS cost, sum(a.subsidy) AS subsidy, "
        "sum(a.farmer_share) AS farmer, max(CAST(:today AS date) - a.current_since) AS oldest "
        "FROM subsidy_application a JOIN subsidy_stage_def d ON d.id = a.current_stage_id "
        "JOIN subsidy_scheme s ON s.id = d.scheme_id "
        "WHERE (CAST(:st AS text) IS NULL OR a.status::text = :st) "
        "GROUP BY d.seq, d.code ORDER BY d.seq"), {"today": today_ist(), "st": status})).all()
    data = [sch.StageRow(seq=r.seq, code=r.code, name=r.name, count=r.n, total_cost=_m(r.cost),
                         subsidy=_m(r.subsidy), farmer_share=_m(r.farmer), oldest_days_in_stage=r.oldest)
            for r in rows]
    return sch.StagePage(data=data, meta=PageMeta(limit=len(data), next_cursor=None))


async def supply_report(db: AsyncSession, status: str | None = None) -> sch.SupplyPage:
    rows = (await db.execute(text(
        "WITH x AS (SELECT a.total_cost, subsidy_value_date(a.id, 'supply') IS NOT NULL AS supplied, "
        "  coalesce((SELECT t.name FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id "
        "    WHERE tc.descendant_id = a.territory_id AND t.level = 'district' LIMIT 1), '(no district)') AS district "
        "  FROM subsidy_application a WHERE (CAST(:st AS text) IS NULL AND a.status <> 'cancelled' "
        "  OR a.status::text = :st)) "
        "SELECT district, count(*) FILTER (WHERE supplied) AS s, count(*) FILTER (WHERE NOT supplied) AS ns, "
        "sum(total_cost) FILTER (WHERE supplied) AS sc, sum(total_cost) FILTER (WHERE NOT supplied) AS nsc "
        "FROM x GROUP BY district ORDER BY district"), {"st": status})).all()
    data = [sch.SupplyRow(district=r.district, supplied=r.s, not_supplied=r.ns, supplied_cost=_m(r.sc),
                          not_supplied_cost=_m(r.nsc)) for r in rows]
    return sch.SupplyPage(data=data, meta=PageMeta(limit=len(data), next_cursor=None))


# ── masters revisions (rule 7) ───────────────────────────────────────────────

class _Kind:
    def __init__(self, table: str, model: type[BaseModel], keys: tuple[str, ...], casts: dict[str, str]) -> None:
        self.table, self.model, self.keys, self.casts = table, model, keys, casts


KINDS: Final[dict[str, _Kind]] = {
    "categories": _Kind("subsidy_category", sch.CategoryRow, ("system_type", "code"),
                        {"system_type": "subsidy_system_type", "variant": "subsidy_matrix_variant"}),
    "parameters": _Kind("subsidy_parameter", sch.ParameterRow, ("system_type", "key"),
                        {"system_type": "subsidy_system_type", "unit": "subsidy_param_unit"}),
    "component-rates": _Kind("subsidy_component_rate", sch.ComponentRateRow,
                             ("system_type", "component_code", "pipe_size_mm", "nozzle"),
                             {"system_type": "subsidy_system_type", "nozzle": "subsidy_nozzle"}),
    "crop-spacings": _Kind("crop_lateral_spacing", sch.CropSpacingRow, ("crop",), {}),
}


async def _scheme_id(db: AsyncSession, code: str) -> str:
    sid = (await db.execute(text("SELECT id FROM subsidy_scheme WHERE code = :c"), {"c": code})).scalar_one_or_none()
    if sid is None:
        raise ValidationFailed(fields={"scheme": "Unknown scheme."})
    return str(sid)


def _check_date(effective_from: dt.date) -> None:
    if effective_from < today_ist():
        raise ValidationFailed("A revision starts today or later; a backdated one would restate stored calculations.",
                               code="revision_in_past", fields={"effective_from": "Today or later."})


async def list_master(db: AsyncSession, kind: str, scheme: str, on: dt.date | None) -> list[dict[str, Any]]:
    k = KINDS[kind]
    sid = await _scheme_id(db, scheme)
    cols = ", ".join(f"{c}::text AS {c}" if c in k.casts or c in ("code", "key", "crop", "component_code") else c
                     for c in k.model.model_fields)
    rows = (await db.execute(text(
        f"SELECT id, {cols}, effective_from, effective_to FROM {k.table} WHERE scheme_id = CAST(:s AS uuid) "
        "AND daterange(effective_from, effective_to, '[)') @> CAST(:d AS date) ORDER BY 2, 3"),
        {"s": sid, "d": on or today_ist()})).mappings().all()
    return [{key: (format(v, "f") if isinstance(v, Decimal) else v.isoformat() if isinstance(v, dt.date) else
                   str(v) if key == "id" else v) for key, v in r.items()} for r in rows]


async def revise(db: AsyncSession, user_id: str, kind: str, body: sch.Revision) -> sch.RevisionResult:
    k = KINDS[kind]
    _check_date(body.effective_from)
    sid = await _scheme_id(db, body.scheme)
    rows: list[BaseModel] = []
    for i, raw in enumerate(body.rows):
        try:
            rows.append(k.model.model_validate(raw))
        except ValidationError as exc:
            raise ValidationFailed(fields={f"rows[{i}]": exc.errors()[0]["msg"]}) from exc
    closed = 0
    for i, row in enumerate(rows):
        values = row.model_dump()
        key_sql = " AND ".join(
            f"{c} IS NOT DISTINCT FROM CAST(:k_{c} AS {k.casts.get(c, 'text' if c != 'pipe_size_mm' else 'smallint')})"
            if c not in ("code", "key", "crop", "component_code")
            else f"{c} = CAST(:k_{c} AS citext)" for c in k.keys)
        kp = {f"k_{c}": values[c] for c in k.keys}
        later = (await db.execute(text(
            f"SELECT effective_from FROM {k.table} WHERE scheme_id = CAST(:s AS uuid) AND {key_sql} "
            "AND effective_from >= :f ORDER BY effective_from LIMIT 1"), {"s": sid, "f": body.effective_from, **kp})).scalar_one_or_none()
        if later == body.effective_from:
            raise ConflictError("A row with this key already starts on that date.", code="revision_on_start_date",
                                fields={f"rows[{i}]": "Starts that day already."})
        if later is not None:
            raise ConflictError("A later revision exists for this row; revise from after it.",
                                code="later_revision_exists", fields={f"rows[{i}]": "A later revision exists."})
        res = await db.execute(text(
            f"UPDATE {k.table} SET effective_to = :f, updated_by = CAST(:u AS uuid) WHERE scheme_id = CAST(:s AS uuid) "
            f"AND {key_sql} AND effective_from < :f AND (effective_to IS NULL OR effective_to > :f)"),
            {"s": sid, "f": body.effective_from, "u": user_id, **kp})
        closed += res.rowcount or 0  # type: ignore[attr-defined]
        cols = list(values)
        placeholders = ", ".join(f"CAST(:{c} AS {k.casts[c]})" if c in k.casts else f":{c}" for c in cols)
        try:
            async with db.begin_nested():
                await db.execute(text(
                    f"INSERT INTO {k.table} (scheme_id, {', '.join(cols)}, effective_from, created_by, updated_by) "
                    f"VALUES (CAST(:s AS uuid), {placeholders}, :f, CAST(:u AS uuid), CAST(:u AS uuid))"),
                    {"s": sid, "f": body.effective_from, "u": user_id, **values})
        except DBAPIError as exc:
            raise ValidationFailed(fields={f"rows[{i}]": str(getattr(exc.orig, 'args', [''])[0])[:200]}) from exc
    engine.clear_cache()
    return sch.RevisionResult(closed=closed, inserted=len(rows), effective_from=body.effective_from.isoformat())


async def revise_matrix(db: AsyncSession, user_id: str, kind: str, body: sch.MatrixRevision) -> sch.RevisionResult:
    _check_date(body.effective_from)
    sid = await _scheme_id(db, body.scheme)
    if kind == "unit-cost-matrices":
        if not body.unit_cost_cells or body.variant is None or body.dimensionality is None:
            raise ValidationFailed(fields={"unit_cost_cells": "Cells, variant and dimensionality are required."})
        table, match = "unit_cost_matrix", "AND variant = CAST(:v AS subsidy_matrix_variant)"
    else:
        if not body.quantity_cells:
            raise ValidationFailed(fields={"quantity_cells": "Cells are required."})
        table, match = "quantity_matrix", ""
    p = {"s": sid, "t": body.system_type, "v": body.variant, "f": body.effective_from, "u": user_id}
    later = (await db.execute(text(
        f"SELECT effective_from FROM {table} WHERE scheme_id = CAST(:s AS uuid) AND system_type = CAST(:t AS subsidy_system_type) "
        f"{match} AND effective_from >= :f ORDER BY effective_from LIMIT 1"), p)).scalar_one_or_none()
    if later is not None:
        raise ConflictError("A matrix already starts on or after that date.",
                            code="revision_on_start_date" if later == body.effective_from else "later_revision_exists")
    res = await db.execute(text(
        f"UPDATE {table} SET effective_to = :f, updated_by = CAST(:u AS uuid) WHERE scheme_id = CAST(:s AS uuid) "
        f"AND system_type = CAST(:t AS subsidy_system_type) {match} AND effective_from < :f "
        "AND (effective_to IS NULL OR effective_to > :f)"), p)
    if kind == "unit-cost-matrices":
        mid: Any = (await db.execute(text(
            "INSERT INTO unit_cost_matrix (scheme_id, system_type, variant, dimensionality, effective_from, source, created_by, updated_by) "
            "VALUES (CAST(:s AS uuid), CAST(:t AS subsidy_system_type), CAST(:v AS subsidy_matrix_variant), :d, :f, :src, "
            "CAST(:u AS uuid), CAST(:u AS uuid)) RETURNING id"), {**p, "d": body.dimensionality, "src": body.source})).scalar_one()
        for c in body.unit_cost_cells or []:
            await db.execute(text("INSERT INTO unit_cost_cell (matrix_id, lateral_spacing, area_breakpoint, unit_cost) "
                                  "VALUES (CAST(:m AS uuid), :ls, :a, :c)"),
                             {"m": str(mid), "ls": c.lateral_spacing, "a": c.area_breakpoint, "c": c.unit_cost})
        n = len(body.unit_cost_cells or [])
    else:
        mid = (await db.execute(text(
            "INSERT INTO quantity_matrix (scheme_id, system_type, effective_from, source, created_by, updated_by) "
            "VALUES (CAST(:s AS uuid), CAST(:t AS subsidy_system_type), :f, :src, CAST(:u AS uuid), CAST(:u AS uuid)) "
            "RETURNING id"), {**p, "src": body.source})).scalar_one()
        for qc in body.quantity_cells or []:
            await db.execute(text("INSERT INTO quantity_matrix_cell (matrix_id, component_code, area_breakpoint, qty) "
                                  "VALUES (CAST(:m AS uuid), :cc, :a, :q)"),
                             {"m": str(mid), "cc": qc.component_code, "a": qc.area_breakpoint, "q": qc.qty})
        n = len(body.quantity_cells or [])
    engine.clear_cache()
    return sch.RevisionResult(closed=res.rowcount or 0, inserted=n,  # type: ignore[attr-defined]
                              effective_from=body.effective_from.isoformat())


async def list_matrices(db: AsyncSession, kind: str, scheme: str, on: dt.date | None) -> list[dict[str, Any]]:
    """The matrices in force on a date, with their cells (code review F-4)."""
    sid = await _scheme_id(db, scheme)
    day = on or today_ist()
    if kind == "unit-cost-matrices":
        heads = (await db.execute(text(
            "SELECT id, system_type::text AS system_type, variant::text AS variant, dimensionality, effective_from, "
            "effective_to, source FROM unit_cost_matrix WHERE scheme_id = CAST(:s AS uuid) "
            "AND daterange(effective_from, effective_to, '[)') @> CAST(:d AS date) ORDER BY system_type, variant"),
            {"s": sid, "d": day})).mappings().all()
        cells_sql = ("SELECT matrix_id, lateral_spacing, area_breakpoint, unit_cost FROM unit_cost_cell "
                     "WHERE matrix_id = ANY(CAST(:ids AS uuid[])) ORDER BY lateral_spacing NULLS FIRST, area_breakpoint")
    else:
        heads = (await db.execute(text(
            "SELECT id, system_type::text AS system_type, effective_from, effective_to, source FROM quantity_matrix "
            "WHERE scheme_id = CAST(:s AS uuid) AND daterange(effective_from, effective_to, '[)') @> CAST(:d AS date) "
            "ORDER BY system_type"), {"s": sid, "d": day})).mappings().all()
        cells_sql = ("SELECT matrix_id, component_code::text AS component_code, area_breakpoint, qty "
                     "FROM quantity_matrix_cell WHERE matrix_id = ANY(CAST(:ids AS uuid[])) "
                     "ORDER BY component_code, area_breakpoint")
    cells = (await db.execute(text(cells_sql), {"ids": [str(h["id"]) for h in heads]})).mappings().all()

    def plain(v: Any) -> Any:
        return format(v, "f") if isinstance(v, Decimal) else v.isoformat() if isinstance(v, dt.date) else v

    out = []
    for h in heads:
        row = {k: (str(v) if k == "id" else plain(v)) for k, v in h.items()}
        row["cells"] = [{k: plain(v) for k, v in c.items() if k != "matrix_id"}
                        for c in cells if c["matrix_id"] == h["id"]]
        out.append(row)
    return out
