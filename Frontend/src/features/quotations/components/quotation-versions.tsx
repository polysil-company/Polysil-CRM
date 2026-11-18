"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { QueryView } from "@/components/patterns/query-view";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { quotationVersionsQueryOptions } from "@/features/quotations/api/quotations.queries";
import type { Quotation, QuotationSummary } from "@/features/quotations/api/quotations.schemas";
import { formatFullDate, formatInr } from "@/lib/format";
import { cn } from "@/lib/utils";

import { QuotationStatusBadge } from "./quotation-status-badge";

/** Only a revised quotation has versions to list. */
export function hasVersions(quotation: Pick<Quotation, "version" | "supersededBy">): boolean {
  return quotation.version > 1 || quotation.supersededBy !== null;
}

/**
 * QUOT-009 · Every version of the quotation's number, oldest first, the one on screen marked.
 * Shown only once there is more than one.
 */
export function QuotationVersions({
  quotation,
}: {
  quotation: Quotation;
}): React.JSX.Element | null {
  const query = useQuery({
    ...quotationVersionsQueryOptions(quotation.id),
    enabled: hasVersions(quotation),
  });

  if (!hasVersions(quotation)) {
    return null;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle level={3}>Versions</CardTitle>
      </CardHeader>
      <CardContent>
        <QueryView
          query={query}
          pending={<VersionsSkeleton />}
          isEmpty={(versions) => versions.length === 0}
          empty={<p className="text-sm text-muted-foreground">No other versions.</p>}
        >
          {(versions) => (
            <ol aria-label="Versions, oldest first" className="flex flex-col gap-1">
              {versions.map((version) => (
                <VersionRow
                  key={version.id}
                  version={version}
                  current={version.id === quotation.id}
                />
              ))}
            </ol>
          )}
        </QueryView>
      </CardContent>
    </Card>
  );
}

function VersionRow({
  version,
  current,
}: {
  version: QuotationSummary;
  current: boolean;
}): React.JSX.Element {
  const body = (
    <>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="font-medium text-foreground">Version {version.version}</span>
        <span className="text-xs text-muted-foreground">
          {version.sentAt === null ? "Not sent" : `Sent ${formatFullDate(version.sentAt)}`} ·{" "}
          {formatInr(version.totals.total, { paise: true })}
        </span>
      </span>
      <QuotationStatusBadge status={version.status} />
    </>
  );
  const row = "flex items-center justify-between gap-3 rounded-md px-2 py-2 text-sm";
  return (
    <li>
      {current ? (
        <div aria-current="page" className={cn(row, "bg-muted")}>
          {body}
        </div>
      ) : (
        <Link
          href={`/quotations/${version.id}`}
          className={cn(row, "focus-ring-inset transition-colors duration-fast hover:bg-muted")}
        >
          {body}
        </Link>
      )}
    </li>
  );
}

function VersionsSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the versions" className="flex flex-col gap-2">
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}
