import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  LEAD_SORT_WIRE_FIELDS,
  leadPageSchema,
  leadResponseSchema,
  leadStatsSchema,
  TIMELINE_PAGE_SIZE,
  timelineEventResponseSchema,
  timelinePageSchema,
  type AddLeadNoteRequest,
  type CreateLeadRequest,
  type Lead,
  type LeadListParams,
  type LeadPage,
  type LeadStats,
  type TimelineEvent,
  type TimelinePage,
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
    log.warn(
      "listLeads",
      `left out ${String(page.skipped)} lead(s) that did not match the contract`,
      {
        dataId: "LEAD-001",
        context: { skipped: page.skipped, kept: page.items.length },
      },
    );
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

/**
 * LEAD-004 · GET /leads/stats — how many leads the caller can see, by stage and priority,
 * and how many wait unassigned. One count query on the backend, no lead rows.
 */
export function getLeadStats(signal?: AbortSignal): Promise<LeadStats> {
  return apiRequest({
    dataId: "LEAD-004",
    logger: log,
    fn: "getLeadStats",
    path: "/leads/stats",
    schema: leadStatsSchema,
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

export interface LeadTimelineParams {
  readonly leadId: string;
  /** From the previous page's `nextCursor`; null for the newest events. */
  readonly cursor: string | null;
}

/** LEAD-005 · GET /leads/{leadId}/timeline — one page of the lead's history, newest first. */
export async function getLeadTimeline(
  { leadId, cursor }: LeadTimelineParams,
  signal?: AbortSignal,
): Promise<TimelinePage> {
  const page = await apiRequest({
    dataId: "LEAD-005",
    logger: log,
    fn: "getLeadTimeline",
    path: `/leads/${encodeURIComponent(leadId)}/timeline`,
    query: { limit: TIMELINE_PAGE_SIZE, cursor },
    schema: timelinePageSchema,
    signal,
  });

  if (page.skipped > 0) {
    // A backend-side issue: the rest of the timeline is still shown.
    log.warn(
      "getLeadTimeline",
      `left out ${String(page.skipped)} event(s) that did not match the contract`,
      { dataId: "LEAD-005", context: { skipped: page.skipped, kept: page.items.length } },
    );
  }

  return page;
}

export interface AddLeadNoteInput {
  readonly leadId: string;
  readonly body: AddLeadNoteRequest;
  /** The same key for a retry of the same note, so a lost reply never adds it twice. */
  readonly idempotencyKey: string;
}

/** LEAD-006 · POST /leads/{leadId}/notes — returns the new timeline event. */
export function addLeadNote({
  leadId,
  body,
  idempotencyKey,
}: AddLeadNoteInput): Promise<TimelineEvent> {
  return apiRequest({
    dataId: "LEAD-006",
    logger: log,
    fn: "addLeadNote",
    method: "POST",
    path: `/leads/${encodeURIComponent(leadId)}/notes`,
    body,
    idempotencyKey,
    schema: timelineEventResponseSchema,
  });
}
