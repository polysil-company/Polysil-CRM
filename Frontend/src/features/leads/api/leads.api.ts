import { z } from "zod";

import { apiDownload, apiRequest, type DownloadedFile } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  LEAD_SORT_WIRE_FIELDS,
  leadAreasResponseSchema,
  leadPageSchema,
  leadResponseSchema,
  leadStatsSchema,
  TIMELINE_PAGE_SIZE,
  timelineEventResponseSchema,
  timelinePageSchema,
  assigneeListResponseSchema,
  dismissResultSchema,
  DUPLICATE_PAGE_SIZE,
  duplicatePageSchema,
  partnerPickListResponseSchema,
  type AddLeadNoteRequest,
  type AssignLeadRequest,
  type Assignee,
  type PartnerPick,
  type CreateLeadRequest,
  type ReopenLeadRequest,
  type TransitionLeadRequest,
  type Lead,
  type LeadArea,
  type LeadAreasParams,
  type LeadListParams,
  type LeadPage,
  type LeadStats,
  type TimelineEvent,
  type TimelinePage,
  type DuplicatePage,
  type MergeLeadRequest,
  type PatchLeadRequest,
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
      territory_id: params.areas.join(","),
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

/** LEAD-009 · GET /leads/export — the list as an Excel file, with the list's filters and sort. */
export function exportLeads(params: LeadListParams): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "LEAD-009",
    logger: log,
    fn: "exportLeads",
    path: "/leads/export",
    query: {
      q: params.q,
      stage: params.stage.join(","),
      source: params.source,
      inquiry_type: params.type,
      sort: LEAD_SORT_WIRE_FIELDS[params.sort],
      order: params.order,
      territory_id: params.areas.join(","),
    },
  });
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

/** LEAD-010 · PATCH /leads/{id} — only the fields that changed. */
export function patchLead({
  leadId,
  body,
  idempotencyKey,
}: {
  leadId: string;
  body: PatchLeadRequest;
  idempotencyKey: string;
}): Promise<Lead> {
  return apiRequest({
    dataId: "LEAD-010",
    logger: log,
    fn: "patchLead",
    method: "PATCH",
    path: `/leads/${encodeURIComponent(leadId)}`,
    body,
    idempotencyKey,
    schema: leadResponseSchema,
  });
}

/** LEAD-011 · DELETE /leads/{id} — a soft delete; 204 always, a repeat included. */
export async function deleteLead({
  leadId,
  idempotencyKey,
}: {
  leadId: string;
  idempotencyKey: string;
}): Promise<void> {
  await apiRequest({
    dataId: "LEAD-011",
    logger: log,
    fn: "deleteLead",
    method: "DELETE",
    path: `/leads/${encodeURIComponent(leadId)}`,
    idempotencyKey,
    schema: z.undefined(),
  });
}

/** LEAD-012 · GET /leads/duplicates — the review queue, newest first. */
export function listDuplicates(
  cursor: string | null,
  signal?: AbortSignal,
): Promise<DuplicatePage> {
  return apiRequest({
    dataId: "LEAD-012",
    logger: log,
    fn: "listDuplicates",
    path: "/leads/duplicates",
    query: { limit: DUPLICATE_PAGE_SIZE, cursor },
    schema: duplicatePageSchema,
    signal,
  });
}

/** LEAD-012 · POST /leads/duplicates/{linkId}/dismiss — not a duplicate after all. */
export function dismissDuplicate({
  linkId,
  idempotencyKey,
}: {
  linkId: string;
  idempotencyKey: string;
}): Promise<{ linkId: string }> {
  return apiRequest({
    dataId: "LEAD-012",
    logger: log,
    fn: "dismissDuplicate",
    method: "POST",
    path: `/leads/duplicates/${encodeURIComponent(linkId)}/dismiss`,
    idempotencyKey,
    schema: dismissResultSchema,
  });
}

