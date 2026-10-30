import { z } from "zod";

import { apiRequest } from "@/lib/api/client";
import type { ApiPath } from "@/lib/api/url";
import { createLogger } from "@/lib/logger";

import {
  documentLinkSchema,
  documentListSchema,
  documentSchema,
  documentTypesSchema,
  type DocumentLink,
  type DocumentType,
  type RecordDocument,
  type RecordType,
} from "./documents.schemas";

const log = createLogger({ file: "features/documents/api/documents.api.ts", dataId: "DOC-001" });

/** An upload of 10 MB takes longer than a JSON call. */
const UPLOAD_TIMEOUT_MS = 90_000;

function documentPath(documentId: string, rest = ""): ApiPath {
  return `/documents/${encodeURIComponent(documentId)}${rest}`;
}

/** DOC-001 · GET /documents — the documents on one record, newest first. */
export function listDocuments(
  recordType: RecordType,
  recordId: string,
  signal?: AbortSignal,
): Promise<RecordDocument[]> {
  return apiRequest({
    dataId: "DOC-001",
    logger: log,
    fn: "listDocuments",
    path: "/documents",
    query: { record_type: recordType, record_id: recordId },
    schema: documentListSchema,
    signal,
  });
}

/**
 * DOC-001 · GET /leads/{id}/documents — everything on the lead and on what came from it: its
 * quotations, their orders, those orders' dispatches and payments, and leads merged into it.
 * Each names its record.
 */
export function listLeadDocuments(leadId: string, signal?: AbortSignal): Promise<RecordDocument[]> {
  return apiRequest({
    dataId: "DOC-001",
    logger: log,
    fn: "listLeadDocuments",
    path: `/leads/${encodeURIComponent(leadId)}/documents`,
    schema: documentListSchema,
    signal,
  });
}

/**
 * DOC-001 · GET /documents/types — the type picker's choices; "other" needs a name. With a
 * record type, only the types that belong on that record (BE-025); without, every type.
 */
export function listDocumentTypes(
  recordType: RecordType | null = null,
  signal?: AbortSignal,
): Promise<DocumentType[]> {
  return apiRequest({
    dataId: "DOC-001",
    logger: log,
    fn: "listDocumentTypes",
    path: "/documents/types",
    query: { record_type: recordType ?? undefined },
    schema: documentTypesSchema,
    signal,
  });
}

/** DOC-001 · GET /documents/{id}/link — a ten-minute link, for an image or a download. */
export function getDocumentLink(documentId: string, signal?: AbortSignal): Promise<DocumentLink> {
  return apiRequest({
    dataId: "DOC-001",
    logger: log,
    fn: "getDocumentLink",
    path: documentPath(documentId, "/link"),
    schema: documentLinkSchema,
    signal,
  });
}

export interface UploadDocumentInput {
  readonly recordType: RecordType;
  readonly recordId: string;
  readonly docType: string;
  /** Required for "other"; a note otherwise. */
  readonly name: string | null;
  readonly file: Blob & { readonly name: string };
  readonly idempotencyKey: string;
}

/**
 * DOC-002 · POST /documents — multipart. `201` adds it; the same file with the same type on
 * the same record answers `200` with the one already there.
 */
export function uploadDocument({
  recordType,
  recordId,
  docType,
  name,
  file,
  idempotencyKey,
}: UploadDocumentInput): Promise<RecordDocument> {
  const body = new FormData();
  body.append("record_type", recordType);
  body.append("record_id", recordId);
  body.append("doc_type", docType);
  if (name !== null) body.append("name", name);
  body.append("file", file, file.name);
  return apiRequest({
    dataId: "DOC-002",
    logger: log,
    fn: "uploadDocument",
    method: "POST",
    path: "/documents",
    body,
    idempotencyKey,
    timeoutMs: UPLOAD_TIMEOUT_MS,
    schema: documentSchema,
  });
}

/** DOC-003 · DELETE /documents/{id} — by whoever added it, or staff who may add to the record. */
export async function deleteDocument({
  documentId,
  idempotencyKey,
}: {
  documentId: string;
  idempotencyKey: string;
}): Promise<void> {
  await apiRequest({
    dataId: "DOC-003",
    logger: log,
    fn: "deleteDocument",
    method: "DELETE",
    path: documentPath(documentId),
    idempotencyKey,
    schema: z.undefined(),
  });
}
