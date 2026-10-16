"use client";

import { DeliveryTruck01Icon, PackageIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { createParser, parseAsStringLiteral, useQueryStates } from "nuqs";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ProportionBar } from "@/components/patterns/proportion-bar";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  dispatchListQueryOptions,
  ordersToShipQueryOptions,
} from "@/features/orders/api/orders.queries";
import type { Dispatch, OrderSummary } from "@/features/orders/api/orders.schemas";
import { ORDER_TYPE_LABELS } from "@/features/orders/lib/order-labels";
import { useCan } from "@/features/session/hooks/use-session";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatDate, formatDateTime, formatInr } from "@/lib/format";

import { OrderStatusBadge } from "./order-status-badge";

const SKELETON_ROWS = 4;
const TABS = ["to-ship", "dispatched"] as const;
const DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

const parseAsDay = createParser({
  parse: (value: string) => (DAY_PATTERN.test(value) ? value : null),
  serialize: (value: string) => value,
});

/**
 * DISP-001 · Dispatch's working screen. "To ship" lists every approved order still waiting
 * to leave, partly sent ones with how much has gone; "Record a dispatch" opens the order with
 * the form already open. "Dispatched" is the log of what left, newest first, voided ones
 * marked, between two days if asked. The tab and the days are in the URL.
 */
export function DispatchQueue(): React.JSX.Element {
  const [state, setState] = useQueryStates({
    tab: parseAsStringLiteral(TABS).withDefault("to-ship"),
    from: parseAsDay,
    to: parseAsDay,
  });

  return (
    <section aria-label="Dispatch queue" className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <ToggleGroup
          aria-label="Which orders"
          value={[state.tab]}
          onValueChange={(next) => {
            const [choice] = next;
            if (choice === "to-ship" || choice === "dispatched") {
              void setState({ tab: choice === "to-ship" ? null : choice });
            }
          }}
        >
          <ToggleGroupItem value="to-ship">To ship</ToggleGroupItem>
          <ToggleGroupItem value="dispatched">Dispatched</ToggleGroupItem>
        </ToggleGroup>
        {state.tab === "dispatched" ? (
          <DayRange
            from={state.from}
            to={state.to}
            onChange={(range) => {
              void setState(range);
            }}
          />
        ) : null}
      </div>
      {state.tab === "to-ship" ? <ToShip /> : <Dispatched from={state.from} to={state.to} />}
    </section>
  );
}

function DayRange({
  from,
  to,
  onChange,
}: {
  from: string | null;
  to: string | null;
  onChange: (range: { from?: string | null; to?: string | null }) => void;
}): React.JSX.Element {
  return (
    <div role="group" aria-label="Sent between" className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        From
        <Input
          type="date"
          value={from ?? ""}
          max={to ?? undefined}
          className="h-control-sm w-auto"
          onChange={(event) => {
            onChange({ from: event.target.value === "" ? null : event.target.value });
          }}
        />
      </label>
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        to
        <Input
          type="date"
          value={to ?? ""}
          min={from ?? undefined}
          className="h-control-sm w-auto"
          onChange={(event) => {
            onChange({ to: event.target.value === "" ? null : event.target.value });
          }}
        />
      </label>
      {from !== null || to !== null ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            onChange({ from: null, to: null });
          }}
        >
          Any day
        </Button>
      ) : null}
    </div>
  );
}

function ToShip(): React.JSX.Element {
  const query = useInfiniteQuery(ordersToShipQueryOptions());
  const total = query.data?.pages[0]?.total ?? null;

  return (
    <QueryView
      query={query}
      pending={<QueueSkeleton label="Loading orders to ship" />}
      isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
      empty={
        <EmptyState
          icon={PackageIcon}
          title="Nothing waiting to ship"
          description="Approved orders appear here until everything on them has left."
          className="rounded-xl border border-dashed border-border"
        />
      }
    >
      {(data) => (
        <div className="flex flex-col gap-3">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {total === null
              ? "Approved orders still to ship."
              : `${String(total)} ${total === 1 ? "order" : "orders"} still to ship.`}
          </p>
          <ul aria-label="Orders to ship" className="flex flex-col gap-2">
            {data.pages.flatMap((page) =>
              page.items.map((order) => <ToShipRow key={order.id} order={order} />),
            )}
          </ul>
          <LoadMore query={query} label="orders" />
        </div>
      )}
    </QueryView>
  );
}

