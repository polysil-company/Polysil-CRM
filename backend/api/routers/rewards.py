"""Reward points (FS-032): rules, settings, gifts, balances, the ledger and redemptions.

**The docstrings below become prose in `docs/api/rewards.md`** (CLAUDE.md 2.3).
"""

# ruff: noqa: E501  (route signatures)

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.rewards import (
    Adjustment,
    Balance,
    Decision,
    Gift,
    GiftCreate,
    GiftPatch,
    GiftRedemptionIn,
    LedgerPage,
    LedgerRow,
    OrderRedemptionIn,
    Redemption,
    RedemptionPage,
    Rule,
    RuleCreate,
    RulePatch,
    Settings,
    SettingsOut,
)
from api.services import rewards as service

rules = APIRouter(prefix="/reward-rules", tags=["rewards"])
settings_router = APIRouter(prefix="/reward-settings", tags=["rewards"])
gifts = APIRouter(prefix="/gifts", tags=["rewards"])
router = APIRouter(prefix="/rewards", tags=["rewards"])
order_points = APIRouter(prefix="/orders", tags=["rewards"])

Id = Annotated[str, Path(pattern=UUID_RE)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "The action is not in your permissions."},
    404: {"model": ErrorResponse, "description": "Not found in your scope."},
    409: {"model": ErrorResponse, "description": "See `error.code`."},
    422: {"model": ErrorResponse, "description": "A field failed validation; see `fields`."},
}


async def _idem(db: Any, claims: Any, idem: str, route: str, body: BaseModel | None,
                work: Callable[[], Awaitable[tuple[int, dict[str, Any]]]]) -> Response:
    digest = payload_digest(body.model_dump(mode="json", exclude_unset=True) if body else {})
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=digest, work=work)
    if outcome.status_code == status.HTTP_204_NO_CONTENT:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


def _ok(model: BaseModel, code: int = status.HTTP_200_OK) -> tuple[int, dict[str, Any]]:
    return code, {"data": model.model_dump(mode="json")}


# ── rules ────────────────────────────────────────────────────────────────────

@rules.get("", response_model=Envelope[list[Rule]], responses=_ERRORS,
           dependencies=[Depends(require("rewards", "view"))])
async def list_rules(db: DbSession) -> Envelope[list[Rule]]:
    """The earning rules, active first."""
    return Envelope(data=await service.list_rules(db))


# `edit`, not `create`: every partner role holds rewards.create, which is how it redeems
# (GAP-043), so `create` must never write a master
@rules.post("", status_code=201, response_model=Envelope[Rule], responses=_ERRORS,
            dependencies=[Depends(require("rewards", "edit"))])
async def create_rule(body: RuleCreate, db: DbSession, caller: CallerDep, claims: Claims,
                      idem: IdemKey) -> Response:
    """Add an earning rule. `order_value`: `points` for every whole `per_amount` rupees of
    a delivered order's value before GST, for the order's partner (`holder: partner`) or
    its staff owner (`holder: staff`). `lead_won`: a flat `points` for the staff owner
    of each won lead. A rule applies to events from its start date; nothing is earned
    backwards."""
    async def work() -> tuple[int, dict[str, Any]]:
        return _ok(await service.create_rule(db, caller, body), 201)
    return await _idem(db, claims, idem, "POST /api/v1/reward-rules", body, work)


@rules.get("/{rule_id}", response_model=Envelope[Rule], responses=_ERRORS,
           dependencies=[Depends(require("rewards", "view"))])
async def get_rule(rule_id: Id, db: DbSession) -> Envelope[Rule]:
    """One rule."""
    return Envelope(data=await service.get_rule(db, rule_id))


@rules.patch("/{rule_id}", response_model=Envelope[Rule], responses=_ERRORS,
             dependencies=[Depends(require("rewards", "edit"))])
async def patch_rule(rule_id: Id, body: RulePatch, db: DbSession, caller: CallerDep,
                     claims: Claims, idem: IdemKey) -> Response:
    """Change a rule. Once it has awarded points, only `valid_to` and `is_active`:
    `409 rule_in_use` otherwise."""
    async def work() -> tuple[int, dict[str, Any]]:
        return _ok(await service.patch_rule(db, caller, rule_id, body))
    return await _idem(db, claims, idem, f"PATCH /api/v1/reward-rules/{rule_id}", body, work)


# ── settings and gifts ───────────────────────────────────────────────────────

