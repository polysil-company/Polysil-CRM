"use client";

import { ShoppingBasket01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { exportMarketingOrders } from "@/features/marketing/api/marketing.api";
import { marketingOrderListQueryOptions } from "@/features/marketing/api/marketing.queries";
import type { MarketingOrderSummary, OrderView } from "@/features/marketing/api/marketing.schemas";
import {
  MARKETING_STATUS_BADGE,
  MARKETING_STATUS_LABELS,
  ORDER_VIEW_LABELS,
} from "@/features/marketing/lib/marketing-labels";
import { formatCount, formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/marketing/components/marketing-orders.tsx",
  dataId: "MKT-003",
});

const EMPTY_TEXT: Readonly<Record<OrderView, { title: string; description: string }>> = {
  mine: {
    title: "You haven't ordered anything",
    description: "Pick items from the catalogue under Order material.",
  },
  awaiting: {
    title: "Nothing to approve",
    description: "Orders from the offices you look after come here.",
  },
  dispatch: {
    title: "Nothing to send",
    description: "Approved orders wait here until their dispatch is recorded.",
  },
  all: {
    title: "No marketing orders yet",
    description: "Orders placed from the catalogue show here.",
  },
};

/**
 * MKT-003 · Marketing orders, newest first, in the views this person has: theirs, the ones to
 * approve (District Managers), the ones to send (the marketing team), and all. Each opens in a
 * dialog. The view and the open order are in the URL; the list exports to Excel.
 */
export function MarketingOrders({
  views,
  view,
  onView,
  onOpen,
}: {
  views: readonly OrderView[];
  view: OrderView;
  onView: (view: OrderView) => void;
  onOpen: (orderId: string) => void;
}): React.JSX.Element {
  const query = useInfiniteQuery(marketingOrderListQueryOptions({ view }));
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {views.length > 1 ? (
          <ToggleGroup
            aria-label="Which orders"
            value={[view]}
            onValueChange={(next) => {
              const chosen = views.find((value) => value === next[0]);
              if (chosen !== undefined) onView(chosen);
            }}
            className="scrollbar-none overflow-x-auto"
          >
            {views.map((value) => (
              <ToggleGroupItem key={value} value={value}>
                {ORDER_VIEW_LABELS[value]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        ) : (
          <span />
        )}
        <DownloadExcelButton
          download={() => exportMarketingOrders({ view })}
          fallbackName="marketing-orders.xlsx"
          what="marketing orders"
          logger={log}
          dataId="MKT-003"
        />
      </div>

      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading marketing orders" className="flex flex-col gap-2">
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={ShoppingBasket01Icon}
          title={EMPTY_TEXT[view].title}
          description={EMPTY_TEXT[view].description}
          className="rounded-xl border border-dashed border-border"
        />
      ) : (
        <div className="flex flex-col gap-3">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {formatCount(rows.length)}
            {query.hasNextPage ? "+" : ""} {rows.length === 1 ? "order" : "orders"}, newest first.
          </p>
          <ul aria-label="Marketing orders" className="flex flex-col gap-2">
            {rows.map((order) => (
              <OrderRow key={order.id} order={order} onOpen={onOpen} />
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

function OrderRow({
  order,
  onOpen,
}: {
  order: MarketingOrderSummary;
  onOpen: (orderId: string) => void;
}): React.JSX.Element {
  const who = order.partner === null ? "Office use" : (order.partner.name ?? "A dealer");
  return (
    <li>
      <button
        type="button"
        aria-label={`Open ${order.orderNo}, ${who}, ${MARKETING_STATUS_LABELS[order.status]}`}
        className="flex w-full press-scale flex-col gap-2 rounded-xl border border-border bg-card p-3 text-left transition-colors duration-fast ease-out hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring sm:flex-row sm:items-center sm:justify-between sm:p-4"
        onClick={() => {
          onOpen(order.id);
        }}
      >
        <span className="flex min-w-0 flex-col gap-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-foreground">{order.orderNo}</span>
            <Badge variant={MARKETING_STATUS_BADGE[order.status]} size="sm" dot>
              {MARKETING_STATUS_LABELS[order.status]}
            </Badge>
          </span>
          <span className="text-xs text-muted-foreground">
            {who} · {order.office.name ?? "an office"} · {order.requestedBy.name ?? "someone"}{" "}
            <RelativeDate value={order.createdAt} />
          </span>
        </span>
        <span className="flex flex-col gap-0.5 sm:items-end">
          <span className="text-sm font-semibold text-foreground tabular-nums">
            {formatInr(order.totals.value, { paise: true })}
          </span>
          <span className="text-xs text-muted-foreground tabular-nums">
            company {formatInr(order.totals.companyShare, { paise: true })} · dealer{" "}
            {formatInr(order.totals.dealerShare, { paise: true })}
          </span>
        </span>
      </button>
    </li>
  );
}
