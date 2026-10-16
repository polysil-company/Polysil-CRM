"use client";

import {
  createParser,
  parseAsArrayOf,
  parseAsBoolean,
  parseAsStringLiteral,
  useQueryStates,
} from "nuqs";

import { useSession } from "@/features/session/hooks/use-session";
import {
  TASK_STATUSES,
  TASK_TYPES,
  type TaskListParams,
  type TaskStatus,
  type TaskType,
} from "@/features/tasks/api/tasks.schemas";

export const TASK_VIEWS = ["day", "team", "all"] as const;
export type TaskView = (typeof TASK_VIEWS)[number];

const DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const USER_ID_PATTERN = /^[\w-]{1,64}$/;

const parseAsCalendarDay = createParser({
  parse: (value: string) => (DAY_PATTERN.test(value) ? value : null),
  serialize: (value: string) => value,
});

const parseAsUserId = createParser({
  parse: (value: string) => (USER_ID_PATTERN.test(value) ? value : null),
  serialize: (value: string) => value,
});

/** The All tasks view's filters, as the URL keeps them. */
export interface TaskFilters {
  readonly status: readonly TaskStatus[];
  readonly type: TaskType | null;
  /** `me`, someone's id, or null for everyone the user can see. */
  readonly assignedTo: string | null;
  readonly overdue: boolean;
}

export interface TaskParams {
  readonly view: TaskView;
  /** The day looked at; null for today. */
  readonly date: string | null;
  /** Someone below the user whose day is open; null for the user's own. */
  readonly userId: string | null;
  readonly filters: TaskFilters;
}

/** The filters as GET /tasks takes them. */
export function taskListParamsOf(filters: TaskFilters): TaskListParams {
  return { leadId: null, ...filters };
}

/**
 * TASK-001 · The Tasks page's place in the URL: the view (`?view=team`, `?view=all`), the
 * day (`?date=2026-10-03`, today when absent), whose day (`?user=`) — so a manager can send a
 * link to someone's Tuesday — and the All tasks filters (`?status=`, `?type=`, `?who=`,
 * `?overdue=true`).
 */
export function useTaskParams(): {
  params: TaskParams;
  setParams: (patch: Partial<Omit<TaskParams, "filters">>) => void;
  setFilters: (patch: Partial<TaskFilters>) => void;
  resetFilters: () => void;
} {
  const [values, setValues] = useQueryStates({
    view: parseAsStringLiteral(TASK_VIEWS).withDefault("day"),
    date: parseAsCalendarDay,
    user: parseAsUserId,
    status: parseAsArrayOf(parseAsStringLiteral(TASK_STATUSES)).withDefault([]),
    type: parseAsStringLiteral(TASK_TYPES),
    who: parseAsUserId,
    overdue: parseAsBoolean.withDefault(false),
  });

  return {
    params: {
      view: values.view,
      date: values.date,
      userId: values.user,
      filters: {
        status: [...new Set(values.status)],
        type: values.type,
        assignedTo: values.who,
        overdue: values.overdue,
      },
    },
    setFilters: (patch) => {
      void setValues({
        ...(patch.status === undefined
          ? {}
          : { status: patch.status.length === 0 ? null : [...patch.status] }),
        ...(patch.type === undefined ? {} : { type: patch.type }),
        ...(patch.assignedTo === undefined ? {} : { who: patch.assignedTo }),
        ...(patch.overdue === undefined ? {} : { overdue: patch.overdue ? true : null }),
      });
    },
    resetFilters: () => {
      void setValues({ status: null, type: null, who: null, overdue: null });
    },
    setParams: (patch) => {
      void setValues({
        ...(patch.view === undefined ? {} : { view: patch.view === "day" ? null : patch.view }),
        ...(patch.date === undefined ? {} : { date: patch.date }),
        ...(patch.userId === undefined ? {} : { user: patch.userId }),
      });
    },
  };
}

/**
 * Whether the user has people below them: a `tasks` grant wider than their own. Managers and
 * admins do; officers, Accounts, Dispatch and QA don't. GET /planner/team is a 403 otherwise.
 */
export function useHasTeam(): boolean {
  const { data } = useSession();
  const scope = data?.permissions.find((permission) => permission.module === "tasks")?.scope;
  return scope !== undefined && scope !== null && scope !== "own";
}
