import type * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { formatInr, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/** One column of a report: the first is each row's header, the rest are figures. */
export interface ReportColumn<Row> {
  readonly id: string;
  readonly header: string;
  readonly cell: (row: Row) => React.ReactNode;
  /** The Total line's cell; nothing when the backend sends no total for it. */
  readonly total?: React.ReactNode;
  /** A column a phone leaves out, so the table fits without scrolling sideways. */
  readonly wide?: boolean;
}

const cell = "py-2 pl-3 text-right tabular-nums sm:pl-4";
const headCell = "py-2 pl-3 text-right font-medium sm:pl-4";
const wideCell = "hidden md:table-cell";

/**
 * RPT-002 · A report's rows under its column headers, with a Total line. Figures sit right,
 * in tabular numbers; the first column names the row.
 */
export function ReportTable<Row>({
  caption,
  rowHeader,
  columns,
  rows,
  rowKey,
  totalLabel = "Total",
}: {
  caption: string;
  rowHeader: ReportColumn<Row>;
  columns: readonly ReportColumn<Row>[];
  rows: readonly Row[];
  rowKey: (row: Row, index: number) => string;
  totalLabel?: string;
}): React.JSX.Element {
  const hasTotals = columns.some((column) => column.total !== undefined);
  return (
    <div className="min-w-0">
      <table className="w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-border text-xs text-muted-foreground">
            <th scope="col" className="py-2 pr-4 text-left font-medium">
              {rowHeader.header}
            </th>
            {columns.map((column) => (
              <th
                key={column.id}
                scope="col"
                className={cn(headCell, column.wide === true && wideCell)}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey(row, index)} className="border-b border-border last:border-0">
              <th
                scope="row"
                className="py-2 pr-4 text-left align-top font-normal wrap-break-word text-foreground"
              >
                {rowHeader.cell(row)}
              </th>
              {columns.map((column) => (
                <td
                  key={column.id}
                  className={cn(cell, "align-top", column.wide === true && wideCell)}
                >
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {hasTotals ? (
          <tfoot>
            <tr className="border-t-2 border-foreground font-semibold text-foreground">
              <th scope="row" className="py-2 pr-4 text-left">
                {totalLabel}
              </th>
              {columns.map((column) => (
                <td key={column.id} className={cn(cell, column.wide === true && wideCell)}>
                  {column.total ?? null}
                </td>
              ))}
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}

/** A figure the user may not see: the backend sends null, never 0 (reports-contract.md). */
export function NotAvailable(): React.JSX.Element {
  return (
    <>
      <span aria-hidden className="text-muted-foreground">
        —
      </span>
      <span className="sr-only">Not available to you</span>
    </>
  );
}

/** A count, or "not available to you". */
export function countCell(value: number | null): React.ReactNode {
  return value === null ? <NotAvailable /> : formatNumber(value);
}

/** Rupees from a decimal string, or "not available to you". */
export function moneyCell(value: string | null): React.ReactNode {
  return value === null ? <NotAvailable /> : formatInr(value);
}

/** "12.8%" from the backend's "12.8". */
export function formatPct(value: string): string {
  return `${formatNumber(Number(value), 1)}%`;
}

export function ReportTableSkeleton({ label }: { label: string }): React.JSX.Element {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-2">
      {Array.from({ length: 6 }, (_, index) => (
        <Skeleton key={index} className="h-9 w-full" />
      ))}
    </div>
  );
}
