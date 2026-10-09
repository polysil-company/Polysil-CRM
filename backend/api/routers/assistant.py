# ruff: noqa: E501  (route signatures and their descriptions)

"""/assistant: the in-app search box (FS-045). Actions you may take and records you
can open; a navigation aid, no model. Staff and dealers; a consumer gets 403."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from api.deps import CallerDep, DbSession
from api.schemas.assistant import AssistantAction, AssistantAnswer
from api.schemas.auth import Envelope, ErrorResponse
from api.services import assistant as service

router = APIRouter(prefix="/assistant", tags=["assistant"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "A consumer (portal) account."},
    422: {"model": ErrorResponse, "description": "q too long or with control characters; limit out of range."},
}


@router.get("", response_model=Envelope[AssistantAnswer], responses=_ERRORS)
async def search(db: DbSession, caller: CallerDep,
                 q: Annotated[str | None, Query(max_length=100,
                                                description="What to do, or a record to find.")] = None,
                 limit: Annotated[int, Query(ge=1, le=20, description="Actions to return.")] = 8,
                 ) -> Envelope[AssistantAnswer]:
    """Actions matching `q` that you may take (a starter set when `q` is empty), and
    from 3 characters, records you can open: leads and their customers by number,
    mobile or name; quotations, orders and complaints by number, or a serial like
    `123`. Debounce 250 ms on the client."""
    return Envelope(data=await service.search(db, caller, q, limit=limit))


@router.get("/actions", response_model=Envelope[list[AssistantAction]], responses=_ERRORS)
async def actions(caller: CallerDep) -> Envelope[list[AssistantAction]]:
    """Every action you may take, for a help page."""
    return Envelope(data=service.catalogue(caller))
