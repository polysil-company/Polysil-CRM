"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type * as React from "react";

import { Button } from "@/components/ui/button";

import { ErrorState } from "./error-state";

export interface QueryViewProps<TData> {
  query: UseQueryResult<TData>;
  /** First load. Must mirror the success layout (same skeleton rules as everywhere). */
  pending: React.ReactNode;
  /** Decides whether loaded data counts as "nothing to show". */
  isEmpty: (data: TData) => boolean;
  empty: React.ReactNode;
  /** Custom error UI. Defaults to <ErrorState> with a retry button. */
  renderError?: (error: Error, retry: () => void) => React.ReactNode;
  children: (data: TData) => React.ReactNode;
}

/**
 * Forces every data view to handle all four states — pending, error, empty
 * and success — at the type level. If a refetch fails while older data is on
 * screen, the data stays and a notice offers a retry.
 */
export function QueryView<TData>({
  query,
  pending,
  isEmpty,
  empty,
  renderError,
  children,
}: QueryViewProps<TData>): React.JSX.Element {
  const retry = (): void => {
    void query.refetch();
  };

  if (query.status === "pending") {
    return <>{pending}</>;
  }

  if (query.status === "error") {
    if (query.data !== undefined) {
      return (
        <>
          <StaleDataNotice onRetry={retry} />
          {isEmpty(query.data) ? empty : children(query.data)}
        </>
      );
    }
    return (
      <>
        {renderError ? (
          renderError(query.error, retry)
        ) : (
          <ErrorState error={query.error} onRetry={retry} />
        )}
      </>
    );
  }

  return <>{isEmpty(query.data) ? empty : children(query.data)}</>;
}

function StaleDataNotice({ onRetry }: { onRetry: () => void }): React.JSX.Element {
  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 border-b border-border bg-warning-soft px-4 py-2 text-sm text-warning"
    >
      <span>Couldn&apos;t refresh. Showing the last loaded data.</span>
      <Button variant="ghost" size="xs" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
