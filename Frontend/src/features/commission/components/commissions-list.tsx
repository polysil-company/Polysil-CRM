"use client";

import { RupeeIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { exportCommissions } from "@/features/commission/api/commission.api";
import { commissionListQueryOptions } from "@/features/commission/api/commission.queries";
import type { Commission, CommissionStatus } from "@/features/commission/api/commission.schemas";
import { formatPct } from "@/features/commission/lib/commission-labels";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { formatCount, formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { CommissionActions } from "./commission-decisions";
import { CommissionStatusBadge } from "./commission-parts";

const log = createLogger({
  file: "features/commission/components/commissions-list.tsx",
  dataId: "SUBS-017",
});

const VIEWS = ["to-approve", "to-pay", "returned", "paid", "all"] as const;
type View = (typeof VIEWS)[number];

const VIEW_STATUS: Readonly<Record<View, CommissionStatus | null>> = {
  "to-approve": "calculated",
  "to-pay": "approved",
  returned: "returned",
  paid: "paid",
  all: null,
};

const VIEW_LABELS: Readonly<Record<View, string>> = {
  "to-approve": "To approve",
  "to-pay": "To pay",
  returned: "Returned",
  paid: "Paid",
  all: "All",
};

const EMPTY_COPY: Readonly<Record<View, { title: string; description: string }>> = {
  "to-approve": {
    title: "Nothing to approve",
    description: "Commissions the co-ordinators record after full FP wait here for Accounts.",
  },
  "to-pay": {
    title: "Nothing to pay",
    description: "Approved commissions wait here until their payment is recorded.",
  },
  returned: {
    title: "Nothing returned",
    description: "A returned commission waits for its co-ordinator to record it again.",
  },
  paid: { title: "Nothing paid yet", description: "Paid commissions are listed here." },
  all: {
    title: "No commissions yet",
    description: "Each one is recorded on its subsidy application at stage 18.",
  },
};

/**
 * SUBS-017 · Dealer commissions for Accounts: approve or return what co-ordinators recorded,
 * then record each payment; the Excel holds the same rows. Newest first.
 */
export function CommissionsList(): React.JSX.Element {
  const [view, setView] = useQueryState(
    "view",
    parseAsStringLiteral(VIEWS).withDefault("to-approve"),
  );
  const params = { status: VIEW_STATUS[view] };
  const query = useInfiniteQuery(commissionListQueryOptions(params));
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <ToggleGroup
          aria-label="Which commissions"
          className="scrollbar-none overflow-x-auto"
          value={[view]}
          onValueChange={(next) => {
            const chosen = VIEWS.find((value) => value === next[0]);
            if (chosen !== undefined) void setView(chosen === "to-approve" ? null : chosen);
          }}
        >
          {VIEWS.map((value) => (
            <ToggleGroupItem key={value} value={value}>
              {VIEW_LABELS[value]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <DownloadExcelButton
          download={() => exportCommissions(params)}
          fallbackName="dealer-commissions.xlsx"
          what="commissions"
          logger={log}
          dataId="SUBS-017"
        />
      </div>

      {query.status === "pending" ? (
        <ListSkeleton />
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={RupeeIcon}
          title={EMPTY_COPY[view].title}
          description={EMPTY_COPY[view].description}
          className="rounded-xl border border-dashed border-border"
        />
      ) : (
        <div className="flex flex-col gap-3">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {formatCount(rows.length)}
            {query.hasNextPage ? "+" : ""} {rows.length === 1 ? "commission" : "commissions"},
            newest first.
          </p>
          <ul aria-label="Dealer commissions" className="flex flex-col gap-2">
            {rows.map((commission) => (
              <CommissionRow key={commission.id} commission={commission} />
            ))}
          </ul>
          {query.hasNextPage ? (
            <Button
              variant="outline"
              className="self-center"
              disabled={query.isFetchingNextPage}
              onClick={() => {
                void query.fetchNextPage();
              }}
            >
              {query.isFetchingNextPage ? "Loading…" : "Show more"}
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}

function CommissionRow({ commission }: { commission: Commission }): React.JSX.Element {
  return (
    <li className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 sm:p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="flex flex-wrap items-center gap-2">
            <Link
              href={`/subsidy/${commission.application.id}`}
              className="font-mono text-sm font-semibold text-foreground underline-offset-4 hover:underline"
            >
              {commission.application.number}
            </Link>
            <CommissionStatusBadge status={commission.status} />
          </span>
          <span className="text-sm text-foreground">{commission.partner.name ?? "The dealer"}</span>
          <span className="text-xs text-muted-foreground">
            Recorded by {commission.recordedBy.name ?? "someone"}{" "}
            <RelativeDate value={commission.recordedAt} />
            {commission.paidOn === null
              ? ""
              : ` · paid ${formatBusinessDay(commission.paidOn)}${commission.paymentReference === null ? "" : `, ${commission.paymentReference}`}`}
          </span>
        </div>
        <div className="flex flex-col gap-0.5 sm:items-end">
          <span className="text-base font-semibold text-foreground tabular-nums">
            {formatInr(commission.total, { paise: true })}
          </span>
          <span className="text-xs text-muted-foreground tabular-nums">
            {formatInr(commission.commissionAmount, { paise: true })} at{" "}
            {formatPct(commission.commissionPct)} · TOD{" "}
            {formatInr(commission.todAmount, { paise: true })} at {formatPct(commission.todPct)}
          </span>
        </div>
      </div>
      {commission.status === "returned" && commission.decisionRemark !== null ? (
        <p className="rounded-md bg-warning-soft p-2 text-sm text-foreground">
          Returned: {commission.decisionRemark}
        </p>
      ) : null}
      <CommissionActions commission={commission} size="sm" />
    </li>
  );
}

function ListSkeleton(): React.JSX.Element {
  return (
    <div aria-busy="true" aria-label="Loading commissions" className="flex flex-col gap-2">
      {[0, 1, 2].map((row) => (
        <Skeleton key={row} className="h-24 w-full rounded-xl" />
      ))}
    </div>
  );
}
