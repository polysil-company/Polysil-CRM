import type { DataTableColumnMeta } from "@/components/patterns/data-table";

/**
 * Single source for the quotations table layout, shared by the columns and the skeleton.
 * Plain module (no "use client") so route loading files can import it.
 */
export const QUOTATION_COLUMN_META = {
  number: { width: "lg", isRowHeader: true },
  party: { width: "fill" },
  status: { width: "sm" },
  salesType: { width: "sm", hideBelow: "xl" },
  owner: { width: "fill", hideBelow: "lg" },
  sentAt: { width: "sm", hideBelow: "md" },
  validUntil: { width: "sm", hideBelow: "lg" },
  total: { width: "sm", align: "end" },
} as const satisfies Record<string, DataTableColumnMeta>;

const COLUMN_ORDER = [
  "number",
  "party",
  "status",
  "salesType",
  "owner",
  "sentAt",
  "validUntil",
  "total",
] as const;

export const QUOTATION_COLUMN_LAYOUT: readonly DataTableColumnMeta[] = COLUMN_ORDER.map(
  (id) => QUOTATION_COLUMN_META[id],
);

export const QUOTATIONS_TABLE_LABEL = "Quotations";

/** Frame around the table, its skeleton and its empty states. */
export const QUOTATIONS_TABLE_FRAME_CLASSES =
  "min-h-80 flex-1 overflow-hidden rounded-xl border border-border lg:min-h-0";

export const QUOTATIONS_EMPTY_FRAME_CLASSES =
  "min-h-80 flex-1 rounded-xl border border-dashed border-border";
