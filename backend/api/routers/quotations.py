"""/quotations (FS-005 4): the document, its lifecycle, its versions and its PDF.

Every mutation takes an Idempotency-Key and `expected_status`. A quotation
outside the caller's scope is 404, not 403: the two are indistinguishable on
purpose. Money comes back as decimal strings; the screen never computes a total.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE, TimelinePage
from api.schemas.quotations import (
    ApprovalRequestIn,
    DeleteRequest,
    LinesReplace,
    PdfLink,
    Quotation,
    QuotationCreate,
    QuotationPage,
    QuotationPatch,
    QuotationSummary,
    ReviseRequest,
    SendRequest,
    TransitionRequest,
)
from api.services import quotations as service
from api.storage import get_storage

router = APIRouter(prefix="/quotations", tags=["quotations"])

QuotationId = Annotated[str, Path(pattern=UUID_RE)]
# `me` or a user id; anything else would reach the uuid column and fail at bind
_OWNER_RE = "^(me|" + UUID_RE.strip("^$") + ")$"

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "The action is not in your permissions."},
    404: {"model": ErrorResponse, "description": "Not in your scope."},
    422: {"model": ErrorResponse, "description": "A field failed validation; see `fields`."},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    409: {"model": ErrorResponse,
          "description": "Key reused, the status moved on, prices changed since the preview "
                         "(`rate_changed`), or the quotation is not a draft."},
}


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=Envelope[Quotation],
    responses=_MUTATION_ERRORS, dependencies=[Depends(require("quotations", "create"))],
)
async def create_quotation(
    body: QuotationCreate, db: DbSession, caller: CallerDep, claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Create a draft on a lead. The lines are priced and taxed as part of the
    save; the response is the whole document, already computed.

    The lead must be `qualified`, `quoted`, `negotiation` or `won` (a second unit on
    a won deal); `new` and `contacted` answer `lead_not_qualified`, and a lost or
    merged lead `lead_not_open`. Everything but `lead_id` and `lines` defaults from
    the lead. **A draft has no number**: `quote_no` is null until it is sent.

    Pass each line's `price_list_item_id` and `gst_rate_id` from the preview. If
    either no longer resolves the same way, the whole save is refused with
    `409 rate_changed` naming the lines; re-run the preview and save again **with a
    new Idempotency-Key**, because the refusal is stored against the old one.
    Omit the two ids and the save takes whatever resolves.

    `commercial` and `industrial` are priced today. `export`, `marketing`, `sample`
    and `subsidised` are refused with `sales_type_unsupported` naming the question
    that blocks them.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        q = await service.create_quotation(db, caller, body, get_settings())
        return status.HTTP_201_CREATED, {"data": q.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route="POST /api/v1/quotations",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("", response_model=QuotationPage, responses=_ERRORS,
            dependencies=[Depends(require("quotations", "view"))])
async def list_quotations(
    db: DbSession, caller: CallerDep,
    lead_id: Annotated[str | None, Query(
        pattern=UUID_RE,
        description="Quotations on this lead, and on any lead merged into it.")] = None,
    status_: Annotated[str | None, Query(
        alias="status",
        description="One status, or several separated by commas: sent,viewed,negotiation.")] = None,
    sales_type: Annotated[str | None, Query()] = None,
    owner: Annotated[str | None, Query(pattern=_OWNER_RE,
                                       description="`me`, or a user id.")] = None,
    partner_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    q: Annotated[str | None, Query(description="Number, party name or mobile.")] = None,
    created_from: Annotated[str | None, Query(alias="from", description="ISO date.")] = None,
    created_to: Annotated[str | None, Query(alias="to", description="ISO date, inclusive.")] = None,
    current_only: Annotated[bool, Query(
        description="Hide superseded versions. On by default; switch it off to see "
                    "every version of every number.")] = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
    include_total: Annotated[bool, Query(
        description="Also count how many match, for a \"1 to 25 of 137\" caption. Off by "
                    "default; the count stops at 1,000 and sets `meta.total_capped`.")] = False,
) -> QuotationPage:
    """The list, in scope, newest first, keyset-paged like the lead list. Rows are
    the header without lines. An empty list means nothing in your scope.
    """
    return await service.list_quotations(
        db, caller, lead_id=lead_id, status=status_, sales_type=sales_type, owner=owner,
        partner_id=partner_id, q=q, created_from=created_from, created_to=created_to,
        current_only=current_only, limit=limit, cursor=cursor, include_total=include_total)


@router.get("/{quotation_id}", response_model=Envelope[Quotation], responses=_ERRORS,
            dependencies=[Depends(require("quotations", "view"))])
async def get_quotation(quotation_id: QuotationId, db: DbSession,
                        caller: CallerDep) -> Envelope[Quotation]:
    """The document in full. Every key is always present; null means not set.
    `lead` is null when the lead is deleted or outside your lead scope. Once sent,
    `share_url` is present on every read and `pdf_state` says whether the PDF is
    ready (`pending` for a few seconds after send, then `ready`, or `failed` with
    `pdf_error`).
    """
    return Envelope(data=await service.get_quotation(db, quotation_id, get_settings(),
                                                     portal=caller.partner_id is not None))


@router.patch("/{quotation_id}", response_model=Envelope[Quotation], responses=_MUTATION_ERRORS,
              dependencies=[Depends(require("quotations", "edit"))])
async def patch_quotation(
    quotation_id: QuotationId, body: QuotationPatch, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Change a draft's header: sales type, partner (null for a direct sale), place
    of supply, seller registration, price date, party, terms. Every change
    re-prices the lines, so the response is the whole document again. Refused on
    anything but a draft with `409 quotation_not_draft`.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        q = await service.patch_quotation(db, caller, quotation_id, body, get_settings())
        return status.HTTP_200_OK, {"data": q.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"PATCH /api/v1/quotations/{quotation_id}",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.put("/{quotation_id}/lines", response_model=Envelope[Quotation],
            responses=_MUTATION_ERRORS, dependencies=[Depends(require("quotations", "edit"))])
async def replace_lines(
    quotation_id: QuotationId, body: LinesReplace, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Replace all the lines of a draft. The array order is the line order. Same
    line shape and the same `rate_changed` contract as create. Zero lines is
    allowed on a draft; sending needs at least one.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        q = await service.replace_lines(db, caller, quotation_id, body, get_settings())
        return status.HTTP_200_OK, {"data": q.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"PUT /api/v1/quotations/{quotation_id}/lines",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("/{quotation_id}/send", response_model=Envelope[Quotation],
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("quotations", "edit"))])
async def send_quotation(
    quotation_id: QuotationId, body: SendRequest, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Freeze the draft, number it, mint the share link, and hand the PDF to the
    worker. The lead moves to `quoted`.

    The response carries `quote_no`, `valid_until` (45 days), `share_url` and
    `pdf_state: pending`. The PDF is rendered within seconds; poll this quotation
    until `pdf_state` is `ready`. With `channel: whatsapp` the link goes to the
    party's mobile once the PDF exists, so the farmer never opens a link whose
    document is not there. To send to another number, change the party first.

    Refused with `discount_approval_required` (the discount is above the owner's
    limit: request approval, `fields.send_gate` says why), `approval_pending`,
    `no_lines`, `quotation_not_draft`, `rate_changed` (a price or tax
    moved under the draft since it was saved: re-preview, save, send again with a
    new key), `predecessor_accepted` (the version this one revises was accepted
    meanwhile), `lead_not_open`. A quotation on stand-in prices **is** sendable;
    its PDF carries an "INDICATIVE PRICING" banner and `is_provisional` is true.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        q = await service.send_quotation(db, caller, quotation_id, body, get_settings())
        return status.HTTP_200_OK, {"data": q.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"POST /api/v1/quotations/{quotation_id}/send",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("/{quotation_id}/request-approval", response_model=Envelope[Quotation],
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("quotations", "edit"))])
async def request_approval(
    quotation_id: QuotationId, body: ApprovalRequestIn, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Ask a manager to approve a discount above the owner's limit (FS-013). Use it
    when the draft's `discount.send_gate` is `required`, `void` or `returned`.

    One step goes to the lowest manager above the owner whose limit covers the
    discount; it appears in their `GET /approvals/pending` as a `quotation` row.
    The draft stays a draft. **Any edit or delete cancels a pending request**, so
    the approval is always for the figures the approver saw. Once approved, send
    as usual. Returns the quotation with `approval` pending.

    Refused with `approval_not_required` (within the limit: just send),
    `approval_pending`, `quotation_not_draft`, `no_approver` (nobody's limit covers
    it: lower the discount or ask an administrator)."""
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        q = await service.request_approval(db, caller, quotation_id, body, get_settings())
        return status.HTTP_200_OK, {"data": q.model_dump(mode="json")}

    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub,
        route=f"POST /api/v1/quotations/{quotation_id}/request-approval",
        payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("/{quotation_id}/transition", response_model=Envelope[Quotation],
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("quotations", "edit"))])
async def transition_quotation(
    quotation_id: QuotationId, body: TransitionRequest, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Record the customer's answer: `accepted`, `rejected` or `negotiation`.

    Acceptance moves the lead to `won`; a negotiation moves it to `negotiation`; a
    rejection moves nothing (mark the lead lost with a reason, or revise). Past
    `valid_until` every answer is `422 quotation_expired`; a superseded version is
    `409 quotation_superseded`. A second quotation accepted on a lead already won
    is accepted and moves nothing.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        q = await service.transition_quotation(db, caller, quotation_id, body, get_settings())
        return status.HTTP_200_OK, {"data": q.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"POST /api/v1/quotations/{quotation_id}/transition",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.post("/{quotation_id}/revise", status_code=status.HTTP_201_CREATED,
             response_model=Envelope[Quotation], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("quotations", "create"))])
