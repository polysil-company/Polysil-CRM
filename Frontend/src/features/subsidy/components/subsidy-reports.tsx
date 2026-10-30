"use client";

import { Analytics01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { EmptyState } from "@/components/patterns/empty-state";
import { SingleFilterPill } from "@/components/patterns/filter-pill";
import { QueryView } from "@/components/patterns/query-view";
import { SearchField } from "@/components/patterns/search-field";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { stageDefsQueryOptions } from "@/features/subsidy/api/subsidy-applications.queries";
import {
  APPLICATION_STATUSES,
  type ApplicationStatus,
} from "@/features/subsidy/api/subsidy-applications.schemas";
import {
  exportAgeing,
  exportStageReport,
  exportSupplyReport,
} from "@/features/subsidy/api/subsidy-reports.api";
import {
  ageingQueryOptions,
  stageReportQueryOptions,
  supplyReportQueryOptions,
} from "@/features/subsidy/api/subsidy-reports.queries";
import {
  AGEING_FIGURES,
  type AgeFigure,
  type AgeingFigureKey,
  type AgeRow,
} from "@/features/subsidy/api/subsidy-reports.schemas";
import {
  APPLICATION_STATUS_DESCRIPTIONS,
  APPLICATION_STATUS_LABELS,
  formatBusinessDay,
  formatDays,
} from "@/features/subsidy/lib/application-labels";
import { toUserFacingError } from "@/lib/api/error-messages";
import { EMPTY_VALUE, formatInr, formatNumber, sumRupees } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/subsidy/components/subsidy-reports.tsx",
  dataId: "SUBS-009",
});

const REPORTS = ["stages", "supply", "ageing"] as const;
type Report = (typeof REPORTS)[number];

const REPORT_LABELS: Readonly<Record<Report, string>> = {
  stages: "Stages",
  supply: "Supply",
  ageing: "Ageing",
};

const STATUS_OPTIONS = APPLICATION_STATUSES.map((value) => ({
  value,
  label: APPLICATION_STATUS_LABELS[value],
  description: APPLICATION_STATUS_DESCRIPTIONS[value],
}));

/** What each ageing figure measures, as the client's sheet names the dates. */
const AGEING_LABELS: Readonly<Record<AgeingFigureKey, string>> = {
  today_to_supply: "Supply to full payment",
  inward_to_submission: "Inward to submission",
  wo_to_tpa_received: "WO to TPA received",
  tpa_cleared_to_inspection_sent: "TPA cleared to inspection sent",
  inspection_sent_to_tr: "Inspection sent to TR",
  fp_submitted_to_full_fp: "FP submitted to full payment",
};

/**
 * SUBS-009 … SUBS-011 · The subsidy reports: where applications stand by stage, supplied and
 * not supplied by district, and the client's six ageing figures per application. Each has its
 * filters in the URL and downloads as Excel.
 */
