# ruff: noqa: E501  (route declarations)

"""/dealer-applications (staff) and /public/dealer-apply/{token} (the applicant),
FS-051 and FS-071."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Header, Path, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.config import get_settings
from api.deps import AnonSession, CallerDep, Claims, DbSession, IdemKey
from api.domain import complaints as files
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.dealer_applications import (
    DealerApplicantSession,
    DealerApplication,
    DealerApplicationCreate,
    DealerApplicationDecision,
    DealerApplicationFields,
    DealerApplicationRemark,
    DealerApplicationRow,
    DealerGstLookup,
    DepositRecord,
    DepositRelaxation,
    PartnerType,
    StaffApplicationFields,
)
from api.schemas.leads import UUID_RE
from api.services import dealer_applications as service
from api.storage import get_storage
from api.upload_limit import BodyTooLarge

router = APIRouter(prefix="/dealer-applications", tags=["dealer applications"])
gstin_router = APIRouter(tags=["dealer applications"])
public = APIRouter(prefix="/public/dealer-apply", tags=["dealer applications"])

Id = Annotated[str, Path(pattern=UUID_RE)]
Token = Annotated[str, Path(min_length=20, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]
Session = Annotated[str | None, Header(alias="X-Apply-Session", max_length=100)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not staff who see partners; or not one who may decide."},
    404: {"model": ErrorResponse, "description": "No such application in your scope."},
    409: {"model": ErrorResponse, "description": "`mobile_in_use`, `application_open`, `application_closed`, `already_decided`, `code_in_use`, `deposit_pending`, `deposit_slip_missing`, `deposit_not_due`, `deposit_paid`, `deposit_recorded`."},
    422: {"model": ErrorResponse, "description": "A field; `application_incomplete` lists what is missing; `deposit_short`, `not_lower`."},
}
_PDF: dict[int | str, dict[str, object]] = {
    200: {"content": {"application/pdf": {}}, "description": "The data sheet."},
    503: {"model": ErrorResponse, "description": "`busy`: other PDFs are being made, try again in a moment; `pdf_unavailable`."},
}


def _attachment(body: bytes, content_type: str, name: str) -> Response:
    ext = "pdf" if content_type == "application/pdf" else "html"
    # ASCII only, so any firm name makes a valid header (FS-071 E-11)
    return Response(body, media_type=content_type, headers={
        "Content-Disposition": f"attachment; filename=\"{name}.{ext}\"; filename*=UTF-8''{name}.{ext}",
        "Cache-Control": "no-store"})
_PUBLIC_ERRORS: dict[int | str, dict[str, object]] = {
    403: {"model": ErrorResponse, "description": "`no_session`: verify the mobile first, or again."},
    404: {"model": ErrorResponse, "description": "The link is unknown, expired or closed."},
    422: {"model": ErrorResponse, "description": "`invalid_code`, `rate_limited`, `application_incomplete`, or a field."},
}


async def _idem(db: DbSession, claims: Claims, idem: IdemKey, route: str, body: dict[str, Any],
                work: Any, status: int = 200) -> JSONResponse:
    async def run() -> tuple[int, dict[str, Any]]:
        out = await work()
        return status, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=payload_digest(body), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("", status_code=201, response_model=Envelope[DealerApplication], responses=_ERRORS)
async def create(body: DealerApplicationCreate, db: DbSession, caller: CallerDep, claims: Claims,
                 idem: IdemKey) -> JSONResponse:
    """Start an application for a prospective dealer. Answers `apply_url`, the link to
    send them (shown once). Needs `partners.view`. `409 mobile_in_use` when the
    mobile already signs in staff or a partner user."""
    return await _idem(db, claims, idem, "POST /api/v1/dealer-applications", body.model_dump(mode="json"),
                       lambda: service.create(db, caller, body), 201)


@router.get("", response_model=Envelope[list[DealerApplicationRow]], responses=_ERRORS)
async def list_applications(db: DbSession, caller: CallerDep,
                            status: Annotated[str | None, Query(description="Comma-separated statuses.")] = None,
                            q: Annotated[str | None, Query(max_length=100)] = None,
                            partner_type: PartnerType | None = None) -> Envelope[list[DealerApplicationRow]]:
    """The applications in your partners scope, newest first (at most 200), with each
    one's type and deposit status."""
    return Envelope(data=await service.list_(db, caller, status=status, q=q, partner_type=partner_type))


