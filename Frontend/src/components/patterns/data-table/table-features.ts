import {
  columnVisibilityFeature,
  createColumnHelper,
  metaHelper,
  rowPaginationFeature,
  rowSelectionFeature,
  rowSortingFeature,
  tableFeatures,
  type ColumnHelper,
  type RowData,
} from "@tanstack/react-table";

import { cn } from "@/lib/utils";

/** Column widths — tokens, not free-form classes, so tables stay consistent. */
export const COLUMN_WIDTH_CLASSES = {
  checkbox: "w-11 min-w-11",
  xs: "w-20 min-w-20",
  sm: "w-28 min-w-28",
  md: "w-40 min-w-40",
  lg: "w-56 min-w-56",
  xl: "w-72 min-w-72",
  fill: "min-w-56",
} as const;

export type ColumnWidth = keyof typeof COLUMN_WIDTH_CLASSES;

export const HIDE_BELOW_CLASSES = {
  sm: "max-sm:hidden",
  md: "max-md:hidden",
  lg: "max-lg:hidden",
  xl: "max-xl:hidden",
} as const;

export interface DataTableColumnMeta {
  /** Numbers and money align to the end. */
  readonly align?: "start" | "end";
  readonly width?: ColumnWidth;
  /** Hide the column below this breakpoint so small screens stay readable. */
  readonly hideBelow?: keyof typeof HIDE_BELOW_CLASSES;
  /** The cell that names the row; rendered as a row header for screen readers. */
  readonly isRowHeader?: boolean;
}

/**
 * The feature set every app table uses (TanStack Table v9 declares features
 * explicitly). Sorting and pagination are server-side ("manual").
 */
export const dataTableFeatures = tableFeatures({
  rowSortingFeature,
  rowPaginationFeature,
  rowSelectionFeature,
  columnVisibilityFeature,
  columnMeta: metaHelper<DataTableColumnMeta>(),
});

export type DataTableFeatures = typeof dataTableFeatures;

export function createDataTableColumnHelper<TData extends RowData>(): ColumnHelper<
  DataTableFeatures,
  TData
> {
  return createColumnHelper<DataTableFeatures, TData>();
}

/** Shared by DataTable and DataTableSkeleton so loading and loaded rows are the same height. */
const ROW_HEIGHT_CLASS = "h-13";
const HEADER_HEIGHT_CLASS = "h-10";

export function headerCellClasses(meta: DataTableColumnMeta | undefined): string {
  return cn(
    "sticky top-0 layer-sticky border-b border-border bg-panel px-3 text-left text-xs font-medium whitespace-nowrap text-muted-foreground first:pl-4 last:pr-4",
    HEADER_HEIGHT_CLASS,
    meta?.align === "end" && "text-right",
    meta?.width && COLUMN_WIDTH_CLASSES[meta.width],
    meta?.hideBelow && HIDE_BELOW_CLASSES[meta.hideBelow],
  );
}

export function bodyCellClasses(meta: DataTableColumnMeta | undefined): string {
  return cn(
    "border-b border-border px-3 text-left text-sm font-normal text-foreground first:pl-4 last:pr-4",
    ROW_HEIGHT_CLASS,
    meta?.align === "end" && "text-right tabular-nums",
    meta?.width && COLUMN_WIDTH_CLASSES[meta.width],
    meta?.hideBelow && HIDE_BELOW_CLASSES[meta.hideBelow],
  );
}
