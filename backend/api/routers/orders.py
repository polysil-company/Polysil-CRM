"""/orders, /approvals and /dispatches (FS-011 4).

Every mutation takes an Idempotency-Key; a refusal is stored against it, so a
retry after fixing the cause needs a new key. An order outside the caller's scope
is 404. Money and quantities come back as decimal strings.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.config import get_settings
from api.deps import CallerDep, Claims, DbSession, IdemKey, require, require_any
from api.idempotency import payload_digest, run_idempotent
from api.routers.exporting import XLSX_RESPONSE, export, filters_of
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE, TimelinePage
from api.schemas.orders import (
    Approval,
    DecisionRequest,
    DecisionResult,
    Dispatch,
    DispatchCreate,
    DispatchPage,
    Order,
    OrderCreate,
    OrderLinesReplace,
    OrderPage,
    OrderPatch,
    OrderStats,
    QueuePage,
    RemarkRequest,
    SubmitRequest,
    Threshold,
    ThresholdPut,
)
from api.schemas.quotations import PdfLink
from api.schemas.schemes import OrderSchemePreview
from api.services import approvals as approval_service
from api.services import exports
from api.services import orders as service
from api.services import schemes as scheme_service
from api.storage import get_storage

router = APIRouter(prefix="/orders", tags=["orders"])

approvals = APIRouter(prefix="/approvals", tags=["approvals"])
dispatches = APIRouter(prefix="/dispatches", tags=["dispatch"])

Id = Annotated[str, Path(pattern=UUID_RE)]
Cursor = Annotated[str | None, Query(description="From the previous page's next_cursor.")]
ToDate = Annotated[str | None, Query(alias="to", description="ISO date, inclusive.")]
_OWNER_RE = "^(me|" + UUID_RE.strip("^$") + ")$"

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not in your permissions, or not your step."},
    404: {"model": ErrorResponse, "description": "Not in your scope."},
    422: {"model": ErrorResponse, "description": "A rule refused it; see `code` and `fields`."},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    409: {"model": ErrorResponse,
          "description": "Key reused, the status moved on, prices changed (`rate_changed`), "
                         "or the order is not in a state that allows it."},
}


async def _idem(db: Any, claims: Any, idem: str, route: str, body: BaseModel | None,
                work: Callable[[], Awaitable[tuple[int, dict[str, Any]]]]) -> Response:
    digest = payload_digest(body.model_dump(mode="json", exclude_unset=True) if body else {})
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=digest, work=work)
    if outcome.status_code == status.HTTP_204_NO_CONTENT:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


def _order(o: Order) -> dict[str, Any]:
    return {"data": o.model_dump(mode="json")}


# ── orders ───────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[Order],
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("sales_orders", "create"))])
async def create_order(body: OrderCreate, db: DbSession, caller: CallerDep, claims: Claims,
                       idem: IdemKey) -> Response:
    """Create a draft, from accepted quotations or from lines typed in; not both.

    **From quotations:** they must be accepted, current, not already on another order,
    and agree on partner, place of supply, seller registration, price date, office and
    territory (`422 quotations_disagree` names the field). The order takes those from
    them. Quotations on one lead make the farmer the party; on several leads of one
    dealer they make a consolidated order whose party is the dealer
    (`422 partner_required` without one). Lines whose figures changed since the
    quotation are listed in `warnings` as `repriced`.

    **Direct:** `party` and `place_of_supply_territory_id` (or a lead) are required; a
    lead must be qualified or later (`422 lead_not_open`). Pass the preview's
    `price_list_item_id` and `gst_rate_id`; `409 rate_changed` if either moved.

    Only `commercial` and `industrial` are built (`422 order_type_unsupported`). The
    draft has no number until it is submitted.
    """
    async def work() -> tuple[int, dict[str, Any]]:
        return 201, _order(await service.create_order(db, caller, body, get_settings()))
    return await _idem(db, claims, idem, "POST /api/v1/orders", body, work)


@router.get("", response_model=OrderPage, responses=_ERRORS,
            dependencies=[Depends(require("sales_orders", "view"))])
async def list_orders(
    db: DbSession, caller: CallerDep,
    status_: Annotated[str | None, Query(
        alias="status",
        description="One status, or several separated by commas: submitted,approved,"
                    "partially_dispatched.")] = None,
    order_type: Annotated[str | None, Query(description="One order type.")] = None,
    partner_id: Annotated[str | None, Query(
        pattern=UUID_RE, description="Orders placed through this partner.")] = None,
    lead_id: Annotated[str | None, Query(
        pattern=UUID_RE, description="Orders on this lead.")] = None,
    quotation_id: Annotated[str | None, Query(
        pattern=UUID_RE, description="Orders this quotation is or was on. A cancelled order "
                                     "released it; add `status` to find the live one.")] = None,
    owner: Annotated[str | None, Query(pattern=_OWNER_RE,
                                       description="`me`, or a user id.")] = None,
    q: Annotated[str | None, Query(description="Order number, party name or mobile.")] = None,
    created_from: Annotated[str | None, Query(alias="from", description="ISO date, IST.")] = None,
    created_to: ToDate = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Cursor = None,
    include_total: Annotated[bool, Query(description="Also count, up to 1,000.")] = False,
) -> OrderPage:
    """The orders in your scope, newest first, keyset-paged. Each row carries how much
    has shipped (`dispatched_pct`) and whom it is waiting on (`approval_waiting_on`)."""
    return await service.list_orders(
        db, caller, status=status_, order_type=order_type, partner_id=partner_id,
        lead_id=lead_id, owner=owner, q=q, created_from=created_from, created_to=created_to,
        limit=limit, cursor=cursor, include_total=include_total, quotation_id=quotation_id)


@router.get("/stats", response_model=OrderStats, responses=_ERRORS,
            dependencies=[Depends(require("sales_orders", "view"))])
async def order_stats(
    db: DbSession, caller: CallerDep,
    status_: Annotated[str | None, Query(alias="status",
                                         description="Comma-separated statuses.")] = None,
    order_type: Annotated[str | None, Query(description="One order type.")] = None,
    partner_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    lead_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    owner: Annotated[str | None, Query(pattern=_OWNER_RE,
                                       description="`me`, or a user id.")] = None,
    created_from: Annotated[str | None, Query(alias="from", description="ISO date, IST.")] = None,
    created_to: ToDate = None,
) -> OrderStats:
    """Counts for the order board and the dashboard tiles: every status, and the
    submitted orders by whose approval is next. Same scope and filters as the list."""
    return await service.order_stats(
        db, caller, status=status_, order_type=order_type, partner_id=partner_id,
        lead_id=lead_id, owner=owner, created_from=created_from, created_to=created_to)


@router.get("/export", response_class=Response, responses={**_ERRORS, **XLSX_RESPONSE},
            dependencies=[Depends(require("sales_orders", "view"))])
async def export_orders(
    db: DbSession, caller: CallerDep,
    filters: Annotated[dict[str, Any], Depends(filters_of(list_orders))],
) -> Response:
    """Download the order list as an Excel file, with the same filters as the list.

    The file holds exactly the rows the list would show for these filters, across
    every page, and nothing outside your scope. Call it with `fetch` and the bearer
    token, then save the blob. More than 5,000 rows is `422 export_too_large`:
    narrow the filters. An empty list gives a file with the header row only.
    """
    return await export(list_orders, stem="orders", title="Orders", columns=exports.ORDERS,
                        user_id=caller.user_id, filters=filters, db=db, caller=caller)


@router.get("/{order_id}", response_model=Envelope[Order], responses=_ERRORS,
            dependencies=[Depends(require("sales_orders", "view"))])
async def get_order(order_id: Id, db: DbSession, caller: CallerDep) -> dict[str, Any]:
    """The order: lines with what has shipped, is short and is open; the approval chain
    as a stepper; the last rejection while back in draft; the dispatches. A lead,
    partner or owner you cannot see is null. A dealer sees no approver names and no
    remarks."""
    return _order(await service.get_order(db, caller, order_id))


@router.get("/{order_id}/schemes", response_model=Envelope[OrderSchemePreview],
            responses=_ERRORS, dependencies=[Depends(require("sales_orders", "view"))])
async def order_schemes(order_id: Id, db: DbSession) -> Envelope[OrderSchemePreview]:
    """The schemes panel on a draft order (FS-031): the discounts and credits submit
    would apply now, the points or credit it would earn on delivery, and the
    payable. Nothing is stored by reading it; submit stores the same figures.
    `409 order_not_draft` once submitted: read `benefits` on the order instead."""
    return Envelope(data=await scheme_service.order_preview(db, order_id))


@router.get("/{order_id}/pdf", response_model=Envelope[PdfLink],
            responses={**_ERRORS, 409: {"model": ErrorResponse, "description":
                                        "`pdf_pending`, `pdf_failed`, `order_cancelled` or "
                                        "`storage_unavailable`."}},
            dependencies=[Depends(require("sales_orders", "view"))])
async def order_pdf(order_id: Id, db: DbSession, caller: CallerDep) -> Envelope[PdfLink]:
    """A URL for the approved order's PDF, valid ten minutes. **Open it in a new tab;
    do not fetch it with the bearer token.** The order's `pdf_state` says when to
    offer it: `ready` shows "Download PDF", `pending` shows "Preparing PDF". `404`
    before approval, `409 pdf_pending` while the worker has not finished,
    `409 pdf_failed` when it gave up (staff see `pdf_error`), `409 order_cancelled`
    once the order is cancelled."""
    return Envelope(data=await service.pdf_link(db, caller, order_id,
                                                get_storage(get_settings())))


@router.patch("/{order_id}", response_model=Envelope[Order], responses=_MUTATION_ERRORS,
              dependencies=[Depends(require("sales_orders", "edit"))])
async def patch_order(order_id: Id, body: OrderPatch, db: DbSession, caller: CallerDep,
                      claims: Claims, idem: IdemKey) -> Response:
    """Change a draft's header (`409 order_not_draft` otherwise); every change re-prices.
    On an order from quotations the fields they fix are fixed."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 200, _order(await service.patch_order(db, caller, order_id, body, get_settings()))
    return await _idem(db, claims, idem, f"PATCH /api/v1/orders/{order_id}", body, work)


