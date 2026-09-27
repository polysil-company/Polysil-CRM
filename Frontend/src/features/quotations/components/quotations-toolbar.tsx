"use client";

import type * as React from "react";

import { FilterPill, SingleFilterPill } from "@/components/patterns/filter-pill";
import { SearchField } from "@/components/patterns/search-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { QUOTATION_STATUSES, SALES_TYPES } from "@/features/quotations/api/quotations.schemas";
import { useQuotationListParams } from "@/features/quotations/hooks/use-quotation-list-params";
import {
  QUOTATION_STATUS_LABELS,
  SALES_TYPE_LABELS,
} from "@/features/quotations/lib/quotation-labels";

const STATUS_OPTIONS = QUOTATION_STATUSES.map((status) => ({
  value: status,
  label: QUOTATION_STATUS_LABELS[status],
}));
const TYPE_OPTIONS = SALES_TYPES.map((type) => ({ value: type, label: SALES_TYPE_LABELS[type] }));

/**
 * QUOT-001 · Search, filters and "every version". The backend filters by several statuses at
 * once and by one sales type. New quotations start from a lead, so there is no New button here.
 */
export function QuotationsToolbar(): React.JSX.Element {
  const { params, setFilters, resetFilters, activeFilterCount } = useQuotationListParams();

  return (
    <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
      <SearchField
        label="Search quotations"
        placeholder="Number, name or mobile"
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
          selected={params.salesType}
          onChange={(type) => {
            setFilters({ type });
          }}
        />
        <div className="flex items-center gap-2 px-1">
          <Checkbox
            id="quotations-all-versions"
            checked={!params.currentOnly}
            onCheckedChange={(checked) => {
              setFilters({ allVersions: checked });
            }}
          />
          <Label
            htmlFor="quotations-all-versions"
            className="text-sm font-normal text-muted-foreground"
          >
            Show older versions
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

/** Mirrors QuotationsToolbar: search field, two filter pills and the versions switch. */
export function QuotationsToolbarSkeleton(): React.JSX.Element {
  return (
    <div
      aria-hidden="true"
      className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center"
    >
      <Skeleton className="h-control-md w-full rounded-md md:w-72 pointer-coarse:h-control-lg" />
      <div className="flex flex-wrap items-center gap-2">
        <Skeleton className="h-control-sm w-20 rounded-full" />
        <Skeleton className="h-control-sm w-16 rounded-full" />
        <Skeleton className="h-5 w-40" />
      </div>
    </div>
  );
}
