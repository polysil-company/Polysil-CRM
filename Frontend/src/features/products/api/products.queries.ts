import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import {
  getHsnHistory,
  getPriceList,
  listProductCategories,
  listUoms,
  listPriceListItems,
  listPriceLists,
  listProducts,
  listTaxRates,
} from "./products.api";
import type { PriceListSalesTypeFilter, ProductListParams } from "./products.schemas";

/**
 * Query keys for the product master. A product, a code's slab or a list's rates change what
 * the others show (a slab shows on every product under its code), so mutations invalidate
 * `productKeys.all`.
 */
export const productKeys = {
  all: ["product-master"] as const,
  products: (params: ProductListParams, page: number) =>
    [...productKeys.all, "products", params, page] as const,
  categories: () => [...productKeys.all, "categories"] as const,
  uoms: () => [...productKeys.all, "uoms"] as const,
  hsn: (productId: string) => [...productKeys.all, "hsn", productId] as const,
  taxRates: (hsnCode: string | null, inForce: boolean, page: number) =>
    [...productKeys.all, "tax-rates", hsnCode, inForce, page] as const,
  priceLists: (
    status: "draft" | "published" | null,
    salesType: PriceListSalesTypeFilter | null,
    page: number,
  ) => [...productKeys.all, "price-lists", status, salesType, page] as const,
  priceList: (listId: string) => [...productKeys.all, "price-list", listId] as const,
  items: (listId: string, q: string, unpriced: boolean, page: number) =>
    [...productKeys.all, "items", listId, q, unpriced, page] as const,
};

/** MSTR-004 · A page of the catalogue; the previous page stays while the next loads. */
export function productListQueryOptions(params: ProductListParams, page: number) {
  return queryOptions({
    queryKey: productKeys.products(params, page),
    queryFn: ({ signal }) => listProducts({ ...params, page }, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "MSTR-004" },
  });
}

/** MSTR-004 · Every product category (BE-024); they change only with a migration. */
export function productCategoriesQueryOptions() {
  return queryOptions({
    queryKey: productKeys.categories(),
    queryFn: ({ signal }) => listProductCategories(signal),
    staleTime: 30 * 60_000,
    meta: { dataId: "MSTR-004" },
  });
}

/** MSTR-004 · Every unit with its decimals (BE-024). */
export function uomsQueryOptions() {
  return queryOptions({
    queryKey: productKeys.uoms(),
    queryFn: ({ signal }) => listUoms(signal),
    staleTime: 30 * 60_000,
    meta: { dataId: "MSTR-004" },
  });
}

/** MSTR-005 · One product's classifications. */
export function hsnHistoryQueryOptions(productId: string) {
  return queryOptions({
    queryKey: productKeys.hsn(productId),
    queryFn: ({ signal }) => getHsnHistory(productId, signal),
    meta: { dataId: "MSTR-005" },
  });
}

/** MSTR-005 · A page of tax rates. */
export function taxRateListQueryOptions(hsnCode: string | null, inForce: boolean, page: number) {
  return queryOptions({
    queryKey: productKeys.taxRates(hsnCode, inForce, page),
    queryFn: ({ signal }) => listTaxRates({ hsnCode, inForce, page }, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "MSTR-005" },
  });
}

/** MSTR-006 · A page of price lists. */
export function priceListListQueryOptions(
  status: "draft" | "published" | null,
  salesType: PriceListSalesTypeFilter | null,
  page: number,
) {
  return queryOptions({
    queryKey: productKeys.priceLists(status, salesType, page),
    queryFn: ({ signal }) => listPriceLists({ status, salesType, page }, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "MSTR-006" },
  });
}

/** MSTR-006 · One price list's header. */
export function priceListQueryOptions(listId: string) {
  return queryOptions({
    queryKey: productKeys.priceList(listId),
    queryFn: ({ signal }) => getPriceList(listId, signal),
    meta: { dataId: "MSTR-006" },
  });
}

/** MSTR-006 · A page of the rate sheet. */
export function priceListItemsQueryOptions(
  listId: string,
  q: string,
  unpriced: boolean,
  page: number,
) {
  return queryOptions({
    queryKey: productKeys.items(listId, q, unpriced, page),
    queryFn: ({ signal }) => listPriceListItems({ listId, q, unpriced, page }, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "MSTR-006" },
  });
}
