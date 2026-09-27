"use client";

import Link from "next/link";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import { createDataTableColumnHelper } from "@/components/patterns/data-table";
import { Badge } from "@/components/ui/badge";
import type { QuotationSummary } from "@/features/quotations/api/quotations.schemas";
import { SALES_TYPE_LABELS, quotationTitle } from "@/features/quotations/lib/quotation-labels";
import { QUOTATION_COLUMN_META } from "@/features/quotations/lib/quotation-table-layout";
import {
  EMPTY_VALUE,
  formatDate,
  formatFullDate,
  formatIndianPhone,
  formatInr,
} from "@/lib/format";
import { cn } from "@/lib/utils";

import { QuotationStatusBadge } from "./quotation-status-badge";

const columnHelper = createDataTableColumnHelper<QuotationSummary>();

function NumberCell({ quotation }: { quotation: QuotationSummary }): React.JSX.Element {
  const superseded = quotation.supersededBy !== null;
  return (
    <Link
      href={`/quotations/${quotation.id}`}
      transitionTypes={["nav-forward"]}
      className="group/number flex min-w-0 flex-col gap-0.5 rounded-sm focus-ring-inset"
    >
      <span
        className={cn(
          "truncate font-mono text-sm font-medium text-foreground underline-offset-4 group-hover/number:underline",
          superseded && "text-muted-foreground",
        )}
      >
        {quotationTitle(quotation)}
      </span>
      <span className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
        {quotation.lead === null ? (
          "Lead not visible"
        ) : (
          <span className="font-mono">{quotation.lead.code}</span>
        )}
        {superseded ? (
          <Badge variant="outline" size="sm">
            Superseded by v{quotation.supersededBy?.version}
          </Badge>
        ) : null}
      </span>
    </Link>
  );
}

/** Columns in display order. Widths and breakpoints come from QUOTATION_COLUMN_META. */
export const quotationColumns = columnHelper.columns([
  columnHelper.accessor("quoteNo", {
    id: "number",
    header: "Quotation",
    enableSorting: false,
    cell: ({ row }) => <NumberCell quotation={row.original} />,
    meta: QUOTATION_COLUMN_META.number,
  }),
  columnHelper.accessor("partyName", {
    id: "party",
    header: "Party",
    enableSorting: false,
    cell: ({ row }) => (
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-sm text-foreground">{row.original.partyName}</span>
        <span className="truncate text-xs text-muted-foreground">
          {row.original.partyMobile === ""
            ? EMPTY_VALUE
            : formatIndianPhone(row.original.partyMobile)}
        </span>
      </span>
    ),
    meta: QUOTATION_COLUMN_META.party,
  }),
  columnHelper.accessor("status", {
    header: "Status",
    enableSorting: false,
    cell: ({ getValue }) => <QuotationStatusBadge status={getValue()} />,
    meta: QUOTATION_COLUMN_META.status,
  }),
  columnHelper.accessor("salesType", {
    header: "Type",
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="text-sm text-muted-foreground">{SALES_TYPE_LABELS[getValue()]}</span>
    ),
    meta: QUOTATION_COLUMN_META.salesType,
  }),
  columnHelper.accessor((quotation) => quotation.owner?.name ?? null, {
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
    meta: QUOTATION_COLUMN_META.owner,
  }),
  columnHelper.accessor("sentAt", {
    header: "Sent",
    enableSorting: false,
    cell: ({ getValue }) => {
      const sentAt = getValue();
      return (
        <span className="text-sm text-muted-foreground">
          {sentAt === null ? "Not sent" : formatDate(sentAt)}
        </span>
      );
    },
    meta: QUOTATION_COLUMN_META.sentAt,
  }),
  columnHelper.accessor("validUntil", {
    header: "Valid until",
    enableSorting: false,
    cell: ({ getValue }) => {
      const validUntil = getValue();
      return (
        <span className="text-sm text-muted-foreground">
          {validUntil === null ? EMPTY_VALUE : formatFullDate(validUntil)}
        </span>
      );
    },
    meta: QUOTATION_COLUMN_META.validUntil,
  }),
  columnHelper.accessor((quotation) => quotation.totals.total, {
    id: "total",
    header: "Total",
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="font-medium tabular-nums">{formatInr(getValue())}</span>
    ),
    meta: QUOTATION_COLUMN_META.total,
  }),
]);
