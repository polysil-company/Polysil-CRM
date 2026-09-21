import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  leadListResponseSchema,
  leadSchema,
  leadSummarySchema,
  type CreateLeadRequest,
  type Lead,
  type LeadListParams,
  type LeadListResponse,
  type LeadSummary,
} from "./leads.schemas";

const log = createLogger({ file: "features/leads/api/leads.api.ts", dataId: "LEAD-001" });

/** LEAD-001 · GET /leads */
export function listLeads(params: LeadListParams, signal?: AbortSignal): Promise<LeadListResponse> {
  return apiRequest({
    dataId: "LEAD-001",
    logger: log,
    fn: "listLeads",
    path: "/leads",
    query: {
      page: params.page,
      pageSize: params.pageSize,
      sort: params.sort,
      order: params.order,
      q: params.q,
      status: params.status,
      source: params.source,
      type: params.type,
    },
    schema: leadListResponseSchema,
    signal,
  });
}

/** LEAD-003 · GET /leads/{leadId} */
export function getLead(leadId: string, signal?: AbortSignal): Promise<Lead> {
  return apiRequest({
    dataId: "LEAD-003",
    logger: log,
    fn: "getLead",
    path: `/leads/${encodeURIComponent(leadId)}`,
    schema: leadSchema,
    signal,
  });
}

/** LEAD-004 · GET /leads/summary */
export function getLeadSummary(signal?: AbortSignal): Promise<LeadSummary> {
  return apiRequest({
    dataId: "LEAD-004",
    logger: log,
    fn: "getLeadSummary",
    path: "/leads/summary",
    schema: leadSummarySchema,
    signal,
  });
}

/** LEAD-002 · POST /leads */
export function createLead(body: CreateLeadRequest): Promise<Lead> {
  return apiRequest({
    dataId: "LEAD-002",
    logger: log,
    fn: "createLead",
    method: "POST",
    path: "/leads",
    body,
    schema: leadSchema,
  });
}
