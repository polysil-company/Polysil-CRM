"use client";

import { Analytics01Icon, SquareLock02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Notice } from "@/components/patterns/notice";
import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import {
  COMPLAINT_STATUS_LABELS,
  SEVERITY_LABELS,
} from "@/features/complaints/lib/complaint-labels";
import { LEAD_STAGE_LABELS } from "@/features/leads/lib/lead-labels";
import { reportQueryOptions } from "@/features/reports/api/reports.queries";
import {
  REPORT_ROW_CAP,
  type ReportData,
  type ReportName,
  type ReportParams,
} from "@/features/reports/api/reports.schemas";
import { REPORTS, saleModeLabel } from "@/features/reports/lib/report-catalogue";
import { isApiError } from "@/lib/api/errors";
import {
  formatCalendarDay,
  formatDate,
  formatDateTime,
  formatInr,
  formatNumber,
} from "@/lib/format";

import {
  countCell,
  formatPct,
  moneyCell,
  NotAvailable,
  ReportTable,
  ReportTableSkeleton,
} from "./report-table";

/**
 * RPT-002 · One report's figures: the window and sale setting they used, a notice when only
 * the first 1,000 rows came back, then its table. A report the user may not run (403) says so.
 */
function ReportFrame<N extends ReportName>({
  name,
  params,
  hidden,
  children,
}: {
  name: N;
  params: ReportParams;
  /** True when some figure on a row is null: not available to this user. */
  hidden: (data: ReportData<N>) => boolean;
  children: (data: ReportData<N>) => React.ReactNode;
}): React.JSX.Element {
  const query = useQuery(reportQueryOptions(name, params));
  const entry = REPORTS[name];
  return (
    <QueryView
      query={query}
      pending={<ReportTableSkeleton label={`Loading ${entry.title.toLowerCase()}`} />}
      isEmpty={(data) => data.rows.length === 0}
      empty={
        <EmptyState
          icon={Analytics01Icon}
          title="Nothing to report"
          description={
            entry.dates
              ? "Nothing in this window. Try a longer window, or fewer filters."
              : "No one has an open task that is due."
          }
          className="rounded-xl border border-dashed border-border"
        />
      }
      renderError={(error, retry) =>
        isApiError(error) && error.status === 403 ? (
          <EmptyState
            icon={SquareLock02Icon}
            title="You can't run this report"
            description="It needs access your role doesn't have. Ask an administrator if you need it."
            className="rounded-xl border border-dashed border-border"
          />
        ) : (
          <ErrorState error={error} onRetry={retry} />
        )
      }
    >
      {(data) => (
        <div className="flex flex-col gap-3">
          <p className="text-xs text-muted-foreground">
            {data.filters.asOf !== null
              ? `As of ${formatDateTime(data.filters.asOf)}.`
              : data.filters.from !== null && data.filters.to !== null
                ? `${formatCalendarDay(data.filters.from)} to ${formatCalendarDay(data.filters.to)}.`
                : null}
            {entry.sales && data.filters.saleCountedAt !== null
              ? ` Sales counted at: ${saleModeLabel(data.filters.saleCountedAt)}.`
              : null}
          </p>
          {data.truncated ? (
            <Notice tone="info">
              Only the first {formatNumber(REPORT_ROW_CAP)} rows are shown. The totals count them
              all, and so does the Excel file&apos;s note.
            </Notice>
          ) : null}
          {children(data)}
          {hidden(data) ? (
            <p className="text-xs text-muted-foreground">
              A dash is a figure your role doesn&apos;t see.
            </p>
          ) : null}
        </div>
      )}
    </QueryView>
  );
}

// ── lead conversion ─────────────────────────────────────────────────────────────

const CONVERSION_GROUP: Readonly<Record<string, string>> = {
  source: "Source",
  owner: "Person",
  territory: "Territory",
};

