"use client";

import { ArrowLeft01Icon, FilterRemoveIcon, PackageIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import type { PaginationState } from "@tanstack/react-table";
import type * as React from "react";

import { DataTable, DataTableSkeleton } from "@/components/patterns/data-table";
import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Button } from "@/components/ui/button";
import { orderListQueryOptions } from "@/features/orders/api/orders.queries";
import { useOrderListParams } from "@/features/orders/hooks/use-order-list-params";
import {
  ORDER_COLUMN_LAYOUT,
  ORDERS_EMPTY_FRAME_CLASSES,
  ORDERS_TABLE_FRAME_CLASSES,
  ORDERS_TABLE_LABEL,
} from "@/features/orders/lib/order-table-layout";
import { readFieldErrors } from "@/lib/api/errors";

import { orderColumns } from "./orders-columns";

export function OrdersTableSkeleton(): React.JSX.Element {
  return (
    <DataTableSkeleton
      label={ORDERS_TABLE_LABEL}
      columns={ORDER_COLUMN_LAYOUT}
      className={ORDERS_TABLE_FRAME_CLASSES}
    />
  );
}

/**
 * SO-001. Every state: skeleton on first load; error with retry and reference; empty with and
 * without filters; a page link that no longer works; and the table. The backend lists newest
 * first and does not sort, so no column has a sort arrow.
 */
export function OrdersTable(): React.JSX.Element {
  const {
    params,
    pageIndex,
    nextPage,
    previousPage,
    firstPage,
    setPageSize,
    resetFilters,
    activeFilterCount,
  } = useOrderListParams();
  const query = useQuery(orderListQueryOptions(params));

  const firstPageAction = (
    <Button variant="outline" size="sm" onClick={firstPage}>
      Go to the first page
    </Button>
  );

  if (query.status === "error" && readFieldErrors(query.error)?.cursor !== undefined) {
    return (
      <EmptyState
        icon={ArrowLeft01Icon}
        title="This page link no longer works"
        description="The link points to a page of an older list. Start again from the first page."
        action={firstPageAction}
        className={ORDERS_EMPTY_FRAME_CLASSES}
      />
    );
  }

  return (
    <QueryView
      query={query}
      pending={<OrdersTableSkeleton />}
      isEmpty={(data) => data.items.length === 0 && pageIndex === 0}
      empty={
        activeFilterCount > 0 ? (
          <EmptyState
            icon={FilterRemoveIcon}
            title="No orders match these filters"
            description="Remove a filter, or search for a different number, party or mobile number."
            action={
              <Button variant="outline" size="sm" onClick={resetFilters}>
                Clear filters
              </Button>
            }
            className={ORDERS_EMPTY_FRAME_CLASSES}
          />
        ) : (
          <EmptyState
            icon={PackageIcon}
            title="No sales orders yet"
            description="Place one from an accepted quotation, or with New order. Orders you can see appear here, newest first."
            className={ORDERS_EMPTY_FRAME_CLASSES}
          />
        )
      }
    >
      {(data) => {
        if (data.items.length === 0) {
          return (
            <EmptyState
              icon={ArrowLeft01Icon}
              title="This page is empty"
              description="The orders that were here have moved on. Start again from the first page."
              action={firstPageAction}
              className={ORDERS_EMPTY_FRAME_CLASSES}
            />
          );
        }

        // While a new page loads, the rows (and their cursor) still belong to the previous page.
        const pageLoading = query.isPlaceholderData;
        const handlePaginationChange = (next: PaginationState): void => {
          if (pageLoading) {
            return;
          }
          if (next.pageSize !== params.pageSize) {
            setPageSize(next.pageSize);
          } else if (next.pageIndex > pageIndex && data.nextCursor !== null) {
            nextPage(data.nextCursor);
          } else if (next.pageIndex < pageIndex) {
            previousPage();
          }
        };

        return (
          <DataTable
            label={ORDERS_TABLE_LABEL}
            columns={orderColumns}
            data={data.items}
            getRowId={(order) => order.id}
            rowCount={data.total}
            rowCountCapped={data.totalCapped}
            hasNextPage={data.nextCursor !== null}
            isPaging={pageLoading}
            sorting={[]}
            onSortingChange={() => undefined}
            pagination={{ pageIndex, pageSize: params.pageSize }}
            onPaginationChange={handlePaginationChange}
            isFetching={query.isFetching}
            className={ORDERS_TABLE_FRAME_CLASSES}
          />
        );
      }}
    </QueryView>
  );
}
