"use client";

import { ArrowLeft01Icon, ArrowDown01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import { useState } from "react";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { Notice } from "@/components/patterns/notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/features/session/hooks/use-session";
import {
  applicationDetailQueryOptions,
  stageDefsQueryOptions,
  stageEntriesQueryOptions,
  storedCalculationQueryOptions,
} from "@/features/subsidy/api/subsidy-applications.queries";
import type {
  Application,
  StageDef,
  StageEntry,
} from "@/features/subsidy/api/subsidy-applications.schemas";
import { subsidyConfigQueryOptions } from "@/features/subsidy/api/subsidy.queries";
import { SYSTEM_TYPES } from "@/features/subsidy/api/subsidy.schemas";
import {
  APPLICATION_STATUS_BADGE,
  APPLICATION_STATUS_LABELS,
  daysInStageText,
  formatBusinessDay,
  formatDays,
} from "@/features/subsidy/lib/application-labels";
import { SYSTEM_LABELS } from "@/features/subsidy/lib/subsidy-labels";
import { isApiError } from "@/lib/api/errors";
import { EMPTY_VALUE, formatFullDate, formatIndianPhone, formatInr } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ApplicationActions } from "./application-actions";
import { ApplicationDocuments } from "./application-documents";
import { CalculationFigures } from "./calculator-results";

function systemLabel(code: string): string {
  const system = SYSTEM_TYPES.find((item) => item === code);
  return system === undefined ? code : SYSTEM_LABELS[system];
}

/**
 * SUBS-006 · One application: its number, Reg. No., status and stage; the farmer and the lead;
 * the stored figures for the chosen category; the stage history, oldest first; the document
 * checklist; and the calculation as it was stored. Whoever may change applications records
 * stages and cancels; anyone who sees it downloads the PIMS sheet.
 */