@settings_router.get("", response_model=Envelope[SettingsOut], responses=_ERRORS)
async def get_settings(db: DbSession, _: Claims) -> Envelope[SettingsOut]:
    """What a point is worth today and the most of an order points may pay."""
    return Envelope(data=await service.get_settings(db))


@settings_router.put("", response_model=Envelope[SettingsOut], responses=_ERRORS,
                     dependencies=[Depends(require("rewards", "edit"))])
async def put_settings(body: Settings, db: DbSession, caller: CallerDep, claims: Claims,
                       idem: IdemKey) -> Response:
    """Change the point value or the limit, from today. Orders already submitted keep
    the value of their own date. Once a day: `409 settings_changed_today`."""
    async def work() -> tuple[int, dict[str, Any]]:
        return _ok(await service.put_settings(db, caller, body))
    return await _idem(db, claims, idem, "PUT /api/v1/reward-settings", body, work)


@gifts.get("", response_model=Envelope[list[Gift]], responses=_ERRORS,
           dependencies=[Depends(require("rewards", "view"))])
async def list_gifts(db: DbSession, active: Annotated[bool | None, Query()] = None) -> Envelope[list[Gift]]:
    """The gift catalogue, cheapest first."""
    return Envelope(data=await service.list_gifts(db, active))


@gifts.post("", status_code=201, response_model=Envelope[Gift], responses=_ERRORS,
            dependencies=[Depends(require("rewards", "edit"))])
async def create_gift(body: GiftCreate, db: DbSession, caller: CallerDep, claims: Claims,
                      idem: IdemKey) -> Response:
    """Add a gift."""
    async def work() -> tuple[int, dict[str, Any]]:
        return _ok(await service.create_gift(db, caller, body), 201)
    return await _idem(db, claims, idem, "POST /api/v1/gifts", body, work)


@gifts.patch("/{gift_id}", response_model=Envelope[Gift], responses=_ERRORS,
             dependencies=[Depends(require("rewards", "edit"))])
async def patch_gift(gift_id: Id, body: GiftPatch, db: DbSession, caller: CallerDep,
                     claims: Claims, idem: IdemKey) -> Response:
    """Change a gift. A pending request keeps the points it was asked at."""
    async def work() -> tuple[int, dict[str, Any]]:
        return _ok(await service.patch_gift(db, caller, gift_id, body))
    return await _idem(db, claims, idem, f"PATCH /api/v1/gifts/{gift_id}", body, work)


# ── balances, the ledger, adjustments ────────────────────────────────────────

_HolderQ = Annotated[str | None, Query(pattern=UUID_RE, description="Staff: a partner they can see.")]
_UserQ = Annotated[str | None, Query(pattern="^(me|" + UUID_RE.strip("^$") + ")$",
                                     description="`me`, or a user in your scope.")]


@router.get("/balance", response_model=Envelope[Balance], responses=_ERRORS,
            dependencies=[Depends(require("rewards", "view"))])
async def get_balance(db: DbSession, caller: CallerDep, partner_id: _HolderQ = None,
                      user_id: _UserQ = None) -> Envelope[Balance]:
    """A balance. A partner user always gets its own partner's. Staff get their own by
    default, a partner's with `partner_id`, or a team member's with `user_id`, within
    their scope: a field officer sees only their own."""
    return Envelope(data=await service.balance(db, caller, partner_id, user_id))


@router.get("/ledger", response_model=LedgerPage, responses=_ERRORS,
            dependencies=[Depends(require("rewards", "view"))])
async def get_ledger(db: DbSession, caller: CallerDep, partner_id: _HolderQ = None,
                     user_id: _UserQ = None,
                     limit: Annotated[int, Query(ge=1, le=100)] = 50,
                     cursor: Annotated[str | None, Query()] = None) -> LedgerPage:
    """Every change to a balance, newest first: earned, held for a redemption,
    released, reversed, expired, adjusted."""
    return await service.ledger(db, caller, partner_id, user_id, cursor, limit)


@router.post("/adjustments", status_code=201, response_model=Envelope[LedgerRow], responses=_ERRORS,
             dependencies=[Depends(require("rewards", "edit"))])
