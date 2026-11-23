"use client";

import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toUserFacingError } from "@/lib/api/error-messages";

const SKELETON_ROWS = 4;

/**
 * DISP-001, ACCT-001 · "Show more" under a work queue's list. A later page that fails keeps the
 * rows already shown and says they are still current.
 */
export function LoadMore({
  query,
  label,
}: {
  query: {
    hasNextPage: boolean;
    isFetchNextPageError: boolean;
    isFetchingNextPage: boolean;
    error: Error | null;
    fetchNextPage: () => Promise<unknown>;
  };
  label: string;
}): React.JSX.Element | null {
  if (!query.hasNextPage) return null;
  return (
    <div className="flex flex-col items-start gap-2">
      {query.isFetchNextPageError ? (
        <p role="alert" className="text-xs text-danger">
          {toUserFacingError(query.error).title}. The {label} above are still current.
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
  );
}

/** DISP-001, ACCT-001 · A work queue's rows while they load. */
export function QueueSkeleton({ label }: { label: string }): React.JSX.Element {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-2">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} className="flex flex-col gap-2 rounded-xl border border-border p-3 sm:p-4">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-3 w-40" />
        </div>
      ))}
    </div>
  );
}
