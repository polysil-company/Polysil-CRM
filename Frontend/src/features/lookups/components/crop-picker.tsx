"use client";

import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";

export interface CropPickerProps {
  id: string;
  /** Crop codes, in the order chosen. */
  value: readonly string[];
  onValueChange: (codes: string[]) => void;
  /** The most that may be chosen; the backend takes 10. */
  max: number;
  "aria-invalid"?: true | undefined;
  "aria-describedby"?: string | undefined;
}

/** "Cotton, Groundnut and 1 more" — the closed field's summary. */
export function cropSummary(names: readonly string[]): string {
  const [first, second] = names;
  if (first === undefined) {
    return "";
  }
  if (second === undefined) {
    return first;
  }
  return names.length === 2
    ? `${first}, ${second}`
    : `${first}, ${second} and ${String(names.length - 2)} more`;
}

/**
 * MSTR-002 · Choose a lead's crops from the admin-edited list (`GET /lookups/crops`). Only
 * active crops are offered. Once `max` are chosen the rest are disabled. It validates with
 * the form on submit rather than on blur: opening the list moves focus into it, which would
 * otherwise show an error before anything was chosen.
 */
export function CropPicker({
  id,
  value,
  onValueChange,
  max,
  ...aria
}: CropPickerProps): React.JSX.Element {
  const query = useQuery(lookupListQueryOptions("crops"));
  const crops = (query.data ?? []).filter((crop) => crop.isActive);
  const items = crops.map((crop) => ({ value: crop.code, label: crop.name }));
  const nameOf = (code: string): string => crops.find((crop) => crop.code === code)?.name ?? code;
  const full = value.length >= max;
  const placeholder = query.isPending
    ? "Loading…"
    : query.isError
      ? "Couldn't load the crops"
      : "Choose the crops";

  return (
    <div className="flex items-center gap-2">
      <Select
        multiple
        items={items}
        value={[...value]}
        disabled={query.isPending || query.isError}
        onValueChange={(next) => {
          onValueChange(next.filter((code) => typeof code === "string"));
        }}
      >
        <SelectTrigger id={id} {...aria}>
          {/* A function child replaces the placeholder, so it shows the placeholder itself. */}
          <SelectValue>
            {(selected: unknown) =>
              Array.isArray(selected) && selected.length > 0
                ? cropSummary(selected.filter((code) => typeof code === "string").map(nameOf))
                : placeholder
            }
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem
              key={item.value}
              value={item.value}
              disabled={full ? !value.includes(item.value) : false}
            >
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {query.isError ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            void query.refetch();
          }}
        >
          Try again
        </Button>
      ) : null}
    </div>
  );
}
