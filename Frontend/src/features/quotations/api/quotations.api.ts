import {
  TIMELINE_PAGE_SIZE,
  timelinePageSchema,
  type TimelinePage,
} from "@/features/leads/api/leads.schemas";
import { apiDownload, apiRequest, type DownloadedFile } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  noContentSchema,
  productPageSchema,
  quotationVersionsResponseSchema,
  quotePreviewResponseSchema,
  pdfLinkResponseSchema,
  publicQuotationResponseSchema,
  quotationPageSchema,
  quotationResponseSchema,
  type CreateQuotationRequest,
  type DeleteQuotationRequest,
  type RequestApprovalRequest,
  type ReviseQuotationRequest,
  type SendQuotationRequest,
  type TransitionQuotationRequest,
  type QuotationSummary,
  type PatchQuotationRequest,
  type PdfLink,
  type PublicQuotation,
  type ProductPick,
  type QuotePreview,
  type QuoteLinesRequest,
  type ReplaceLinesRequest,
  type Quotation,
  type QuotationListParams,
  type QuotationPage,
} from "./quotations.schemas";

const log = createLogger({ file: "features/quotations/api/quotations.api.ts", dataId: "QUOT-001" });

/**
 * QUOT-001 · GET /quotations — one page, newest first, with the matching total.
 * `current_only` is sent only when switched off, so the backend's default applies otherwise.
 */
export async function listQuotations(
  params: QuotationListParams,
  signal?: AbortSignal,
): Promise<QuotationPage> {
  const page = await apiRequest({
    dataId: "QUOT-001",
    logger: log,
    fn: "listQuotations",
    path: "/quotations",
    query: {
      limit: params.pageSize,
      cursor: params.cursor,
      include_total: params.countTotal ?? true,
      q: params.q,
      status: params.status.join(","),
      sales_type: params.salesType,
      lead_id: params.leadId,
      current_only: params.currentOnly ? undefined : false,
    },
    schema: quotationPageSchema,
    signal,
  });

  if (page.skipped > 0) {
    // A backend-side issue: the page is still shown, so it would otherwise go unnoticed.
    log.warn(
      "listQuotations",
      `left out ${String(page.skipped)} quotation(s) that did not match the contract`,
      { dataId: "QUOT-001", context: { skipped: page.skipped, kept: page.items.length } },
    );
  }

  return page;
}

/** QUOT-013 · GET /quotations/export — the list as an Excel file, with the list's filters. */
export function exportQuotations(params: QuotationListParams): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "QUOT-013",
    logger: log,
    fn: "exportQuotations",
    path: "/quotations/export",
    query: {
      q: params.q,
      status: params.status.join(","),
      sales_type: params.salesType,
      lead_id: params.leadId,
      current_only: params.currentOnly ? undefined : false,
    },
  });
}

/** QUOT-002 · GET /quotations/{quotationId} — the document. 404 outside the caller's scope. */
export function getQuotation(quotationId: string, signal?: AbortSignal): Promise<Quotation> {
  return apiRequest({
    dataId: "QUOT-002",
    logger: log,
    fn: "getQuotation",
    path: `/quotations/${encodeURIComponent(quotationId)}`,
    schema: quotationResponseSchema,
    signal,
  });
}

/**
 * QUOT-003 · GET /quotations/{quotationId}/pdf — a signed URL valid for ten minutes, to open
 * in a new tab. 404 on a draft; 409 `pdf_pending` while rendering, `pdf_failed` when it gave up.
 */
export function getQuotationPdf(quotationId: string): Promise<PdfLink> {
  return apiRequest({
    dataId: "QUOT-003",
    logger: log,
    fn: "getQuotationPdf",
    path: `/quotations/${encodeURIComponent(quotationId)}/pdf`,
    schema: pdfLinkResponseSchema,
  });
}

/** How many products one picker search returns. */
export const PRODUCT_SEARCH_LIMIT = 20;

/** MSTR-003 · GET /products — active products whose description contains `q`. */
export async function searchProducts(q: string, signal?: AbortSignal): Promise<ProductPick[]> {
  const page = await apiRequest({
    dataId: "MSTR-003",
    logger: log,
    fn: "searchProducts",
    path: "/products",
    query: { q, active: true, limit: PRODUCT_SEARCH_LIMIT },
    schema: productPageSchema,
    signal,
  });
  return page.items;
}

/**
 * QUOT-005 · POST /pricing/quote-lines — prices a basket without storing anything. A read in
 * all but method, so it runs as a query: abandoned previews are cancelled.
 */
export function previewQuoteLines(
  request: QuoteLinesRequest,
  signal?: AbortSignal,
): Promise<QuotePreview> {
  return apiRequest({
    dataId: "QUOT-005",
    logger: log,
    fn: "previewQuoteLines",
    method: "POST",
    path: "/pricing/quote-lines",
    body: request,
    schema: quotePreviewResponseSchema,
    signal,
  });
}

export interface SaveInput<TBody> {
  readonly body: TBody;
  /** The same key for a retry of the same save; a new one after `rate_changed`. */
  readonly idempotencyKey: string;
}

/** QUOT-004 · POST /quotations — a new draft on a lead. */
export function createQuotation({
  body,
  idempotencyKey,
}: SaveInput<CreateQuotationRequest>): Promise<Quotation> {
  return apiRequest({
    dataId: "QUOT-004",
    logger: log,
    fn: "createQuotation",
    method: "POST",
    path: "/quotations",
    body,
    idempotencyKey,
    schema: quotationResponseSchema,
  });
}

