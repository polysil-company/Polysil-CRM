"use client";

import Link from "next/link";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import {
  createDataTableColumnHelper,
  createSelectionColumn,
} from "@/components/patterns/data-table";
import { TagList, toneForLabel } from "@/components/patterns/tag";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { LEAD_COLUMN_META } from "@/features/leads/lib/lead-table-layout";
import { LookupName } from "@/features/lookups/components/lookup-name";
import { EMPTY_VALUE, formatInr } from "@/lib/format";

import { LeadStageBadge } from "./lead-stage-badge";

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
        {lead.territory.name}
      </span>
    </Link>
  );
}

/**
 * A column the backend does not supply on the list. TODO(TASK-001): a lead's next follow-up
 * is a task (BE-002); it shows here once the tasks module is connected.
 */
function NotRecorded(): React.JSX.Element {
  return <span className="text-sm text-subtle-foreground">{EMPTY_VALUE}</span>;
}

/**
 * Whether the backend sorts `GET /leads`. It does not yet (BE-001), and an arrow that changes
 * nothing tells the user the list is sorted when it is not — so no column offers one.
 * TODO(LEAD-001): set to true once BE-001 is done; the sort already travels in the URL and the
 * request.
 */
const BACKEND_SORTS_LEADS = false;

/** Columns in display order. Widths and breakpoints come from LEAD_COLUMN_META (shared with the skeleton). */
export const leadColumns = columnHelper.columns([
  createSelectionColumn(columnHelper, (lead) => lead.customerName),
  columnHelper.accessor("customerName", {
    header: "Customer",
    enableSorting: BACKEND_SORTS_LEADS,
    cell: ({ row }) => <LeadNameCell lead={row.original} />,
    meta: LEAD_COLUMN_META.customerName,
  }),
  columnHelper.accessor("stage", {
    header: "Stage",
    enableSorting: false,
    cell: ({ getValue }) => <LeadStageBadge stage={getValue()} />,
    meta: LEAD_COLUMN_META.stage,
  }),
  columnHelper.accessor("source", {
    header: "Source",
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="text-sm text-muted-foreground">
        <LookupName list="lead-sources" code={getValue()} />
      </span>
    ),
    meta: LEAD_COLUMN_META.source,
  }),
  columnHelper.accessor("crops", {
    header: "Crops",
    enableSorting: false,
    cell: ({ getValue }) => {
      const crops = getValue();
      return crops.length === 0 ? (
        <NotRecorded />
      ) : (
        <TagList
          max={2}
          items={crops.map((crop) => ({
            id: crop.code,
            label: crop.name,
            tone: toneForLabel(crop.name),
          }))}
        />
      );
    },
    meta: LEAD_COLUMN_META.crops,
  }),
  columnHelper.accessor((lead) => lead.owner?.name ?? null, {
    id: "owner",
    header: "Owner",
    enableSorting: false,
    cell: ({ getValue }) => {
      const name = getValue();
      return name === null ? (
        <span className="text-sm text-muted-foreground">Unassigned</span>
      ) : (
        <AvatarLabel name={name} size="xs" />
      );
    },
    meta: LEAD_COLUMN_META.owner,
  }),
  columnHelper.display({
    id: "followUpAt",
    header: "Follow-up",
    cell: () => <NotRecorded />,
    meta: LEAD_COLUMN_META.followUpAt,
  }),
  columnHelper.accessor("estimatedValue", {
    header: "Value",
    enableSorting: BACKEND_SORTS_LEADS,
    // Whole rupees in every row, so a column never mixes "₹69,910" with "₹2.41 L".
    cell: ({ getValue }) => <span className="font-medium">{formatInr(getValue())}</span>,
    meta: LEAD_COLUMN_META.estimatedValue,
  }),
]);
