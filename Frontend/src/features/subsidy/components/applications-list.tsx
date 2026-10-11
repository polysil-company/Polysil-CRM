"use client";

import { LegalDocument01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { EmptyState } from "@/components/patterns/empty-state";
import { SingleFilterPill } from "@/components/patterns/filter-pill";
import { QueryView } from "@/components/patterns/query-view";
import { SearchField } from "@/components/patterns/search-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { exportApplications } from "@/features/subsidy/api/subsidy-applications.api";
import {
  applicationListQueryOptions,
  stageDefsQueryOptions,
} from "@/features/subsidy/api/subsidy-applications.queries";
import {
  APPLICATION_STATUSES,
  type Application,
  type ApplicationListParams,
} from "@/features/subsidy/api/subsidy-applications.schemas";
import {
  APPLICATION_STATUS_BADGE,
  APPLICATION_STATUS_DESCRIPTIONS,
  APPLICATION_STATUS_LABELS,
  daysInStageText,
} from "@/features/subsidy/lib/application-labels";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/subsidy/components/applications-list.tsx",
  dataId: "SUBS-005",
});

const SKELETON_ROWS = 5;

const STATUS_OPTIONS = APPLICATION_STATUSES.map((value) => ({
  value,
  label: APPLICATION_STATUS_LABELS[value],
  description: APPLICATION_STATUS_DESCRIPTIONS[value],
}));

/** SUBS-005 · The worklist's filters, in the URL: status, stage and search. */
function useApplicationListParams(): {
  params: ApplicationListParams;
  activeFilterCount: number;
  setFilters: (patch: Partial<Omit<ApplicationListParams, "leadId">>) => void;
  resetFilters: () => void;
} {
  const [values, setValues] = useQueryStates({
    q: parseAsString.withDefault(""),
    status: parseAsStringLiteral(APPLICATION_STATUSES),
    stage: parseAsString,
  });
  const params: ApplicationListParams = {
    q: values.q.trim(),
    status: values.status,
    stage: values.stage,
    leadId: null,
  };
  return {
    params,
    activeFilterCount:
      (params.q === "" ? 0 : 1) +
      (params.status === null ? 0 : 1) +
      (params.stage === null ? 0 : 1),
    setFilters: (patch) => {
      void setValues({
        ...(patch.q === undefined ? {} : { q: patch.q === "" ? null : patch.q }),
        ...(patch.status === undefined ? {} : { status: patch.status }),
        ...(patch.stage === undefined ? {} : { stage: patch.stage }),
      });
    },
    resetFilters: () => {
      void setValues({ q: null, status: null, stage: null });
    },
  };
}

/**
 * SUBS-005 · Subsidy applications: newest first, each with its farmer, stage and how long it
 * has sat there, the Reg. No. and the subsidy. Filtered by status, stage and a search on the
 * number, Reg. No. or farmer — all in the URL — and downloadable as Excel.
 */
