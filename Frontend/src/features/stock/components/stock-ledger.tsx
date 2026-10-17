"use client";

import { Book02Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { movementsQueryOptions } from "@/features/stock/api/stock.queries";
import {
  MOVEMENT_KIND_BADGE,
  MOVEMENT_KIND_LABELS,
  isNegative,
  signedQuantity,
} from "@/features/stock/lib/stock-labels";
import { cn } from "@/lib/utils";

import { WarehouseSelect } from "./warehouse-select";

/**
 * MSTR-014 · The stock ledger, newest first: every receipt, correction and dispatch, with the
 * dispatch and order behind it and who recorded it.
 */
export function StockLedger(): React.JSX.Element {
  const [warehouseId, setWarehouseId] = useState<string | null>(null);
  const query = useInfiniteQuery(movementsQueryOptions({ warehouseId, productId: null }));
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <Field className="md:w-60">
        <FieldLabel htmlFor="ledger-warehouse">Warehouse</FieldLabel>
        <WarehouseSelect
          id="ledger-warehouse"
          value={warehouseId}
          anyLabel="Every warehouse"
          onValueChange={setWarehouseId}
        />
      </Field>

      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading the stock ledger" className="flex flex-col gap-2">
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-16 w-full rounded-lg" />
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
          icon={Book02Icon}
          title="No stock movements yet"
          description="Receipts, corrections and dispatches show here as they happen."
          className="rounded-xl border border-dashed border-border"
        />
      ) : (
        <div className="flex flex-col gap-3">
          <ul
            aria-label="Stock movements"
            className="flex flex-col divide-y divide-border rounded-xl border border-border bg-card"
          >
            {rows.map((row) => (
              <li
                key={row.id}
                className="flex flex-col gap-1 p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4"
              >
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <Badge variant={MOVEMENT_KIND_BADGE[row.kind]} size="sm">
                      {MOVEMENT_KIND_LABELS[row.kind]}
                    </Badge>
                    <span className="text-sm text-foreground">{row.product.name}</span>
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {row.warehouse.name}
                    {row.reference === null ? "" : ` · ${row.reference}`}
                    {row.dispatchNo === null ? "" : ` · ${row.dispatchNo}`}
                    {row.orderNo === null ? "" : ` · order ${row.orderNo}`} ·{" "}
                    {row.createdBy ?? "the system"} <RelativeDate value={row.createdAt} />
                  </span>
                  {row.note === null ? null : (
                    <span className="text-xs text-muted-foreground">{row.note}</span>
                  )}
                </span>
                <span
                  className={cn(
                    "text-sm font-semibold tabular-nums",
                    isNegative(row.qty) ? "text-danger" : "text-foreground",
                  )}
                >
                  {signedQuantity(row.qty)}
                </span>
              </li>
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
