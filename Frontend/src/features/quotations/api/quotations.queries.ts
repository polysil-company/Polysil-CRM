import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { getQuotation, listQuotations } from "./quotations.api";
import type { QuotationListParams } from "./quotations.schemas";

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
