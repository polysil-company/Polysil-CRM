"use client";

import { ArrowLeft01Icon, ArrowRight01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { FilterPillFrame, filterOptionRowClasses } from "@/components/patterns/filter-pill";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { leadAreasQueryOptions } from "@/features/leads/api/leads.queries";
import {
  MAX_LEAD_AREAS,
  type LeadArea,
  type LeadAreaLevel,
} from "@/features/leads/api/leads.schemas";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/** An area the picker has opened, to show what is under it. */
interface OpenedArea {
  readonly id: string;
  readonly name: string;
  readonly level: LeadAreaLevel;
}

const CHILD_LEVEL: Record<LeadAreaLevel, LeadAreaLevel | null> = {
  state: "district",
  district: "taluka",
  taluka: null,
};

const CHILD_NOUN: Record<LeadAreaLevel, string> = {
  state: "districts",
  district: "talukas",
  taluka: "",
};

export interface LeadAreaFilterProps {
  /** Selected territory ids, from the URL. */
  selected: readonly string[];
  onChange: (next: string[]) => void;
}

/**
 * LEAD-001 · The Area pill on the leads list: pick states, districts or talukas, drilling down
 * from the top. Only areas that hold a lead you can see are offered, each with how many.
 * Choosing a district includes every taluka and village under it. The backend takes at most
 * 20 areas; past that the rest are disabled. With a single state (Gujarat today) the picker
 * starts at its districts, since choosing the state would filter nothing.
 */
export function LeadAreaFilter({ selected, onChange }: LeadAreaFilterProps): React.JSX.Element {
  // Kept outside the popover so it reopens where it was left.
  const [path, setPath] = useState<readonly OpenedArea[]>([]);
  // Names of areas picked in this visit, for the pill's summary; a shared link shows a count.
  const [names, setNames] = useState<Readonly<Record<string, string>>>({});

  const firstName = selected.length === 1 ? names[selected[0] ?? ""] : undefined;
  const summary =
    selected.length === 0
      ? undefined
      : (firstName ?? `${String(selected.length)} ${selected.length === 1 ? "area" : "areas"}`);

  return (
    <FilterPillFrame
      label="Area"
      icon={undefined}
      summary={summary}
      className={undefined}
      wide
      onClear={() => {
        onChange([]);
      }}
    >
      <AreaPicker
        path={path}
        onPathChange={setPath}
        selected={selected}
        onToggle={(area, checked) => {
          setNames((current) => ({ ...current, [area.id]: area.name }));
          onChange(checked ? [...selected, area.id] : selected.filter((id) => id !== area.id));
        }}
      />
    </FilterPillFrame>
  );
}

/** The popover body. It mounts when the popover opens, so nothing loads until then. */
function AreaPicker({
  path,
  onPathChange,
  selected,
  onToggle,
}: {
  path: readonly OpenedArea[];
  onPathChange: (next: readonly OpenedArea[]) => void;
  selected: readonly string[];
  onToggle: (area: LeadArea, checked: boolean) => void;
}): React.JSX.Element {
  const states = useQuery(leadAreasQueryOptions({ level: "state", parentId: null }));
  const onlyState = states.data?.length === 1 ? states.data[0] : undefined;

  // With one state, its districts are the top of the picker.
  const root: readonly OpenedArea[] =
    onlyState === undefined ? [] : [{ id: onlyState.id, name: onlyState.name, level: "state" }];
  const trail = [...root, ...path];
  const opened = trail.at(-1);
  const level: LeadAreaLevel =
    opened === undefined ? "state" : (CHILD_LEVEL[opened.level] ?? "taluka");

  const areas = useQuery({
    ...leadAreasQueryOptions({ level, parentId: opened?.id ?? null }),
    enabled: states.isSuccess && (level !== "state" || onlyState === undefined),
  });
  // At the top with several states, the states query is the list itself.
  const list = level === "state" ? states : areas;
  const full = selected.length >= MAX_LEAD_AREAS;

  return (
    <div className="flex flex-col">
      {path.length > 0 ? (
        <Button
          variant="ghost"
          size="sm"
          className="self-start"
          onClick={() => {
            onPathChange(path.slice(0, -1));
          }}
        >
          <Icon icon={ArrowLeft01Icon} />
          {path.length === 1
            ? `All ${root.length === 0 ? "states" : CHILD_NOUN.state}`
            : path.at(-2)?.name}
        </Button>
      ) : null}
      <p className="px-2 pt-1 pb-1.5 text-xs font-medium text-muted-foreground">
        {opened === undefined
          ? "States"
          : `${capitalise(CHILD_NOUN[opened.level])} in ${opened.name}`}
      </p>

      {list.isPending ? (
        <div role="status" aria-label="Loading areas" className="flex flex-col gap-1 p-2">
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-4/5" />
          <Skeleton className="h-5 w-3/5" />
        </div>
      ) : list.isError ? (
        <div className="flex flex-col items-start gap-2 px-2 py-1.5">
          <p role="alert" className="text-sm text-muted-foreground">
            {toUserFacingError(list.error).title}.
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void list.refetch();
            }}
          >
            Try again
          </Button>
        </div>
      ) : list.data.length === 0 ? (
        <p className="px-2 py-1.5 text-sm text-muted-foreground">
          {opened === undefined
            ? "No leads in any area yet."
            : `No lead in ${opened.name} is filed under a ${singular(CHILD_NOUN[opened.level])} yet. Go back and choose ${opened.name} itself.`}
        </p>
      ) : (
        <ul
          aria-label={opened === undefined ? "States" : `Areas in ${opened.name}`}
          className="flex flex-col"
        >
          {list.data.map((area) => {
            const checked = selected.includes(area.id);
            const child = CHILD_LEVEL[area.level];
            return (
              <li key={area.id} className="flex items-center gap-1">
                <label className={cn(filterOptionRowClasses, "min-w-0 flex-1")}>
                  <Checkbox
                    checked={checked}
                    disabled={!checked && full}
                    onCheckedChange={(next) => {
                      onToggle(area, next);
                    }}
                  />
                  <span className="flex-1 truncate">{area.name}</span>
                  <span className="text-xs text-subtle-foreground tabular-nums">
                    <span className="sr-only">, </span>
                    {formatNumber(area.leadCount)}
                    <span className="sr-only"> {area.leadCount === 1 ? "lead" : "leads"}</span>
                  </span>
                </label>
                {child === null ? null : (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Show ${CHILD_NOUN[area.level]} in ${area.name}`}
                    onClick={() => {
                      onPathChange([...path, { id: area.id, name: area.name, level: area.level }]);
                    }}
                  >
                    <Icon icon={ArrowRight01Icon} />
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {full ? (
        <p role="status" className="px-2 pt-1.5 text-xs text-pretty text-muted-foreground">
          {MAX_LEAD_AREAS} areas is the most at once. Choose a district instead of its talukas to
          cover more.
        </p>
      ) : null}
    </div>
  );
}

function singular(noun: string): string {
  return noun.replace(/s$/, "");
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
