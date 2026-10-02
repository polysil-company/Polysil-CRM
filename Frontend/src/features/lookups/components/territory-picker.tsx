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
import { territorySearchQueryOptions } from "@/features/lookups/api/lookups.queries";
import type {
  TerritoryChoice,
  TerritorySearchParams,
} from "@/features/lookups/api/lookups.schemas";
import { territoryLevelLabel } from "@/features/lookups/lib/lookup-labels";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

/** Search once typing pauses for this long. */
const SEARCH_DEBOUNCE_MS = 250;

/**
 * Opening the picker lists districts to start from; typing searches every level.
 * TODO(LEAD-002): the backend docs say a lead sits in a taluka or district, but the search
 * also returns villages and the state — which levels to offer is asked (Frontend-Scope §10).
 */
const START_PARAMS: TerritorySearchParams = { q: "", level: "district", limit: 50 };
const SEARCH_LIMIT = 20;

export interface TerritoryPickerProps {
  id: string;
  value: TerritoryChoice | null;
  onValueChange: (territory: TerritoryChoice | null) => void;
  onBlur?: () => void;
  disabled?: boolean;
  placeholder?: string;
  "aria-invalid"?: true | undefined;
  "aria-describedby"?: string | undefined;
}

/**
 * MSTR-002 · Pick a territory by typing its name: GET /lookups/territories searches on the
 * server, so the list never has to hold every village. Each option names its level and the
 * place above it ("Gondal · Taluka in Rajkot"), because the same name can exist twice.
 */
export function TerritoryPicker({
  id,
  value,
  onValueChange,
  onBlur,
  disabled = false,
  placeholder = "Search a district, taluka or village",
  ...aria
}: TerritoryPickerProps): React.JSX.Element {
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const params: TerritorySearchParams =
    term === "" ? START_PARAMS : { q: term, level: null, limit: SEARCH_LIMIT };
  const query = useQuery(territorySearchQueryOptions(params));

  const results: readonly TerritoryChoice[] = query.data ?? [];
  // Keep the chosen territory among the items so the field can still name it while a new
  // search loads, or after one that does not include it.
  const items =
    value !== null && !results.some((territory) => territory.id === value.id)
      ? [...results, value]
      : results;

  const waiting = search.trim() !== term || query.isFetching;
  const searching = waiting && term !== "";
  const browsing = term === "" && search.trim() === "";

  return (
    <Combobox
      items={items}
      value={value}
      onValueChange={(next) => {
        onValueChange(next);
      }}
      onInputValueChange={(next, details) => {
        // Choosing an option writes its name into the field; that is not a new search.
        if (details.reason !== "item-press") {
          setSearch(next);
        }
      }}
      itemToStringLabel={(territory: TerritoryChoice) => territory.name}
      isItemEqualToValue={(item: TerritoryChoice, selected: TerritoryChoice) =>
        item.id === selected.id
      }
      filter={null}
      disabled={disabled}
    >
      <ComboboxInput
        id={id}
        placeholder={placeholder}
        autoComplete="off"
        onBlur={onBlur}
        {...aria}
      />
      <ComboboxContent aria-busy={waiting || undefined}>
        <ComboboxStatus>
          <PickerStatus
            pending={query.isPending}
            failed={query.isError}
            searching={searching}
            browsing={browsing}
          />
        </ComboboxStatus>
        <ComboboxEmpty>
          {term !== "" && !waiting && !query.isError ? `No place matches “${term}”.` : null}
        </ComboboxEmpty>
        <ComboboxList>
          {(territory: TerritoryChoice) => (
            <ComboboxItem key={territory.id} value={territory}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate">{territory.name}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {territoryLevelLabel(territory.level)}
                  {territory.parent ? ` in ${territory.parent.name}` : ""}
                </span>
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}

function PickerStatus({
  pending,
  failed,
  searching,
  browsing,
}: {
  pending: boolean;
  failed: boolean;
  searching: boolean;
  browsing: boolean;
}): React.ReactNode {
  if (failed) {
    return "Places couldn't be loaded. Check your connection, then type again.";
  }
  if (pending || searching) {
    return (
      <>
        <Spinner />
        {pending && browsing ? "Loading districts…" : "Searching…"}
      </>
    );
  }
  if (browsing) {
    return "Districts. Type to find a taluka or village.";
  }
  return null;
}
