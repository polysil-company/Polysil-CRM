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
import { leadListQueryOptions } from "@/features/leads/api/leads.queries";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

const SEARCH_DEBOUNCE_MS = 250;

/** A lead as the check-in form keeps it. */
export interface LeadChoice {
  readonly id: string;
  readonly code: string;
  readonly name: string;
}

/** TRK-003 · Pick the lead being visited by farmer, mobile or inquiry number. */
export function VisitLeadPicker({
  id,
  value,
  onValueChange,
  invalid,
}: {
  id: string;
  value: LeadChoice | null;
  onValueChange: (lead: LeadChoice | null) => void;
  invalid?: boolean;
}): React.JSX.Element {
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const query = useQuery(
    leadListQueryOptions({
      cursor: null,
      pageSize: 8,
      sort: "createdAt",
      order: "desc",
      q: term,
      stage: [],
      source: null,
      type: null,
      areas: [],
      campaign: null,
    }),
  );
  const results: LeadChoice[] = (query.data?.items ?? []).map((lead) => ({
    id: lead.id,
    code: lead.code,
    name: lead.customerName,
  }));
  const items =
    value !== null && !results.some((lead) => lead.id === value.id) ? [value, ...results] : results;
  const waiting = search.trim() !== term || query.isFetching;

  return (
    <Combobox
      items={items}
      value={value}
      onValueChange={(next: LeadChoice | null) => {
        onValueChange(next);
      }}
      onInputValueChange={(next, details) => {
        if (details.reason !== "item-press") setSearch(next);
      }}
      itemToStringLabel={(lead: LeadChoice) => `${lead.code} · ${lead.name}`}
      isItemEqualToValue={(item: LeadChoice, selected: LeadChoice) => item.id === selected.id}
      filter={null}
    >
      <ComboboxInput
        id={id}
        placeholder="Farmer, mobile or inquiry number"
        autoComplete="off"
        aria-invalid={invalid === true ? true : undefined}
      />
      <ComboboxContent aria-busy={waiting || undefined}>
        <ComboboxStatus>
          {query.isError ? (
            "Leads couldn't be loaded. Check your connection, then type again."
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
              ? "No leads yet."
              : `No lead matches “${term}”.`}
        </ComboboxEmpty>
        <ComboboxList>
          {(lead: LeadChoice) => (
            <ComboboxItem key={lead.id} value={lead}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate font-mono text-sm">{lead.code}</span>
                <span className="truncate text-xs text-muted-foreground">{lead.name}</span>
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
