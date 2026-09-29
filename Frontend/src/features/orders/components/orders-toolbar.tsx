"use client";

import type * as React from "react";

import { FilterPill, SingleFilterPill } from "@/components/patterns/filter-pill";
import { SearchField } from "@/components/patterns/search-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ORDER_STATUSES, ORDER_TYPES } from "@/features/orders/api/orders.schemas";
import { useOrderListParams } from "@/features/orders/hooks/use-order-list-params";
import { ORDER_STATUS_LABELS, ORDER_TYPE_LABELS } from "@/features/orders/lib/order-labels";

const STATUS_OPTIONS = ORDER_STATUSES.map((status) => ({
  value: status,
  label: ORDER_STATUS_LABELS[status],
}));
const TYPE_OPTIONS = ORDER_TYPES.map((type) => ({ value: type, label: ORDER_TYPE_LABELS[type] }));

/**
 * SO-001 · Search, filters and "only mine". The backend filters by several statuses at once
 * and by one order type. Orders start from an accepted quotation, so there is no New button.
 */
export function OrdersToolbar(): React.JSX.Element {
  const { params, setFilters, resetFilters, activeFilterCount } = useOrderListParams();

  return (
    <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
      <SearchField
        label="Search orders"
        placeholder="Number, party or mobile"
        value={params.q}
        onSearch={(q) => {
          setFilters({ q });
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <FilterPill
          label="Status"
          options={STATUS_OPTIONS}
          selected={params.status}
          onChange={(status) => {
            setFilters({ status });
          }}
        />
        <SingleFilterPill
          label="Type"
          options={TYPE_OPTIONS}
          selected={params.orderType}
          onChange={(type) => {
            setFilters({ type });
          }}
        />
        <div className="flex items-center gap-2 px-1">
          <Checkbox
            id="orders-only-mine"
            checked={params.mine}
            onCheckedChange={(checked) => {
              setFilters({ mine: checked });
            }}
          />
          <Label htmlFor="orders-only-mine" className="text-sm font-normal text-muted-foreground">
            Only my orders
          </Label>
        </div>
        {activeFilterCount > 0 ? (
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            Reset filters
          </Button>
        ) : null}
      </div>
    </div>
  );
}

/** Mirrors OrdersToolbar: search field, two filter pills and the "only mine" switch. */
export function OrdersToolbarSkeleton(): React.JSX.Element {
  return (
    <div
      aria-hidden="true"
      className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center"
    >
      <Skeleton className="h-control-md w-full rounded-md md:w-72 pointer-coarse:h-control-lg" />
      <div className="flex flex-wrap items-center gap-2">
        <Skeleton className="h-control-sm w-20 rounded-full" />
        <Skeleton className="h-control-sm w-16 rounded-full" />
        <Skeleton className="h-5 w-32" />
      </div>
    </div>
  );
}
