"use client";

import Link from "next/link";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import {
  createDataTableColumnHelper,
  createSelectionColumn,
} from "@/components/patterns/data-table";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { LEAD_COLUMN_META } from "@/features/leads/lib/lead-table-layout";
import { LookupName } from "@/features/lookups/components/lookup-name";
import { EMPTY_VALUE, formatInrCompact } from "@/lib/format";

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
 * A column the backend does not supply yet. The column stays so the table keeps its shape
 * once the data arrives. TODO(LEAD-001): crops, win probability, weekly activity and the
 * next follow-up are requested from the backend (Docs/Frontend-Scope.md §10).
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
  columnHelper.display({
    id: "crops",
    header: "Crops",
    cell: () => <NotRecorded />,
    meta: LEAD_COLUMN_META.crops,
  }),
  columnHelper.display({
    id: "winProbability",
    header: "Probability",
    cell: () => <NotRecorded />,
    meta: LEAD_COLUMN_META.winProbability,
  }),
  columnHelper.display({
    id: "engagement",
    header: "Activity",
    cell: () => <NotRecorded />,
    meta: LEAD_COLUMN_META.engagement,
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
    cell: ({ getValue }) => <span className="font-medium">{formatInrCompact(getValue())}</span>,
    meta: LEAD_COLUMN_META.estimatedValue,
  }),
]);
