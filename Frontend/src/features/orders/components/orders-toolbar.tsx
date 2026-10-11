"use client";

import { Add01Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { FilterPill, SingleFilterPill } from "@/components/patterns/filter-pill";
import { SearchField } from "@/components/patterns/search-field";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Checkbox } from "@/components/ui/checkbox";
import { Icon } from "@/components/ui/icon";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { exportOrders } from "@/features/orders/api/orders.api";
import { ORDER_STATUSES, ORDER_TYPES } from "@/features/orders/api/orders.schemas";
import { useOrderListParams } from "@/features/orders/hooks/use-order-list-params";
import { ORDER_STATUS_LABELS, ORDER_TYPE_LABELS } from "@/features/orders/lib/order-labels";
import { useCan } from "@/features/session/hooks/use-session";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/orders/components/orders-toolbar.tsx",
  dataId: "SO-001",
});

const STATUS_OPTIONS = ORDER_STATUSES.map((status) => ({
  value: status,
  label: ORDER_STATUS_LABELS[status],
}));
const TYPE_OPTIONS = ORDER_TYPES.map((type) => ({ value: type, label: ORDER_TYPE_LABELS[type] }));

/**
 * SO-001 · Search, filters and "only mine". The backend filters by several statuses at once
 * and by one order type. "New order" types one in without a quotation (SO-005); "Download
 * Excel" saves the list with these filters (SO-006).
 */
export function OrdersToolbar(): React.JSX.Element {
  const { params, setFilters, resetFilters, activeFilterCount } = useOrderListParams();
  const canCreate = useCan("sales_orders", "create");

  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
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
      <div className="flex flex-wrap items-center gap-2">
        <DownloadExcelButton
          download={() => exportOrders(params)}
          fallbackName="orders.xlsx"
          what="orders"
          logger={log}
          dataId="SO-006"
        />
        {canCreate ? (
          <Link href="/sales-orders/new" className={buttonVariants()}>
            <Icon icon={Add01Icon} />
            New order
          </Link>
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
