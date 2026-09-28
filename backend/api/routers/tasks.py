"""/tasks, /planner and /minutes (FS-014): what field staff will do and did, their
day, their team's day, and meeting minutes whose action items are tasks.
Staff only: portal roles hold no tasks (RBAC 6.3)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import CallerDep, Claims, DbSession, IdemKey, require
from api.idempotency import payload_digest, run_idempotent
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE, UserRef
from api.schemas.tasks import (
    Minutes,
    MinutesCreate,
    PlannerDay,
    Task,
    TaskCancel,
    TaskComplete,
    TaskCreate,
    TaskPage,
    TaskPatch,
    TeamPage,
)
from api.services import tasks as service
from api.services.clock import today_ist

router = APIRouter(prefix="/tasks", tags=["tasks"])
planner = APIRouter(prefix="/planner", tags=["tasks"])
minutes = APIRouter(prefix="/minutes", tags=["tasks"])

Id = Annotated[str, Path(pattern=UUID_RE)]
_OWNER_RE = "^(me|" + UUID_RE.strip("^$") + ")$"
Day = Annotated[dt.date | None, Query(description="IST date; today by default.")]
Statuses = Annotated[list[str] | None, Query(description="Repeatable: open, done, cancelled.")]
Cursor = Annotated[str | None, Query(description="From the previous page's next_cursor.")]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Not in your permissions."},
    404: {"model": ErrorResponse, "description": "Not in your scope."},
    422: {"model": ErrorResponse, "description": "A rule refused it; see `code` and `fields`."},
}
_MUTATION_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    400: {"model": ErrorResponse, "description": "Idempotency-Key missing."},
    409: {"model": ErrorResponse, "description": "`task_not_open` or `task_not_done`: the "
                                               "task moved on. A retried complete that "
                                               "answers task_not_open is settled."},
}


async def _idem(db: Any, claims: Any, idem: str, route: str, body: BaseModel | None,
                work: Callable[[], Awaitable[Any]], status: int = 200) -> Response:
    async def run() -> tuple[int, dict[str, Any]]:
        out = await work()
        return status, {"data": out.model_dump(mode="json")}
    digest = payload_digest(body.model_dump(mode="json", exclude_unset=True) if body else {})
    outcome = await run_idempotent(db, key=idem, user_id=claims.sub, route=route,
                                   payload_hash=digest, work=run)
    return JSONResponse(outcome.body, status_code=outcome.status_code)


# ── tasks ────────────────────────────────────────────────────────────────────

@router.post("", status_code=201, response_model=Envelope[Task], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("tasks", "create"))])
async def create_task(body: TaskCreate, db: DbSession, caller: CallerDep, claims: Claims,
                      idem: IdemKey) -> Response:
    """Log a call, visit, meeting or follow-up, for yourself or someone below you,
    optionally about one lead, dealer or order. A meeting on a lead carries one of
    the lead's meeting types. `422 not_assignable`: that person is not yours to
    assign to. `422 link_not_visible_to_assignee`: they cannot open the lead or
    order the task is about. `422 lead_merged` or `lead_deleted`: use the lead it
    was merged into."""
    return await _idem(db, claims, idem, "POST /api/v1/tasks", body,
                       lambda: service.create_task(db, caller, body), 201)


@router.get("", response_model=TaskPage, responses=_ERRORS,
            dependencies=[Depends(require("tasks", "view"))])
async def list_tasks(
    db: DbSession, caller: CallerDep,
    assigned_to: Annotated[str | None, Query(pattern=_OWNER_RE,
                                             description="`me` or a user id.")] = None,
    status: Statuses = None,
    task_type: Annotated[str | None, Query()] = None,
    lead_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    partner_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    sales_order_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
    due_from: Annotated[dt.date | None, Query(description="IST date, inclusive.")] = None,
    due_to: Annotated[dt.date | None, Query(description="IST date, inclusive.")] = None,
    overdue: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Cursor = None,
    include_total: bool = False,
) -> TaskPage:
    """Tasks in your scope, earliest due first: yours, and your team's for a manager.
    A lead's tasks and meetings: `?lead_id=`."""
    return await service.list_tasks(
        db, caller, assigned_to=assigned_to, status=status, task_type=task_type, lead_id=lead_id,
        partner_id=partner_id, sales_order_id=sales_order_id, due_from=due_from, due_to=due_to,
        overdue=overdue, limit=limit, cursor=cursor, include_total=include_total)


@router.get("/assignees", response_model=Envelope[list[UserRef]], responses=_ERRORS,
            dependencies=[Depends(require("tasks", "create"))])
async def task_assignees(db: DbSession, caller: CallerDep) -> Envelope[list[UserRef]]:
    """The assignee picker: you first, then the active staff below you."""
    return Envelope(data=await service.assignees(db, caller))


@router.get("/{task_id}", response_model=Envelope[Task], responses=_ERRORS,
            dependencies=[Depends(require("tasks", "view"))])
async def get_task(task_id: Id, db: DbSession) -> Envelope[Task]:
    """One task. A link you can no longer see reads `{"id", "hidden": true}`."""
    return Envelope(data=await service.get_task(db, task_id))


@router.patch("/{task_id}", response_model=Envelope[Task], responses=_MUTATION_ERRORS,
              dependencies=[Depends(require("tasks", "edit"))])