export function ApplicationDetail({ applicationId }: { applicationId: string }): React.JSX.Element {
  const query = useQuery(applicationDetailQueryOptions(applicationId));
  if (query.status === "pending") return <ApplicationDetailSkeleton />;
  if (query.status === "error") {
    if (isApiError(query.error) && query.error.status === 404) notFound();
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  return <ApplicationView application={query.data} />;
}

function Fact({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <div className={cn("flex min-w-0 flex-col gap-0.5", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm text-foreground">{children}</dd>
    </div>
  );
}

function ApplicationView({ application }: { application: Application }): React.JSX.Element {
  // Both hooks always run; the backend lets either change an application.
  const canCreate = useCan("subsidy", "create");
  const canEdit = useCan("subsidy", "edit");
  const canWrite = canCreate || canEdit;
  const open = application.status === "open";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Link
            href="/subsidy"
            transitionTypes={["nav-back"]}
            className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
          >
            <Icon icon={ArrowLeft01Icon} size="sm" />
            All applications
          </Link>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="truncate font-mono text-lg font-semibold text-foreground sm:text-xl">
              {application.number}
            </h2>
            <Badge variant={APPLICATION_STATUS_BADGE[application.status]} dot>
              {APPLICATION_STATUS_LABELS[application.status]}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {application.farmerName} ·{" "}
            <Link
              href={`/leads/${application.lead.id}`}
              className="font-mono text-foreground underline-offset-4 hover:underline"
            >
              {application.lead.inquiryNo}
            </Link>{" "}
            · {systemLabel(application.systemType)} · {application.scheme}
          </p>
        </div>
        <ApplicationActions application={application} canWrite={canWrite} />
      </div>

      {application.status === "cancelled" ? (
        <Notice tone="info">
          <p className="font-medium">Cancelled</p>
          <p>{application.cancellation?.reason ?? "No reason was given."}</p>
          <p className="text-muted-foreground">The lead can start a new application.</p>
        </Notice>
      ) : null}
      {application.status === "full_fp_received" ? (
        <Notice tone="success">
          <p className="font-medium">
            Every payment received
            {application.closedOn === null ? "" : ` on ${formatBusinessDay(application.closedOn)}`}
          </p>
          <p>The application closed by itself and takes no more entries.</p>
        </Notice>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3 lg:items-start">
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-0.5">
                <CardTitle level={3}>
                  {application.stage.seq}. {application.stage.name}
                </CardTitle>
                <CardDescription>
                  Since {formatBusinessDay(application.stage.since)}
                  {open ? ` · ${daysInStageText(application.daysInStage)}` : ""}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-3">
                <Fact label="Reg. No.">{application.regNo ?? "Not yet"}</Fact>
                <Fact label="Since inward">
                  {application.daysSinceInward === null
                    ? EMPTY_VALUE
                    : formatDays(application.daysSinceInward)}
                </Fact>
                <Fact label="Documents">
                  {application.documents.uploaded} of {application.documents.listed} on the
                  checklist
                </Fact>
              </dl>
            </CardContent>
          </Card>

          <StageHistory applicationId={application.id} scheme={application.scheme} />
          <ApplicationDocuments application={application} canWrite={canWrite} />
        </div>

        {/* The figures come first on a phone, before the long checklist. */}
        <div className="order-first flex min-w-0 flex-col gap-4 lg:order-0">
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-0.5">
                <CardTitle level={3}>Figures</CardTitle>
                {/* The scheme's names carry their percentage ("Small Farmer 70 %"). */}
                <CardDescription>{application.category.name}</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-3">
                <div className="flex flex-col gap-0.5 rounded-md bg-muted px-3 py-2">
                  <dt className="text-xs text-muted-foreground">Subsidy</dt>
                  <dd className="text-lg font-semibold text-foreground tabular-nums">
                    {formatInr(application.figures.subsidy, { paise: true })}
                  </dd>
                </div>
                <Fact label="Farmer pays">
                  <span className="tabular-nums">
                    {formatInr(application.figures.farmerShare, { paise: true })}
                  </span>
                </Fact>
                <Fact label="Total cost with GST">
                  <span className="tabular-nums">
                    {formatInr(application.figures.totalCost, { paise: true })}
                  </span>
                </Fact>
                <Fact label="Area">
                  <span className="tabular-nums">{application.totalArea} Ha</span>
                  {application.groupTotalArea === null ? null : (
                    <span className="block text-xs text-muted-foreground tabular-nums">
                      Group of {application.groupTotalArea} Ha
                    </span>
                  )}
                </Fact>
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle level={3}>Farmer</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-3">
                <Fact label="Mobile">{formatIndianPhone(application.mobile)}</Fact>
                <Fact label="Village">{application.village ?? EMPTY_VALUE}</Fact>
                <Fact label="Survey No.">{application.surveyNo ?? EMPTY_VALUE}</Fact>
                <Fact label="Area">{application.territory.name}</Fact>
                <Fact label="Dealer">{application.partner?.name ?? EMPTY_VALUE}</Fact>
                <Fact label="Owner">
                  {application.owner?.name ?? "Unassigned"}
                  <span className="block text-xs text-muted-foreground">
                    {application.office.name}
                  </span>
                </Fact>
                <Fact label="Started">{formatFullDate(application.createdAt)}</Fact>
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>

      <StoredCalculation application={application} />
    </div>
  );
}

// ── the stage history ─────────────────────────────────────────────────────────────

function valueText(defs: readonly StageDef[], key: string, value: string | null): string {
  if (value === null) return "Cleared";
  const field = defs.flatMap((stage) => stage.fields).find((item) => item.key === key);
  if (field?.type === "date") return formatBusinessDay(value);
  if (field?.type === "amount") return formatInr(value, { paise: true });
  return value;
}

function labelOf(defs: readonly StageDef[], key: string): string {
  return defs.flatMap((stage) => stage.fields).find((item) => item.key === key)?.label ?? key;
}

/** SUBS-006 · Every entry, oldest first, with what was entered and why. */
function StageHistory({
  applicationId,
  scheme,
}: {
  applicationId: string;
  scheme: string;
}): React.JSX.Element {
  const entries = useQuery(stageEntriesQueryOptions(applicationId));
  const defs = useQuery(stageDefsQueryOptions(scheme)).data ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Stages</CardTitle>
          <CardDescription>As recorded, oldest first</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {entries.status === "pending" ? (
          <div className="flex flex-col gap-3" aria-hidden>
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : entries.status === "error" ? (
          <ErrorState
            error={entries.error}
            onRetry={() => {
              void entries.refetch();
            }}
          />
        ) : entries.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing recorded yet.</p>
        ) : (
          <ol aria-label="Stage history" className="flex flex-col">
            {entries.data.map((entry, index) => (
              <StageEntryRow
                key={entry.id}
                entry={entry}
                defs={defs}
                previousSeq={entries.data[index - 1]?.stage.seq ?? null}
              />
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function StageEntryRow({
  entry,
  defs,
  previousSeq,
}: {
  entry: StageEntry;
  defs: readonly StageDef[];
  previousSeq: number | null;
}): React.JSX.Element {
  const values = Object.entries(entry.values);
  const back = previousSeq !== null && entry.stage.seq < previousSeq;
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      <span
        aria-hidden
        className="mt-1.5 size-2 shrink-0 rounded-full bg-primary ring-4 ring-primary-soft"
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
          <span className="font-medium text-foreground">
            {entry.stage.seq}. {entry.stage.name}
          </span>
          {back ? <Badge variant="warning">Back</Badge> : null}
          <span className="text-xs text-muted-foreground">
            {formatBusinessDay(entry.occurredOn)}
            {entry.enteredBy === null ? "" : ` · ${entry.enteredBy.name}`}
          </span>
        </p>
        {values.length > 0 ? (
          <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
            {values.map(([key, value]) => (
              <div key={key} className="flex min-w-0 gap-1.5">
                <dt className="text-muted-foreground">{labelOf(defs, key)}</dt>
                <dd
                  className={cn(
                    "min-w-0 wrap-break-word text-foreground tabular-nums",
                    value === null && "text-muted-foreground italic",
                  )}
                >
                  {valueText(defs, key, value)}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
        {entry.remark === null ? null : (
          <p className="text-sm wrap-break-word text-muted-foreground">“{entry.remark}”</p>
        )}
      </div>
    </li>
  );
}

// ── the stored calculation ────────────────────────────────────────────────────────

/** SUBS-006 · The calculation as stored at create, shown on request: it never changes. */
function StoredCalculation({ application }: { application: Application }): React.JSX.Element {
  const [shown, setShown] = useState(false);
  const calculation = useQuery({
    ...storedCalculationQueryOptions(application.id),
    enabled: shown,
  });
  const config = useQuery({ ...subsidyConfigQueryOptions(), enabled: shown });
  const hasHeadUnit =
    config.data?.systems.find((system) => system.systemType === application.systemType)
      ?.hasHeadUnit ?? application.systemType !== "sprinkler";

  return (
    <section aria-labelledby="stored-calculation-title" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <h3 id="stored-calculation-title" className="text-base font-semibold text-foreground">
            The calculation
          </h3>
          <p className="text-sm text-muted-foreground">
            As stored when the application started; never recalculated.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          aria-expanded={shown}
          aria-controls="stored-calculation"
          onClick={() => {
            setShown((value) => !value);
          }}
        >
          <Icon
            icon={ArrowDown01Icon}
            className={cn("transition-transform duration-fast", shown && "rotate-180")}
          />
          {shown ? "Hide it" : "Show it"}
        </Button>
      </div>
      <div id="stored-calculation" hidden={!shown} className="flex flex-col gap-4">
        {!shown ? null : calculation.status === "pending" ? (
          <Skeleton className="h-72 w-full rounded-xl" />
        ) : calculation.status === "error" ? (
          <ErrorState
            error={calculation.error}
            onRetry={() => {
              void calculation.refetch();
            }}
          />
        ) : (
          <CalculationFigures
            result={calculation.data}
            hasHeadUnit={hasHeadUnit}
            parameters={config.data?.parameters ?? {}}
            stored
          />
        )}
      </div>
    </section>
  );
}

export function ApplicationDetailSkeleton(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-5" aria-hidden>
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-7 w-72 max-w-full" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="flex flex-col gap-4 lg:col-span-2">
          <Skeleton className="h-32 w-full rounded-xl" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
        <Skeleton className="h-80 w-full rounded-xl" />
      </div>
    </div>
  );
}
