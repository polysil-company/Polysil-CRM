"""/campaigns: Marketing's campaigns, and the picker a lead or QR code names one
from (FS-040). Any staff user reads; writes follow RBAC 6.2 `campaigns`."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.campaigns import Campaign, CampaignCreate, CampaignPatch, CampaignType
from api.schemas.leads import UUID_RE
from api.services import campaigns as service

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

CampaignId = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse,
          "description": "`idempotency_key_required`: a write sent without an Idempotency-Key."},
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse,
          "description": "A dealer; or a write without campaigns.create, .edit or .delete."},
    404: {"model": ErrorResponse, "description": "No such campaign."},
    409: {"model": ErrorResponse,
          "description": "`campaign_name_taken`: another campaign has the name (case ignored). "
                         "`campaign_in_use`: leads or QR codes name it, so it cannot be deleted."},
    422: {"model": ErrorResponse, "description": "A field, such as an end date before the start."},
}


@router.get("", response_model=Envelope[list[Campaign]], responses=_ERRORS)
async def list_campaigns(
        db: DbSession, caller: CallerDep,
        active: Annotated[bool | None, Query(
            description="true: only active ones, for a picker; false: only switched off.")] = None,
        type_: Annotated[CampaignType | None, Query(alias="type",
                                                    description="One campaign type.")] = None,
        q: Annotated[str | None, Query(max_length=100, description="Name contains.")] = None,
) -> Envelope[list[Campaign]]:
    """The campaigns, newest start first, at most 500. For the Marketing screen, and
    for the campaign picker on a lead or QR code (`active=true`). Any staff user.
    The cost fields are null unless you have campaigns.view; `lead_count` counts the
    leads you can see."""
    return Envelope(data=await service.list_campaigns(db, caller, active=active, type_=type_, q=q))


@router.post("", status_code=201, response_model=Envelope[Campaign], responses=_ERRORS,
             dependencies=[Depends(require("campaigns", "create"))])
async def create_campaign(body: CampaignCreate, db: DbSession, caller: CallerDep, claims: Claims,
                          idem: IdemKey) -> Response:
    """Add a campaign. It starts active."""
    async def work() -> tuple[int, dict[str, Any]]:
        c = await service.create_campaign(db, caller, body)
        return 201, {"data": c.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route="POST /api/v1/campaigns",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.get("/{campaign_id}", response_model=Envelope[Campaign], responses=_ERRORS)
async def get_campaign(campaign_id: CampaignId, db: DbSession,
                       caller: CallerDep) -> Envelope[Campaign]:
    """One campaign with `summary`: its leads you can see, wins, sales and cost per
    lead and per win."""
    return Envelope(data=await service.get_campaign(db, caller, campaign_id))


@router.patch("/{campaign_id}", response_model=Envelope[Campaign], responses=_ERRORS,
              dependencies=[Depends(require("campaigns", "edit"))])
async def patch_campaign(campaign_id: CampaignId, body: CampaignPatch, db: DbSession,
                         caller: CallerDep, claims: Claims, idem: IdemKey) -> Response:
    """Change a campaign, or switch it off with `is_active: false`. Leads that already
    name a switched-off campaign keep it. Send only what changes."""
    async def work() -> tuple[int, dict[str, Any]]:
        c = await service.patch_campaign(db, caller, campaign_id, body)
        return 200, {"data": c.model_dump(mode="json")}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"PATCH /api/v1/campaigns/{campaign_id}",
        payload_hash=payload_digest(body.model_dump(mode="json", exclude_unset=True)), work=work)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


@router.delete("/{campaign_id}", status_code=204, responses=_ERRORS,
               dependencies=[Depends(require("campaigns", "delete"))])
async def delete_campaign(campaign_id: CampaignId, db: DbSession, caller: CallerDep, claims: Claims,
                          idem: IdemKey) -> Response:
    """Delete a campaign entered by mistake. Refused with `campaign_in_use` once any
    lead or QR code names it, including leads you cannot see; switch it off instead."""
    async def work() -> tuple[int, dict[str, Any]]:
        await service.delete_campaign(db, caller, campaign_id)
        return 204, {}
    outcome = await run_idempotent(
        db, key=idem, user_id=claims.sub, route=f"DELETE /api/v1/campaigns/{campaign_id}",
        payload_hash=payload_digest({"id": campaign_id}), work=work)
    if outcome.status_code == 204:
        return Response(status_code=204)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
