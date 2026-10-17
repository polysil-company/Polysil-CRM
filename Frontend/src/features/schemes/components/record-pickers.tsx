"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
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
import { partnerListQueryOptions } from "@/features/partners/api/partners.queries";
import { productListQueryOptions } from "@/features/products/api/products.queries";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

/** A record a scheme can be aimed at: its id, and enough to name it. */
export interface PickedRecord {
  readonly id: string;
  readonly name: string;
  readonly note: string;
}

const SEARCH_DEBOUNCE_MS = 250;

interface SearchResults {
  readonly items: readonly PickedRecord[];
  readonly pending: boolean;
  readonly failed: boolean;
  readonly fetching: boolean;
}

/** A search box that lists what the server finds; choosing one hands it back and clears. */
function SearchCombobox({
  id,
  placeholder,
  noun,
  search,
  onSearch,
  term,
  results,
  onPick,
  ...aria
}: {
  id: string;
  placeholder: string;
  noun: string;
  search: string;
  onSearch: (next: string) => void;
  term: string;
  results: SearchResults;
  onPick: (record: PickedRecord) => void;
  "aria-describedby"?: string | undefined;
}): React.JSX.Element {
  const waiting = search.trim() !== term || results.fetching;
  return (
    <Combobox
      items={results.items}
      value={null}
      onValueChange={(next: PickedRecord | null) => {
        if (next !== null) onPick(next);
        onSearch("");
      }}
      onInputValueChange={(next, details) => {
        if (details.reason !== "item-press") onSearch(next);
      }}
      itemToStringLabel={(record: PickedRecord) => record.name}
      isItemEqualToValue={(item: PickedRecord, selected: PickedRecord) => item.id === selected.id}
      filter={null}
    >
      <ComboboxInput id={id} placeholder={placeholder} autoComplete="off" {...aria} />
      <ComboboxContent aria-busy={waiting || undefined}>
        <ComboboxStatus>
          {results.failed ? (
            `The ${noun}s couldn't be loaded. Check your connection, then type again.`
          ) : results.pending || waiting ? (
            <>
              <Spinner />
              Searching…
            </>
          ) : null}
        </ComboboxStatus>
        <ComboboxEmpty>
          {!waiting && !results.failed
            ? term === ""
              ? `No ${noun}s yet.`
              : `No ${noun} matches “${term}”.`
            : null}
        </ComboboxEmpty>
        <ComboboxList>
          {(record: PickedRecord) => (
            <ComboboxItem key={record.id} value={record}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate">{record.name}</span>
                <span className="truncate text-xs text-muted-foreground">{record.note}</span>
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}

const PARTNER_TYPE_NAMES: Readonly<Record<string, string>> = {
  distributor: "Distributor",
  dealer: "Dealer",
  sub_dealer: "Sub-dealer",
};

/** SCHM-002 · Find an open channel partner by name. */
export function PartnerSearchPicker({
  id,
  onPick,
  placeholder = "Search a distributor, dealer or sub-dealer",
  ...aria
}: {
  id: string;
  onPick: (record: PickedRecord) => void;
  placeholder?: string;
  "aria-describedby"?: string | undefined;
}): React.JSX.Element {
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const query = useInfiniteQuery(
    partnerListQueryOptions({ q: term, type: null, parentId: null, active: true }),
  );
  const items = (query.data?.pages[0]?.items ?? []).slice(0, 20).map((partner) => ({
    id: partner.id,
    name: partner.name,
    note: PARTNER_TYPE_NAMES[partner.type] ?? partner.type,
  }));
  return (
    <SearchCombobox
      id={id}
      placeholder={placeholder}
      noun="partner"
      search={search}
      onSearch={setSearch}
      term={term}
      results={{
        items,
        pending: query.isPending,
        failed: query.isError,
        fetching: query.isFetching,
      }}
      onPick={onPick}
      {...aria}
    />
  );
}

/** SCHM-002 · Find an active product by its code or description. */
export function ProductSearchPicker({
  id,
  onPick,
  ...aria
}: {
  id: string;
  onPick: (record: PickedRecord) => void;
  "aria-describedby"?: string | undefined;
}): React.JSX.Element {
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const query = useQuery(
    productListQueryOptions({ q: term, category: null, quotationCategory: null, active: true }, 1),
  );
  const items = (query.data?.items ?? []).slice(0, 20).map((product) => ({
    id: product.id,
    name: product.description,
    note: `${product.itemCode} · ${product.category}`,
  }));
  return (
    <SearchCombobox
      id={id}
      placeholder="Search a product by code or name"
      noun="product"
      search={search}
      onSearch={setSearch}
      term={term}
      results={{
        items,
        pending: query.isPending,
        failed: query.isError,
        fetching: query.isFetching,
      }}
      onPick={onPick}
      {...aria}
    />
  );
}
