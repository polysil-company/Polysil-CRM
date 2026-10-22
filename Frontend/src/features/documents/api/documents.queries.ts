import { queryOptions } from "@tanstack/react-query";

import {
  getDocumentLink,
  listDocumentTypes,
  listDocuments,
  listLeadDocuments,
} from "./documents.api";
import type { DocumentsScope, RecordType } from "./documents.schemas";

/**
 * Query keys for documents. A document added to a quotation shows on its lead too, so writes
 * invalidate `documentKeys.all`.
 */
export const documentKeys = {
  all: ["documents"] as const,
  record: (recordType: RecordType, recordId: string) =>
    [...documentKeys.all, "record", recordType, recordId] as const,
  lead: (leadId: string) => [...documentKeys.all, "lead", leadId] as const,
  types: (recordType: RecordType | null) => [...documentKeys.all, "types", recordType] as const,
  link: (documentId: string) => [...documentKeys.all, "link", documentId] as const,
};

/**
 * DOC-001 · The documents on one record, or on a lead and everything made from it (each
 * naming its record).
 */
export function documentsQueryOptions(scope: DocumentsScope) {
  return queryOptions({
    queryKey:
      scope.kind === "lead"
        ? documentKeys.lead(scope.leadId)
        : documentKeys.record(scope.recordType, scope.recordId),
    queryFn: ({ signal }) =>
      scope.kind === "lead"
        ? listLeadDocuments(scope.leadId, signal)
        : listDocuments(scope.recordType, scope.recordId, signal),
    meta: { dataId: "DOC-001" },
  });
}

/** DOC-001 · The types a record takes (BE-025); the list changes only with a release. */
export function documentTypesQueryOptions(recordType: RecordType | null = null) {
  return queryOptions({
    queryKey: documentKeys.types(recordType),
    queryFn: ({ signal }) => listDocumentTypes(recordType, signal),
    staleTime: 30 * 60_000,
    meta: { dataId: "DOC-001" },
  });
}

/** DOC-001 · A ten-minute link, renewed before it runs out. */
export function documentLinkQueryOptions(documentId: string) {
  return queryOptions({
    queryKey: documentKeys.link(documentId),
    queryFn: ({ signal }) => getDocumentLink(documentId, signal),
    staleTime: 9 * 60_000,
    refetchInterval: 9 * 60_000,
    meta: { dataId: "DOC-001" },
  });
}
