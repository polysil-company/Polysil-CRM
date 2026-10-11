"use client";

import { Clock01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { TimelineEvent } from "@/features/leads/api/leads.schemas";
import { quotationTimelineQueryOptions } from "@/features/quotations/api/quotations.queries";
import {
  quotationHistoryEntry,
  type QuotationHistoryEntry,
} from "@/features/quotations/lib/quotation-lifecycle";
import { toUserFacingError } from "@/lib/api/error-messages";
import { cn } from "@/lib/utils";

const SKELETON_ROWS = 3;

const DOT_CLASSES: Readonly<Record<QuotationHistoryEntry["tone"], string>> = {
  neutral: "bg-subtle-foreground",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

/**
 * QUOT-010 · The quotation's history, newest first: drafted, edited, sent, opened, the
 * customer's answer, discount approval, revisions. "Show older" loads the next page; a
 * failure there keeps what is shown and offers a retry.
 */
export function QuotationHistory({ quotationId }: { quotationId: string }): React.JSX.Element {
  const query = useInfiniteQuery(quotationTimelineQueryOptions(quotationId));

  return (
    <QueryView
      query={query}
      pending={<QuotationHistorySkeleton />}
      isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
      empty={
        <EmptyState
          icon={Clock01Icon}
          title="No history yet"
          description="Every change to this quotation shows here."
        />
      }
    >
      {(data) => (
        <div className="flex flex-col gap-3">
          <ol aria-label="Quotation history, newest first" className="flex flex-col">
            {data.pages.flatMap((page) =>
              page.items.map((event) => <HistoryItem key={event.id} event={event} />),
            )}
          </ol>
          {query.hasNextPage ? (
            <div className="flex flex-col items-start gap-2 pl-5">
              {query.isFetchNextPageError ? (
                <p role="alert" className="text-xs text-danger">
                  {toUserFacingError(query.error).title}. The history above is still current.
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
                {query.isFetchNextPageError ? "Try again" : "Show older"}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </QueryView>
  );
}

function HistoryItem({ event }: { event: TimelineEvent }): React.JSX.Element {
  const entry = quotationHistoryEntry(event);
  return (
    <li className="group relative flex gap-3 pb-4 last:pb-0">
      <span
        aria-hidden="true"
        className="absolute top-4 bottom-0 left-1 w-px bg-border group-last:hidden"
      />
      <span
        aria-hidden="true"
        className={cn("mt-1.5 size-2 shrink-0 rounded-full", DOT_CLASSES[entry.tone])}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <p className="text-sm text-foreground">
          <span className="font-medium">{entry.title}</span>
          {event.actor?.name == null ? null : (
            <span className="text-muted-foreground"> · {event.actor.name}</span>
          )}
        </p>
        {entry.detail === null ? null : (
          <p className="text-sm wrap-break-word whitespace-pre-line text-muted-foreground">
            {entry.detail}
          </p>
        )}
        <RelativeDate value={event.occurredAt} className="text-xs text-muted-foreground" />
      </div>
    </li>
  );
}

export function QuotationHistorySkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the history" className="flex flex-col gap-4">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} className="flex gap-3">
          <Skeleton className="mt-1.5 size-2 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-20" />
          </div>
        </div>
      ))}
    </div>
  );
}
