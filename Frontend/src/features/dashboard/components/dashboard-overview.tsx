"use client";

import {
  Clock01Icon,
  DashboardSquare02Icon,
  IndianRupeeIcon,
  Target02Icon,
  UserAdd01Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import { EmptyState } from "@/components/patterns/empty-state";
import { ProportionBar } from "@/components/patterns/proportion-bar";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { describeTrend } from "@/components/patterns/sparkline";
import { StatCard, StatCardSkeleton } from "@/components/patterns/stat-card";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { dashboardOverviewQueryOptions } from "@/features/dashboard/api/dashboard.queries";
import {
  figure,
  trendPoints,
  type DashboardKpi,
  type DashboardOverview as Overview,
} from "@/features/dashboard/api/dashboard.schemas";
import { LEAD_STAGE_LABELS } from "@/features/leads/lib/lead-labels";
import { EMPTY_VALUE, formatInrCompact, formatNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/** RPT-001 · Dashboard overview with all states handled by QueryView. */
export function DashboardOverview(): React.JSX.Element {
  const query = useQuery(dashboardOverviewQueryOptions());

  return (
    <QueryView
      query={query}
      pending={<DashboardOverviewSkeleton />}
      isEmpty={(data) => data.pipeline.every((stage) => stage.count === 0)}
      empty={
        <EmptyState
          icon={DashboardSquare02Icon}
          title="Nothing to report yet"
          description="The dashboard fills in as leads are captured in your territory."
          className="rounded-xl border border-dashed border-border"
        />
      }
    >
      {(data) => <DashboardContent data={data} />}
    </QueryView>
  );
}

/** The card's change and sparkline from a KPI: `undefined` when the backend has none. */
function kpiCardProps(kpi: DashboardKpi): { delta: number | undefined; trend: number[] } {
  return { delta: figure(kpi.deltaPercent) ?? undefined, trend: trendPoints(kpi.trend) };
}

function DashboardContent({ data }: { data: Overview }): React.JSX.Element {
  const { kpis } = data;
  const pipeline = kpiCardProps(kpis.pipelineValue);
  const newLeads = kpiCardProps(kpis.newLeads);
  const conversion = kpiCardProps(kpis.conversionRate);
  const overdue = kpiCardProps(kpis.overdueFollowUps);

  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Key figures" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Open pipeline"
          icon={IndianRupeeIcon}
          value={
            kpis.pipelineValue.value === null
              ? EMPTY_VALUE
              : formatInrCompact(kpis.pipelineValue.value)
          }
          delta={pipeline.delta}
          trend={pipeline.trend}
          trendLabel={describeTrend(pipeline.trend, "Pipeline value")}
          footnote="Open leads, now"
        />
        <StatCard
          label="New leads"
          icon={UserAdd01Icon}
          value={formatNumber(figure(kpis.newLeads.value))}
          delta={newLeads.delta}
          trend={newLeads.trend}
          trendLabel={describeTrend(newLeads.trend, "New leads")}
          footnote={data.periodLabel}
        />
        <StatCard
          label="Conversion rate"
          icon={Target02Icon}
          value={formatPercent(figure(kpis.conversionRate.value), 1)}
          delta={conversion.delta}
          trend={conversion.trend}
          trendLabel={describeTrend(conversion.trend, "Conversion rate")}
          footnote="Of the period's new leads, won now"
        />
        <StatCard
          label="Overdue follow-ups"
          icon={Clock01Icon}
          value={formatNumber(figure(kpis.overdueFollowUps.value))}
          delta={overdue.delta}
          increaseIsGood={false}
          trend={overdue.trend}
          trendLabel={describeTrend(overdue.trend, "Overdue follow-ups")}
          footnote="Open tasks past their due date"
        />
      </section>

      <div className="grid gap-4 lg:grid-cols-5">
        <PipelineCard pipeline={data.pipeline} className="lg:col-span-3" />
        <FollowUpsCard followUps={data.followUps} className="lg:col-span-2" />
      </div>

      <SourcesCard sources={data.sources} />
    </div>
  );
}

function PipelineCard({
  pipeline,
  className,
}: {
  pipeline: Overview["pipeline"];
  className?: string;
}): React.JSX.Element {
  const maxCount = Math.max(1, ...pipeline.map((stage) => stage.count));

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>Pipeline by stage</CardTitle>
          <CardDescription>Leads and estimated value in each stage</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-3">
          {pipeline.map((stage) => (
            <li key={stage.stage} className="grid grid-cols-[6.5rem_1fr_auto] items-center gap-3">
              <span className="truncate text-sm text-muted-foreground">
                {LEAD_STAGE_LABELS[stage.stage]}
              </span>
              <ProportionBar
                value={stage.count}
                max={maxCount}
                tone={
                  stage.stage === "won" ? "success" : stage.stage === "lost" ? "danger" : "primary"
                }
              />
              <span className="text-right text-sm whitespace-nowrap tabular-nums">
                <span className="font-medium text-foreground">{formatNumber(stage.count)}</span>
                <span className="ml-2 text-muted-foreground">{formatInrCompact(stage.value)}</span>
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function FollowUpsCard({
  followUps,
  className,
}: {
  followUps: Overview["followUps"];
  className?: string;
}): React.JSX.Element {
  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>Follow-ups due</CardTitle>
          <CardDescription>Soonest first</CardDescription>
        </div>
        <Link
          href="/leads"
          transitionTypes={["nav-forward"]}
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          All leads
        </Link>
      </CardHeader>
      <CardContent className="px-2 pb-2">
        {followUps.length === 0 ? (
          <p className="px-3 py-8 text-center text-sm text-muted-foreground">
            No follow-ups scheduled.
          </p>
        ) : (
          <ul className="flex flex-col">
            {followUps.map((item) => (
              <li key={item.taskId}>
                <Link
                  href={`/leads/${item.leadId}`}
                  transitionTypes={["nav-forward"]}
                  className="flex items-center justify-between gap-3 rounded-md px-3 py-2.5 focus-ring-inset transition-colors duration-fast hover:bg-accent"
                >
                  <AvatarLabel
                    name={item.customerName}
                    secondary={[item.district, item.ownerName ?? "Unassigned"]
                      .filter((part) => part !== null)
                      .join(" · ")}
                  />
                  <span className="flex shrink-0 flex-col items-end gap-0.5">
                    <RelativeDate value={item.dueAt} highlightOverdue className="text-xs" />
                    {item.overdue ? (
                      <span className="text-2xs font-medium text-danger">Overdue</span>
                    ) : null}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function SourcesCard({ sources }: { sources: Overview["sources"] }): React.JSX.Element {
  const total = sources.reduce((sum, item) => sum + item.count, 0);
  const maxCount = Math.max(1, ...sources.map((item) => item.count));

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>Lead sources</CardTitle>
          <CardDescription>Where leads in your territory come from</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
          {sources.map((item) => (
            <li key={item.source} className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate text-muted-foreground">{item.name}</span>
                <span className="font-medium whitespace-nowrap text-foreground tabular-nums">
                  {formatNumber(item.count)}
                  <span className="ml-1.5 font-normal text-subtle-foreground">
                    {formatPercent(total === 0 ? 0 : (item.count / total) * 100)}
                  </span>
                </span>
              </div>
              <ProportionBar value={item.count} max={maxCount} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function CardSkeletonHeader({
  titleWidth,
  descriptionWidth,
}: {
  titleWidth: string;
  descriptionWidth: string;
}): React.JSX.Element {
  return (
    <CardHeader>
      <div className="flex flex-col gap-0.5">
        <Skeleton className={cn("h-6", titleWidth)} />
        <Skeleton className={cn("h-5", descriptionWidth)} />
      </div>
    </CardHeader>
  );
}

/** Mirrors DashboardContent: four KPI cards, pipeline + follow-ups, sources. */
export function DashboardOverviewSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading dashboard" className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <Card aria-hidden="true" className="lg:col-span-3">
          <CardSkeletonHeader titleWidth="w-36" descriptionWidth="w-60" />
          <CardContent>
            <div className="flex flex-col gap-3">
              {Array.from({ length: 7 }, (_, index) => (
                <div key={index} className="grid grid-cols-[6.5rem_1fr_auto] items-center gap-3">
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-2 w-full rounded-full" />
                  <Skeleton className="h-5 w-20" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card aria-hidden="true" className="lg:col-span-2">
          <CardSkeletonHeader titleWidth="w-32" descriptionWidth="w-24" />
          <CardContent className="px-2 pb-2">
            {Array.from({ length: 5 }, (_, index) => (
              <div key={index} className="flex items-center justify-between gap-3 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <Skeleton className="size-6 rounded-full" />
                  <div className="flex flex-col gap-1">
                    <Skeleton className="h-4 w-28" />
                    <Skeleton className="h-3 w-36" />
                  </div>
                </div>
                <Skeleton className="h-4 w-16" />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <Card aria-hidden="true">
        <CardSkeletonHeader titleWidth="w-28" descriptionWidth="w-64" />
        <CardContent>
          <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }, (_, index) => (
              <div key={index} className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <Skeleton className="h-5 w-24" />
                  <Skeleton className="h-5 w-14" />
                </div>
                <Skeleton className="h-2 w-full rounded-full" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