function ConversionReport({ params }: { params: ReportParams }): React.JSX.Element {
  const header = CONVERSION_GROUP[params.groupBy ?? "source"] ?? "Group";
  return (
    <ReportFrame name="lead-conversion" params={params} hidden={() => false}>
      {(data) => (
        <ReportTable
          caption={`Lead conversion by ${header.toLowerCase()}`}
          rows={data.rows}
          rowKey={(row, index) => row.key.id ?? `none-${String(index)}`}
          rowHeader={{ id: "key", header, cell: (row) => row.key.label }}
          columns={[
            {
              id: "leads",
              header: "Leads",
              cell: (row) => formatNumber(row.leads),
              total: formatNumber(data.totals.leads),
            },
            {
              id: "contacted",
              header: "Contacted",
              cell: (row) => formatNumber(row.contacted),
              wide: true,
            },
            {
              id: "qualified",
              header: "Qualified",
              cell: (row) => formatNumber(row.qualified),
              wide: true,
            },
            { id: "quoted", header: "Quoted", cell: (row) => formatNumber(row.quoted), wide: true },
            {
              id: "won",
              header: "Won",
              cell: (row) => formatNumber(row.won),
              total: formatNumber(data.totals.won),
            },
            { id: "lost", header: "Lost", cell: (row) => formatNumber(row.lost), wide: true },
            { id: "open", header: "Open", cell: (row) => formatNumber(row.open), wide: true },
            {
              id: "conversion",
              header: "Converted",
              cell: (row) => formatPct(row.conversionPct),
              total: formatPct(data.totals.conversionPct),
            },
          ]}
        />
      )}
    </ReportFrame>
  );
}

// ── salesperson performance ─────────────────────────────────────────────────────

function SalespersonReport({ params }: { params: ReportParams }): React.JSX.Element {
  return (
    <ReportFrame
      name="salesperson-performance"
      params={params}
      hidden={(data) =>
        data.rows.some(
          (row) =>
            row.quotationsSent === null ||
            row.orders === null ||
            row.visits === null ||
            row.tasksDone === null,
        )
      }
    >
      {(data) => (
        <ReportTable
          caption="Salesperson performance"
          rows={data.rows}
          rowKey={(row, index) => row.user.id ?? `none-${String(index)}`}
          rowHeader={{ id: "user", header: "Person", cell: (row) => row.user.name }}
          columns={[
            {
              id: "created",
              header: "Leads",
              cell: (row) => formatNumber(row.leadsCreated),
              total: formatNumber(data.totals.leadsCreated),
            },
            {
              id: "won",
              header: "Won",
              cell: (row) => formatNumber(row.leadsWon),
              total: formatNumber(data.totals.leadsWon),
            },
            {
              id: "quotations",
              header: "Quotations sent",
              cell: (row) => countCell(row.quotationsSent),
              wide: true,
            },
            { id: "orders", header: "Orders", cell: (row) => countCell(row.orders), wide: true },
            { id: "value", header: "Order value", cell: (row) => moneyCell(row.orderValue) },
            { id: "visits", header: "Visits", cell: (row) => countCell(row.visits), wide: true },
            {
              id: "done",
              header: "Tasks done",
              cell: (row) => countCell(row.tasksDone),
              wide: true,
            },
            {
              id: "overdue",
              header: "Tasks overdue",
              cell: (row) => countCell(row.tasksOverdue),
              wide: true,
            },
          ]}
        />
      )}
    </ReportFrame>
  );
}

// ── lost leads ──────────────────────────────────────────────────────────────────

function stageLabel(stage: string): string {
  if (stage === "unknown") return "Not recorded";
  const labels: Readonly<Record<string, string>> = LEAD_STAGE_LABELS;
  return labels[stage] ?? stage;
}

/** "Quoted 4 · Qualified 2": where they dropped off, most first. */
function droppedOff(byStage: Readonly<Record<string, number>>): string {
  return Object.entries(byStage)
    .sort(([, left], [, right]) => right - left)
    .map(([stage, count]) => `${stageLabel(stage)} ${formatNumber(count)}`)
    .join(" · ");
}

