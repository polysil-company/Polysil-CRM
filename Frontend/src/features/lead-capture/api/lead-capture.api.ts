import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  publicLeadFormSchema,
  publicLeadResultSchema,
  publicTerritoriesSchema,
  qrCodeListSchema,
  qrCodeResponseSchema,
  verifySentSchema,
  type CreateQrCodeRequest,
  type PatchQrCodeRequest,
  type PublicLeadForm,
  type PublicLeadRequest,
  type PublicLeadResult,
  type PublicTerritory,
  type QrCode,
  type VerifySent,
} from "./lead-capture.schemas";

const log = createLogger({
  file: "features/lead-capture/api/lead-capture.api.ts",
  dataId: "LEAD-013",
});

// ── QR codes (LEAD-013) ──────────────────────────────────────────────────────────

/** LEAD-013 · GET /lead-qr-codes — newest first, each with the leads it brought. */
export function listQrCodes(signal?: AbortSignal): Promise<QrCode[]> {
  return apiRequest({
    dataId: "LEAD-013",
    logger: log,
    fn: "listQrCodes",
    path: "/lead-qr-codes",
    schema: qrCodeListSchema,
    signal,
  });
}

/** LEAD-013 · POST /lead-qr-codes */
export function createQrCode({
  body,
  idempotencyKey,
}: {
  body: CreateQrCodeRequest;
  idempotencyKey: string;
}): Promise<QrCode> {
  return apiRequest({
    dataId: "LEAD-013",
    logger: log,
    fn: "createQrCode",
    method: "POST",
    path: "/lead-qr-codes",
    body,
    idempotencyKey,
    schema: qrCodeResponseSchema,
  });
}

/** LEAD-013 · PATCH /lead-qr-codes/{id} — rename, re-point, or switch off. */
export function patchQrCode({
  qrId,
  body,
  idempotencyKey,
}: {
  qrId: string;
  body: PatchQrCodeRequest;
  idempotencyKey: string;
}): Promise<QrCode> {
  return apiRequest({
    dataId: "LEAD-013",
    logger: log,
    fn: "patchQrCode",
    method: "PATCH",
    path: `/lead-qr-codes/${encodeURIComponent(qrId)}`,
    body,
    idempotencyKey,
    schema: qrCodeResponseSchema,
  });
}

// ── the public enquiry page (LEAD-014) ────────────────────────────────────────────

/** LEAD-014 · GET /public/lead-form — the code's label, the states and the systems. */
export function getPublicLeadForm(
  qr: string | null,
  signal?: AbortSignal,
): Promise<PublicLeadForm> {
  return apiRequest({
    dataId: "LEAD-014",
    logger: log,
    fn: "getPublicLeadForm",
    path: "/public/lead-form",
    query: { qr: qr ?? undefined },
    auth: "none",
    schema: publicLeadFormSchema,
    signal,
  });
}

/** LEAD-014 · GET /public/territories?parent_id= — a state's districts, a district's talukas. */
export function listPublicTerritories(
  parentId: string,
  signal?: AbortSignal,
): Promise<PublicTerritory[]> {
  return apiRequest({
    dataId: "LEAD-014",
    logger: log,
    fn: "listPublicTerritories",
    path: "/public/territories",
    query: { parent_id: parentId },
    auth: "none",
    schema: publicTerritoriesSchema,
    signal,
  });
}

/** LEAD-014 · POST /public/leads/verify — a six-digit code by WhatsApp. The mobile is masked. */
export function sendEnquiryCode(mobile: string): Promise<VerifySent> {
  return apiRequest({
    dataId: "LEAD-014",
    logger: log,
    fn: "sendEnquiryCode",
    method: "POST",
    path: "/public/leads/verify",
    body: { mobile },
    auth: "none",
    sensitive: true,
    schema: verifySentSchema,
  });
}

/** LEAD-014 · POST /public/leads — once the code matches; a retry answers the same number. */
export function submitEnquiry(body: PublicLeadRequest): Promise<PublicLeadResult> {
  return apiRequest({
    dataId: "LEAD-014",
    logger: log,
    fn: "submitEnquiry",
    method: "POST",
    path: "/public/leads",
    body,
    auth: "none",
    sensitive: true,
    schema: publicLeadResultSchema,
  });
}
