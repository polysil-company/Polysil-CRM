import { z } from "zod";

import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";

/**
 * Tasks and the planner (TASK-001…005), from the backend's `Task`, `PlannerDay`, `TeamPage`,
 * `TaskCreate`, `TaskComplete` and `TaskCancel` (backend/docs/api/tasks.md, and the handover
 * backend/docs/handover/tasks-and-planner-contract.md). Days are Indian calendar days.
 */

export const TASK_TYPES = ["call", "visit", "meeting", "followup", "other"] as const;
export type TaskType = (typeof TASK_TYPES)[number];

export const TASK_STATUSES = ["open", "done", "cancelled"] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];

/** The backend's limits (backend/api/domain/tasks.py). */
export const TASK_TITLE_MAX = 200;
export const TASK_TEXT_MAX = 2000;
/** A done task can be reopened for this many days; after that, raise a new one. */
export const TASK_REOPEN_DAYS = 7;
/** A due date given without a time is due at this time of day in India. */
export const DEFAULT_DUE_TIME = "18:00";

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;
const isoDateTime = z.iso.datetime({ offset: true });
const id = z.string().min(1);

const userRefSchema = z
  .object({ id, full_name: z.string() })
  .transform((user) => ({ id: user.id, name: user.full_name.trim() || "Unnamed" }));

/** A link the caller can no longer open reads `{ id, hidden: true }`, its other fields null. */
const leadLinkSchema = z
  .object({
    id,
    hidden: z.boolean().optional(),
    inquiry_no: z.string().nullish(),
    farmer_name: z.string().nullish(),
  })
  .transform((lead) => ({
    id: lead.id,
    hidden: lead.hidden ?? false,
    inquiryNo: lead.inquiry_no ?? null,
    farmerName: lead.farmer_name?.trim() || null,
  }));

const partnerLinkSchema = z
  .object({
    id,
    hidden: z.boolean().optional(),
    name: z.string().nullish(),
    partner_type: z.string().nullish(),
  })
  .transform((partner) => ({
    id: partner.id,
    hidden: partner.hidden ?? false,
    name: partner.name?.trim() || null,
    partnerType: partner.partner_type ?? null,
  }));

const orderLinkSchema = z
  .object({ id, hidden: z.boolean().optional(), order_no: z.string().nullish() })
  .transform((order) => ({
    id: order.id,
    hidden: order.hidden ?? false,
    orderNo: order.order_no ?? null,
  }));

const taskWireSchema = z.object({
  id,
  title: z.string(),
  task_type: z.enum(TASK_TYPES),
  status: z.enum(TASK_STATUSES),
  /** Open and past its due time — the server's word; never computed on the screen. */
  overdue: z.boolean(),
  due_at: isoDateTime,
  assigned_to: userRefSchema.nullable(),
  assigned_by: userRefSchema.nullable(),
  lead: leadLinkSchema.nullable(),
  partner: partnerLinkSchema.nullable(),
  sales_order: orderLinkSchema.nullable(),
  meeting_type: z.object({ id, code: z.string(), name: z.string() }).nullable(),
  minutes_id: z.string().nullable(),
  notes: z.string().nullable(),
  outcome: z.string().nullable(),
  gift_shown: z.boolean().nullable(),
  cancel_reason: z.string().nullable(),
  completed_at: isoDateTime.nullable(),
  completed_by: userRefSchema.nullable(),
  created_at: isoDateTime,
  updated_at: isoDateTime,
});

/** The backend's JSON for one task, as the mock backend must produce it. */
export type TaskWire = z.input<typeof taskWireSchema>;

export const taskSchema = taskWireSchema.transform((wire) => ({
  id: wire.id,
  title: wire.title.trim() || "Untitled task",
  type: wire.task_type,
  status: wire.status,
  overdue: wire.overdue,
  dueAt: wire.due_at,
  assignedTo: wire.assigned_to,
  assignedBy: wire.assigned_by,
  lead: wire.lead,
  partner: wire.partner,
  salesOrder: wire.sales_order,
  meetingType: wire.meeting_type,
  minutesId: wire.minutes_id,
  notes: wire.notes?.trim() || null,
  outcome: wire.outcome?.trim() || null,
  giftShown: wire.gift_shown,
  cancelReason: wire.cancel_reason?.trim() || null,
  completedAt: wire.completed_at,
  completedBy: wire.completed_by,
  createdAt: wire.created_at,
}));

export type Task = z.output<typeof taskSchema>;

export const taskResponseSchema = z.object({ data: taskSchema }).transform(({ data }) => data);

/** GET /tasks — one row at a time, so one odd task never blanks a lead's list. */
export const taskPageSchema = cursorPageSchema(taskSchema);
export type TaskPage = CursorPage<Task>;
export type TaskPageWire = { data: TaskWire[]; meta: PageMetaWire };

/** Tasks a page of GET /tasks asks for. */
export const TASK_PAGE_SIZE = 25;

export interface TaskListParams {
  readonly leadId: string;
}

/** GET /planner — one person's day: due that day, by time, and open tasks overdue before it. */
export const plannerDaySchema = z
  .object({
    data: z.object({
      date: z.string().regex(DATE_PATTERN),
      user: userRefSchema.nullable(),
      due: z.array(taskSchema),
      overdue: z.array(taskSchema),
    }),
  })
  .transform(({ data }) => data);

