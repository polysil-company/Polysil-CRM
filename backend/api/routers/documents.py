# ruff: noqa: E501  (embedded SQL and field declarations)

"""/documents and /leads/{id}/documents (FS-050): named files on records."""

from __future__ import annotations

import hashlib
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.deps import CallerDep, Claims, DbSession, IdemKey
from api.domain import complaints as files
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.documents import (
    DocType,
    RecordDocument,
    RecordDocumentLink,
    RecordDocumentType,
    RecordType,
)
from api.schemas.leads import UUID_RE
from api.services import documents as service
from api.storage import get_storage
from api.upload_limit import BodyTooLarge

router = APIRouter(prefix="/documents", tags=["documents"])
leads = APIRouter(prefix="/leads", tags=["documents"])

Id = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "`idempotency_key_required` on a write."},
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "You can see the record but may not add to it, "
                                                 "or may not remove that document."},
    404: {"model": ErrorResponse, "description": "No such record or document, or not visible to you."},
    409: {"model": ErrorResponse, "description": "`record_closed`: a deleted or merged lead, or a "
                                                 "voided dispatch."},
    413: {"model": ErrorResponse, "description": "Over 10 MB."},
    422: {"model": ErrorResponse, "description": "`too_many_documents` (50), `attachment_type`, or a "
                                                 "field; see `fields`."},
    503: {"model": ErrorResponse, "description": "`storage_unavailable`: retry later."},
}


@router.get("/types", response_model=Envelope[list[RecordDocumentType]], responses=_ERRORS)
async def document_types(
    caller: CallerDep,
    record_type: Annotated[RecordType | None, Query(
        description="FS-070: only the types this kind of record takes. A dealer application "
        "takes its five shop and tax documents and `other`; every other record the ten "
        "general types. Omitted: every type.")] = None,
) -> Envelope[list[RecordDocumentType]]:
    """The document types and their labels, for the type picker. `other` needs a name.

    Send the record's `record_type` so the picker offers only what belongs on it."""
    return Envelope(data=service.types(record_type))


@router.post("", status_code=201, response_model=Envelope[RecordDocument], responses=_ERRORS)
async def add_document(db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
                       record_type: Annotated[RecordType, Form()],
                       record_id: Annotated[str, Form(pattern=UUID_RE)],
                       doc_type: Annotated[DocType, Form()],
                       file: Annotated[UploadFile, File()],
                       name: Annotated[str | None, Form(max_length=80)] = None) -> Response:
    """Attach a file to a lead, quotation, sales order, dispatch or payment: JPEG,
    PNG, WebP, HEIC or PDF, up to 10 MB, judged by its content. `name` is required
    for `other`. The same file with the same type on the same record answers `200`
    with the one already there. Who may add depends on the record (FS-050)."""
    data = await file.read(files.MAX_UPLOAD_BYTES + 1)
    if len(data) > files.MAX_UPLOAD_BYTES:
        raise BodyTooLarge()
    digest = {"sha256": hashlib.sha256(data).hexdigest(), "record_type": record_type,
              "record_id": record_id, "doc_type": doc_type, "name": name or ""}
    storage = get_storage(get_settings(), bounded=True)

    async def run() -> tuple[int, dict[str, Any]]:
        doc, new = await service.add(db, caller, record_type=record_type, record_id=record_id,
                                     doc_type=doc_type, name=name, filename=file.filename,
                                     data=data, storage=storage)
        return (201 if new else 200), {"data": doc.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route="POST /api/v1/documents",
                                   payload_hash=payload_digest(digest), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("", response_model=Envelope[list[RecordDocument]], responses=_ERRORS)
async def list_documents(db: DbSession, caller: CallerDep,
                         record_type: Annotated[RecordType, Query()],
                         record_id: Annotated[str, Query(pattern=UUID_RE)]) -> Envelope[list[RecordDocument]]:
    """The documents on one record, newest first."""
    return Envelope(data=await service.on_record(db, record_type, record_id))


@router.get("/{document_id}/link", response_model=Envelope[RecordDocumentLink], responses=_ERRORS)
async def document_link(document_id: Id, db: DbSession, caller: CallerDep) -> Envelope[RecordDocumentLink]:
    """A ten-minute link to the file. Use it as an image source or a download."""
    return Envelope(data=await service.link(db, document_id, get_storage(get_settings())))


@router.delete("/{document_id}", status_code=204, responses=_ERRORS)
async def remove_document(document_id: Id, db: DbSession, caller: CallerDep, claims: Claims,
                          idem: IdemKey) -> Response:
    """Remove a document: whoever added it, or a staff member who may add to the
    record. It stays on record, hidden from lists."""
    async def run() -> tuple[int, dict[str, Any]]:
        await service.remove(db, caller, document_id)
        return 204, {}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"DELETE /api/v1/documents/{document_id}",
                                   payload_hash=payload_digest({}), work=run)
    if outcome.status_code == 204:
        return Response(status_code=204)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@leads.get("/{lead_id}/documents", response_model=Envelope[list[RecordDocument]], responses=_ERRORS)
async def lead_documents(lead_id: Id, db: DbSession, caller: CallerDep) -> Envelope[list[RecordDocument]]:
    """Everything on the lead and on what was made from it: its quotations, their
    orders, those orders' dispatches and payments, and leads merged into it. Each
    row names its record (`record_label`). Only records you can see."""
    return Envelope(data=await service.on_lead(db, lead_id))
