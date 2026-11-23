"use client";

import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import {
  availabilityQueryOptions,
  warehousesQueryOptions,
} from "@/features/stock/api/stock.queries";
import { MAX_AVAILABILITY_PRODUCTS } from "@/features/stock/api/stock.schemas";
import { quantityText } from "@/features/stock/lib/stock-labels";
import { cn } from "@/lib/utils";

import { WarehouseSelect } from "./warehouse-select";

/**
 * DISP-003 · "Order to": the warehouse the order is served from. Null means the default, which
 * the picker shows as chosen. Staff only; a dealer's order always comes from the default.
 */
export function OrderToField({
  value,
  onValueChange,
  className,
}: {
  value: string | null;
  onValueChange: (warehouseId: string | null) => void;
  className?: string;
}): React.JSX.Element {
  const warehouses = useQuery(warehousesQueryOptions());
  const fallback = warehouses.data?.find((warehouse) => warehouse.isDefault)?.id ?? null;
  return (
    <Field className={className}>
      <FieldLabel htmlFor="order-to">Order to</FieldLabel>
      <WarehouseSelect
        id="order-to"
        value={value ?? fallback}
        aria-describedby="order-to-help"
        onValueChange={(next) => {
          // Picking the default is the same as leaving it: the backend serves from it either way.
          onValueChange(next === fallback ? null : next);
        }}
      />
      <FieldDescription id="order-to-help">
        The warehouse it ships from. Stock below is for this warehouse; a shortfall warns and never
        blocks the order.
      </FieldDescription>
    </Field>
  );
}

/**
 * DISP-003 · Where a dispatch's goods left from: the order's warehouse (or the default) unless
 * Dispatch picks another. The stock comes out of this one.
 */
export function LeftFromField({
  value,
  onValueChange,
}: {
  value: string | null;
  onValueChange: (warehouseId: string | null) => void;
}): React.JSX.Element {
  const warehouses = useQuery(warehousesQueryOptions());
  const fallback = warehouses.data?.find((warehouse) => warehouse.isDefault)?.id ?? null;
  return (
    <Field className="sm:col-span-2">
      <FieldLabel htmlFor="dispatch-warehouse">Left from</FieldLabel>
      <WarehouseSelect
        id="dispatch-warehouse"
        value={value ?? fallback}
        aria-describedby="dispatch-warehouse-help"
        onValueChange={onValueChange}
      />
      <FieldDescription id="dispatch-warehouse-help">
        The stock comes out of this warehouse.
      </FieldDescription>
    </Field>
  );
}

export interface AvailabilityLine {
  readonly key: string;
  readonly productId: string;
  readonly name: string;
  readonly qty: string;
  readonly uom: string;
}

/**
 * DISP-003 · What the chosen warehouse has for each line's product: "850 available", or
 * "Short by 50" in amber when the line wants more. Re-read when the warehouse or lines change.
 */
export function LineAvailability({
  warehouseId,
  lines,
}: {
  warehouseId: string | null;
  lines: readonly AvailabilityLine[];
}): React.JSX.Element | null {
  const warehouses = useQuery(warehousesQueryOptions());
  const resolved =
    warehouseId ?? warehouses.data?.find((warehouse) => warehouse.isDefault)?.id ?? null;
  const productIds = [...new Set(lines.map((line) => line.productId))]
    .sort()
    .slice(0, MAX_AVAILABILITY_PRODUCTS);
  const query = useQuery({
    ...availabilityQueryOptions(resolved ?? "", productIds),
    enabled: resolved !== null && productIds.length > 0,
  });
  if (lines.length === 0) return null;
  const warehouseName =
    warehouses.data?.find((warehouse) => warehouse.id === resolved)?.name ?? "the warehouse";

  return (
    <section
      aria-label="Stock for these lines"
      className="flex flex-col gap-2 rounded-lg border border-border p-3"
    >
      <h3 className="text-sm font-medium text-foreground">Stock at {warehouseName}</h3>
      {query.isError ? (
        <p className="text-sm text-muted-foreground">Stock couldn&apos;t be read just now.</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {lines.map((line) => {
            const item = query.data?.items.find((entry) => entry.productId === line.productId);
            const wanted = Number(line.qty);
            const available = item === undefined ? null : Number(item.available);
            const short = available !== null && Number.isFinite(wanted) && wanted > available;
            return (
              <li key={line.key} className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className="min-w-0 truncate text-foreground">{line.name}</span>
                <span
                  className={cn(
                    "tabular-nums",
                    short ? "font-medium text-warning" : "text-muted-foreground",
                  )}
                >
                  {item === undefined
                    ? query.isFetching
                      ? "Checking…"
                      : "—"
                    : short
                      ? `Short by ${quantityText(String(wanted - Math.max(0, available ?? 0)), line.uom)}`
                      : `${quantityText(item.available, line.uom)} available`}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
