"""/complaints and /complaint-sla-policies (FS-015): a complaint from entry to the
quality verdict. Replacement orders and refunds are FS-015b."""

# ruff: noqa: E501  (route signatures and their descriptions)

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, RootModel

from api.config import get_settings
from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.domain import complaints as domain
from api.idempotency import payload_digest, run_idempotent
from api.routers.exporting import XLSX_RESPONSE, export, filters_of
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.complaints import (
    Assignee,
    AttachmentLink,
    CancelIn,
    CheckIn,
    Complaint,
    ComplaintCreate,
    ComplaintPage,
    ComplaintPatch,
    Kind,
    LinesReplace,
    QcIn,
    RemedyIn,
    ReopenIn,
    Severity,
    SlaPolicy,
    SlaPolicyIn,
    Stats,
    Status,
    WithdrawIn,
)
from api.schemas.leads import UUID_RE, TimelinePage
from api.services import complaints as service
from api.services import exports
from api.storage import get_storage
from api.upload_limit import BodyTooLarge

router = APIRouter(prefix="/complaints", tags=["complaints"])
policies = APIRouter(prefix="/complaint-sla-policies", tags=["complaints"])

Id = Annotated[str, Path(pattern=UUID_RE)]
Cursor = Annotated[str | None, Query(description="From the previous page's next_cursor.")]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not yours to do."},
    404: {"model": ErrorResponse, "description": "Not in your scope."},
    422: {"model": ErrorResponse, "description": "A rule refused it; see `code` and `fields`."},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    409: {"model": ErrorResponse, "description": "`status_changed`: someone acted first, reload. "
                                               "`complaint_not_draft`: it was submitted."},
}


async def _idem(db: Any, claims: Any, idem: str, route: str, body: BaseModel | dict[str, Any] | None,
                work: Callable[[], Awaitable[Any]], code: int = 200) -> Response:
    async def run() -> tuple[int, dict[str, Any]]:
        out = await work()
        return code, {"data": out.model_dump(mode="json")}
    payload = (body.model_dump(mode="json", exclude_unset=True) if isinstance(body, BaseModel)
               else body or {})
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=payload_digest(payload), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


# ── the complaint ────────────────────────────────────────────────────────────

@router.post("", status_code=201, response_model=Envelope[Complaint], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("complaints", "create"))])
async def create_complaint(body: ComplaintCreate, db: DbSession, caller: CallerDep, claims: Claims,
                           idem: IdemKey) -> Response:
    """Record a complaint as a draft: the type, the contact, where the material is
    installed, and the products with their supplied and defective quantities. A
    dealer's complaint is always their own. Linking an order fills the challan and
    supply date from its latest dispatch. `422 territory_without_state_code`: the
    territory cannot be numbered yet."""
    return await _idem(db, claims, idem, "POST /api/v1/complaints", body,
                       lambda: service.create_complaint(db, caller, body), 201)


@router.get("", response_model=ComplaintPage, responses=_ERRORS,
            dependencies=[Depends(require("complaints", "view"))])