function LostLeadsReport({ params }: { params: ReportParams }): React.JSX.Element {
  const header = params.groupBy === "owner" ? "Person" : "Reason";
  return (
    <ReportFrame name="lost-leads" params={params} hidden={() => false}>
      {(data) => (
        <ReportTable
          caption={`Lost leads by ${header.toLowerCase()}`}
          rows={data.rows}
          rowKey={(row, index) => row.key.id ?? `none-${String(index)}`}
          rowHeader={{ id: "key", header, cell: (row) => row.key.label }}
          columns={[
            {
              id: "count",
              header: "Lost",
              cell: (row) => formatNumber(row.count),
              total: formatNumber(data.totals.lost),
            },
            { id: "share", header: "Share", cell: (row) => formatPct(row.sharePct) },
            {
              id: "days",
              header: "Days to loss",
              cell: (row) =>
                row.avgDaysToLoss === null ? "—" : formatNumber(Number(row.avgDaysToLoss), 1),
              wide: true,
            },
            {
              id: "stage",
              header: "Dropped off at",
              cell: (row) => (
                <span className="text-xs text-muted-foreground">{droppedOff(row.byStage)}</span>
              ),
              wide: true,
            },
          ]}
        />
      )}
    </ReportFrame>
  );
}

// ── follow-ups ──────────────────────────────────────────────────────────────────

function FollowUpsReport({ params }: { params: ReportParams }): React.JSX.Element {
  return (
    <ReportFrame name="follow-ups" params={params} hidden={() => false}>
      {(data) => (
        <ReportTable
          caption="Open follow-ups by person"
          rows={data.rows}
          rowKey={(row, index) => row.user.id ?? `none-${String(index)}`}
          rowHeader={{ id: "user", header: "Person", cell: (row) => row.user.name }}
          columns={[
            {
              id: "today",
              header: "Due today",
              cell: (row) => formatNumber(row.dueToday),
              total: formatNumber(data.totals.dueToday),
            },
            {
              id: "1-2",
              header: "1–2 days late",
              cell: (row) => formatNumber(row.overdue1to2),
              total: formatNumber(data.totals.overdue1to2),
              wide: true,
            },
            {
              id: "3-7",
              header: "3–7 days",
              cell: (row) => formatNumber(row.overdue3to7),
              total: formatNumber(data.totals.overdue3to7),
              wide: true,
            },
            {
              id: "8-30",
              header: "8–30 days",
              cell: (row) => formatNumber(row.overdue8to30),
              total: formatNumber(data.totals.overdue8to30),
              wide: true,
            },
            {
              id: "31",
              header: "Over 30 days",
              cell: (row) => formatNumber(row.overdue31Plus),
              total: formatNumber(data.totals.overdue31Plus),
            },
            {
              id: "oldest",
              header: "Oldest due",
              cell: (row) => (row.oldestDueAt === null ? "—" : formatDate(row.oldestDueAt)),
            },
          ]}
        />
      )}
    </ReportFrame>
  );
}

// ── dealer performance ──────────────────────────────────────────────────────────

