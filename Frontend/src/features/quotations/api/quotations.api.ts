import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  pdfLinkResponseSchema,
  quotationPageSchema,
  quotationResponseSchema,
  type PdfLink,
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
      include_total: true,
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