@router.put("/{order_id}/lines", response_model=Envelope[Order], responses=_MUTATION_ERRORS,
            dependencies=[Depends(require("sales_orders", "edit"))])
async def replace_lines(order_id: Id, body: OrderLinesReplace, db: DbSession,
                        caller: CallerDep, claims: Claims, idem: IdemKey) -> Response:
    """Replace a draft's lines wholesale, priced as new lines."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 200, _order(await service.replace_lines(db, caller, order_id, body,
                                                       get_settings()))
    return await _idem(db, claims, idem, f"PUT /api/v1/orders/{order_id}/lines", body, work)


@router.post("/{order_id}/submit", response_model=Envelope[Order], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("sales_orders", "edit"))])
async def submit_order(order_id: Id, body: SubmitRequest, db: DbSession, caller: CallerDep,
                       claims: Claims, idem: IdemKey) -> Response:
    """Number the order, snapshot the seller, and start its approval chain.

    Re-prices at the order's price date with GST at today's date: `409 rate_changed`
    with the new figures if anything moved (re-save, then submit with a new key).
    `422 no_lines`, `422 zero_total`, `422 lead_not_open`,
    `422 seller_registration_ended`, and `422 no_approver` when nobody holds a role the
    chain needs."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 200, _order(await service.submit_order(db, caller, order_id, body,
                                                      get_settings()))
    return await _idem(db, claims, idem, f"POST /api/v1/orders/{order_id}/submit", body, work)


