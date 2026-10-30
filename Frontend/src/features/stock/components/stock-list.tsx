"use client";

import { Cancel01Icon, PackageIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ProductSearchPicker } from "@/features/schemes/components/record-pickers";
import { stockListQueryOptions } from "@/features/stock/api/stock.queries";
import { isNegative, quantityText } from "@/features/stock/lib/stock-labels";
import { cn } from "@/lib/utils";

import { WarehouseSelect } from "./warehouse-select";

/**
 * MSTR-014 · What each warehouse holds of each product: on hand, committed to open orders, and
 * available. A negative figure is short and shows in red. Filters: warehouse, product, short only.
 */
export function StockList(): React.JSX.Element {
  const [warehouseId, setWarehouseId] = useState<string | null>(null);
  const [product, setProduct] = useState<{ id: string; name: string } | null>(null);
  const [shortOnly, setShortOnly] = useState(false);
  const query = useInfiniteQuery(
    stockListQueryOptions({ warehouseId, productId: product?.id ?? null, shortOnly }),
  );
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];
  const filtered = warehouseId !== null || product !== null || shortOnly;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-end">
        <Field className="md:w-60">
          <FieldLabel htmlFor="stock-warehouse">Warehouse</FieldLabel>
          <WarehouseSelect
            id="stock-warehouse"
            value={warehouseId}
            anyLabel="Every warehouse"
            onValueChange={setWarehouseId}
          />
        </Field>
        <Field className="md:w-72">
          <FieldLabel htmlFor="stock-product">Product</FieldLabel>
          {product === null ? (
            <ProductSearchPicker
              id="stock-product"
              onPick={(picked) => {
                setProduct({ id: picked.id, name: picked.name });
              }}
            />
          ) : (
            <div className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm">
              <span className="truncate text-foreground">{product.name}</span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Every product, not only ${product.name}`}
                onClick={() => {
                  setProduct(null);
                }}
              >
                <Icon icon={Cancel01Icon} />
              </Button>
            </div>
          )}
        </Field>
        <div className="flex items-center gap-2 md:pb-2">
          <Checkbox
            id="stock-short-only"
            checked={shortOnly}
            onCheckedChange={(checked) => {
              setShortOnly(checked);
            }}
          />
          <Label htmlFor="stock-short-only">Short only</Label>
        </div>
      </div>

      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading stock" className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((row) => (
            <Skeleton key={row} className="h-12 w-full rounded-lg" />
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
          icon={PackageIcon}
          title={
            shortOnly ? "Nothing is short" : filtered ? "No stock matches" : "No stock recorded yet"
          }
          description={
            shortOnly
              ? "Every warehouse holds enough for its open orders."
              : "Record what each warehouse holds, starting with an opening balance."
          }
          className="rounded-xl border border-dashed border-border"
        />
      ) : (
        <div className="flex flex-col gap-3">
          <div
            role="region"
            aria-label="Stock by warehouse and product"
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must be reachable by keyboard (WCAG 2.1.1)
            tabIndex={0}
            className="overflow-x-auto rounded-xl border border-border focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <table className="w-full min-w-2xl text-sm">
              <caption className="sr-only">
                On hand, committed to open orders, and available, by warehouse and product
              </caption>
              <thead className="bg-muted text-left text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Product
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Warehouse
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    On hand
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    Committed
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    Available
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((row) => (
                  <tr key={`${row.warehouse.id}:${row.product.id}`}>
                    <td className="px-3 py-2">
                      <span className="block text-foreground">{row.product.name}</span>
                      {row.product.code === null ? null : (
                        <span className="font-mono text-xs text-muted-foreground">
                          {row.product.code}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{row.warehouse.name}</td>
                    <td
                      className={cn(
                        "px-3 py-2 text-right whitespace-nowrap tabular-nums",
                        isNegative(row.onHand) && "font-semibold text-danger",
                      )}
                    >
                      {quantityText(row.onHand, row.uom)}
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap text-muted-foreground tabular-nums">
                      {quantityText(row.committed, row.uom)}
                    </td>
                    <td
                      className={cn(
                        "px-3 py-2 text-right whitespace-nowrap tabular-nums",
                        isNegative(row.available) ? "font-semibold text-danger" : "text-foreground",
                      )}
                    >
                      {isNegative(row.available)
                        ? `Short by ${quantityText(String(-Number(row.available)), row.uom)}`
                        : quantityText(row.available, row.uom)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
