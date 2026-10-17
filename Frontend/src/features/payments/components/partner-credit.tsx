"use client";

import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { partnerCreditQueryOptions } from "@/features/payments/api/payments.queries";
import { isApiError } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";

/** Rupees with the sign dropped: the words around it say which way it goes. */
function unsigned(amount: string): string {
  return formatInr(amount.startsWith("-") ? amount.slice(1) : amount, { paise: true });
}

/**
 * ACCT-005 · Where a dealer stands against its credit limit: what it owes on open orders less
 * what it has paid, and what is left. Staff only; a 403 (partners, field officers) hides it.
 */
export function PartnerCreditCard({ partnerId }: { partnerId: string }): React.JSX.Element | null {
  const query = useQuery(partnerCreditQueryOptions(partnerId));

  if (query.status === "error" && isApiError(query.error) && query.error.status === 403) {
    return null;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle level={2}>Credit standing</CardTitle>
        <CardDescription>Owed on open orders, less payments received.</CardDescription>
      </CardHeader>
      <CardContent>
        {query.status === "pending" ? (
          <div
            aria-busy="true"
            aria-label="Loading credit standing"
            className="grid gap-3 sm:grid-cols-3"
          >
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
          <dl className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-0.5">
              <dt className="text-xs text-muted-foreground">Credit limit</dt>
              <dd className="text-sm font-medium text-foreground tabular-nums">
                {query.data.creditLimit === null ? (
                  <span className="text-subtle-foreground">Not set: never checked</span>
                ) : (
                  formatInr(query.data.creditLimit, { paise: true })
                )}
              </dd>
            </div>
            <div className="flex flex-col gap-0.5">
              <dt className="text-xs text-muted-foreground">Exposure</dt>
              <dd className="text-sm font-medium text-foreground tabular-nums">
                {Number(query.data.exposure) < 0
                  ? `${unsigned(query.data.exposure)} in credit`
                  : formatInr(query.data.exposure, { paise: true })}
              </dd>
            </div>
            {query.data.available === null ? null : (
              <div className="flex flex-col gap-0.5">
                <dt className="text-xs text-muted-foreground">Available</dt>
                <dd className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground tabular-nums">
                  {Number(query.data.available) < 0 ? (
                    <>
                      <span>{unsigned(query.data.available)} over</span>
                      <Badge variant="danger" size="sm">
                        Over the limit
                      </Badge>
                    </>
                  ) : (
                    formatInr(query.data.available, { paise: true })
                  )}
                </dd>
              </div>
            )}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
