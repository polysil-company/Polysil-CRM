import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockLookupRows } from "@/mocks/data/lookups";
import { MOCK_TASK_ME, MOCK_TEAM } from "@/mocks/data/tasks";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

import {
  cancelTask,
  completeTask,
  createTask,
  getPlannerDay,
  getTeamDay,
  listTaskAssignees,
  listTasks,
  reopenTask,
} from "./tasks.api";
import { taskFormSchema, type TaskFormValues } from "./tasks.schemas";

const TODAY = todayInIndia();

function anOpenTaskOf(userId: string): string {
  const task = mockDb.tasks.find(
    (item) => item.status === "open" && item.assigned_to?.id === userId,
  );
  if (task === undefined) throw new Error("No open task in the mock");
  return task.id;
}

const FORM: TaskFormValues = {
  title: "  Call Ramesh about the quotation ",
  type: "call",
  dueDate: "2026-10-05",
  dueTime: "",
  assignedTo: MOCK_TASK_ME.id,
  meetingTypeId: "",
  notes: "",
};

/** Each test starts from the seed, as the admin. */
function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[TASK-001] getPlannerDay", () => {
  afterEach(reset);

  it("returns the user's day: due today by time, and what is overdue from before", async () => {
    const day = await getPlannerDay({ date: TODAY, userId: null });

    expect(day.date).toBe(TODAY);
    expect(day.user).toEqual({ id: MOCK_TASK_ME.id, name: MOCK_TASK_ME.full_name });
    expect(day.due.length).toBeGreaterThanOrEqual(6);
    const times = day.due.map((task) => task.dueAt);
    expect(times).toEqual([...times].sort());
    expect(day.overdue.length).toBeGreaterThanOrEqual(3);
    expect(day.overdue.every((task) => task.status === "open" && task.overdue)).toBe(true);
  });

  it("has nothing overdue on a future day", async () => {
    const day = await getPlannerDay({ date: "2099-01-01", userId: null });

    expect(day.overdue).toEqual([]);
  });

  it("opens the day of someone below a manager", async () => {
    const person = MOCK_TEAM[1];
    const day = await getPlannerDay({ date: TODAY, userId: person?.id ?? null });

    expect(day.user?.name).toBe(person?.full_name);
  });

  it("reports a day that breaks the contract", async () => {
    server.use(http.get(buildApiUrl("/planner"), () => HttpResponse.json({ data: { due: 1 } })));

    await expect(getPlannerDay({ date: TODAY, userId: null })).rejects.toMatchObject({
      kind: "contract",
    });
  });
});

describe("[TASK-002] getTeamDay", () => {
  afterEach(reset);

  it("lists each person below the manager with due, done and overdue counts", async () => {
    const page = await getTeamDay({ date: TODAY, cursor: null });

    expect(page.items.map((row) => row.user.name)).toEqual(
      MOCK_TEAM.map((person) => person.full_name),
    );
    expect(page.items.every((row) => row.dueToday >= 0 && row.overdue >= 0)).toBe(true);
  });

  it("is refused for someone with no team", async () => {
    writeMockRole("employee");

    await expect(getTeamDay({ date: TODAY, cursor: null })).rejects.toMatchObject({
      status: 403,
    });
  });
});

describe("[TASK-003] listTasks", () => {
  afterEach(reset);

  it("lists a lead's tasks, earliest due first, with the total", async () => {
    const leadId = mockDb.tasks.find((task) => task.lead !== null)?.lead?.id ?? "";

    const page = await listTasks({ leadId, cursor: null });

    expect(page.items.length).toBeGreaterThan(0);
    expect(page.items.every((task) => task.lead?.id === leadId)).toBe(true);
    expect(page.total).toBe(page.items.length);
  });

  it("reads a link the user can no longer open as hidden", async () => {
    server.use(
      http.get(buildApiUrl("/tasks"), () => {
        const task = mockDb.tasks[0];
        return HttpResponse.json({
          data: [{ ...task, overdue: false, lead: { id: "l-1", hidden: true } }],
          meta: { limit: 25, next_cursor: null, total: 1 },
        });
      }),
    );

    const page = await listTasks({ leadId: "x", cursor: null });

    expect(page.items[0]?.lead).toEqual({
      id: "l-1",
      hidden: true,
      inquiryNo: null,
      farmerName: null,
    });
  });
});

