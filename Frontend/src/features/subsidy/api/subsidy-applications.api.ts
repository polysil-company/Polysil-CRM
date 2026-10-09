import { apiDownload, apiRequest, type DownloadedFile } from "@/lib/api/client";
import type { ApiPath } from "@/lib/api/url";
import { createLogger } from "@/lib/logger";

import {
  APPLICATION_PAGE_SIZE,
  applicationPageSchema,
  applicationResponseSchema,
  checklistSchema,
  documentLinkSchema,
  leadSchemeSchema,
  stageDefsSchema,
  stageEntriesSchema,
  storedCalculationSchema,
  uploadedDocumentSchema,
  type Application,
  type ApplicationListParams,
  type ApplicationPage,
  type CancelApplicationRequest,
  type ChecklistItem,
  type CreateApplicationRequest,
  type DocumentLink,
  type LeadScheme,
  type RecordStageRequest,
  type StageDef,
  type StageEntry,
} from "./subsidy-applications.schemas";
import type { SubsidyCalculation } from "./subsidy.schemas";

const log = createLogger({
  file: "features/subsidy/api/subsidy-applications.api.ts",
  dataId: "SUBS-006",
});

const BASE = "/subsidy-applications";

function applicationPath(applicationId: string, rest = ""): ApiPath {
  return `${BASE}/${encodeURIComponent(applicationId)}${rest}`;
}

export interface WriteInput<TBody> {
  readonly body: TBody;
  readonly idempotencyKey: string;
}

function filterQuery(params: ApplicationListParams): Record<string, string | undefined> {
  return {
    status: params.status ?? undefined,
    stage: params.stage ?? undefined,
    q: params.q === "" ? undefined : params.q,
    // TODO(SUBS-006): BE-023 — the backend ignores this until it adds the filter.
    lead_id: params.leadId ?? undefined,
  };
}

/** SUBS-004 · POST /subsidy-applications — forward a subsidised lead; it moves to won. */
export function createApplication({
  body,
  idempotencyKey,
}: WriteInput<CreateApplicationRequest>): Promise<Application> {
  return apiRequest({
    dataId: "SUBS-004",
    logger: log,
    fn: "createApplication",
    method: "POST",
    path: BASE,
    body,
    idempotencyKey,
    schema: applicationResponseSchema,
  });
}

/**
 * SUBS-004 · GET /subsidy-schemes/for-lead/{leadId} — the scheme the lead's state runs. 422
 * `no_scheme_for_state` or `territory_without_state_code` when there is none to use.
 */
export function getLeadScheme(leadId: string, signal?: AbortSignal): Promise<LeadScheme> {
  return apiRequest({
    dataId: "SUBS-004",
    logger: log,
    fn: "getLeadScheme",
    path: `/subsidy-schemes/for-lead/${encodeURIComponent(leadId)}`,
    schema: leadSchemeSchema,
    signal,
  });
}

/** SUBS-005 · GET /subsidy-applications — newest first, in the caller's scope. */
export async function listApplications(
  params: ApplicationListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<ApplicationPage> {
  const page = await apiRequest({
    dataId: "SUBS-005",
    logger: log,
    fn: "listApplications",
    path: BASE,
    query: { ...filterQuery(params), cursor: params.cursor, limit: APPLICATION_PAGE_SIZE },
    schema: applicationPageSchema,
    signal,
  });
  if (params.leadId === null) return page;
  return { ...page, items: page.items.filter((row) => row.lead.id === params.leadId) };
}

/** SUBS-005 · GET /subsidy-applications/export — the list as Excel, with the same filters. */
export function exportApplications(params: ApplicationListParams): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "SUBS-005",
    logger: log,
    fn: "exportApplications",
    path: `${BASE}/export`,
    query: filterQuery({ ...params, leadId: null }),
  });
}

/** SUBS-006 · GET /subsidy-applications/{id} */
export function getApplication(applicationId: string, signal?: AbortSignal): Promise<Application> {
  return apiRequest({
    dataId: "SUBS-006",
    logger: log,
    fn: "getApplication",
    path: applicationPath(applicationId),
    schema: applicationResponseSchema,
    signal,
  });
}