async def list_complaints(
    db: DbSession, caller: CallerDep,
    status_: Annotated[list[Status] | None, Query(alias="status", description="Repeatable.")] = None,
    complaint_type_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    severity: Severity | None = None,
    partner_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    lead_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    sales_order_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    owner: Annotated[str | None, Query(pattern="^none$", description="`none`: no owner yet.")] = None,
    breached: bool = False,
    awaiting: Annotated[str | None, Query(pattern="^me$", description="`me`: waiting for my check "
                                                                     "or my QC verdict, oldest first; "
                                                                     "one page.")] = None,
    q: Annotated[str | None, Query(max_length=60, description="Number, contact name or mobile.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Cursor = None,
) -> ComplaintPage:
    """Complaints in your scope, newest first. A lead's or an order's: `?lead_id=`,
    `?sales_order_id=`."""
    return await service.list_complaints(
        db, caller, status=list(status_) if status_ else None, complaint_type_id=complaint_type_id,
        severity=severity, partner_id=partner_id, lead_id=lead_id, sales_order_id=sales_order_id,
        owner=owner, breached=breached, awaiting=awaiting, q=q, limit=limit, cursor=cursor)


@router.get("/stats", response_model=Envelope[Stats], responses=_ERRORS,
            dependencies=[Depends(require("complaints", "view"))])
async def complaint_stats(db: DbSession) -> Envelope[Stats]:
    """Counts by status, breached and no-target counts, and whether files can be
    stored now (`storage_available`; hide the upload button when false)."""
    return Envelope(data=await service.stats(db, get_storage(get_settings())))


@router.get("/export", response_class=Response, responses={**_ERRORS, **XLSX_RESPONSE},
            dependencies=[Depends(require("complaints", "view"))])
async def export_complaints(
    db: DbSession, caller: CallerDep,
    filters: Annotated[dict[str, Any], Depends(filters_of(list_complaints))],
) -> Response:
    """Download the complaint list as an Excel file, with the same filters as the list.

    The file holds exactly the rows the list would show for these filters, across
    every page, and nothing outside your scope. Call it with `fetch` and the bearer
    token, then save the blob. More than 5,000 rows is `422 export_too_large`:
    narrow the filters. An empty list gives a file with the header row only.
    """
    if filters.get("awaiting"):
        # the queue is one page with no cursor: draining it would stop at 100 (FS-030 rule 10)
        raise exports.FilterNotExportableError(
            "The approval queue cannot be exported. Remove the awaiting filter.")
    return await export(list_complaints, stem="complaints", title="Complaints", columns=exports.COMPLAINTS,
                        user_id=caller.user_id, filters=filters, db=db, caller=caller)


@router.get("/{complaint_id}", response_model=Envelope[Complaint], responses=_ERRORS,
            dependencies=[Depends(require("complaints", "view"))])
async def get_complaint(complaint_id: Id, db: DbSession, caller: CallerDep) -> Envelope[Complaint]:
    """One complaint. Show only the buttons in `can`."""
    return Envelope(data=await service.get_complaint(db, caller, complaint_id))


@router.patch("/{complaint_id}", response_model=Envelope[Complaint], responses=_MUTATION_ERRORS,
              dependencies=[Depends(require("complaints", "edit"))])
async def patch_complaint(complaint_id: Id, body: ComplaintPatch, db: DbSession, caller: CallerDep,
                          claims: Claims, idem: IdemKey) -> Response:
    """Change a draft's header. `409 complaint_not_draft` once it is submitted."""
    return await _idem(db, claims, idem, f"PATCH /api/v1/complaints/{complaint_id}", body,
                       lambda: service.patch_complaint(db, caller, complaint_id, body))


@router.put("/{complaint_id}/lines", response_model=Envelope[Complaint], responses=_MUTATION_ERRORS,
            dependencies=[Depends(require("complaints", "edit"))])
async def replace_lines(complaint_id: Id, body: LinesReplace, db: DbSession, caller: CallerDep,
                        claims: Claims, idem: IdemKey) -> Response:
    """Replace a draft's products, 1 to 20, each once."""
    return await _idem(db, claims, idem, f"PUT /api/v1/complaints/{complaint_id}/lines", body,
                       lambda: service.replace_lines(db, caller, complaint_id, body))


@router.delete("/{complaint_id}", status_code=204, responses=_MUTATION_ERRORS,
               dependencies=[Depends(require("complaints", "delete"))])
async def delete_complaint(complaint_id: Id, db: DbSession, caller: CallerDep, claims: Claims,
                           idem: IdemKey) -> Response:
    """Delete a draft that was never submitted. A submitted one is cancelled."""
    async def run() -> tuple[int, dict[str, Any]]:
        await service.delete_complaint(db, caller, complaint_id)
        return 204, {}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"DELETE /api/v1/complaints/{complaint_id}",
                                   payload_hash=payload_digest({}), work=run)
    if outcome.status_code == 204:
        return Response(status_code=204)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


# ── the transitions ──────────────────────────────────────────────────────────

@router.post("/{complaint_id}/submit", response_model=Envelope[Complaint], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("complaints", "view"))])
async def submit(complaint_id: Id, db: DbSession, caller: CallerDep, claims: Claims,
                 idem: IdemKey) -> Response:
    """Send the draft for the manager's check. The first submit gives it its number
    and its targets. `422 missing_for_submit` (the challan number or supply date),
    `422 nothing_defective`, `422 no_checker` (nobody may check it: ask the admin)."""
    return await _idem(db, claims, idem, f"POST /api/v1/complaints/{complaint_id}/submit", None,
                       lambda: service.submit(db, caller, complaint_id))


@router.post("/{complaint_id}/check", response_model=Envelope[Complaint], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("complaints", "approve"))])
async def check(complaint_id: Id, body: CheckIn, db: DbSession, caller: CallerDep, claims: Claims,
                idem: IdemKey) -> Response:
    """The manager's check: `approve` sends it to QC, `return` sends it back to the
    raiser with the remark. With approve, optionally a new severity and an owner from
    `GET /complaints/{id}/assignees`."""
    return await _idem(db, claims, idem, f"POST /api/v1/complaints/{complaint_id}/check", body,
                       lambda: service.check(db, caller, complaint_id, body))