describe("[TASK-004] createTask", () => {
  afterEach(reset);

  it("offers the user first, then the people below them", async () => {
    const people = await listTaskAssignees();

    expect(people[0]).toEqual({ id: MOCK_TASK_ME.id, name: MOCK_TASK_ME.full_name });
    expect(people).toHaveLength(1 + MOCK_TEAM.length);
  });

  it("offers an officer only themselves", async () => {
    writeMockRole("employee");

    await expect(listTaskAssignees()).resolves.toHaveLength(1);
  });

  it("turns the form into the request: a date alone, or a date and time in India", () => {
    const schema = taskFormSchema(null);

    expect(schema.parse(FORM)).toEqual({
      title: "Call Ramesh about the quotation",
      task_type: "call",
      due_at: "2026-10-05",
      assigned_to: MOCK_TASK_ME.id,
      lead_id: null,
      meeting_type_id: null,
      notes: null,
    });
    expect(schema.parse({ ...FORM, dueTime: "10:30" }).due_at).toBe("2026-10-05T10:30:00+05:30");
  });

  it("asks for the kind of meeting on a lead, and sends none elsewhere", () => {
    const onLead = taskFormSchema({ leadId: "lead-1", label: "Ramesh" });
    const result = onLead.safeParse({ ...FORM, type: "meeting" });

    expect(result.success).toBe(false);
    expect(result.error?.issues[0]).toMatchObject({
      path: ["meetingTypeId"],
      message: "Choose the kind of meeting.",
    });
    expect(
      taskFormSchema(null).parse({ ...FORM, type: "meeting", meetingTypeId: "m-1" })
        .meeting_type_id,
    ).toBeNull();
  });

  it("creates a meeting on a lead that shows on the lead and in the day", async () => {
    const lead = mockDb.leads.find((item) => item.stage !== "merged");
    const meetingType = mockLookupRows("meeting-types")[1];
    const body = taskFormSchema({ leadId: lead?.id ?? "", label: "lead" }).parse({
      ...FORM,
      title: "Survey the farm",
      type: "meeting",
      dueDate: TODAY,
      dueTime: "23:30",
      meetingTypeId: meetingType?.id ?? "",
    });

    const task = await createTask({ body, idempotencyKey: "t-1" });

    expect(task).toMatchObject({
      title: "Survey the farm",
      type: "meeting",
      status: "open",
      meetingType: { name: "Survey & Design" },
      lead: { id: lead?.id },
      assignedBy: { id: MOCK_TASK_ME.id },
    });
    const day = await getPlannerDay({ date: TODAY, userId: null });
    expect(day.due.map((item) => item.id)).toContain(task.id);
    const onLead = await listTasks({ leadId: lead?.id ?? "", cursor: null });
    expect(onLead.items.map((item) => item.id)).toContain(task.id);
  });

  it("replays a retry with the same key instead of creating a second task", async () => {
    const body = taskFormSchema(null).parse(FORM);
    const before = mockDb.tasks.length;

    const first = await createTask({ body, idempotencyKey: "t-2" });
    const again = await createTask({ body, idempotencyKey: "t-2" });

    expect(again.id).toBe(first.id);
    expect(mockDb.tasks).toHaveLength(before + 1);
  });

  it("puts a person the user may not assign on the assignee field", async () => {
    writeMockRole("employee");
    const body = taskFormSchema(null).parse({ ...FORM, assignedTo: MOCK_TEAM[0]?.id ?? "" });

    const error: unknown = await createTask({ body, idempotencyKey: "t-3" }).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: "not_assignable",
      details: { fields: { assigned_to: expect.any(String) } },
    });
  });
});

describe("[TASK-005] complete, cancel and reopen", () => {
  afterEach(reset);

  it("completes a task with what happened, then reopens it", async () => {
    const taskId = anOpenTaskOf(MOCK_TASK_ME.id);

    const done = await completeTask({
      taskId,
      body: { outcome: "Spoke to him." },
      idempotencyKey: "c-1",
    });
    expect(done).toMatchObject({ status: "done", outcome: "Spoke to him.", overdue: false });

    const reopened = await reopenTask({ taskId, idempotencyKey: "r-1" });
    expect(reopened).toMatchObject({ status: "open", outcome: null });
  });

  it("refuses completing a task that is no longer open", async () => {
    const taskId = anOpenTaskOf(MOCK_TASK_ME.id);
    await completeTask({ taskId, body: { outcome: "Done." }, idempotencyKey: "c-2" });

    await expect(
      completeTask({ taskId, body: { outcome: "Done again." }, idempotencyKey: "c-3" }),
    ).rejects.toMatchObject({ status: 409, code: "task_not_open" });
  });

  it("cancels a task the manager gave, with the reason", async () => {
    const taskId = anOpenTaskOf(MOCK_TEAM[0]?.id ?? "");

    const cancelled = await cancelTask({
      taskId,
      body: { reason: "The farmer bought elsewhere." },
      idempotencyKey: "x-1",
    });

    expect(cancelled).toMatchObject({
      status: "cancelled",
      cancelReason: "The farmer bought elsewhere.",
    });
  });

  it("refuses an officer cancelling a task someone else gave them", async () => {
    const given = mockDb.tasks.find(
      (task) =>
        task.status === "open" &&
        task.assigned_to?.id === MOCK_TASK_ME.id &&
        task.assigned_by?.id !== MOCK_TASK_ME.id,
    );
    if (given === undefined) throw new Error("No task given to the user by someone else");

    await expect(
      cancelTask({ taskId: given.id, body: { reason: "Not needed." }, idempotencyKey: "x-2" }),
    ).rejects.toMatchObject({ status: 403 });
  });
});