/** SUBS-006 · GET /subsidy-applications/{id}/calculation — as stored at create. */
export function getStoredCalculation(
  applicationId: string,
  signal?: AbortSignal,
): Promise<SubsidyCalculation> {
  return apiRequest({
    dataId: "SUBS-006",
    logger: log,
    fn: "getStoredCalculation",
    path: applicationPath(applicationId, "/calculation"),
    schema: storedCalculationSchema,
    signal,
  });
}

/**
 * SUBS-006 · GET /subsidy-stages — a scheme's stages and their fields; data, never hard-coded.
 * Null asks for the backend's default (GGRC).
 */
export function listStageDefs(scheme: string | null, signal?: AbortSignal): Promise<StageDef[]> {
  return apiRequest({
    dataId: "SUBS-006",
    logger: log,
    fn: "listStageDefs",
    path: "/subsidy-stages",
    query: { scheme: scheme ?? undefined },
    schema: stageDefsSchema,
    signal,
  });
}

/** SUBS-006 · GET /subsidy-applications/{id}/stages — the history, oldest first. */
export function listStageEntries(
  applicationId: string,
  signal?: AbortSignal,
): Promise<StageEntry[]> {
  return apiRequest({
    dataId: "SUBS-006",
    logger: log,
    fn: "listStageEntries",
    path: applicationPath(applicationId, "/stages"),
    schema: stageEntriesSchema,
    signal,
  });
}

/** SUBS-006 · POST /subsidy-applications/{id}/stages */
export function recordStage(
  applicationId: string,
  { body, idempotencyKey }: WriteInput<RecordStageRequest>,
): Promise<Application> {
  return apiRequest({
    dataId: "SUBS-006",
    logger: log,
    fn: "recordStage",
    method: "POST",
    path: applicationPath(applicationId, "/stages"),
    body,
    idempotencyKey,
    schema: applicationResponseSchema,
  });
}

/** SUBS-006 · POST /subsidy-applications/{id}/cancel — frees the lead to start again. */
export function cancelApplication(
  applicationId: string,
  { body, idempotencyKey }: WriteInput<CancelApplicationRequest>,
): Promise<Application> {
  return apiRequest({
    dataId: "SUBS-006",
    logger: log,
    fn: "cancelApplication",
    method: "POST",
    path: applicationPath(applicationId, "/cancel"),
    body,
    idempotencyKey,
    schema: applicationResponseSchema,
  });
}

/** SUBS-007 · GET /subsidy-applications/{id}/documents — the checklist with its files. */
export function listChecklist(
  applicationId: string,
  signal?: AbortSignal,
): Promise<ChecklistItem[]> {
  return apiRequest({
    dataId: "SUBS-007",
    logger: log,
    fn: "listChecklist",
    path: applicationPath(applicationId, "/documents"),
    schema: checklistSchema,
    signal,
  });
}

/**
 * SUBS-007 · POST /subsidy-applications/{id}/documents — one file against a checklist item,
 * multipart. The same file again answers with the one already there.
 */
export async function uploadApplicationDocument({
  applicationId,
  documentType,
  file,
  idempotencyKey,
}: {
  applicationId: string;
  documentType: string;
  /** A picked `File`, or any named Blob. */
  file: Blob & { readonly name: string };
  idempotencyKey: string;
}): Promise<void> {
  const body = new FormData();
  body.append("file", file, file.name);
  body.append("document_type", documentType);
  await apiRequest({
    dataId: "SUBS-007",
    logger: log,
    fn: "uploadApplicationDocument",
    method: "POST",
    path: applicationPath(applicationId, "/documents"),
    body,
    idempotencyKey,
    // Uploads over a field connection take longer than a JSON call.
    timeoutMs: 90_000,
    schema: uploadedDocumentSchema,
  });
}

/** SUBS-007 · GET …/documents/{docId} — a ten-minute link; never fetched with the token. */
export function getDocumentLink(
  applicationId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentLink> {
  return apiRequest({
    dataId: "SUBS-007",
    logger: log,
    fn: "getDocumentLink",
    path: applicationPath(applicationId, `/documents/${encodeURIComponent(documentId)}`),
    schema: documentLinkSchema,
    signal,
  });
}

/** SUBS-008 · GET /subsidy-applications/{id}/pims.xlsx — the sheet for the GGRC portal. */
export function downloadPims(applicationId: string): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "SUBS-008",
    logger: log,
    fn: "downloadPims",
    path: applicationPath(applicationId, "/pims.xlsx"),
  });
}
