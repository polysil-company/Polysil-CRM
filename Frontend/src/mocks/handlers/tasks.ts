import { http, HttpResponse } from "msw";

import {
  TASK_REOPEN_DAYS,
  TASK_STATUSES,
  cancelTaskRequestSchema,
  completeTaskRequestSchema,
  createMinutesRequestSchema,
  createTaskRequestSchema,
  patchTaskRequestSchema,
  type MinutesWire,
  type PlannerDayWire,
  type TaskPageWire,
  type TaskStatus,
  type TaskWire,
  type TeamPageWire,
} from "@/features/tasks/api/tasks.schemas";
import { summarizeSchemaIssues } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockLookupRows } from "@/mocks/data/lookups";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, MOCK_PARTNERS, mockUuid } from "@/mocks/data/reference";
import { mockMeFor } from "@/mocks/data/sessions";
import { MOCK_TEAM, type MockMinutes, type MockTask, type MockUser } from "@/mocks/data/tasks";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

const DAY_MS = 24 * 60 * 60 * 1000;
const OVERDUE_LOOKBACK_DAYS = 90;
const DEFAULT_LIMIT = 25;
const MAX_LIMIT = 100;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
/** The backend refuses a bigger export: narrow the filters. */
const EXPORT_MAX_ROWS = 5000;

/** The signed-in user, as GET /auth/me names them. */
function currentUser(): MockUser {
  const me = mockMeFor(readMockRole()).data;
  return { id: me.id, full_name: me.full_name };
}

/** How far the user's `tasks` grant reaches, or null without one (dealers get no tasks). */
function taskScope(): string | null {
  return (
    mockPermissionsFor(readMockRole()).find((grant) => grant.module === "tasks")?.scope ?? null
  );
}

/** The people below the user: none for an officer. */
function teamOf(scope: string | null): readonly MockUser[] {
  return scope === null || scope === "own" ? [] : MOCK_TEAM;
}

/** Tasks the user may see: their own, and their team's for a manager. */
function visibleTasks(me: MockUser, scope: string | null): MockTask[] {
  const team = new Set(teamOf(scope).map((person) => person.id));
  return mockDb.tasks.filter(
    (task) =>
      task.assigned_to !== null && (task.assigned_to.id === me.id || team.has(task.assigned_to.id)),
  );
}

/** As the backend serves it: open and past its due time is overdue. */
function toWire(task: MockTask, now: number = Date.now()): TaskWire {
  return { ...task, overdue: task.status === "open" && Date.parse(task.due_at) < now };
}

/** [start, end) of an Indian calendar day, in epoch ms. */
function dayBounds(date: string): [number, number] {
  const start = Date.parse(`${date}T00:00:00+05:30`);
  return [start, start + DAY_MS];
}

/** A request that fails the schema, as the backend's `fields` map. */
function fieldsOf(error: Parameters<typeof summarizeSchemaIssues>[0]): Record<string, string> {
  return Object.fromEntries(
    summarizeSchemaIssues(error).map((issue) => [issue.path, issue.message]),
  );
}

/** Minutes as the backend serves them: each action item's task as it stands now. */
function minutesWire(minutes: MockMinutes): MinutesWire {
  const { action_item_ids: ids, ...rest } = minutes;
  return {
    ...rest,
    action_items: ids.flatMap((taskId) => {
      const task = mockDb.tasks.find((item) => item.id === taskId);
      return task === undefined ? [] : [toWire(task)];
    }),
  };
}

function noTasksModule(): Response {
  return errorResponse(403, "forbidden", "Tasks are not in your permissions.");
}

/** Replays a write made with the same Idempotency-Key, or refuses the key for another request. */
function replay(key: string, serialized: string): Response | null {
  const earlier = mockDb.taskWrites.get(key);
  if (earlier === undefined) return null;
  if (earlier.body !== serialized) {
    return errorResponse(
      409,
      "idempotency_key_reused",
      "This Idempotency-Key was already used for a different request.",
    );
  }
  const task = mockDb.tasks.find((item) => item.id === earlier.taskId);
  return task === undefined ? null : HttpResponse.json({ data: toWire(task) });
}

function notOpen(task: MockTask, expected: TaskStatus): Response {
  return errorResponse(409, `task_not_${expected}`, `The task is ${task.status}.`, {
    status: task.status,
  });
}

