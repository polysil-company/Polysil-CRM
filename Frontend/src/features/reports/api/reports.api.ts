import type { z } from "zod";

import { apiDownload, apiRequest, type DownloadedFile } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  lead360Schema,
  REPORT_SCHEMAS,
  type Lead360,
  type ReportData,
  type ReportName,
  type ReportParams,
} from "./reports.schemas";

const log = createLogger({ file: "features/reports/api/reports.api.ts", dataId: "RPT-002" });

/** The query a report takes: the window, areas, a person and its grouping, when set. */
function reportQuery(name: ReportName, params: ReportParams): Record<string, string | undefined> {
  return {
    from: params.from ?? undefined,
    to: params.to ?? undefined,
    territory_id: params.territories.length === 0 ? undefined : params.territories.join(","),
    owner_id: params.owner ?? undefined,
    [name === "territory-performance" ? "level" : "group_by"]: params.groupBy ?? undefined,
  };
}

function fetchReport<TSchema extends z.ZodType>(
  name: ReportName,
  schema: TSchema,
  params: ReportParams,
  signal?: AbortSignal,
): Promise<z.output<TSchema>> {
  return apiRequest({
    dataId: "RPT-002",
    logger: log,
    fn: "getReport",
    path: `/reports/${name}`,
    query: reportQuery(name, params),
    schema,
    signal,
  });
}

type ReportFetcher<N extends ReportName> = (
  params: ReportParams,
  signal?: AbortSignal,
) => Promise<ReportData<N>>;

const FETCHERS: { readonly [N in ReportName]: ReportFetcher<N> } = {
  "lead-conversion": (params, signal) =>
    fetchReport("lead-conversion", REPORT_SCHEMAS["lead-conversion"], params, signal).then(
      ({ data }) => data,
    ),
  "salesperson-performance": (params, signal) =>
    fetchReport(
      "salesperson-performance",
      REPORT_SCHEMAS["salesperson-performance"],
      params,
      signal,
    ).then(({ data }) => data),
  "lost-leads": (params, signal) =>
    fetchReport("lost-leads", REPORT_SCHEMAS["lost-leads"], params, signal).then(
      ({ data }) => data,
    ),
  "follow-ups": (params, signal) =>
    fetchReport("follow-ups", REPORT_SCHEMAS["follow-ups"], params, signal).then(
      ({ data }) => data,
    ),
  "dealer-performance": (params, signal) =>
    fetchReport("dealer-performance", REPORT_SCHEMAS["dealer-performance"], params, signal).then(
      ({ data }) => data,
    ),
  "campaign-performance": (params, signal) =>
    fetchReport(
      "campaign-performance",
      REPORT_SCHEMAS["campaign-performance"],
      params,
      signal,
    ).then(({ data }) => data),
  "territory-performance": (params, signal) =>
    fetchReport(
      "territory-performance",
      REPORT_SCHEMAS["territory-performance"],
      params,
      signal,
    ).then(({ data }) => data),
  complaints: (params, signal) =>
    fetchReport("complaints", REPORT_SCHEMAS.complaints, params, signal).then(({ data }) => data),
};

/** RPT-002 · GET /reports/{name}: its rows, totals and the filters the figures used. */
export function getReport<N extends ReportName>(
  name: N,
  params: ReportParams,
  signal?: AbortSignal,
): Promise<ReportData<N>> {
  const fetcher: ReportFetcher<N> = FETCHERS[name];
  return fetcher(params, signal);
}

/** RPT-002 · The same report as Excel (`format=xlsx`), with the same filters. */
export function downloadReport(name: ReportName, params: ReportParams): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "RPT-002",
    logger: log,
    fn: "downloadReport",
    path: `/reports/${name}`,
    query: { ...reportQuery(name, params), format: "xlsx" },
  });
}

/** RPT-003 · GET /leads/{id}/360: the lead's tiles and the leads on its mobile. */
export function getLead360(leadId: string, signal?: AbortSignal): Promise<Lead360> {
  return apiRequest({
    dataId: "RPT-003",
    logger: log,
    fn: "getLead360",
    path: `/leads/${leadId}/360`,
    schema: lead360Schema,
    signal,
  });
}
