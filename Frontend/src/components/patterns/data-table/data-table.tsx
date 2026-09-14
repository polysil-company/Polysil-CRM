"use client";
// TanStack Table keeps stable row/cell objects while state changes. React Compiler
// memoisation would then skip re-rendering cells (e.g. selection checkboxes), so this
// file opts out — the TanStack Table v9 React Compiler guide's documented escape hatch.
"use no memo";

import {
  ArrowDown01Icon,
  ArrowLeft01Icon,
  ArrowRight01Icon,
  ArrowUp01Icon,
  ArrowUpDownIcon,
} from "@hugeicons/core-free-icons";
import {
  FlexRender,
  functionalUpdate,
  useTable,
  type Header,
  type PaginationState,
  type RowData,
  type RowSelectionState,
  type SortingState,
  type TableOptions,
} from "@tanstack/react-table";
import type * as React from "react";

import { IndeterminateBar } from "@/components/patterns/indeterminate-bar";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  bodyCellClasses,
  dataTableFeatures,
  headerCellClasses,
  type DataTableFeatures,
} from "./table-features";

const EMPTY_SELECTION: RowSelectionState = {};

export const DEFAULT_PAGE_SIZES: readonly number[] = [25, 50, 100];

export interface DataTableProps<TData extends RowData> {
  /** Accessible table name, e.g. "Leads". */
  label: string;
  columns: TableOptions<DataTableFeatures, TData>["columns"];
  data: readonly TData[];
  getRowId: (row: TData) => string;
  /** Total rows across all pages (server-side pagination). */
  rowCount: number;
  sorting: SortingState;
  onSortingChange: (sorting: SortingState) => void;
  pagination: PaginationState;
  onPaginationChange: (pagination: PaginationState) => void;
  /** Pass both to enable row selection. */
  rowSelection?: RowSelectionState;
  onRowSelectionChange?: (selection: RowSelectionState) => void;
  /** A background refetch is running: rows stay visible and a progress line shows. */
  isFetching?: boolean;
  pageSizeOptions?: readonly number[];
  className?: string;
}

/**
 * The app's table. Server-side sorting and pagination; sticky header; scrolls
 * inside its own area so the header and pagination stay in view.
 * Loading state: <DataTableSkeleton>; empty/error: handled by the parent's <QueryView>.
 */