/** Saves a change to one task and answers with it. */
function saveTask(key: string, serialized: string, next: MockTask): Response {
  mockDb.tasks = mockDb.tasks.map((task) => (task.id === next.id ? next : task));
  mockDb.taskWrites.set(key, { body: serialized, taskId: next.id });
  return HttpResponse.json({ data: toWire(next) });
}

/** Finds a task the user may act on, or the response that says why not. */
function findTask(taskId: unknown): MockTask | Response {
  const scope = taskScope();
  if (scope === null) return noTasksModule();
  const task = visibleTasks(currentUser(), scope).find((item) => item.id === taskId);
  return task ?? errorResponse(404, "not_found", "No such task.");
}

function idempotencyKeyOf(request: Request): string | Response {
  return (
    request.headers.get("idempotency-key") ??
    errorResponse(400, "idempotency_key_required", "Idempotency-Key missing.")
  );
}

/** The filters GET /tasks and GET /tasks/export share: the export holds exactly the list. */
function filterTasks(params: URLSearchParams, scope: string | null): MockTask[] {
  const me = currentUser();
  const leadId = params.get("lead_id");
  const assignedTo = params.get("assigned_to");
  const type = params.get("task_type");
  const overdueOnly = params.get("overdue") === "true";
  const statuses = params
    .getAll("status")
    .flatMap((value) => value.split(","))
    .filter((value): value is TaskStatus => TASK_STATUSES.some((status) => status === value));
  const now = Date.now();
  return visibleTasks(me, scope).filter(
    (task) =>
      (leadId === null || task.lead?.id === leadId) &&
      (assignedTo === null ||
        task.assigned_to?.id === (assignedTo === "me" ? me.id : assignedTo)) &&
      (type === null || task.task_type === type) &&
      (!overdueOnly || (task.status === "open" && Date.parse(task.due_at) < now)) &&
      (statuses.length === 0 || statuses.includes(task.status)),
  );
}

