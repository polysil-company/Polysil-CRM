import { apiRequest } from "@/lib/api/client";
import type { ApiPath } from "@/lib/api/url";
import { createLogger } from "@/lib/logger";

import {
  hsnHistorySchema,
  priceListItemsPageSchema,
  priceListPageSchema,
  priceListSchema,
  productPageSchema,
  productSchema,
  publishResultSchema,
  taxRatePageSchema,
  type CreatePriceListRequest,
  type CreateProductRequest,
  type HsnRow,
  type OffsetPage,
  type PatchProductRequest,
  type PriceList,
  type PriceListSalesTypeFilter,
  type PriceListItemsPage,
  type Product,
  type ProductListParams,
  type TaxRate,
} from "./products.schemas";

const log = createLogger({ file: "features/products/api/products.api.ts", dataId: "MSTR-004" });

export const PRODUCT_PAGE_SIZE = 50;
/** The backend's ceiling on one page of products. */
const PRODUCT_PAGE_MAX = 200;
export const RATE_SHEET_PAGE_SIZE = 100;
/** The backend's ceiling on one page of a rate sheet. */
const RATE_SHEET_PAGE_MAX = 500;
/** Stops a runaway loop if a total ever disagreed with the pages. */
const MAX_PAGES = 100;

function productPath(productId: string, rest = ""): ApiPath {
  return `/products/${encodeURIComponent(productId)}${rest}`;
}

function listPath(listId: string, rest = ""): ApiPath {
  return `/price-lists/${encodeURIComponent(listId)}${rest}`;
}

function productQuery(params: ProductListParams): Record<string, string | boolean | undefined> {
  return {
    q: params.q.trim() === "" ? undefined : params.q.trim(),
    category: params.category ?? undefined,
    quotation_category: params.quotationCategory ?? undefined,
    active: params.active ?? undefined,
  };
}

/**
 * MSTR-004 · GET /products — the catalogue, a page at a time, with a total. The backend lists
 * active products unless `active=false` is asked for.
 */
export function listProducts(
  params: ProductListParams & { page: number },
  signal?: AbortSignal,
): Promise<OffsetPage<Product>> {
  return apiRequest({
    dataId: "MSTR-004",
    logger: log,
    fn: "listProducts",
    path: "/products",
    query: { ...productQuery(params), page: params.page, limit: PRODUCT_PAGE_SIZE },
    schema: productPageSchema,
    signal,
  });
}

/**
 * MSTR-004 · The categories and units the catalogue uses, read from the catalogue itself,
 * active products and switched-off ones. No endpoint lists them yet (BE-024); the form offers
 * these so a typo never becomes a category of one.
 */
export async function listCatalogueFacets(signal?: AbortSignal): Promise<{
  categories: string[];
  units: { code: string; decimals: number }[];
}> {
  const categories = new Set<string>();
  const units = new Map<string, number>();
  for (const active of [true, false]) {
    for (let page = 1; page <= MAX_PAGES; page += 1) {
      const result = await apiRequest({
        dataId: "MSTR-004",
        logger: log,
        fn: "listCatalogueFacets",
        path: "/products",
        query: { active, page, limit: PRODUCT_PAGE_MAX },
        schema: productPageSchema,
        signal,
      });
      for (const product of result.items) {
        categories.add(product.category);
        units.set(product.uom, product.uomDecimals);
      }
      if (page * PRODUCT_PAGE_MAX >= result.total) break;
    }
  }
  return {
    categories: [...categories].sort((a, b) => a.localeCompare(b)),
    units: [...units.entries()]
      .map(([code, decimals]) => ({ code, decimals }))
      .sort((a, b) => a.code.localeCompare(b.code)),
  };
}

/** MSTR-004 · POST /products — 409 `duplicate_description` for a description already in use. */
export function createProduct({
  body,
  idempotencyKey,
}: {
  body: CreateProductRequest;
  idempotencyKey: string;
}): Promise<Product> {
  return apiRequest({
    dataId: "MSTR-004",
    logger: log,
    fn: "createProduct",
    method: "POST",
    path: "/products",
    body,
    idempotencyKey,
    schema: productSchema,
  });
}