# before /{app_id}: Starlette matches the path first (FS-071 E-14)
@router.get("/form.pdf", response_class=Response, responses={**_ERRORS, **_PDF})
async def blank_form(caller: CallerDep, partner_type: PartnerType = "dealer") -> Response:
    """The blank data sheet, to print and fill by hand. Needs `partners.view`."""
    body, ctype, name = await service.blank_sheet(caller, partner_type)
    return _attachment(body, ctype, name)


@router.get("/{app_id}", response_model=Envelope[DealerApplication], responses=_ERRORS)
async def get_application(app_id: Id, db: DbSession, caller: CallerDep) -> Envelope[DealerApplication]:
    """One application: every field, what is missing, and what you can do (`can`).
    Documents: `GET /documents?record_type=dealer_application&record_id=`."""
    return Envelope(data=await service.get(db, caller, app_id))


@router.get("/{app_id}/pdf", response_class=Response, responses={**_ERRORS, **_PDF})
async def application_pdf(app_id: Id, db: DbSession, caller: CallerDep) -> Response:
    """The data sheet filled from the application, as the client's paper form. The
    bank account is masked to its last 4 digits for everyone. Made when asked."""
    body, ctype, name = await service.sheet(db, caller, app_id)
    return _attachment(body, ctype, name)


@router.patch("/{app_id}", response_model=Envelope[DealerApplication], responses=_ERRORS)
async def patch_application(app_id: Id, body: StaffApplicationFields, db: DbSession, caller: CallerDep,
                            claims: Claims, idem: IdemKey) -> JSONResponse:
    """Fill or correct fields for the applicant, while draft, returned or submitted.
    `partner_type` changes the type while draft or returned, before any deposit entry,
    and re-reads that type's deposit (`409 deposit_recorded` after one)."""
    fields = service._clean_fields(body)
    return await _idem(db, claims, idem, f"PATCH /api/v1/dealer-applications/{app_id}", fields,
                       lambda: service.staff_action(db, caller, app_id, "patch", fields=fields))


@router.post("/{app_id}/submit", response_model=Envelope[DealerApplication], responses=_ERRORS)
async def submit(app_id: Id, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey) -> JSONResponse:
    """Submit for the applicant. `422 application_incomplete` lists what is missing."""
    return await _idem(db, claims, idem, f"POST /api/v1/dealer-applications/{app_id}/submit", {},
                       lambda: service.staff_action(db, caller, app_id, "submit"))


@router.post("/{app_id}/decision", response_model=Envelope[DealerApplication], responses=_ERRORS)
async def decision(app_id: Id, body: DealerApplicationDecision, db: DbSession, caller: CallerDep, claims: Claims,
                   idem: IdemKey) -> JSONResponse:
    """Approve, reject or return a submitted application. Approving creates the dealer
    (under `parent_id`, or directly under Polysil) or the distributor (always under
    Polysil) and a login on the applicant's mobile, who then signs in with a WhatsApp
    code. Only a role listed in the type's `*_application_deciders` setting, never
    whoever started it. Approval waits for the deposit: `409 deposit_pending`."""
    return await _idem(db, claims, idem, f"POST /api/v1/dealer-applications/{app_id}/decision",
                       body.model_dump(mode="json"), lambda: service.decide(db, caller, app_id, body))


