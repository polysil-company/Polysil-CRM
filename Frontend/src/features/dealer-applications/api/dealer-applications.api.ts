import { apiDownload, apiRequest, type DownloadedFile, type ExportFormat } from "@/lib/api/client";
import type { ApiPath } from "@/lib/api/url";
import { createLogger } from "@/lib/logger";

import type { PartnerType } from "./data-sheet.schemas";
import {
  dealerApplicationListSchema,
  dealerApplicationSchema,
  type CreateDealerApplicationRequest,
  type DealerApplication,
  type StaffApplicationFieldsRequest,
  type DealerApplicationListParams,
  type DealerApplicationRow,
  type DecisionRequest,
  type DepositRecordRequest,
  type DepositRelaxationRequest,
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
      partner_type: params.partnerType ?? undefined,
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
}: WriteInput<StaffApplicationFieldsRequest>): Promise<DealerApplication> {
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

/** CHNL-007 · GET /dealer-applications/export (FS-081) — the applications, with the filters. */
export function exportDealerApplications(
  params: DealerApplicationListParams,
  format: ExportFormat = "xlsx",
): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "CHNL-007",
    logger: log,
    fn: "exportDealerApplications",
    path: "/dealer-applications/export",
    query: {
      status: params.status.length === 0 ? undefined : params.status.join(","),
      q: params.q.trim() === "" ? undefined : params.q.trim(),
      partner_type: params.partnerType ?? undefined,
      format,
    },
  });
}

/**
 * CHNL-007 · POST /dealer-applications/{id}/deposit (FS-071): the deposit paid, with the pay
 * slip already uploaded as a `deposit_slip` document. The latest payment counts.
 */
export function recordDealerApplicationDeposit({
  applicationId,
  body,
  idempotencyKey,
}: WriteInput<DepositRecordRequest>): Promise<DealerApplication> {
  return apiRequest({
    dataId: "CHNL-007",
    logger: log,
    fn: "recordDealerApplicationDeposit",
    method: "POST",
    path: applicationPath(applicationId, "/deposit"),
    body,
    idempotencyKey,
    schema: dealerApplicationSchema,
    sensitive: true,
  });
}

/**
 * CHNL-007 · POST /dealer-applications/{id}/deposit/relaxation (FS-071): a lower amount due,
 * or 0 to waive it, with why. Only the roles `deposit_relaxation_roles` names, never whoever
 * started the application, and not after a payment.
 */
export function relaxDealerApplicationDeposit({
  applicationId,
  body,
  idempotencyKey,
}: WriteInput<DepositRelaxationRequest>): Promise<DealerApplication> {
  return apiRequest({
    dataId: "CHNL-007",
    logger: log,
    fn: "relaxDealerApplicationDeposit",
    method: "POST",
    path: applicationPath(applicationId, "/deposit/relaxation"),
    body,
    idempotencyKey,
    schema: dealerApplicationSchema,
    sensitive: true,
  });
}

/**
 * CHNL-007 · GET /dealer-applications/form.pdf (FS-071): the blank data sheet for a dealer or
 * a distributor, to print and fill in by hand.
 */
export function downloadBlankApplicationForm(partnerType: PartnerType): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "CHNL-007",
    logger: log,
    fn: "downloadBlankApplicationForm",
    path: "/dealer-applications/form.pdf",
    query: { partner_type: partnerType },
  });
}

/**
 * CHNL-007 · GET /dealer-applications/{id}/pdf (FS-071): the data sheet filled from the
 * application, as the client's paper form. The bank account is masked for everyone.
 */
export function downloadDealerApplicationPdf(applicationId: string): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "CHNL-007",
    logger: log,
    fn: "downloadDealerApplicationPdf",
    path: applicationPath(applicationId, "/pdf"),
  });
}
