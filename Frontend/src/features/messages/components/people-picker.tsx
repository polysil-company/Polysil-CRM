"use client";

import { UserMultiple02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { SearchField } from "@/components/patterns/search-field";
import { Avatar, AvatarFallback, getInitials } from "@/components/ui/avatar";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { staffDirectoryQueryOptions } from "@/features/messages/api/messages.queries";
import type { Person } from "@/features/messages/api/messages.schemas";
import { describePerson } from "@/features/messages/lib/format-messages";

export interface PeoplePickerProps {
  /** Colleagues chosen so far, in the order they were picked. */
  chosen: readonly Person[];
  onChange: (chosen: readonly Person[]) => void;
  /** Already in the group: listed as members, not offered. */
  excludeIds?: ReadonlySet<string>;
  /** How many more may be chosen; the rest are disabled once it is reached. */
  limit: number;
  /** Search the directory only while the dialog that holds the picker is open. */
  enabled: boolean;
}

/**
 * MSG-006 · Choose several colleagues from the staff directory, for a new group or to add to
 * one. Search narrows the list; ticks are kept across searches.
 */
export function PeoplePicker({
  chosen,
  onChange,
  excludeIds,
  limit,
  enabled,
}: PeoplePickerProps): React.JSX.Element {
  const [q, setQ] = useState("");
  const directory = useQuery({ ...staffDirectoryQueryOptions(q), enabled });
  const chosenIds = new Set(chosen.map((person) => person.id));
  const full = chosen.length >= limit;
  const listId = useId();

  const toggle = (person: Person, checked: boolean): void => {
    onChange(checked ? [...chosen, person] : chosen.filter((item) => item.id !== person.id));
  };

  return (
    <div className="flex flex-col gap-2">
      <SearchField
        label="Search colleagues"
        value={q}
        placeholder="Name, role or office"
        onSearch={setQ}
        className="md:w-full"
      />
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {chosen.length === 0
          ? "No one chosen yet."
          : `${String(chosen.length)} chosen: ${chosen.map((person) => person.name).join(", ")}`}
        {full ? " That's as many as the group takes." : ""}
      </p>
      <QueryView
        query={directory}
        pending={<PickerSkeleton />}
        isEmpty={(people) =>
          people.filter((person) => excludeIds?.has(person.id) !== true).length === 0
        }
        empty={
          <EmptyState
            icon={UserMultiple02Icon}
            title={q === "" ? "No colleagues to add" : `No one matches “${q}”`}
            description="Try a first name, a role such as “Dispatch”, or an office."
            className="py-6"
          />
        }
      >
        {(people) => (
          <ul aria-label="Colleagues" id={listId} className="flex flex-col gap-0.5">
            {people
              .filter((person) => excludeIds?.has(person.id) !== true)
              .map((person) => {
                const checked = chosenIds.has(person.id);
                const id = `${listId}-${person.id}`;
                return (
                  <li key={person.id}>
                    <label
                      htmlFor={id}
                      className="flex cursor-pointer items-center gap-3 rounded-lg p-2 transition-colors duration-fast hover:bg-accent has-disabled:cursor-not-allowed has-disabled:opacity-60"
                    >
                      <Checkbox
                        id={id}
                        checked={checked}
                        disabled={!checked && full}
                        onCheckedChange={(next) => {
                          toggle(person, next);
                        }}
                      />
                      <Avatar size="md">
                        <AvatarFallback>{getInitials(person.name)}</AvatarFallback>
                      </Avatar>
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="truncate text-sm font-medium text-foreground">
                          {person.name}
                        </span>
                        <span className="truncate text-xs text-muted-foreground">
                          {describePerson(person)}
                        </span>
                      </span>
                    </label>
                  </li>
                );
              })}
          </ul>
        )}
      </QueryView>
    </div>
  );
}

function PickerSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading colleagues" className="flex flex-col gap-0.5">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex items-center gap-3 p-2">
          <Skeleton className="size-4 rounded-sm" />
          <Skeleton className="size-8 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3.5 w-32" />
            <Skeleton className="h-3 w-44" />
          </div>
        </div>
      ))}
    </div>
  );
}
