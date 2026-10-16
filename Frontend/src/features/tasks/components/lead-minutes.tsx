"use client";

import { Add01Icon, Agreement01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { leadMinutesQueryOptions } from "@/features/tasks/api/tasks.queries";
import type { Minutes } from "@/features/tasks/api/tasks.schemas";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { MinutesDialog } from "./minutes-dialog";

export interface LeadMinutesProps {
  leadId: string;
  leadName: string;
  /** A merged lead takes no new minutes: they go on the lead it was merged into. */
  merged: boolean;
}

/**
 * TASK-007 · A lead's meeting minutes, newest first: when, who was there, what was discussed,
 * and each action item as its task stands now ("1 of 2 done"). "Record minutes" adds a
 * meeting that wasn't planned as a task; a planned one is recorded from its row.
 */
export function LeadMinutes({ leadId, leadName, merged }: LeadMinutesProps): React.JSX.Element {
  const query = useQuery(leadMinutesQueryOptions(leadId));
  const session = useSession();
  const canCreate = useCan("tasks", "create");
  const meId = session.data?.user.id ?? null;
  const [open, setOpen] = useState(false);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Meeting minutes</CardTitle>
          <CardDescription>What was agreed, and what came of it</CardDescription>
        </div>
        {canCreate && !merged ? (
          <Button
            variant="outline"
            onClick={() => {
              setOpen(true);
            }}
          >
            <Icon icon={Add01Icon} />
            Record minutes
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        <QueryView
          query={query}
          pending={<LeadMinutesSkeleton />}
          isEmpty={(rows) => rows.length === 0}
          empty={
            <EmptyState
              icon={Agreement01Icon}
              title="No minutes yet"
              description="After a meeting with the farmer, record who was there, what was agreed, and the follow-ups."
            />
          }
        >
          {(rows) => (
            <ol aria-label="Meeting minutes, newest first" className="flex flex-col gap-3">
              {rows.map((minutes) => (
                <MinutesEntry key={minutes.id} minutes={minutes} />
              ))}
            </ol>
          )}
        </QueryView>
      </CardContent>
      <MinutesDialog
        subject={open ? { leadId, leadName, meeting: null } : null}
        meId={meId}
        onClose={() => {
          setOpen(false);
        }}
      />
    </Card>
  );
}

function MinutesEntry({ minutes }: { minutes: Minutes }): React.JSX.Element {
  const done = minutes.actionItems.filter((task) => task.status === "done").length;
  const total = minutes.actionItems.length;

  return (
    <li
      aria-label={`Meeting on ${formatDateTime(minutes.heldAt)}`}
      className="flex flex-col gap-2 rounded-xl border border-border p-3 sm:p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-foreground">
          <time dateTime={minutes.heldAt}>{formatDateTime(minutes.heldAt)}</time>
        </p>
        {total === 0 ? null : (
          <Badge variant={done === total ? "success" : "neutral"}>
            {done} of {total} done
          </Badge>
        )}
      </div>
      {minutes.attendees.length === 0 ? null : (
        <p className="text-xs text-muted-foreground">With {minutes.attendees.join(", ")}</p>
      )}
      <p className="text-sm text-pretty whitespace-pre-line text-foreground">{minutes.notes}</p>
      {total === 0 ? null : (
        <ul aria-label="Action items" className="flex flex-col gap-1 border-t border-border pt-2">
          {minutes.actionItems.map((task) => (
            <li key={task.id} className="flex items-start gap-2 text-sm">
              <span
                aria-hidden="true"
                className={cn(
                  "mt-1.5 size-2 shrink-0 rounded-full",
                  task.status === "done"
                    ? "bg-success"
                    : task.status === "cancelled"
                      ? "bg-subtle-foreground"
                      : task.overdue
                        ? "bg-danger"
                        : "bg-warning",
                )}
              />
              <span
                className={cn(
                  "min-w-0 flex-1 text-pretty",
                  task.status === "cancelled" && "text-muted-foreground line-through",
                )}
              >
                {task.title}
                <span className="text-muted-foreground">
                  {" "}
                  · {task.assignedTo?.name ?? "Unassigned"} · due {formatDate(task.dueAt)}
                </span>
                <span className="sr-only">
                  {task.status === "done"
                    ? ", done"
                    : task.status === "cancelled"
                      ? ", cancelled"
                      : task.overdue
                        ? ", overdue"
                        : ", open"}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {minutes.createdBy === null ? null : (
        <p className="text-xs text-subtle-foreground">Recorded by {minutes.createdBy.name}</p>
      )}
    </li>
  );
}

export function LeadMinutesSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading minutes" className="flex flex-col gap-2">
      <Skeleton className="h-24 w-full rounded-xl" />
    </div>
  );
}
