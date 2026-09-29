"""Subsidy applications (FS-009). Every write to an application goes through its
definers (migration 025); reads run under the `subsidy` scope's policies."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import io
import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import complaints as upload_rules
from api.domain.leads import financial_year
from api.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationFailed,
)
from api.schemas import subsidy_applications as sch
from api.schemas.leads import UserRef
from api.schemas.subsidy import CalculateResponse
from api.services import people
from api.services import subsidy as engine
from api.services.clock import today_ist
from api.services.leads import _decode_cursor, _encode_cursor
from api.storage import Storage

log = structlog.get_logger(__name__)

MAX_DOCUMENTS = 40          # edge case 19; the checklist has 20 items
MAX_AMOUNT = Decimal("1e12")  # numeric(14,2) holds twelve digits before the point
_LIMIT = 100
_MONEY = Decimal("0.01")


def _state(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _message(exc: DBAPIError) -> str:
    return str(getattr(exc.orig, "args", [""])[0] or exc.orig).split("\n")[0]


def _dec(v: Any) -> str | None:
    return None if v is None else format(Decimal(v), "f")


# ── forwarding a lead ────────────────────────────────────────────────────────

def _prefixed(exc: ValidationFailed) -> ValidationFailed:
    """The engine's field paths, under `calculation.` (review R-12)."""
    fields = {f"calculation.{k}": v for k, v in (exc.fields or {}).items()}
    return ValidationFailed(exc.message, code=exc.code, fields=fields or {"calculation": exc.message})


def figures_for(calc: CalculateResponse, category_code: str) -> tuple[Decimal, Decimal, str, str]:
    """(subsidy, farmer share, name, pct) for a category that applies on every crop:
    the per-crop figures summed (review B-6)."""
    subsidy = farmer = Decimal(0)
    name = pct = ""
    for i, crop in enumerate(calc.crops):
        row = next((c for c in crop.categories if c.code == category_code), None)
        if row is None:
            raise ValidationFailed(fields={"category_code": "not a category of this calculation"})
        if not row.applicable:
            raise ValidationFailed(fields={"category_code": row.reason or f"does not apply on crop {i + 1}"})
        subsidy += Decimal(row.subsidy)
        farmer += Decimal(row.farmer_share)
        name, pct = row.name, row.pct
    return subsidy, farmer, name, pct


_CREATE_ERRORS = {
    "SAPNS": ("lead_not_subsidised", "the lead's inquiry is not subsidised"),
    "SAPST": ("lead_not_forwardable", "the lead must be qualified, quoted, in negotiation or won"),
    "SAPSY": ("lead_system_not_subsidised", "the lead's system has no subsidy calculation"),
    "SAPDU": ("already_forwarded", "the lead has an application"),
    "SAPSC": ("territory_without_state_code", "the lead's territory has no coded state"),
}


async def create(db: AsyncSession, caller: Caller, body: sch.ApplicationCreate) -> sch.Application:
    lead = (await db.execute(text(
        "SELECT l.id, ms.code AS mis FROM lead l JOIN mis_system ms ON ms.id = l.mis_system_id "
        "WHERE l.id = CAST(:l AS uuid) AND l.deleted_at IS NULL"), {"l": body.lead_id})).one_or_none()
    if lead is None:
        raise NotFoundError("No such lead.")
    if body.calculation.system_type != lead.mis:
        raise ValidationFailed(fields={"calculation.system_type": f"the lead's system is {lead.mis}"})
    try:
        calc = await engine.calculate(db, body.calculation)
    except ValidationFailed as exc:
        raise _prefixed(exc) from exc
    subsidy, farmer, name, pct = figures_for(calc, body.category_code)
    total_area = sum((c.area for c in body.calculation.crops), Decimal(0))
    try:
        async with db.begin_nested():
            app_id = str((await db.execute(text(
                "SELECT subsidy_application_create(CAST(:l AS uuid), :cc, :cn, CAST(:cp AS numeric), "
                "CAST(:req AS jsonb), CAST(:calc AS jsonb), :tc, :sub, :fs, :area, :grp, :fv, "
                "CAST(:rm AS uuid), CAST(:sm AS uuid), :as_of, :survey, :fy, :sys)"), {
                    "l": body.lead_id, "cc": body.category_code, "cn": name, "cp": pct,
                    "req": body.calculation.model_dump_json(), "calc": calc.model_dump_json(),
                    "tc": Decimal(calc.total.blocks.total_incl_gst), "sub": subsidy, "fs": farmer,
                    "area": total_area, "grp": body.calculation.group_total_area,
                    "fv": calc.masters.formula_version, "rm": calc.masters.regular_matrix_id,
                    "sm": calc.masters.seven_year_matrix_id,
                    "as_of": dt.date.fromisoformat(calc.masters.as_of), "survey": body.survey_no,
                    "fy": financial_year(dt.datetime.now(dt.UTC)),
                    "sys": body.calculation.system_type})).scalar_one())
    except DBAPIError as exc:
        state = _state(exc)
        if state == "SAPNF":
            raise NotFoundError("No such lead.") from exc
        if state in _CREATE_ERRORS:
            code, why = _CREATE_ERRORS[state]
            raise ValidationFailed(code=code, fields={"lead_id": why}) from exc
        if state == "23505":  # the partial unique index, behind the lead lock (review F-3)
            code, why = _CREATE_ERRORS["SAPDU"]
            raise ValidationFailed(code=code, fields={"lead_id": why}) from exc
        if state == "42501":
            raise ForbiddenError("You may not start subsidy applications.") from exc
        raise
    return await get(db, app_id)


