import type { DataTableColumnMeta } from "@/components/patterns/data-table";

/**
 * Single source for the leads table layout, shared by the real columns and
 * the loading skeleton — so the skeleton always matches the table.
 * Plain module (no "use client") so route loading files can import it.
 *
 * The three text columns are `fill`: on a large monitor they share the leftover width
 * instead of one of them holding it all. Their floors match the fixed widths they had, so
 * nothing changes on a laptop, where there is no width to spare.
 */
export const LEAD_COLUMN_META = {
  select: { width: "checkbox" },
  customerName: { width: "fill", isRowHeader: true },
  status: { width: "sm" },
  source: { width: "sm", hideBelow: "lg" },
  crops: { width: "fill", hideBelow: "xl" },
  winProbability: { width: "md", hideBelow: "md" },
  engagement: { width: "md", hideBelow: "xl" },
  owner: { width: "fill", hideBelow: "lg" },
  followUpAt: { width: "sm", hideBelow: "sm" },
  estimatedValue: { width: "sm", align: "end" },
} as const satisfies Record<string, DataTableColumnMeta>;

const COLUMN_ORDER = [
  "select",
  "customerName",
  "status",
  "source",
  "crops",
  "winProbability",
  "engagement",
  "owner",
  "followUpAt",
  "estimatedValue",
] as const;

export const LEAD_COLUMN_LAYOUT: readonly DataTableColumnMeta[] = COLUMN_ORDER.map(
  (id) => LEAD_COLUMN_META[id],
);

export const LEADS_TABLE_LABEL = "Leads";

/** Frame around the table, its skeleton and its empty states. */
export const LEADS_TABLE_FRAME_CLASSES =
  "min-h-80 flex-1 overflow-hidden rounded-xl border border-border lg:min-h-0";

export const LEADS_EMPTY_FRAME_CLASSES =
  "min-h-80 flex-1 rounded-xl border border-dashed border-border";