@router.post("/{complaint_id}/qc", response_model=Envelope[Complaint], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("complaints", "approve"))])
async def quality(complaint_id: Id, body: QcIn, db: DbSession, caller: CallerDep, claims: Claims,
                  idem: IdemKey) -> Response:
    """QC's verdict with its dates. Dates cannot be after today, nor before the
    supply date; tested not before received."""
    return await _idem(db, claims, idem, f"POST /api/v1/complaints/{complaint_id}/qc", body,
                       lambda: service.qc(db, caller, complaint_id, body))


@router.post("/{complaint_id}/remedy", response_model=Envelope[Complaint], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("complaints", "approve"))])
async def choose_remedy(complaint_id: Id, body: RemedyIn, db: DbSession, caller: CallerDep,
                        claims: Claims, idem: IdemKey) -> Response:
    """Settle a `qc_approved` complaint. `refund`: an amount and a payee, approved by
    the managers by amount, then paid by the Account Manager. `replacement`: a free
    order of the defective lines, approved by the Dispatch Manager. `none`: close
    it now. Answers the complaint, `remedy_pending` or `closed`. Refusals:

    - `409 status_changed`: not `qc_approved`;
    - `403`: only QC chooses, and never the complaint's raiser or owner;
    - `422` on `amount`, `payee_name`, `paid_through_partner_id` or `remark`;
    - `422 nothing_defective`: a replacement with no defective quantity;
    - `422 replacement_unpriced`: a defective product has no price today, or its
      quantity breaks its unit; `fields` names the line;
    - `422 no_approver`: a role the approval needs has nobody active."""
    return await _idem(db, claims, idem, f"POST /api/v1/complaints/{complaint_id}/remedy", body,
                       lambda: service.choose_remedy(db, caller, complaint_id, body))


@router.post("/{complaint_id}/remedy/withdraw", response_model=Envelope[Complaint],
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("complaints", "approve"))])
async def withdraw_remedy(complaint_id: Id, body: WithdrawIn, db: DbSession, caller: CallerDep,
                          claims: Claims, idem: IdemKey) -> Response:
    """QC takes back the pending remedy: a refund while its approval is open, a
    replacement while nothing has shipped (its order is cancelled). The complaint
    returns to `qc_approved`. Refusals: `409 status_changed` once it moved on (decided,
    shipped, or withdrawn already); `403` for anyone but QC, and for the complaint's
    raiser or owner; `422` on `remark`."""
    return await _idem(db, claims, idem, f"POST /api/v1/complaints/{complaint_id}/remedy/withdraw",
                       body, lambda: service.withdraw_remedy(db, caller, complaint_id, body))


@router.post("/{complaint_id}/cancel", response_model=Envelope[Complaint], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("complaints", "view"))])
async def cancel(complaint_id: Id, body: CancelIn, db: DbSession, caller: CallerDep, claims: Claims,
                 idem: IdemKey) -> Response:
    """Cancel a draft or a submitted complaint, with a reason. The raiser, the owner,
    or someone who may delete complaints."""
    return await _idem(db, claims, idem, f"POST /api/v1/complaints/{complaint_id}/cancel", body,
                       lambda: service.cancel(db, caller, complaint_id, body))


@router.post("/{complaint_id}/reopen", response_model=Envelope[Complaint], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("complaints", "view"))])
async def reopen(complaint_id: Id, body: ReopenIn, db: DbSession, caller: CallerDep, claims: Claims,
                 idem: IdemKey) -> Response:
    """Reopen a closed or QC-rejected complaint, with a reason. It goes through the
    check, QC and a remedy again. The raiser may reopen a closed one; others need a
    role in the `complaint_reopen_roles` setting, and a rejection only those roles.
    `422 reopen_window_closed` after `complaint_reopen_days` or `complaint_reopen_max`.
    `can.reopen` on the detail says whether the button applies."""
    return await _idem(db, claims, idem, f"POST /api/v1/complaints/{complaint_id}/reopen", body,
                       lambda: service.reopen(db, caller, complaint_id, body))


@router.get("/{complaint_id}/assignees", response_model=Envelope[list[Assignee]], responses=_ERRORS,
            dependencies=[Depends(require("complaints", "approve"))])
async def assignees(complaint_id: Id, db: DbSession) -> Envelope[list[Assignee]]:
    """The owner picker in the check dialog. `403` unless you may check it."""
    return Envelope(data=await service.assignees(db, complaint_id))


@router.get("/{complaint_id}/timeline", response_model=TimelinePage, responses=_ERRORS,
            dependencies=[Depends(require("complaints", "view"))])