async def adjust(body: Adjustment, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Add or take away points by hand, with a reason. May take a balance below zero."""
    async def work() -> tuple[int, dict[str, Any]]:
        return _ok(await service.adjust(db, body), 201)
    return await _idem(db, claims, idem, "POST /api/v1/rewards/adjustments", body, work)


# ── redemptions ──────────────────────────────────────────────────────────────

@order_points.post("/{order_id}/reward-redemption", status_code=201,
                   response_model=Envelope[Redemption], responses=_ERRORS,
                   dependencies=[Depends(require("rewards", "create"))])
async def redeem_on_order(order_id: Id, body: OrderRedemptionIn, db: DbSession,
                          caller: CallerDep, claims: Claims, idem: IdemKey) -> Response:
    """The dealer puts points on its own draft order. The points are held at once.
    At submit they come off the payable as a `reward_redemption` benefit, worth
    points times the point value, or the payable left, whichever is less; points not needed
    go back. `422 insufficient_points`, `over_redeem_limit`; `409 points_on_order`."""
    async def work() -> tuple[int, dict[str, Any]]:
        return _ok(await service.redeem_on_order(db, caller, order_id, body.points), 201)
    return await _idem(db, claims, idem, f"POST /api/v1/orders/{order_id}/reward-redemption", body, work)


@order_points.delete("/{order_id}/reward-redemption", status_code=204, responses=_ERRORS,
                     dependencies=[Depends(require("rewards", "create"))])
async def remove_from_order(order_id: Id, db: DbSession, caller: CallerDep, claims: Claims,
                            idem: IdemKey) -> Response:
    """Take the points off a draft; they go back to the balance."""
    async def work() -> tuple[int, dict[str, Any]]:
        await service.remove_from_order(db, caller, order_id)
        return status.HTTP_204_NO_CONTENT, {}
    return await _idem(db, claims, idem, f"DELETE /api/v1/orders/{order_id}/reward-redemption", None, work)


@router.post("/gift-redemptions", status_code=201, response_model=Envelope[Redemption],
             responses=_ERRORS, dependencies=[Depends(require("rewards", "create"))])
async def request_gift(body: GiftRedemptionIn, db: DbSession, caller: CallerDep, claims: Claims,
                       idem: IdemKey) -> Response:
    """Ask for a gift with your points (a partner user: its partner's). The points are
    held at once; a reject or a withdrawal gives them back."""
    async def work() -> tuple[int, dict[str, Any]]:
        return _ok(await service.request_gift(db, caller, body.gift_id), 201)
    return await _idem(db, claims, idem, "POST /api/v1/rewards/gift-redemptions", body, work)


@router.get("/gift-redemptions", response_model=RedemptionPage, responses=_ERRORS,
            dependencies=[Depends(require("rewards", "view"))])
async def list_redemptions(
    db: DbSession,
    status_: Annotated[Literal["pending", "applied", "fulfilled", "rejected", "withdrawn", "released"] | None,
                       Query(alias="status")] = None,
    kind: Annotated[Literal["order", "gift"] | None, Query()] = "gift",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> RedemptionPage:
    """Redemptions in your scope, newest first. `?status=pending` is the gift desk's queue."""
    return await service.list_redemptions(db, status=status_, kind=kind, cursor=cursor, limit=limit)


async def _decide(db: Any, claims: Any, idem: str, rid: str, to: str, body: Decision) -> Response:
    async def work() -> tuple[int, dict[str, Any]]:
        return _ok(await service.decide(db, rid, to, body.remark))
    return await _idem(db, claims, idem, f"POST /api/v1/rewards/gift-redemptions/{rid}/{to}", body, work)


@router.post("/gift-redemptions/{rid}/fulfil", response_model=Envelope[Redemption], responses=_ERRORS,
             dependencies=[Depends(require("rewards", "approve"))])
async def fulfil(rid: Id, body: Decision, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """The gift was handed over. Not by the person who asked."""
    return await _decide(db, claims, idem, rid, "fulfilled", body)


@router.post("/gift-redemptions/{rid}/reject", response_model=Envelope[Redemption], responses=_ERRORS,
             dependencies=[Depends(require("rewards", "approve"))])
async def reject(rid: Id, body: Decision, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """Refuse the request, with a remark; the points go back."""
    return await _decide(db, claims, idem, rid, "rejected", body)


@router.post("/gift-redemptions/{rid}/withdraw", response_model=Envelope[Redemption], responses=_ERRORS,
             dependencies=[Depends(require("rewards", "create"))])
async def withdraw(rid: Id, body: Decision, db: DbSession, claims: Claims, idem: IdemKey) -> Response:
    """The requester takes it back while pending; the points go back."""
    return await _decide(db, claims, idem, rid, "withdrawn", body)