@router.post("/{order_id}/cancel", response_model=Envelope[Order], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("sales_orders", "view"))])
async def cancel_order(order_id: Id, body: RemarkRequest, db: DbSession, caller: CallerDep,
                       claims: Claims, idem: IdemKey) -> Response:
    """Cancel, with a reason. From draft or submitted by the owner or creator or a holder
    of delete; from approved (nothing shipped) by a holder of delete only.
    `409 order_dispatched` once something has shipped; `409 order_not_cancellable`
    otherwise. Releases the order's quotations."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 200, _order(await service.cancel_order(db, caller, order_id, body,
                                                      get_settings()))
    return await _idem(db, claims, idem, f"POST /api/v1/orders/{order_id}/cancel", body, work)


@router.post("/{order_id}/amend", response_model=Envelope[Order], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("sales_orders", "view"))])
async def amend_order(order_id: Id, body: RemarkRequest, db: DbSession, caller: CallerDep,
                      claims: Claims, idem: IdemKey) -> Response:
    """Take an approved order back to draft to change it, keeping its number. Only
    before anything ships (`409 order_dispatched`) and before money is allocated to it
    (`409 order_has_payments`); never a replacement order (`422 order_type_fixed`).
    The owner, the creator or a holder of edit. Then edit and submit as usual: with
    the `order_amend_reapproval` setting at `value_rises`, a total that did not rise
    goes straight to Accounts. Payment instalments are cleared; the PDF returns on
    approval."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 200, _order(await service.amend_order(db, caller, order_id, body,
                                                     get_settings()))
    return await _idem(db, claims, idem, f"POST /api/v1/orders/{order_id}/amend", body, work)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses=_MUTATION_ERRORS,
               dependencies=[Depends(require("sales_orders", "delete"))])
