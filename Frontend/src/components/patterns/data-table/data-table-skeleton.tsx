import type * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { bodyCellClasses, headerCellClasses, type DataTableColumnMeta } from "./table-features";

const WIDTH_CYCLE = ["w-3/4", "w-1/2", "w-2/3", "w-5/6"] as const;

export interface DataTableSkeletonProps {
  /** Same label as the DataTable it stands in for. */
  label: string;
  /** Same column meta as the real columns — identical widths and breakpoints. */
  columns: readonly DataTableColumnMeta[];
  rows?: number;
  /** Index of the selection checkbox column, if any. */
  checkboxColumn?: number;
  className?: string;
}

/** Loading table built from the same cell classes as DataTable, so nothing shifts when rows arrive. */
export function DataTableSkeleton({
  label,
  columns,
  rows = 10,
  checkboxColumn,
  className,
}: DataTableSkeletonProps): React.JSX.Element {
  return (
    <div
      role="status"
      aria-label={`Loading ${label.toLowerCase()}`}
      className={cn("flex min-h-0 flex-col", className)}
    >
      <div className="min-h-0 flex-1 overflow-hidden">
        <table aria-hidden="true" className="w-full border-separate border-spacing-0">
          <thead>
            <tr>
              {columns.map((meta, columnIndex) => (
                <th key={columnIndex} className={headerCellClasses(meta)}>
                  {columnIndex === checkboxColumn ? (
                    <Skeleton className="size-4 rounded-xs" />
                  ) : (
                    <Skeleton className="h-3 w-16" />
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }, (_, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((meta, columnIndex) => (
                  <td key={columnIndex} className={bodyCellClasses(meta)}>
                    <SkeletonCell
                      meta={meta}
                      isCheckbox={columnIndex === checkboxColumn}
                      seed={rowIndex + columnIndex}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-2.5">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-control-sm w-48" />
      </div>
    </div>
  );
}

function SkeletonCell({
  meta,
  isCheckbox,
  seed,
}: {
  meta: DataTableColumnMeta;
  isCheckbox: boolean;
  seed: number;
}): React.JSX.Element {
  if (isCheckbox) {
    return <Skeleton className="size-4 rounded-xs" />;
  }
  if (meta.isRowHeader) {
    return (
      <span className="flex items-center gap-2">
        <Skeleton className="size-6 shrink-0 rounded-full" />
        <span className="flex flex-1 flex-col gap-1">
          <Skeleton className="h-3.5 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </span>
      </span>
    );
  }
  return (
    <Skeleton
      className={cn(
        "h-3.5",
        WIDTH_CYCLE[seed % WIDTH_CYCLE.length],
        meta.align === "end" && "ml-auto",
      )}
    />
  );
}
