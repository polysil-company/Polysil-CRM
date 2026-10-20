import type * as React from "react";

import { ProportionBar } from "@/components/patterns/proportion-bar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { amount, type DashboardOverview } from "@/features/dashboard/api/dashboard.schemas";
import { formatInrCompact, formatMonth, formatNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

type SystemArea = DashboardOverview["areaBySystem"][number];
type MonthTarget = NonNullable<DashboardOverview["targetsByMonth"]>[number];

function leadsLabel(count: number): string {
  return `${formatNumber(count)} ${count === 1 ? "lead" : "leads"}`;
}

/** Most land first; the backend sends name order, which hides the comparison. */
function byLand(systems: readonly SystemArea[]): SystemArea[] {
  return [...systems].sort(
    (a, b) =>
      amount(b.hectares) - amount(a.hectares) || b.leads - a.leads || a.name.localeCompare(b.name),
  );
}

/**
 * RPT-001 · Open and won leads now, by irrigation system, with their land (FS-052).
 * `wide` spreads the rows over columns when the card has the row to itself.
 */
export function AreaBySystemCard({
  systems,
  wide = false,
  className,
}: {
  systems: DashboardOverview["areaBySystem"];
  wide?: boolean;
  className?: string;
}): React.JSX.Element {
  const rows = byLand(systems);
  const maxHectares = Math.max(0, ...rows.map((row) => amount(row.hectares)));

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>Area by irrigation system</CardTitle>
          <CardDescription>Land on open and won leads, now</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No open or won leads yet.
          </p>
        ) : (
          <>
            <ul
              className={cn(
                "grid gap-x-6 gap-y-4",
                wide ? "sm:grid-cols-2 lg:grid-cols-3" : "sm:grid-cols-2 lg:grid-cols-1",
              )}
            >
              {rows.map((row) => (
                <li key={row.system} className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="truncate text-muted-foreground">{row.name}</span>
                    <span className="font-medium whitespace-nowrap text-foreground tabular-nums">
                      {formatNumber(amount(row.hectares), 1)} hectares
                      <span className="ml-1.5 font-normal text-subtle-foreground">
                        {leadsLabel(row.leads)}
                      </span>
                    </span>
                  </div>
                  <ProportionBar value={amount(row.hectares)} max={maxHectares} />
                </li>
              ))}
            </ul>
            {maxHectares === 0 ? (
              <p className="mt-4 text-xs text-muted-foreground">
                None of these leads has its land recorded yet.
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** "₹8.2 L of ₹12 L", with the share of the target, as far as the role may see. */
function MonthFigures({ month }: { month: MonthTarget }): React.JSX.Element {
  const target = amount(month.target);
  if (month.achieved === null) {
    return <>{target > 0 ? `Target ${formatInrCompact(month.target)}` : "No target"}</>;
  }
  if (target === 0) {
    return (
      <>
        {formatInrCompact(month.achieved)}
        <span className="ml-1.5 font-normal text-subtle-foreground">no target</span>
      </>
    );
  }
  return (
    <>
      {formatInrCompact(month.achieved)}
      <span className="font-normal text-muted-foreground">
        {" "}
        of {formatInrCompact(month.target)}
      </span>
      <span className="ml-1.5 font-normal text-subtle-foreground">
        {formatPercent((amount(month.achieved) / target) * 100)}
      </span>
    </>
  );
}

/** The key: what the bar and the line stand for. Identity never rests on colour alone. */
function TargetsKey({ showSold }: { showSold: boolean }): React.JSX.Element {
  return (
    <ul aria-label="Key" className="flex items-center gap-3 text-xs text-muted-foreground">
      {showSold ? (
        <li className="flex items-center gap-1.5">
          <span aria-hidden="true" className="h-2 w-3 rounded-full bg-primary" />
          Sold
        </li>
      ) : null}
      <li className="flex items-center gap-1.5">
        <span aria-hidden="true" className="h-3 w-0.5 bg-foreground" />
        Target
      </li>
    </ul>
  );
}

/**
 * RPT-001 · Order value sold each month against the team's target: this month and the five
 * before it, oldest first (FS-052). The page leaves it out when the role has no targets.
 */
export function TargetsCard({
  months,
  className,
}: {
  months: NonNullable<DashboardOverview["targetsByMonth"]>;
  className?: string;
}): React.JSX.Element {
  const showSold = months.some((month) => month.achieved !== null);
  const anyTarget = months.some((month) => amount(month.target) > 0);
  const max = Math.max(
    0,
    ...months.flatMap((month) => [amount(month.target), amount(month.achieved)]),
  );
  const lastMonth = months.at(-1)?.month;

  return (
    <Card className={className}>
      <CardHeader className="flex-wrap">
        <div className="flex flex-col gap-0.5">
          <CardTitle>Orders against target</CardTitle>
          <CardDescription>
            {showSold
              ? "Order value sold each month, against your team's target"
              : "Your team's order value target each month"}
          </CardDescription>
        </div>
        {max > 0 ? <TargetsKey showSold={showSold} /> : null}
      </CardHeader>
      <CardContent>
        {max === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {showSold
              ? "No targets set and nothing sold in the last six months."
              : "No targets set for the last six months."}
          </p>
        ) : (
          <>
            <ul className="flex flex-col gap-4">
              {months.map((month) => (
                <li key={month.month} className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="truncate text-muted-foreground">
                      {formatMonth(month.month)}
                      {month.month === lastMonth ? (
                        <span className="ml-1.5 text-subtle-foreground">so far</span>
                      ) : null}
                    </span>
                    <span className="font-medium whitespace-nowrap text-foreground tabular-nums">
                      <MonthFigures month={month} />
                    </span>
                  </div>
                  <ProportionBar
                    value={amount(month.achieved)}
                    max={max}
                    {...(amount(month.target) > 0 ? { marker: amount(month.target) } : {})}
                  />
                </li>
              ))}
            </ul>
            {!anyTarget ? (
              <p className="mt-4 text-xs text-muted-foreground">No targets set for these months.</p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Mirrors the two cards side by side: a title, a description and rows of label and bar. */
export function DashboardChartsSkeleton(): React.JSX.Element {
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      {[
        { span: "lg:col-span-2", rows: 5 },
        { span: "lg:col-span-3", rows: 6 },
      ].map((card) => (
        <Card key={card.span} aria-hidden="true" className={card.span}>
          <CardHeader>
            <div className="flex flex-col gap-0.5">
              <Skeleton className="h-6 w-44" />
              <Skeleton className="h-5 w-56" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-4">
              {Array.from({ length: card.rows }, (_, index) => (
                <div key={index} className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <Skeleton className="h-5 w-24" />
                    <Skeleton className="h-5 w-28" />
                  </div>
                  <Skeleton className="h-2 w-full rounded-full" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