async def delete_order(order_id: Id, db: DbSession, caller: CallerDep, claims: Claims,
                       idem: IdemKey) -> Response:
    """Delete a draft that was never submitted. A numbered draft is cancelled instead
    (`409 order_was_submitted`)."""
    async def work() -> tuple[int, dict[str, Any]]:
        await service.delete_order(db, caller, order_id)
        return 204, {}
    return await _idem(db, claims, idem, f"DELETE /api/v1/orders/{order_id}", None, work)


@router.get("/{order_id}/timeline", response_model=TimelinePage, responses=_ERRORS,
            dependencies=[Depends(require("sales_orders", "view"))])
async def order_timeline(order_id: Id, db: DbSession, caller: CallerDep,
                         limit: Annotated[int, Query(ge=1, le=100)] = 100,
                         cursor: Cursor = None) -> TimelinePage:
    """Newest first; no money in any event. Approval events show who and why to staff,
    and only the outcome to a dealer."""
    return await service.timeline(db, caller, order_id, limit=limit, cursor=cursor)


@router.get("/{order_id}/dispatches", response_model=Envelope[list[Dispatch]],
            responses=_ERRORS, dependencies=[Depends(require("dispatch", "view"))])
async def order_dispatches(order_id: Id, db: DbSession, caller: CallerDep) -> dict[str, Any]:
    """The order's dispatches, voided ones included and marked."""
    return {"data": [d.model_dump(mode="json")
                     for d in await service.order_dispatches(db, caller, order_id)]}


@router.post("/{order_id}/dispatches", status_code=status.HTTP_201_CREATED,
             response_model=Envelope[Dispatch], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("dispatch", "create"))])
async def record_dispatch(order_id: Id, body: DispatchCreate, db: DbSession, caller: CallerDep,
                          claims: Claims, idem: IdemKey) -> Response:
    """Record what left, per line, for an approved or partly dispatched order.

    At least one line, each once, above zero, in the line's unit, at most its open
    quantity (`422 over_open_quantity`, `422 unit_precision`, `422 duplicate_line`).
    `dispatched_at` cannot be in the future. An invoice date before the DC date and an
    invoice number already used come back as `warnings`, not refusals. The invoice
    number is recorded as given; this system does not issue invoices."""
    async def work() -> tuple[int, dict[str, Any]]:
        d = await service.record_dispatch(db, caller, order_id, body)
        return 201, {"data": d.model_dump(mode="json")}
    return await _idem(db, claims, idem, f"POST /api/v1/orders/{order_id}/dispatches", body, work)


@router.post("/{order_id}/close-short", response_model=Envelope[Order],
             responses=_MUTATION_ERRORS, dependencies=[Depends(require("dispatch", "edit"))])
async def close_short(order_id: Id, body: RemarkRequest, db: DbSession, caller: CallerDep,
                      claims: Claims, idem: IdemKey) -> Response:
    """Close the order: every open quantity becomes short, and nothing else ships.
    From approved or partly dispatched."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 200, _order(await service.close_short(db, caller, order_id, body))
    return await _idem(db, claims, idem, f"POST /api/v1/orders/{order_id}/close-short", body,
                       work)


# ── dispatches ───────────────────────────────────────────────────────────────

@dispatches.get("", response_model=DispatchPage, responses=_ERRORS,
                dependencies=[Depends(require("dispatch", "view"))])
async def list_dispatches(
    db: DbSession,
    caller: CallerDep,
    order_id: Annotated[str | None, Query(
        pattern=UUID_RE, description="One order's dispatches.")] = None,
    partner_id: Annotated[str | None, Query(
        pattern=UUID_RE, description="Dispatches on this partner's orders.")] = None,
    created_from: Annotated[str | None, Query(alias="from", description="ISO date, IST.")] = None,
    created_to: ToDate = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Cursor = None,
) -> DispatchPage:
    """Dispatches across the orders you can see, newest first."""
    return await service.list_dispatches(db, caller, order_id=order_id, partner_id=partner_id,
                                         created_from=created_from, created_to=created_to,
                                         limit=limit, cursor=cursor)


@dispatches.post("/{dispatch_id}/void", response_model=Envelope[Order],
                 responses=_MUTATION_ERRORS, dependencies=[Depends(require("dispatch", "edit"))])
async def void_dispatch(dispatch_id: Id, body: RemarkRequest, db: DbSession, caller: CallerDep,
                        claims: Claims, idem: IdemKey) -> Response:
    """Void a dispatch, with a reason. It stays on record, marked; its quantities are
    open again. `409 dispatch_voided` on a second void, `409 order_closed` on a closed
    order."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 200, _order(await service.void_dispatch(db, caller, dispatch_id, body))
    return await _idem(db, claims, idem, f"POST /api/v1/dispatches/{dispatch_id}/void", body,
                       work)


