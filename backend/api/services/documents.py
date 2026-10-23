# ruff: noqa: E501  (embedded SQL and field declarations)

"""Documents on records (FS-050). The file is sniffed, hashed and stored before
the row, outside any lock, as complaint attachments (ADR-041); the row and its
event are written by `record_document_add()`, which checks who may add."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import complaints as files
from api.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationFailed,
)
from api.schemas import documents as sch
from api.services import people
from api.services.complaints import _download_name, _safe_filename
from api.storage import Storage

log = structlog.get_logger()

MAX_PER_RECORD = 50


def _state(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _raise_for(code: str | None, exc: Exception | None = None) -> None:
    if code == "DOCNF":
        raise NotFoundError("No such record.") from exc
    if code == "DOCFB":
        raise ForbiddenError("You may not add documents to this record.") from exc
    if code == "DOCCL":
        raise ConflictError("This record takes no more documents.", code="record_closed") from exc
    if code == "DOCMX":
        raise ValidationFailed(f"Up to {MAX_PER_RECORD} documents on one record.",
                               code="too_many_documents") from exc


def types(record_type: str | None = None) -> list[sch.RecordDocumentType]:
    keep = sch.DOC_TYPES_BY_RECORD[record_type] if record_type else tuple(sch.DOC_TYPE_LABELS)
    return [sch.RecordDocumentType(code=k, label=v, needs_name=k == "other")
            for k, v in sch.DOC_TYPE_LABELS.items() if k in keep]


_SELECT = ("SELECT d.*, u.full_name FROM record_document d LEFT JOIN app_user u ON u.id = d.uploaded_by ")


async def _rows(db: AsyncSession, rows: Any, labels: dict[tuple[str, str], str] | None = None
                ) -> list[sch.RecordDocument]:
    names = await people.resolve(db, rows, [("uploaded_by", "full_name")])
    return [sch.RecordDocument(
        id=str(r.id), record_type=r.record_type, record_id=str(r.record_id),
        record_label=(labels or {}).get((r.record_type, str(r.record_id))),
        doc_type=r.doc_type, doc_type_label=sch.DOC_TYPE_LABELS[r.doc_type], name=r.name,
        filename=r.filename, content_type=r.content_type, size_bytes=r.size_bytes,
        preview=r.content_type != "image/heic", uploaded_by=names.user(r.uploaded_by, r.full_name),
        uploaded_at=r.uploaded_at.isoformat()) for r in rows]


async def add(db: AsyncSession, caller: Caller, *, record_type: str, record_id: str, doc_type: str,
              name: str | None, filename: str | None, data: bytes,
              storage: Storage) -> tuple[sch.RecordDocument, bool]:
    if not data:
        raise ValidationFailed(fields={"file": "empty"})
    if len(data) > files.MAX_UPLOAD_BYTES:
        raise ValidationFailed("Up to 10 MB.", code="attachment_too_large", fields={"file": "over 10 MB"})
    if doc_type == "other" and not (name or "").strip():
        raise ValidationFailed(fields={"name": "name the document"})
    if name is not None and ("\x00" in name or len(name.strip()) > 80):
        raise ValidationFailed(fields={"name": "1 to 80 characters"})
    sniffed = files.sniff(data[:16])
    if sniffed is None:
        raise ValidationFailed("JPEG, PNG, WebP, HEIC or PDF only.", code="attachment_type",
                               fields={"file": "not an allowed type"})
    digest = hashlib.sha256(data).hexdigest()
    # who may add comes first, a duplicate included: a viewer re-sending a file the
    # record already holds is refused, not answered 200 (code review 5)
    why = (await db.execute(text("SELECT record_document_refusal(:t, CAST(:r AS uuid))"),
                            {"t": record_type, "r": record_id})).scalar_one()
    _raise_for(why)
    existing = (await db.execute(text(
        _SELECT + "WHERE d.record_type = :t AND d.record_id = CAST(:r AS uuid) AND d.doc_type = :k "
        "AND d.sha256 = :h AND d.deleted_at IS NULL"),
        {"t": record_type, "r": record_id, "k": doc_type, "h": digest})).all()
    if existing:
        return (await _rows(db, existing))[0], False
    live = (await db.execute(text(
        "SELECT count(*) FROM record_document WHERE record_type = :t AND record_id = CAST(:r AS uuid) "
        "AND deleted_at IS NULL"), {"t": record_type, "r": record_id})).scalar_one()
    _raise_for("DOCMX" if live >= MAX_PER_RECORD else None)
    key = f"documents/{record_type}/{record_id}/{uuid.uuid4().hex}.{sniffed.extension}"
    try:
        await asyncio.to_thread(storage.put, key, data, sniffed.content_type)
    except Exception as exc:
        log.warning("document.storage_unavailable", error=type(exc).__name__)
        raise ServiceUnavailableError("Files cannot be stored right now; try again later.",
                                      code="storage_unavailable") from exc
    try:
        async with db.begin_nested():
            row = (await db.execute(text(
                "SELECT * FROM record_document_add(:t, CAST(:r AS uuid), :k, :n, :key, :fn, :ct, :sz, :h)"),
                {"t": record_type, "r": record_id, "k": doc_type, "n": name, "key": key,
                 "fn": _safe_filename(filename, sniffed.extension), "ct": sniffed.content_type,
                 "sz": len(data), "h": digest})).one()
    except DBAPIError as exc:
        _raise_for(_state(exc), exc)
        raise
    got = (await db.execute(text(_SELECT + "WHERE d.id = :i"), {"i": row.id})).all()
    return (await _rows(db, got))[0], bool(row.created)


async def on_record(db: AsyncSession, record_type: str, record_id: str) -> list[sch.RecordDocument]:
    """The documents on one record, newest first; 404 when the record is not visible."""
    why = (await db.execute(text("SELECT record_document_refusal(:t, CAST(:r AS uuid))"),
                            {"t": record_type, "r": record_id})).scalar_one()
    if why == "DOCNF":
        raise NotFoundError("No such record.")
    rows = (await db.execute(text(
        _SELECT + "WHERE d.record_type = :t AND d.record_id = CAST(:r AS uuid) AND d.deleted_at IS NULL "
        "ORDER BY d.uploaded_at DESC, d.id DESC"), {"t": record_type, "r": record_id})).all()
    return await _rows(db, rows)


# The lead and its merged losers, its quotations, the orders from them or carrying the
# lead, those orders' dispatches, and payments allocated to them: one UNION per type,
# each read under the caller's own policies (plan review R-6)
_LEAD_RECORDS = """
WITH leads AS (
    SELECT id FROM lead WHERE id = CAST(:l AS uuid)
    UNION SELECT id FROM lead WHERE merged_into_id = CAST(:l AS uuid)),
