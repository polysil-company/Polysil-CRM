import { http, HttpResponse } from "msw";

import {
  QUOTATION_STATUSES,
  type PdfLinkWire,
  type QuotationPageWire,
  type QuotationStatus,
  type QuotationWire,
} from "@/features/quotations/api/quotations.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { toQuotationSummary } from "@/mocks/data/quotations";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * QUOT-001 … QUOT-003 · The backend's quotation reads (backend/docs/api/quotations.md): the
 * list with its filters, cursor paging and capped total; the document; and the PDF link,
 * with 404 on a draft and 409 while the PDF renders or after it failed.
 */

const DEFAULT_LIMIT = 25;
const MAX_LIMIT = 100;
/** The backend stops counting here and says so with `total_capped`. */
const TOTAL_CEILING = 1000;
const PDF_LINK_MINUTES = 10;

function isStatus(value: string): value is QuotationStatus {
  return QUOTATION_STATUSES.some((status) => status === value);
}

/** Number (contains), party name (contains) or the mobile's digits (contains). */
function matchesSearch(quotation: QuotationWire, q: string): boolean {
  const query = q.trim().toLowerCase();
  if (query === "") {
    return true;
  }
  const digits = query.replace(/\D/g, "");
  return (
    (quotation.quote_no ?? "").toLowerCase().includes(query) ||
    quotation.party.name.toLowerCase().includes(query) ||
    (digits.length >= 3 && quotation.party.mobile.includes(digits))
  );
}

/** A lead's quotations include those on leads merged into it, as on the backend. */
function onLead(quotation: QuotationWire, leadId: string): boolean {
  if (quotation.lead?.id === leadId) {
    return true;
  }
  const lead = mockDb.leads.find((item) => item.id === quotation.lead?.id);
  return lead?.merged_into?.id === leadId;
}

export const quotationHandlers = [
  http.get(buildApiUrl("/quotations"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const url = new URL(request.url);
    const limit = Math.min(
      MAX_LIMIT,
      Math.max(1, Number(url.searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT),
    );
    const cursorParam = url.searchParams.get("cursor");
    const offset = cursorParam === null ? 0 : decodeCursor(cursorParam);
    if (offset === null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        cursor: "malformed cursor",
      });
    }
    if (scenario === "contract") {
      // Deliberately wrong shape: exercises CONTRACT_VIOLATION handling end to end.
      return HttpResponse.json({ data: [{ id: 7, status: "lost" }], meta: { limit: "25" } });
    }

    const statuses = (url.searchParams.get("status") ?? "")
      .split(",")
      .map((status) => status.trim())
      .filter(isStatus);
    const salesType = url.searchParams.get("sales_type");
    const leadId = url.searchParams.get("lead_id");
    const q = url.searchParams.get("q") ?? "";
    const currentOnly = url.searchParams.get("current_only") !== "false";

    const matches =
      scenario === "empty"
        ? []
        : mockDb.quotations.filter(
            (quotation) =>
              (statuses.length === 0 || statuses.includes(quotation.status)) &&
              (salesType === null || salesType === "" || quotation.sales_type === salesType) &&
              (leadId === null || leadId === "" || onLead(quotation, leadId)) &&
              (!currentOnly || quotation.superseded_by === null) &&
              matchesSearch(quotation, q),
          );
    const counted = url.searchParams.get("include_total") === "true";
    const hasMore = offset + limit < matches.length;

    const body: QuotationPageWire = {
      data: matches.slice(offset, offset + limit).map(toQuotationSummary),
      meta: {
        limit,
        next_cursor: hasMore ? encodeCursor(offset + limit) : null,
        total: counted ? Math.min(matches.length, TOTAL_CEILING) : null,
        total_capped: counted && matches.length > TOTAL_CEILING,
      },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/quotations/:quotationId"), async ({ params }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const quotation = mockDb.quotations.find((item) => item.id === params.quotationId);
    if (quotation === undefined) {
      return errorResponse(404, "not_found", "No such quotation.");
    }
    if (scenario === "contract") {
      return HttpResponse.json({ data: { ...quotation, totals: null } });
    }
    return HttpResponse.json({ data: quotation });
  }),

  http.get(buildApiUrl("/quotations/:quotationId/pdf"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const quotation = mockDb.quotations.find((item) => item.id === params.quotationId);
    if (quotation === undefined || quotation.status === "draft") {
      return errorResponse(404, "not_found", "A draft has no PDF.");
    }
    if (quotation.pdf_state === "pending") {
      return errorResponse(409, "pdf_pending", "The PDF is still being prepared.");
    }
    if (quotation.pdf_state === "failed") {
      return errorResponse(409, "pdf_failed", quotation.pdf_error ?? "The PDF could not be made.");
    }
    const filename = `${(quotation.quote_no ?? "quotation").replace(/\//g, "-")}-v${String(quotation.version)}.pdf`;
    const body: PdfLinkWire = {
      data: {
        // TODO(QUOT-003): the mock has no PDFs; the real link is a signed storage URL.
        url: `https://files.polysil.example/quotations/${filename}`,
        expires_at: new Date(Date.now() + PDF_LINK_MINUTES * 60 * 1000).toISOString(),
        filename,
      },
    };
    return HttpResponse.json(body);
  }),
];