function DealerReport({ params }: { params: ReportParams }): React.JSX.Element {
  return (
    <ReportFrame
      name="dealer-performance"
      params={params}
      hidden={(data) =>
        data.rows.some(
          (row) => row.leadsAssigned === null || row.received === null || row.complaints === null,
        )
      }
    >
      {(data) => (
        <div className="flex flex-col gap-2">
          <ReportTable
            caption="Dealer performance"
            rows={data.rows}
            rowKey={(row) => row.partner.id}
            rowHeader={{
              id: "partner",
              header: "Dealer",
              cell: (row) => (
                <Link
                  href={`/partners/${row.partner.id}`}
                  className="underline-offset-4 hover:underline"
                >
                  {row.partner.name}
                </Link>
              ),
            }}
            columns={[
              {
                id: "orders",
                header: "Orders",
                cell: (row) => formatNumber(row.orders),
                total: formatNumber(data.totals.orders),
              },
              {
                id: "value",
                header: "Order value",
                cell: (row) => formatInr(row.orderValue),
                total: formatInr(data.totals.orderValue),
              },
              {
                id: "dispatched",
                header: "Shipped",
                cell: (row) => formatInr(row.dispatchedValue),
                wide: true,
              },
              {
                id: "leads",
                header: "Leads given",
                cell: (row) => countCell(row.leadsAssigned),
                wide: true,
              },
              {
                id: "received",
                header: "Received",
                cell: (row) => moneyCell(row.received),
                wide: true,
              },
              { id: "balance", header: "Balance", cell: (row) => moneyCell(row.balance) },
              {
                id: "complaints",
                header: "Complaints",
                cell: (row) => countCell(row.complaints),
                wide: true,
              },
            ]}
          />
          <p className="text-xs text-muted-foreground">
            Received and balance are all time, not just this window.
          </p>
        </div>
      )}
    </ReportFrame>
  );
}

// ── campaign performance ────────────────────────────────────────────────────────

function CampaignReport({ params }: { params: ReportParams }): React.JSX.Element {
  return (
    <ReportFrame
      name="campaign-performance"
      params={params}
      hidden={(data) => data.rows.some((row) => row.salesCount === null || row.cost === null)}
    >
      {(data) => (
        <ReportTable
          caption="Campaign performance"
          rows={data.rows}
          rowKey={(row) => row.campaign.id}
          rowHeader={{
            id: "campaign",
            header: "Campaign",
            cell: (row) => (
              <span className="flex flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-1.5">
                  {row.campaign.name}
                  {row.campaign.isActive ? null : <Badge variant="outline">Ended</Badge>}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatCalendarDay(row.campaign.startDate)}
                  {row.campaign.endDate === null || row.campaign.endDate === row.campaign.startDate
                    ? ""
                    : ` to ${formatCalendarDay(row.campaign.endDate)}`}
                </span>
              </span>
            ),
          }}
          columns={[
            {
              id: "leads",
              header: "Leads",
              cell: (row) => formatNumber(row.leads),
              total: formatNumber(data.totals.leads),
            },
            {
              id: "won",
              header: "Won",
              cell: (row) => formatNumber(row.won),
              total: formatNumber(data.totals.won),
            },
            {
              id: "conversion",
              header: "Converted",
              cell: (row) => formatPct(row.conversionPct),
              wide: true,
            },
            {
              id: "sales",
              header: "Sales",
              cell: (row) => moneyCell(row.salesValue),
              total: moneyCell(data.totals.salesValue),
            },
            {
              id: "cost",
              header: "Cost",
              cell: (row) => moneyCell(row.cost),
              total: moneyCell(data.totals.cost),
              wide: true,
            },
            {
              id: "per-lead",
              header: "Per lead",
              cell: (row) => (row.cost === null ? <NotAvailable /> : moneyOrDash(row.costPerLead)),
              wide: true,
            },
            {
              id: "per-won",
              header: "Per win",
              cell: (row) => (row.cost === null ? <NotAvailable /> : moneyOrDash(row.costPerWon)),
              wide: true,
            },
          ]}
        />
      )}
    </ReportFrame>
  );
}

/** A cost per lead or win: none when there were no leads or wins to divide by. */
function moneyOrDash(value: string | null): string {
  return value === null ? "—" : formatInr(value);
}

// ── territory performance ───────────────────────────────────────────────────────