/** MSTR-004 · PATCH /products/{id} — only what changes. */
export function patchProduct({
  productId,
  body,
  idempotencyKey,
}: {
  productId: string;
  body: PatchProductRequest;
  idempotencyKey: string;
}): Promise<Product> {
  return apiRequest({
    dataId: "MSTR-004",
    logger: log,
    fn: "patchProduct",
    method: "PATCH",
    path: productPath(productId),
    body,
    idempotencyKey,
    schema: productSchema,
  });
}

/** MSTR-005 · GET /products/{id}/hsn — every classification, newest first. */
export function getHsnHistory(productId: string, signal?: AbortSignal): Promise<HsnRow[]> {
  return apiRequest({
    dataId: "MSTR-005",
    logger: log,
    fn: "getHsnHistory",
    path: productPath(productId, "/hsn"),
    schema: hsnHistorySchema,
    signal,
  });
}

/**
 * MSTR-005 · PUT /products/{id}/hsn — classify from a date; the row in force closes. The current
 * row's own start date is a 409 `hsn_same_start_date`.
 */
export function assignHsn({
  productId,
  hsnCode,
  from,
  idempotencyKey,
}: {
  productId: string;
  hsnCode: string;
  from: string;
  idempotencyKey: string;
}): Promise<HsnRow[]> {
  return apiRequest({
    dataId: "MSTR-005",
    logger: log,
    fn: "assignHsn",
    method: "PUT",
    path: productPath(productId, "/hsn"),
    body: { hsn_code: hsnCode, effective_from: from },
    idempotencyKey,
    schema: hsnHistorySchema,
  });
}

/** MSTR-005 · GET /tax-rates — a page of rates, optionally one code or only those in force. */
export function listTaxRates(
  params: { hsnCode: string | null; inForce: boolean; page: number },
  signal?: AbortSignal,
): Promise<OffsetPage<TaxRate>> {
  return apiRequest({
    dataId: "MSTR-005",
    logger: log,
    fn: "listTaxRates",
    path: "/tax-rates",
    query: {
      hsn_code: params.hsnCode ?? undefined,
      in_force: params.inForce ? true : undefined,
      page: params.page,
      limit: PRODUCT_PAGE_SIZE,
    },
    schema: taxRatePageSchema,
    signal,
  });
}

/**
 * MSTR-005 · PUT /tax-rates/{hsn} — a slab from a date, for every product under the code. Only
 * the slabs in force are accepted.
 */
export function setTaxRate({
  hsnCode,
  rate,
  from,
  idempotencyKey,
}: {
  hsnCode: string;
  rate: string;
  from: string;
  idempotencyKey: string;
}): Promise<OffsetPage<TaxRate>> {
  return apiRequest({
    dataId: "MSTR-005",
    logger: log,
    fn: "setTaxRate",
    method: "PUT",
    path: `/tax-rates/${encodeURIComponent(hsnCode)}`,
    body: { rate, effective_from: from },
    idempotencyKey,
    schema: taxRatePageSchema,
  });
}

/** MSTR-006 · GET /price-lists — newest first, optionally drafts or published ones. */
export function listPriceLists(
  params: {
    status: "draft" | "published" | null;
    /** MSTR-008 · One sale type, `general` for the lists with none, or null for every list. */
    salesType: PriceListSalesTypeFilter | null;
    page: number;
  },
  signal?: AbortSignal,
): Promise<OffsetPage<PriceList>> {
  return apiRequest({
    dataId: "MSTR-006",
    logger: log,
    fn: "listPriceLists",
    path: "/price-lists",
    query: {
      status: params.status ?? undefined,
      sales_type: params.salesType ?? undefined,
      page: params.page,
      limit: PRODUCT_PAGE_SIZE,
    },
    schema: priceListPageSchema,
    signal,
  });
}

/** MSTR-006 · GET /price-lists/{id} */
export function getPriceList(listId: string, signal?: AbortSignal): Promise<PriceList> {
  return apiRequest({
    dataId: "MSTR-006",
    logger: log,
    fn: "getPriceList",
    path: listPath(listId),
    schema: priceListSchema,
    signal,
  });
}

