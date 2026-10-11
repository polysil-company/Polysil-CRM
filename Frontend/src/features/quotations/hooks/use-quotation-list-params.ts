"use client";

import {
  parseAsArrayOf,
  parseAsBoolean,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
  useQueryStates,
} from "nuqs";

import {
  QUOTATION_PAGE_SIZES,
  QUOTATION_STATUSES,
  SALES_TYPES,
  type QuotationListParams,
  type QuotationStatus,
  type SalesType,
} from "@/features/quotations/api/quotations.schemas";

const DEFAULT_PAGE_SIZE = QUOTATION_PAGE_SIZES[0];

/**
 * URL ⇄ state for the Quotations page, as the lead list does it: filters and the page live in
 * the URL, and `cursors` keeps the cursor of every page moved forward through. `versions=all`
 * shows superseded versions too; by default only the current version of each number shows.
 */
export const quotationListSearchParams = {
  cursors: parseAsArrayOf(parseAsString).withDefault([]),
  pageSize: parseAsInteger.withDefault(DEFAULT_PAGE_SIZE),
  q: parseAsString.withDefault(""),
  status: parseAsArrayOf(parseAsStringLiteral(QUOTATION_STATUSES)).withDefault([]),
  type: parseAsStringLiteral(SALES_TYPES),
  allVersions: parseAsBoolean.withDefault(false),
};

export interface QuotationFilterPatch {
  readonly q?: string;
  readonly status?: readonly QuotationStatus[];
  readonly type?: SalesType | null;
  readonly allVersions?: boolean;
}

export interface QuotationListParamsControls {
  readonly params: QuotationListParams;
  /** 0 on the first page, one more for each page moved forward. */
  readonly pageIndex: number;
  /** Active filters, including a search and showing every version. */
  readonly activeFilterCount: number;
  /** Changing a filter returns to the first page: cursors belong to one exact list. */
  setFilters: (patch: QuotationFilterPatch) => void;
  nextPage: (cursor: string) => void;
  previousPage: () => void;
  firstPage: () => void;
  setPageSize: (pageSize: number) => void;
  resetFilters: () => void;
}

function normalizePageSize(value: number): number {
  return QUOTATION_PAGE_SIZES.find((size) => size === value) ?? DEFAULT_PAGE_SIZE;
}

export function useQuotationListParams(): QuotationListParamsControls {
  const [values, setValues] = useQueryStates(quotationListSearchParams, {
    history: "replace",
    clearOnDefault: true,
  });

  const cursors = values.cursors.filter((cursor) => cursor !== "");
  const params: QuotationListParams = {
    cursor: cursors.at(-1) ?? null,
    pageSize: normalizePageSize(values.pageSize),
    q: values.q.trim(),
    status: values.status,
    salesType: values.type,
    currentOnly: !values.allVersions,
    leadId: null,
  };

  const activeFilterCount = [
    params.q !== "",
    params.status.length > 0,
    params.salesType !== null,
    !params.currentOnly,
  ].filter(Boolean).length;

  return {
    params,
    pageIndex: cursors.length,
    activeFilterCount,
    setFilters: (patch) => {
      void setValues({
        cursors: null,
        ...(patch.q === undefined ? {} : { q: patch.q }),
        ...(patch.status === undefined ? {} : { status: [...patch.status] }),
        ...(patch.type === undefined ? {} : { type: patch.type }),
        ...(patch.allVersions === undefined ? {} : { allVersions: patch.allVersions }),
      });
    },
    nextPage: (cursor) => {
      void setValues({ cursors: [...cursors, cursor] });
    },
    previousPage: () => {
      void setValues({ cursors: cursors.slice(0, -1) });
    },
    firstPage: () => {
      void setValues({ cursors: null });
    },
    setPageSize: (pageSize) => {
      void setValues({ pageSize: normalizePageSize(pageSize), cursors: null });
    },
    resetFilters: () => {
      void setValues({ q: null, status: null, type: null, allVersions: null, cursors: null });
    },
  };
}
