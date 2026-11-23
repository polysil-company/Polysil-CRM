"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { LEAD_STAGES, type LeadStage } from "@/features/leads/api/leads.schemas";
import { LeadStageBadge } from "@/features/leads/components/lead-stage-badge";
import { lead360QueryOptions } from "@/features/reports/api/reports.queries";
import type { Lead360 } from "@/features/reports/api/reports.schemas";
import { useCan } from "@/features/session/hooks/use-session";
import { isApiError } from "@/lib/api/errors";
import { formatInr, formatNumber } from "@/lib/format";

function leadStageOf(stage: string): LeadStage | null {
  return LEAD_STAGES.find((item) => item === stage) ?? null;
}

interface Tile {
  readonly label: string;
  /** Null: not available to this user. */
  readonly value: string | null;
  readonly note?: string;
}

function countTile(label: string, value: number | null): Tile {
  return { label, value: value === null ? null : formatNumber(value) };
}

function tilesOf(summary: Lead360["summary"], seesSubsidy: boolean): Tile[] {
  return [
    countTile("Quotations", summary.quotations),
    {
      label: "Orders",
      value: summary.orders === null ? null : formatNumber(summary.orders),
      ...(summary.orderValue === null || summary.orders === 0
        ? {}
        : { note: formatInr(summary.orderValue) }),
    },
    { label: "Received", value: summary.received === null ? null : formatInr(summary.received) },
    countTile("Complaints", summary.complaints),
    countTile("Visits", summary.visits),
    countTile("Open tasks", summary.openTasks),
    {
      label: "Subsidy",
      // Null is also what an allowed user gets when the lead has no application.
      value:
        summary.subsidyStage !== null
          ? `Stage ${formatNumber(summary.subsidyStage)}`
          : seesSubsidy
            ? "None"
            : null,
    },
  ];
}

/**
 * RPT-003 · A lead's 360° view: tiles across the top of the lead, and other leads on the same
 * mobile ("same mobile", never "same customer": farmers share phones). The timeline below is
 * the lead's own. Needs reports, as well as leads; without it, or on a 403, nothing shows.
 */
export function Lead360Card({ leadId }: { leadId: string }): React.JSX.Element | null {
  const seesReports = useCan("reports");
  const seesSubsidy = useCan("subsidy");
  const query = useQuery({ ...lead360QueryOptions(leadId), enabled: seesReports });
  if (!seesReports || (isApiError(query.error) && query.error.status === 403)) return null;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>At a glance</CardTitle>
          <CardDescription>Everything on this lead so far</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {query.status === "pending" ? (
          <Lead360Skeleton />
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
              {tilesOf(query.data.summary, seesSubsidy).map((tile) => (
                <div
                  key={tile.label}
                  className="flex flex-col gap-0.5 rounded-lg border border-border p-3"
                >
                  <dt className="text-xs text-muted-foreground">{tile.label}</dt>
                  <dd className="text-lg font-semibold text-foreground tabular-nums">
                    {tile.value === null ? (
                      <>
                        <span aria-hidden className="text-muted-foreground">
                          —
                        </span>
                        <span className="sr-only">Not available to you</span>
                      </>
                    ) : (
                      tile.value
                    )}
                  </dd>
                  {tile.note === undefined ? null : (
                    <dd className="text-xs text-muted-foreground tabular-nums">{tile.note}</dd>
                  )}
                </div>
              ))}
            </dl>
            <RelatedLeads leads={query.data.relatedLeads} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function RelatedLeads({ leads }: { leads: Lead360["relatedLeads"] }): React.JSX.Element {
  if (leads.length === 0) {
    return <p className="text-sm text-muted-foreground">No other leads on this mobile.</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-sm font-medium text-foreground">
        Same mobile ({formatNumber(leads.length)})
      </h4>
      <ul className="flex flex-col gap-1.5">
        {leads.map((lead) => {
          const stage = leadStageOf(lead.stage);
          return (
            <li key={lead.id} className="flex flex-wrap items-center gap-2 text-sm">
              <Link
                href={`/leads/${lead.id}`}
                className="font-medium text-foreground underline underline-offset-4"
              >
                {lead.inquiryNo}
              </Link>
              {stage === null ? (
                <span className="text-muted-foreground">{lead.stage}</span>
              ) : (
                <LeadStageBadge stage={stage} />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Lead360Skeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the lead at a glance" className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
        {Array.from({ length: 7 }, (_, index) => (
          <Skeleton key={index} className="h-16 w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-5 w-48" />
    </div>
  );
}