/** MSTR-006 · POST /price-lists — always a draft. */
export function createPriceList({
  body,
  idempotencyKey,
}: {
  body: CreatePriceListRequest;
  idempotencyKey: string;
}): Promise<PriceList> {
  return apiRequest({
    dataId: "MSTR-006",
    logger: log,
    fn: "createPriceList",
    method: "POST",
    path: "/price-lists",
    body,
    idempotencyKey,
    schema: priceListSchema,
  });
}

/** MSTR-006 · PATCH /price-lists/{id} — close it from a date (exclusive, forward only). */
export function closePriceList({
  listId,
  to,
  idempotencyKey,
}: {
  listId: string;
  to: string;
  idempotencyKey: string;
}): Promise<PriceList> {
  return apiRequest({
    dataId: "MSTR-006",
    logger: log,
    fn: "closePriceList",
    method: "PATCH",
    path: listPath(listId),
    body: { effective_to: to },
    idempotencyKey,
    schema: priceListSchema,
  });
}

/** MSTR-006 · GET /price-lists/{id}/items — the rate sheet, a page at a time. */
export function listPriceListItems(
  params: { listId: string; q: string; unpriced: boolean; page: number },
  signal?: AbortSignal,
): Promise<PriceListItemsPage> {
  return apiRequest({
    dataId: "MSTR-006",
    logger: log,
    fn: "listPriceListItems",
    path: listPath(params.listId, "/items"),
    query: {
      q: params.q.trim() === "" ? undefined : params.q.trim(),
      unpriced: params.unpriced ? true : undefined,
      page: params.page,
      limit: RATE_SHEET_PAGE_SIZE,
    },
    schema: priceListItemsPageSchema,
    signal,
  });
}

/**
 * MSTR-006 · Every rate a list holds, product id → rate: the starting point of a save, since
 * `PUT /items` replaces them all.
 */
export async function readAllRates(listId: string): Promise<Map<string, string>> {
  const rates = new Map<string, string>();
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const result = await apiRequest({
      dataId: "MSTR-006",
      logger: log,
      fn: "readAllRates",
      path: listPath(listId, "/items"),
      query: { page, limit: RATE_SHEET_PAGE_MAX },
      schema: priceListItemsPageSchema,
    });
    for (const item of result.items) {
      if (item.rate !== null) rates.set(item.productId, item.rate);
    }
    if (page * RATE_SHEET_PAGE_MAX >= result.total) break;
  }
  return rates;
}

/**
 * MSTR-006 · PUT /price-lists/{id}/items — a draft's rates, all of them: a product left out has
 * no rate. More than two decimals, or zero, is refused, not rounded.
 */
export function replaceRates({
  listId,
  rates,
  idempotencyKey,
}: {
  listId: string;
  rates: ReadonlyMap<string, string>;
  idempotencyKey: string;
}): Promise<PriceListItemsPage> {
  return apiRequest({
    dataId: "MSTR-006",
    logger: log,
    fn: "replaceRates",
    method: "PUT",
    path: listPath(listId, "/items"),
    body: {
      items: [...rates.entries()].map(([productId, rate]) => ({ product_id: productId, rate })),
    },
    idempotencyKey,
    schema: priceListItemsPageSchema,
  });
}

/**
 * MSTR-006 · POST /price-lists/{id}/publish — into force, closing what it supersedes. A list
 * missing rates is a 409 `price_list_unpriced` unless `allowUnpriced` says that is meant.
 */
export function publishPriceList({
  listId,
  allowUnpriced,
  idempotencyKey,
}: {
  listId: string;
  allowUnpriced: boolean;
  idempotencyKey: string;
}): Promise<{ closedPredecessorId: string | null }> {
  return apiRequest({
    dataId: "MSTR-006",
    logger: log,
    fn: "publishPriceList",
    method: "POST",
    path: listPath(listId, "/publish"),
    body: { allow_unpriced: allowUnpriced },
    idempotencyKey,
    schema: publishResultSchema,
  });
}
