"""Price lists, and the pricing preview (FS-010 section 4).

Thin: parse, gate, delegate, shape.

Two gates matter here and are worth stating in one place:

* **Reading a price list needs `pricing.view`; writing one needs `pricing.edit`.**
  A partner who can read is still narrowed to their own tier by a restrictive
  policy in the database, not by anything in this file.
* **`POST /pricing/quote-lines` takes no idempotency key.** It stores nothing, for
  the same reason `POST /subsidy/calculate` takes none.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse

from api.deps import Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.products import (
    PriceList,
    PriceListCreate,
    PriceListItemsPage,
    PriceListItemsPut,
    PriceListPage,
    PriceListPatch,
    PublishRequest,
    PublishResult,
    QuoteLinesRequest,
    QuoteLinesResponse,
)
from api.services import pricing as service

price_lists = APIRouter(prefix="/price-lists", tags=["pricing"],
                        dependencies=[Depends(require("pricing", "view"))],
                        responses={403: {"model": ErrorResponse,
                                         "description": "No pricing.view."}})
router = APIRouter(prefix="/pricing", tags=["pricing"],
                   dependencies=[Depends(require("pricing", "view"))],
                   responses={403: {"model": ErrorResponse, "description": "No pricing.view."}})

_EDIT = Depends(require("pricing", "edit"))
_WRITE_ERRORS = {
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    403: {"model": ErrorResponse, "description": "No pricing.edit."},
    404: {"model": ErrorResponse, "description": "No such price list."},
    409: {"model": ErrorResponse,
          "description": "Published, unpriced, or overlapping another list."},
    422: {"model": ErrorResponse, "description": "A field failed a rule; `fields` names it."},
}

ListId = Annotated[str, Path(pattern=UUID_RE)]


@price_lists.get("", response_model=PriceListPage)
async def list_price_lists(
    db: DbSession,
    status_: Annotated[str | None, Query(alias="status",
                                         description="draft or published.")] = None,
    state_territory_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    channel_tier: Annotated[str | None, Query(
        description="distributor, dealer, sub_dealer or farmer.")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PriceListPage:
    """Every price list you may see, newest first.

    A list is scoped by state, by tier, by both, or by neither, and the most
    specific published list in force wins **per product**. So a state list holding
    three corrections sits over a complete base list and overrides only those
    three.

    `unpriced_count` is how many active products the list holds no rate for. It is
    the number the publish step refuses on, so show it on the editing screen
    rather than at publish time.

    A partner sees only their own tier's lists and the untiered ones. That is
    enforced in the database, so an empty page is an answer, not a failure.
    """
    return await service.list_price_lists(db, status=status_,
                                          state_territory_id=state_territory_id,
                                          channel_tier=channel_tier, page=page, limit=limit)


@price_lists.get("/{list_id}", response_model=Envelope[PriceList],
                 responses={404: {"model": ErrorResponse, "description": "No such price list."}})
async def get_price_list(list_id: ListId, db: DbSession) -> Envelope[PriceList]:
    """One price list, in the same shape the list returns."""
    return Envelope(data=await service.get_price_list(db, list_id))


@price_lists.post("", response_model=Envelope[PriceList], status_code=status.HTTP_201_CREATED,
                  responses=_WRITE_ERRORS, dependencies=[_EDIT])
async def create_price_list(body: PriceListCreate, db: DbSession, claims: Claims,
                            idem: IdemKey) -> JSONResponse:
    """Start a new price list. It is always a draft.

    Fill it with `PUT /price-lists/{id}/items`, then publish it. Nothing it holds
    affects a quotation until it is published, so a list can be built over weeks.

    `state_territory_id` must be a state; a district or taluka is a 422. Leave it
    and `channel_tier` null for the base list that applies everywhere.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        created = await service.create_price_list(db, body)
        return status.HTTP_201_CREATED, {"data": created.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route="POST /api/v1/price-lists", payload_hash=payload_hash,
                                   work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@price_lists.patch("/{list_id}", response_model=Envelope[PriceList], responses=_WRITE_ERRORS,
                   dependencies=[_EDIT])
async def patch_price_list(list_id: ListId, body: PriceListPatch, db: DbSession, claims: Claims,
                           idem: IdemKey) -> JSONResponse:
    """Close a price list at a date. `effective_to` is the only editable field.

    A published list's rates and scope never change. A correction is a new list
    effective from the day the new rates start, because editing one in place would
    restate every order already priced from it.

    The date is exclusive and must be forward: later than the list's own start,
    and not in the past.
    """
    payload_hash = payload_digest(body.model_dump(mode="json"))

    async def work() -> tuple[int, dict]:
        updated = await service.patch_price_list(db, list_id, body)
        return status.HTTP_200_OK, {"data": updated.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route="PATCH /api/v1/price-lists/{id}",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@price_lists.get("/{list_id}/items", response_model=PriceListItemsPage,
                 responses={404: {"model": ErrorResponse, "description": "No such price list."}})
async def list_items(
    list_id: ListId, db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    unpriced: Annotated[bool, Query(
        description="Only the active products this list has no rate for.")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> PriceListItemsPage:
    """The rate sheet: every product beside this list's rate for it.

    Products with no rate in this list come back with `rate: null` rather than
    being left out, because the screen's job is filling the gaps. `?unpriced=true`
    narrows it to exactly those.
    """
    return await service.list_items(db, list_id, q=q, unpriced=unpriced, page=page, limit=limit)


@price_lists.put("/{list_id}/items", response_model=PriceListItemsPage, responses=_WRITE_ERRORS,
                 dependencies=[_EDIT])
async def replace_items(list_id: ListId, body: PriceListItemsPut, db: DbSession, claims: Claims,
                        idem: IdemKey) -> JSONResponse:
    """Set a draft's rates. This replaces them all: a product left out has no rate.

    Draft only. A published list is a `409 price_list_published`.

    A rate with more than two decimals is **refused, not rounded**. It is the
    client's number and we may not quietly change it. A rate of zero or below is
    refused too: a blank cell means no row, never a zero row.

    At most 2,000 items in one call.
    """
    payload_hash = payload_digest(body.model_dump(mode="json"))

    async def work() -> tuple[int, dict]:
        page = await service.replace_items(db, list_id, body)
        return status.HTTP_200_OK, page.model_dump(mode="json")

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route="PUT /api/v1/price-lists/{id}/items",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@price_lists.post("/{list_id}/publish", response_model=Envelope[PublishResult],
                  responses=_WRITE_ERRORS, dependencies=[_EDIT])
async def publish(list_id: ListId, body: PublishRequest, db: DbSession, claims: Claims,
                  idem: IdemKey) -> JSONResponse:
    """Put a draft into force, closing the list it supersedes.

    Both happen in one transaction, closing first, so there is no instant where
    two lists cover the same scope and the same day, and none where neither does.
    `closed_predecessor_id` names what was closed.

    **Publishing refuses a list that does not price every active product**, with
    `409 price_list_unpriced` and the count. That is the case worth understanding:
    a successor built over March and only half filled would, on the day it starts,
    leave every other product falling through to a less specific list or refusing
    to price at all. Send `allow_unpriced: true` when a partial list is what you
    mean, which is the normal case for a state list that corrects a few rates.
    """
    payload_hash = payload_digest(body.model_dump(mode="json"))

    async def work() -> tuple[int, dict]:
        result = await service.publish(db, list_id, body)
        return status.HTTP_200_OK, {"data": result.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route="POST /api/v1/price-lists/{id}/publish",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


# ── the preview ──────────────────────────────────────────────────────────────

@router.post("/quote-lines", response_model=Envelope[QuoteLinesResponse],
             responses={404: {"model": ErrorResponse,
                              "description": "No seller registration is in force."},
                        422: {"model": ErrorResponse,
                              "description": "A field failed a rule; `fields` names it."}})
async def quote_lines(body: QuoteLinesRequest, db: DbSession) -> Envelope[QuoteLinesResponse]:
    """Price and tax a set of lines without creating anything.

    A quotation screen needs live totals while the user types, so this is a
    preview: safe to call on every change, debounce it on the client. **Nothing is
    stored and nothing is locked**, and it takes no idempotency key.

    Send the products, the quantities and any per-line discount, plus where the
    goods are delivered. The rate comes from the most specific published list in
    force for that state and tier, per product. A partner's tier comes from their
    own account; `partner_id` is for a staff user pricing on a partner's behalf.

    **Every printed figure comes back, in print order**, including `gross`,
    `cgst_rate` and `sgst_rate`, so nothing on the screen re-derives them and
    lands on a different paisa. `intra_state` says which tax applies. Intra-state
    supply splits into CGST and SGST, each computed at half the slab and rounded
    on its own, so the two are always equal and a small line carries a paisa more
    than the same value would inter-state. Both are correct.

    Keep `price_list_item_id` and `gst_rate_id` on each line. Saving a quotation
    re-resolves and compares them, which is how a rate that changed between the
    preview and the save is caught without locking anything.

    Read `warnings`. Each is `code: sentence`. `provisional_pricing` means some
    figures are still our stand-ins and the quotation must not go to a farmer;
    `future_price_date` means you asked for a date ahead of today;
    `mixed_price_lists` means the lines drew from more than one list, which is
    right if a state list is a discount layer and a mispricing if it replaces the
    base, and nobody has told us which.
    """
    return Envelope(data=await service.quote_lines(db, body))
