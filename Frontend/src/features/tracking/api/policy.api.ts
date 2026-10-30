import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  policySchema,
  viewLogPageSchema,
  type Policy,
  type PolicyRequest,
  type ViewLogPage,
} from "./policy.schemas";

const log = createLogger({ file: "features/tracking/api/policy.api.ts", dataId: "TRK-006" });

/** TRK-006 · The tracking policy in force. */
export function getTrackingPolicy(signal?: AbortSignal): Promise<Policy> {
  return apiRequest({
    dataId: "TRK-006",
    logger: log,
    fn: "getTrackingPolicy",
    path: "/tracking/policy",
    schema: policySchema,
    signal,
  });
}

/** TRK-006 · Add a version from `effective_from` (masters.edit). 409 `policy_exists`; 422 fields. */
export function putTrackingPolicy({
  body,
  idempotencyKey,
}: {
  readonly body: PolicyRequest;
  readonly idempotencyKey: string;
}): Promise<Policy> {
  return apiRequest({
    dataId: "TRK-006",
    logger: log,
    fn: "putTrackingPolicy",
    method: "PUT",
    path: "/tracking/policy",
    body,
    idempotencyKey,
    schema: policySchema,
  });
}

/** TRK-007 · Who looked at whose location, newest first; empty for anyone but Admin and MD. */
export function listViewLog(
  {
    subjectUserId,
    cursor,
  }: { readonly subjectUserId: string | null; readonly cursor: string | null },
  signal?: AbortSignal,
): Promise<ViewLogPage> {
  return apiRequest({
    dataId: "TRK-007",
    logger: log,
    fn: "listViewLog",
    path: "/tracking/view-log",
    query: { subject_user_id: subjectUserId, limit: 50, cursor },
    schema: viewLogPageSchema,
    signal,
  });
}
