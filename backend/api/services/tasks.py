"""Tasks, the planner and meeting minutes (FS-014).

Reads run under the caller's RLS (the `tasks` ScopeSpec). Assignment goes through
`authz_user_assignable('tasks', …)` (rule 3) and the link through
`task_link_visible_as()` (rule 4), both definers. Every change writes its event in
the same transaction; the service never commits.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import tasks as domain
from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import tasks as sch
from api.schemas.leads import UUID_RE, PageMeta, PartnerRef, UserRef
from api.services import people
from api.services.clock import today_ist
from api.services.leads import _decode_cursor, _encode_cursor

_MAX_LIMIT = 100


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _iso(v: Any) -> str | None:
    return None if v is None else v.isoformat()


def _sqlstate(exc: DBAPIError) -> str:
    return str(getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None) or "")


# ── reading ──────────────────────────────────────────────────────────────────

# Links join under the caller's RLS: a null join over a set id is a link the caller
# can no longer see (rule 4, GAP-142).
_SELECT = """
SELECT t.*, t.task_type::text AS type_text, t.status::text AS status_text,
       l.id AS l_id, l.inquiry_no::text AS l_no, l.farmer_name AS l_name,
       cp.id AS p_id, cp.name AS p_name, cp.partner_type::text AS p_type,
       o.id AS o_id, o.order_no::text AS o_no,
       mt.code::text AS mt_code, mt.name AS mt_name,
       ua.full_name AS assigned_to_name, ub.full_name AS assigned_by_name,
       uc.full_name AS completed_by_name
  FROM task t
  LEFT JOIN lead l ON l.id = t.lead_id
  LEFT JOIN channel_partner cp ON cp.id = t.partner_id
  LEFT JOIN sales_order o ON o.id = t.sales_order_id
  LEFT JOIN meeting_type mt ON mt.id = t.meeting_type_id
  LEFT JOIN app_user ua ON ua.id = t.assigned_to
  LEFT JOIN app_user ub ON ub.id = t.assigned_by
  LEFT JOIN app_user uc ON uc.id = t.completed_by"""


def _lead(set_id: Any, seen_id: Any, no: Any, name: Any) -> sch.LeadLink | None:
    if set_id is None:
        return None
    if seen_id is None:
        return sch.LeadLink(id=str(set_id), hidden=True)
    return sch.LeadLink(id=str(set_id), inquiry_no=no, farmer_name=name)


def _partner(set_id: Any, seen_id: Any, name: Any, kind: Any) -> sch.PartnerLink | None:
    if set_id is None:
        return None
    if seen_id is None:
        return sch.PartnerLink(id=str(set_id), hidden=True)
    return sch.PartnerLink(id=str(set_id), name=name, partner_type=kind)


def _order(set_id: Any, seen_id: Any, no: Any) -> sch.OrderLink | None:
    if set_id is None:
        return None
    if seen_id is None:
        return sch.OrderLink(id=str(set_id), hidden=True)
    return sch.OrderLink(id=str(set_id), order_no=no)


async def _names(db: AsyncSession, rows: list[Any]) -> people.Names:
    return await people.resolve(db, rows, [("assigned_to", "assigned_to_name"),
                                           ("assigned_by", "assigned_by_name"),
                                           ("completed_by", "completed_by_name")])


def _out(r: Any, names: people.Names, now: dt.datetime) -> sch.Task:
    return sch.Task(
        id=str(r.id), title=r.title, task_type=r.type_text, status=r.status_text,
        overdue=domain.is_overdue(r.status_text, r.due_at, now), due_at=r.due_at.isoformat(),
        assigned_to=names.user(r.assigned_to, r.assigned_to_name),
        assigned_by=names.user(r.assigned_by, r.assigned_by_name),
        lead=_lead(r.lead_id, r.l_id, r.l_no, r.l_name),
        partner=_partner(r.partner_id, r.p_id, r.p_name, r.p_type),
        sales_order=_order(r.sales_order_id, r.o_id, r.o_no),
        meeting_type=(sch.MeetingTypeRef(id=str(r.meeting_type_id), code=r.mt_code,
                                         name=r.mt_name) if r.meeting_type_id else None),
        minutes_id=str(r.minutes_id) if r.minutes_id else None,
        notes=r.notes, outcome=r.outcome, gift_shown=r.gift_shown,
        cancel_reason=r.cancel_reason, completed_at=_iso(r.completed_at),
        completed_by=names.user(r.completed_by, r.completed_by_name),
        created_at=r.created_at.isoformat(), updated_at=r.updated_at.isoformat())


async def _many(db: AsyncSession, where: str, params: dict[str, Any], order: str,
                limit: int | None = None) -> list[sch.Task]:
    sql = f"{_SELECT} WHERE {where} ORDER BY {order}" + (f" LIMIT {int(limit)}" if limit else "")
    rows = list((await db.execute(text(sql), params)).all())
    names = await _names(db, rows)
    now = _now()
    return [_out(r, names, now) for r in rows]


async def get_task(db: AsyncSession, task_id: str) -> sch.Task:
    found = await _many(db, "t.id = CAST(:id AS uuid)", {"id": task_id}, "t.id")
    if not found:
        raise NotFoundError("No such task.")
    return found[0]


async def list_tasks(db: AsyncSession, caller: Caller, *, assigned_to: str | None = None,
                     status: list[str] | None = None, task_type: str | None = None,
                     lead_id: str | None = None, partner_id: str | None = None,
                     sales_order_id: str | None = None, due_from: dt.date | None = None,
                     due_to: dt.date | None = None, overdue: bool = False, limit: int = 50,
                     cursor: str | None = None, include_total: bool = False) -> sch.TaskPage:
    limit = max(1, min(limit, _MAX_LIMIT))
    where = ["true"]
    params: dict[str, Any] = {}
    if assigned_to:
        where.append("t.assigned_to = CAST(:who AS uuid)")
        params["who"] = caller.user_id if assigned_to == "me" else assigned_to
    if status:
        where.append("t.status::text = ANY(:status)")
        params["status"] = status
    for col, val in (("task_type", task_type), ("lead_id", lead_id),
                     ("partner_id", partner_id), ("sales_order_id", sales_order_id)):
        if val:
            where.append(f"t.{col}::text = :{col}")
            params[col] = val
    if due_from:
        where.append("t.due_at >= :df")
        params["df"] = domain.day_bounds(due_from)[0]
    if due_to:
        where.append("t.due_at < :dt")
        params["dt"] = domain.day_bounds(due_to)[1]
    if overdue:
        where.append("t.status = 'open' AND t.due_at < now()")
    total = None
    if include_total:
        total = int((await db.execute(text(
            "SELECT count(*) FROM task t WHERE " + " AND ".join(where)), params)).scalar_one())
    if cursor:
        at, tid = _decode_cursor(cursor)
        where.append("(t.due_at, t.id) > (:cat, CAST(:cid AS uuid))")
        params.update(cat=at, cid=tid)
    tasks = await _many(db, " AND ".join(where), params, "t.due_at, t.id", limit + 1)
    next_cursor = None
    if len(tasks) > limit:
        tasks = tasks[:limit]
        last = tasks[-1]
        next_cursor = _encode_cursor(dt.datetime.fromisoformat(last.due_at), last.id)
    return sch.TaskPage(data=tasks, meta=PageMeta(limit=limit, next_cursor=next_cursor,
                                                  total=total))


# ── writing ──────────────────────────────────────────────────────────────────

def _due(value: dt.datetime | dt.date, field: str = "due_at") -> dt.datetime:
    due = (value if isinstance(value, dt.datetime) else domain.due_from_date(value))
    problem = domain.due_problem(due, _now())
    if problem:
        raise ValidationFailed(fields={field: problem})
    return due


async def _emit(db: AsyncSession, *, entity_type: str, entity_id: Any, lead_id: Any,
                kind: str, actor_id: str, **payload: Any) -> None:
    name = (await db.execute(text(
        "SELECT full_name FROM app_user WHERE id = (SELECT app_current_user_id())"))
    ).scalar_one_or_none()
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES (:et, CAST(:e AS uuid), CAST(:l AS uuid), :k, CAST(:me AS uuid), "
        "CAST(:p AS jsonb))"),
        {"et": entity_type, "e": str(entity_id), "l": str(lead_id) if lead_id else None,
         "k": kind, "me": actor_id, "p": json.dumps({"actor_name": name or "", **payload})})


async def _assignee_office(db: AsyncSession, caller: Caller, user_id: str,
                           field: str = "assigned_to") -> str:
    """Rule 3: yourself, or someone `authz_user_assignable('tasks')` admits. Their
    office comes from `staff_directory('tasks')`, not a user row the caller may not
    read (plan review)."""
    if user_id == caller.user_id:
        if caller.org_unit_id is None:
            raise ForbiddenError("Tasks are for Polysil staff.")
        return caller.org_unit_id
    row = (await db.execute(text(
        "SELECT org_unit_id FROM staff_directory('tasks') WHERE id = CAST(:u AS uuid)"),
        {"u": user_id})).one_or_none()
    ok = bool((await db.execute(text(
        "SELECT authz_user_assignable('tasks', CAST(:u AS uuid))"), {"u": user_id})).scalar_one())
    if not ok:
        raise ValidationFailed("You can assign only to yourself or someone below you.",
                               code="not_assignable", fields={field: "not assignable by you"})
    if row is None:
        # FS-037: a dealer's user has no directory row; the task stays in the
        # assigner's office (ADR-034 as amended)
        if caller.org_unit_id is None:
            raise ForbiddenError("Tasks are for Polysil staff.")
        return caller.org_unit_id
    return str(row.org_unit_id)


async def _link_visible_as(db: AsyncSession, caller_id: str, user_id: str,
                           lead_id: str | None, partner_id: str | None, order_id: str | None,
                           field: str = "assigned_to") -> None:
    """Rule 4: the assignee must be able to open what the task hangs off."""
    if lead_id is None and partner_id is None and order_id is None:
        return
    ok = bool((await db.execute(text(
        "SELECT task_link_visible_as(CAST(:u AS uuid), CAST(:l AS uuid), CAST(:p AS uuid), "
        "CAST(:o AS uuid))"), {"u": user_id, "l": lead_id, "p": partner_id,
                               "o": order_id})).scalar_one())
    if ok:
        return
    link = "lead_id" if lead_id else "partner_id" if partner_id else "sales_order_id"
    if user_id == caller_id:
        # your own task: the link is what is wrong, not the person (code review F-11)
        raise ValidationFailed(fields={link: "not found or not yours"})
    raise ValidationFailed("That person cannot open what this task is about.",
                           code="link_not_visible_to_assignee",
                           fields={field: "cannot see the lead, dealer or order"})


async def _lead_still_open(db: AsyncSession, lead_id: str | None) -> None:
    """A task or minutes on a merged or deleted lead would sit where the default
    list hides it, and nothing moves it later (PR 25 review). Checked after the
    insert: the foreign key has locked the lead row by then, so a merge waits for
    this transaction, and one that committed first is visible to this read."""
    if lead_id is None:
        return
    row = (await db.execute(text(
        "SELECT l.stage::text AS stage, l.deleted_at, mi.inquiry_no AS survivor "
        "FROM lead l LEFT JOIN lead mi ON mi.id = l.merged_into_id "
        "WHERE l.id = CAST(:l AS uuid)"), {"l": lead_id})).one_or_none()
    if row is None:
        return
    if row.stage == "merged":
        where = f" into {row.survivor}" if row.survivor else ""
        raise ValidationFailed(f"That lead was merged{where}. Use the lead it was merged into.",
                               code="lead_merged", fields={"lead_id": f"merged{where}"})
    if row.deleted_at is not None:
        raise ValidationFailed("That lead was deleted.", code="lead_deleted",
                               fields={"lead_id": "deleted"})


async def _meeting_type_active(db: AsyncSession, meeting_type_id: str | None) -> None:
    if meeting_type_id is None:
        return
    active = (await db.execute(text(
        "SELECT is_active FROM meeting_type WHERE id = CAST(:m AS uuid) AND deleted_at IS NULL"),
        {"m": meeting_type_id})).scalar_one_or_none()
    if active is None:
        raise ValidationFailed(fields={"meeting_type_id": "no such meeting type"})
    if not active:
        raise ValidationFailed("That meeting type is switched off.", code="meeting_type_inactive",
                               fields={"meeting_type_id": "switched off"})


def _refused_field(exc: DBAPIError, lead_id: str | None, partner_id: str | None,
                   order_id: str | None) -> str:
    """The FK names its column; the policy does not, so it is the one link given."""
    message = str(exc.orig)
    for column in ("meeting_type_id", "minutes_id", "sales_order_id", "partner_id", "lead_id"):
        if column in message:
            return column
    if partner_id:
        return "partner_id"
    if order_id:
        return "sales_order_id"
    return "lead_id"


async def _insert(db: AsyncSession, caller: Caller, *, title: str, task_type: str,
                  due_at: dt.datetime, assignee: str, office: str, lead_id: str | None,
                  partner_id: str | None, order_id: str | None, meeting_type_id: str | None,
                  notes: str | None, minutes_id: str | None = None) -> str:
    try:
        async with db.begin_nested():
            task_id: Any = (await db.execute(text(
                "INSERT INTO task (title, task_type, due_at, assigned_to, assigned_by, "
                "owner_org_unit_id, lead_id, partner_id, sales_order_id, meeting_type_id, "
                "minutes_id, notes, created_by, updated_by) VALUES (:title, "
                "CAST(:tt AS task_type), :due, CAST(:to AS uuid), CAST(:by AS uuid), "
                "CAST(:ou AS uuid), CAST(:l AS uuid), CAST(:p AS uuid), CAST(:o AS uuid), "
                "CAST(:mt AS uuid), CAST(:m AS uuid), :notes, CAST(:by AS uuid), "
                "CAST(:by AS uuid)) RETURNING id"),
                {"title": title, "tt": task_type, "due": due_at, "to": assignee,
                 "by": caller.user_id, "ou": office, "l": lead_id, "p": partner_id,
                 "o": order_id, "mt": meeting_type_id, "m": minutes_id,
                 "notes": notes})).scalar_one()
    except DBAPIError as exc:
        if _sqlstate(exc) in ("42501", "23503"):
            # the insert policy's parent check, or a link that does not exist
            raise ValidationFailed(fields={_refused_field(exc, lead_id, partner_id, order_id):
                                           "not found or not yours"}) from exc
        raise
    await _emit(db, entity_type="task", entity_id=task_id, lead_id=lead_id,
                kind="task.created", actor_id=caller.user_id, task_type=task_type,
                assigned_to=assignee)
    return str(task_id)


async def create_task(db: AsyncSession, caller: Caller, body: sch.TaskCreate) -> sch.Task:
    fields = domain.link_problem(body.lead_id, body.partner_id, body.sales_order_id,
                                 body.task_type, body.meeting_type_id)
    if fields:
        raise ValidationFailed(fields=fields)
    due = _due(body.due_at)
    assignee = body.assigned_to or caller.user_id
    office = await _assignee_office(db, caller, assignee)
    await _meeting_type_active(db, body.meeting_type_id)
    await _link_visible_as(db, caller.user_id, assignee, body.lead_id, body.partner_id,
                           body.sales_order_id)
    task_id = await _insert(db, caller, title=body.title, task_type=body.task_type, due_at=due,
                            assignee=assignee, office=office, lead_id=body.lead_id,
                            partner_id=body.partner_id, order_id=body.sales_order_id,
                            meeting_type_id=body.meeting_type_id, notes=body.notes)
    await _lead_still_open(db, body.lead_id)
    return await get_task(db, task_id)


async def _lock(db: AsyncSession, task_id: str) -> Any:
    """The task, locked, under the UPDATE policy: one the caller may read but not
    change locks nothing and reads as 404 (EC-4)."""
    row = (await db.execute(text(
        "SELECT id, status::text AS status, task_type::text AS task_type, assigned_to, "
        "assigned_by, lead_id, partner_id, sales_order_id, completed_at "
        "FROM task WHERE id = CAST(:id AS uuid) FOR UPDATE"), {"id": task_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such task.")
    return row


def _must_be(row: Any, status: str) -> None:
    if row.status != status:
        raise ConflictError(f"The task is {row.status}.", code=f"task_not_{status}",
                            fields={"status": row.status})


async def patch_task(db: AsyncSession, caller: Caller, task_id: str,
                     body: sch.TaskPatch) -> sch.Task:
    if caller.partner_id is not None:
        # FS-037: a dealer completes its own task and does nothing else with it
        raise ForbiddenError("A dealer can only complete its task.")
    row = await _lock(db, task_id)
    if body.expected_status and body.expected_status != row.status:
        raise ConflictError(f"The task is now {row.status}.", code="status_changed")
    _must_be(row, "open")
    sets: list[str] = ["updated_by = CAST(:me AS uuid)"]
    params: dict[str, Any] = {"id": task_id, "me": caller.user_id}
    given = body.model_fields_set
    if "title" in given and body.title:
        sets.append("title = :title")
        params["title"] = body.title
    if "notes" in given:
        sets.append("notes = :notes")
        params["notes"] = body.notes
    if "due_at" in given and body.due_at is not None:
        sets.append("due_at = :due")
        params["due"] = _due(body.due_at)
    reassigned = None
    if "assigned_to" in given and body.assigned_to and body.assigned_to != str(row.assigned_to):
        office = await _assignee_office(db, caller, body.assigned_to)
        await _link_visible_as(db, caller.user_id, body.assigned_to,
                               str(row.lead_id) if row.lead_id else None,
                               str(row.partner_id) if row.partner_id else None,
                               str(row.sales_order_id) if row.sales_order_id else None)
        # rule 12: the office follows the new assignee
        sets += ["assigned_to = CAST(:to AS uuid)", "owner_org_unit_id = CAST(:ou AS uuid)"]
        params.update(to=body.assigned_to, ou=office)
        reassigned = body.assigned_to
    await db.execute(text(f"UPDATE task SET {', '.join(sets)} WHERE id = CAST(:id AS uuid)"),
                     params)
    await _emit(db, entity_type="task", entity_id=task_id, lead_id=row.lead_id,
                kind="task.reassigned" if reassigned else "task.updated",
                actor_id=caller.user_id,
                **({"assigned_to": reassigned} if reassigned else
                   {"fields": sorted(given - {"expected_status"})}))
    return await get_task(db, task_id)


async def complete_task(db: AsyncSession, caller: Caller, task_id: str,
                        body: sch.TaskComplete) -> sch.Task:
    row = await _lock(db, task_id)
    _must_be(row, "open")
    if body.gift_shown is not None and row.task_type != "meeting":
        raise ValidationFailed(fields={"gift_shown": "meetings only"})
    try:
        async with db.begin_nested():
            await db.execute(text(
                "UPDATE task SET status = 'done', outcome = :outcome, gift_shown = :gift, "
                "completed_at = now(), completed_by = CAST(:me AS uuid), "
                "updated_by = CAST(:me AS uuid) WHERE id = CAST(:id AS uuid)"),
                {"outcome": body.outcome, "gift": body.gift_shown, "me": caller.user_id,
                 "id": task_id})
    except DBAPIError as exc:
        # task_partner_guard (042): the database's half of the dealer rule
        if str(getattr(exc.orig, "sqlstate", "")) == "42501":
            raise ForbiddenError("A dealer can only complete its own task.") from exc
        raise
    await _emit(db, entity_type="task", entity_id=task_id, lead_id=row.lead_id,
                kind="task.completed", actor_id=caller.user_id, task_type=row.task_type)
    return await get_task(db, task_id)


async def cancel_task(db: AsyncSession, caller: Caller, task_id: str,
                      body: sch.TaskCancel) -> sch.Task:
    if caller.partner_id is not None:
        # FS-037: a dealer completes its own task and does nothing else with it
        raise ForbiddenError("A dealer can only complete its task.")
    row = await _lock(db, task_id)
    _must_be(row, "open")
    # §3: the assigner or someone above the assignee cancels. An assignee is never
    # above themselves, so they cancel only what they gave themselves (EC-11,
    # code review F-7: a District Manager given a task by Admin-Sales).
    if str(row.assigned_to) == caller.user_id and str(row.assigned_by) != caller.user_id:
        raise ForbiddenError("Only whoever gave you this task can cancel it.")
    await db.execute(text(
        "UPDATE task SET status = 'cancelled', cancel_reason = :r, updated_by = CAST(:me AS uuid) "
        "WHERE id = CAST(:id AS uuid)"), {"r": body.reason, "me": caller.user_id, "id": task_id})
    await _emit(db, entity_type="task", entity_id=task_id, lead_id=row.lead_id,
                kind="task.cancelled", actor_id=caller.user_id)
    return await get_task(db, task_id)


async def reopen_task(db: AsyncSession, caller: Caller, task_id: str) -> sch.Task:
    if caller.partner_id is not None:
        # FS-037: a dealer completes its own task and does nothing else with it
        raise ForbiddenError("A dealer can only complete its task.")
    row = await _lock(db, task_id)
    _must_be(row, "done")
    if caller.user_id not in (str(row.assigned_to), str(row.assigned_by)):
        raise ForbiddenError("The assignee or whoever gave the task reopens it.")
    if not domain.reopen_allowed(row.completed_at, _now()):
        raise ConflictError("Done more than 7 days ago: raise a new task.",
                            code="reopen_window_passed")
    # the assigner asks the directory, not app_user: a row the users scope does not
    # reach read as "active" and reopened a leaver's task (code review F-2)
    if str(row.assigned_to) == caller.user_id:
        office = caller.org_unit_id
    else:
        office = (await db.execute(text(
            "SELECT org_unit_id FROM staff_directory('tasks') WHERE id = CAST(:u AS uuid)"),
            {"u": str(row.assigned_to)})).scalar_one_or_none()
        # FS-037: a dealer's user has no directory row; the task keeps its office
        if office is None and not bool((await db.execute(text(
                "SELECT authz_user_assignable('tasks', CAST(:u AS uuid))"),
                {"u": str(row.assigned_to)})).scalar_one()):
            raise ConflictError("The assignee is no longer active or no longer in your team.",
                                code="assignee_inactive")
    # the office-move trigger moves open tasks only, so a done task kept the old
    # office; reopened, it follows the assignee (rule 12; astra P1, reproduced)
    await db.execute(text(
        "UPDATE task SET status = 'open', outcome = NULL, gift_shown = NULL, completed_at = NULL, "
        "completed_by = NULL, owner_org_unit_id = COALESCE(CAST(:ou AS uuid), owner_org_unit_id), "
        "updated_by = CAST(:me AS uuid) WHERE id = CAST(:id AS uuid)"),
        {"me": caller.user_id, "id": task_id, "ou": str(office) if office else None})
    await _emit(db, entity_type="task", entity_id=task_id, lead_id=row.lead_id,
                kind="task.reopened", actor_id=caller.user_id)
    return await get_task(db, task_id)


async def assignees(db: AsyncSession, caller: Caller,
                    include_partners: bool = False) -> list[sch.TaskAssignee]:
    me = (await db.execute(text(
        "SELECT full_name FROM app_user WHERE id = CAST(:u AS uuid)"),
        {"u": caller.user_id})).scalar_one_or_none()
    others = (await db.execute(text(
        "SELECT id, full_name FROM staff_directory('tasks') WHERE id <> CAST(:u AS uuid) "
        "ORDER BY full_name, id"), {"u": caller.user_id})).all()
    out = [sch.TaskAssignee(id=caller.user_id, full_name=me or "")] + [
        sch.TaskAssignee(id=str(r.id), full_name=r.full_name) for r in others]
    if include_partners:
        # FS-037: empty unless the setting is on and the caller assigns downwards
        rows = (await db.execute(text(
            "SELECT id, full_name, partner_id, partner_name, partner_type "
            "FROM task_partner_assignees()"))).all()
        out += [sch.TaskAssignee(id=str(r.id), full_name=r.full_name, kind="partner",
                                 partner=PartnerRef(id=str(r.partner_id), name=r.partner_name,
                                                    partner_type=r.partner_type))
                for r in rows]
    return out


# ── the planner ──────────────────────────────────────────────────────────────

async def planner(db: AsyncSession, caller: Caller, day: dt.date,
                  user_id: str | None = None) -> sch.PlannerDay:
    who = user_id or caller.user_id
    if who != caller.user_id:
        allowed = bool((await db.execute(text(
            "SELECT authz_user_assignable('tasks', CAST(:u AS uuid))"), {"u": who})).scalar_one())
        if not allowed:
            raise NotFoundError("No such person in your team.")
    start, end = domain.day_bounds(day)
    due = await _many(db, "t.assigned_to = CAST(:u AS uuid) AND t.status <> 'cancelled' "
                          "AND t.due_at >= :s AND t.due_at < :e",
                      {"u": who, "s": start, "e": end}, "t.due_at, t.id")
    window = domain.overdue_window(day, today_ist())
    overdue: list[sch.Task] = []
    if window:
        overdue = await _many(db, "t.assigned_to = CAST(:u AS uuid) AND t.status = 'open' "
                                  "AND t.due_at >= :from AND t.due_at < :to",
                              {"u": who, "from": window[0], "to": window[1]}, "t.due_at, t.id")
    names = await people.resolve_ids(db, [who])
    return sch.PlannerDay(date=day.isoformat(), user=names.user(who, None), due=due,
                          overdue=overdue)


async def team(db: AsyncSession, caller: Caller, day: dt.date, org_unit_id: str | None = None,
               limit: int = 100, cursor: str | None = None) -> sch.TeamPage:
    if caller.scopes.get("tasks") not in ("org_subtree", "global"):
        raise ForbiddenError("The team view is for managers.")
    limit = max(1, min(limit, _MAX_LIMIT))
    params: dict[str, Any] = {"lim": limit + 1}
    where = ["true"]
    if org_unit_id:
        # every signed-in caller reads every office, so reach is the closure's
        reach: bool = (await db.execute(text(
            "SELECT app_scope('tasks') = 'global' OR EXISTS (SELECT 1 FROM org_closure "
            "WHERE ancestor_id = app_current_org_unit() AND descendant_id = CAST(:o AS uuid))"),
            {"o": org_unit_id})).scalar_one()
        if not reach:
            raise NotFoundError("No such office in your reach.")
        where.append("d.org_unit_id IN (SELECT descendant_id FROM org_closure "
                     "WHERE ancestor_id = CAST(:o AS uuid))")
        params["o"] = org_unit_id
    if cursor:
        name, pid = _decode_team_cursor(cursor)
        where.append("(d.full_name, d.id) > (:cn, CAST(:cid AS uuid))")
        params.update(cn=name, cid=pid)
    start, end = domain.day_bounds(day)
    window = domain.overdue_window(day, today_ist())
    params.update(s=start, e=end, of=window[0] if window else start, ot=window[1] if window else start)
    # one statement: the people below the caller, each with a lateral count under
    # the caller's RLS; a person with no tasks is listed with zeros (plan review)
    rows = (await db.execute(text(f"""
        SELECT d.id, d.full_name, d.org_unit_id, c.due_today, c.done_today, c.overdue
          FROM staff_directory('tasks') d
          LEFT JOIN LATERAL (
            SELECT count(*) FILTER (WHERE t.status <> 'cancelled' AND t.due_at >= :s AND t.due_at < :e) AS due_today,
                   count(*) FILTER (WHERE t.status = 'done' AND t.completed_at >= :s AND t.completed_at < :e) AS done_today,
                   count(*) FILTER (WHERE t.status = 'open' AND t.due_at >= :of AND t.due_at < :ot) AS overdue
              FROM task t WHERE t.assigned_to = d.id) c ON true
         WHERE {" AND ".join(where)}
         ORDER BY d.full_name, d.id LIMIT :lim"""), params)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_team_cursor(rows[-1].full_name, str(rows[-1].id))
    return sch.TeamPage(data=[sch.TeamRow(
        user=UserRef(id=str(r.id), full_name=r.full_name),
        org_unit_id=str(r.org_unit_id) if r.org_unit_id else None,
        due_today=int(r.due_today or 0), done_today=int(r.done_today or 0),
        overdue=int(r.overdue or 0)) for r in rows],
        meta=PageMeta(limit=limit, next_cursor=next_cursor))


def _encode_team_cursor(name: str, pid: str) -> str:
    import base64
    return base64.urlsafe_b64encode(f"{name}\x1f{pid}".encode()).decode()


def _decode_team_cursor(cursor: str) -> tuple[str, str]:
    import base64
    import binascii
    try:
        name, _, pid = base64.urlsafe_b64decode(cursor.encode()).decode().partition("\x1f")
    except (ValueError, binascii.Error) as exc:
        raise ValidationFailed(fields={"cursor": "malformed cursor"}) from exc
    if not re.fullmatch(UUID_RE, pid):
        raise ValidationFailed(fields={"cursor": "malformed cursor"})
    return name, pid


# ── meeting minutes ──────────────────────────────────────────────────────────

async def create_minutes(db: AsyncSession, caller: Caller, body: sch.MinutesCreate) -> sch.Minutes:
    if (body.lead_id is None) == (body.partner_id is None):
        raise ValidationFailed(fields={"lead_id": "give a lead or a dealer, not both"})
    if caller.org_unit_id is None:
        raise ForbiddenError("Minutes are for Polysil staff.")
    try:
        async with db.begin_nested():
            minutes_id = str((await db.execute(text(
                "INSERT INTO meeting_minutes (lead_id, partner_id, task_id, held_at, attendees, "
                "notes, created_by, updated_by) VALUES (CAST(:l AS uuid), CAST(:p AS uuid), "
                "CAST(:t AS uuid), :held, :att, :notes, CAST(:me AS uuid), CAST(:me AS uuid)) "
                "RETURNING id"),
                {"l": body.lead_id, "p": body.partner_id, "t": body.task_id,
                 "held": body.held_at, "att": domain.clean_attendees(body.attendees),
                 "notes": body.notes, "me": caller.user_id})).scalar_one())
    except DBAPIError as exc:
        if _sqlstate(exc) in ("42501", "23503"):
            raise ValidationFailed(fields={"partner_id" if body.partner_id else "lead_id":
                                           "not found or not yours"}) from exc
        raise
    await _lead_still_open(db, body.lead_id)
    if body.task_id:
        await _record_meeting(db, caller, body)
    # all or nothing (EC-7): the first bad item refuses the request, and the
    # dependency rolls the minutes back with it
    for i, item in enumerate(body.action_items):
        field = f"action_items[{i}]"
        try:
            due = _due(item.due_at, f"{field}.due_at")
            assignee = item.assigned_to or caller.user_id
            office = await _assignee_office(db, caller, assignee, f"{field}.assigned_to")
            await _link_visible_as(db, caller.user_id, assignee, body.lead_id, body.partner_id, None,
                                   f"{field}.assigned_to")
        except ValidationFailed as exc:
            raise ValidationFailed(f"Action item {i + 1}: {exc.message}", code=exc.code,
                                   fields=exc.fields) from exc
        await _insert(db, caller, title=item.title, task_type=item.task_type, due_at=due,
                      assignee=assignee, office=office, lead_id=body.lead_id,
                      partner_id=body.partner_id, order_id=None, meeting_type_id=None,
                      notes=None, minutes_id=minutes_id)
    await _emit(db, entity_type="meeting_minutes", entity_id=minutes_id, lead_id=body.lead_id,
                kind="minutes.recorded", actor_id=caller.user_id,
                action_items=len(body.action_items))
    return await get_minutes(db, minutes_id)


async def _record_meeting(db: AsyncSession, caller: Caller, body: sch.MinutesCreate) -> None:
    """EC-6: the meeting the minutes record must be on the same lead or dealer and
    not cancelled; if open, it is completed as 'Minutes recorded'."""
    assert body.task_id is not None
    row = await _lock(db, body.task_id)
    same = (str(row.lead_id) if row.lead_id else None) == body.lead_id and \
           (str(row.partner_id) if row.partner_id else None) == body.partner_id
    if not same:
        raise ValidationFailed("That task is on something else.", code="task_link_mismatch",
                               fields={"task_id": "not on this lead or dealer"})
    if row.task_type != "meeting":
        # a call or a visit on the same lead would otherwise be completed as
        # "Minutes recorded" (astra, reproduced)
        raise ValidationFailed("That task is not a meeting.", code="task_not_a_meeting",
                               fields={"task_id": "not a meeting"})
    if row.status == "cancelled":
        raise ConflictError("That task was cancelled.", code="task_not_open")
    if row.status == "open":
        await complete_task(db, caller, body.task_id,
                            sch.TaskComplete(outcome=domain.MINUTES_OUTCOME))


_MINUTES = (
    "SELECT m.*, l.id AS l_id, l.inquiry_no::text AS l_no, l.farmer_name AS l_name, "
    "cp.id AS p_id, cp.name AS p_name, cp.partner_type::text AS p_type, "
    "u.full_name AS created_by_name "
    "FROM meeting_minutes m LEFT JOIN lead l ON l.id = m.lead_id "
    "LEFT JOIN channel_partner cp ON cp.id = m.partner_id "
    "LEFT JOIN app_user u ON u.id = m.created_by ")


async def _minutes_out(db: AsyncSession, rows: list[Any]) -> list[sch.Minutes]:
    """Three statements for any number of minutes (code review F-10)."""
    if not rows:
        return []
    names = await people.resolve(db, rows, [("created_by", "created_by_name")])
    items = await _many(db, "t.minutes_id = ANY(CAST(:m AS uuid[]))",
                        {"m": [str(r.id) for r in rows]}, "t.due_at, t.id")
    by_minutes: dict[str, list[sch.Task]] = {}
    for item in items:
        by_minutes.setdefault(item.minutes_id or "", []).append(item)
    return [sch.Minutes(
        id=str(r.id), lead=_lead(r.lead_id, r.l_id, r.l_no, r.l_name),
        partner=_partner(r.partner_id, r.p_id, r.p_name, r.p_type),
        task_id=str(r.task_id) if r.task_id else None, held_at=r.held_at.isoformat(),
        attendees=list(r.attendees or []), notes=r.notes,
        created_by=names.user(r.created_by, r.created_by_name),
        created_at=r.created_at.isoformat(), action_items=by_minutes.get(str(r.id), []))
        for r in rows]


async def get_minutes(db: AsyncSession, minutes_id: str) -> sch.Minutes:
    rows = list((await db.execute(text(_MINUTES + "WHERE m.id = CAST(:id AS uuid)"),
                                  {"id": minutes_id})).all())
    if not rows:
        raise NotFoundError("No such minutes.")
    return (await _minutes_out(db, rows))[0]


async def list_minutes(db: AsyncSession, *, lead_id: str | None,
                       partner_id: str | None) -> list[sch.Minutes]:
    if (lead_id is None) == (partner_id is None):
        raise ValidationFailed(fields={"lead_id": "give lead_id or partner_id"})
    rows = list((await db.execute(text(
        _MINUTES + "WHERE (CAST(:l AS uuid) IS NULL OR m.lead_id = CAST(:l AS uuid)) "
        "AND (CAST(:p AS uuid) IS NULL OR m.partner_id = CAST(:p AS uuid)) "
        "ORDER BY m.held_at DESC, m.id DESC LIMIT 100"), {"l": lead_id, "p": partner_id})).all())
    return await _minutes_out(db, rows)