quotes AS (SELECT q.id, q.quote_no::text AS label FROM quotation q WHERE q.lead_id IN (SELECT id FROM leads)),
orders AS (
    SELECT o.id, o.order_no::text AS label FROM sales_order o WHERE o.lead_id IN (SELECT id FROM leads)
    UNION
    SELECT o.id, o.order_no::text FROM sales_order o
      JOIN order_quotation oq ON oq.sales_order_id = o.id WHERE oq.quotation_id IN (SELECT id FROM quotes))
SELECT 'lead' AS kind, l.id, l.inquiry_no::text AS label FROM lead l WHERE l.id IN (SELECT id FROM leads)
UNION ALL SELECT 'quotation', id, label FROM quotes
UNION ALL SELECT 'sales_order', id, label FROM orders
UNION ALL SELECT 'dispatch', d.id, d.dispatch_no::text FROM dispatch d WHERE d.sales_order_id IN (SELECT id FROM orders)
UNION ALL SELECT DISTINCT 'payment', p.id, NULL FROM payment p
  JOIN payment_allocation a ON a.payment_id = p.id
 WHERE a.sales_order_id IN (SELECT id FROM orders) AND NOT a.voided
"""


async def on_lead(db: AsyncSession, lead_id: str) -> list[sch.RecordDocument]:
    if not (await db.execute(text("SELECT lead_visible(CAST(:l AS uuid))"), {"l": lead_id})).scalar_one():
        raise NotFoundError("No such lead.")
    records = (await db.execute(text(_LEAD_RECORDS), {"l": lead_id})).all()
    labels = {(r.kind, str(r.id)): r.label for r in records}
    if not records:
        return []
    rows = (await db.execute(text(
        _SELECT + "WHERE (d.record_type, d.record_id) IN (SELECT x.t, x.id FROM unnest(CAST(:ts AS text[]), "
        "CAST(:ids AS uuid[])) AS x(t, id)) AND d.deleted_at IS NULL ORDER BY d.uploaded_at DESC, d.id DESC"),
        {"ts": [r.kind for r in records], "ids": [str(r.id) for r in records]})).all()
    return await _rows(db, rows, labels)


async def link(db: AsyncSession, document_id: str, storage: Storage) -> sch.RecordDocumentLink:
    r = (await db.execute(text(
        "SELECT storage_key, filename, content_type FROM record_document WHERE id = CAST(:i AS uuid) "
        "AND deleted_at IS NULL"), {"i": document_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such document.")
    try:
        url, expires = storage.presign_get(
            r.storage_key, filename=_download_name(r.filename, r.content_type),
            disposition="attachment" if r.content_type == "image/heic" else "inline")
    except RuntimeError as exc:
        raise ServiceUnavailableError("Files cannot be opened right now.",
                                      code="storage_unavailable") from exc
    return sch.RecordDocumentLink(url=url, expires_at=expires.isoformat(), filename=r.filename,
                                  content_type=r.content_type)


async def remove(db: AsyncSession, caller: Caller, document_id: str) -> None:
    try:
        async with db.begin_nested():
            await db.execute(text("SELECT record_document_remove(CAST(:i AS uuid))"), {"i": document_id})
    except DBAPIError as exc:
        code = _state(exc)
        if code == "DOCNF":
            raise NotFoundError("No such document.") from exc
        if code == "DOCFB":
            raise ForbiddenError("Only whoever added it, or a staff editor, removes it.") from exc
        raise