/** LEAD-012 · POST /leads/{id}/merge — this lead into the survivor; answers the survivor. */
export function mergeLead({
  leadId,
  body,
  idempotencyKey,
}: {
  leadId: string;
  body: MergeLeadRequest;
  idempotencyKey: string;
}): Promise<Lead> {
  return apiRequest({
    dataId: "LEAD-012",
    logger: log,
    fn: "mergeLead",
    method: "POST",
    path: `/leads/${encodeURIComponent(leadId)}/merge`,
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

export interface TransitionLeadInput {
  readonly leadId: string;
  readonly body: TransitionLeadRequest;
  /** The same key for a retry of the same move, so a lost reply never moves it twice. */
  readonly idempotencyKey: string;
}

/** LEAD-007 · POST /leads/{leadId}/transition — returns the lead after the move. */
export function transitionLead({
  leadId,
  body,
  idempotencyKey,
}: TransitionLeadInput): Promise<Lead> {
  return apiRequest({
    dataId: "LEAD-007",
    logger: log,
    fn: "transitionLead",
    method: "POST",
    path: `/leads/${encodeURIComponent(leadId)}/transition`,
    body,
    idempotencyKey,
    schema: leadResponseSchema,
  });
}

export interface ReopenLeadInput {
  readonly leadId: string;
  readonly body: ReopenLeadRequest;
  readonly idempotencyKey: string;
}

/** LEAD-007 · POST /leads/{leadId}/reopen — returns the lead at the stage it was lost from. */
export function reopenLead({ leadId, body, idempotencyKey }: ReopenLeadInput): Promise<Lead> {
  return apiRequest({
    dataId: "LEAD-007",
    logger: log,
    fn: "reopenLead",
    method: "POST",
    path: `/leads/${encodeURIComponent(leadId)}/reopen`,
    body,
    idempotencyKey,
    schema: leadResponseSchema,
  });
}

/** LEAD-008 · GET /leads/assignees — who the caller may make the owner. */
export function listAssignees(signal?: AbortSignal): Promise<Assignee[]> {
  return apiRequest({
    dataId: "LEAD-008",
    logger: log,
    fn: "listAssignees",
    path: "/leads/assignees",
    schema: assigneeListResponseSchema,
    signal,
  });
}

/** How many partners one search returns. */
export const PARTNER_SEARCH_LIMIT = 20;

/** LEAD-008 · GET /lookups/partners — channel partners in scope, by name or code. */
export function searchPartners(q: string, signal?: AbortSignal): Promise<PartnerPick[]> {
  return apiRequest({
    dataId: "LEAD-008",
    logger: log,
    fn: "searchPartners",
    path: "/lookups/partners",
    query: { q, limit: PARTNER_SEARCH_LIMIT },
    schema: partnerPickListResponseSchema,
    signal,
  });
}

export interface AssignLeadInput {
  readonly leadId: string;
  readonly body: AssignLeadRequest;
  readonly idempotencyKey: string;
}

/** LEAD-008 · POST /leads/{leadId}/assign — returns the lead with its new owner or partner. */
export function assignLead({ leadId, body, idempotencyKey }: AssignLeadInput): Promise<Lead> {
  return apiRequest({
    dataId: "LEAD-008",
    logger: log,
    fn: "assignLead",
    method: "POST",
    path: `/leads/${encodeURIComponent(leadId)}/assign`,
    body,
    idempotencyKey,
    schema: leadResponseSchema,
  });
}

/** LEAD-001 · GET /leads/areas — the area filter's options at one level, with lead counts. */
export function listLeadAreas(params: LeadAreasParams, signal?: AbortSignal): Promise<LeadArea[]> {
  return apiRequest({
    dataId: "LEAD-001",
    logger: log,
    fn: "listLeadAreas",
    path: "/leads/areas",
    query: { level: params.level, parent_id: params.parentId },
    schema: leadAreasResponseSchema,
    signal,
  });
}
