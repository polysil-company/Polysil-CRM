"use client";

import { Invoice03Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { quotationListQueryOptions } from "@/features/quotations/api/quotations.queries";
import type {
  QuotationListParams,
  QuotationSummary,
} from "@/features/quotations/api/quotations.schemas";
import { quotationTitle } from "@/features/quotations/lib/quotation-labels";
import { formatDate, formatInr, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import { QuotationStatusBadge } from "./quotation-status-badge";

/** A lead rarely has more; past this the card says so. */
const LEAD_QUOTATION_LIMIT = 25;

function paramsFor(leadId: string): QuotationListParams {
  return {
    cursor: null,
    pageSize: LEAD_QUOTATION_LIMIT,
    q: "",
    status: [],
    salesType: null,
    // Every version: an older one shows muted, "superseded by v2".
    currentOnly: false,
    leadId,
  };
}

/**
 * QUOT-001 · The lead's quotations, newest first — every version, older ones muted — including
 * those on leads merged into it. TODO(QUOT-004): "New quotation" arrives with the builder.
 */
export function LeadQuotations({ leadId }: { leadId: string }): React.JSX.Element {
  const query = useQuery(quotationListQueryOptions(paramsFor(leadId)));

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Quotations</CardTitle>
          <CardDescription>Every version, newest first</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <QueryView
          query={query}
          pending={<LeadQuotationsSkeleton />}
          isEmpty={(data) => data.items.length === 0}
          empty={
            <EmptyState
              icon={Invoice03Icon}
              title="No quotations yet"
              description="Quotations made for this lead will show here, with their status and total."
            />
          }
        >
          {(data) => (
            <div className="flex flex-col gap-2">
              <ul
                aria-label="Quotations on this lead"
                className="flex flex-col divide-y divide-border"
              >
                {data.items.map((quotation) => (
                  <LeadQuotationRow key={quotation.id} quotation={quotation} />
                ))}
              </ul>
              {data.nextCursor === null ? null : (
                <p className="text-xs text-muted-foreground">
                  Showing the latest {formatNumber(data.items.length)}.
                </p>
              )}
            </div>
          )}
        </QueryView>
      </CardContent>
    </Card>
  );
}

function LeadQuotationRow({ quotation }: { quotation: QuotationSummary }): React.JSX.Element {
  const superseded = quotation.supersededBy !== null;
  return (
    <li
      className={cn("flex items-center justify-between gap-3 py-2.5", superseded && "opacity-70")}
    >
      <div className="flex min-w-0 flex-col gap-0.5">
        <Link
          href={`/quotations/${quotation.id}`}
          transitionTypes={["nav-forward"]}
          className="truncate rounded-sm font-mono text-sm font-medium text-foreground underline-offset-4 focus-ring-inset hover:underline"
        >
          {quotationTitle(quotation)}
        </Link>
        <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          {quotation.sentAt === null ? "Not sent" : `Sent ${formatDate(quotation.sentAt)}`}
          {superseded ? (
            <Badge variant="outline" size="sm">
              Superseded by v{quotation.supersededBy?.version}
            </Badge>
          ) : null}
        </span>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <QuotationStatusBadge status={quotation.status} />
        <span className="text-sm font-medium tabular-nums">
          {formatInr(quotation.totals.total)}
        </span>
      </div>
    </li>
  );
}

/** Mirrors the rows: number and date, status and total. */
export function LeadQuotationsSkeleton(): React.JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading quotations"
      className="flex flex-col divide-y divide-border"
    >
      {[0, 1].map((row) => (
        <div key={row} className="flex items-center justify-between gap-3 py-2.5">
          <div className="flex flex-col gap-1">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-3.5 w-24" />
          </div>
          <div className="flex flex-col items-end gap-1">
            <Skeleton className="h-6 w-20 rounded-full" />
            <Skeleton className="h-5 w-16" />
          </div>
        </div>
      ))}
    </div>
  );
}
