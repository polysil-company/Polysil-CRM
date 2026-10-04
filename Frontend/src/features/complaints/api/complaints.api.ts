import { z } from "zod";

import { timelinePageSchema, type TimelinePage } from "@/features/leads/api/leads.schemas";
import { apiRequest } from "@/lib/api/client";
import type { DataId } from "@/lib/data-ids";
import { createLogger } from "@/lib/logger";

import {
  COMPLAINT_PAGE_SIZE,
  complaintAssigneesSchema,
  complaintPageSchema,
  complaintResponseSchema,
  complaintStatsSchema,
  type CancelComplaintRequest,
  type CheckRequest,
  type Complaint,
  type ComplaintAssignee,
  type ComplaintListParams,
  type ComplaintPage,
  type ComplaintStats,
  type CreateComplaintRequest,
  type PatchComplaintRequest,
  type QcRequest,
  type ReplaceLinesRequest,
} from "./complaints.schemas";

const log = createLogger({ file: "features/complaints/api/complaints.api.ts", dataId: "CMPL-001" });

const noContentSchema = z.undefined();

/** One write: its body and the key that makes a retry safe to replay. */
export interface WriteInput<TBody> {
  readonly body: TBody;
  readonly idempotencyKey: string;
}

function complaintPath(complaintId: string, rest = ""): `/${string}` {
  return `/complaints/${encodeURIComponent(complaintId)}${rest}`;
}

/** CMPL-001 · GET /complaints — newest first; `awaiting=me` is the user's queue, oldest first. */
export async function listComplaints(
  params: ComplaintListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<ComplaintPage> {
  const page = await apiRequest({
    dataId: "CMPL-001",
    logger: log,
    fn: "listComplaints",
    path: "/complaints",
    query: {
      status: params.status.length === 0 ? undefined : [...params.status],
      severity: params.severity ?? undefined,
      complaint_type_id: params.typeId ?? undefined,
      q: params.q === "" ? undefined : params.q,
      breached: params.breached ? true : undefined,
      owner: params.noOwner ? "none" : undefined,
      awaiting: params.awaitingMe ? "me" : undefined,
      lead_id: params.leadId ?? undefined,
      sales_order_id: params.orderId ?? undefined,
      cursor: params.cursor,
      limit: COMPLAINT_PAGE_SIZE,
      include_total: params.cursor === null,
    },
    schema: complaintPageSchema,
    signal,
  });
  if (page.skipped > 0) {
    log.warn(
      "listComplaints",
      `left out ${String(page.skipped)} complaint(s) that did not match the contract`,
      { dataId: "CMPL-001", context: { skipped: page.skipped, kept: page.items.length } },
    );
  }
  return page;
}

/** CMPL-001 · GET /complaints/stats — counts by status, breached, and whether uploads work. */
export function getComplaintStats(signal?: AbortSignal): Promise<ComplaintStats> {
  return apiRequest({
    dataId: "CMPL-001",
    logger: log,
    fn: "getComplaintStats",
    path: "/complaints/stats",
    schema: complaintStatsSchema,
    signal,
  });
}

/** CMPL-002 · GET /complaints/{id} */
export function getComplaint(complaintId: string, signal?: AbortSignal): Promise<Complaint> {
  return apiRequest({
    dataId: "CMPL-002",
    logger: log,
    fn: "getComplaint",
    path: complaintPath(complaintId),
    schema: complaintResponseSchema,
    signal,
  });
}

/** CMPL-002 · GET /complaints/{id}/timeline — newest first. */
export function getComplaintTimeline(
  { complaintId, cursor }: { complaintId: string; cursor: string | null },
  signal?: AbortSignal,
): Promise<TimelinePage> {
  return apiRequest({
    dataId: "CMPL-002",
    logger: log,
    fn: "getComplaintTimeline",
    path: complaintPath(complaintId, "/timeline"),
    query: { cursor, limit: 20 },
    schema: timelinePageSchema,
    signal,
  });
}

/** One write that answers with the complaint. */
function write<TBody>(
  dataId: DataId,
  fn: string,
  method: "POST" | "PATCH" | "PUT",
  path: `/${string}`,
  { body, idempotencyKey }: WriteInput<TBody>,
): Promise<Complaint> {
  return apiRequest({
    dataId,
    logger: log,
    fn,
    method,
    path,
    body,
    idempotencyKey,
    schema: complaintResponseSchema,
  });
}

/** CMPL-003 · POST /complaints — a draft. */
export function createComplaint(input: WriteInput<CreateComplaintRequest>): Promise<Complaint> {
  return write("CMPL-003", "createComplaint", "POST", "/complaints", input);
}

/** CMPL-003 · PATCH /complaints/{id} — a draft's header. */
export function patchComplaint(
  complaintId: string,
  input: WriteInput<PatchComplaintRequest>,
): Promise<Complaint> {
  return write("CMPL-003", "patchComplaint", "PATCH", complaintPath(complaintId), input);
}

/** CMPL-003 · PUT /complaints/{id}/lines — a draft's products. */
export function replaceComplaintLines(
  complaintId: string,
  input: WriteInput<ReplaceLinesRequest>,
): Promise<Complaint> {
  return write(
    "CMPL-003",
    "replaceComplaintLines",
    "PUT",
    complaintPath(complaintId, "/lines"),
    input,
  );
}

/** CMPL-003 · POST /complaints/{id}/submit — numbers it and starts the targets. */
export function submitComplaint(complaintId: string, idempotencyKey: string): Promise<Complaint> {
  return write("CMPL-003", "submitComplaint", "POST", complaintPath(complaintId, "/submit"), {
    body: {},
    idempotencyKey,
  });
}

/** CMPL-003 · POST /complaints/{id}/cancel — a draft or a submitted one, with a reason. */
export function cancelComplaint(
  complaintId: string,
  input: WriteInput<CancelComplaintRequest>,
): Promise<Complaint> {
  return write("CMPL-003", "cancelComplaint", "POST", complaintPath(complaintId, "/cancel"), input);
}

/** CMPL-003 · DELETE /complaints/{id} — a draft never submitted. */
export function deleteComplaint(complaintId: string, idempotencyKey: string): Promise<void> {
  return apiRequest({
    dataId: "CMPL-003",
    logger: log,
    fn: "deleteComplaint",
    method: "DELETE",
    path: complaintPath(complaintId),
    idempotencyKey,
    schema: noContentSchema,
  });
}

/** CMPL-004 · POST /complaints/{id}/check — approve (to QC) or return (to the raiser). */
export function checkComplaint(
  complaintId: string,
  input: WriteInput<CheckRequest>,
): Promise<Complaint> {
  return write("CMPL-004", "checkComplaint", "POST", complaintPath(complaintId, "/check"), input);
}

/** CMPL-004 · GET /complaints/{id}/assignees — who may own it. */
export function listComplaintAssignees(
  complaintId: string,
  signal?: AbortSignal,
): Promise<ComplaintAssignee[]> {
  return apiRequest({
    dataId: "CMPL-004",
    logger: log,
    fn: "listComplaintAssignees",
    path: complaintPath(complaintId, "/assignees"),
    schema: complaintAssigneesSchema,
    signal,
  });
}

/** CMPL-005 · POST /complaints/{id}/qc — approved or rejected, with the sample's dates. */
export function qcComplaint(complaintId: string, input: WriteInput<QcRequest>): Promise<Complaint> {
  return write("CMPL-005", "qcComplaint", "POST", complaintPath(complaintId, "/qc"), input);
}
