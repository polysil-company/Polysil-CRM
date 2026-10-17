"use client";

import { Cancel01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { partnerLedgerQueryOptions } from "@/features/payments/api/payments.queries";
import type { PartnerLedger } from "@/features/payments/api/payments.schemas";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { isApiError } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";

const KIND_LABELS: Readonly<Record<PartnerLedger["rows"][number]["kind"], string>> = {
  order: "Order",
  benefit: "Benefit",
  receipt: "Receipt",
};

/** "₹1,000.00 owed", "₹500.00 in credit" or "Settled": a ledger balance in words, sign aside. */
export function balanceText(balance: string): string {
  const value = Number(balance);
  if (value === 0) return "Settled";
  const amount = formatInr(balance.startsWith("-") ? balance.slice(1) : balance, { paise: true });
  return value > 0 ? `${amount} owed` : `${amount} in credit`;
}

/**
 * ACCT-005 · A dealer's ledger: approved orders as debits, applied benefits and receipts as
 * credits, with a running balance over a date range. Positive: the dealer owes. A 403 hides it.
 */
export function PartnerLedgerCard({
  partnerId,
  title = "Ledger",
}: {
  partnerId: string;
  title?: string;
}): React.JSX.Element | null {
  const [range, setRange] = useState<{ from: string | null; to: string | null }>({
    from: null,
    to: null,
  });
  const query = useQuery(partnerLedgerQueryOptions(partnerId, range.from, range.to));

  if (query.status === "error" && isApiError(query.error) && query.error.status === 403) {
    return null;
  }
  return (
    <Card>
      <CardHeader className="flex-col gap-1">
        <CardTitle level={2}>{title}</CardTitle>
        <CardDescription>
          Approved orders, less scheme and reward benefits, less payments received.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div role="group" aria-label="Between" className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            From
            <Input
              type="date"
              value={range.from ?? ""}
              max={range.to ?? undefined}
              className="h-control-sm w-auto"
              onChange={(event) => {
                setRange({ ...range, from: event.target.value === "" ? null : event.target.value });
              }}
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            to
            <Input
              type="date"
              value={range.to ?? ""}
              min={range.from ?? undefined}
              className="h-control-sm w-auto"
              onChange={(event) => {
                setRange({ ...range, to: event.target.value === "" ? null : event.target.value });
              }}
            />
          </label>
          {range.from !== null || range.to !== null ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setRange({ from: null, to: null });
              }}
            >
              <Icon icon={Cancel01Icon} />
              All dates
            </Button>
          ) : null}
        </div>

        {query.status === "pending" ? (
          <div aria-busy="true" aria-label="Loading the ledger" className="flex flex-col gap-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        ) : (
          <LedgerBody ledger={query.data} />
        )}
      </CardContent>
    </Card>
  );
}

function LedgerBody({ ledger }: { ledger: PartnerLedger }): React.JSX.Element {
  const ranged = ledger.from !== null;
  return (
    <div className="flex flex-col gap-3">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {ranged ? (
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs text-muted-foreground">Brought forward</dt>
            <dd className="text-sm font-medium text-foreground tabular-nums">
              {balanceText(ledger.openingBalance)}
            </dd>
          </div>
        ) : null}
        <div className="flex flex-col gap-0.5">
          <dt className="text-xs text-muted-foreground">Balance</dt>
          <dd className="text-base font-semibold text-foreground tabular-nums">
            {balanceText(ledger.closingBalance)}
          </dd>
        </div>
        {Number(ledger.unallocated) > 0 ? (
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs text-muted-foreground">On account, not on an order</dt>
            <dd className="text-sm font-medium text-foreground tabular-nums">
              {formatInr(ledger.unallocated, { paise: true })}
            </dd>
          </div>
        ) : null}
      </dl>

      {ledger.rows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
          {ranged || ledger.to !== null
            ? "Nothing between these dates."
            : "Nothing yet: an order shows here once it is approved."}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-xl text-sm">
            <caption className="sr-only">
              Ledger entries, oldest first, with the balance after each
            </caption>
            <thead className="bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  Date
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Entry
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Debit
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Credit
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Balance
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {ledger.rows.map((row, index) => (
                <tr key={`${row.on}-${row.ref}-${String(index)}`}>
                  <td className="px-3 py-2 whitespace-nowrap text-muted-foreground">
                    {formatBusinessDay(row.on)}
                  </td>
                  <td className="px-3 py-2">
                    <span className="flex flex-wrap items-center gap-2">
                      <Badge
                        size="sm"
                        variant={
                          row.kind === "order"
                            ? "neutral"
                            : row.kind === "receipt"
                              ? "success"
                              : "info"
                        }
                      >
                        {KIND_LABELS[row.kind]}
                      </Badge>
                      <span className="font-mono text-xs text-foreground">{row.ref}</span>
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.debit === null ? "" : formatInr(row.debit, { paise: true })}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.credit === null ? "" : formatInr(row.credit, { paise: true })}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap tabular-nums">
                    {balanceText(row.balance)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
