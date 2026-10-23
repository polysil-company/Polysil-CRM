"use client";

import { ArrowLeft01Icon, FilterRemoveIcon, Invoice03Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import type { PaginationState } from "@tanstack/react-table";
import type * as React from "react";

import { DataTable, DataTableSkeleton } from "@/components/patterns/data-table";
import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Button } from "@/components/ui/button";
import { quotationListQueryOptions } from "@/features/quotations/api/quotations.queries";
import { useQuotationListParams } from "@/features/quotations/hooks/use-quotation-list-params";
import {
  QUOTATION_COLUMN_LAYOUT,
  QUOTATIONS_EMPTY_FRAME_CLASSES,
  QUOTATIONS_TABLE_FRAME_CLASSES,
  QUOTATIONS_TABLE_LABEL,
} from "@/features/quotations/lib/quotation-table-layout";
import { readFieldErrors } from "@/lib/api/errors";

import { quotationColumns } from "./quotations-columns";

export function QuotationsTableSkeleton(): React.JSX.Element {
  return (
    <DataTableSkeleton
      label={QUOTATIONS_TABLE_LABEL}
      columns={QUOTATION_COLUMN_LAYOUT}
      className={QUOTATIONS_TABLE_FRAME_CLASSES}
    />
  );
}

/**
 * QUOT-001. Every state: skeleton on first load; error with retry and reference; empty with and
 * without filters; a page link that no longer works; and the table. The backend lists newest
 * first and does not sort, so no column has a sort arrow.
 */
export function QuotationsTable(): React.JSX.Element {
  const {
    params,
    pageIndex,
    nextPage,
    previousPage,
    firstPage,
    setPageSize,
    resetFilters,
    activeFilterCount,
  } = useQuotationListParams();
  const query = useQuery(quotationListQueryOptions(params));

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
        className={QUOTATIONS_EMPTY_FRAME_CLASSES}
      />
    );
  }

  return (
    <QueryView
      query={query}
      pending={<QuotationsTableSkeleton />}
      isEmpty={(data) => data.items.length === 0 && pageIndex === 0}
      empty={
        activeFilterCount > 0 ? (
          <EmptyState
            icon={FilterRemoveIcon}
            title="No quotations match these filters"
            description="Remove a filter, or search for a different number, name or mobile number."
            action={
              <Button variant="outline" size="sm" onClick={resetFilters}>
                Clear filters
              </Button>
            }
            className={QUOTATIONS_EMPTY_FRAME_CLASSES}
          />
        ) : (
          <EmptyState
            icon={Invoice03Icon}
            title="No quotations yet"
            description="Quotations are made from a qualified lead. Those you can see appear here, newest first."
            className={QUOTATIONS_EMPTY_FRAME_CLASSES}
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
              description="The quotations that were here have moved on. Start again from the first page."
              action={firstPageAction}
              className={QUOTATIONS_EMPTY_FRAME_CLASSES}
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
            label={QUOTATIONS_TABLE_LABEL}
            columns={quotationColumns}
            data={data.items}
            getRowId={(quotation) => quotation.id}
            rowCount={data.total}
            rowCountCapped={data.totalCapped}
            hasNextPage={data.nextCursor !== null}
            isPaging={pageLoading}
            sorting={[]}
            onSortingChange={() => undefined}
            pagination={{ pageIndex, pageSize: params.pageSize }}
            onPaginationChange={handlePaginationChange}
            isFetching={query.isFetching}
            className={QUOTATIONS_TABLE_FRAME_CLASSES}
          />
        );
      }}
    </QueryView>
  );
}