export const taskHandlers = [
  /** TASK-001 · One person's day: due that day by time, and open tasks overdue before it. */
  http.get(buildApiUrl("/planner"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const scope = taskScope();
    if (scope === null) return noTasksModule();

    const url = new URL(request.url);
    const date = url.searchParams.get("date") ?? todayInIndia();
    if (!DATE_PATTERN.test(date)) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        date: "give a date like 2026-10-02",
      });
    }
    const me = currentUser();
    const userId = url.searchParams.get("user_id") ?? me.id;
    const person = [me, ...teamOf(scope)].find((candidate) => candidate.id === userId);
    if (person === undefined) {
      return errorResponse(404, "not_found", "That person is not in your team.");
    }

    const [start, end] = dayBounds(date);
    const theirs =
      scenario === "empty" ? [] : mockDb.tasks.filter((task) => task.assigned_to?.id === person.id);
    const due = theirs.filter((task) => {
      const at = Date.parse(task.due_at);
      return at >= start && at < end;
    });
    // A future day has no overdue: a task is due that day or overdue, never both.
    const overdue =
      date > todayInIndia()
        ? []
        : theirs.filter((task) => {
            const at = Date.parse(task.due_at);
            return (
              task.status === "open" && at < start && at >= start - OVERDUE_LOOKBACK_DAYS * DAY_MS
            );
          });

    if (scenario === "contract") {
      return HttpResponse.json({ data: { date, due: "none" } });
    }
    const body: PlannerDayWire = {
      data: {
        date,
        user: person,
        due: due.map((task) => toWire(task)),
        overdue: overdue.map((task) => toWire(task)),
      },
    };
    return HttpResponse.json(body);
  }),

  /** TASK-002 · One row per person below the manager, people with no tasks included. */
  http.get(buildApiUrl("/planner/team"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const scope = taskScope();
    const team = teamOf(scope);
    if (team.length === 0) {
      return errorResponse(403, "forbidden", "You have no team.");
    }

    const date = new URL(request.url).searchParams.get("date") ?? todayInIndia();
    const [start, end] = dayBounds(date);
    const now = Date.now();
    const inDay = (value: string | null): boolean => {
      const at = value === null ? Number.NaN : Date.parse(value);
      return at >= start && at < end;
    };
    const body: TeamPageWire = {
      data:
        scenario === "empty"
          ? []
          : team.map((person) => {
              const theirs = mockDb.tasks.filter((task) => task.assigned_to?.id === person.id);
              return {
                user: person,
                org_unit_id: null,
                due_today: theirs.filter(
                  (task) => task.status !== "cancelled" && inDay(task.due_at),
                ).length,
                done_today: theirs.filter(
                  (task) => task.status === "done" && inDay(task.completed_at),
                ).length,
                overdue: theirs.filter(
                  (task) => task.status === "open" && Date.parse(task.due_at) < now,
                ).length,
              };
            }),
      meta: { limit: MAX_LIMIT, next_cursor: null },
    };
    return HttpResponse.json(body);
  }),

  /** TASK-004 · The user first, then the active staff below them. */
  http.get(buildApiUrl("/tasks/assignees"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const scope = taskScope();
    if (scope === null) return noTasksModule();
    return HttpResponse.json({ data: [currentUser(), ...teamOf(scope)] });
  }),

  /** TASK-003 · Tasks in the user's scope, earliest due first, filtered by lead or status. */
  http.get(buildApiUrl("/tasks"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const scope = taskScope();
    if (scope === null) return noTasksModule();

    const url = new URL(request.url);
    const limit = Math.min(
      MAX_LIMIT,
      Math.max(1, Number(url.searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT),
    );
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : decodeCursor(cursor);
    if (offset === null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        cursor: "malformed cursor",
      });
    }
    const matches = scenario === "empty" ? [] : filterTasks(url.searchParams, scope);
    const page = matches.slice(offset, offset + limit);
    const counted = url.searchParams.get("include_total") === "true";
    const body: TaskPageWire = {
      data: page.map((task) => toWire(task)),
      meta: {
        limit,
        next_cursor: offset + limit < matches.length ? encodeCursor(offset + limit) : null,
        total: counted ? matches.length : null,
      },
    };
    return HttpResponse.json(body);
  }),

  /** TASK-004 · A call, visit, meeting or follow-up, for the user or someone below them. */
  http.post(buildApiUrl("/tasks"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const scope = taskScope();
    if (scope === null) return noTasksModule();
    const key = idempotencyKeyOf(request);
    if (key instanceof Response) return key;

    const raw: unknown = await request.json();
    const serialized = JSON.stringify(raw);
    const replayed = replay(key, serialized);
    if (replayed !== null) return replayed;

    const parsed = createTaskRequestSchema.safeParse(raw);
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        fieldsOf(parsed.error),
      );
    }
    const body = parsed.data;
    const me = currentUser();
    const assignee = [me, ...teamOf(scope)].find(
      (person) => person.id === (body.assigned_to ?? me.id),
    );
    if (assignee === undefined) {
      return errorResponse(422, "not_assignable", "That person is not yours to assign to.", {
        assigned_to: "not assignable by you",
      });
    }
    const links = [body.lead_id, body.partner_id, body.sales_order_id].filter(
      (link) => link !== null && link !== undefined,
    );
    if (links.length > 1) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        lead_id: "a task hangs off one thing: a lead, a dealer or an order",
      });
    }
    const lead =
      body.lead_id === null || body.lead_id === undefined
        ? null
        : mockDb.leads.find((item) => item.id === body.lead_id);
    if (lead === undefined) {
      return errorResponse(404, "not_found", "No such lead.");
    }
    if (lead?.stage === "merged") {
      return errorResponse(422, "lead_merged", "That lead was merged into another.", {
        lead_id: "merged",
      });
    }
    const wantsType = body.task_type === "meeting" && lead !== null;
    const meetingType = mockLookupRows("meeting-types").find(
      (row) => row.id === body.meeting_type_id,
    );
    if (wantsType && meetingType === undefined) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        meeting_type_id: "required for a meeting on a lead",
      });
    }
    if (!wantsType && body.meeting_type_id !== null && body.meeting_type_id !== undefined) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        meeting_type_id: "only for a meeting on a lead",
      });
    }
    // A date alone is due at 18:00 in India.
    const due = DATE_PATTERN.test(body.due_at) ? `${body.due_at}T18:00:00+05:30` : body.due_at;
    if (Number.isNaN(Date.parse(due))) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        due_at: "give a date and time with a timezone",
      });
    }
    const partner = MOCK_PARTNERS.find((item) => item.id === body.partner_id);
    const created = new Date().toISOString();
    const task: MockTask = {
      id: mockUuid(MOCK_ID_SPACE.task, 0x1000 + mockDb.taskWrites.size + mockDb.tasks.length),
      title: body.title.trim(),
      task_type: body.task_type,
      status: "open",
      due_at: new Date(due).toISOString(),
      assigned_to: assignee,
      assigned_by: me,
      lead:
        lead === null
          ? null
          : {
              id: lead.id,
              hidden: false,
              inquiry_no: lead.inquiry_no,
              farmer_name: lead.farmer_name,
            },
      partner:
        partner === undefined
          ? null
          : {
              id: partner.id,
              hidden: false,
              name: partner.name,
              partner_type: partner.partner_type,
            },
      sales_order: null,
      meeting_type:
        wantsType && meetingType !== undefined
          ? { id: meetingType.id, code: meetingType.code, name: meetingType.name }
          : null,
      minutes_id: null,
      notes: body.notes?.trim() || null,
      outcome: null,
      gift_shown: null,
      cancel_reason: null,
      completed_at: null,
      completed_by: null,
      created_at: created,
      updated_at: created,
    };
    mockDb.tasks = [...mockDb.tasks, task].sort(
      (a, b) => a.due_at.localeCompare(b.due_at) || a.id.localeCompare(b.id),
    );
    mockDb.taskWrites.set(key, { body: serialized, taskId: task.id });
    return HttpResponse.json({ data: toWire(task) }, { status: 201 });
  }),

  /** TASK-008 · The list as a file, with the same filters. Before /tasks/:taskId. */
  http.get(buildApiUrl("/tasks/export"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const scope = taskScope();
    if (scope === null) return noTasksModule();
    const rows = filterTasks(new URL(request.url).searchParams, scope);
    if (rows.length > EXPORT_MAX_ROWS) {
      return errorResponse(422, "export_too_large", "More than 5000 rows: narrow the filters.");
    }
    // A stand-in for the workbook: one line per task, with the real file's headers.
    const lines = [
      "Title\tKind\tStatus\tDue\tFor",
      ...rows.map((task) =>
        [
          task.title,
          task.task_type,
          task.status,
          task.due_at,
          task.assigned_to?.full_name ?? "",
        ].join("\t"),
      ),
    ];
    return new HttpResponse(lines.join("\n"), {
      headers: {
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "content-disposition": `attachment; filename="tasks-${todayInIndia()}.xlsx"`,
      },
    });
  }),

  /** TASK-006 · An open task's title, due time or notes, or who does it. */
  http.patch(buildApiUrl("/tasks/:taskId"), async ({ request, params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const key = idempotencyKeyOf(request);
    if (key instanceof Response) return key;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ task: params.taskId, raw });
    const replayed = replay(key, serialized);
    if (replayed !== null) return replayed;
    const task = findTask(params.taskId);
    if (task instanceof Response) return task;

    const parsed = patchTaskRequestSchema.safeParse(raw);
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        fieldsOf(parsed.error),
      );
    }
    const body = parsed.data;
    if (body.expected_status !== undefined && body.expected_status !== task.status) {
      return errorResponse(409, "status_changed", `The task is now ${task.status}.`);
    }
    if (task.status !== "open") return notOpen(task, "open");
    let assignee = task.assigned_to;
    if (body.assigned_to !== undefined && body.assigned_to !== task.assigned_to?.id) {
      const scope = taskScope();
      const next = [currentUser(), ...teamOf(scope)].find(
        (person) => person.id === body.assigned_to,
      );
      if (next === undefined) {
        return errorResponse(422, "not_assignable", "That person is not yours to assign to.", {
          assigned_to: "not assignable by you",
        });
      }
      assignee = next;
    }
    const due =
      body.due_at === undefined
        ? task.due_at
        : new Date(
            DATE_PATTERN.test(body.due_at) ? `${body.due_at}T18:00:00+05:30` : body.due_at,
          ).toISOString();
    return saveTask(key, serialized, {
      ...task,
      title: body.title?.trim() ?? task.title,
      notes: body.notes === undefined ? task.notes : body.notes?.trim() || null,
      due_at: due,
      assigned_to: assignee,
      updated_at: new Date().toISOString(),
    });
  }),

  /** TASK-007 · A lead's minutes, newest first. Exactly one of lead_id and partner_id. */
  http.get(buildApiUrl("/minutes"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (taskScope() === null) return noTasksModule();
    const url = new URL(request.url);
    const leadId = url.searchParams.get("lead_id");
    const partnerId = url.searchParams.get("partner_id");
    if ((leadId === null) === (partnerId === null)) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        lead_id: "give lead_id or partner_id",
      });
    }
    const rows =
      scenario === "empty"
        ? []
        : mockDb.minutes
            .filter((minutes) =>
              leadId === null ? minutes.partner?.id === partnerId : minutes.lead?.id === leadId,
            )
            .sort((a, b) => b.held_at.localeCompare(a.held_at));
    return HttpResponse.json({ data: rows.map(minutesWire) });
  }),

  /**
   * TASK-007 · The minutes and a task per action item, in one save; one bad item refuses the
   * whole save with `fields.action_items.i…`. The meeting it records is completed if open.
   */
  http.post(buildApiUrl("/minutes"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const scope = taskScope();
    if (scope === null) return noTasksModule();
    const key = idempotencyKeyOf(request);
    if (key instanceof Response) return key;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify(raw);
    const earlier = mockDb.minutesWrites.get(key);
    if (earlier !== undefined) {
      const minutes = mockDb.minutes.find((item) => item.id === earlier.minutesId);
      if (earlier.body !== serialized) {
        return errorResponse(
          409,
          "idempotency_key_reused",
          "This Idempotency-Key was already used for a different request.",
        );
      }
      if (minutes !== undefined)
        return HttpResponse.json({ data: minutesWire(minutes) }, { status: 201 });
    }

    const parsed = createMinutesRequestSchema.safeParse(raw);
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        fieldsOf(parsed.error),
      );
    }
    const body = parsed.data;
    const lead = mockDb.leads.find((item) => item.id === body.lead_id);
    if (lead === undefined) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        lead_id: "give lead_id or partner_id",
      });
    }
    if (lead.stage === "merged") {
      return errorResponse(422, "lead_merged", "That lead was merged into another.", {
        lead_id: "merged",
      });
    }
    const me = currentUser();
    const people = [me, ...teamOf(scope)];
    const fields: Record<string, string> = {};
    body.action_items.forEach((item, index) => {
      if (item.assigned_to && !people.some((person) => person.id === item.assigned_to)) {
        fields[`action_items.${String(index)}.assigned_to`] = "not assignable by you";
      }
      const due = DATE_PATTERN.test(item.due_at) ? `${item.due_at}T18:00:00+05:30` : item.due_at;
      if (Number.isNaN(Date.parse(due))) {
        fields[`action_items.${String(index)}.due_at`] = "give a date and time with a timezone";
      }
    });
    if (Object.keys(fields).length > 0) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
    }
    const meeting = body.task_id
      ? mockDb.tasks.find((task) => task.id === body.task_id)
      : undefined;
    if (body.task_id && meeting === undefined) {
      return errorResponse(404, "not_found", "No such task.");
    }
    if (meeting !== undefined) {
      if (meeting.lead?.id !== lead.id) {
        return errorResponse(422, "task_link_mismatch", "That task is on something else.", {
          task_id: "on another lead",
        });
      }
      if (meeting.task_type !== "meeting") {
        return errorResponse(422, "task_not_a_meeting", "That task is not a meeting.", {
          task_id: "not a meeting",
        });
      }
      if (meeting.status === "cancelled") {
        return errorResponse(409, "task_not_open", "That task was cancelled.");
      }
    }

    const now = new Date().toISOString();
    const minutesId = mockUuid(MOCK_ID_SPACE.task, 0x8000 + mockDb.minutes.length + 1);
    const leadLink = {
      id: lead.id,
      hidden: false,
      inquiry_no: lead.inquiry_no,
      farmer_name: lead.farmer_name,
    };
    const actionTasks: MockTask[] = body.action_items.map((item, index) => {
      const assignee = people.find((person) => person.id === item.assigned_to) ?? me;
      const due = DATE_PATTERN.test(item.due_at) ? `${item.due_at}T18:00:00+05:30` : item.due_at;
      return {
        id: mockUuid(MOCK_ID_SPACE.task, 0x9000 + mockDb.tasks.length + index),
        title: item.title.trim(),
        task_type: item.task_type ?? "followup",
        status: "open",
        due_at: new Date(due).toISOString(),
        assigned_to: assignee,
        assigned_by: me,
        lead: leadLink,
        partner: null,
        sales_order: null,
        meeting_type: null,
        minutes_id: minutesId,
        notes: null,
        outcome: null,
        gift_shown: null,
        cancel_reason: null,
        completed_at: null,
        completed_by: null,
        created_at: now,
        updated_at: now,
      };
    });
    mockDb.tasks = [...mockDb.tasks, ...actionTasks]
      .map((task) =>
        meeting !== undefined && task.id === meeting.id && task.status === "open"
          ? {
              ...task,
              status: "done" as const,
              outcome: "Minutes recorded",
              completed_at: now,
              completed_by: me,
              updated_at: now,
            }
          : task,
      )
      .sort((a, b) => a.due_at.localeCompare(b.due_at) || a.id.localeCompare(b.id));
    const minutes: MockMinutes = {
      id: minutesId,
      lead: leadLink,
      partner: null,
      task_id: body.task_id ?? null,
      held_at: new Date(body.held_at).toISOString(),
      attendees: body.attendees.map((name) => name.trim()).filter((name) => name !== ""),
      notes: body.notes.trim(),
      created_by: me,
      created_at: now,
      action_item_ids: actionTasks.map((task) => task.id),
    };
    mockDb.minutes = [minutes, ...mockDb.minutes];
    mockDb.minutesWrites.set(key, { body: serialized, minutesId });
    return HttpResponse.json({ data: minutesWire(minutes) }, { status: 201 });
  }),

  http.get(buildApiUrl("/tasks/:taskId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const task = findTask(params.taskId);
    return task instanceof Response ? task : HttpResponse.json({ data: toWire(task) });
  }),

  /** TASK-005 · Done, with what happened. `gift_shown` on a meeting only. */
  http.post(buildApiUrl("/tasks/:taskId/complete"), async ({ request, params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const key = idempotencyKeyOf(request);
    if (key instanceof Response) return key;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ task: params.taskId, raw });
    const replayed = replay(key, serialized);
    if (replayed !== null) return replayed;
    const task = findTask(params.taskId);
    if (task instanceof Response) return task;

    const parsed = completeTaskRequestSchema.safeParse(raw);
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        fieldsOf(parsed.error),
      );
    }
    if (task.status !== "open") return notOpen(task, "open");
    if (
      parsed.data.gift_shown !== null &&
      parsed.data.gift_shown !== undefined &&
      task.task_type !== "meeting"
    ) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        gift_shown: "meetings only",
      });
    }
    const now = new Date().toISOString();
    const me = currentUser();
    return saveTask(key, serialized, {
      ...task,
      status: "done",
      outcome: parsed.data.outcome.trim(),
      gift_shown: parsed.data.gift_shown ?? null,
      completed_at: now,
      completed_by: me,
      updated_at: now,
    });
  }),

  /** TASK-005 · Cancel with a reason. An officer cannot cancel a task a manager gave them. */
  http.post(buildApiUrl("/tasks/:taskId/cancel"), async ({ request, params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const key = idempotencyKeyOf(request);
    if (key instanceof Response) return key;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ task: params.taskId, raw });
    const replayed = replay(key, serialized);
    if (replayed !== null) return replayed;
    const task = findTask(params.taskId);
    if (task instanceof Response) return task;

    const parsed = cancelTaskRequestSchema.safeParse(raw);
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        fieldsOf(parsed.error),
      );
    }
    if (task.status !== "open") return notOpen(task, "open");
    const me = currentUser();
    if (task.assigned_to?.id === me.id && task.assigned_by?.id !== me.id) {
      return errorResponse(403, "forbidden", "Only whoever gave you this task can cancel it.");
    }
    return saveTask(key, serialized, {
      ...task,
      status: "cancelled",
      cancel_reason: parsed.data.reason.trim(),
      updated_at: new Date().toISOString(),
    });
  }),

  /** TASK-005 · Reopen a done task, within 7 days, by its assignee or whoever gave it. */
  http.post(buildApiUrl("/tasks/:taskId/reopen"), async ({ request, params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const key = idempotencyKeyOf(request);
    if (key instanceof Response) return key;
    const serialized = JSON.stringify({ task: params.taskId });
    const replayed = replay(key, serialized);
    if (replayed !== null) return replayed;
    const task = findTask(params.taskId);
    if (task instanceof Response) return task;

    if (task.status !== "done") return notOpen(task, "done");
    const me = currentUser();
    if (task.assigned_to?.id !== me.id && task.assigned_by?.id !== me.id) {
      return errorResponse(403, "forbidden", "The assignee or whoever gave the task reopens it.");
    }
    const completed = task.completed_at === null ? 0 : Date.parse(task.completed_at);
    if (Date.now() - completed > TASK_REOPEN_DAYS * DAY_MS) {
      return errorResponse(
        409,
        "reopen_window_passed",
        "Done more than 7 days ago: raise a new task.",
      );
    }
    return saveTask(key, serialized, {
      ...task,
      status: "open",
      outcome: null,
      gift_shown: null,
      completed_at: null,
      completed_by: null,
      updated_at: new Date().toISOString(),
    });
  }),
];
