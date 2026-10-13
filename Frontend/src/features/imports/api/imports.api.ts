import { z } from "zod";

import { apiRequest } from "@/lib/api/client";
import type { ApiPath } from "@/lib/api/url";
import { createLogger } from "@/lib/logger";

import {
  importBatchSchema,
  importCheckSchema,
  importCommitSchema,
  type ImportBatch,
  type ImportCheck,
  type ImportCheckRequest,
  type ImportCommitResult,
  type ImportKind,
} from "./imports.schemas";

const log = createLogger({ file: "features/imports/api/imports.api.ts", dataId: "MSTR-007" });

/** A sheet of thousands of rows takes longer than a JSON call. */
const IMPORT_TIMEOUT_MS = 90_000;

function batchPath(batchId: string, rest = ""): ApiPath {
  return `/imports/${encodeURIComponent(batchId)}${rest}`;
}

export interface UploadImportInput {
  readonly kind: ImportKind;
  /** A picked `File`, or any named Blob. */
  readonly file: Blob & { readonly name: string };
  /** The draft price list, for `price_list_items` only. */
  readonly targetId?: string | undefined;
  /** Another sheet of the workbook, or another header row: a new upload of the same file. */
  readonly sheet?: string | undefined;
  readonly headerRow?: number | undefined;
  readonly idempotencyKey: string;
}

/**
 * MSTR-007 · POST /imports — step 1: the sheet's headers, five sample rows, this kind's fields
 * and a suggested match. Multipart; `.xlsx` or `.csv`, 10 MB and 5,000 rows at most.
 */
export function uploadImport({
  kind,
  file,
  targetId,
  sheet,
  headerRow,
  idempotencyKey,
}: UploadImportInput): Promise<ImportBatch> {
  const body = new FormData();
  body.append("kind", kind);
  body.append("file", file, file.name);
  if (targetId !== undefined) body.append("target_id", targetId);
  if (sheet !== undefined) body.append("sheet", sheet);
  if (headerRow !== undefined) body.append("header_row", String(headerRow));
  return apiRequest({
    dataId: "MSTR-007",
    logger: log,
    fn: "uploadImport",
    method: "POST",
    path: "/imports",
    body,
    idempotencyKey,
    timeoutMs: IMPORT_TIMEOUT_MS,
    schema: importBatchSchema,
  });
}

/** MSTR-007 · POST /imports/{id}/check — step 2: every row against a mapping. Run as often as needed. */
export function checkImport({
  batchId,
  body,
  idempotencyKey,
}: {
  batchId: string;
  body: ImportCheckRequest;
  idempotencyKey: string;
}): Promise<ImportCheck> {
  return apiRequest({
    dataId: "MSTR-007",
    logger: log,
    fn: "checkImport",
    method: "POST",
    path: batchPath(batchId, "/check"),
    body,
    idempotencyKey,
    timeoutMs: IMPORT_TIMEOUT_MS,
    schema: importCheckSchema,
  });
}

/**
 * MSTR-007 · POST /imports/{id}/commit — step 3, partners and rates only: all or nothing, unless
 * `skipInvalid` saves the good rows. Every row is checked again first.
 */
export function commitImport({
  batchId,
  skipInvalid,
  idempotencyKey,
}: {
  batchId: string;
  skipInvalid: boolean;
  idempotencyKey: string;
}): Promise<ImportCommitResult> {
  return apiRequest({
    dataId: "MSTR-007",
    logger: log,
    fn: "commitImport",
    method: "POST",
    path: batchPath(batchId, "/commit"),
    body: { skip_invalid: skipInvalid },
    idempotencyKey,
    timeoutMs: IMPORT_TIMEOUT_MS,
    schema: importCommitSchema,
  });
}

/** MSTR-007 · DELETE /imports/{id} — an import closed without committing: its rows go at once. */
export async function discardImport({
  batchId,
  idempotencyKey,
}: {
  batchId: string;
  idempotencyKey: string;
}): Promise<void> {
  await apiRequest({
    dataId: "MSTR-007",
    logger: log,
    fn: "discardImport",
    method: "DELETE",
    path: batchPath(batchId),
    idempotencyKey,
    schema: z.undefined(),
  });
}
