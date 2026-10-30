"use client";

import { ArrowLeft01Icon, ArrowRight01Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { formatCount } from "@/lib/format";

/**
 * "51–100 of 134" with Previous and Next, for the product master's offset-paged lists. Both
 * buttons wait while a page change is landing, so a second click never reads the wrong page.
 */
export function Pager({
  page,
  limit,
  total,
  noun,
  isPaging,
  onPage,
}: {
  page: number;
  limit: number;
  total: number;
  noun: string;
  isPaging: boolean;
  onPage: (page: number) => void;
}): React.JSX.Element | null {
  const pages = Math.max(1, Math.ceil(total / limit));
  if (pages === 1 && page === 1) return null;
  const first = Math.min(total, (page - 1) * limit + 1);
  const last = Math.min(total, page * limit);
  return (
    <nav aria-label={`Pages of ${noun}`} className="flex items-center justify-between gap-3">
      <p aria-live="polite" className="text-sm text-muted-foreground tabular-nums">
        {total === 0 || first > total
          ? `Past the end: ${formatCount(total)} ${noun} in all.`
          : `${formatCount(first)}–${formatCount(last)} of ${formatCount(total)}`}
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={isPaging || page <= 1}
          aria-label="Previous page"
          onClick={() => {
            onPage(Math.min(page - 1, pages));
          }}
        >
          <Icon icon={ArrowLeft01Icon} />
          <span className="hidden sm:inline">Previous</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={isPaging || page >= pages}
          aria-label="Next page"
          onClick={() => {
            onPage(page + 1);
          }}
        >
          <span className="hidden sm:inline">Next</span>
          <Icon icon={ArrowRight01Icon} />
        </Button>
      </div>
    </nav>
  );
}