# ── reading ──────────────────────────────────────────────────────────────────

_SELECT = """
SELECT a.*, s.code AS scheme_code, d.seq AS stage_seq, d.code AS stage_code, d.name AS stage_name,
       l.inquiry_no::text AS inquiry_no, t.name AS territory_name, t.level::text AS territory_level,
       cp.name AS partner_name, ou.name AS org_unit_name,
       (SELECT count(DISTINCT sd.document_type_id) FROM subsidy_document sd
         WHERE sd.application_id = a.id AND sd.deleted_at IS NULL) AS docs_uploaded,
       (SELECT count(*) FROM subsidy_document_type dt2 WHERE dt2.is_active AND dt2.deleted_at IS NULL) AS docs_listed,
       COALESCE(
         (SELECT sv.value_date FROM subsidy_stage_value sv JOIN subsidy_stage_entry e ON e.id = sv.entry_id
           WHERE e.application_id = a.id AND sv.field_key = 'app_inward'
           ORDER BY e.entered_at DESC, e.id DESC LIMIT 1),
         (SELECT e.occurred_on FROM subsidy_stage_entry e JOIN subsidy_stage_def d4 ON d4.id = e.stage_def_id
           WHERE e.application_id = a.id AND d4.seq = 4 ORDER BY e.entered_at, e.id LIMIT 1)) AS inward_on
  FROM subsidy_application a
  JOIN subsidy_scheme s ON s.id = a.scheme_id
  JOIN subsidy_stage_def d ON d.id = a.current_stage_id
  JOIN lead l ON l.id = a.lead_id
  JOIN territory t ON t.id = a.territory_id
  JOIN org_unit ou ON ou.id = a.owner_org_unit_id
  LEFT JOIN channel_partner cp ON cp.id = a.partner_id
"""


def _to_app(r: Any, names: people.Names) -> sch.Application:
    today = today_ist()
    owner = names.user(r.owner_user_id, None)
    return sch.Application(
        id=str(r.id), application_no=r.application_no, reg_no=r.reg_no, status=r.status,
        current_stage=sch.StageRef(seq=r.stage_seq, code=r.stage_code, name=r.stage_name,
                                   since=r.current_since.isoformat()),
        scheme=r.scheme_code, system_type=r.system_type,
        category=sch.Category(code=r.category_code, name=r.category_name, pct=_dec(r.category_pct) or "0"),
        lead=sch.ApplicationLeadRef(id=str(r.lead_id), inquiry_no=r.inquiry_no or ""),
        farmer_name=r.farmer_name, mobile=r.mobile, village=r.village, survey_no=r.survey_no,
        territory=sch.TerritoryRef(id=str(r.territory_id), name=r.territory_name, level=r.territory_level),
        partner=sch.Ref(id=str(r.partner_id), name=r.partner_name or "") if r.partner_id else None,
        total_area=_dec(r.total_area) or "0", group_total_area=_dec(r.group_total_area),
        figures=sch.Figures(total_cost=_dec(r.total_cost) or "0", subsidy=_dec(r.subsidy) or "0",
                            farmer_share=_dec(r.farmer_share) or "0"),
        owner=owner, owner_org_unit=sch.Ref(id=str(r.owner_org_unit_id), name=r.org_unit_name),
        documents=sch.DocumentCount(uploaded=int(r.docs_uploaded), listed=int(r.docs_listed)),
        ageing=sch.Ageing(days_in_stage=(today - r.current_since).days,
                          days_since_inward=(today - r.inward_on).days if r.inward_on else None),
        full_fp_received_on=r.full_fp_received_on.isoformat() if r.full_fp_received_on else None,
        created_at=r.created_at.isoformat(),
        cancellation=sch.ApplicationCancellation(reason=r.cancel_reason) if r.cancel_reason else None)


