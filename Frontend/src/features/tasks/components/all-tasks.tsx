"use client";

import { Task01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { EmptyState } from "@/components/patterns/empty-state";
import { FilterPill, SingleFilterPill } from "@/components/patterns/filter-pill";
import { QueryView } from "@/components/patterns/query-view";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { exportTasks } from "@/features/tasks/api/tasks.api";
import {
  taskAssigneesQueryOptions,
  taskListQueryOptions,
} from "@/features/tasks/api/tasks.queries";
import { TASK_STATUSES, TASK_TYPES, type TaskListParams } from "@/features/tasks/api/tasks.schemas";
import { taskListParamsOf, type TaskFilters } from "@/features/tasks/hooks/use-task-params";
import { TASK_TYPE_LABELS } from "@/features/tasks/lib/task-labels";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatCount } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { PlannerDaySkeleton } from "./planner-day";
import type { PendingTaskAction } from "./task-action-dialog";
import { TaskRow } from "./task-row";

const log = createLogger({ file: "features/tasks/components/all-tasks.tsx", dataId: "TASK-008" });

const STATUS_LABELS = { open: "Open", done: "Done", cancelled: "Cancelled" } as const;
const STATUS_OPTIONS = TASK_STATUSES.map((value) => ({ value, label: STATUS_LABELS[value] }));
const TYPE_OPTIONS = TASK_TYPES.map((value) => ({ value, label: TASK_TYPE_LABELS[value] }));

export interface AllTasksProps {
  filters: TaskFilters;
  onFiltersChange: (patch: Partial<TaskFilters>) => void;
  onReset: () => void;
  hasTeam: boolean;
  meId: string | null;
  canEdit: boolean;
  onAction: (action: PendingTaskAction) => void;
}

/**
 * TASK-003, TASK-008 · Every task the user can see — theirs, and their team's for a manager —
 * earliest due first, filtered by status, kind, person and overdue (all in the URL), and
 * downloaded as an Excel file with the same filters. The download holds every page; past
 * 5,000 rows the backend asks for narrower filters.
 */
export function AllTasks({
  filters,
  onFiltersChange,
  onReset,
  hasTeam,
  meId,
  canEdit,
  onAction,
}: AllTasksProps): React.JSX.Element {
  const params: TaskListParams = taskListParamsOf(filters);
  const query = useInfiniteQuery(taskListQueryOptions(params));
  const people = useQuery({ ...taskAssigneesQueryOptions(), enabled: hasTeam });
  const total = query.data?.pages[0]?.total ?? null;
  const capped = query.data?.pages[0]?.totalCapped ?? false;
  const filtered =
    filters.status.length > 0 ||
    filters.type !== null ||
    filters.assignedTo !== null ||
    filters.overdue;

  const personOptions = [
    { value: "me", label: "Me" },
    ...(people.data ?? [])
      .filter((person) => person.id !== meId)
      .map((person) => ({ value: person.id, label: person.name })),
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <FilterPill
            label="Status"
            options={STATUS_OPTIONS}
            selected={filters.status}
            onChange={(status) => {
              onFiltersChange({ status });
            }}
          />
          <SingleFilterPill
            label="Kind"
            options={TYPE_OPTIONS}
            selected={filters.type}
            onChange={(type) => {
              onFiltersChange({ type });
            }}
          />
          {hasTeam ? (
            <SingleFilterPill
              label="For"
              options={personOptions}
              selected={filters.assignedTo}
              emptyMessage={people.isPending ? "Loading people…" : "No one to choose."}
              onChange={(assignedTo) => {
                onFiltersChange({ assignedTo });
              }}
            />
          ) : null}
          <div className="flex items-center gap-2 px-1">
            <Checkbox
              id="tasks-overdue-only"
              checked={filters.overdue}
              onCheckedChange={(checked) => {
                onFiltersChange({ overdue: checked });
              }}
            />
            <Label htmlFor="tasks-overdue-only" className="text-sm">
              Overdue only
            </Label>
          </div>
          {filtered ? (
            <Button variant="ghost" size="sm" onClick={onReset}>
              Reset filters
            </Button>
          ) : null}
        </div>
        <DownloadExcelButton
          download={() => exportTasks(params)}
          fallbackName="tasks.xlsx"
          what="tasks"
          logger={log}
          dataId="TASK-008"
        />
      </div>

      <p aria-live="polite" className="text-sm text-muted-foreground">
        {total === null
          ? "Earliest due first."
          : `${formatCount(total, { atLeast: capped })} ${total === 1 ? "task" : "tasks"}, earliest due first.`}
      </p>

      <QueryView
        query={query}
        pending={<PlannerDaySkeleton />}
        isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
        empty={
          <EmptyState
            icon={Task01Icon}
            title={filtered ? "No tasks match these filters" : "No tasks yet"}
            description={
              filtered
                ? "Change or reset the filters to see more."
                : "Tasks you add, and tasks given to you, appear here."
            }
            action={
              filtered ? (
                <Button variant="outline" size="sm" onClick={onReset}>
                  Reset filters
                </Button>
              ) : undefined
            }
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <ol aria-label="Tasks, earliest due first" className="flex flex-col gap-2">
              {data.pages.flatMap((page) =>
                page.items.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    meId={meId}
                    canEdit={canEdit}
                    when="date"
                    showAssignee={hasTeam}
                    onAction={onAction}
                  />
                )),
              )}
            </ol>
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
        )}
      </QueryView>
    </div>
  );
}
