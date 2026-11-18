"use client";

import { Calendar03Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Skeleton } from "@/components/ui/skeleton";
import { plannerDayQueryOptions } from "@/features/tasks/api/tasks.queries";
import type { PlannerDay as PlannerDayData, Task } from "@/features/tasks/api/tasks.schemas";
import { formatCalendarDay } from "@/lib/format";

import type { PendingTaskAction } from "./task-action-dialog";
import { TaskRow } from "./task-row";

const SKELETON_ROWS = 4;

export interface PlannerDayProps {
  /** The day, `YYYY-MM-DD`. */
  date: string;
  /** Today in India, to say "today" rather than the date. */
  today: string;
  /** Someone below the user; null for the user's own day. */
  userId: string | null;
  meId: string | null;
  canEdit: boolean;
  onAction: (action: PendingTaskAction) => void;
}

/**
 * TASK-001 · One person's day: what is overdue from before it (up to 90 days back) on top,
 * then what is due that day, by time. A future day has nothing overdue: a task is due on its
 * day or overdue, never both. The server says what is overdue; the screen never works it out.
 */
export function PlannerDay({
  date,
  today,
  userId,
  meId,
  canEdit,
  onAction,
}: PlannerDayProps): React.JSX.Element {
  const query = useQuery(plannerDayQueryOptions({ date, userId }));
  const isToday = date === today;
  const dayName = isToday ? "today" : `on ${formatCalendarDay(date)}`;
  const someoneElse = userId !== null && userId !== meId;

  return (
    <QueryView
      query={query}
      pending={<PlannerDaySkeleton />}
      isEmpty={(day) => day.due.length === 0 && day.overdue.length === 0}
      empty={
        <EmptyState
          icon={Calendar03Icon}
          title={isToday ? "A clear day" : "Nothing due"}
          description={
            someoneElse
              ? `Nothing is due ${dayName}, and nothing is overdue.`
              : `Nothing is due ${dayName}, and nothing is overdue. Add a task to plan a call or a visit.`
          }
          className="rounded-xl border border-dashed border-border"
        />
      }
    >
      {(day) => (
        <div className="flex flex-col gap-6">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {daySummary(day, dayName)}
          </p>
          {day.overdue.length === 0 ? null : (
            <TaskSection
              id="tasks-overdue"
              title="Overdue from earlier"
              tone="danger"
              tasks={day.overdue}
              when="date"
              meId={meId}
              canEdit={canEdit}
              onAction={onAction}
            />
          )}
          <TaskSection
            id="tasks-due"
            title={isToday ? "Today" : formatCalendarDay(date)}
            tone="default"
            tasks={day.due}
            when="time"
            meId={meId}
            canEdit={canEdit}
            onAction={onAction}
            empty={`Nothing is due ${dayName}.`}
          />
        </div>
      )}
    </QueryView>
  );
}

/** "6 due today, 2 done · 3 overdue from earlier". */
function daySummary(day: PlannerDayData, dayName: string): string {
  const done = day.due.filter((task) => task.status === "done").length;
  const parts = [
    `${String(day.due.length)} due ${dayName}${done > 0 ? `, ${String(done)} done` : ""}`,
  ];
  if (day.overdue.length > 0) {
    parts.push(`${String(day.overdue.length)} overdue from earlier`);
  }
  return parts.join(" · ");
}

function TaskSection({
  id,
  title,
  tone,
  tasks,
  when,
  meId,
  canEdit,
  onAction,
  empty,
}: {
  id: string;
  title: string;
  tone: "default" | "danger";
  tasks: readonly Task[];
  when: "time" | "date";
  meId: string | null;
  canEdit: boolean;
  onAction: (action: PendingTaskAction) => void;
  empty?: string;
}): React.JSX.Element {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h2
        id={id}
        className={
          tone === "danger"
            ? "text-sm font-semibold text-danger"
            : "text-sm font-semibold text-foreground"
        }
      >
        {title}
        <span className="ml-2 font-normal text-muted-foreground tabular-nums">{tasks.length}</span>
      </h2>
      {tasks.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
          {empty}
        </p>
      ) : (
        <ol aria-labelledby={id} className="flex flex-col gap-2">
          {tasks.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              meId={meId}
              canEdit={canEdit}
              when={when}
              onAction={onAction}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

export function PlannerDaySkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the day" className="flex flex-col gap-3">
      <Skeleton className="h-4 w-56" />
      <Skeleton className="mt-3 h-4 w-24" />
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} className="flex gap-3 rounded-xl border border-border p-3 sm:p-4">
          <Skeleton className="size-8 rounded-full" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-4 w-3/5" />
            <Skeleton className="h-3 w-2/5" />
          </div>
          <Skeleton className="h-control-sm w-16" />
        </div>
      ))}
    </div>
  );
}