export function ApplicationsList(): React.JSX.Element {
  const { params, activeFilterCount, setFilters, resetFilters } = useApplicationListParams();
  const stages = useQuery(stageDefsQueryOptions());
  const stageOptions = (stages.data ?? []).map((stage) => ({
    value: stage.code,
    label: `${String(stage.seq)}. ${stage.name}`,
  }));

  return (
    <section aria-label="Subsidy applications" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <p className="max-w-prose text-sm text-muted-foreground">
          An application starts from a subsidised lead and follows the scheme&apos;s stages until
          every payment is in.
        </p>
        <DownloadExcelButton
          download={() => exportApplications(params)}
          fallbackName="subsidy-applications.xlsx"
          what="applications"
          logger={log}
          dataId="SUBS-005"
        />
      </div>

      <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
        <SearchField
          label="Search applications"
          placeholder="Number, Reg. No. or farmer"
          value={params.q}
          onSearch={(q) => {
            setFilters({ q });
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          <SingleFilterPill
            label="Status"
            options={STATUS_OPTIONS}
            selected={params.status}
            onChange={(status) => {
              setFilters({ status });
            }}
          />
          <SingleFilterPill
            label="Stage"
            options={stageOptions}
            selected={params.stage}
            emptyMessage={stages.isPending ? "Loading stages…" : "The stages couldn't be loaded."}
            onChange={(stage) => {
              setFilters({ stage });
            }}
          />
          {activeFilterCount > 0 ? (
            <Button variant="ghost" size="sm" onClick={resetFilters}>
              Reset filters
            </Button>
          ) : null}
        </div>
      </div>

      <ApplicationRows params={params} filtered={activeFilterCount > 0} onReset={resetFilters} />
    </section>
  );
}

export interface ApplicationRowsProps {
  params: ApplicationListParams;
  filtered: boolean;
  onReset?: () => void;
  /** What to say when there are none, e.g. on a lead's page. */
  emptyMessage?: string;
}

/** SUBS-005 · The rows for any filters: the worklist, or one lead's application. */
export function ApplicationRows({
  params,
  filtered,
  onReset,
  emptyMessage,
}: ApplicationRowsProps): React.JSX.Element {
  const query = useInfiniteQuery(applicationListQueryOptions(params));

  return (
    <QueryView
      query={query}
      pending={<ApplicationsListSkeleton />}
      isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
      empty={
        emptyMessage === undefined ? (
          <EmptyState
            icon={LegalDocument01Icon}
            title={filtered ? "No applications match these filters" : "No applications yet"}
            description={
              filtered
                ? "Change or reset the filters to see more."
                : "Start one from a subsidised lead: “Start subsidy application” on its page."
            }
            action={
              filtered && onReset !== undefined ? (
                <Button variant="outline" size="sm" onClick={onReset}>
                  Reset filters
                </Button>
              ) : undefined
            }
            className="rounded-xl border border-dashed border-border"
          />
        ) : (
          <p className="text-sm text-muted-foreground">{emptyMessage}</p>
        )
      }
    >
      {(data) => (
        <div className="flex flex-col gap-3">
          <ul aria-label="Subsidy applications" className="flex flex-col gap-2">
            {data.pages.flatMap((page) =>
              page.items.map((application) => (
                <ApplicationRow key={application.id} application={application} />
              )),
            )}
          </ul>
          {query.hasNextPage ? (
            <div className="flex flex-col items-start gap-2">
              {query.isFetchNextPageError ? (
                <p role="alert" className="text-xs text-danger">
                  {toUserFacingError(query.error).title}. The applications above are still current.
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
  );
}

function ApplicationRow({ application }: { application: Application }): React.JSX.Element {
  const open = application.status === "open";
  return (
    <li>
      <Link
        href={`/subsidy/${application.id}`}
        aria-label={`${application.number}, ${application.farmerName}, ${APPLICATION_STATUS_LABELS[application.status]}, ${application.stage.name}`}
        className="flex flex-col gap-1.5 rounded-xl border border-border bg-card p-3 transition-colors duration-fast hover:bg-accent sm:p-4"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold text-foreground">
            {application.number}
          </span>
          <Badge variant={APPLICATION_STATUS_BADGE[application.status]} dot>
            {APPLICATION_STATUS_LABELS[application.status]}
          </Badge>
          {application.regNo === null ? null : (
            <span className="text-xs text-muted-foreground">Reg. {application.regNo}</span>
          )}
          <span className="ml-auto text-sm font-medium text-foreground tabular-nums">
            {formatInr(application.figures.subsidy)}
            <span className="ml-1 text-xs font-normal text-muted-foreground">subsidy</span>
          </span>
        </div>
        <p className="truncate text-sm font-medium text-foreground">{application.farmerName}</p>
        <p className="text-xs text-muted-foreground">
          {application.stage.seq}. {application.stage.name}
          {open ? ` · ${daysInStageText(application.daysInStage)}` : ""} ·{" "}
          {application.territory.name} · {application.lead.inquiryNo}
        </p>
      </Link>
    </li>
  );
}

export function ApplicationsListSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading applications" className="flex flex-col gap-2">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} className="flex flex-col gap-2 rounded-xl border border-border p-3 sm:p-4">
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-56" />
        </div>
      ))}
    </div>
  );
}
