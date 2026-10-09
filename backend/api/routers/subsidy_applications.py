"""/subsidy-applications, /subsidy-stages and /subsidy-document-types (FS-009)."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.config import get_settings
from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.domain import complaints as upload_rules
from api.idempotency import payload_digest, run_idempotent
from api.routers.exporting import XLSX_RESPONSE, export, filters_of
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.subsidy_applications import (
    Application,
    ApplicationCreate,
    ApplicationPage,
    Cancel,
    ChecklistItem,
    Document,
    DocumentLink,
    DocumentType,
    Entry,
    StageDef,
    StageRecord,
)
from api.services import exports
from api.services import subsidy_applications as service
from api.storage import get_storage
from api.upload_limit import BodyTooLarge

router = APIRouter(prefix="/subsidy-applications", tags=["subsidy applications"])
lookups = APIRouter(tags=["subsidy applications"])

Id = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse,
          "description": "`idempotency_key_required`: a write sent without an Idempotency-Key."},
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "No subsidy permission: every dealer, and staff "
                                                 "without the module."},
    404: {"model": ErrorResponse, "description": "Not an application (or a lead) in your scope."},
    422: {"model": ErrorResponse, "description": "A field needs correcting; see `fields`."},
}
_REUSED = "`idempotency_key_reused`: the same key was sent with a different body."
_CREATE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    409: {"model": ErrorResponse, "description": (
        "`scheme_changed`: a scheme for the lead's state was added or switched meanwhile; "
        "calculate again. " + _REUSED)},
    422: {"model": ErrorResponse, "description": (
        "A field needs correcting; see `fields`. `calculation.scheme`: not the lead's scheme "
        "(GET /subsidy-schemes/for-lead/{id}). `no_scheme_for_state`: the lead's state has none.")},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    409: {"model": ErrorResponse, "description": "`status_changed`: the application is closed "
                                                 "or cancelled. " + _REUSED},
}
_NO_STORAGE: dict[int | str, dict[str, object]] = {
    503: {"model": ErrorResponse, "description": "`storage_unavailable`: retry later."}}


async def _idem(db: DbSession, claims: Claims, idem: IdemKey, route: str, body: BaseModel,
                work: Callable[[], Awaitable[tuple[int, Any]]]) -> JSONResponse:
    async def run() -> tuple[int, dict[str, Any]]:
        code, out = await work()
        return code, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=route,
        payload_hash=payload_digest(body.model_dump(mode="json")), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@lookups.get("/subsidy-stages", response_model=Envelope[list[StageDef]], responses=_ERRORS,
             dependencies=[Depends(require("subsidy", "view"))])
async def stages(db: DbSession, scheme: Annotated[str, Query(max_length=30)] = "GGRC",
                 ) -> Envelope[list[StageDef]]:
    """The stages of a scheme in order, each with the fields its form asks for.
    Build "Record stage" from this; the stages are data, not code."""
    return Envelope(data=await service.stage_defs(db, scheme))


@lookups.get("/subsidy-document-types", response_model=Envelope[list[DocumentType]],
             responses=_ERRORS, dependencies=[Depends(require("subsidy", "view"))])
async def document_types(db: DbSession) -> Envelope[list[DocumentType]]:
    """The document checklist: the enclosures GGRC asks for. None is required yet."""
    return Envelope(data=await service.document_types(db))


@router.post("", response_model=Envelope[Application], status_code=201, responses=_CREATE_ERRORS,
             dependencies=[Depends(require("subsidy", "create"))])
async def create(body: ApplicationCreate, db: DbSession, caller: CallerDep, claims: Claims,
                 idem: IdemKey) -> JSONResponse:
    """Forward a subsidised lead into an application. Send the calculator's request
    and the farmer's category; the backend runs the calculation again, stores it with
    the category's subsidy and farmer share, and moves the lead to won. `422` on
    `lead_id` (`lead_not_subsidised`, `lead_not_forwardable`,
    `lead_system_not_subsidised`, `already_forwarded`), on `category_code`, or under
    `calculation.` for the calculation's own fields."""
    async def work() -> tuple[int, Any]:
        return 201, await service.create(db, caller, body)
    return await _idem(db, claims, idem, "POST /api/v1/subsidy-applications", body, work)


