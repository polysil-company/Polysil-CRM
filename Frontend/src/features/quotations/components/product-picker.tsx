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
import { productSearchQueryOptions } from "@/features/quotations/api/quotations.queries";
import type { ProductPick } from "@/features/quotations/api/quotations.schemas";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

/** Search once typing pauses for this long. */
const SEARCH_DEBOUNCE_MS = 250;

export interface ProductPickerProps {
  id: string;
  value: ProductPick | null;
  onValueChange: (product: ProductPick | null) => void;
  "aria-label"?: string;
  "aria-invalid"?: true | undefined;
  "aria-describedby"?: string | undefined;
}

/**
 * MSTR-003 · Pick a product by typing part of its description. The catalogue is searched on
 * the server (it runs to a thousand rows); opening the picker lists the first ones. Each option
 * names its unit and HSN, since two sizes of one pipe read alike.
 */
export function ProductPicker({
  id,
  value,
  onValueChange,
  ...aria
}: ProductPickerProps): React.JSX.Element {
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const query = useQuery(productSearchQueryOptions(term));

  const results: readonly ProductPick[] = query.data ?? [];
  // Keep the chosen product among the items, so the field can still name it during a search.
  const items =
    value !== null && !results.some((product) => product.id === value.id)
      ? [value, ...results]
      : results;
  const waiting = search.trim() !== term || query.isFetching;

  return (
    <Combobox
      items={items}
      value={value}
      onValueChange={(next: ProductPick | null) => {
        onValueChange(next);
      }}
      onInputValueChange={(next, details) => {
        if (details.reason !== "item-press") {
          setSearch(next);
        }
      }}
      itemToStringLabel={(product: ProductPick) => product.description}
      isItemEqualToValue={(item: ProductPick, selected: ProductPick) => item.id === selected.id}
      filter={null}
    >
      <ComboboxInput id={id} placeholder="Search a product" autoComplete="off" {...aria} />
      <ComboboxContent aria-busy={waiting || undefined}>
        <ComboboxStatus>
          {query.isError ? (
            "Products couldn't be loaded. Check your connection, then type again."
          ) : waiting ? (
            <>
              <Spinner />
              Searching…
            </>
          ) : null}
        </ComboboxStatus>
        <ComboboxEmpty>
          {term !== "" && !waiting && !query.isError ? `No product matches “${term}”.` : null}
        </ComboboxEmpty>
        <ComboboxList>
          {(product: ProductPick) => (
            <ComboboxItem key={product.id} value={product}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate">{product.description}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {product.uom}
                  {product.hsnCode === null ? "" : ` · HSN ${product.hsnCode}`}
                  {product.code === null ? "" : ` · ${product.code}`}
                </span>
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
