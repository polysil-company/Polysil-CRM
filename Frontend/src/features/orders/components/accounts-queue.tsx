"use client";

import { CheckmarkBadge01Icon, RupeeIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { buttonVariants } from "@/components/ui/button-variants";
import { Icon } from "@/components/ui/icon";
import { exportOrders } from "@/features/orders/api/orders.api";
import { ACCOUNTS_QUEUE, accountsQueueQueryOptions } from "@/features/orders/api/orders.queries";
import type { OrderSummary } from "@/features/orders/api/orders.schemas";
import { ORDER_TYPE_LABELS } from "@/features/orders/lib/order-labels";
import { useCanApprove } from "@/features/session/hooks/use-session";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { OrderStatusBadge } from "./order-status-badge";
import { LoadMore, QueueSkeleton } from "./queue-parts";

const log = createLogger({
  file: "features/orders/components/accounts-queue.tsx",
  dataId: "ACCT-001",
});

/**
 * ACCT-001 · Accounts' working screen (BE-022): every submitted order whose next approval step
 * is Accounts' payment check, with its party, dealer, value and when it was submitted. Accounts
 * decides each in Approvals; the list can be saved as Excel. Recording payments comes with the
 * payments screens (plan item 26).
 */
export function AccountsQueue(): React.JSX.Element {
  const query = useInfiniteQuery(accountsQueueQueryOptions());
  const total = query.data?.pages[0]?.total ?? null;

  return (
    <section aria-label="Accounts queue" className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p aria-live="polite" className="text-sm text-muted-foreground">
          {total === null
            ? "Submitted orders waiting on Accounts' payment check."
            : total === 0
              ? "Nothing waits on Accounts."
              : `${String(total)} ${total === 1 ? "order waits" : "orders wait"} on Accounts' payment check.`}
        </p>
        <DownloadExcelButton
          download={() => exportOrders(ACCOUNTS_QUEUE)}
          fallbackName="accounts-queue.xlsx"
          what="orders"
          logger={log}
          dataId="ACCT-001"
        />
      </div>
      <QueryView
        query={query}
        pending={<QueueSkeleton label="Loading the Accounts queue" />}
        isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
        empty={
          <EmptyState
            icon={RupeeIcon}
            title="Nothing waits on Accounts"
            description="A submitted order appears here once its managers have approved it and the payment check is next."
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <ul aria-label="Orders waiting on Accounts" className="flex flex-col gap-2">
              {data.pages.flatMap((page) =>
                page.items.map((order) => <AccountsRow key={order.id} order={order} />),
              )}
            </ul>
            <LoadMore query={query} label="orders" />
          </div>
        )}
      </QueryView>
    </section>
  );
}

function AccountsRow({ order }: { order: OrderSummary }): React.JSX.Element {
  const canApprove = useCanApprove();
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
        <p className="truncate text-sm font-medium text-foreground">
          {order.partyName}
          {order.partner === null ? null : (
            <span className="font-normal text-muted-foreground"> · {order.partner.name}</span>
          )}
        </p>
        <p className="text-xs text-muted-foreground">
          {ORDER_TYPE_LABELS[order.orderType]}
          {order.owner === null ? null : <> · {order.owner.name}</>}
          {order.submittedAt === null ? null : (
            <>
              {" "}
              · submitted <RelativeDate value={order.submittedAt} />
            </>
          )}
        </p>
      </div>
      <p className="text-sm font-semibold text-foreground tabular-nums sm:w-36 sm:text-right">
        {formatInr(order.totals.total, { paise: true })}
      </p>
      {canApprove ? (
        <Link
          href="/approvals"
          aria-label={`Decide ${title} for ${order.partyName} in Approvals`}
          className={buttonVariants({
            size: "sm",
            variant: "outline",
            className: "self-start sm:self-center",
          })}
        >
          <Icon icon={CheckmarkBadge01Icon} />
          Decide in Approvals
        </Link>
      ) : null}
    </li>
  );
}
