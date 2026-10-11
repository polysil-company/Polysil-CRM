"use client";

import { parseAsInteger, parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";

import {
  QUOTATION_CATEGORIES,
  type ProductListParams,
} from "@/features/products/api/products.schemas";

export const PRODUCT_MASTER_TABS = ["products", "price-lists", "tax-rates"] as const;
export type ProductMasterTab = (typeof PRODUCT_MASTER_TABS)[number];

export const PRODUCT_STATUSES = ["active", "off", "all"] as const;
export type ProductStatus = (typeof PRODUCT_STATUSES)[number];

const ACTIVE_OF: Readonly<Record<ProductStatus, boolean | null>> = {
  active: true,
  off: false,
  all: null,
};

/**
 * MSTR-004 · The product master's place in the URL: the tab, and the catalogue's search,
 * category, block, status and page — so a filtered view can be sent to a colleague.
 */
export function useProductMasterParams(): {
  tab: ProductMasterTab;
  status: ProductStatus;
  params: ProductListParams;
  page: number;
  activeFilterCount: number;
  setTab: (tab: ProductMasterTab) => void;
  setFilters: (patch: {
    q?: string;
    category?: string | null;
    quotationCategory?: ProductListParams["quotationCategory"];
    status?: ProductStatus;
  }) => void;
  setPage: (page: number) => void;
  resetFilters: () => void;
} {
  const [values, setValues] = useQueryStates({
    tab: parseAsStringLiteral(PRODUCT_MASTER_TABS).withDefault("products"),
    q: parseAsString.withDefault(""),
    category: parseAsString,
    block: parseAsStringLiteral(QUOTATION_CATEGORIES),
    status: parseAsStringLiteral(PRODUCT_STATUSES).withDefault("active"),
    page: parseAsInteger.withDefault(1),
  });
  const params: ProductListParams = {
    q: values.q.trim(),
    category: values.category,
    quotationCategory: values.block,
    active: ACTIVE_OF[values.status],
  };
  const activeFilterCount =
    (params.q === "" ? 0 : 1) +
    (params.category === null ? 0 : 1) +
    (params.quotationCategory === null ? 0 : 1) +
    (values.status === "active" ? 0 : 1);

  return {
    tab: values.tab,
    status: values.status,
    params,
    page: Math.max(1, values.page),
    activeFilterCount,
    setTab: (tab) => {
      void setValues({ tab: tab === "products" ? null : tab });
    },
    // Any filter change starts again from the first page.
    setFilters: (patch) => {
      void setValues({
        page: null,
        ...(patch.q === undefined ? {} : { q: patch.q === "" ? null : patch.q }),
        ...(patch.category === undefined ? {} : { category: patch.category }),
        ...(patch.quotationCategory === undefined ? {} : { block: patch.quotationCategory }),
        ...(patch.status === undefined
          ? {}
          : { status: patch.status === "active" ? null : patch.status }),
      });
    },
    setPage: (page) => {
      void setValues({ page: page <= 1 ? null : page });
    },
    resetFilters: () => {
      void setValues({ q: null, category: null, block: null, status: null, page: null });
    },
  };
}
