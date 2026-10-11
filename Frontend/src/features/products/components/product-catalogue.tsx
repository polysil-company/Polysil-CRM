"use client";

import { Add01Icon, PackageIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { SingleFilterPill } from "@/components/patterns/filter-pill";
import { QueryView } from "@/components/patterns/query-view";
import { SearchField } from "@/components/patterns/search-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { PRODUCT_PAGE_SIZE } from "@/features/products/api/products.api";
import {
  catalogueFacetsQueryOptions,
  productListQueryOptions,
} from "@/features/products/api/products.queries";
import { QUOTATION_CATEGORIES, type Product } from "@/features/products/api/products.schemas";
import { Pager } from "@/features/products/components/pager";
import { ProductDialog } from "@/features/products/components/product-dialog";
import {
  PRODUCT_STATUSES,
  useProductMasterParams,
  type ProductStatus,
} from "@/features/products/hooks/use-product-master-params";
import { QUOTATION_CATEGORY_LABELS, slabText } from "@/features/products/lib/product-labels";
import { formatCount, formatInr } from "@/lib/format";

const SKELETON_ROWS = 6;

const BLOCK_OPTIONS = QUOTATION_CATEGORIES.map((value) => ({
  value,
  label: QUOTATION_CATEGORY_LABELS[value],
}));

const STATUS_LABELS: Readonly<Record<ProductStatus, string>> = {
  active: "Active",
  off: "Switched off",
  all: "All",
};
const STATUS_OPTIONS = PRODUCT_STATUSES.filter((value) => value !== "active").map((value) => ({
  value,
  label: STATUS_LABELS[value],
}));

type Editing = { readonly mode: "new" } | { readonly mode: "edit"; readonly product: Product };

/**
 * MSTR-004 · The catalogue: every product quotations and orders can carry, searchable by name
 * or item code, filtered by category, quotation block and status, a page at a time. Admin-Sales
 * and the MD add and correct products; everyone else reads them.
 */
export function ProductCatalogue({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const { params, status, page, activeFilterCount, setFilters, setPage, resetFilters } =
    useProductMasterParams();
  const query = useQuery(productListQueryOptions(params, page));
  const facets = useQuery(catalogueFacetsQueryOptions());
  const [editing, setEditing] = useState<Editing | null>(null);
  const categoryOptions = (facets.data?.categories ?? []).map((value) => ({ value, label: value }));
  const filtered = activeFilterCount > 0;

  return (
    <section aria-label="Products" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
        <SearchField
          label="Search products"
          placeholder="Description or item code"
          value={params.q}
          onSearch={(q) => {
            setFilters({ q });
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          <SingleFilterPill
            label="Category"
            options={categoryOptions}
            selected={params.category}
            emptyMessage={facets.isPending ? "Loading categories…" : "No categories yet."}
            onChange={(category) => {
              setFilters({ category });
            }}
          />
          <SingleFilterPill
            label="Block"
            options={BLOCK_OPTIONS}
            selected={params.quotationCategory}
            onChange={(quotationCategory) => {
              setFilters({ quotationCategory });
            }}
          />
          <SingleFilterPill
            label="Status"
            options={STATUS_OPTIONS}
            selected={status === "active" ? null : status}
            onChange={(next) => {
              setFilters({ status: next ?? "active" });
            }}
          />
          {filtered ? (
            <Button variant="ghost" size="sm" onClick={resetFilters}>
              Reset filters
            </Button>
          ) : null}
        </div>
        {canEdit ? (
          <Button
            className="md:ml-auto"
            onClick={() => {
              setEditing({ mode: "new" });
            }}
          >
            <Icon icon={Add01Icon} />
            New product
          </Button>
        ) : null}
      </div>

      <QueryView
        query={query}
        pending={<ProductCatalogueSkeleton />}
        isEmpty={(data) => data.total === 0}
        empty={
          <EmptyState
            icon={PackageIcon}
            title={filtered ? "No products match these filters" : "No products yet"}
            description={
              filtered
                ? "Change or reset the filters to see more."
                : canEdit
                  ? "Add the first product: quotations and orders can carry it once it has a rate."
                  : "Admin-Sales adds products here."
            }
            action={
              filtered ? (
                <Button variant="outline" size="sm" onClick={resetFilters}>
                  Reset filters
                </Button>
              ) : undefined
            }
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <p aria-live="polite" className="text-sm text-muted-foreground">
              {formatCount(data.total)} {data.total === 1 ? "product" : "products"}
              {status === "active" ? ", active" : status === "off" ? ", switched off" : ""}.
            </p>
            {data.items.length === 0 ? (
              <p className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
                This page is past the end of the list.{" "}
                <Button
                  variant="link"
                  className="h-auto p-0"
                  onClick={() => {
                    setPage(1);
                  }}
                >
                  Back to the first page
                </Button>
              </p>
            ) : (
              <ul aria-label="Products" className="flex flex-col gap-2">
                {data.items.map((product) => (
                  <ProductRow
                    key={product.id}
                    product={product}
                    onOpen={() => {
                      setEditing({ mode: "edit", product });
                    }}
                  />
                ))}
              </ul>
            )}
            <Pager
              page={page}
              limit={PRODUCT_PAGE_SIZE}
              total={data.total}
              noun="products"
              isPaging={query.isPlaceholderData}
              onPage={setPage}
            />
          </div>
        )}
      </QueryView>

      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      >
        <DialogContent size="lg">
          {editing === null ? null : (
            <ProductDialog
              key={editing.mode === "new" ? "new" : editing.product.id}
              product={editing.mode === "new" ? null : editing.product}
              canEdit={canEdit}
              onClose={() => {
                setEditing(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function ProductRow({
  product,
  onOpen,
}: {
  product: Product;
  onOpen: () => void;
}): React.JSX.Element {
  const standIns = product.provisional.length;
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        aria-label={`${product.description}${product.active ? "" : ", switched off"}${standIns > 0 ? ", has stand-in figures" : ""}`}
        className="flex w-full flex-col gap-1.5 rounded-xl border border-border bg-card p-3 text-left transition-colors duration-fast hover:bg-accent sm:p-4"
      >
        <span className="flex flex-wrap items-center gap-2">
          <span className="min-w-0 text-sm font-medium wrap-break-word text-foreground">
            {product.description}
          </span>
          {product.active ? null : (
            <Badge variant="neutral" size="sm" dot>
              Switched off
            </Badge>
          )}
          {product.hsnCode === null ? (
            <Badge variant="danger" size="sm">
              No HSN
            </Badge>
          ) : null}
          {standIns > 0 ? (
            <Badge variant="warning" size="sm">
              {standIns === 1 ? "1 stand-in" : `${String(standIns)} stand-ins`}
            </Badge>
          ) : null}
        </span>
        <span className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          {product.itemCode === null ? null : <span className="font-mono">{product.itemCode}</span>}
          <span>{product.category}</span>
          <span>{QUOTATION_CATEGORY_LABELS[product.quotationCategory]}</span>
          <span>{product.uom}</span>
          {product.hsnCode === null ? null : (
            <span>
              HSN {product.hsnCode}
              {product.gstSlab === null ? "" : ` · GST ${slabText(product.gstSlab)}`}
            </span>
          )}
          {product.mrp === null ? null : (
            <span className="tabular-nums">MRP {formatInr(product.mrp, { paise: true })}</span>
          )}
        </span>
      </button>
    </li>
  );
}

export function ProductCatalogueSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading products" className="flex flex-col gap-2">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} className="flex flex-col gap-2 rounded-xl border border-border p-3 sm:p-4">
          <Skeleton className="h-4 w-72 max-w-full" />
          <Skeleton className="h-3 w-56 max-w-full" />
        </div>
      ))}
    </div>
  );
}
