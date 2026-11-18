"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxStatus,
} from "@/components/ui/combobox";
import { Spinner } from "@/components/ui/spinner";
import { officeSearchQueryOptions } from "@/features/users/api/users.queries";
import type { OfficeChoice } from "@/features/users/api/users.schemas";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

const SEARCH_DEBOUNCE_MS = 250;

/** An office as the form keeps it: its id to send, its name to show. */
export interface OfficeValue {
  readonly id: string;
  readonly name: string;
  readonly detail?: string;
}

/**
 * ADMN-003 · Pick an open office by name (`GET /org-units?is_open=true`). Each option names the
 * office above it and the territory it covers, since branch names repeat.
 */
export function OfficePicker({
  id,
  value,
  onValueChange,
  invalid,
  describedBy,
}: {
  id: string;
  value: OfficeValue | null;
  onValueChange: (office: OfficeValue | null) => void;
  invalid?: boolean;
  describedBy?: string;
}): React.JSX.Element {
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const query = useQuery(officeSearchQueryOptions(term));
  const results: OfficeValue[] = (query.data ?? []).map((office: OfficeChoice) => ({
    id: office.id,
    name: office.name,
    detail: [office.territoryName, office.parentName === null ? null : `under ${office.parentName}`]
      .filter((part) => part !== null)
      .join(" · "),
  }));
  const items =
    value !== null && !results.some((office) => office.id === value.id)
      ? [value, ...results]
      : results;
  const waiting = search.trim() !== term || query.isFetching;

  return (
    <Combobox
      items={items}
      value={value}
      onValueChange={(next: OfficeValue | null) => {
        onValueChange(next);
      }}
      onInputValueChange={(next, details) => {
        if (details.reason !== "item-press") setSearch(next);
      }}
      itemToStringLabel={(office: OfficeValue) => office.name}
      isItemEqualToValue={(item: OfficeValue, selected: OfficeValue) => item.id === selected.id}
      filter={null}
    >
      <ComboboxInput
        id={id}
        placeholder="Search an office"
        autoComplete="off"
        aria-invalid={invalid === true ? true : undefined}
        aria-describedby={describedBy}
      />
      <ComboboxContent aria-busy={waiting || undefined}>
        <ComboboxStatus>
          {query.isError ? (
            "Offices couldn't be loaded. Check your connection, then type again."
          ) : waiting ? (
            <>
              <Spinner />
              Searching…
            </>
          ) : null}
        </ComboboxStatus>
        <ComboboxEmpty>
          {waiting || query.isError
            ? null
            : term === ""
              ? "No open offices."
              : `No open office matches “${term}”.`}
        </ComboboxEmpty>
        <ComboboxList>
          {(office: OfficeValue) => (
            <ComboboxItem key={office.id} value={office}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate">{office.name}</span>
                {office.detail === undefined || office.detail === "" ? null : (
                  <span className="truncate text-xs text-muted-foreground">{office.detail}</span>
                )}
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
