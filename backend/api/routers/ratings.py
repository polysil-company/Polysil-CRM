# ruff: noqa: E501  (route signatures)

"""Ratings (FS-043): feedback entered on an installation, a service visit or a
product, and the dealer rating derived from payment days and order value.

**The docstrings below become prose in `docs/api/ratings.md`** (CLAUDE.md 2.3).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey
from api.idempotency import payload_digest, run_idempotent
from api.schemas import ratings as sch
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.services import ratings as service

router = APIRouter(prefix="/ratings", tags=["ratings"])
partners = APIRouter(prefix="/partners", tags=["ratings"])

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "`idempotency_key_required`."},
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": (
        "Not permitted to rate this; `not_your_order` (a dealer on a sub-dealer's or another "
        "dealer's document); `rating_not_permitted` (the dealer card without `payments.view`).")},
    404: {"model": ErrorResponse, "description": "No such document, or not one the caller can see."},
    409: {"model": ErrorResponse, "description": "`rating_exists`: rated already by this kind of rater."},
    422: {"model": ErrorResponse, "description": (
        "`not_rateable` (nothing has shipped; the complaint is not closed), "
        "`product_not_shipped`, or a field.")},
}
Id = Annotated[str, Path(pattern=UUID_RE)]


@router.post("", status_code=201, response_model=Envelope[sch.Rating], responses=_ERRORS)
async def create_rating(body: sch.RatingCreate, db: DbSession, caller: CallerDep, claims: Claims,
                        idem: IdemKey) -> Response:
    """Record one rating. Staff record what a farmer said (`rated_by: customer`) on an
    order they can edit or a complaint they can edit. A dealer's portal user records
    its own (`rated_by: dealer`) on its own orders and complaints. An installation is
    rateable once something has shipped, a product once it has shipped on that order,
    a service once the complaint is closed. One rating per thing per kind of rater,
    never changed."""
    async def run() -> tuple[int, dict[str, Any]]:
        out = await service.record(db, caller, body)
        return 201, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route="POST /api/v1/ratings",
                                   payload_hash=payload_digest(body.model_dump(mode="json")), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("", response_model=sch.RatingPage, responses=_ERRORS)
async def list_ratings(
        db: DbSession, caller: CallerDep,
        target: sch.Target | None = None,
        partner_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
        product_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
        lead_id: Annotated[str | None, Query(pattern=UUID_RE, description="Also matches leads merged into it.")] = None,
        sales_order_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
        complaint_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
        from_: Annotated[dt.date | None, Query(alias="from")] = None,
        to: dt.date | None = None,
        max_score: Annotated[int | None, Query(ge=1, le=5, description="2 shows the low ones.")] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: str | None = None) -> sch.RatingPage:
    """Ratings the caller can see through their order or complaint, newest first. A
    dealer sees a customer's rating as the score only: no comment, no name."""
    return await service.list_ratings(
        db, caller, target=target, partner_id=partner_id, product_id=product_id, lead_id=lead_id,
        sales_order_id=sales_order_id, complaint_id=complaint_id, start=from_, end=to,
        max_score=max_score, limit=limit, cursor=cursor)


@router.get("/summary", response_model=Envelope[list[sch.SummaryRow]], responses=_ERRORS)
async def summary(db: DbSession, _: CallerDep,
                  group_by: Literal["partner", "product", "target"],
                  from_: Annotated[dt.date | None, Query(alias="from")] = None,
                  to: dt.date | None = None) -> Envelope[list[sch.SummaryRow]]:
    """Count, average and low ratings (1 or 2) by dealer, by product or by kind, over
    the ratings the caller can see. Lowest average first."""
    return Envelope(data=await service.summary(db, group_by=group_by, start=from_, end=to))


@partners.get("/{partner_id}/dealer-rating", response_model=Envelope[sch.DealerRating], responses=_ERRORS)
async def dealer_rating(partner_id: Id, db: DbSession, _: CallerDep) -> Envelope[sch.DealerRating]:
    """A dealer's derived rating, as of today: the value-weighted days from order to
    full payment and the order value over the window, each scored 1 to 5 by the
    settings' bands, and their mean. Never entered by hand. For staff who see payments
    and can read the dealer, and for the dealer itself; the figures are the same for
    every reader."""
    return Envelope(data=await service.dealer_rating(db, partner_id))
