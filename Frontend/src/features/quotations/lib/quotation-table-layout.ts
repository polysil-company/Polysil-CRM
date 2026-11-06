import type { DataTableColumnMeta } from "@/components/patterns/data-table";

/**
 * Single source for the quotations table layout, shared by the columns and the skeleton.
 * Plain module (no "use client") so route loading files can import it.
 */
export const QUOTATION_COLUMN_META = {
  number: { width: "lg", isRowHeader: true },
  party: { width: "fill" },
  status: { width: "sm" },
  // APP-009 (live test D-05) · The row spilt past its frame on a laptop and hid Total: the
  // optional columns wait for the room.
  salesType: { width: "sm", hideBelow: "3xl" },
  owner: { width: "fill", hideBelow: "lg" },
  sentAt: { width: "sm", hideBelow: "2xl" },
  validUntil: { width: "sm", hideBelow: "3xl" },
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
