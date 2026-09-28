import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { getQuotation, listQuotations, previewQuoteLines, searchProducts } from "./quotations.api";
import type { QuoteLinesRequest, QuotationListParams } from "./quotations.schemas";

/** How often a just-sent quotation is re-read while its PDF renders (a few seconds). */
export const PDF_PENDING_POLL_MS = 3000;

/**
 * Query keys for quotations. Invalidate by prefix:
 *   quotationKeys.all      → everything about quotations
 *   quotationKeys.lists()  → every list, whatever the filters (including a lead's)
 */
export const quotationKeys = {
  all: ["quotations"] as const,
  lists: () => [...quotationKeys.all, "list"] as const,
  list: (params: QuotationListParams) => [...quotationKeys.lists(), params] as const,
  details: () => [...quotationKeys.all, "detail"] as const,
  detail: (quotationId: string) => [...quotationKeys.details(), quotationId] as const,
  products: (q: string) => [...quotationKeys.all, "products", q] as const,
  previews: () => [...quotationKeys.all, "preview"] as const,
  preview: (request: QuoteLinesRequest) => [...quotationKeys.previews(), request] as const,
};

/** QUOT-001 · Keeps the previous page on screen while the next one loads. */
export function quotationListQueryOptions(params: QuotationListParams) {
  return queryOptions({
    queryKey: quotationKeys.list(params),
    queryFn: ({ signal }) => listQuotations(params, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "QUOT-001" },
  });
}

/** QUOT-002 · Re-reads every few seconds while the PDF is being rendered, then stops. */
export function quotationDetailQueryOptions(quotationId: string) {
  return queryOptions({
    queryKey: quotationKeys.detail(quotationId),
    queryFn: ({ signal }) => getQuotation(quotationId, signal),
    refetchInterval: (query) =>
      query.state.data?.pdfState === "pending" ? PDF_PENDING_POLL_MS : false,
    meta: { dataId: "QUOT-002" },
  });
}

/** MSTR-003 · The picker's results; the previous ones stay while the next search loads. */
export function productSearchQueryOptions(q: string) {
  return queryOptions({
    queryKey: quotationKeys.products(q),
    queryFn: ({ signal }) => searchProducts(q, signal),
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
    meta: { dataId: "MSTR-003" },
  });
}

/**
 * QUOT-005 · The priced basket. Keyed by the request, so an unchanged basket is not priced
 * twice; the previous figures stay on screen while the next ones load. Prices move rarely
 * but can, so a preview older than a minute is priced again.
 */
export function quotePreviewQueryOptions(request: QuoteLinesRequest) {
  return queryOptions({
    queryKey: quotationKeys.preview(request),
    queryFn: ({ signal }) => previewQuoteLines(request, signal),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    retry: false,
    meta: { dataId: "QUOT-005" },
  });
}
