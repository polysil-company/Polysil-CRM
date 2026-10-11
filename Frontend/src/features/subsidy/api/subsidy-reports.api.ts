import { apiDownload, apiRequest, type DownloadedFile } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import type { ApplicationStatus } from "./subsidy-applications.schemas";
import {
  AGEING_PAGE_SIZE,
  ageingPageSchema,
  stageReportSchema,
  supplyReportSchema,
  type AgeingPage,
  type AgeingParams,
  type StageReportRow,
  type SupplyReportRow,
} from "./subsidy-reports.schemas";

const log = createLogger({
  file: "features/subsidy/api/subsidy-reports.api.ts",
  dataId: "SUBS-009",
});

function ageingQuery(params: AgeingParams): Record<string, string | undefined> {
  return {
    status: params.status ?? undefined,
    stage: params.stage ?? undefined,
    q: params.q === "" ? undefined : params.q,
  };
}

/** SUBS-009 · GET /subsidy-reports/ageing — newest first, a page at a time. */
export function getAgeing(
  params: AgeingParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<AgeingPage> {
  return apiRequest({
    dataId: "SUBS-009",
    logger: log,
    fn: "getAgeing",
    path: "/subsidy-reports/ageing",
    query: { ...ageingQuery(params), cursor: params.cursor, limit: AGEING_PAGE_SIZE },
    schema: ageingPageSchema,
    signal,
  });
}

/** SUBS-009 · GET /subsidy-reports/ageing/export */
export function exportAgeing(params: AgeingParams): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "SUBS-009",
    logger: log,
    fn: "exportAgeing",
    path: "/subsidy-reports/ageing/export",
    query: ageingQuery(params),
  });
}

/**
 * SUBS-010 · GET /subsidy-reports/stages — one row per stage holding an application, for one
 * status (the backend's default is open; it has no "every status").
 */
export function getStageReport(
  status: ApplicationStatus,
  signal?: AbortSignal,
): Promise<StageReportRow[]> {
  return apiRequest({
    dataId: "SUBS-010",
    logger: log,
    fn: "getStageReport",
    path: "/subsidy-reports/stages",
    query: { status },
    schema: stageReportSchema,
    signal,
  });
}

/** SUBS-010 · GET /subsidy-reports/stages/export */
export function exportStageReport(status: ApplicationStatus): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "SUBS-010",
    logger: log,
    fn: "exportStageReport",
    path: "/subsidy-reports/stages/export",
    query: { status },
  });
}

/** SUBS-011 · GET /subsidy-reports/supply — by district; cancelled ones left out by default. */
export function getSupplyReport(
  status: ApplicationStatus | null,
  signal?: AbortSignal,
): Promise<SupplyReportRow[]> {
  return apiRequest({
    dataId: "SUBS-011",
    logger: log,
    fn: "getSupplyReport",
    path: "/subsidy-reports/supply",
    query: { status: status ?? undefined },
    schema: supplyReportSchema,
    signal,
  });
}

/** SUBS-011 · GET /subsidy-reports/supply/export */
export function exportSupplyReport(status: ApplicationStatus | null): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "SUBS-011",
    logger: log,
    fn: "exportSupplyReport",
    path: "/subsidy-reports/supply/export",
    query: { status: status ?? undefined },
  });
}
