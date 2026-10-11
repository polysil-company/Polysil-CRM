# ruff: noqa: E501  (route signatures)

"""Seller GSTINs and their LUTs (FS-042).

**The docstrings below become prose in `docs/api/seller-gstins.md`** (CLAUDE.md 2.3).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Response
from fastapi.responses import JSONResponse

from api.deps import Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.seller_gstins import Lut, LutCreate, SellerGstin
from api.services import seller_gstins as service

router = APIRouter(prefix="/seller-gstins", tags=["seller gstins"])

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse,
          "description": "`idempotency_key_required`: a write sent without an Idempotency-Key."},
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not permitted: needs `products.edit` to write."},
    404: {"model": ErrorResponse, "description": "No such registration or LUT."},
    409: {"model": ErrorResponse, "description": (
        "`lut_overlap` (another LUT of the registration covers some of the dates), "
        "`lut_duplicate` (the same ARN twice), `lut_in_use` (a document carries it).")},
    422: {"model": ErrorResponse, "description": "`lut_dates`: the range crosses 31 March or ends before it starts; or a field."},
}
_EDIT = [Depends(require("products", "edit"))]
Id = Annotated[str, Path(pattern=r"^[0-9a-fA-F-]{36}$")]


@router.get("", response_model=Envelope[list[SellerGstin]], responses=_ERRORS,
            dependencies=[Depends(require("products", "view"))])
async def list_gstins(db: DbSession, _: Claims) -> Envelope[list[SellerGstin]]:
    """Our GST registrations, the default first, each with its LUTs by year. An export
    under the LUT setting needs a LUT of the selling registration covering the
    quotation's price date, or the order's submit day."""
    return Envelope(data=await service.list_gstins(db))


@router.post("/{gstin_id}/luts", status_code=201, response_model=Envelope[Lut], responses=_ERRORS,
             dependencies=_EDIT)
async def add_lut(gstin_id: Id, body: LutCreate, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Record a LUT for one financial year. Next year's may be added before this year's
    ends; their dates may not overlap. A LUT is never edited: a mistyped one that no
    document carries yet is removed and added again."""
    async def run() -> tuple[int, dict[str, Any]]:
        out = await service.add_lut(db, gstin_id, body)
        return 201, {"data": out.model_dump(mode="json")}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"POST /api/v1/seller-gstins/{gstin_id}/luts",
                                   payload_hash=payload_digest(body.model_dump(mode="json")), work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.delete("/{gstin_id}/luts/{lut_id}", status_code=204, responses=_ERRORS, dependencies=_EDIT)
async def delete_lut(gstin_id: Id, lut_id: Id, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Remove a LUT that no quotation or order carries yet (`in_use` false)."""
    async def run() -> tuple[int, dict[str, Any]]:
        await service.delete_lut(db, gstin_id, lut_id)
        return 204, {}
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub,
                                   route=f"DELETE /api/v1/seller-gstins/{gstin_id}/luts/{lut_id}",
                                   payload_hash=payload_digest({}), work=run)
    if outcome.status_code == 204:
        return Response(status_code=204)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