@router.get("", response_model=ApplicationPage, responses=_ERRORS,
            dependencies=[Depends(require("subsidy", "view"))])
async def list_applications(
        db: DbSession,
        status: Annotated[Literal["open", "full_fp_received", "cancelled"] | None, Query()] = None,
        stage: Annotated[str | None, Query(max_length=60, description="A stage code.")] = None,
        q: Annotated[str | None, Query(max_length=100, description="Application number, "
                                       "registration number or farmer's name.")] = None,
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50) -> ApplicationPage:
    """The worklist, newest first, in your scope."""
    return await service.list_applications(db, status=status, stage=stage, q=q, cursor=cursor,
                                           limit=limit)


@router.get("/export", response_class=Response, responses={**_ERRORS, **XLSX_RESPONSE},
            dependencies=[Depends(require("subsidy", "view"))])
async def export_applications(
    db: DbSession, caller: CallerDep,
    filters: Annotated[dict[str, Any], Depends(filters_of(list_applications))],
) -> Response:
    """Download the subsidy application list as an Excel file, with the same filters as the list.

    The file holds exactly the rows the list would show for these filters, across
    every page, and nothing outside your scope. Call it with `fetch` and the bearer
    token, then save the blob. More than 5,000 rows is `422 export_too_large`:
    narrow the filters. An empty list gives a file with the header row only.
    """
    return await export(list_applications, stem="subsidy-applications",
                        title="Subsidy applications", columns=exports.SUBSIDY_APPLICATIONS,
                        user_id=caller.user_id, filters=filters, db=db, caller=caller)


@router.get("/{app_id}", response_model=Envelope[Application], responses=_ERRORS,
            dependencies=[Depends(require("subsidy", "view"))])
async def get_application(app_id: Id, db: DbSession) -> Envelope[Application]:
    """The application, with its current stage, figures, document count and ageing."""
    return Envelope(data=await service.get(db, app_id))


@router.get("/{app_id}/calculation", response_model=Envelope[dict[str, Any]],
            responses=_ERRORS,
            dependencies=[Depends(require("subsidy", "view"))])
async def get_calculation(app_id: Id, db: DbSession) -> Envelope[dict[str, Any]]:
    """The FS-008 calculation as it was at create: the same shape as
    POST /subsidy/calculate answers. Never recomputed."""
    return Envelope(data=await service.calculation(db, app_id))


@router.get("/{app_id}/stages", response_model=Envelope[list[Entry]], responses=_ERRORS,
            dependencies=[Depends(require("subsidy", "view"))])
async def list_stages(app_id: Id, db: DbSession) -> Envelope[list[Entry]]:
    """The stage history, oldest first, with each entry's values."""
    return Envelope(data=await service.entries(db, app_id))


@router.post("/{app_id}/stages", response_model=Envelope[Application], status_code=201,
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("subsidy", "edit"))])
async def record_stage(app_id: Id, body: StageRecord, db: DbSession, claims: Claims,
                       idem: IdemKey) -> JSONResponse:
    """Record a stage with its business date and values. Any stage, forwards or
    back; a backward or same-stage entry needs a `remark`. The application closes
    itself once every stage-16 amount has its stage-17 received date. `422` on
    `values.<key>`, `occurred_on`, `stage_code` or `remark`."""
    async def work() -> tuple[int, Any]:
        return 201, await service.record(db, app_id, body)
    return await _idem(db, claims, idem,
                       f"POST /api/v1/subsidy-applications/{app_id}/stages", body, work)


@router.post("/{app_id}/cancel", response_model=Envelope[Application],
             responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("subsidy", "edit"))])
