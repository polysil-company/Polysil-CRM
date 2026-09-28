import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  QUEUE_PAGE_SIZE,
  decisionResultSchema,
  queuePageSchema,
  type DecisionRequest,
  type DecisionResult,
  type QueuePage,
  type QueueParams,
} from "./approvals.schemas";

const log = createLogger({ file: "features/approvals/api/approvals.api.ts", dataId: "APPR-001" });

/**
 * APPR-001 · GET /approvals/pending — what is waiting on the user, oldest first. The first
 * page asks for the count, for the badge.
 */
export async function listPendingApprovals(
  params: QueueParams & { cursor: string | null; limit?: number },
  signal?: AbortSignal,
): Promise<QueuePage> {
  const page = await apiRequest({
    dataId: "APPR-001",
    logger: log,
    fn: "listPendingApprovals",
    path: "/approvals/pending",
    query: {
      limit: params.limit ?? QUEUE_PAGE_SIZE,
      cursor: params.cursor,
      include_total: params.cursor === null,
      include_below: params.includeBelow ? true : undefined,
    },
    schema: queuePageSchema,
    signal,
  });
  if (page.skipped > 0) {
    // A backend-side issue: the rest of the inbox is still shown.
    log.warn(
      "listPendingApprovals",
      `left out ${String(page.skipped)} row(s) that did not match the contract`,
      { dataId: "APPR-001", context: { skipped: page.skipped, kept: page.items.length } },
    );
  }
  return page;
}

/** APPR-001 · POST /approvals/steps/{id}/decision — approve or reject one step. */
export function decideApprovalStep(
  stepId: string,
  { body, idempotencyKey }: { body: DecisionRequest; idempotencyKey: string },
): Promise<DecisionResult> {
  return apiRequest({
    dataId: "APPR-001",
    logger: log,
    fn: "decideApprovalStep",
    method: "POST",
    path: `/approvals/steps/${encodeURIComponent(stepId)}/decision`,
    body,
    idempotencyKey,
    schema: decisionResultSchema,
  });
}
