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
import { partnerSearchQueryOptions } from "@/features/leads/api/leads.queries";
import { partnerTypeLabel } from "@/features/leads/lib/lead-labels";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

/** Search once typing pauses for this long. */
const SEARCH_DEBOUNCE_MS = 250;

/** A dealer as a form keeps it: enough to send its id and to name it in the field. */
export interface DealerChoice {
  readonly id: string;
  readonly name: string;
  /** "Dealer · Rajkot", when it came from a search. */
  readonly detail?: string;
}

export interface DealerPickerProps {
  id: string;
  value: DealerChoice | null;
  onValueChange: (dealer: DealerChoice | null) => void;
}

/**
 * LEAD-008 · Pick a channel partner by name, code or contact person, from those in the user's
 * area. Clearing the field leaves it empty; the choice is optional.
 */
export function DealerPicker({ id, value, onValueChange }: DealerPickerProps): React.JSX.Element {
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const query = useQuery(partnerSearchQueryOptions(term));
  const results: DealerChoice[] = (query.data ?? []).map((partner) => ({
    id: partner.id,
    name: partner.name,
    detail: [partnerTypeLabel(partner.partnerType), partner.territoryName]
      .filter((part) => part !== null)
      .join(" · "),
  }));
  // Keep the chosen dealer among the items so the field can still name it during a search.
  const items =
    value !== null && !results.some((dealer) => dealer.id === value.id)
      ? [value, ...results]
      : results;
  const waiting = search.trim() !== term || query.isFetching;

  return (
    <Combobox
      items={items}
      value={value}
      onValueChange={(next: DealerChoice | null) => {
        onValueChange(next);
      }}
      onInputValueChange={(next, details) => {
        if (details.reason !== "item-press") setSearch(next);
      }}
      itemToStringLabel={(dealer: DealerChoice) => dealer.name}
      isItemEqualToValue={(item: DealerChoice, selected: DealerChoice) => item.id === selected.id}
      filter={null}
    >
      <ComboboxInput id={id} placeholder="Dealer name, code or contact person" autoComplete="off" />
      <ComboboxContent aria-busy={waiting || undefined}>
        <ComboboxStatus>
          {query.isError ? (
            "Dealers couldn't be loaded. Check your connection, then type again."
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
              ? "No dealers in your area."
              : `No dealer matches “${term}”.`}
        </ComboboxEmpty>
        <ComboboxList>
          {(dealer: DealerChoice) => (
            <ComboboxItem key={dealer.id} value={dealer}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate">{dealer.name}</span>
                {dealer.detail === undefined || dealer.detail === "" ? null : (
                  <span className="truncate text-xs text-muted-foreground">{dealer.detail}</span>
                )}
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