async def patch_task(task_id: Id, body: TaskPatch, db: DbSession, caller: CallerDep,
                     claims: Claims, idem: IdemKey) -> Response:
    """Change an open task's title, due time or notes, or reassign it. A reassign
    checks the new person as a create would."""
    return await _idem(db, claims, idem, f"PATCH /api/v1/tasks/{task_id}", body,
                       lambda: service.patch_task(db, caller, task_id, body))


@router.post("/{task_id}/complete", response_model=Envelope[Task], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("tasks", "edit"))])
async def complete_task(task_id: Id, body: TaskComplete, db: DbSession, caller: CallerDep,
                        claims: Claims, idem: IdemKey) -> Response:
    """Mark it done with what happened. `gift_shown` on a meeting only."""
    return await _idem(db, claims, idem, f"POST /api/v1/tasks/{task_id}/complete", body,
                       lambda: service.complete_task(db, caller, task_id, body))


@router.post("/{task_id}/cancel", response_model=Envelope[Task], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("tasks", "edit"))])
async def cancel_task(task_id: Id, body: TaskCancel, db: DbSession, caller: CallerDep,
                      claims: Claims, idem: IdemKey) -> Response:
    """Cancel with a reason. An officer cannot cancel a task a manager gave them."""
    return await _idem(db, claims, idem, f"POST /api/v1/tasks/{task_id}/cancel", body,
                       lambda: service.cancel_task(db, caller, task_id, body))


@router.post("/{task_id}/reopen", response_model=Envelope[Task], responses=_MUTATION_ERRORS,
             dependencies=[Depends(require("tasks", "edit"))])
async def reopen_task(task_id: Id, db: DbSession, caller: CallerDep, claims: Claims,
                      idem: IdemKey) -> Response:
    """Reopen a done task, within 7 days, by its assignee or whoever gave it.
    `409 reopen_window_passed` after that: raise a new task."""
    return await _idem(db, claims, idem, f"POST /api/v1/tasks/{task_id}/reopen", None,
                       lambda: service.reopen_task(db, caller, task_id))


# ── the planner ──────────────────────────────────────────────────────────────

@planner.get("", response_model=Envelope[PlannerDay], responses=_ERRORS,
             dependencies=[Depends(require("tasks", "view"))])
async def my_day(db: DbSession, caller: CallerDep,
                 date: Day = None,
                 user_id: Annotated[str | None, Query(pattern=UUID_RE,
                                                      description="Someone below you; "
                                                                  "you by default.")] = None,
                 ) -> Envelope[PlannerDay]:
    """One person's day: what is due that day, and open tasks overdue before it (up
    to 90 days back). A task is either due that day or overdue, never both."""
    return Envelope(data=await service.planner(db, caller, date or today_ist(), user_id))


@planner.get("/team", response_model=TeamPage, responses=_ERRORS,
             dependencies=[Depends(require("tasks", "view"))])
async def team_day(db: DbSession, caller: CallerDep,
                   date: Day = None,
                   org_unit_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                   limit: Annotated[int, Query(ge=1, le=100)] = 100,
                   cursor: Annotated[str | None, Query()] = None) -> TeamPage:
    """A manager's day: one row per active person below you (or below `org_unit_id`),
    with due today, done today and overdue. People with no tasks are listed.
    `403` for someone with no team."""
    return await service.team(db, caller, date or today_ist(), org_unit_id, limit, cursor)


# ── meeting minutes ──────────────────────────────────────────────────────────

@minutes.post("", status_code=201, response_model=Envelope[Minutes], responses=_MUTATION_ERRORS,
              dependencies=[Depends(require("tasks", "create"))])
async def create_minutes(body: MinutesCreate, db: DbSession, caller: CallerDep, claims: Claims,
                         idem: IdemKey) -> Response:
    """Record a meeting on a lead or a dealer, with its action items. One save: a
    bad action item refuses the whole request, with `fields.action_items[i]`.
    `task_id`, the meeting being recorded, is completed if still open.
    `422 task_link_mismatch`: that task is on another lead or dealer.
    `422 task_not_a_meeting`: it is a call or a visit. `409`: it was cancelled.
    `422 lead_merged` or `lead_deleted`: use the lead it was merged into."""
    return await _idem(db, claims, idem, "POST /api/v1/minutes", body,
                       lambda: service.create_minutes(db, caller, body), 201)


@minutes.get("", response_model=Envelope[list[Minutes]], responses=_ERRORS,
             dependencies=[Depends(require("tasks", "view"))])
async def list_minutes(db: DbSession,
                       lead_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                       partner_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                       ) -> Envelope[list[Minutes]]:
    """A lead's or a dealer's minutes, newest first. Staff only. Give exactly one of
    `lead_id` and `partner_id`; none or both is a `422`."""
    return Envelope(data=await service.list_minutes(db, lead_id=lead_id, partner_id=partner_id))


@minutes.get("/{minutes_id}", response_model=Envelope[Minutes], responses=_ERRORS,
             dependencies=[Depends(require("tasks", "view"))])
async def get_minutes(minutes_id: Id, db: DbSession) -> Envelope[Minutes]:
    """The minutes and each action item's task as it stands now."""
    return Envelope(data=await service.get_minutes(db, minutes_id))