async def revise_quotation(
    quotation_id: QuotationId, body: ReviseRequest, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """A new version of the number, as a draft: lines and header copied and
    re-priced at `price_effective_date` (today by default, a new offer at today's
    rates). `warnings` names lines whose rate or slab changed (`repriced`) and
    products no longer sold (`discontinued_products`).

    Allowed from `sent`, `viewed`, `negotiation`, `rejected` and `expired`; not from
    a draft (edit it), an accepted version (`invalid_transition`) or an older
    superseded one (`quotation_superseded`). One open revision per number
    (`409 revision_exists`). Sending the revision marks the version it supersedes.
    A quotation on a merged lead is revised on the survivor.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        q = await service.revise_quotation(db, caller, quotation_id, body, get_settings())
        return status.HTTP_201_CREATED, {"data": q.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"POST /api/v1/quotations/{quotation_id}/revise",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("/{quotation_id}/versions", response_model=Envelope[list[QuotationSummary]],
            responses=_ERRORS, dependencies=[Depends(require("quotations", "view"))])
async def list_versions(quotation_id: QuotationId,
                        db: DbSession) -> Envelope[list[QuotationSummary]]:
    """Every version of the number, oldest first. Any version's id works."""
    return Envelope(data=await service.versions(db, quotation_id))


@router.get("/{quotation_id}/timeline", response_model=TimelinePage, responses=_ERRORS,
            dependencies=[Depends(require("quotations", "view"))])
async def quotation_timeline(
    quotation_id: QuotationId, db: DbSession, caller: CallerDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    cursor: Annotated[str | None, Query()] = None,
) -> TimelinePage:
    """The quotation's events, newest first: created, updated, lines_replaced, sent,
    viewed, accepted, rejected, negotiation, expired, revised, deleted, and the
    discount approval's requested, approved, returned and cancelled. The same rows
    appear on the lead's timeline. No payload carries a money figure. A dealer sees
    no staff remark and not who decided a discount.
    """
    return await service.timeline(db, quotation_id, limit=limit, cursor=cursor,
                                  portal=caller.partner_id is not None)


@router.get("/{quotation_id}/pdf", response_model=Envelope[PdfLink],
            responses={**_ERRORS, 409: {"model": ErrorResponse,
                                        "description": "`pdf_pending` or `pdf_failed`."}},
            dependencies=[Depends(require("quotations", "view"))])
async def quotation_pdf(quotation_id: QuotationId, db: DbSession) -> Envelope[PdfLink]:
    """A URL for the PDF, valid ten minutes. **Open it in a new tab; do not fetch
    it with the bearer token.** `404` on a draft, `409 pdf_pending` while the
    worker has not finished, `409 pdf_failed` with `pdf_error` when it gave up.
    """
    return Envelope(data=await service.pdf_link(db, quotation_id, get_storage(get_settings())))


@router.delete("/{quotation_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses=_MUTATION_ERRORS, dependencies=[Depends(require("quotations", "delete"))])
async def delete_quotation(
    quotation_id: QuotationId, body: DeleteRequest, db: DbSession, caller: CallerDep,
    claims: Claims, idem: IdemKey,
) -> Response:
    """Soft-delete a draft. A sent document is never deleted; it is superseded or
    it expires (`409 quotation_not_draft`)."""
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        await service.delete_quotation(db, caller, quotation_id, body)
        return status.HTTP_204_NO_CONTENT, {}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"DELETE /api/v1/quotations/{quotation_id}",
                                   payload_hash=payload_hash, work=work)
    if outcome.status_code == status.HTTP_204_NO_CONTENT:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
