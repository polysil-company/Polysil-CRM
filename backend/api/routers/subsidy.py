"""The subsidy calculation endpoints (FS-008 section 4).

Thin: parse, gate, delegate, shape. Every rule lives in the service or the
domain, and nothing here is a mutation, so no endpoint takes an idempotency key.

**The docstrings below become prose in `docs/api/subsidy.md`** (CLAUDE.md 2.3),
the document the frontend track builds against. They say what the endpoint is
*for*.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.deps import DbSession, require
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.subsidy import (
    CalculateRequest,
    CalculateResponse,
    CategoryItem,
    ConfigOut,
    CropItem,
    SystemType,
)
from api.services import subsidy as service

router = APIRouter(prefix="/subsidy", tags=["subsidy"],
                   dependencies=[Depends(require("subsidy", "view"))],
                   responses={403: {"model": ErrorResponse, "description": "No subsidy.view."}})

SchemeQuery = Annotated[str, Query(max_length=30, description="Subsidy scheme code.")]
AsOfQuery = Annotated[dt.date | None, Query(
    description="Read the masters in force on this date. Today in India by default.")]


@router.post("/calculate", response_model=Envelope[CalculateResponse],
             responses={404: {"model": ErrorResponse,
                              "description": "No master table is in force on that date."},
                        422: {"model": ErrorResponse,
                              "description": "A field failed a rule; `fields` names it."}})
async def calculate(body: CalculateRequest, db: DbSession) -> Envelope[CalculateResponse]:
    """Turn a bill of quantities into the subsidised quotation breakdown.

    Give it the crops with their areas, spacings and field-unit lines, the head
    unit once for the whole quotation, and the installation rate. You get back the
    block-by-block cost of every crop, the total column, the unit cost the scheme
    allows per hectare, and one row per farmer category with the subsidy and what
    the farmer pays.

    Sprinkler works differently and needs less: one crop, no lines, a nozzle type.
    The engine derives every line from the area, and the pipe size follows the
    area band rather than being sent.

    **Nothing is stored and nothing changes.** This is a preview, safe to call on
    every keystroke; debounce it on the client. It takes no idempotency key.

    Read `warnings` on the response and on each crop. They are stable codes with a
    sentence each, and they mark the places where the scheme's own tool does
    something the engine deliberately does not: a spacing outside the tabulated
    rows, an area below the smallest column, a total column that differs from the
    sum of the crops by a paisa of rounding.
    """
    return Envelope(data=await service.calculate(db, body))


@router.get("/config", response_model=Envelope[ConfigOut],
            responses={404: {"model": ErrorResponse, "description": "Nothing in force."}})
async def config(db: DbSession, scheme: SchemeQuery = "GGRC",
                 as_of: AsOfQuery = None) -> Envelope[ConfigOut]:
    """What each of the three systems accepts, and the constants behind the sums.

    Read this once when the quotation screen loads. It says how many crop blocks a
    system takes, whether it has a head unit, whether a group of farmers can share
    one, which areas a Sprinkler quotation may use, and the rates the calculation
    applies. The figures come from the masters in force, so a screen that prints
    "insurance at 0.28 %" stays right when the scheme changes it.
    """
    return Envelope(data=await service.config(db, scheme, as_of))


@router.get("/crops", response_model=Envelope[list[CropItem]])
async def crops(db: DbSession, scheme: SchemeQuery = "GGRC",
                as_of: AsOfQuery = None) -> Envelope[list[CropItem]]:
    """The crops the scheme tabulates, with the standard lateral spacing of each.

    Use it for the crop picker. The spacing matters to the user: the calculation
    runs at the larger of this and the spacing the designer chose, so a designer
    who picks something tighter than the standard sees no change in the subsidy.
    Sending a crop that is not on this list is refused, rather than quietly
    treated as no crop at all.
    """
    return Envelope(data=await service.crops(db, scheme, as_of))


@router.get("/categories", response_model=Envelope[list[CategoryItem]],
            responses={404: {"model": ErrorResponse, "description": "Nothing in force."}})
async def categories(db: DbSession, system_type: SystemType, scheme: SchemeQuery = "GGRC",
                     as_of: AsOfQuery = None) -> Envelope[list[CategoryItem]]:
    """The farmer categories for one system, in the order the quotation prints them.

    Every category comes back from `/calculate` anyway. This is for a screen that
    wants to show the list, or the labels, before anything has been calculated.
    """
    return Envelope(data=await service.categories(db, scheme, system_type, as_of))
