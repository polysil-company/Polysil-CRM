"use client";

import type { ColumnHelper, DisplayColumnDef, RowData } from "@tanstack/react-table";

import { Checkbox } from "@/components/ui/checkbox";

import type { DataTableFeatures } from "./table-features";

/** Checkbox column with page-level select-all. `getRowLabel` names each row for screen readers. */
export function createSelectionColumn<TData extends RowData>(
  helper: ColumnHelper<DataTableFeatures, TData>,
  getRowLabel: (row: TData) => string,
): DisplayColumnDef<DataTableFeatures, TData, unknown> {
  return helper.display({
    id: "select",
    header: ({ table }) => (
      <Checkbox
        aria-label="Select all rows on this page"
        checked={table.getIsAllPageRowsSelected()}
        indeterminate={table.getIsSomePageRowsSelected() && !table.getIsAllPageRowsSelected()}
        onCheckedChange={(checked) => {
          table.toggleAllPageRowsSelected(checked);
        }}
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        aria-label={`Select ${getRowLabel(row.original)}`}
        checked={row.getIsSelected()}
        disabled={!row.getCanSelect()}
        onCheckedChange={(checked) => {
          row.toggleSelected(checked);
        }}
      />
    ),
    enableSorting: false,
    meta: { width: "checkbox" },
  });
}
