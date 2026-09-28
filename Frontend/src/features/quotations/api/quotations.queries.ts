import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query";

import {
  getPublicQuotation,
  getQuotation,
  getQuotationTimeline,
  listQuotationVersions,
  listQuotations,
  previewQuoteLines,
  searchProducts,
} from "./quotations.api";
import type { QuoteLinesRequest, QuotationListParams } from "./quotations.schemas";

/** How often a just-sent quotation is re-read while its PDF renders (a few seconds). */
export const PDF_PENDING_POLL_MS = 3000;
/** How often the customer's page checks whether the PDF is ready. */
export const PUBLIC_PDF_POLL_MS = 4000;
/** How often a draft waiting on a discount approval is re-read: a manager decides in minutes. */
export const APPROVAL_PENDING_POLL_MS = 30_000;

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
  timelines: () => [...quotationKeys.all, "timeline"] as const,
  timeline: (quotationId: string) => [...quotationKeys.timelines(), quotationId] as const,
  versionLists: () => [...quotationKeys.all, "versions"] as const,
  versions: (quotationId: string) => [...quotationKeys.versionLists(), quotationId] as const,
  shared: (token: string) => [...quotationKeys.all, "shared", token] as const,
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

/**
 * QUOT-002 · Re-reads every few seconds while the PDF is being rendered, and now and then
 * while a discount approval is pending (QUOT-007), then stops.
 */
export function quotationDetailQueryOptions(quotationId: string) {
  return queryOptions({
    queryKey: quotationKeys.detail(quotationId),
    queryFn: ({ signal }) => getQuotation(quotationId, signal),
    refetchInterval: (query) => {
      const quotation = query.state.data;
      if (quotation?.pdfState === "pending") return PDF_PENDING_POLL_MS;
      if (quotation?.approval?.status === "pending") return APPROVAL_PENDING_POLL_MS;
      return false;
    },
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

/** The first timeline page has no cursor. */
const NEWEST_TIMELINE_PAGE: string | null = null;

/** QUOT-009 · Every version of the quotation's number, oldest first. */
export function quotationVersionsQueryOptions(quotationId: string) {
  return queryOptions({
    queryKey: quotationKeys.versions(quotationId),
    queryFn: ({ signal }) => listQuotationVersions(quotationId, signal),
    meta: { dataId: "QUOT-009" },
  });
}

/** QUOT-010 · The quotation's history, newest first, a page at a time. */
export function quotationTimelineQueryOptions(quotationId: string) {
  return infiniteQueryOptions({
    queryKey: quotationKeys.timeline(quotationId),
    queryFn: ({ pageParam, signal }) =>
      getQuotationTimeline({ quotationId, cursor: pageParam }, signal),
    initialPageParam: NEWEST_TIMELINE_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "QUOT-010" },
  });
}

/**
 * QUOT-012 · The customer's page. Checks every few seconds until the PDF is ready. A 404 is
 * an unknown link — retrying cannot help.
 */
export function publicQuotationQueryOptions(token: string) {
  return queryOptions({
    queryKey: quotationKeys.shared(token),
    queryFn: ({ signal }) => getPublicQuotation(token, signal),
    refetchInterval: (query) => (query.state.data?.pdfReady === false ? PUBLIC_PDF_POLL_MS : false),
    retry: false,
    meta: { dataId: "QUOT-012" },
  });
}
