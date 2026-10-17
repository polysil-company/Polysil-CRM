"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Skeleton } from "@/components/ui/skeleton";
import {
  orderDetailQueryOptions,
  orderListQueryOptions,
} from "@/features/orders/api/orders.queries";
import { DEFAULT_ORDER_PAGE_SIZE, type OrderStatus } from "@/features/orders/api/orders.schemas";
import { rupeesProblem } from "@/features/payments/lib/payment-labels";
import { formatInr } from "@/lib/format";

/** Orders that can take a payment: everything after submit, short of cancelled. */
const PAYABLE_STATUSES: readonly OrderStatus[] = [
  "submitted",
  "approved",
  "partially_dispatched",
  "dispatched",
  "closed_short",
];

/** At most this many of a dealer's orders are offered, each with its balance read. */
const MAX_ROWS = 10;

export type Allocations = Readonly<Record<string, string>>;

/**
 * ACCT-002, ACCT-003 · A dealer's payable orders, newest first, each with its balance and an
 * amount to put on it. The parent owns the amounts and works out what is left.
 */
export function AllocationEditor({
  partnerId,
  value,
  onChange,
  problems,
}: {
  partnerId: string;
  value: Allocations;
  onChange: (next: Allocations) => void;
  problems: Readonly<Record<string, string>>;
}): React.JSX.Element {
  const list = useQuery(
    orderListQueryOptions({
      cursor: null,
      pageSize: DEFAULT_ORDER_PAGE_SIZE,
      q: "",
      status: PAYABLE_STATUSES,
      orderType: null,
      mine: false,
      leadId: null,
      quotationId: null,
      areas: [],
      officeId: null,
      partnerId,
    }),
  );
  const rows = (list.data?.items ?? []).slice(0, MAX_ROWS);
  const details = useQueries({
    queries: rows.map((row) => orderDetailQueryOptions(row.id)),
  });

  if (list.status === "pending") {
    return (
      <div
        aria-busy="true"
        aria-label="Loading the dealer's orders"
        className="flex flex-col gap-2"
      >
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }
  if (list.status === "error") {
    return (
      <p role="alert" className="text-sm text-danger">
        The dealer&apos;s orders couldn&apos;t be loaded. Close and try again.
      </p>
    );
  }
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No orders to pay: the whole amount stays on the dealer&apos;s account.
      </p>
    );
  }
  return (
    <ul aria-label="Put it on these orders" className="flex flex-col divide-y divide-border">
      {rows.map((row, index) => {
        const balance = details[index]?.data?.payments?.balance ?? null;
        const id = `allocation-${row.id}`;
        const problem =
          problems[row.id] ??
          (value[row.id] === undefined ? null : rupeesProblem(value[row.id] ?? "", false));
        return (
          <li
            key={row.id}
            className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center sm:justify-between"
          >
            <label htmlFor={id} className="flex min-w-0 flex-col gap-0.5">
              <span className="font-mono text-sm text-foreground">{row.orderNo ?? "Order"}</span>
              <span className="text-xs text-muted-foreground tabular-nums">
                Total {formatInr(row.totals.total, { paise: true })}
                {balance === null ? "" : ` · balance ${formatInr(balance, { paise: true })}`}
              </span>
            </label>
            <div className="flex flex-col gap-1 sm:w-44">
              <InputGroup>
                <InputGroupAddon>₹</InputGroupAddon>
                <InputGroupInput
                  id={id}
                  inputMode="decimal"
                  autoComplete="off"
                  className="tabular-nums"
                  placeholder={balance !== null && Number(balance) > 0 ? balance : "0"}
                  value={value[row.id] ?? ""}
                  aria-invalid={problem === null ? undefined : true}
                  aria-describedby={problem === null ? undefined : `${id}-error`}
                  onChange={(event) => {
                    onChange({ ...value, [row.id]: event.target.value });
                  }}
                />
              </InputGroup>
              {problem === null ? null : (
                <span id={`${id}-error`} className="text-xs text-danger">
                  {problem}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
