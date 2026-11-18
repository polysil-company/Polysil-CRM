"use client";

import { Task01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { taskListQueryOptions } from "@/features/tasks/api/tasks.queries";
import { leadTaskParams, type Task } from "@/features/tasks/api/tasks.schemas";
import { toUserFacingError } from "@/lib/api/error-messages";

import { NewTaskDialog } from "./new-task-dialog";
import type { PendingTaskAction } from "./task-action-dialog";
import { TaskDialogs } from "./task-dialogs";
import { TaskRow } from "./task-row";

export interface LeadTasksProps {
  leadId: string;
  /** The farmer's name, to say what a new task is about. */
  leadName: string;
  /** A merged lead takes no new tasks: they go on the lead it was merged into. */
  merged: boolean;
}

/**
 * TASK-003 · A lead's tasks and meetings: what is still to do, by due date, then what was done
 * or cancelled. "Add task" plans a call, visit or meeting about this lead; a meeting names its
 * kind (Survey & Design, Follow-up…).
 */
export function LeadTasks({ leadId, leadName, merged }: LeadTasksProps): React.JSX.Element {
  const query = useInfiniteQuery(taskListQueryOptions(leadTaskParams(leadId)));
  const session = useSession();
  const canCreate = useCan("tasks", "create");
  const canEdit = useCan("tasks", "edit");
  const meId = session.data?.user.id ?? null;
  const [pending, setPending] = useState<PendingTaskAction | null>(null);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Tasks and meetings</CardTitle>
          <CardDescription>What is still to do comes first</CardDescription>
        </div>
        {canCreate && !merged ? (
          <NewTaskDialog
            subject={{ leadId, label: leadName }}
            meId={meId}
            triggerVariant="outline"
          />
        ) : null}
      </CardHeader>
      <CardContent>
        <QueryView
          query={query}
          pending={<LeadTasksSkeleton />}
          isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
          empty={
            <EmptyState
              icon={Task01Icon}
              title="No tasks yet"
              description={
                merged
                  ? "This lead was merged; plan work on the lead it was merged into."
                  : "Plan a call, a farm visit or a meeting about this lead."
              }
            />
          }
        >
          {(data) => {
            const tasks = data.pages.flatMap((page) => page.items);
            const open = tasks.filter((task) => task.status === "open");
            const closed = tasks.filter((task) => task.status !== "open").reverse();
            return (
              <div className="flex flex-col gap-5">
                <TaskGroup
                  title="To do"
                  tasks={open}
                  meId={meId}
                  canEdit={canEdit}
                  onAction={setPending}
                  empty="Nothing left to do on this lead."
                />
                {closed.length === 0 ? null : (
                  <TaskGroup
                    title="Done and cancelled"
                    tasks={closed}
                    meId={meId}
                    canEdit={canEdit}
                    onAction={setPending}
                  />
                )}
                {query.hasNextPage ? (
                  <div className="flex flex-col items-start gap-2">
                    {query.isFetchNextPageError ? (
                      <p role="alert" className="text-xs text-danger">
                        {toUserFacingError(query.error).title}. The tasks above are still current.
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
                      {query.isFetchNextPageError ? "Try again" : "Show more"}
                    </Button>
                  </div>
                ) : null}
              </div>
            );
          }}
        </QueryView>
      </CardContent>
      <TaskDialogs
        pending={pending}
        meId={meId}
        onClose={() => {
          setPending(null);
        }}
      />
    </Card>
  );
}

function TaskGroup({
  title,
  tasks,
  meId,
  canEdit,
  onAction,
  empty,
}: {
  title: string;
  tasks: readonly Task[];
  meId: string | null;
  canEdit: boolean;
  onAction: (action: PendingTaskAction) => void;
  empty?: string;
}): React.JSX.Element {
  return (
    <section aria-label={title} className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
        <span className="ml-1.5 tabular-nums">{tasks.length}</span>
      </h4>
      {tasks.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {tasks.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              meId={meId}
              canEdit={canEdit}
              when="date"
              showAssignee
              hideSubject
              onAction={onAction}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

export function LeadTasksSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading tasks" className="flex flex-col gap-2">
      <Skeleton className="h-3 w-16" />
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-16 w-full rounded-xl" />
    </div>
  );
}
