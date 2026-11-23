"""/customers: the customer record (FS-041). A customer is made when one of its leads
reaches qualified; you see it when you see one of its leads."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.customers import CustomerDetail, CustomerPage, CustomerPatch, CustomerTimeline
from api.schemas.leads import UUID_RE
from api.services import customers as service

router = APIRouter(prefix="/customers", tags=["customers"],
                   dependencies=[Depends(require("leads", "view"))])

CustomerId = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse,
          "description": "`idempotency_key_required`: a write sent without an Idempotency-Key."},
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse,
          "description": "No leads.view; on PATCH, a dealer or no leads.edit."},
    404: {"model": ErrorResponse, "description": "You can see none of its leads."},
    422: {"model": ErrorResponse, "description": "A field."},
}


@router.get("", response_model=CustomerPage, responses=_ERRORS)
async def list_customers(
        db: DbSession, caller: CallerDep,
        q: Annotated[str | None, Query(
            max_length=100,
            description="Name or mobile, at least 3 characters.")] = None,
        territory_id: Annotated[str | None, Query(
            max_length=800, description="Customers with a lead you can see in or under these "
                                        "territories, up to 20 ids comma-separated.")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(description="A previous page's next_cursor.")] = None,
) -> CustomerPage:
    """Find a customer, newest first. You see a customer when you can see one of its
    leads."""
    return await service.list_customers(db, caller, q=q, territory_id=territory_id,
                                        limit=limit, cursor=cursor)


@router.get("/{customer_id}", response_model=Envelope[CustomerDetail], responses=_ERRORS)
async def get_customer(customer_id: CustomerId, db: DbSession,
                       caller: CallerDep) -> Envelope[CustomerDetail]:
    """The customer page: details, and the leads (with what brought each), quotations
    and orders you can see on it."""
    return Envelope(data=await service.get_customer(db, caller, customer_id))


@router.get("/{customer_id}/timeline", response_model=CustomerTimeline, responses=_ERRORS)
async def customer_timeline(
        customer_id: CustomerId, db: DbSession, caller: CallerDep,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        before: Annotated[str | None, Query(description="A previous page's next_cursor.")] = None,
) -> CustomerTimeline:
    """Everything that happened on the customer's leads you can see, and to the
    customer itself, newest first. Each entry says which lead it was on."""
    return await service.timeline(db, caller, customer_id, limit=limit, cursor=before)


@router.patch("/{customer_id}", response_model=Envelope[CustomerDetail], responses=_ERRORS,
              dependencies=[Depends(require("leads", "edit"))])
async def patch_customer(customer_id: CustomerId, body: CustomerPatch, db: DbSession,
                         caller: CallerDep, claims: Claims, idem: IdemKey) -> Response:
    """Correct the customer's details or record consent. Its leads, quotations and
    orders keep the party they were made with. Staff only."""
    async def work() -> tuple[int, dict[str, Any]]:
        c = await service.patch_customer(db, caller, customer_id, body)
        return 200, {"data": c.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"PATCH /api/v1/customers/{customer_id}",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
