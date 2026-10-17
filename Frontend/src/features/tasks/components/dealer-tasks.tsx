"use client";

import { Task01Icon, TaskDone01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useSession } from "@/features/session/hooks/use-session";
import { taskListQueryOptions } from "@/features/tasks/api/tasks.queries";
import { dealerTaskParams } from "@/features/tasks/hooks/use-dealer-tasks";
import { isApiError } from "@/lib/api/errors";

import { TaskActionDialog, type PendingTaskAction } from "./task-action-dialog";
import { TaskRow } from "./task-row";

const VIEWS = ["open", "done"] as const;
type View = (typeof VIEWS)[number];

const VIEW_LABELS: Readonly<Record<View, string>> = { open: "To do", done: "Done" };

/**
 * TASK-009 · A dealer user's tasks, given by Polysil staff (FS-037): what to do and by when,
 * what it is about, and who gave it. Done, with what happened, is the only action; done tasks
 * keep what was said. While `tasks_for_dealers` is off the backend answers 403, and the page
 * says tasks aren't switched on.
 */
export function DealerTasks(): React.JSX.Element {
  const { data: session } = useSession();
  const [view, setView] = useState<View>("open");
  const [pending, setPending] = useState<PendingTaskAction | null>(null);
  const query = useInfiniteQuery({
    ...taskListQueryOptions(dealerTaskParams(view)),
    retry: false,
  });
  const tasks = query.data?.pages.flatMap((page) => page.items) ?? [];
  const off = query.status === "error" && isApiError(query.error) && query.error.status === 403;
  const doneAction = (action: PendingTaskAction): void => {
    if (action.kind === "complete") setPending(action);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-prose text-sm text-muted-foreground">
          Calls, visits and follow-ups Polysil has given you. Mark each done with what happened.
        </p>
        {off ? null : (
          <ToggleGroup
            aria-label="Show"
            value={[view]}
            onValueChange={(next) => {
              const chosen = VIEWS.find((item) => item === next[0]);
              if (chosen !== undefined) setView(chosen);
            }}
          >
            {VIEWS.map((item) => (
              <ToggleGroupItem key={item} value={item}>
                {VIEW_LABELS[item]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        )}
      </div>

      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading your tasks" className="flex flex-col gap-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      ) : off ? (
        <EmptyState
          icon={Task01Icon}
          title="Tasks aren't switched on"
          description="Polysil switches on tasks for dealers in its company settings. Until then there is nothing here."
          className="py-12"
        />
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : tasks.length === 0 ? (
        <EmptyState
          icon={view === "open" ? TaskDone01Icon : Task01Icon}
          title={view === "open" ? "Nothing to do" : "Nothing done yet"}
          description={
            view === "open"
              ? "Tasks Polysil gives you appear here, earliest first."
              : "Tasks you mark done stay here with what you said."
          }
          className="py-12"
        />
      ) : (
        <>
          <ul
            aria-label={view === "open" ? "Tasks to do" : "Done tasks"}
            className="flex flex-col gap-3"
          >
            {tasks.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                meId={session?.user.id ?? null}
                canEdit
                completeOnly
                when="date"
                onAction={doneAction}
              />
            ))}
          </ul>
          {query.hasNextPage ? (
            <Button
              variant="outline"
              size="sm"
              className="self-center"
              disabled={query.isFetchingNextPage}
              onClick={() => {
                void query.fetchNextPage();
              }}
            >
              {query.isFetchingNextPage ? "Loading…" : "Show more"}
            </Button>
          ) : null}
        </>
      )}
      <TaskActionDialog
        pending={pending?.kind === "complete" ? { task: pending.task, kind: "complete" } : null}
        onClose={() => {
          setPending(null);
        }}
      />
    </div>
  );
}
