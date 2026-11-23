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
import { parentSearchQueryOptions } from "@/features/partners/api/partners.queries";
import type { PartnerType } from "@/features/partners/api/partners.schemas";
import { PARTNER_TYPE_LABELS, PARTNER_TYPE_PLURALS } from "@/features/partners/lib/partner-labels";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

/** Search once typing pauses for this long. */
const SEARCH_DEBOUNCE_MS = 250;

/** The partner a new one goes under, as the form keeps it. */
export interface ParentChoice {
  readonly id: string;
  readonly name: string;
  /** "D-001 · Rajkot", when it came from a search. */
  readonly detail?: string;
}

export interface ParentPickerProps {
  id: string;
  /** The parent's type: a distributor for a dealer, a dealer for a sub-dealer. */
  type: PartnerType;
  value: ParentChoice | null;
  onValueChange: (parent: ParentChoice | null) => void;
  "aria-invalid"?: true | undefined;
  "aria-describedby"?: string | undefined;
}

/**
 * CHNL-002 · Pick the partner a new dealer or sub-dealer sits under: the open partners of the
 * type one up, by name, code or contact person (GET /partners), in the caller's scope.
 */
export function ParentPicker({
  id,
  type,
  value,
  onValueChange,
  ...aria
}: ParentPickerProps): React.JSX.Element {
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const query = useQuery(parentSearchQueryOptions(type, term));
  const results: ParentChoice[] = (query.data ?? []).map((partner) => ({
    id: partner.id,
    name: partner.name,
    detail: [partner.code, partner.territory?.name ?? null]
      .filter((part) => part !== null && part !== "")
      .join(" · "),
  }));
  // Keep the chosen parent among the items so the field can still name it during a search.
  const items =
    value !== null && !results.some((parent) => parent.id === value.id)
      ? [value, ...results]
      : results;
  const waiting = search.trim() !== term || query.isFetching;
  const label = PARTNER_TYPE_LABELS[type].toLowerCase();

  return (
    <Combobox
      items={items}
      value={value}
      onValueChange={(next: ParentChoice | null) => {
        onValueChange(next);
      }}
      onInputValueChange={(next, details) => {
        if (details.reason !== "item-press") setSearch(next);
      }}
      itemToStringLabel={(parent: ParentChoice) => parent.name}
      isItemEqualToValue={(item: ParentChoice, selected: ParentChoice) => item.id === selected.id}
      filter={null}
    >
      <ComboboxInput
        id={id}
        placeholder={`The ${label}'s name, code or contact person`}
        autoComplete="off"
        {...aria}
      />
      <ComboboxContent aria-busy={waiting || undefined}>
        <ComboboxStatus>
          {query.isError ? (
            `The ${PARTNER_TYPE_PLURALS[type]} couldn't be loaded. Check your connection, then type again.`
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
              ? `No open ${PARTNER_TYPE_PLURALS[type]} in your area. Add one first.`
              : `No open ${label} matches “${term}”.`}
        </ComboboxEmpty>
        <ComboboxList>
          {(parent: ParentChoice) => (
            <ComboboxItem key={parent.id} value={parent}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate">{parent.name}</span>
                {parent.detail === undefined || parent.detail === "" ? null : (
                  <span className="truncate text-xs text-muted-foreground">{parent.detail}</span>
                )}
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
