import { apiDownload, apiRequest, type DownloadedFile } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  commissionPageSchema,
  commissionPreviewSchema,
  commissionResponseSchema,
  rateListSchema,
  rateResponseSchema,
  type AddRateRequest,
  type Commission,
  type CommissionListParams,
  type CommissionPage,
  type CommissionPreview,
  type CommissionRate,
  type DecisionRequest,
  type PaymentRequest,
  type RecordCommissionRequest,
} from "./commission.schemas";

const log = createLogger({ file: "features/commission/api/commission.api.ts", dataId: "SUBS-016" });

export interface WriteInput<TBody> {
  readonly body: TBody;
  readonly idempotencyKey: string;
}

const applicationPath = (applicationId: string): `/${string}` =>
  `/subsidy-applications/${encodeURIComponent(applicationId)}/commission`;

/** SUBS-016 · Stage 18 before anything is typed. 409 not_closed, 422 no_partner. */
export function getCommissionPreview(
  applicationId: string,
  signal?: AbortSignal,
): Promise<CommissionPreview> {
  return apiRequest({
    dataId: "SUBS-016",
    logger: log,
    fn: "getCommissionPreview",
    path: `${applicationPath(applicationId)}/preview`,
    schema: commissionPreviewSchema,
    signal,
  });
}

/** SUBS-016 · The application's live commission; 404 when none is recorded. */
export function getLiveCommission(
  applicationId: string,
  signal?: AbortSignal,
): Promise<Commission> {
  return apiRequest({
    dataId: "SUBS-016",
    logger: log,
    fn: "getLiveCommission",
    path: applicationPath(applicationId),
    schema: commissionResponseSchema,
    signal,
  });
}

/** SUBS-016 · Record stage 18; again while calculated or returned replaces the figures. */
export function recordCommission(
  applicationId: string,
  { body, idempotencyKey }: WriteInput<RecordCommissionRequest>,
): Promise<Commission> {
  return apiRequest({
    dataId: "SUBS-016",
    logger: log,
    fn: "recordCommission",
    method: "POST",
    path: applicationPath(applicationId),
    body,
    idempotencyKey,
    schema: commissionResponseSchema,
  });
}

function listQuery(params: CommissionListParams): Record<string, string | undefined> {
  return { status: params.status ?? undefined };
}

/** SUBS-017 · The commission report, newest first; by status it is Accounts' queue. */
export function listCommissions(
  params: CommissionListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<CommissionPage> {
  return apiRequest({
    dataId: "SUBS-017",
    logger: log,
    fn: "listCommissions",
    path: "/dealer-commissions",
    query: { ...listQuery(params), cursor: params.cursor ?? undefined },
    schema: commissionPageSchema,
    signal,
  });
}

/** SUBS-017 · The same rows as an Excel workbook. */
export function exportCommissions(params: CommissionListParams): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "SUBS-017",
    logger: log,
    fn: "exportCommissions",
    path: "/dealer-commissions/export",
    query: listQuery(params),
  });
}

export type CommissionDecision = "approve" | "return" | "cancel";

/**
 * SUBS-017 · Approve (Accounts; never whoever recorded it: 403 own_decision), return with a
 * remark, or cancel with a remark. 409 status_changed when it has moved on.
 */
export function decideCommission(
  commissionId: string,
  decision: CommissionDecision,
  { body, idempotencyKey }: WriteInput<DecisionRequest>,
): Promise<Commission> {
  return apiRequest({
    dataId: "SUBS-017",
    logger: log,
    fn: "decideCommission",
    method: "POST",
    path: `/dealer-commissions/${encodeURIComponent(commissionId)}/${decision}`,
    body,
    idempotencyKey,
    schema: commissionResponseSchema,
  });
}

/** SUBS-017 · Record the payment of an approved commission. */
export function payCommission(
  commissionId: string,
  { body, idempotencyKey }: WriteInput<PaymentRequest>,
): Promise<Commission> {
  return apiRequest({
    dataId: "SUBS-017",
    logger: log,
    fn: "payCommission",
    method: "POST",
    path: `/dealer-commissions/${encodeURIComponent(commissionId)}/pay`,
    body,
    idempotencyKey,
    schema: commissionResponseSchema,
  });
}

/** SUBS-018 · Every rate of a scheme, newest first. */
export function listCommissionRates(
  scheme: string,
  signal?: AbortSignal,
): Promise<CommissionRate[]> {
  return apiRequest({
    dataId: "SUBS-018",
    logger: log,
    fn: "listCommissionRates",
    path: "/commission-rates",
    query: { scheme },
    schema: rateListSchema,
    signal,
  });
}

/** SUBS-018 · Add a rate from a date; rates are never edited. */
export function addCommissionRate({
  body,
  idempotencyKey,
}: WriteInput<AddRateRequest>): Promise<CommissionRate> {
  return apiRequest({
    dataId: "SUBS-018",
    logger: log,
    fn: "addCommissionRate",
    method: "POST",
    path: "/commission-rates",
    body,
    idempotencyKey,
    schema: rateResponseSchema,
  });
}
