"use client";

import { ArrowLeft01Icon, FilterRemoveIcon, UserAdd01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import type { RowSelectionState, SortingState } from "@tanstack/react-table";
import { useState } from "react";
import type * as React from "react";

import { DataTable, DataTableSkeleton, SelectionBar } from "@/components/patterns/data-table";
import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Button } from "@/components/ui/button";
import { leadListQueryOptions } from "@/features/leads/api/leads.queries";
import { LEAD_SORT_FIELDS, type LeadSortField } from "@/features/leads/api/leads.schemas";
import { useLeadListParams } from "@/features/leads/hooks/use-lead-list-params";
import {
  LEAD_COLUMN_LAYOUT,
  LEADS_EMPTY_FRAME_CLASSES,
  LEADS_TABLE_FRAME_CLASSES,
  LEADS_TABLE_LABEL,
} from "@/features/leads/lib/lead-table-layout";
import { formatInrCompact, formatNumber } from "@/lib/format";

import { leadColumns } from "./leads-columns";

/** Columns the table can sort by. "createdAt" (the default order) has no column. */
const SORTABLE_COLUMNS: readonly LeadSortField[] = [
  "customerName",
  "estimatedValue",
  "followUpAt",
  "winProbability",
];

const EMPTY_SELECTION: RowSelectionState = {};

export function LeadsTableSkeleton(): React.JSX.Element {
  return (
    <DataTableSkeleton
      label={LEADS_TABLE_LABEL}
      columns={LEAD_COLUMN_LAYOUT}
      checkboxColumn={0}
      className={LEADS_TABLE_FRAME_CLASSES}
    />
  );
}

/**
 * LEAD-001. All four states: skeleton on first load, error with retry and
 * reference, empty (with and without filters, and an out-of-range page), and
 * the table. Background refetches keep rows visible.
 */
export function LeadsTable(): React.JSX.Element {
  const { params, setSort, setPage, resetFilters, activeFilterCount } = useLeadListParams();
  const query = useQuery(leadListQueryOptions(params));

  // Selection belongs to one exact list (filters + sort + page); any change clears it.
  const listKey = JSON.stringify(params);
  const [selection, setSelection] = useState<{ listKey: string; rows: RowSelectionState }>({
    listKey,
    rows: EMPTY_SELECTION,
  });
  const rowSelection = selection.listKey === listKey ? selection.rows : EMPTY_SELECTION;

  const sorting: SortingState = SORTABLE_COLUMNS.includes(params.sort)
    ? [{ id: params.sort, desc: params.order === "desc" }]
    : [];

  const handleSortingChange = (next: SortingState): void => {
    const first = next[0];
    if (first === undefined) {
      setSort("createdAt", "desc");
      return;
    }
    const field = LEAD_SORT_FIELDS.find((candidate) => candidate === first.id);
    if (field !== undefined) {
      setSort(field, first.desc ? "desc" : "asc");
    }
  };

  return (
    <QueryView
      query={query}
      pending={<LeadsTableSkeleton />}
      isEmpty={(data) => data.total === 0}
      empty={
        activeFilterCount > 0 ? (
          <EmptyState
            icon={FilterRemoveIcon}
            title="No leads match these filters"
            description="Remove a filter, or search for a different name, phone number or lead code."
            action={
              <Button variant="outline" size="sm" onClick={resetFilters}>
                Clear filters
              </Button>
            }
            className={LEADS_EMPTY_FRAME_CLASSES}
          />
        ) : (
          <EmptyState
            icon={UserAdd01Icon}
            title="No leads yet"
            description="Leads from WhatsApp, the website, QR codes and field visits appear here as they are captured."
            className={LEADS_EMPTY_FRAME_CLASSES}
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
              description={`There are ${formatNumber(data.total)} leads, but none on page ${formatNumber(data.page)}.`}
              action={
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setPage(1, data.pageSize);
                  }}
                >
                  Go to the first page
                </Button>
              }
              className={LEADS_EMPTY_FRAME_CLASSES}
            />
          );
        }

        const selectedLeads = data.items.filter((lead) => rowSelection[lead.id] === true);
        const selectedValue = selectedLeads.reduce(
          (sum, lead) => sum + (lead.estimatedValue ?? 0),
          0,
        );

        return (
          <>
            <DataTable
              label={LEADS_TABLE_LABEL}
              columns={leadColumns}
              data={data.items}
              getRowId={(lead) => lead.id}
              rowCount={data.total}
              sorting={sorting}
              onSortingChange={handleSortingChange}
              pagination={{ pageIndex: data.page - 1, pageSize: data.pageSize }}
              onPaginationChange={(next) => {
                setPage(next.pageIndex + 1, next.pageSize);
              }}
              rowSelection={rowSelection}
              onRowSelectionChange={(rows) => {
                setSelection({ listKey, rows });
              }}
              isFetching={query.isFetching}
              className={LEADS_TABLE_FRAME_CLASSES}
            />
            <SelectionBar
              count={selectedLeads.length}
              summary={`${formatInrCompact(selectedValue)} estimated on this page`}
              onClear={() => {
                setSelection({ listKey, rows: EMPTY_SELECTION });
              }}
            />
          </>
        );
      }}
    </QueryView>
  );
}
