"use client";

import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { warehousesQueryOptions } from "@/features/stock/api/stock.queries";

/**
 * MSTR-014, DISP-003 · Pick a warehouse, the default first and marked. With `anyLabel` it also
 * offers "every warehouse" as null, for a filter.
 */
export function WarehouseSelect({
  id,
  value,
  onValueChange,
  anyLabel,
  className,
  ...aria
}: {
  id: string;
  value: string | null;
  onValueChange: (warehouseId: string | null) => void;
  /** A filter's "all" option; leave out on a field that needs a warehouse. */
  anyLabel?: string;
  className?: string | undefined;
  "aria-invalid"?: true | undefined;
  "aria-describedby"?: string | undefined;
}): React.JSX.Element {
  const query = useQuery(warehousesQueryOptions());
  const items = (query.data ?? []).map((warehouse) => ({
    value: warehouse.id,
    label: warehouse.isDefault ? `${warehouse.name} (default)` : warehouse.name,
  }));
  return (
    <Select
      items={items}
      value={value}
      disabled={query.isPending || query.isError}
      onValueChange={(next) => {
        onValueChange(typeof next === "string" ? next : null);
      }}
    >
      <SelectTrigger id={id} {...(className === undefined ? {} : { className })} {...aria}>
        <SelectValue
          placeholder={
            query.isError
              ? "Warehouses couldn't be loaded"
              : query.isPending
                ? "Loading warehouses…"
                : (anyLabel ?? "Choose a warehouse")
          }
        />
      </SelectTrigger>
      <SelectContent>
        {anyLabel === undefined ? null : (
          <SelectItem value={null} className="text-muted-foreground">
            {anyLabel}
          </SelectItem>
        )}
        {items.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
