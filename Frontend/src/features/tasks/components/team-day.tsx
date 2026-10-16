"use client";

import { ArrowRight01Icon, UserGroupIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { teamDayQueryOptions } from "@/features/tasks/api/tasks.queries";
import type { TeamRow } from "@/features/tasks/api/tasks.schemas";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatCalendarDay } from "@/lib/format";
import { cn } from "@/lib/utils";

const SKELETON_ROWS = 4;

export interface TeamDayProps {
  /** The day, `YYYY-MM-DD`. */
  date: string;
  today: string;
  /** Opens one person's day. */
  onOpenPerson: (userId: string) => void;
}

/**
 * TASK-002 · A manager's day: one row per person below them — due that day, done that day,
 * and overdue now — people with nothing to do included, so an idle day is visible too. A row
 * opens that person's day.
 */
export function TeamDay({ date, today, onOpenPerson }: TeamDayProps): React.JSX.Element {
  const query = useInfiniteQuery(teamDayQueryOptions(date));
  const dayName = date === today ? "today" : formatCalendarDay(date);

  return (
    <QueryView
      query={query}
      pending={<TeamDaySkeleton />}
      isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
      empty={
        <EmptyState
          icon={UserGroupIcon}
          title="No one reports to you"
          description="People below you in the organisation appear here with their day."
          className="rounded-xl border border-dashed border-border"
        />
      }
    >
      {(data) => (
        <div className="flex flex-col gap-3">
          <ul aria-label={`Your team, ${dayName}`} className="flex flex-col gap-2">
            {data.pages.flatMap((page) =>
              page.items.map((row) => (
                <TeamPersonRow
                  key={row.user.id}
                  row={row}
                  dayName={dayName}
                  onOpen={() => {
                    onOpenPerson(row.user.id);
                  }}
                />
              )),
            )}
          </ul>
          {query.hasNextPage ? (
            <div className="flex flex-col items-start gap-2">
              {query.isFetchNextPageError ? (
                <p role="alert" className="text-xs text-danger">
                  {toUserFacingError(query.error).title}. The people above are still current.
                </p>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                state={query.isFetchingNextPage ? "loading" : "idle"}
                loadingLabel="Loading…"
                onClick={() => {
                  void query.fetchNextPage();
                }}
              >
                {query.isFetchNextPageError ? "Try again" : "Show more people"}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </QueryView>
  );
}

function TeamPersonRow({
  row,
  dayName,
  onOpen,
}: {
  row: TeamRow;
  dayName: string;
  onOpen: () => void;
}): React.JSX.Element {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        aria-label={`${row.user.name}: ${String(row.dueToday)} due ${dayName}, ${String(row.doneToday)} done, ${String(row.overdue)} overdue. Open their day`}
        className="flex w-full press-scale items-center gap-3 rounded-xl border border-border bg-card p-3 text-left transition-colors duration-fast hover:bg-accent sm:p-4"
      >
        <AvatarLabel name={row.user.name} className="min-w-0 flex-1 font-medium" />
        <dl className="grid shrink-0 grid-cols-3 gap-3 text-center sm:gap-6">
          <TeamStat label="Due" value={row.dueToday} />
          <TeamStat
            label="Done"
            value={row.doneToday}
            tone={row.doneToday > 0 ? "success" : "default"}
          />
          <TeamStat
            label="Overdue"
            value={row.overdue}
            tone={row.overdue > 0 ? "danger" : "default"}
          />
        </dl>
        <Icon icon={ArrowRight01Icon} size="sm" className="shrink-0 text-subtle-foreground" />
      </button>
    </li>
  );
}

function TeamStat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "success" | "danger";
}): React.JSX.Element {
  return (
    <div className="flex min-w-10 flex-col-reverse">
      <dt className="text-2xs text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          "text-base font-semibold tabular-nums",
          tone === "danger"
            ? "text-danger"
            : tone === "success"
              ? "text-success"
              : "text-foreground",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

export function TeamDaySkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading your team" className="flex flex-col gap-2">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 rounded-xl border border-border p-3 sm:p-4"
        >
          <Skeleton className="size-7 rounded-full" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-8 w-36" />
        </div>
      ))}
    </div>
  );
}
