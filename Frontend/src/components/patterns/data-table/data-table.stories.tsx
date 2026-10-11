import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import type { PaginationState, RowSelectionState, SortingState } from "@tanstack/react-table";
import { useState } from "react";
import type * as React from "react";

import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { formatInr } from "@/lib/format";

import { DataTable } from "./data-table";
import { DataTableSkeleton } from "./data-table-skeleton";
import { SelectionBar } from "./selection-bar";
import { createSelectionColumn } from "./selection-column";
import { createDataTableColumnHelper, type DataTableColumnMeta } from "./table-features";

type PartnerType = "Distributor" | "Dealer" | "Sub-dealer";
type PartnerStatus = "active" | "onboarding" | "paused";

interface ChannelPartner {
  readonly id: string;
  readonly name: string;
  readonly district: string;
  readonly type: PartnerType;
  readonly status: PartnerStatus;
  readonly outstanding: number;
}

const NAMES = [
  "Shree Krishna Agro",
  "Patel Irrigation",
  "Kisan Seva Kendra",
  "Narmada Drip Store",
  "Sardar Agri Traders",
  "Jay Ambe Krishi",
  "Mahi Farm Solutions",
  "Om Sai Pipes",
] as const;
const DISTRICTS = ["Vadodara", "Anand", "Kheda", "Bharuch", "Panchmahal", "Surat"] as const;
const TYPES: readonly PartnerType[] = ["Distributor", "Dealer", "Sub-dealer"];
const STATUSES: readonly PartnerStatus[] = ["active", "active", "onboarding", "active", "paused"];

/** Deterministic sample data — the same rows on every render and in every screenshot. */
const PARTNERS: readonly ChannelPartner[] = Array.from({ length: 64 }, (_, index) => ({
  id: `partner-${index + 1}`,
  name: `${NAMES[index % NAMES.length] ?? "Partner"} ${Math.floor(index / NAMES.length) + 1}`,
  district: DISTRICTS[(index * 5) % DISTRICTS.length] ?? "Vadodara",
  type: TYPES[index % TYPES.length] ?? "Dealer",
  status: STATUSES[(index * 3) % STATUSES.length] ?? "active",
  outstanding: 25_000 + ((index * 7_919) % 90) * 5_000,
}));

const STATUS_BADGES: Readonly<Record<PartnerStatus, { label: string; variant: BadgeVariant }>> = {
  active: { label: "Active", variant: "success" },
  onboarding: { label: "Onboarding", variant: "info" },
  paused: { label: "Paused", variant: "neutral" },
};

const helper = createDataTableColumnHelper<ChannelPartner>();

const columns = helper.columns([
  createSelectionColumn(helper, (partner) => partner.name),
  helper.accessor("name", {
    header: "Channel partner",
    meta: { isRowHeader: true, width: "fill" },
  }),
  helper.accessor("type", { header: "Type", meta: { width: "sm", hideBelow: "md" } }),
  helper.accessor("district", { header: "District", meta: { width: "sm", hideBelow: "sm" } }),
  helper.accessor("status", {
    header: "Status",
    enableSorting: false,
    meta: { width: "sm" },
    cell: (info) => {
      const badge = STATUS_BADGES[info.getValue()];
      return (
        <Badge dot variant={badge.variant}>
          {badge.label}
        </Badge>
      );
    },
  }),
  helper.accessor("outstanding", {
    header: "Outstanding",
    meta: { align: "end", width: "md" },
    cell: (info) => formatInr(info.getValue()),
  }),
]);

/** Same widths and breakpoints as `columns`, for the loading state. */
const SKELETON_COLUMNS: readonly DataTableColumnMeta[] = [
  { width: "checkbox" },
  { isRowHeader: true, width: "fill" },
  { width: "sm", hideBelow: "md" },
  { width: "sm", hideBelow: "sm" },
  { width: "sm" },
  { align: "end", width: "md" },
];

function textFor(partner: ChannelPartner, columnId: string): string {
  switch (columnId) {
    case "type":
      return partner.type;
    case "district":
      return partner.district;
    default:
      return partner.name;
  }
}

/** The app sorts on the server; the story stands in for the API. */
function sortPartners(rows: readonly ChannelPartner[], sorting: SortingState): ChannelPartner[] {
  const [rule] = sorting;
  if (rule === undefined) {
    return [...rows];
  }
  const direction = rule.desc ? -1 : 1;
  return [...rows].sort((a, b) => {
    if (rule.id === "outstanding") {
      return (a.outstanding - b.outstanding) * direction;
    }
    const left = textFor(a, rule.id);
    const right = textFor(b, rule.id);
    if (left === right) {
      return 0;
    }
    return (left < right ? -1 : 1) * direction;
  });
}

function ChannelPartnersTable({
  rows,
  isFetching = false,
  isPaging = false,
}: {
  rows: readonly ChannelPartner[];
  isFetching?: boolean;
  isPaging?: boolean;
}): React.JSX.Element {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const start = pagination.pageIndex * pagination.pageSize;
  const page = sortPartners(rows, sorting).slice(start, start + pagination.pageSize);
  const selected = rows.filter((partner) => rowSelection[partner.id] === true);
  const outstanding = selected.reduce((total, partner) => total + partner.outstanding, 0);

  return (
    <>
      <div className="flex h-150 w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-border bg-card">
        <DataTable
          label="Channel partners"
          columns={columns}
          data={page}
          getRowId={(partner) => partner.id}
          rowCount={rows.length}
          sorting={sorting}
          onSortingChange={(next) => {
            setSorting(next);
            setPagination((current) => ({ ...current, pageIndex: 0 }));
          }}
          pagination={pagination}
          onPaginationChange={setPagination}
          rowSelection={rowSelection}
          onRowSelectionChange={setRowSelection}
          isFetching={isFetching}
          isPaging={isPaging}
          className="min-h-0 flex-1"
        />
      </div>
      <SelectionBar
        count={selected.length}
        summary={`${formatInr(outstanding)} outstanding`}
        onClear={() => {
          setRowSelection({});
        }}
      />
    </>
  );
}

const meta = {
  title: "Patterns/DataTable",
  parameters: { layout: "padded" },
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/**
 * Sort by a header, select rows (the floating bar sums what you picked) and
 * page through. Narrow the canvas: Type and District hide on small screens.
 */
export const Default: Story = {
  render: () => <ChannelPartnersTable rows={PARTNERS} />,
};

/** A background refetch: rows stay readable while the progress line runs. */
export const Refreshing: Story = {
  render: () => <ChannelPartnersTable rows={PARTNERS} isFetching />,
};

/**
 * A page change that has not landed: the rows still belong to the previous page, so both
 * paging buttons wait rather than reading the next click against the wrong page.
 */
export const Paging: Story = {
  render: () => <ChannelPartnersTable rows={PARTNERS} isFetching isPaging />,
};

export const SinglePage: Story = {
  render: () => <ChannelPartnersTable rows={PARTNERS.slice(0, 6)} />,
};

/** Built from the same cell classes as the table, so the swap to real rows does not move anything. */
export const Loading: Story = {
  render: () => (
    <div className="flex h-150 w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-border bg-card">
      <DataTableSkeleton
        label="Channel partners"
        columns={SKELETON_COLUMNS}
        checkboxColumn={0}
        className="min-h-0 flex-1"
      />
    </div>
  ),
};
