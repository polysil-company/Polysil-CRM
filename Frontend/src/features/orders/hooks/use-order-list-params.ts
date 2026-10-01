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
  DEFAULT_ORDER_PAGE_SIZE,
  ORDER_PAGE_SIZE_OPTIONS,
  ORDER_STATUSES,
  ORDER_TYPES,
  type OrderListParams,
  type OrderStatus,
  type OrderType,
} from "@/features/orders/api/orders.schemas";

/**
 * URL ⇄ state for the Sales orders page, as the quotation list does it: filters and the page
 * live in the URL, and `cursors` keeps the cursor of every page moved forward through.
 * `mine=true` shows only the signed-in user's own orders.
 */
export const orderListSearchParams = {
  cursors: parseAsArrayOf(parseAsString).withDefault([]),
  pageSize: parseAsInteger.withDefault(DEFAULT_ORDER_PAGE_SIZE),
  q: parseAsString.withDefault(""),
  status: parseAsArrayOf(parseAsStringLiteral(ORDER_STATUSES)).withDefault([]),
  type: parseAsStringLiteral(ORDER_TYPES),
  mine: parseAsBoolean.withDefault(false),
};

export interface OrderFilterPatch {
  readonly q?: string;
  readonly status?: readonly OrderStatus[];
  readonly type?: OrderType | null;
  readonly mine?: boolean;
}

export interface OrderListParamsControls {
  readonly params: OrderListParams;
  /** 0 on the first page, one more for each page moved forward. */
  readonly pageIndex: number;
  /** Active filters, including a search and "only mine". */
  readonly activeFilterCount: number;
  /** Changing a filter returns to the first page: cursors belong to one exact list. */
  setFilters: (patch: OrderFilterPatch) => void;
  nextPage: (cursor: string) => void;
  previousPage: () => void;
  firstPage: () => void;
  setPageSize: (pageSize: number) => void;
  resetFilters: () => void;
}

function normalizePageSize(value: number): number {
  return ORDER_PAGE_SIZE_OPTIONS.find((size) => size === value) ?? DEFAULT_ORDER_PAGE_SIZE;
}

export function useOrderListParams(): OrderListParamsControls {
  const [values, setValues] = useQueryStates(orderListSearchParams, {
    history: "replace",
    clearOnDefault: true,
  });

  const cursors = values.cursors.filter((cursor) => cursor !== "");
  const params: OrderListParams = {
    cursor: cursors.at(-1) ?? null,
    pageSize: normalizePageSize(values.pageSize),
    q: values.q.trim(),
    status: values.status,
    orderType: values.type,
    mine: values.mine,
    leadId: null,
  };

  const activeFilterCount = [
    params.q !== "",
    params.status.length > 0,
    params.orderType !== null,
    params.mine,
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
        ...(patch.mine === undefined ? {} : { mine: patch.mine }),
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
      void setValues({ q: null, status: null, type: null, mine: null, cursors: null });
    },
  };
}
