"use client";

import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { FilterPill } from "@/components/patterns/filter-pill";
import { SearchField } from "@/components/patterns/search-field";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { leadSummaryQueryOptions } from "@/features/leads/api/leads.queries";
import { LEAD_SOURCES, LEAD_STATUSES, ORDER_TYPES } from "@/features/leads/api/leads.schemas";
import { useLeadListParams } from "@/features/leads/hooks/use-lead-list-params";
import {
  LEAD_SOURCE_LABELS,
  LEAD_STATUS_LABELS,
  ORDER_TYPE_LABELS,
} from "@/features/leads/lib/lead-labels";
import { useCan } from "@/features/session/hooks/use-session";

import { NewLeadDialog } from "./new-lead-dialog";

/** Search, filters (with live counts) and the primary action for the leads list. */
export function LeadsToolbar(): React.JSX.Element {
  const { params, setFilters, resetFilters, activeFilterCount } = useLeadListParams();
  const { data: summary } = useQuery(leadSummaryQueryOptions());
  const canCreate = useCan("leads", "create");

  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
        <SearchField
          label="Search leads"
          placeholder="Name, phone or lead code"
          value={params.q}
          onSearch={(q) => {
            setFilters({ q });
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          <FilterPill
            label="Status"
            options={LEAD_STATUSES.map((status) => ({
              value: status,
              label: LEAD_STATUS_LABELS[status],
              count: summary?.byStatus[status],
            }))}
            selected={params.status}
            onChange={(status) => {
              setFilters({ status });
            }}
          />
          <FilterPill
            label="Source"
            options={LEAD_SOURCES.map((source) => ({
              value: source,
              label: LEAD_SOURCE_LABELS[source],
              count: summary?.bySource[source],
            }))}
            selected={params.source}
            onChange={(source) => {
              setFilters({ source });
            }}
          />
          <FilterPill
            label="Type"
            options={ORDER_TYPES.map((type) => ({
              value: type,
              label: ORDER_TYPE_LABELS[type],
              count: summary?.byType[type],
            }))}
            selected={params.type}
            onChange={(type) => {
              setFilters({ type });
            }}
          />
          {activeFilterCount > 0 ? (
            <Button variant="ghost" size="sm" onClick={resetFilters}>
              Reset filters
            </Button>
          ) : null}
        </div>
      </div>
      {canCreate ? <NewLeadDialog /> : null}
    </div>
  );
}

/** Mirrors LeadsToolbar: search field, three filter pills, primary button. */
export function LeadsToolbarSkeleton(): React.JSX.Element {
  return (
    <div
      aria-hidden="true"
      className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"
    >
      <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
        <Skeleton className="h-control-md w-full rounded-md md:w-72 pointer-coarse:h-control-lg" />
        <div className="flex flex-wrap items-center gap-2">
          <Skeleton className="h-control-sm w-20 rounded-full" />
          <Skeleton className="h-control-sm w-20 rounded-full" />
          <Skeleton className="h-control-sm w-16 rounded-full" />
        </div>
      </div>
      <Skeleton className="h-control-md w-28 rounded-md" />
    </div>
  );
}