async def timeline(complaint_id: Id, db: DbSession, caller: CallerDep,
                   limit: Annotated[int, Query(ge=1, le=100)] = 100,
                   cursor: Cursor = None) -> TimelinePage:
    """The complaint's events, newest first. A dealer never sees who decided."""
    return await service.timeline(db, caller, complaint_id, limit=limit, cursor=cursor)


# ── attachments (ADR-041) ────────────────────────────────────────────────────

@router.post("/{complaint_id}/attachments", status_code=201, response_model=Envelope[Any],
             responses={**_MUTATION_ERRORS,
                        413: {"model": ErrorResponse, "description": "Over 10 MB."},
                        503: {"model": ErrorResponse, "description": "`storage_unavailable`: retry later."}},
             dependencies=[Depends(require("complaints", "view"))])
async def add_attachment(complaint_id: Id, db: DbSession, caller: CallerDep, claims: Claims,
                         idem: IdemKey, file: Annotated[UploadFile, File()],
                         kind: Annotated[Kind, Form()] = "photo") -> Response:
    """Add a photo or a document: JPEG, PNG, WebP, HEIC or PDF, up to 10 MB, judged
    by the file's content. Up to 10 per complaint. The same file again answers `200`
    with the one already there. HEIC is stored but cannot be previewed."""
    data = await file.read(domain.MAX_UPLOAD_BYTES + 1)
    if len(data) > domain.MAX_UPLOAD_BYTES:
        # the same 413 as the middleware's, for a file just past 10 MB whose body was
        # under the framing allowance (code review F-7)
        raise BodyTooLarge()
    digest = {"sha256": hashlib.sha256(data).hexdigest(), "kind": kind, "filename": file.filename or ""}
    storage = get_storage(get_settings(), bounded=True)

    async def run() -> tuple[int, dict[str, Any]]:
        attachment, new = await service.add_attachment(db, caller, complaint_id, kind=kind,
                                                       filename=file.filename, data=data, storage=storage)
        return (201 if new else 200), {"data": attachment.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"POST /api/v1/complaints/{complaint_id}/attachments",
                                   payload_hash=payload_digest(digest), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("/{complaint_id}/attachments/{attachment_id}", response_model=Envelope[AttachmentLink],
            responses=_ERRORS, dependencies=[Depends(require("complaints", "view"))])
async def attachment_link(complaint_id: Id, attachment_id: Id, db: DbSession) -> Envelope[AttachmentLink]:
    """A ten-minute link to the file. Use it as an image source or a download; never
    fetch it with the bearer token."""
    return Envelope(data=await service.attachment_link(db, complaint_id, attachment_id,
                                                       get_storage(get_settings())))


@router.delete("/{complaint_id}/attachments/{attachment_id}", status_code=204,
               responses=_MUTATION_ERRORS, dependencies=[Depends(require("complaints", "view"))])
async def remove_attachment(complaint_id: Id, attachment_id: Id, db: DbSession, caller: CallerDep,
                            claims: Claims, idem: IdemKey) -> Response:
    """Remove a file. In a draft: whoever added it or an editor. After submit: only
    whoever added it."""
    async def run() -> tuple[int, dict[str, Any]]:
        await service.remove_attachment(db, caller, complaint_id, attachment_id)
        return 204, {}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub,
        route=f"DELETE /api/v1/complaints/{complaint_id}/attachments/{attachment_id}",
        payload_hash=payload_digest({}), work=run)
    if outcome.status_code == 204:
        return Response(status_code=204)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


# ── the targets ──────────────────────────────────────────────────────────────

@policies.get("", response_model=Envelope[list[SlaPolicy]], responses=_ERRORS,
              dependencies=[Depends(require("complaints", "view"))])
async def list_policies(db: DbSession) -> Envelope[list[SlaPolicy]]:
    """The response and resolution targets, in force and past, in working hours
    (Monday to Saturday, 09:30 to 18:30 IST) unless `business_hours_only` is false."""
    return Envelope(data=await service.sla_policies(db))


@policies.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[list[SlaPolicy]],
               responses=_MUTATION_ERRORS, dependencies=[Depends(require("masters", "edit"))])
async def set_policy(body: SlaPolicyIn, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Set a target from a date. The target in force then ends that day; complaints
    already submitted keep theirs. `409 target_exists` when one already starts that day;
    `422 target_in_the_past` for a date before today (IST)."""
    return await _idem(db, claims, idem, "POST /api/v1/complaint-sla-policies", body,
                       lambda: _policies(db, body), 201)


async def _policies(db: Any, body: SlaPolicyIn) -> RootModel[list[SlaPolicy]]:
    return RootModel[list[SlaPolicy]](await service.set_sla_policy(db, body))
