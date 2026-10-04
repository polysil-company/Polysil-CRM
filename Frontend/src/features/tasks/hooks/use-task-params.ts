"use client";

import { createParser, parseAsStringLiteral, useQueryStates } from "nuqs";

import { useSession } from "@/features/session/hooks/use-session";

export const TASK_VIEWS = ["day", "team"] as const;
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

export interface TaskParams {
  readonly view: TaskView;
  /** The day looked at; null for today. */
  readonly date: string | null;
  /** Someone below the user whose day is open; null for the user's own. */
  readonly userId: string | null;
}

/**
 * TASK-001 · The Tasks page's place in the URL: the view (`?view=team`), the day
 * (`?date=2026-10-03`, today when absent) and whose day (`?user=`), so a manager can send a
 * link to someone's Tuesday.
 */
export function useTaskParams(): {
  params: TaskParams;
  setParams: (patch: Partial<TaskParams>) => void;
} {
  const [values, setValues] = useQueryStates({
    view: parseAsStringLiteral(TASK_VIEWS).withDefault("day"),
    date: parseAsCalendarDay,
    user: parseAsUserId,
  });

  return {
    params: { view: values.view, date: values.date, userId: values.user },
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
