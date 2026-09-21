"use client";

import {
  parseAsArrayOf,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
  useQueryStates,
} from "nuqs";

import {
  LEAD_PAGE_SIZES,
  LEAD_SORT_FIELDS,
  LEAD_SOURCES,
  LEAD_STATUSES,
  ORDER_TYPES,
  SORT_ORDERS,
  type LeadListParams,
  type LeadSortField,
  type LeadSource,
  type LeadStatus,
  type OrderType,
  type SortOrder,
} from "@/features/leads/api/leads.schemas";

const DEFAULT_PAGE_SIZE = LEAD_PAGE_SIZES[0];

/**
 * URL ⇄ state parsers. Filters, sort and page live in the URL, so a filtered
 * list can be bookmarked or sent to a colleague. Defaults are left out of the URL.
 */
export const leadListSearchParams = {
  page: parseAsInteger.withDefault(1),
  pageSize: parseAsInteger.withDefault(DEFAULT_PAGE_SIZE),
  sort: parseAsStringLiteral(LEAD_SORT_FIELDS).withDefault("createdAt"),
  order: parseAsStringLiteral(SORT_ORDERS).withDefault("desc"),
  q: parseAsString.withDefault(""),
  status: parseAsArrayOf(parseAsStringLiteral(LEAD_STATUSES)).withDefault([]),
  source: parseAsArrayOf(parseAsStringLiteral(LEAD_SOURCES)).withDefault([]),
  type: parseAsArrayOf(parseAsStringLiteral(ORDER_TYPES)).withDefault([]),
};

export interface LeadFilterPatch {
  readonly q?: string;
  readonly status?: readonly LeadStatus[];
  readonly source?: readonly LeadSource[];
  readonly type?: readonly OrderType[];
}

export interface LeadListParamsControls {
  readonly params: LeadListParams;
  /** Active filters, including a search. */
  readonly activeFilterCount: number;
  /** Changing a filter always returns to page 1. */
  setFilters: (patch: LeadFilterPatch) => void;
  setSort: (sort: LeadSortField, order: SortOrder) => void;
  setPage: (page: number, pageSize: number) => void;
  resetFilters: () => void;
}

function normalizePageSize(value: number): number {
  return LEAD_PAGE_SIZES.find((size) => size === value) ?? DEFAULT_PAGE_SIZE;
}

export function useLeadListParams(): LeadListParamsControls {
  const [values, setValues] = useQueryStates(leadListSearchParams, {
    history: "replace",
    clearOnDefault: true,
  });

  const params: LeadListParams = {
    page: Math.max(1, values.page),
    pageSize: normalizePageSize(values.pageSize),
    sort: values.sort,
    order: values.order,
    q: values.q,
    status: values.status,
    source: values.source,
    type: values.type,
  };

  const activeFilterCount = [
    params.q !== "",
    params.status.length > 0,
    params.source.length > 0,
    params.type.length > 0,
  ].filter(Boolean).length;

  return {
    params,
    activeFilterCount,
    setFilters: (patch) => {
      void setValues({
        page: null,
        ...(patch.q === undefined ? {} : { q: patch.q }),
        ...(patch.status === undefined ? {} : { status: [...patch.status] }),
        ...(patch.source === undefined ? {} : { source: [...patch.source] }),
        ...(patch.type === undefined ? {} : { type: [...patch.type] }),
      });
    },
    setSort: (sort, order) => {
      void setValues({ sort, order, page: null });
    },
    setPage: (page, pageSize) => {
      void setValues({ page, pageSize });
    },
    resetFilters: () => {
      void setValues({ q: null, status: null, source: null, type: null, page: null });
    },
  };
}
