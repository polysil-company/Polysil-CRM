"use client";

import { ArrowLeft01Icon, ArrowRight01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { taskAssigneesQueryOptions } from "@/features/tasks/api/tasks.queries";
import { useHasTeam, useTaskParams, type TaskView } from "@/features/tasks/hooks/use-task-params";
import { formatCalendarDay, shiftCalendarDay, todayInIndia } from "@/lib/format";

import { NewTaskDialog } from "./new-task-dialog";
import { PlannerDay, PlannerDaySkeleton } from "./planner-day";
import { TaskActionDialog, type PendingTaskAction } from "./task-action-dialog";
import { TeamDay } from "./team-day";

/**
 * TASK-001 · The Tasks page. "My day" is today's tasks with the overdue ones on top; a
 * manager also has "Team": one row per person below them, each opening that person's day.
 * The day moves back and forward, or jumps to a date; all of it is in the URL.
 */
export function TasksView(): React.JSX.Element {
  const { params, setParams } = useTaskParams();
  const [today] = useState(todayInIndia);
  const [pending, setPending] = useState<PendingTaskAction | null>(null);
  const session = useSession();
  const hasTeam = useHasTeam();
  const canCreate = useCan("tasks", "create");
  const canEdit = useCan("tasks", "edit");
  const meId = session.data?.user.id ?? null;

  const date = params.date ?? today;
  const view: TaskView = hasTeam ? params.view : "day";
  const personId = view === "day" && params.userId !== meId ? params.userId : null;

  return (
    <section aria-label="Tasks" className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          {hasTeam ? (
            <ToggleGroup
              aria-label="Whose tasks"
              value={[personId === null ? view : "team"]}
              onValueChange={(next) => {
                const [choice] = next;
                if (choice === "day" || choice === "team") {
                  setParams({ view: choice, userId: null });
                }
              }}
            >
              <ToggleGroupItem value="day">My day</ToggleGroupItem>
              <ToggleGroupItem value="team">Team</ToggleGroupItem>
            </ToggleGroup>
          ) : null}
          <DayNavigator
            date={date}
            today={today}
            onChange={(next) => {
              setParams({ date: next === today ? null : next });
            }}
          />
        </div>
        {canCreate && view === "day" ? (
          <NewTaskDialog
            subject={null}
            defaultDate={date}
            meId={meId}
            defaultAssigneeId={personId}
          />
        ) : null}
      </div>

      {personId === null ? null : (
        <PersonHeader
          personId={personId}
          onBack={() => {
            setParams({ view: "team", userId: null });
          }}
        />
      )}

      {session.isPending ? (
        <PlannerDaySkeleton />
      ) : view === "team" ? (
        <TeamDay
          date={date}
          today={today}
          onOpenPerson={(userId) => {
            setParams({ view: "day", userId });
          }}
        />
      ) : (
        <PlannerDay
          date={date}
          today={today}
          userId={personId}
          meId={meId}
          canEdit={canEdit}
          onAction={setPending}
        />
      )}

      <TaskActionDialog
        pending={pending}
        onClose={() => {
          setPending(null);
        }}
      />
    </section>
  );
}

/** Back a day, forward a day, back to today, or any date. */
function DayNavigator({
  date,
  today,
  onChange,
}: {
  date: string;
  today: string;
  onChange: (date: string) => void;
}): React.JSX.Element {
  return (
    <div role="group" aria-label="Day" className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Previous day"
        onClick={() => {
          onChange(shiftCalendarDay(date, -1));
        }}
      >
        <Icon icon={ArrowLeft01Icon} />
      </Button>
      <label className="relative">
        <span className="sr-only">Go to a day</span>
        <Input
          type="date"
          value={date}
          className="h-control-sm w-auto"
          onChange={(event) => {
            if (event.target.value !== "") onChange(event.target.value);
          }}
        />
      </label>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Next day"
        onClick={() => {
          onChange(shiftCalendarDay(date, 1));
        }}
      >
        <Icon icon={ArrowRight01Icon} />
      </Button>
      {date === today ? (
        <span className="ml-1 text-sm font-medium text-foreground">Today</span>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          aria-label={`Back to today, ${formatCalendarDay(today)}`}
          onClick={() => {
            onChange(today);
          }}
        >
          Today
        </Button>
      )}
    </div>
  );
}

/** Whose day this is, when a manager opened someone else's, with the way back. */
function PersonHeader({
  personId,
  onBack,
}: {
  personId: string;
  onBack: () => void;
}): React.JSX.Element {
  const people = useQuery(taskAssigneesQueryOptions());
  const person = people.data?.find((candidate) => candidate.id === personId);

  return (
    <div className="flex items-center gap-2">
      <Button variant="ghost" size="sm" onClick={onBack}>
        <Icon icon={ArrowLeft01Icon} />
        Back to team
      </Button>
      <h2 className="text-base font-semibold text-foreground">
        {person === undefined ? (
          people.isPending ? (
            <Skeleton className="h-5 w-40" />
          ) : (
            "Their day"
          )
        ) : (
          `${person.name}'s day`
        )}
      </h2>
    </div>
  );
}