async def cancel(app_id: Id, body: Cancel, db: DbSession, claims: Claims,
                 idem: IdemKey) -> JSONResponse:
    """Withdraw the application, with a reason. The lead can be forwarded again."""
    async def work() -> tuple[int, Any]:
        return 200, await service.cancel(db, app_id, body)
    return await _idem(db, claims, idem,
                       f"POST /api/v1/subsidy-applications/{app_id}/cancel", body, work)


@router.get("/{app_id}/documents", response_model=Envelope[list[ChecklistItem]],
            responses=_ERRORS,
            dependencies=[Depends(require("subsidy", "view"))])
async def checklist(app_id: Id, db: DbSession) -> Envelope[list[ChecklistItem]]:
    """The checklist with the files uploaded against each item."""
    return Envelope(data=await service.checklist(db, app_id))


@router.post("/{app_id}/documents", status_code=201, response_model=Envelope[Document],
             responses={**_MUTATION_ERRORS, **_NO_STORAGE,
                        403: {"model": ErrorResponse,
                              "description": "View only: adding a document needs subsidy "
                                             "create or edit. Hide the upload control."},
                        413: {"model": ErrorResponse, "description": "Over 10 MB."}},
             dependencies=[Depends(require("subsidy", "view"))])
async def add_document(app_id: Id, db: DbSession, caller: CallerDep, claims: Claims,
                       idem: IdemKey,
                       file: Annotated[UploadFile, File()],
                       document_type: Annotated[str, Form(max_length=60)]) -> Response:
    """Upload a document against a checklist item: PDF, JPEG, PNG, WebP or HEIC, up
    to 10 MB, judged by content. The same file again answers `200` with the one
    already there. Refusals:

    - `422 too_many_documents`: the application has 40 files already;
    - `422 attachment_type`: not one of the allowed types, on `file`;
    - `422` on `file` "empty", or on `document_type` "not on the checklist";
    - `403`: the caller may view applications but not add to them;
    - `409 status_changed`: the application is cancelled."""
    data = await file.read(upload_rules.MAX_UPLOAD_BYTES + 1)
    if len(data) > upload_rules.MAX_UPLOAD_BYTES:
        raise BodyTooLarge()
    digest = {"sha256": hashlib.sha256(data).hexdigest(), "type": document_type,
              "filename": file.filename or ""}
    storage = get_storage(get_settings(), bounded=True)

    async def run() -> tuple[int, dict[str, Any]]:
        doc, new = await service.add_document(db, caller, app_id, document_type=document_type,
                                              filename=file.filename, data=data, storage=storage)
        return (201 if new else 200), {"data": doc.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"POST /api/v1/subsidy-applications/{app_id}/documents",
                                   payload_hash=payload_digest(digest), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("/{app_id}/documents/{doc_id}", response_model=Envelope[DocumentLink],
            responses={**_ERRORS, **_NO_STORAGE},
            dependencies=[Depends(require("subsidy", "view"))])
async def document_link(app_id: Id, doc_id: Id, db: DbSession) -> Envelope[DocumentLink]:
    """A ten-minute link to the file. Never fetch it with the bearer token.
    `503 storage_unavailable` while file storage is not configured."""
    return Envelope(data=await service.document_link(db, app_id, doc_id,
                                                     get_storage(get_settings())))


@router.get("/{app_id}/pims.xlsx", responses={**_ERRORS, 200: {
    "content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}},
    "description": "The PIMS sheet."}}, dependencies=[Depends(require("subsidy", "view"))])
async def pims(app_id: Id, db: DbSession) -> Response:
    """The PIMS sheet for the GGRC portal: one row per line of the stored
    calculation, in the columns CostType, Crop, ItemCode, Item, Size, Unit, Rate,
    Quantity, Amount, Remark. Our reading of the one sample the client gave (GAP-177).
    GGRC applications only: another scheme's is 422 `pims_not_for_scheme` (GAP-363)."""
    rows = await service.pims_rows(db, app_id)
    data = await asyncio.to_thread(service.pims_workbook, rows)
    return Response(content=data,
                    headers={"Content-Disposition": f'attachment; filename="pims-{app_id}.xlsx"'},
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