@router.post("/{app_id}/deposit", response_model=Envelope[DealerApplication], responses=_ERRORS)
async def record_deposit(app_id: Id, body: DepositRecord, db: DbSession, caller: CallerDep, claims: Claims,
                         idem: IdemKey) -> JSONResponse:
    """Record the deposit paid. Upload the pay slip first as a `deposit_slip` document
    and name it in `slip_id`. The amount must cover the amount due. Each record is kept
    in `deposit.history`; the latest counts. `409 deposit_not_due` when nothing is due."""
    return await _idem(db, claims, idem, f"POST /api/v1/dealer-applications/{app_id}/deposit",
                       body.model_dump(mode="json"), lambda: service.record_deposit(db, caller, app_id, body))


@router.post("/{app_id}/deposit/relaxation", response_model=Envelope[DealerApplication], responses=_ERRORS)
async def relax_deposit(app_id: Id, body: DepositRelaxation, db: DbSession, caller: CallerDep, claims: Claims,
                        idem: IdemKey) -> JSONResponse:
    """Lower the amount due, to 0 to waive it, with a reason. Only a role listed in the
    `deposit_relaxation_roles` setting, never whoever started the application, and not
    after a payment (`409 deposit_paid`). `403 not_your_relaxation`."""
    return await _idem(db, claims, idem, f"POST /api/v1/dealer-applications/{app_id}/deposit/relaxation",
                       body.model_dump(mode="json"), lambda: service.relax_deposit(db, caller, app_id, body))


@router.post("/{app_id}/withdraw", response_model=Envelope[DealerApplication], responses=_ERRORS)
async def withdraw(app_id: Id, body: DealerApplicationRemark, db: DbSession, caller: CallerDep, claims: Claims,
                   idem: IdemKey) -> JSONResponse:
    """Close an open application. The link stops working."""
    return await _idem(db, claims, idem, f"POST /api/v1/dealer-applications/{app_id}/withdraw",
                       body.model_dump(mode="json"),
                       lambda: service.staff_action(db, caller, app_id, "withdraw", remark=body.remark))


@router.post("/{app_id}/link", response_model=Envelope[DealerApplication], responses=_ERRORS)
async def renew_link(app_id: Id, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey) -> JSONResponse:
    """A new link for 30 days (`apply_url`). The old link and any open applicant
    session stop working."""
    return await _idem(db, claims, idem, f"POST /api/v1/dealer-applications/{app_id}/link", {},
                       lambda: service.staff_action(db, caller, app_id, "renew"))


@gstin_router.get("/gstin/{gstin}", response_model=Envelope[DealerGstLookup], responses=_ERRORS)
async def gstin_lookup(gstin: Annotated[str, Path(max_length=20)], caller: CallerDep) -> Envelope[DealerGstLookup]:
    """What a GSTIN says about itself (valid, its state code and PAN), and its legal
    name, trade name, address and status from the GST data provider when one is
    configured (`lookup: found`); `unavailable` without one."""
    return Envelope(data=await service.lookup(gstin))


# ── the applicant ────────────────────────────────────────────────────────────

class _Code(BaseModel):
    code: str


@public.get("/{token}", responses=_PUBLIC_ERRORS)
async def applicant_view(token: Token, db: AnonSession, session: Session = None) -> dict[str, Any]:
    """The form. Without a session: the firm name, the masked mobile, the status and
    what is required. With `X-Apply-Session`: every field and the documents."""
    return {"data": await service.view(db, token, session)}


@public.post("/{token}/verify", status_code=202, responses=_PUBLIC_ERRORS)
async def applicant_send_code(token: Token, db: AnonSession) -> dict[str, Any]:
    """Send a WhatsApp code to the application's mobile. One a minute, ten a day."""
    await service.send_code(db, token)
    return {"data": {"sent": True}}