# ── approvals ────────────────────────────────────────────────────────────────

@approvals.get("/pending", response_model=QueuePage, responses=_ERRORS,
               dependencies=[Depends(require_any(("sales_orders", "approve"),
                                                 ("quotations", "approve")))])
async def pending(db: DbSession, caller: CallerDep,
                  include_below: Annotated[bool, Query(
                      description="Also every lower step in your area, so you can cover a "
                                  "manager on leave.")] = False,
                  limit: Annotated[int, Query(ge=1, le=100)] = 50,
                  cursor: Cursor = None,
                  include_total: Annotated[bool, Query(
                      description="Also count everything waiting, for the inbox badge. "
                                  "Stops at 1,000 and sets meta.total_capped.")] = False,
                  ) -> QueuePage:
    """What is waiting on you, oldest first: steps of your role whose earlier steps are
    done, on orders you can see, never your own. A lower step nobody of its own role
    covers comes back `stalled`, and you may decide it."""
    return await approval_service.queue(db, caller, include_below=include_below, limit=limit,
                                        cursor=cursor, include_total=include_total)


@approvals.get("/thresholds", response_model=Envelope[list[Threshold]], responses=_ERRORS)
async def get_thresholds(db: DbSession, caller: CallerDep) -> dict[str, Any]:
    """The approval limits per manager role (and per territory where set), including
    GST. The highest role with a row has no limit in effect."""
    return {"data": [t.model_dump(mode="json") for t in await approval_service.thresholds(db)]}


@approvals.put("/thresholds", response_model=Envelope[list[Threshold]],
               responses=_MUTATION_ERRORS, dependencies=[Depends(require("masters", "edit"))])
async def put_threshold(body: ThresholdPut, db: DbSession, caller: CallerDep, claims: Claims,
                        idem: IdemKey) -> Response:
    """Set one role's limit, company-wide or for a territory. A higher role's limit must
    stay above a lower one's (`422 thresholds_not_increasing`). Applies to orders
    submitted from now on."""
    async def work() -> tuple[int, dict[str, Any]]:
        rows = await approval_service.put_threshold(db, caller, body)
        return 200, {"data": [t.model_dump(mode="json") for t in rows]}
    return await _idem(db, claims, idem, "PUT /api/v1/approvals/thresholds", body, work)


@approvals.get("/{request_id}", response_model=Envelope[Approval], responses=_ERRORS,
               dependencies=[Depends(require_any(("sales_orders", "view"),
                                                 ("quotations", "view")))])
async def get_request(request_id: Id, db: DbSession, caller: CallerDep) -> dict[str, Any]:
    """One approval chain."""
    a = await approval_service.get_request(db, caller, request_id)
    return {"data": a.model_dump(mode="json")}


@approvals.post("/steps/{step_id}/decision", response_model=DecisionResult,
                responses=_MUTATION_ERRORS,
                dependencies=[Depends(require_any(("sales_orders", "approve"),
                                                  ("quotations", "approve"),
                                                  ("complaints", "approve")))])
async def decide(step_id: Id, body: DecisionRequest, db: DbSession, caller: CallerDep,
                 claims: Claims, idem: IdemKey) -> Response:
    """Approve or reject a step. A remark is required to reject, and on every Accounts
    decision. `403 not_your_step`, `403 self_approval`, `409 step_already_decided`,
    `409 earlier_step_undecided`, `409 request_closed`. Returns the order with its new
    status: the last approval approves it, any rejection returns it to draft.

    For a quotation step (`doc_type: quotation` in the queue) it returns the
    quotation: its `discount.send_gate` is `approved` or `returned`, and its status
    stays draft. `409 figures_changed` when the draft was edited under the request.

    For a refund step (`doc_type: complaint`, FS-015b) it returns the complaint:
    `remedy_pending`, or `closed` once the Account Manager approves. On the Account
    Manager's step the remark is the payment reference, and required. A rejection
    returns the complaint to `qc_approved`. `409 request_closed` once QC withdrew the
    refund."""
    async def work() -> tuple[int, dict[str, Any]]:
        return 200, {"data": (await approval_service.decide(db, caller, step_id, body)
                              ).model_dump(mode="json")}
    return await _idem(db, claims, idem, f"POST /api/v1/approvals/steps/{step_id}/decision",
                       body, work)
