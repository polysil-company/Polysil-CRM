import { ArrowDownRight01Icon, ArrowUpRight01Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Icon, type IconGlyph } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDelta } from "@/lib/format";
import { cn } from "@/lib/utils";

import { Sparkline } from "./sparkline";

export interface StatCardProps {
  label: string;
  /** Already formatted: "₹4.5 Cr", "128". */
  value: string;
  icon?: IconGlyph;
  /** Percentage change vs the previous period. */
  delta?: number | undefined;
  /** False when a decrease is the good outcome (e.g. overdue follow-ups). */
  increaseIsGood?: boolean;
  trend?: readonly number[] | undefined;
  /** Accessible summary of the trend — use describeTrend(). */
  trendLabel?: string;
  footnote?: string;
  className?: string;
}

/** KPI card: label, value, change vs last period and a sparkline. */
export function StatCard({
  label,
  value,
  icon,
  delta,
  increaseIsGood = true,
  trend,
  trendLabel,
  footnote,
  className,
}: StatCardProps): React.JSX.Element {
  const hasDelta = delta !== undefined && Number.isFinite(delta);
  const good = hasDelta && (increaseIsGood ? delta >= 0 : delta <= 0);

  return (
    <Card className={cn("gap-4 p-4", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 text-sm font-medium text-muted-foreground">
          {icon ? <Icon icon={icon} size="sm" /> : null}
          <span className="truncate">{label}</span>
        </span>
        {hasDelta ? (
          <Badge size="sm" variant={delta === 0 ? "neutral" : good ? "success" : "danger"}>
            <Icon icon={delta >= 0 ? ArrowUpRight01Icon : ArrowDownRight01Icon} />
            {formatDelta(delta)}
          </Badge>
        ) : null}
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate text-2xl font-semibold text-foreground tabular-nums">
            {value}
          </span>
          {footnote ? (
            <span className="truncate text-xs text-subtle-foreground">{footnote}</span>
          ) : null}
        </div>
        {trend && trendLabel ? (
          <Sparkline
            values={trend}
            label={trendLabel}
            tone={hasDelta && !good ? "danger" : "primary"}
          />
        ) : null}
      </div>
    </Card>
  );
}

/** Mirrors StatCard line for line: label row (h-5), value (h-8.5), footnote (h-4), sparkline (h-7). */
export function StatCardSkeleton({ className }: { className?: string }): React.JSX.Element {
  return (
    <Card aria-hidden="true" className={cn("gap-4 p-4", className)}>
      <div className="flex items-center justify-between gap-2">
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-5 w-12 rounded-full" />
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <Skeleton className="h-8.5 w-24" />
          <Skeleton className="h-4 w-20" />
        </div>
        <Skeleton className="h-7 w-24" />
      </div>
    </Card>
  );
}