/** QUOT-004 · PATCH /quotations/{id} — a draft's header. */
export function patchQuotation(
  quotationId: string,
  { body, idempotencyKey }: SaveInput<PatchQuotationRequest>,
): Promise<Quotation> {
  return apiRequest({
    dataId: "QUOT-004",
    logger: log,
    fn: "patchQuotation",
    method: "PATCH",
    path: `/quotations/${encodeURIComponent(quotationId)}`,
    body,
    idempotencyKey,
    schema: quotationResponseSchema,
  });
}

/** QUOT-004 · PUT /quotations/{id}/lines — a draft's whole basket, in order. */
export function replaceQuotationLines(
  quotationId: string,
  { body, idempotencyKey }: SaveInput<ReplaceLinesRequest>,
): Promise<Quotation> {
  return apiRequest({
    dataId: "QUOT-004",
    logger: log,
    fn: "replaceQuotationLines",
    method: "PUT",
    path: `/quotations/${encodeURIComponent(quotationId)}/lines`,
    body,
    idempotencyKey,
    schema: quotationResponseSchema,
  });
}

/** QUOT-006 · POST /quotations/{id}/send — numbers the draft; the PDF follows within seconds. */
export function sendQuotation(
  quotationId: string,
  { body, idempotencyKey }: SaveInput<SendQuotationRequest>,
): Promise<Quotation> {
  return apiRequest({
    dataId: "QUOT-006",
    logger: log,
    fn: "sendQuotation",
    method: "POST",
    path: `/quotations/${encodeURIComponent(quotationId)}/send`,
    body,
    idempotencyKey,
    schema: quotationResponseSchema,
  });
}

/** QUOT-007 · POST /quotations/{id}/request-approval — asks a manager to approve the discount. */
export function requestQuotationApproval(
  quotationId: string,
  { body, idempotencyKey }: SaveInput<RequestApprovalRequest>,
): Promise<Quotation> {
  return apiRequest({
    dataId: "QUOT-007",
    logger: log,
    fn: "requestQuotationApproval",
    method: "POST",
    path: `/quotations/${encodeURIComponent(quotationId)}/request-approval`,
    body,
    idempotencyKey,
    schema: quotationResponseSchema,
  });
}

/** QUOT-008 · POST /quotations/{id}/transition — the customer's answer. */
export function transitionQuotation(
  quotationId: string,
  { body, idempotencyKey }: SaveInput<TransitionQuotationRequest>,
): Promise<Quotation> {
  return apiRequest({
    dataId: "QUOT-008",
    logger: log,
    fn: "transitionQuotation",
    method: "POST",
    path: `/quotations/${encodeURIComponent(quotationId)}/transition`,
    body,
    idempotencyKey,
    schema: quotationResponseSchema,
  });
}

/** QUOT-009 · POST /quotations/{id}/revise — a new draft of the same number, re-priced. */
export function reviseQuotation(
  quotationId: string,
  { body, idempotencyKey }: SaveInput<ReviseQuotationRequest>,
): Promise<Quotation> {
  return apiRequest({
    dataId: "QUOT-009",
    logger: log,
    fn: "reviseQuotation",
    method: "POST",
    path: `/quotations/${encodeURIComponent(quotationId)}/revise`,
    body,
    idempotencyKey,
    schema: quotationResponseSchema,
  });
}

/** QUOT-009 · GET /quotations/{id}/versions — every version of the number, oldest first. */
export function listQuotationVersions(
  quotationId: string,
  signal?: AbortSignal,
): Promise<QuotationSummary[]> {
  return apiRequest({
    dataId: "QUOT-009",
    logger: log,
    fn: "listQuotationVersions",
    path: `/quotations/${encodeURIComponent(quotationId)}/versions`,
    schema: quotationVersionsResponseSchema,
    signal,
  });
}

export interface QuotationTimelineParams {
  readonly quotationId: string;
  /** From the previous page's `nextCursor`; null for the newest events. */
  readonly cursor: string | null;
}

/** QUOT-010 · GET /quotations/{id}/timeline — one page of the quotation's history, newest first. */
export async function getQuotationTimeline(
  { quotationId, cursor }: QuotationTimelineParams,
  signal?: AbortSignal,
): Promise<TimelinePage> {
  const page = await apiRequest({
    dataId: "QUOT-010",
    logger: log,
    fn: "getQuotationTimeline",
    path: `/quotations/${encodeURIComponent(quotationId)}/timeline`,
    query: { limit: TIMELINE_PAGE_SIZE, cursor },
    schema: timelinePageSchema,
    signal,
  });
  if (page.skipped > 0) {
    // A backend-side issue: the rest of the history is still shown.
    log.warn(
      "getQuotationTimeline",
      `left out ${String(page.skipped)} event(s) that did not match the contract`,
      { dataId: "QUOT-010", context: { skipped: page.skipped, kept: page.items.length } },
    );
  }
  return page;
}

/** QUOT-011 · DELETE /quotations/{id} — a draft only; 204 with no body. */
export async function deleteQuotation(
  quotationId: string,
  { body, idempotencyKey }: SaveInput<DeleteQuotationRequest>,
): Promise<void> {
  await apiRequest({
    dataId: "QUOT-011",
    logger: log,
    fn: "deleteQuotation",
    method: "DELETE",
    path: `/quotations/${encodeURIComponent(quotationId)}`,
    body,
    idempotencyKey,
    schema: noContentSchema,
  });
}

/**
 * QUOT-012 · GET /public/q/{token} — the customer's page, without signing in. The answer holds
 * no personal data (no party, mobile or lines), so it is logged like any other read.
 */
export function getPublicQuotation(token: string, signal?: AbortSignal): Promise<PublicQuotation> {
  return apiRequest({
    dataId: "QUOT-012",
    logger: log,
    fn: "getPublicQuotation",
    path: `/public/q/${encodeURIComponent(token)}`,
    auth: "none",
    schema: publicQuotationResponseSchema,
    signal,
  });
}
