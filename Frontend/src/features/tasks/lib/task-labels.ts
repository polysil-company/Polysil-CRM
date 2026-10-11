import {
  Agreement01Icon,
  CallIcon,
  Location01Icon,
  Note01Icon,
  RepeatIcon,
} from "@hugeicons/core-free-icons";

import type { IconGlyph } from "@/components/ui/icon";
import type { Task, TaskType } from "@/features/tasks/api/tasks.schemas";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";

export const TASK_TYPE_LABELS: Readonly<Record<TaskType, string>> = {
  call: "Call",
  visit: "Visit",
  meeting: "Meeting",
  followup: "Follow-up",
  other: "Other",
};

export const TASK_TYPE_ICONS: Readonly<Record<TaskType, IconGlyph>> = {
  call: CallIcon,
  visit: Location01Icon,
  meeting: Agreement01Icon,
  followup: RepeatIcon,
  other: Note01Icon,
};

/** What the task is about, in a few words, or null for a task about nothing in particular. */
export function taskSubjectLabel(task: Task): string | null {
  if (task.lead !== null) {
    if (task.lead.hidden) return "Lead not visible to you";
    return [task.lead.farmerName, task.lead.inquiryNo].filter(Boolean).join(" · ") || "A lead";
  }
  if (task.partner !== null) {
    return task.partner.hidden ? "Dealer not visible to you" : (task.partner.name ?? "A dealer");
  }
  if (task.salesOrder !== null) {
    return task.salesOrder.hidden
      ? "Order not visible to you"
      : (task.salesOrder.orderNo ?? "A draft order");
  }
  return null;
}

/** How a refused task action reads, and whether the screen should just refresh. */
export interface TaskRefusal {
  readonly title: string;
  readonly message: string;
  /** The task moved on (done, cancelled or reopened elsewhere): close and show the latest. */
  readonly stale: boolean;
  /** A field the backend named, with its reason. */
  readonly fields: Readonly<Record<string, string>> | null;
}

/**
 * The backend's task refusals in plain words: `task_not_open` and `task_not_done` (someone
 * moved it on), `reopen_window_passed`, a cancel the officer may not make (403), and the
 * create rules (`not_assignable`, `link_not_visible_to_assignee`, `lead_merged`).
 */
export function taskRefusal(error: unknown): TaskRefusal {
  const fields = readFieldErrors(error);
  if (isApiError(error)) {
    switch (error.code) {
      case "task_not_open":
      case "task_not_done":
      case "status_changed":
        return {
          title: "This task changed",
          message: "Someone else updated it meanwhile. The list now shows where it stands.",
          stale: true,
          fields: null,
        };
      case "reopen_window_passed":
        return {
          title: "Too late to reopen",
          message: "It was done more than 7 days ago. Add a new task instead.",
          stale: false,
          fields: null,
        };
      case "link_not_visible_to_assignee":
        return {
          title: "They can't open this lead",
          message: "Choose someone who works this lead's area, or give it to yourself.",
          stale: false,
          fields: { assigned_to: "can't open the lead this task is about" },
        };
      case "lead_merged":
      case "lead_deleted":
        return {
          title: "This lead is gone",
          message: "It was merged into another lead or deleted. Add the task there.",
          stale: false,
          fields: null,
        };
      default:
        break;
    }
    if (error.status === 403) {
      return {
        title: "Not yours to change",
        message: "Only whoever gave you this task can cancel it. Ask them, or mark it done.",
        stale: false,
        fields: null,
      };
    }
  }
  const view = toUserFacingError(error);
  return { title: view.title, message: view.description, stale: false, fields };
}
