"""/imports (FS-062): Excel import with column matching."""

from __future__ import annotations

import hashlib
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey
from api.domain import complaints as files
from api.domain.imports.template import FILE_NAMES
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.imports import (
    ImportBatch,
    ImportCheck,
    ImportCheckRequest,
    ImportCommitRequest,
    ImportCommitResult,
    ImportKind,
)
from api.schemas.leads import UUID_RE
from api.services import imports as service
from api.upload_limit import BodyTooLarge

router = APIRouter(prefix="/imports", tags=["imports"])

Id = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "`idempotency_key_required` on a write."},
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "No permission for this kind of import. Partner "
                                                 "and price imports are staff only."},
    404: {"model": ErrorResponse, "description": "No such import, one uploaded by someone else, "
                                                 "or one purged after seven days."},
    409: {"model": ErrorResponse, "description": "`import_wrong_state` (committed, discarded, not "
                                                 "checked, or a lines import at commit); "
                                                 "`price_list_published`."},
    413: {"model": ErrorResponse, "description": "`attachment_too_large`: over 10 MB."},
    422: {"model": ErrorResponse, "description": "`import_unreadable`, `import_too_many_rows`, "
                                                 "`import_has_errors`, or `validation_error` with "
                                                 "`fields.mapping.<key>`."},
}


@router.post("", status_code=201, response_model=Envelope[ImportBatch], responses=_ERRORS)
async def upload(db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
                 kind: Annotated[ImportKind, Form()],
                 file: Annotated[UploadFile, File()],
                 target_id: Annotated[str | None, Form(pattern=UUID_RE)] = None,
                 sheet: Annotated[str | None, Form(max_length=100)] = None,
                 header_row: Annotated[int | None, Form(ge=1, le=1000)] = None) -> Response:
    """Step 1: upload an `.xlsx` or `.csv` (up to 10 MB and 5,000 rows).

    The answer has the column headers, five sample rows, this kind's fields and a
    suggested match for each. Nothing is saved to partners, prices or documents
    until commit. `target_id` is the draft price list, for `price_list_items` only.
    Choose `sheet` and `header_row` when the guess is wrong: the first visible sheet
    and the first non-empty row are the defaults."""
    data = await file.read(files.MAX_UPLOAD_BYTES + 1)
    if len(data) > files.MAX_UPLOAD_BYTES:
        raise BodyTooLarge()
    sha = hashlib.sha256(data).hexdigest()
    digest = {"sha256": sha, "kind": kind, "target_id": target_id or "", "sheet": sheet or "",
              "header_row": header_row or 0}

    async def run() -> tuple[int, dict[str, Any]]:
        batch = await service.upload(db, caller, kind=kind, target_id=target_id,
                                     file_name=file.filename or "upload", data=data, sha256=sha,
                                     sheet=sheet, header_row=header_row)
        return 201, {"data": batch.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route="POST /api/v1/imports",
                                   payload_hash=payload_digest(digest), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# Declared above /{batch_id}: its UUID pattern validates, it does not route, so
# "template" would reach get_import and fail there (FS-068 EC-2).
@router.get("/template", responses={
    200: {"content": {XLSX: {}}, "description": "The blank `.xlsx`."},
    401: _ERRORS[401],
    403: {"model": ErrorResponse, "description": "No permission to upload this kind of import."},
    422: {"model": ErrorResponse, "description": "`validation_error`: `kind` missing or unknown."}})
async def download_template(kind: Annotated[ImportKind, Query()], db: DbSession,
                            caller: CallerDep) -> Response:
    """A blank file to fill for this import, for the "Download template" link on the
    upload screen. Sheet 1 has our column names in row 1 and no rows. Sheet 2, "How
    to fill", says what goes in each column, with an example. A filled sheet 1
    uploads with every column matched by name.

    The same permission as upload. Fetch it with the bearer token as a blob, and
    save it as `partner-import-template.xlsx`, `price-list-template.xlsx` or
    `order-lines-template.xlsx`: `Content-Disposition` is not readable from another
    origin."""
    data = await service.template(db, caller, kind)
    return Response(content=data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{FILE_NAMES[kind]}"'})


@router.get("/{batch_id}", response_model=Envelope[ImportBatch], responses=_ERRORS)
async def get_import(batch_id: Id, db: DbSession, caller: CallerDep) -> Envelope[ImportBatch]:
    """An import you uploaded: the same body as the upload, plus the last `mapping`
    and `check`. Batches are purged seven days after upload."""
    return Envelope(data=await service.get(db, batch_id))


@router.post("/{batch_id}/check", response_model=Envelope[ImportCheck], responses=_ERRORS)
async def check_import(batch_id: Id, body: ImportCheckRequest, db: DbSession, caller: CallerDep,
                       claims: Claims, idem: IdemKey) -> Response:
    """Step 2: check every row against a mapping (field key to column index).

    Returns the counts, every bad row with its reasons (at most 500), the first 20
    good rows as they will be saved, and warnings about whole columns. For `lines`,
    `lines` holds every good row for the line editor. Run it again with a new
    mapping as often as needed. Saves the mapping, so the next upload of this kind
    suggests it."""

    async def run() -> tuple[int, dict[str, Any]]:
        result = await service.check(db, caller, batch_id, body)
        return 200, {"data": result.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"POST /api/v1/imports/{batch_id}/check",
                                   payload_hash=payload_digest(body.model_dump(mode="json")),
                                   work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("/{batch_id}/commit", response_model=Envelope[ImportCommitResult],
             responses=_ERRORS)
async def commit_import(batch_id: Id, body: ImportCommitRequest, db: DbSession,
                        caller: CallerDep, claims: Claims, idem: IdemKey) -> Response:
    """Step 3: save a checked partner or price import. Every row is checked again
    first, because masters may have changed. All or nothing: with any bad row and
    `skip_invalid` false, nothing is saved (`import_has_errors`, the rows in
    `fields` as `rows[<sheet row>].<field>`). A partner import never creates a
    login. A `lines` import has no commit: the form saves the lines."""

    async def run() -> tuple[int, dict[str, Any]]:
        result = await service.commit(db, caller, batch_id, body)
        return 200, {"data": result.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"POST /api/v1/imports/{batch_id}/commit",
                                   payload_hash=payload_digest(body.model_dump(mode="json")),
                                   work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.delete("/{batch_id}", status_code=204, responses=_ERRORS)
async def discard_import(batch_id: Id, db: DbSession, caller: CallerDep, claims: Claims,
                         idem: IdemKey) -> Response:
    """Discard an uncommitted import. Its rows are removed at once."""

    async def run() -> tuple[int, dict[str, Any]]:
        await service.discard(db, batch_id)
        return 204, {}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"DELETE /api/v1/imports/{batch_id}",
                                   payload_hash=payload_digest({}), work=run)
    if outcome.status_code == 204:
        return Response(status_code=204)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