function ToShipRow({ order }: { order: OrderSummary }): React.JSX.Element {
  const canRecord = useCan("dispatch", "create");
  const title = order.orderNo ?? "Order";

  return (
    <li
      aria-label={`${title}, ${order.partyName}`}
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 sm:flex-row sm:items-center sm:gap-4 sm:p-4"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`/sales-orders/${order.id}`}
            className="font-mono text-sm font-semibold text-foreground underline-offset-2 hover:underline"
          >
            {title}
          </Link>
          <OrderStatusBadge status={order.status} />
        </div>
        <p className="truncate text-sm font-medium text-foreground">{order.partyName}</p>
        <p className="text-xs text-muted-foreground">
          {ORDER_TYPE_LABELS[order.orderType]} · {formatInr(order.totals.total, { paise: true })}
          {order.submittedAt === null ? null : (
            <>
              {" "}
              · submitted <RelativeDate value={order.submittedAt} />
            </>
          )}
        </p>
      </div>
      <div className="flex w-full items-center gap-2 sm:w-44">
        <ProportionBar value={order.dispatchedPct} max={100} className="flex-1" />
        <span className="w-16 text-right text-xs text-muted-foreground tabular-nums">
          {order.dispatchedPct}% sent
        </span>
      </div>
      {canRecord ? (
        <Link
          href={`/sales-orders/${order.id}?record=dispatch`}
          aria-label={`Record a dispatch on ${title} for ${order.partyName}`}
          className={buttonVariants({ size: "sm", className: "self-start sm:self-center" })}
        >
          <Icon icon={DeliveryTruck01Icon} />
          Record a dispatch
        </Link>
      ) : null}
    </li>
  );
}

function Dispatched({ from, to }: { from: string | null; to: string | null }): React.JSX.Element {
  const query = useInfiniteQuery(dispatchListQueryOptions({ from, to }));
  const ranged = from !== null || to !== null;

  return (
    <QueryView
      query={query}
      pending={<QueueSkeleton label="Loading dispatches" />}
      isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
      empty={
        <EmptyState
          icon={DeliveryTruck01Icon}
          title={ranged ? "Nothing sent on these days" : "Nothing dispatched yet"}
          description={
            ranged
              ? "Choose other days, or any day."
              : "Each dispatch recorded on an order appears here."
          }
          className="rounded-xl border border-dashed border-border"
        />
      }
    >
      {(data) => (
        <div className="flex flex-col gap-3">
          <ol aria-label="Dispatches, newest first" className="flex flex-col gap-2">
            {data.pages.flatMap((page) =>
              page.items.map((dispatch) => <DispatchRow key={dispatch.id} dispatch={dispatch} />),
            )}
          </ol>
          <LoadMore query={query} label="dispatches" />
        </div>
      )}
    </QueryView>
  );
}

function DispatchRow({ dispatch }: { dispatch: Dispatch }): React.JSX.Element {
  const voided = dispatch.voidedAt !== null;
  const papers = [
    dispatch.dcNo === null
      ? null
      : `DC ${dispatch.dcNo}${dispatch.dcDate === null ? "" : `, ${formatDate(dispatch.dcDate)}`}`,
    dispatch.invoiceNo === null
      ? null
      : `Invoice ${dispatch.invoiceNo}${dispatch.invoiceDate === null ? "" : `, ${formatDate(dispatch.invoiceDate)}`}`,
    [dispatch.transporter, dispatch.vehicleNo].filter(Boolean).join(" · ") || null,
  ].filter((part): part is string => part !== null);

  return (
    <li
      aria-label={`${dispatch.dispatchNo}${voided ? ", voided" : ""}`}
      className="flex flex-col gap-1.5 rounded-xl border border-border bg-card p-3 sm:p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-semibold text-foreground">
          {dispatch.dispatchNo}
        </span>
        {voided ? <Badge variant="outline">Voided</Badge> : null}
        <span className="ml-auto text-xs text-muted-foreground">
          <time dateTime={dispatch.dispatchedAt}>{formatDateTime(dispatch.dispatchedAt)}</time>
        </span>
      </div>
      <p className="text-sm text-foreground">
        <Link
          href={`/sales-orders/${dispatch.order.id}`}
          className="font-medium underline-offset-2 hover:underline"
        >
          {dispatch.order.orderNo ?? "Order"}
        </Link>{" "}
        · {dispatch.order.partyName} · {dispatch.lines.length}{" "}
        {dispatch.lines.length === 1 ? "item" : "items"}
      </p>
      {papers.length === 0 ? null : (
        <p className="text-xs text-muted-foreground">{papers.join(" · ")}</p>
      )}
      {voided && dispatch.voidRemark !== null ? (
        <p className="text-sm text-pretty text-muted-foreground">
          <span className="sr-only">Why it was voided: </span>
          {dispatch.voidRemark}
        </p>
      ) : null}
      {dispatch.dispatchedBy === null ? null : (
        <p className="text-xs text-subtle-foreground">Recorded by {dispatch.dispatchedBy.name}</p>
      )}
    </li>
  );
}

function LoadMore({
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

export function DispatchQueueSkeleton(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-5">
      <Skeleton className="h-control-sm w-52 rounded-md" />
      <QueueSkeleton label="Loading the dispatch queue" />
    </div>
  );
}

function QueueSkeleton({ label }: { label: string }): React.JSX.Element {
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