export function DataTable<TData extends RowData>({
  label,
  columns,
  data,
  getRowId,
  rowCount,
  sorting,
  onSortingChange,
  pagination,
  onPaginationChange,
  rowSelection,
  onRowSelectionChange,
  isFetching = false,
  pageSizeOptions = DEFAULT_PAGE_SIZES,
  className,
}: DataTableProps<TData>): React.JSX.Element {
  const selectable = rowSelection !== undefined && onRowSelectionChange !== undefined;
  const currentSelection = rowSelection ?? EMPTY_SELECTION;

  const table = useTable({
    features: dataTableFeatures,
    columns,
    data,
    getRowId,
    rowCount,
    manualSorting: true,
    manualPagination: true,
    enableRowSelection: selectable,
    state: { sorting, pagination, rowSelection: currentSelection },
    onSortingChange: (updater) => {
      onSortingChange(functionalUpdate(updater, sorting));
    },
    onPaginationChange: (updater) => {
      onPaginationChange(functionalUpdate(updater, pagination));
    },
    onRowSelectionChange: (updater) => {
      onRowSelectionChange?.(functionalUpdate(updater, currentSelection));
    },
  });

  const rows = table.getRowModel().rows;
  const firstRowIndex = pagination.pageIndex * pagination.pageSize;

  return (
    <div data-slot="data-table" className={cn("flex min-h-0 flex-col", className)}>
      <div className="relative min-h-0 flex-1">
        <IndeterminateBar
          active={isFetching}
          label={`Updating ${label.toLowerCase()}`}
          className="absolute inset-x-0 top-10 layer-header"
        />
        <div className="h-full scrollbar-thin overflow-auto">
          <table
            aria-label={label}
            aria-rowcount={rowCount + 1}
            className="w-full border-separate border-spacing-0"
          >
            <thead>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id} aria-rowindex={1}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      scope="col"
                      colSpan={header.colSpan}
                      aria-sort={ariaSort(header)}
                      className={headerCellClasses(header.column.columnDef.meta)}
                    >
                      {header.isPlaceholder ? null : <HeaderContent header={header} />}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr
                  key={row.id}
                  aria-rowindex={firstRowIndex + index + 2}
                  aria-selected={selectable ? row.getIsSelected() : undefined}
                  data-selected={row.getIsSelected()}
                  className="transition-colors duration-fast hover:bg-accent data-[selected=true]:bg-row-selected"
                >
                  {row.getVisibleCells().map((cell) => {
                    const meta = cell.column.columnDef.meta;
                    return meta?.isRowHeader ? (
                      <th key={cell.id} scope="row" className={bodyCellClasses(meta)}>
                        <FlexRender cell={cell} />
                      </th>
                    ) : (
                      <td key={cell.id} className={bodyCellClasses(meta)}>
                        <FlexRender cell={cell} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <Pagination
        pageIndex={pagination.pageIndex}
        pageSize={pagination.pageSize}
        pageCount={table.getPageCount()}
        rowCount={rowCount}
        canPrevious={table.getCanPreviousPage()}
        canNext={table.getCanNextPage()}
        onPrevious={() => {
          table.previousPage();
        }}
        onNext={() => {
          table.nextPage();
        }}
        onPageSizeChange={(pageSize) => {
          onPaginationChange({ pageIndex: 0, pageSize });
        }}
        pageSizeOptions={pageSizeOptions}
      />
    </div>
  );
}

function ariaSort<TData extends RowData>(
  header: Header<DataTableFeatures, TData, unknown>,
): React.AriaAttributes["aria-sort"] {
  if (!header.column.getCanSort()) {
    return undefined;
  }
  const direction = header.column.getIsSorted();
  return direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none";
}

function HeaderContent<TData extends RowData>({
  header,
}: {
  header: Header<DataTableFeatures, TData, unknown>;
}): React.JSX.Element {
  if (!header.column.getCanSort()) {
    return <FlexRender header={header} />;
  }

  const direction = header.column.getIsSorted();
  const sortIcon =
    direction === "asc" ? ArrowUp01Icon : direction === "desc" ? ArrowDown01Icon : ArrowUpDownIcon;

  return (
    <button
      type="button"
      onClick={header.column.getToggleSortingHandler()}
      className="group/sort -mx-1.5 inline-flex h-7 items-center gap-1 rounded-sm px-1.5 whitespace-nowrap transition-colors duration-fast hover:bg-accent hover:text-foreground"
    >
      <FlexRender header={header} />
      <Icon
        icon={sortIcon}
        size="sm"
        className={cn(
          direction === false
            ? "text-subtle-foreground opacity-0 group-hover/sort:opacity-100 group-focus-visible/sort:opacity-100"
            : "text-foreground",
        )}
      />
    </button>
  );
}

interface PaginationProps {
  pageIndex: number;
  pageSize: number;
  pageCount: number;
  rowCount: number;
  canPrevious: boolean;
  canNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onPageSizeChange: (pageSize: number) => void;
  pageSizeOptions: readonly number[];
}

function Pagination({
  pageIndex,
  pageSize,
  pageCount,
  rowCount,
  canPrevious,
  canNext,
  onPrevious,
  onNext,
  onPageSizeChange,
  pageSizeOptions,
}: PaginationProps): React.JSX.Element {
  const from = rowCount === 0 ? 0 : pageIndex * pageSize + 1;
  const to = Math.min(rowCount, (pageIndex + 1) * pageSize);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-2.5">
      <p className="text-xs text-muted-foreground tabular-nums" aria-live="polite">
        {formatNumber(from)}–{formatNumber(to)} of {formatNumber(rowCount)}
      </p>
      <div className="flex items-center gap-1.5">
        <Select
          value={String(pageSize)}
          onValueChange={(value) => {
            if (typeof value === "string") {
              onPageSizeChange(Number(value));
            }
          }}
        >
          <SelectTrigger size="sm" className="w-20" aria-label="Rows per page">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {pageSizeOptions.map((option) => (
              <SelectItem key={option} value={String(option)}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Previous page"
          disabled={!canPrevious}
          onClick={onPrevious}
        >
          <Icon icon={ArrowLeft01Icon} />
        </Button>
        <span className="min-w-20 text-center text-xs text-muted-foreground tabular-nums">
          Page {formatNumber(pageIndex + 1)} of {formatNumber(Math.max(pageCount, 1))}
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Next page"
          disabled={!canNext}
          onClick={onNext}
        >
          <Icon icon={ArrowRight01Icon} />
        </Button>
      </div>
    </div>
  );
}
