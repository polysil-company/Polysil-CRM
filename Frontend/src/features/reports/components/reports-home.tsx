"use client";

import { Analytics01Icon, ArrowRight01Icon } from "@hugeicons/core-free-icons";
import { useQueries, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { reportQueryOptions } from "@/features/reports/api/reports.queries";
import {
  REPORT_NAMES,
  type ReportData,
  type ReportName,
  type ReportParams,
} from "@/features/reports/api/reports.schemas";
import { REPORTS } from "@/features/reports/lib/report-catalogue";
import { isApiError } from "@/lib/api/errors";
import { formatInrCompact, formatNumber } from "@/lib/format";

import { formatPct } from "./report-table";

/** The home page asks each report for its default window: the last 30 days. */
const DEFAULTS: ReportParams = {
  from: null,
  to: null,
  territories: [],
  owner: null,
  groupBy: null,
};

function forbidden(error: unknown): boolean {
  return isApiError(error) && error.status === 403;
}

/** A report's own page; its name is one segment. */
function reportHref(name: string): `/reports/${string}` {
  return `/reports/${name}`;
}

interface Figure {
  readonly value: string;
  readonly note: string;
}

function plural(count: number, one: string, many: string): string {
  return `${formatNumber(count)} ${count === 1 ? one : many}`;
}

/** Each report's figure for its card, and a line under it. */
const HEADLINES: { readonly [N in ReportName]: (data: ReportData<N>) => Figure } = {
  "lead-conversion": (data) => ({
    value: `${formatPct(data.totals.conversionPct)} converted`,
    note: `${formatNumber(data.totals.won)} won of ${plural(data.totals.leads, "lead", "leads")}`,
  }),
  "salesperson-performance": (data) => ({
    value: `${formatNumber(data.totals.leadsWon)} won`,
    note: `${plural(data.totals.leadsCreated, "lead", "leads")} across ${plural(data.rows.length, "person", "people")}`,
  }),
  "lost-leads": (data) => {
    const top = data.rows[0];
    return {
      value: `${formatNumber(data.totals.lost)} lost`,
      note:
        top === undefined
          ? "None lost"
          : `Most often: ${top.key.label} (${formatPct(top.sharePct)})`,
    };
  },
  "follow-ups": (data) => ({
    value: `${formatNumber(
      data.totals.overdue1to2 +
        data.totals.overdue3to7 +
        data.totals.overdue8to30 +
        data.totals.overdue31Plus,
    )} overdue`,
    note: `${formatNumber(data.totals.dueToday)} due today, as of now`,
  }),
  "dealer-performance": (data) => ({
    value: formatInrCompact(data.totals.orderValue),
    note: `${plural(data.totals.orders, "order", "orders")} from ${plural(data.rows.length, "dealer", "dealers")}`,
  }),
  "campaign-performance": (data) => ({
    value: plural(data.totals.leads, "lead", "leads"),
    note: `${formatNumber(data.totals.won)} won, from ${plural(data.rows.length, "campaign", "campaigns")}`,
  }),
  "territory-performance": (data) => ({
    value: plural(data.totals.leads, "lead", "leads"),
    note: `${formatNumber(data.totals.won)} won, in ${plural(data.rows.length, "district", "districts")}`,
  }),
  complaints: (data) => ({
    value: plural(data.totals.count, "complaint", "complaints"),
    note: `${formatNumber(data.totals.resolved)} resolved`,
  }),
};

/**
 * RPT-002 · Reports home: a card per report the user may open, with its headline over the
 * last 30 days. A report that answers 403 is left out, as the handover asks.
 */
export function ReportsHome(): React.JSX.Element {
  const results = useQueries({
    queries: REPORT_NAMES.map((name) => reportQueryOptions(name, DEFAULTS)),
  });
  if (results.length > 0 && results.every((result) => forbidden(result.error))) {
    return (
      <EmptyState
        icon={Analytics01Icon}
        title="No reports for your role"
        description="Ask an administrator if you need one."
        className="rounded-xl border border-dashed border-border"
      />
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-prose text-sm text-muted-foreground">
        Every figure counts only what you may see. The cards show the last 30 days; open one for its
        filters and its Excel file.
      </p>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {REPORT_NAMES.map((name) => (
          <ReportCard key={name} name={name} />
        ))}
      </ul>
    </div>
  );
}

function ReportCard<N extends ReportName>({ name }: { name: N }): React.JSX.Element | null {
  const query = useQuery(reportQueryOptions(name, DEFAULTS));
  const entry = REPORTS[name];
  if (forbidden(query.error)) return null;
  const figure = query.data === undefined ? null : HEADLINES[name](query.data);
  return (
    <li className="flex">
      <Card className="relative flex w-full flex-col gap-3 p-4 transition-colors duration-fast ease-out hover:bg-muted/40">
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-base font-semibold text-foreground">
            <Link
              href={reportHref(name)}
              className="after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none"
            >
              {entry.title}
            </Link>
          </h2>
          <Icon icon={ArrowRight01Icon} className="mt-0.5 text-muted-foreground" />
        </div>
        <p className="text-sm text-muted-foreground">{entry.description}</p>
        <div className="mt-auto flex flex-col gap-0.5">
          {query.status === "pending" ? (
            <>
              <Skeleton className="h-7 w-24" />
              <Skeleton className="h-4 w-40" />
            </>
          ) : figure === null ? (
            <span className="text-xs text-muted-foreground">
              The figures couldn&apos;t be loaded. Open it to try again.
            </span>
          ) : (
            <>
              <span className="text-2xl font-semibold text-foreground tabular-nums">
                {figure.value}
              </span>
              <span className="text-xs text-muted-foreground">{figure.note}</span>
            </>
          )}
        </div>
      </Card>
    </li>
  );
}
