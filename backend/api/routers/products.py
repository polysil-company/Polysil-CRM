"""The catalogue and tax endpoints (FS-010 section 4).

Thin: parse, gate, delegate, shape. Every rule lives in the service or the domain.

**The docstrings below become prose in `docs/api/products.md`** (CLAUDE.md 2.3),
the document the frontend track builds against. They say what the endpoint is
*for*.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse

from api.deps import Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.products import (
    HSN_RE,
    HsnAssign,
    HsnRow,
    Product,
    ProductCreate,
    ProductPage,
    ProductPatch,
    TaxRatePage,
    TaxRateUpsert,
)
from api.services import pricing as service

router = APIRouter(prefix="/products", tags=["products"],
                   dependencies=[Depends(require("products", "view"))],
                   responses={403: {"model": ErrorResponse, "description": "No products.view."}})
tax_rates = APIRouter(prefix="/tax-rates", tags=["products"],
                      dependencies=[Depends(require("products", "view"))],
                      responses={403: {"model": ErrorResponse,
                                       "description": "No products.view."}})

_EDIT = Depends(require("products", "edit"))
_WRITE_ERRORS = {
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    403: {"model": ErrorResponse, "description": "No products.edit."},
    409: {"model": ErrorResponse, "description": "A conflict with a row that already exists."},
    422: {"model": ErrorResponse, "description": "A field failed a rule; `fields` names it."},
}

ProductId = Annotated[str, Path(pattern=UUID_RE)]
AsOfQuery = Annotated[dt.date | None, Query(
    description="Resolve the classification and slab as they were on this date. Today in "
                "India by default.")]


@router.get("", response_model=ProductPage)
async def list_products(
    db: DbSession,
    q: Annotated[str | None, Query(
        max_length=100,
        description="Matches anywhere in the description, ignoring case.")] = None,
    category: Annotated[str | None, Query(max_length=50,
                                          description="A product category code.")] = None,
    quotation_category: Annotated[str | None, Query(
        description="head, field or both. Filter the picker to the block being filled.")] = None,
    active: Annotated[bool | None, Query(description="Leave unset to list both.")] = True,
    as_of: AsOfQuery = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ProductPage:
    """The product picker, and the catalogue screen behind it.

    Every signed-in user can read this, including a dealer on the partner portal:
    a picker that cannot list products is not a picker.

    `hsn_code` and `gst_slab` are the ones in force on `as_of`, so a screen
    quoting for April shows April's tax. Both are null when the product has no
    classification yet.

    **Read `provisional_fields` on every row and show it.** It names which of
    `hsn_code`, `gst_slab`, `mrp` and `pack_multiple` are still our stand-ins
    rather than the client's own figures. An empty list means everything on the
    row is theirs.
    """
    return await service.list_products(
        db, q=q, category=category, quotation_category=quotation_category, active=active,
        as_of=as_of, page=page, limit=limit)


@router.get("/{product_id}", response_model=Envelope[Product],
            responses={404: {"model": ErrorResponse, "description": "No such product."}})
async def get_product(product_id: ProductId, db: DbSession,
                      as_of: AsOfQuery = None) -> Envelope[Product]:
    """One catalogue row, in the same shape the list returns."""
    return Envelope(data=await service.get_product(db, product_id, as_of))


@router.post("", response_model=Envelope[Product], status_code=status.HTTP_201_CREATED,
             responses=_WRITE_ERRORS, dependencies=[_EDIT])
async def create_product(body: ProductCreate, db: DbSession, claims: Claims,
                         idem: IdemKey) -> JSONResponse:
    """Add a product to the catalogue.

    `product_category` and `uom` are sent as their codes, and an unknown one is a
    422. Neither is created implicitly: a typo would otherwise become a category
    of one in every picker.

    `description` is the identity until the client sends item codes, so it is
    unique, matched ignoring case, and trimmed of spaces, tabs, line breaks and
    non-breaking spaces. A second product with the same description is a `409
    duplicate_description`, not a silent second row.

    Nothing created here is provisional. A figure an administrator typed is the
    client's own, which is exactly what `provisional_fields` marks the absence of.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        product = await service.create_product(db, body)
        return status.HTTP_201_CREATED, {"data": product.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route="POST /api/v1/products", payload_hash=payload_hash,
                                   work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.patch("/{product_id}", response_model=Envelope[Product],
              responses={**_WRITE_ERRORS,
                         404: {"model": ErrorResponse, "description": "No such product."}},
              dependencies=[_EDIT])
async def patch_product(product_id: ProductId, body: ProductPatch, db: DbSession, claims: Claims,
                        idem: IdemKey) -> JSONResponse:
    """Correct a catalogue row. Send only the fields that change.

    **Setting a field clears that field's `provisional_fields` entry and no
    other.** Sending a pack multiple confirms the pack multiple; it says nothing
    about whether the tax slab is still a guess of ours.

    The classification and the slab are not editable here. They are dated facts
    with their own endpoints, because they change for their own reasons.
    """
    payload_hash = payload_digest(body.model_dump(mode="json", exclude_unset=True))

    async def work() -> tuple[int, dict]:
        product = await service.patch_product(db, product_id, body)
        return status.HTTP_200_OK, {"data": product.model_dump(mode="json")}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route="PATCH /api/v1/products/{id}", payload_hash=payload_hash,
                                   work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("/{product_id}/hsn", response_model=Envelope[list[HsnRow]],
            responses={404: {"model": ErrorResponse, "description": "No such product."}})
async def hsn_history(product_id: ProductId, db: DbSession) -> Envelope[list[HsnRow]]:
    """Every classification this product has had, newest first.

    `effective_to` is exclusive and null on the row in force. A reprinted invoice
    must show the code that applied on its own date, which is what this history
    is for.
    """
    await service.get_product(db, product_id)
    return Envelope(data=await service.hsn_history(db, product_id))


@router.put("/{product_id}/hsn", response_model=Envelope[list[HsnRow]],
            responses={**_WRITE_ERRORS,
                       404: {"model": ErrorResponse, "description": "No such product."}},
            dependencies=[_EDIT])
async def assign_hsn(product_id: ProductId, body: HsnAssign, db: DbSession, claims: Claims,
                     idem: IdemKey) -> JSONResponse:
    """Classify a product under a tariff code, from a date.

    Writing a row closes the one in force at the same date, so the history stays
    a continuous line with no gap and no overlap. A date equal to the current
    row's own start is a `409 hsn_same_start_date`: that row would be left in
    force for no day at all, and every past document that cited it could no longer
    explain itself. Pick a later date, or correct the existing row.

    This also removes `hsn_code` from the product's `provisional_fields`, and
    `gst_slab` too once a rate exists for the new code.
    """
    payload_hash = payload_digest(body.model_dump(mode="json"))

    async def work() -> tuple[int, dict]:
        rows = await service.assign_hsn(db, product_id, body)
        return status.HTTP_200_OK, {"data": [r.model_dump(mode="json") for r in rows]}

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route="PUT /api/v1/products/{id}/hsn",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


# ── tax rates, which belong to a code rather than to a product ───────────────

@tax_rates.get("", response_model=TaxRatePage)
async def list_tax_rates(
    db: DbSession,
    hsn_code: Annotated[str | None, Query(pattern=HSN_RE)] = None,
    in_force: Annotated[bool, Query(description="Only the rate applying today.")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TaxRatePage:
    """The Council's rates, one row per change per code.

    Any signed-in principal can read them. They are not a per-product fact: one
    row covers every product classified under that code, which is why a slab
    change is one write rather than 1,092.
    """
    return await service.list_tax_rates(db, hsn_code=hsn_code, in_force=in_force,
                                        page=page, limit=limit)


@tax_rates.put("/{hsn_code}", response_model=TaxRatePage, responses=_WRITE_ERRORS,
               dependencies=[_EDIT])
async def set_tax_rate(
    hsn_code: Annotated[str, Path(pattern=HSN_RE)],
    body: TaxRateUpsert, db: DbSession, claims: Claims, idem: IdemKey,
) -> JSONResponse:
    """Record a rate for a tariff code, from a date.

    Only the slabs in force are accepted: 0, 0.25, 3, 5, 12, 18 and 28. Anything
    else is a 422. A new slab is a Council decision and arrives as a migration,
    deliberately, because it is a legal event and should not be one data entry
    away.

    As with a classification, writing closes the rate in force at the same date,
    and a date equal to that row's own start is a `409 tax_rate_same_start_date`.

    Every product classified under this code stops marking its slab provisional.
    """
    payload_hash = payload_digest(body.model_dump(mode="json"))

    async def work() -> tuple[int, dict]:
        page = await service.set_tax_rate(db, hsn_code, body)
        return status.HTTP_200_OK, page.model_dump(mode="json")

    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route="PUT /api/v1/tax-rates/{hsn_code}",
                                   payload_hash=payload_hash, work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
