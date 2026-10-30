import { apiRequest } from "@/lib/api/client";
import type { ApiPath } from "@/lib/api/url";
import { createLogger } from "@/lib/logger";

import {
  dealerApplicationListSchema,
  dealerApplicationSchema,
  type CreateDealerApplicationRequest,
  type DealerApplication,
  type DealerApplicationFieldsRequest,
  type DealerApplicationListParams,
  type DealerApplicationRow,
  type DecisionRequest,
  type RemarkRequest,
} from "./dealer-applications.schemas";

const log = createLogger({
  file: "features/dealer-applications/api/dealer-applications.api.ts",
  dataId: "CHNL-007",
});

function applicationPath(applicationId: string, rest = ""): ApiPath {
  return `/dealer-applications/${encodeURIComponent(applicationId)}${rest}`;
}

interface WriteInput<TBody> {
  readonly applicationId: string;
  readonly body: TBody;
  readonly idempotencyKey: string;
}

/** CHNL-007 · GET /dealer-applications — in the caller's partners scope, newest first. */
export function listDealerApplications(
  params: DealerApplicationListParams,
  signal?: AbortSignal,
): Promise<DealerApplicationRow[]> {
  return apiRequest({
    dataId: "CHNL-007",
    logger: log,
    fn: "listDealerApplications",
    path: "/dealer-applications",
    query: {
      status: params.status.length === 0 ? undefined : params.status.join(","),
      q: params.q.trim() === "" ? undefined : params.q.trim(),
    },
    schema: dealerApplicationListSchema,
    signal,
  });
}

/** CHNL-007 · GET /dealer-applications/{id}: every field, `missing` and `can`. */
export function getDealerApplication(
  applicationId: string,
  signal?: AbortSignal,
): Promise<DealerApplication> {
  return apiRequest({
    dataId: "CHNL-007",
    logger: log,
    fn: "getDealerApplication",
    path: applicationPath(applicationId),
    schema: dealerApplicationSchema,
    // bank and tax numbers stay out of the logs
    sensitive: true,
    signal,
  });
}

/** CHNL-007 · POST /dealer-applications. Answers `apply_url`, shown only now. */
export function createDealerApplication({
  body,
  idempotencyKey,
}: {
  body: CreateDealerApplicationRequest;
  idempotencyKey: string;
}): Promise<DealerApplication> {
  return apiRequest({
    dataId: "CHNL-007",
    logger: log,
    fn: "createDealerApplication",
    method: "POST",
    path: "/dealer-applications",
    body,
    idempotencyKey,
    schema: dealerApplicationSchema,
    sensitive: true,
  });
}

/** CHNL-007 · PATCH /dealer-applications/{id}: staff fill fields for the applicant. */
export function patchDealerApplication({
  applicationId,
  body,
  idempotencyKey,
}: WriteInput<DealerApplicationFieldsRequest>): Promise<DealerApplication> {
  return apiRequest({
    dataId: "CHNL-007",
    logger: log,
    fn: "patchDealerApplication",
    method: "PATCH",
    path: applicationPath(applicationId),
    body,
    idempotencyKey,
    schema: dealerApplicationSchema,
    sensitive: true,
  });
}

/** CHNL-007 · POST …/submit for the applicant. `422 application_incomplete` names what's missing. */
export function submitDealerApplication({
  applicationId,
  idempotencyKey,
}: Omit<WriteInput<null>, "body">): Promise<DealerApplication> {
  return apiRequest({
    dataId: "CHNL-007",
    logger: log,
    fn: "submitDealerApplication",
    method: "POST",
    path: applicationPath(applicationId, "/submit"),
    idempotencyKey,
    schema: dealerApplicationSchema,
    sensitive: true,
  });
}

/** CHNL-007 · POST …/withdraw: closes an open application; its link stops working. */
export function withdrawDealerApplication({
  applicationId,
  body,
  idempotencyKey,
}: WriteInput<RemarkRequest>): Promise<DealerApplication> {
  return apiRequest({
    dataId: "CHNL-007",
    logger: log,
    fn: "withdrawDealerApplication",
    method: "POST",
    path: applicationPath(applicationId, "/withdraw"),
    body,
    idempotencyKey,
    schema: dealerApplicationSchema,
    sensitive: true,
  });
}

/** CHNL-007 · POST …/link: a new link for 30 days; the old one stops. Answers `apply_url`. */
export function renewDealerApplicationLink({
  applicationId,
  idempotencyKey,
}: Omit<WriteInput<null>, "body">): Promise<DealerApplication> {
  return apiRequest({
    dataId: "CHNL-007",
    logger: log,
    fn: "renewDealerApplicationLink",
    method: "POST",
    path: applicationPath(applicationId, "/link"),
    idempotencyKey,
    schema: dealerApplicationSchema,
    sensitive: true,
  });
}

/** CHNL-007 · POST …/decision: approving makes the dealer and its login. */
export function decideDealerApplication({
  applicationId,
  body,
  idempotencyKey,
}: WriteInput<DecisionRequest>): Promise<DealerApplication> {
  return apiRequest({
    dataId: "CHNL-007",
    logger: log,
    fn: "decideDealerApplication",
    method: "POST",
    path: applicationPath(applicationId, "/decision"),
    body,
    idempotencyKey,
    schema: dealerApplicationSchema,
    sensitive: true,
  });
}
