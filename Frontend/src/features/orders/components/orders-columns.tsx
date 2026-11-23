"use client";

import Link from "next/link";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import { createDataTableColumnHelper } from "@/components/patterns/data-table";
import { ProportionBar } from "@/components/patterns/proportion-bar";
import { Badge } from "@/components/ui/badge";
import type { OrderSummary } from "@/features/orders/api/orders.schemas";
import { ORDER_TYPE_LABELS, orderNumber, waitingOnLabel } from "@/features/orders/lib/order-labels";
import { ORDER_COLUMN_META } from "@/features/orders/lib/order-table-layout";
import { formatDate, formatInr, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

import { OrderStatusBadge } from "./order-status-badge";

const columnHelper = createDataTableColumnHelper<OrderSummary>();

function NumberCell({ order }: { order: OrderSummary }): React.JSX.Element {
  return (
    <Link
      href={`/sales-orders/${order.id}`}
      transitionTypes={["nav-forward"]}
      className="group/number flex min-w-0 flex-col gap-0.5 rounded-sm focus-ring-inset"
    >
      <span
        className={cn(
          "truncate font-mono text-sm font-medium text-foreground underline-offset-4 group-hover/number:underline",
          order.orderNo === null && "font-sans text-muted-foreground",
        )}
      >
        {orderNumber(order)}
      </span>
      <span className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
        {order.partner === null ? "Direct sale" : order.partner.name}
        {order.isProvisional ? (
          <Badge variant="warning" size="sm">
            Provisional
          </Badge>
        ) : null}
      </span>
    </Link>
  );
}

function StatusCell({ order }: { order: OrderSummary }): React.JSX.Element {
  const waiting = waitingOnLabel(order.waitingOn);
  return (
    <span className="flex min-w-0 flex-col items-start gap-1">
      <OrderStatusBadge status={order.status} />
      {waiting === null ? null : (
        <span className="truncate text-xs text-muted-foreground">{waiting}</span>
      )}
    </span>
  );
}

/** How much has shipped: the share as text, with a thin bar beside it. */
function DispatchedCell({ order }: { order: OrderSummary }): React.JSX.Element {
  const shipping = ["partially_dispatched", "dispatched", "closed_short"].includes(order.status);
  if (!shipping && order.dispatchedPct === 0) {
    return <span className="text-sm text-muted-foreground">Not yet</span>;
  }
  return (
    <span className="flex min-w-0 flex-col gap-1">
      <span className="text-sm tabular-nums">{formatPercent(order.dispatchedPct)}</span>
      <ProportionBar
        value={order.dispatchedPct}
        max={100}
        tone={order.dispatchedPct === 100 ? "success" : "primary"}
        className="h-1.5 w-20"
      />
    </span>
  );
}

/** Columns in display order. Widths and breakpoints come from ORDER_COLUMN_META. */
export const orderColumns = columnHelper.columns([
  columnHelper.accessor("orderNo", {
    id: "number",
    header: "Order",
    enableSorting: false,
    cell: ({ row }) => <NumberCell order={row.original} />,
    meta: ORDER_COLUMN_META.number,
  }),
  columnHelper.accessor("partyName", {
    id: "party",
    header: "Party",
    enableSorting: false,
    cell: ({ getValue }) => <span className="truncate text-sm text-foreground">{getValue()}</span>,
    meta: ORDER_COLUMN_META.party,
  }),
  columnHelper.accessor("status", {
    header: "Status",
    enableSorting: false,
    cell: ({ row }) => <StatusCell order={row.original} />,
    meta: ORDER_COLUMN_META.status,
  }),
  columnHelper.accessor("dispatchedPct", {
    id: "dispatched",
    header: "Dispatched",
    enableSorting: false,
    cell: ({ row }) => <DispatchedCell order={row.original} />,
    meta: ORDER_COLUMN_META.dispatched,
  }),
  columnHelper.accessor("orderType", {
    header: "Type",
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="text-sm text-muted-foreground">{ORDER_TYPE_LABELS[getValue()]}</span>
    ),
    meta: ORDER_COLUMN_META.orderType,
  }),
  columnHelper.accessor((order) => order.owner?.name ?? null, {
    id: "owner",
    header: "Owner",
    enableSorting: false,
    cell: ({ getValue }) => {
      const name = getValue();
      return name === null ? (
        <span className="text-sm text-muted-foreground">Not visible</span>
      ) : (
        <AvatarLabel name={name} size="xs" />
      );
    },
    meta: ORDER_COLUMN_META.owner,
  }),
  columnHelper.accessor("createdAt", {
    header: "Created",
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="text-sm text-muted-foreground">{formatDate(getValue())}</span>
    ),
    meta: ORDER_COLUMN_META.createdAt,
  }),
  columnHelper.accessor((order) => order.totals.total, {
    id: "total",
    header: "Total",
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="font-medium tabular-nums">{formatInr(getValue())}</span>
    ),
    meta: ORDER_COLUMN_META.total,
  }),
]);
