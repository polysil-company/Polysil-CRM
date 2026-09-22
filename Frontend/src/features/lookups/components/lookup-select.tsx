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
import type { LookupList } from "@/features/lookups/api/lookups.schemas";

export interface LookupSelectProps {
  id: string;
  list: LookupList;
  /** A code from the list, or null for none. */
  value: string | null;
  onValueChange: (code: string | null) => void;
  onBlur?: () => void;
  placeholder: string;
  /**
   * Offers "Not set", so a field that may be left empty can be emptied again. Without it a
   * chosen code can only be swapped for another one. Default false.
   */
  clearable?: boolean;
  "aria-invalid"?: true | undefined;
  "aria-describedby"?: string | undefined;
}

/** What the closed field says while the list is on its way, or once it failed. */
function fieldPlaceholder(isPending: boolean, isError: boolean, placeholder: string): string {
  if (isPending) {
    return "Loading…";
  }
  if (isError) {
    return "Couldn't load the list";
  }
  return placeholder;
}

/**
 * MSTR-002 · Choose from one of the admin-edited lists. Only active rows are offered: the
 * backend refuses new records that use an inactive one. While the list loads the field says
 * so; if it fails, a retry sits beside it instead of an empty menu.
 */
export function LookupSelect({
  id,
  list,
  value,
  onValueChange,
  onBlur,
  placeholder,
  clearable = false,
  ...aria
}: LookupSelectProps): React.JSX.Element {
  const query = useQuery(lookupListQueryOptions(list));
  const items = (query.data ?? [])
    .filter((item) => item.isActive)
    .map((item) => ({ value: item.code, label: item.name }));

  const unavailable = query.isPending || query.isError;

  return (
    <div className="flex items-center gap-2">
      <Select
        items={items}
        value={value}
        disabled={unavailable}
        onValueChange={(next) => {
          if (typeof next === "string") {
            onValueChange(next);
            return;
          }
          // Base UI sends null for the "Not set" row; ignored on a field that needs a value.
          if (clearable && next === null) {
            onValueChange(null);
          }
        }}
      >
        <SelectTrigger id={id} onBlur={onBlur} {...aria}>
          <SelectValue
            placeholder={fieldPlaceholder(query.isPending, query.isError, placeholder)}
          />
        </SelectTrigger>
        <SelectContent>
          {clearable ? (
            <SelectItem value={null} className="text-muted-foreground">
              Not set
            </SelectItem>
          ) : null}
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
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
