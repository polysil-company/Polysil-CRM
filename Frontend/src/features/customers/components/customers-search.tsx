"use client";

import { UserAccountIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { SearchField } from "@/components/patterns/search-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { customerListQueryOptions } from "@/features/customers/api/customers.queries";
import { CUSTOMER_SEARCH_MIN_LENGTH } from "@/features/customers/api/customers.schemas";
import { CUSTOMER_TYPE_LABELS } from "@/features/customers/lib/customer-labels";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { formatIndianPhone } from "@/lib/format";

/**
 * LEAD-016 · Find a customer by name or mobile (three characters or more), in an area, newest
 * first. A customer shows when the user can see one of its leads.
 */
export function CustomersSearch(): React.JSX.Element {
  const [q, setQ] = useState("");
  const [area, setArea] = useState<TerritoryChoice | null>(null);
  const typed = q.trim();
  const tooShort = typed.length > 0 && typed.length < CUSTOMER_SEARCH_MIN_LENGTH;
  const query = useInfiniteQuery(
    customerListQueryOptions({
      q: tooShort ? "" : typed,
      territoryId: area?.id ?? null,
    }),
  );
  const customers = query.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field>
          <SearchField
            label="Find a customer"
            value={q}
            placeholder="Name or mobile"
            onSearch={setQ}
          />
          {tooShort ? (
            <p className="text-xs text-muted-foreground">
              Type at least {CUSTOMER_SEARCH_MIN_LENGTH} letters or digits to search.
            </p>
          ) : null}
        </Field>
        <Field>
          <FieldLabel htmlFor="customer-area" className="sr-only">
            Area
          </FieldLabel>
          <TerritoryPicker
            id="customer-area"
            value={area}
            placeholder="Any area"
            onValueChange={setArea}
          />
        </Field>
      </div>

      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading customers" className="flex flex-col gap-2">
          <Skeleton className="h-16 w-full rounded-xl" />
          <Skeleton className="h-16 w-full rounded-xl" />
          <Skeleton className="h-16 w-full rounded-xl" />
        </div>
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : customers.length === 0 ? (
        <EmptyState
          icon={UserAccountIcon}
          title={
            typed.length >= CUSTOMER_SEARCH_MIN_LENGTH || area !== null
              ? "No customer matches"
              : "No customers yet"
          }
          description={
            typed.length >= CUSTOMER_SEARCH_MIN_LENGTH || area !== null
              ? "Try part of the name, the last digits of the mobile, or another area."
              : "A lead becomes a customer when it is qualified."
          }
          level={2}
          className="py-12"
        />
      ) : (
        <>
          <ul aria-label="Customers" className="flex flex-col gap-2">
            {customers.map((customer) => (
              <li key={customer.id}>
                <Link
                  href={`/customers/${customer.id}`}
                  className="flex flex-col gap-1 rounded-xl border border-border bg-card p-3 focus-ring-inset transition-colors duration-fast hover:bg-muted/50 sm:flex-row sm:items-center sm:justify-between sm:p-4"
                >
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="text-sm font-medium text-foreground">{customer.name}</span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {formatIndianPhone(customer.mobile)}
                      {customer.village === null ? "" : ` · ${customer.village}`}
                      {customer.territory === null ? "" : ` · ${customer.territory.name}`}
                    </span>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <Badge variant="outline" size="sm">
                      {CUSTOMER_TYPE_LABELS[customer.type]}
                    </Badge>
                    <Badge variant="neutral" size="sm">
                      {customer.leadCount === 1 ? "1 lead" : `${String(customer.leadCount)} leads`}
                    </Badge>
                    {customer.consentGivenAt === null ? null : (
                      <Badge variant="success" size="sm">
                        Consent
                      </Badge>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
          {query.hasNextPage ? (
            <Button
              variant="outline"
              size="sm"
              className="self-center"
              disabled={query.isFetchingNextPage}
              onClick={() => {
                void query.fetchNextPage();
              }}
            >
              {query.isFetchingNextPage ? "Loading…" : "Show more"}
            </Button>
          ) : null}
        </>
      )}
    </div>
  );
}