@public.post("/{token}/verify/check", response_model=Envelope[DealerApplicantSession], responses=_PUBLIC_ERRORS)
async def applicant_check_code(token: Token, body: _Code, db: AnonSession) -> Response:
    """Check the code. Answers a session for 2 hours: send it as `X-Apply-Session`.
    Five wrong tries burn the code; ask for a new one."""
    got = await service.check_code(db, token, body.code)
    if got is None:
        # an answer, not a raise, so the attempt count commits with the request
        return JSONResponse({"error": {"code": "invalid_code",
                                       "message": "That code didn't work. Check it, or ask for a new one."}},
                            status_code=422)
    return JSONResponse({"data": got.model_dump(mode="json")})


@public.patch("/{token}", responses=_PUBLIC_ERRORS)
async def applicant_patch(token: Token, body: DealerApplicationFields, db: AnonSession,
                          session: Session = None) -> dict[str, Any]:
    """Save fields, while the application is a draft or returned."""
    await service.applicant_write(db, token, session, "patch", service._clean_fields(body))
    return {"data": await service.view(db, token, session)}


@public.post("/{token}/submit", responses=_PUBLIC_ERRORS)
async def applicant_submit(token: Token, db: AnonSession, session: Session = None) -> dict[str, Any]:
    """Submit. `422 application_incomplete` lists what is missing. A repeat answers 200."""
    await service.applicant_write(db, token, session, "submit")
    return {"data": {"submitted": True}}


@public.get("/{token}/gstin/{gstin}", response_model=Envelope[DealerGstLookup], responses=_PUBLIC_ERRORS)
async def applicant_gstin(token: Token, gstin: Annotated[str, Path(max_length=20)], db: AnonSession,
                          session: Session = None) -> Envelope[DealerGstLookup]:
    """The GSTIN read from itself, for the form's "Fetch details" button."""
    await service.view(db, token, session)
    return Envelope(data=await service.lookup(gstin))


@public.post("/{token}/documents", status_code=201, responses=_PUBLIC_ERRORS)
async def applicant_upload(token: Token, db: AnonSession, file: Annotated[UploadFile, File()],
                           doc_type: Annotated[str, Form(pattern=r"^(gst_certificate|pan_card|cancelled_cheque|shop_photo|shop_licence|deposit_slip|other)$")],
                           name: Annotated[str | None, Form(max_length=80)] = None,
                           session: Session = None) -> Response:
    """Upload a document: JPEG, PNG, WebP, HEIC or PDF, up to 10 MB."""
    data = await file.read(files.MAX_UPLOAD_BYTES + 1)
    if len(data) > files.MAX_UPLOAD_BYTES:
        raise BodyTooLarge()
    if doc_type == "other" and not (name or "").strip():
        from api.errors import ValidationFailed
        raise ValidationFailed(fields={"name": "name the document"})
    got = await service.applicant_document(db, token, session, doc_type=doc_type, name=name,
                                           filename=file.filename, data=data,
                                           storage=get_storage(get_settings(), bounded=True))
    return JSONResponse({"data": got}, status_code=201 if got["created"] else 200)


@public.get("/{token}/pdf", response_class=Response, responses={**_PUBLIC_ERRORS, **_PDF})
async def applicant_pdf(token: Token, db: AnonSession, session: Session = None) -> Response:
    """Your data sheet as filled so far, to print and sign. Needs `X-Apply-Session`,
    so only while the application is a draft or returned."""
    body, ctype, name = await service.applicant_sheet(db, token, session)
    return _attachment(body, ctype, name)


@public.delete("/{token}/documents/{doc_id}", status_code=204, responses=_PUBLIC_ERRORS)
async def applicant_remove(token: Token, doc_id: Id, db: AnonSession, session: Session = None) -> Response:
    """Remove one of your own uploads, while the application is a draft or returned.
    `409 document_in_use` for a pay slip a recorded payment names."""
    await service.applicant_document_remove(db, token, session, doc_id)
    return Response(status_code=204)