function TerritoryReport({ params }: { params: ReportParams }): React.JSX.Element {
  const header = params.groupBy === "taluka" ? "Taluka" : "District";
  return (
    <ReportFrame
      name="territory-performance"
      params={params}
      hidden={(data) => data.rows.some((row) => row.orders === null)}
    >
      {(data) => (
        <ReportTable
          caption={`Performance by ${header.toLowerCase()}`}
          rows={data.rows}
          rowKey={(row, index) => row.territory.id ?? `above-${String(index)}`}
          rowHeader={{ id: "territory", header, cell: (row) => row.territory.name }}
          columns={[
            {
              id: "leads",
              header: "Leads",
              cell: (row) => formatNumber(row.leads),
              total: formatNumber(data.totals.leads),
            },
            {
              id: "won",
              header: "Won",
              cell: (row) => formatNumber(row.won),
              total: formatNumber(data.totals.won),
            },
            { id: "conversion", header: "Converted", cell: (row) => formatPct(row.conversionPct) },
            { id: "orders", header: "Orders", cell: (row) => countCell(row.orders), wide: true },
            { id: "value", header: "Order value", cell: (row) => moneyCell(row.orderValue) },
          ]}
        />
      )}
    </ReportFrame>
  );
}

// ── complaints ──────────────────────────────────────────────────────────────────

/** The backend sends a status or severity's code as its label; these read better. */
function complaintKeyLabel(groupBy: string | null, label: string): string {
  const labels: Readonly<Record<string, string>> =
    groupBy === "status" ? COMPLAINT_STATUS_LABELS : groupBy === "severity" ? SEVERITY_LABELS : {};
  return labels[label] ?? label;
}

const COMPLAINT_GROUP: Readonly<Record<string, string>> = {
  type: "Type",
  status: "Status",
  severity: "Severity",
};

function ComplaintsReport({ params }: { params: ReportParams }): React.JSX.Element {
  const header = COMPLAINT_GROUP[params.groupBy ?? "type"] ?? "Group";
  return (
    <ReportFrame name="complaints" params={params} hidden={() => false}>
      {(data) => (
        <div className="flex flex-col gap-2">
          <ReportTable
            caption={`Complaints by ${header.toLowerCase()}`}
            rows={data.rows}
            rowKey={(row, index) => row.key.id ?? `none-${String(index)}`}
            rowHeader={{
              id: "key",
              header,
              cell: (row) => complaintKeyLabel(params.groupBy, row.key.label),
            }}
            columns={[
              {
                id: "count",
                header: "Complaints",
                cell: (row) => formatNumber(row.count),
                total: formatNumber(data.totals.count),
              },
              {
                id: "resolved",
                header: "Resolved",
                cell: (row) => formatNumber(row.resolved),
                total: formatNumber(data.totals.resolved),
              },
              {
                id: "sla",
                header: "Within target",
                cell: (row) => formatPct(row.resolvedWithinSlaPct),
              },
              {
                id: "breaches",
                header: "Late responses",
                cell: (row) => formatNumber(row.responseBreaches),
                wide: true,
              },
            ]}
          />
          <p className="text-sm text-foreground">
            Refunds paid: {formatNumber(data.totals.refunds.count)},{" "}
            {formatInr(data.totals.refunds.amount)}.
          </p>
        </div>
      )}
    </ReportFrame>
  );
}

/** The body of a report, by name. */
export function ReportBody({
  name,
  params,
}: {
  name: ReportName;
  params: ReportParams;
}): React.JSX.Element {
  switch (name) {
    case "lead-conversion":
      return <ConversionReport params={params} />;
    case "salesperson-performance":
      return <SalespersonReport params={params} />;
    case "lost-leads":
      return <LostLeadsReport params={params} />;
    case "follow-ups":
      return <FollowUpsReport params={params} />;
    case "dealer-performance":
      return <DealerReport params={params} />;
    case "campaign-performance":
      return <CampaignReport params={params} />;
    case "territory-performance":
      return <TerritoryReport params={params} />;
    case "complaints":
      return <ComplaintsReport params={params} />;
  }
}