export type PlannerDay = z.output<typeof plannerDaySchema>;
export type PlannerDayWire = z.input<typeof plannerDaySchema>;

export interface PlannerParams {
  /** An Indian calendar day, `YYYY-MM-DD`. */
  readonly date: string;
  /** Someone below the user; null for the user's own day. */
  readonly userId: string | null;
}

const teamRowWireSchema = z.object({
  user: userRefSchema,
  org_unit_id: z.string().nullable(),
  due_today: z.number().int().nonnegative(),
  done_today: z.number().int().nonnegative(),
  overdue: z.number().int().nonnegative(),
});

export type TeamRowWire = z.input<typeof teamRowWireSchema>;

const teamRowSchema = teamRowWireSchema.transform((wire) => ({
  user: wire.user,
  dueToday: wire.due_today,
  doneToday: wire.done_today,
  overdue: wire.overdue,
}));

export type TeamRow = z.output<typeof teamRowSchema>;

/** GET /planner/team — one row per active person below the manager, 100 a page. */
export const teamPageSchema = cursorPageSchema(teamRowSchema);
export type TeamPage = CursorPage<TeamRow>;
export type TeamPageWire = { data: TeamRowWire[]; meta: PageMetaWire };

/** GET /tasks/assignees — the user first, then the active staff below them. */
export const taskAssigneesSchema = z
  .object({ data: z.array(userRefSchema) })
  .transform(({ data }) => data);

export type TaskAssignee = z.output<typeof taskAssigneesSchema>[number];

// ---------------------------------------------------------------------------------------------
// Requests

/** POST /tasks. At most one of the three links; a meeting on a lead carries a meeting type. */
export const createTaskRequestSchema = z.object({
  title: z.string().min(1).max(TASK_TITLE_MAX),
  task_type: z.enum(TASK_TYPES),
  /** With a timezone, or a date alone (due at 18:00 IST). */
  due_at: z.string().min(1),
  assigned_to: z.string().nullish(),
  lead_id: z.string().nullish(),
  partner_id: z.string().nullish(),
  sales_order_id: z.string().nullish(),
  meeting_type_id: z.string().nullish(),
  notes: z.string().max(TASK_TEXT_MAX).nullish(),
});

export type CreateTaskRequest = z.infer<typeof createTaskRequestSchema>;

export const completeTaskRequestSchema = z.object({
  outcome: z.string().min(1).max(TASK_TEXT_MAX),
  gift_shown: z.boolean().nullish(),
});

export type CompleteTaskRequest = z.infer<typeof completeTaskRequestSchema>;

export const cancelTaskRequestSchema = z.object({
  reason: z.string().min(1).max(TASK_TEXT_MAX),
});

export type CancelTaskRequest = z.infer<typeof cancelTaskRequestSchema>;

// ---------------------------------------------------------------------------------------------
// Forms

/** What a task is about, fixed by where the form was opened (a lead's page). */
export interface TaskSubject {
  readonly leadId: string;
  readonly label: string;
}

/** The task form's fields, as the inputs hold them. */
export interface TaskFormValues {
  title: string;
  type: TaskType;
  /** `YYYY-MM-DD`. */
  dueDate: string;
  /** `HH:MM`, or empty for the backend's default. */
  dueTime: string;
  assignedTo: string;
  /** Empty unless it is a meeting about a lead. */
  meetingTypeId: string;
  notes: string;
}

/**
 * The task form. The due time is optional: without one the backend makes it 18:00 in India.
 * A meeting about a lead needs a meeting type; anywhere else it takes none.
 */
export function taskFormSchema(
  subject: TaskSubject | null,
): z.ZodType<CreateTaskRequest, TaskFormValues> {
  return z
    .object({
      title: z
        .string()
        .trim()
        .min(1, "Say what is to be done.")
        .max(TASK_TITLE_MAX, `Keep it under ${String(TASK_TITLE_MAX)} characters.`),
      type: z.enum(TASK_TYPES, "Choose what kind of task it is."),
      dueDate: z.string().regex(DATE_PATTERN, "Choose the day it is due."),
      dueTime: z.union([z.literal(""), z.string().regex(TIME_PATTERN, "Enter a time like 10:30.")]),
      assignedTo: z.string().min(1, "Choose who does it."),
      meetingTypeId: z.string(),
      notes: z
        .string()
        .trim()
        .max(TASK_TEXT_MAX, `Keep notes under ${String(TASK_TEXT_MAX)} characters.`),
    })
    .superRefine((values, ctx) => {
      if (subject !== null && values.type === "meeting" && values.meetingTypeId === "") {
        ctx.addIssue({
          code: "custom",
          path: ["meetingTypeId"],
          message: "Choose the kind of meeting.",
        });
      }
    })
    .transform((values): CreateTaskRequest => ({
      title: values.title,
      task_type: values.type,
      due_at:
        values.dueTime === "" ? values.dueDate : `${values.dueDate}T${values.dueTime}:00+05:30`,
      assigned_to: values.assignedTo,
      lead_id: subject?.leadId ?? null,
      meeting_type_id:
        subject !== null && values.type === "meeting" && values.meetingTypeId !== ""
          ? values.meetingTypeId
          : null,
      notes: values.notes === "" ? null : values.notes,
    }));
}
