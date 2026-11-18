import type { DataTableColumnMeta } from "@/components/patterns/data-table";

/**
 * Single source for the orders table layout, shared by the columns and the skeleton.
 * Plain module (no "use client") so route loading files can import it.
 */
export const ORDER_COLUMN_META = {
  number: { width: "lg", isRowHeader: true },
  party: { width: "fill" },
  status: { width: "md" },
  dispatched: { width: "sm", hideBelow: "md" },
  orderType: { width: "sm", hideBelow: "xl" },
  owner: { width: "fill", hideBelow: "lg" },
  createdAt: { width: "sm", hideBelow: "lg" },
  total: { width: "sm", align: "end" },
} as const satisfies Record<string, DataTableColumnMeta>;

const COLUMN_ORDER = [
  "number",
  "party",
  "status",
  "dispatched",
  "orderType",
  "owner",
  "createdAt",
  "total",
] as const;

export const ORDER_COLUMN_LAYOUT: readonly DataTableColumnMeta[] = COLUMN_ORDER.map(
  (id) => ORDER_COLUMN_META[id],
);

export const ORDERS_TABLE_LABEL = "Sales orders";

/** Frame around the table, its skeleton and its empty states. */
export const ORDERS_TABLE_FRAME_CLASSES =
  "min-h-80 flex-1 overflow-hidden rounded-xl border border-border lg:min-h-0";

export const ORDERS_EMPTY_FRAME_CLASSES =
  "min-h-80 flex-1 rounded-xl border border-dashed border-border";