async def get(db: AsyncSession, app_id: str) -> sch.Application:
    r = (await db.execute(text(_SELECT + " WHERE a.id = CAST(:a AS uuid)"), {"a": app_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such application.")
    return _to_app(r, await people.resolve_ids(db, [str(r.owner_user_id)] if r.owner_user_id else []))


async def list_applications(db: AsyncSession, *, status: str | None = None, stage: str | None = None,
                            q: str | None = None, cursor: str | None = None,
                            limit: int = 50) -> sch.ApplicationPage:
    limit = max(1, min(limit, _LIMIT))
    where: list[str] = ["true"]
    params: dict[str, Any] = {"lim": limit + 1}
    if status:
        where.append("a.status::text = :st")
        params["st"] = status
    if stage:
        where.append("d.code = :sg")
        params["sg"] = stage
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(a.application_no ILIKE :q OR a.reg_no ILIKE :q OR a.farmer_name ILIKE :q)")
        params["q"] = like
    if cursor:
        at, aid = _decode_cursor(cursor)
        where.append("(a.created_at, a.id) < (:at, CAST(:aid AS uuid))")
        params.update(at=at, aid=aid)
    rows = (await db.execute(text(_SELECT + " WHERE " + " AND ".join(where) +
                                  " ORDER BY a.created_at DESC, a.id DESC LIMIT :lim"), params)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].created_at, str(rows[-1].id))
    names = await people.resolve_ids(db, {str(r.owner_user_id) for r in rows if r.owner_user_id})
    return sch.ApplicationPage(data=[_to_app(r, names) for r in rows],
                               meta=sch.ApplicationPageMeta(next_cursor=next_cursor))


async def calculation(db: AsyncSession, app_id: str) -> dict[str, Any]:
    raw = (await db.execute(text("SELECT calculation FROM subsidy_application WHERE id = CAST(:a AS uuid)"),
                            {"a": app_id})).scalar_one_or_none()
    if raw is None:
        raise NotFoundError("No such application.")
    out: dict[str, Any] = json.loads(raw) if isinstance(raw, str) else raw
    return out


# ── stages ───────────────────────────────────────────────────────────────────

async def stage_defs(db: AsyncSession, scheme: str) -> list[sch.StageDef]:
    rows = (await db.execute(text(
        "SELECT d.id, d.seq, d.code, d.name, f.field_key, f.label, f.type::text AS type, f.is_required "
        "FROM subsidy_stage_def d JOIN subsidy_scheme s ON s.id = d.scheme_id "
        "LEFT JOIN subsidy_stage_field f ON f.stage_def_id = d.id AND f.is_active "
        "WHERE s.code = :s AND d.is_active ORDER BY d.seq, f.sort_order"), {"s": scheme})).all()
    out: dict[str, sch.StageDef] = {}
    for r in rows:
        stage = out.setdefault(str(r.id), sch.StageDef(seq=r.seq, code=r.code, name=r.name, fields=[]))
        if r.field_key:
            stage.fields.append(sch.FieldDef(key=r.field_key, label=r.label, type=r.type,
                                             required=r.is_required))
    return list(out.values())


async def entries(db: AsyncSession, app_id: str) -> list[sch.Entry]:
    if (await db.execute(text("SELECT 1 FROM subsidy_application WHERE id = CAST(:a AS uuid)"),
                         {"a": app_id})).one_or_none() is None:
        raise NotFoundError("No such application.")
    rows = (await db.execute(text(
        "SELECT e.id, e.occurred_on, e.remark, e.entered_by, e.entered_at, d.seq, d.code, d.name, "
        "       v.field_key, v.value_text, v.value_date, v.value_amount "
        "FROM subsidy_stage_entry e JOIN subsidy_stage_def d ON d.id = e.stage_def_id "
        "LEFT JOIN subsidy_stage_value v ON v.entry_id = e.id "
        "WHERE e.application_id = CAST(:a AS uuid) ORDER BY e.entered_at, e.id, v.field_key"),
        {"a": app_id})).all()
    names = await people.resolve_ids(db, {str(r.entered_by) for r in rows})
    out: dict[str, sch.Entry] = {}
    for r in rows:
        who = str(r.entered_by)
        e = out.setdefault(str(r.id), sch.Entry(
            id=str(r.id), stage=sch.StageRef(seq=r.seq, code=r.code, name=r.name,
                                             since=r.occurred_on.isoformat()),
            occurred_on=r.occurred_on.isoformat(), values={}, remark=r.remark,
            entered_by=UserRef(id=who, full_name=names.users.get(who) or ""),
            entered_at=r.entered_at.isoformat()))
        if r.field_key:
            value = (r.value_date.isoformat() if r.value_date else _dec(r.value_amount)
                     if r.value_amount is not None else r.value_text)
            e.values[r.field_key] = value
    return list(out.values())


def _check_value(kind: str, key: str, value: Any) -> None:
    """The per-field 422 before the definer's generic one (review R-7)."""
    if value is None:
        return
    raw = str(value).strip()
    if kind == "date":
        try:
            day = dt.date.fromisoformat(raw)
        except ValueError as exc:
            raise ValidationFailed(fields={f"values.{key}": "an ISO date"}) from exc
        if day > today_ist():
            raise ValidationFailed(fields={f"values.{key}": "not after today"})
    elif kind == "amount":
        # the quantize raises on a huge value, so it sits in the try (review F-1)
        try:
            amt = Decimal(raw)
            ok = amt.is_finite() and 0 <= amt < MAX_AMOUNT and amt == amt.quantize(_MONEY)
        except InvalidOperation as exc:
            raise ValidationFailed(fields={f"values.{key}": "a decimal amount"}) from exc
        if not ok:
            raise ValidationFailed(fields={f"values.{key}": "an amount, 0 or more, under 1,00,00,00,00,000, two decimals at most"})
    elif len(raw) > 500 or "\x00" in raw:
        raise ValidationFailed(fields={f"values.{key}": "500 characters at most"})


_STAGE_ERRORS = {
    "SAPSG": ("stage_code", "not a stage of this scheme"),
    "SAPDT": ("occurred_on", "not after today"),
    "SAPRM": ("remark", "required for a backward or same-stage entry"),
}


async def record(db: AsyncSession, app_id: str, body: sch.StageRecord) -> sch.Application:
    if body.occurred_on > today_ist():
        raise ValidationFailed(fields={"occurred_on": "not after today"})
    fields = {r.field_key: r.type for r in (await db.execute(text(
        "SELECT f.field_key, f.type::text AS type FROM subsidy_stage_field f "
        "JOIN subsidy_stage_def d ON d.id = f.stage_def_id "
        "JOIN subsidy_application a ON a.scheme_id = d.scheme_id AND a.id = CAST(:a AS uuid) "
        "WHERE d.code = :s AND f.is_active"), {"a": app_id, "s": body.stage_code})).all()}
    for key, value in body.values.items():
        if key not in fields:
            raise ValidationFailed(fields={f"values.{key}": "not a field of this stage"})
        _check_value(fields[key], key, value)
    # blank text is a cleared field, as null is (review F-2)
    values = {k: (None if v is None or str(v).strip() == "" else str(v).strip()) for k, v in body.values.items()}
    try:
        async with db.begin_nested():
            await db.execute(text(
                "SELECT subsidy_stage_record(CAST(:a AS uuid), :s, :d, CAST(:v AS jsonb), :r)"),
                {"a": app_id, "s": body.stage_code, "d": body.occurred_on,
                 "v": json.dumps(values), "r": body.remark})
    except DBAPIError as exc:
        state = _state(exc)
        if state == "SAPAN":
            raise NotFoundError("No such application.") from exc
        if state == "SAPCL":
            raise ConflictError("The application is closed.", code="status_changed") from exc
        if state in _STAGE_ERRORS:
            field, why = _STAGE_ERRORS[state]
            raise ValidationFailed(fields={field: why}) from exc
        if state in ("SAPFK", "SAPFV"):
            raise ValidationFailed(fields={f"values.{_message(exc)}": "not accepted"}) from exc
        if state == "42501":
            raise ForbiddenError("You may not record stages.") from exc
        raise
    return await get(db, app_id)


async def cancel(db: AsyncSession, app_id: str, body: sch.Cancel) -> sch.Application:
    try:
        async with db.begin_nested():
            await db.execute(text("SELECT subsidy_application_cancel(CAST(:a AS uuid), :r)"),
                             {"a": app_id, "r": body.reason})
    except DBAPIError as exc:
        state = _state(exc)
        if state == "SAPAN":
            raise NotFoundError("No such application.") from exc
        if state == "SAPCL":
            raise ConflictError("The application is closed.", code="status_changed") from exc
        if state == "42501":
            raise ForbiddenError("You may not cancel applications.") from exc
        raise
    return await get(db, app_id)


# ── documents (ADR-041) ──────────────────────────────────────────────────────

async def document_types(db: AsyncSession) -> list[sch.DocumentType]:
    rows = (await db.execute(text(
        "SELECT id, code::text AS code, name, is_active FROM subsidy_document_type "
        "WHERE deleted_at IS NULL ORDER BY sort_order, name"))).all()
    return [sch.DocumentType(id=str(r.id), code=r.code, name=r.name, is_active=r.is_active) for r in rows]


async def checklist(db: AsyncSession, app_id: str) -> list[sch.ChecklistItem]:
    if (await db.execute(text("SELECT 1 FROM subsidy_application WHERE id = CAST(:a AS uuid)"),
                         {"a": app_id})).one_or_none() is None:
        raise NotFoundError("No such application.")
    files = (await db.execute(text(
        "SELECT id, document_type_id, content_type, size_bytes, original_name, uploaded_by, created_at "
        "FROM subsidy_document WHERE application_id = CAST(:a AS uuid) AND deleted_at IS NULL "
        "ORDER BY created_at"), {"a": app_id})).all()
    names = await people.resolve_ids(db, {str(f.uploaded_by) for f in files})
    by_type: dict[str, list[sch.Document]] = {}
    for f in files:
        who = str(f.uploaded_by)
        by_type.setdefault(str(f.document_type_id), []).append(sch.Document(
            id=str(f.id), content_type=f.content_type, size_bytes=f.size_bytes, filename=f.original_name,
            uploaded_by=UserRef(id=who, full_name=names.users.get(who) or ""),
            created_at=f.created_at.isoformat()))
    # active types, plus a switched-off type that has a file (edge case 18)
    return [sch.ChecklistItem(type=t, files=by_type.get(t.id, []))
            for t in await document_types(db) if t.is_active or t.id in by_type]


async def _document(db: AsyncSession, doc_id: str) -> sch.Document:
    f = (await db.execute(text(
        "SELECT id, content_type, size_bytes, original_name, uploaded_by, created_at FROM subsidy_document "
        "WHERE id = CAST(:d AS uuid)"), {"d": doc_id})).one()
    who = str(f.uploaded_by)
    names = await people.resolve_ids(db, [who])
    return sch.Document(id=str(f.id), content_type=f.content_type, size_bytes=f.size_bytes,
                        filename=f.original_name,
                        uploaded_by=UserRef(id=who, full_name=names.users.get(who) or ""),
                        created_at=f.created_at.isoformat())


async def add_document(db: AsyncSession, caller: Caller, app_id: str, *, document_type: str,
                       filename: str | None, data: bytes, storage: Storage) -> tuple[sch.Document, bool]:
    """Sniff and hash, write to storage outside any lock, then lock, count and
    insert: the complaint path (ADR-041)."""
    if not data:
        raise ValidationFailed(fields={"file": "empty"})
    if len(data) > upload_rules.MAX_UPLOAD_BYTES:
        raise ValidationFailed("Up to 10 MB.", code="attachment_too_large", fields={"file": "over 10 MB"})
    sniffed = upload_rules.sniff(data[:16])
    if sniffed is None:
        raise ValidationFailed("JPEG, PNG, WebP, HEIC or PDF only.", code="attachment_type",
                               fields={"file": "not an allowed type"})
    dtype = (await db.execute(text(
        "SELECT id FROM subsidy_document_type WHERE code = :c AND is_active AND deleted_at IS NULL"),
        {"c": document_type})).scalar_one_or_none()
    if dtype is None:
        raise ValidationFailed(fields={"document_type": "not on the checklist"})
    status = (await db.execute(text("SELECT status::text FROM subsidy_application WHERE id = CAST(:a AS uuid)"),
                               {"a": app_id})).scalar_one_or_none()
    if status is None:
        raise NotFoundError("No such application.")
    if status == "cancelled":
        raise ConflictError("The application is cancelled.", code="status_changed")
    # refuse before anything reaches storage: the route gate is subsidy.view, and a
    # viewer's file would otherwise be written and then refused by the lock
    if not (await db.execute(text(
            "SELECT app_has_permission('subsidy', 'create') OR app_has_permission('subsidy', 'edit')"))).scalar_one():
        raise ForbiddenError("You may not add documents.")
    digest = hashlib.sha256(data).hexdigest()
    existing = (await db.execute(text(
        "SELECT id FROM subsidy_document WHERE application_id = CAST(:a AS uuid) AND sha256 = :h "
        "AND deleted_at IS NULL"), {"a": app_id, "h": digest})).scalar_one_or_none()
    if existing is not None:
        return await _document(db, str(existing)), False
    key = f"subsidy/{app_id}/{uuid.uuid4().hex}.{sniffed.extension}"
    try:
        await asyncio.to_thread(storage.put, key, data, sniffed.content_type)
    except Exception as exc:  # the unconfigured adapter's RuntimeError and every network error
        log.warning("subsidy.storage_unavailable", error=type(exc).__name__)
        raise ServiceUnavailableError("Files cannot be stored right now; try again later.",
                                      code="storage_unavailable") from exc
    try:
        async with db.begin_nested():
            lock = (await db.execute(text("SELECT * FROM subsidy_document_lock(CAST(:a AS uuid))"),
                                     {"a": app_id})).one()
    except DBAPIError as exc:
        if _state(exc) == "42501":
            raise ForbiddenError("You may not add documents.") from exc
        if _state(exc) == "SAPAN":
            raise NotFoundError("No such application.") from exc
        raise
    if lock.status == "cancelled":
        raise ConflictError("The application is cancelled.", code="status_changed")
    if lock.files >= MAX_DOCUMENTS:
        raise ValidationFailed(f"Up to {MAX_DOCUMENTS} files.", code="too_many_documents")
    safe = re.sub(r"[^\w.\- ]", "_", (filename or ""))[:255] or None
    try:
        async with db.begin_nested():
            doc_id = str((await db.execute(text(
                "INSERT INTO subsidy_document (application_id, document_type_id, storage_key, content_type, "
                "size_bytes, sha256, original_name, uploaded_by) VALUES (CAST(:a AS uuid), CAST(:t AS uuid), "
                ":k, :ct, :sz, :h, :fn, CAST(:me AS uuid)) RETURNING id"),
                {"a": app_id, "t": str(dtype), "k": key, "ct": sniffed.content_type, "sz": len(data),
                 "h": digest, "fn": safe, "me": caller.user_id})).scalar_one())
    except DBAPIError as exc:
        if _state(exc) == "23505":
            again = (await db.execute(text(
                "SELECT id FROM subsidy_document WHERE application_id = CAST(:a AS uuid) AND sha256 = :h "
                "AND deleted_at IS NULL"), {"a": app_id, "h": digest})).scalar_one()
            return await _document(db, str(again)), False
        if _state(exc) == "42501":
            raise ForbiddenError("You may not add documents.") from exc
        raise
    lead = (await db.execute(text("SELECT lead_id FROM subsidy_application WHERE id = CAST(:a AS uuid)"),
                             {"a": app_id})).scalar_one()
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('subsidy_application', CAST(:a AS uuid), :l, 'subsidy.document_added', CAST(:me AS uuid), "
        "CAST(:p AS jsonb))"),
        {"a": app_id, "l": lead, "me": caller.user_id,
         "p": json.dumps({"document_id": doc_id, "document_type": document_type})})
    return await _document(db, doc_id), True


async def document_link(db: AsyncSession, app_id: str, doc_id: str, storage: Storage) -> sch.DocumentLink:
    r = (await db.execute(text(
        "SELECT storage_key, original_name, content_type FROM subsidy_document WHERE id = CAST(:d AS uuid) "
        "AND application_id = CAST(:a AS uuid) AND deleted_at IS NULL"),
        {"d": doc_id, "a": app_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such document.")
    try:
        url, expires = storage.presign_get(
            r.storage_key, filename=r.original_name or "document",
            disposition="attachment" if r.content_type == "image/heic" else "inline")
    except RuntimeError as exc:
        raise ServiceUnavailableError("Files cannot be opened right now.",
                                      code="storage_unavailable") from exc
    return sch.DocumentLink(url=url, expires_at=expires.isoformat())


# ── the PIMS sheet (rule 11, GAP-177) ────────────────────────────────────────

PIMS_COLUMNS = ("CostType", "Crop", "ItemCode", "Item", "Size", "Unit", "Rate", "Quantity", "Amount", "Remark")


async def pims_rows(db: AsyncSession, app_id: str) -> list[tuple[Any, ...]]:
    row = (await db.execute(text(
        "SELECT calculation_request, calculation FROM subsidy_application WHERE id = CAST(:a AS uuid)"),
        {"a": app_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such application.")
    req = row.calculation_request if isinstance(row.calculation_request, dict) else json.loads(row.calculation_request)
    calc = row.calculation if isinstance(row.calculation, dict) else json.loads(row.calculation)
    ids = {line["product_id"].lower() for c in req.get("crops", []) for line in c.get("lines", []) if line.get("product_id")}
    ids |= {line["product_id"].lower() for line in req.get("head_lines", []) if line.get("product_id")}
    codes: dict[str, str] = {}
    if ids:
        codes = {str(r.id): r.item_code or "" for r in (await db.execute(text(
            "SELECT id, item_code::text AS item_code FROM product WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": sorted(ids)})).all()}

    def line_row(cost_type: str, crop: str, line: dict[str, Any], size: str = "") -> tuple[Any, ...]:
        rate, qty = Decimal(str(line["rate"])), Decimal(str(line["qty"]))
        return (cost_type, crop, codes.get((line.get("product_id") or "").lower(), ""), line["description"], size,
                line["uom"], rate, qty, rate * qty, "")

    rows: list[tuple[Any, ...]] = []
    education = Decimal(calc["total"]["blocks"].get("education", "0"))
    if education > 0:
        rows.append(("FARMER EDUCATION AND TRAINING", "", "CR 01",
                     "FARMER EDUCATION AND TRAINING WITH @0% CGST & SGST", "", "No", education, Decimal(1),
                     education, ""))
    install_rate = Decimal(str(req.get("installation_rate_per_ha") or "0"))
    for c in req.get("crops", []):
        crop = (c.get("crop") or "").upper()
        if install_rate > 0:
            area = Decimal(str(c["area"]))
            rows.append(("Installation", crop, "BQ 01", "Installation Charges", "", "Ha", install_rate, area,
                         install_rate * area, ""))
    for line in req.get("head_lines", []):
        rows.append(line_row("Head", "", line))
    sprinkler = calc.get("sprinkler")
    if sprinkler:
        for line in sprinkler.get("lines", []):
            rows.append(("Field", "", "", line["description"], str(sprinkler.get("pipe_size_mm", "")), line["uom"],
                         Decimal(line["rate"]), Decimal(line["qty"]), Decimal(line["rate"]) * Decimal(line["qty"]), ""))
    for c in req.get("crops", []):
        crop = (c.get("crop") or "").upper()
        for line in c.get("lines", []):
            rows.append(line_row("Field", crop, line))
    return rows


def pims_workbook(rows: list[tuple[Any, ...]]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "PIMS"
    ws.append(list(PIMS_COLUMNS))
    for r in rows:
        ws.append(list(r))   # openpyxl writes Decimal as a number: no float on the way (rule 4)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
