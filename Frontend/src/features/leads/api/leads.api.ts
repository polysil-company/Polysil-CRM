import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  LEAD_SORT_WIRE_FIELDS,
  leadCountSchema,
  leadPageSchema,
  leadResponseSchema,
  type CreateLeadRequest,
  type Lead,
  type LeadCount,
  type LeadListParams,
  type LeadPage,
} from "./leads.schemas";

const log = createLogger({ file: "features/leads/api/leads.api.ts", dataId: "LEAD-001" });

/**
 * LEAD-001 · GET /leads — one page, newest first, with the matching total.
 * `include_total` costs the backend a second query; the list shows "1–25 of 74", so it asks.
 */
export async function listLeads(params: LeadListParams, signal?: AbortSignal): Promise<LeadPage> {
  const page = await apiRequest({
    dataId: "LEAD-001",
    logger: log,
    fn: "listLeads",
    path: "/leads",
    query: {
      limit: params.pageSize,
      cursor: params.cursor,
      include_total: true,
      q: params.q,
      stage: params.stage.join(","),
      source: params.source,
      inquiry_type: params.type,
      sort: LEAD_SORT_WIRE_FIELDS[params.sort],
      order: params.order,
    },
    schema: leadPageSchema,
    signal,
  });

  if (page.skipped > 0) {
    // A backend-side issue: the page is still shown, so it would otherwise go unnoticed.
    log.warn("listLeads", `left out ${String(page.skipped)} lead(s) that did not match the contract`, {
      dataId: "LEAD-001",
      context: { skipped: page.skipped, kept: page.items.length },
    });
  }

  return page;
}

/** LEAD-003 · GET /leads/{leadId} */
export function getLead(leadId: string, signal?: AbortSignal): Promise<Lead> {
  return apiRequest({
    dataId: "LEAD-003",
    logger: log,
    fn: "getLead",
    path: `/leads/${encodeURIComponent(leadId)}`,
    schema: leadResponseSchema,
    signal,
  });
}

/** LEAD-004 · How many leads the caller can see, for navigation: one row plus the count. */
export function countLeads(signal?: AbortSignal): Promise<LeadCount> {
  return apiRequest({
    dataId: "LEAD-004",
    logger: log,
    fn: "countLeads",
    path: "/leads",
    query: { limit: 1, include_total: true },
    schema: leadCountSchema,
    signal,
  });
}

export interface CreateLeadInput {
  readonly body: CreateLeadRequest;
  /**
   * Send the same key when retrying the same body: the backend replays the first result
   * instead of creating a second lead. A different body needs a new key (the same key with
   * a different body is a 409).
   */
  readonly idempotencyKey: string;
}

/** LEAD-002 · POST /leads */
export function createLead({ body, idempotencyKey }: CreateLeadInput): Promise<Lead> {
  return apiRequest({
    dataId: "LEAD-002",
    logger: log,
    fn: "createLead",
    method: "POST",
    path: "/leads",
    body,
    idempotencyKey,
    schema: leadResponseSchema,
  });
}