export function SubsidyReports(): React.JSX.Element {
  const [values, setValues] = useQueryStates({
    report: parseAsStringLiteral(REPORTS).withDefault("stages"),
    status: parseAsStringLiteral(APPLICATION_STATUSES),
    stage: parseAsString,
    q: parseAsString.withDefault(""),
  });

  return (
    <Tabs
      value={values.report}
      onValueChange={(report: Report) => {
        // Each report reads the status its own way; a new report starts unfiltered.
        void setValues({
          report: report === "stages" ? null : report,
          status: null,
          stage: null,
          q: null,
        });
      }}
    >
      <TabsList variant="segmented" aria-label="Report">
        {REPORTS.map((report) => (
          <TabsTrigger key={report} value={report} variant="segmented">
            {REPORT_LABELS[report]}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value="stages">
        <StageReport
          status={values.status ?? "open"}
          onStatus={(status) => {
            void setValues({ status: status === "open" ? null : status });
          }}
        />
      </TabsContent>
      <TabsContent value="supply">
        <SupplyReport
          status={values.status}
          onStatus={(status) => {
            void setValues({ status });
          }}
        />
      </TabsContent>
      <TabsContent value="ageing">
        <AgeingReport
          params={{ status: values.status, stage: values.stage, q: values.q.trim() }}
          onChange={(patch) => {
            void setValues(patch);
          }}
        />
      </TabsContent>
    </Tabs>
  );
}

function ReportHeader({
  description,
  children,
}: {
  description: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <p className="max-w-prose text-sm text-muted-foreground">{description}</p>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

function ReportEmpty({
  title,
  description,
}: {
  title: string;
  description: string;
}): React.JSX.Element {
  return (
    <EmptyState
      icon={Analytics01Icon}
      title={title}
      description={description}
      className="rounded-xl border border-dashed border-border"
    />
  );
}

function TableSkeleton({ label }: { label: string }): React.JSX.Element {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-2">
      {Array.from({ length: 6 }, (_, index) => (
        <Skeleton key={index} className="h-9 w-full" />
      ))}
    </div>
  );
}

const cell = "py-2 pl-3 text-right tabular-nums sm:pl-4";
const headCell = "py-2 pl-3 text-right font-medium sm:pl-4";
/** A column a phone leaves out, so the table fits without scrolling sideways. */
const wide = "hidden sm:table-cell";

// ── stages (SUBS-010) ─────────────────────────────────────────────────────────────

function StageReport({
  status,
  onStatus,
}: {
  status: ApplicationStatus;
  onStatus: (status: ApplicationStatus) => void;
}): React.JSX.Element {
  const query = useQuery(stageReportQueryOptions(status));
  return (
    <section aria-label="Applications by stage" className="flex flex-col gap-4">
      <ReportHeader description="Applications and their money in each stage, with how long the oldest has waited there.">
        <SingleFilterPill
          label="Status"
          options={STATUS_OPTIONS}
          selected={status}
          onChange={(next) => {
            onStatus(next ?? "open");
          }}
        />
        <DownloadExcelButton
          download={() => exportStageReport(status)}
          fallbackName="subsidy-stages.xlsx"
          what="the stage report"
          logger={log}
          dataId="SUBS-010"
        />
      </ReportHeader>
      <QueryView
        query={query}
        pending={<TableSkeleton label="Loading the stage report" />}
        isEmpty={(rows) => rows.length === 0}
        empty={
          <ReportEmpty
            title={`No ${APPLICATION_STATUS_LABELS[status].toLowerCase()} applications`}
            description="Only stages holding an application appear."
          />
        }
      >
        {(rows) => (
          <div>
            <table className="w-full text-sm">
              <caption className="sr-only">
                {APPLICATION_STATUS_LABELS[status]} applications by stage
              </caption>
              <thead>
                <tr className="border-b border-border text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-4 text-left font-medium">
                    Stage
                  </th>
                  <th scope="col" className={headCell}>
                    Applications
                  </th>
                  <th scope="col" className={cn(headCell, wide)}>
                    Total cost
                  </th>
                  <th scope="col" className={headCell}>
                    Subsidy
                  </th>
                  <th scope="col" className={cn(headCell, wide)}>
                    Farmer share
                  </th>
                  <th scope="col" className={headCell}>
                    Oldest
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.code} className="border-b border-border last:border-0">
                    <th scope="row" className="py-2 pr-4 text-left font-normal text-foreground">
                      {row.seq}. {row.name}
                    </th>
                    <td className={cell}>{formatNumber(row.count)}</td>
                    <td className={cn(cell, wide)}>{formatInr(row.totalCost)}</td>
                    <td className={cell}>{formatInr(row.subsidy)}</td>
                    <td className={cn(cell, wide)}>{formatInr(row.farmerShare)}</td>
                    <td className={cell}>
                      {row.oldestDays === null ? EMPTY_VALUE : formatDays(row.oldestDays)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-foreground font-semibold text-foreground">
                  <th scope="row" className="py-2 pr-4 text-left">
                    All stages
                  </th>
                  <td className={cell}>
                    {formatNumber(rows.reduce((sum, row) => sum + row.count, 0))}
                  </td>
                  <td className={cn(cell, wide)}>
                    {formatInr(sumRupees(rows.map((row) => row.totalCost)))}
                  </td>
                  <td className={cell}>{formatInr(sumRupees(rows.map((row) => row.subsidy)))}</td>
                  <td className={cn(cell, wide)}>
                    {formatInr(sumRupees(rows.map((row) => row.farmerShare)))}
                  </td>
                  <td className={cell} aria-hidden />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </QueryView>
    </section>
  );
}

// ── supply (SUBS-011) ─────────────────────────────────────────────────────────────

function SupplyReport({
  status,
  onStatus,
}: {
  status: ApplicationStatus | null;
  onStatus: (status: ApplicationStatus | null) => void;
}): React.JSX.Element {
  const query = useQuery(supplyReportQueryOptions(status));
  return (
    <section aria-label="Supply by district" className="flex flex-col gap-4">
      <ReportHeader description="Supplied means the material supply date is recorded (stage 7). Cancelled applications are left out unless chosen.">
        <SingleFilterPill
          label="Status"
          options={STATUS_OPTIONS}
          selected={status}
          onChange={onStatus}
        />
        <DownloadExcelButton
          download={() => exportSupplyReport(status)}
          fallbackName="subsidy-supply.xlsx"
          what="the supply report"
          logger={log}
          dataId="SUBS-011"
        />
      </ReportHeader>
      <QueryView
        query={query}
        pending={<TableSkeleton label="Loading the supply report" />}
        isEmpty={(rows) => rows.length === 0}
        empty={
          <ReportEmpty
            title="No applications to report"
            description="Applications appear here by district once they start."
          />
        }
      >
        {(rows) => (
          <div>
            <table className="w-full text-sm">
              <caption className="sr-only">Supplied and not supplied, by district</caption>
              <thead>
                <tr className="border-b border-border text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-4 text-left font-medium">
                    District
                  </th>
                  <th scope="col" className={headCell}>
                    Supplied
                  </th>
                  <th scope="col" className={headCell}>
                    Not supplied
                  </th>
                  <th scope="col" className={cn(headCell, wide)}>
                    Supplied cost
                  </th>
                  <th scope="col" className={cn(headCell, wide)}>
                    Not supplied cost
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.district} className="border-b border-border last:border-0">
                    <th scope="row" className="py-2 pr-4 text-left font-normal text-foreground">
                      {row.district}
                    </th>
                    <td className={cell}>{formatNumber(row.supplied)}</td>
                    <td className={cn(cell, row.notSupplied > 0 && "text-warning")}>
                      {formatNumber(row.notSupplied)}
                    </td>
                    <td className={cn(cell, wide)}>{formatInr(row.suppliedCost)}</td>
                    <td className={cn(cell, wide)}>{formatInr(row.notSuppliedCost)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-foreground font-semibold text-foreground">
                  <th scope="row" className="py-2 pr-4 text-left">
                    All districts
                  </th>
                  <td className={cell}>
                    {formatNumber(rows.reduce((sum, row) => sum + row.supplied, 0))}
                  </td>
                  <td className={cell}>
                    {formatNumber(rows.reduce((sum, row) => sum + row.notSupplied, 0))}
                  </td>
                  <td className={cn(cell, wide)}>
                    {formatInr(sumRupees(rows.map((row) => row.suppliedCost)))}
                  </td>
                  <td className={cn(cell, wide)}>
                    {formatInr(sumRupees(rows.map((row) => row.notSuppliedCost)))}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </QueryView>
    </section>
  );
}

// ── ageing (SUBS-009) ─────────────────────────────────────────────────────────────

function AgeingReport({
  params,
  onChange,
}: {
  params: { status: ApplicationStatus | null; stage: string | null; q: string };
  onChange: (patch: {
    status?: ApplicationStatus | null;
    stage?: string | null;
    q?: string | null;
  }) => void;
}): React.JSX.Element {
  const query = useInfiniteQuery(ageingQueryOptions(params));
  const stages = useQuery(stageDefsQueryOptions());
  const stageOptions = (stages.data ?? []).map((stage) => ({
    value: stage.code,
    label: `${String(stage.seq)}. ${stage.name}`,
  }));
  const filtered = params.status !== null || params.stage !== null || params.q !== "";

  return (
    <section aria-label="Ageing" className="flex flex-col gap-4">
      <ReportHeader description="How long each step took, in days. A step with no end yet counts to today and says so; a dash means its start isn't recorded.">
        <DownloadExcelButton
          download={() => exportAgeing(params)}
          fallbackName="subsidy-ageing.xlsx"
          what="the ageing report"
          logger={log}
          dataId="SUBS-009"
        />
      </ReportHeader>
      <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
        <SearchField
          label="Search applications"
          placeholder="Number, Reg. No. or farmer"
          value={params.q}
          onSearch={(q) => {
            onChange({ q: q === "" ? null : q });
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          <SingleFilterPill
            label="Status"
            options={STATUS_OPTIONS}
            selected={params.status}
            onChange={(status) => {
              onChange({ status });
            }}
          />
          <SingleFilterPill
            label="Stage"
            options={stageOptions}
            selected={params.stage}
            emptyMessage={stages.isPending ? "Loading stages…" : "The stages couldn't be loaded."}
            onChange={(stage) => {
              onChange({ stage });
            }}
          />
          {filtered ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                onChange({ status: null, stage: null, q: null });
              }}
            >
              Reset filters
            </Button>
          ) : null}
        </div>
      </div>
      <QueryView
        query={query}
        pending={<TableSkeleton label="Loading the ageing report" />}
        isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
        empty={
          <ReportEmpty
            title={filtered ? "No applications match these filters" : "No applications yet"}
            description={
              filtered
                ? "Change or reset the filters to see more."
                : "Ageing starts with the first application."
            }
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <ul aria-label="Ageing by application" className="flex flex-col gap-2">
              {data.pages.flatMap((page) =>
                page.items.map((row) => <AgeingCard key={row.application.id} row={row} />),
              )}
            </ul>
            {query.hasNextPage ? (
              <div className="flex flex-col items-start gap-2">
                {query.isFetchNextPageError ? (
                  <p role="alert" className="text-xs text-danger">
                    {toUserFacingError(query.error).title}. The rows above are still current.
                  </p>
                ) : null}
                <Button
                  variant="outline"
                  size="sm"
                  state={query.isFetchingNextPage ? "loading" : "idle"}
                  loadingLabel="Loading…"
                  onClick={() => {
                    void query.fetchNextPage();
                  }}
                >
                  {query.isFetchNextPageError ? "Try again" : "Show more"}
                </Button>
              </div>
            ) : null}
          </div>
        )}
      </QueryView>
    </section>
  );
}

function figureTitle(figure: AgeFigure): string | undefined {
  if (figure.since === null) return undefined;
  const from = `From ${formatBusinessDay(figure.since)}`;
  return figure.until === null
    ? `${from}, still running`
    : `${from} to ${formatBusinessDay(figure.until)}`;
}

function AgeingCard({ row }: { row: AgeRow }): React.JSX.Element {
  const { application } = row;
  return (
    <li className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 sm:p-4">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <Link
          href={`/subsidy/${application.id}`}
          className="font-mono text-sm font-semibold text-foreground underline-offset-4 hover:underline"
        >
          {application.number}
        </Link>
        <span className="text-sm text-foreground">{application.farmerName}</span>
        <span className="text-xs text-muted-foreground">
          {application.stage}
          {application.district === null ? "" : ` · ${application.district}`}
          {application.regNo === null ? "" : ` · Reg. ${application.regNo}`}
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        {AGEING_FIGURES.map((key) => {
          const figure = row.figures[key];
          return (
            <div
              key={key}
              title={figureTitle(figure)}
              className={cn(
                "flex flex-col gap-0.5 rounded-md border border-border px-2.5 py-2",
                figure.running && "border-warning bg-warning-soft",
              )}
            >
              <dt className="text-xs text-muted-foreground">{AGEING_LABELS[key]}</dt>
              <dd className="text-sm font-medium text-foreground tabular-nums">
                {figure.days === null ? (
                  <>
                    {EMPTY_VALUE}
                    <span className="sr-only"> not started</span>
                  </>
                ) : (
                  <>
                    {formatDays(figure.days)}
                    {figure.running ? (
                      <span className="ml-1 text-xs font-normal text-warning">running</span>
                    ) : null}
                  </>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </li>
  );
}
