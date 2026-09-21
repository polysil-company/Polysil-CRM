"use client";

import Link from "next/link";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import {
  createDataTableColumnHelper,
  createSelectionColumn,
} from "@/components/patterns/data-table";
import { RelativeDate } from "@/components/patterns/relative-date";
import { SegmentedMeter } from "@/components/patterns/segmented-meter";
import { describeTrend, Sparkline } from "@/components/patterns/sparkline";
import { TagList } from "@/components/patterns/tag";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { LEAD_SOURCE_LABELS } from "@/features/leads/lib/lead-labels";
import { LEAD_COLUMN_META } from "@/features/leads/lib/lead-table-layout";
import { formatInrCompact } from "@/lib/format";

import { LeadStatusBadge } from "./lead-status-badge";

const columnHelper = createDataTableColumnHelper<Lead>();

function LeadNameCell({ lead }: { lead: Lead }): React.JSX.Element {
  return (
    <Link
      href={`/leads/${lead.id}`}
      transitionTypes={["nav-forward"]}
      className="group/name flex min-w-0 flex-col rounded-sm focus-ring-inset"
    >
      <span className="truncate text-sm font-medium text-foreground underline-offset-4 group-hover/name:underline">
        {lead.customerName}
      </span>
      <span className="truncate text-xs text-muted-foreground">
        <span className="font-mono">{lead.code}</span> · {lead.village ? `${lead.village}, ` : ""}
        {lead.district}
      </span>
    </Link>
  );
}

/** Columns in display order. Widths and breakpoints come from LEAD_COLUMN_META (shared with the skeleton). */
export const leadColumns = columnHelper.columns([
  createSelectionColumn(columnHelper, (lead) => lead.customerName),
  columnHelper.accessor("customerName", {
    header: "Customer",
    cell: ({ row }) => <LeadNameCell lead={row.original} />,
    meta: LEAD_COLUMN_META.customerName,
  }),
  columnHelper.accessor("status", {
    header: "Status",
    enableSorting: false,
    cell: ({ getValue }) => <LeadStatusBadge status={getValue()} />,
    meta: LEAD_COLUMN_META.status,
  }),
  columnHelper.accessor("source", {
    header: "Source",
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="text-sm text-muted-foreground">{LEAD_SOURCE_LABELS[getValue()]}</span>
    ),
    meta: LEAD_COLUMN_META.source,
  }),
  columnHelper.accessor("crops", {
    header: "Crops",
    enableSorting: false,
    cell: ({ getValue }) => (
      <TagList items={getValue().map((crop) => ({ id: crop, label: crop }))} />
    ),
    meta: LEAD_COLUMN_META.crops,
  }),
  columnHelper.accessor("winProbability", {
    header: "Probability",
    cell: ({ getValue }) => <SegmentedMeter value={getValue()} label="Win probability" />,
    meta: LEAD_COLUMN_META.winProbability,
  }),
  columnHelper.accessor("engagement", {
    header: "Activity",
    enableSorting: false,
    cell: ({ getValue }) => (
      <Sparkline values={getValue()} label={describeTrend(getValue(), "Interactions per week")} />
    ),
    meta: LEAD_COLUMN_META.engagement,
  }),
  columnHelper.accessor((lead) => lead.owner.name, {
    id: "owner",
    header: "Owner",
    enableSorting: false,
    cell: ({ row }) => (
      <AvatarLabel
        name={row.original.owner.name}
        imageUrl={row.original.owner.avatarUrl}
        size="xs"
      />
    ),
    meta: LEAD_COLUMN_META.owner,
  }),
  columnHelper.accessor("followUpAt", {
    header: "Follow-up",
    cell: ({ getValue }) => <RelativeDate value={getValue()} highlightOverdue />,
    meta: LEAD_COLUMN_META.followUpAt,
  }),
  columnHelper.accessor("estimatedValue", {
    header: "Value",
    cell: ({ getValue }) => <span className="font-medium">{formatInrCompact(getValue())}</span>,
    meta: LEAD_COLUMN_META.estimatedValue,
  }),
]);
