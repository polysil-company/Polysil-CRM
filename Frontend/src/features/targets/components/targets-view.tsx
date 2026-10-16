"use client";

import { ArrowLeft01Icon, ArrowRight01Icon, Target02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { createParser, useQueryState } from "nuqs";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ProportionBar } from "@/components/patterns/proportion-bar";
import { QueryView } from "@/components/patterns/query-view";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { achievementQueryOptions } from "@/features/targets/api/targets.queries";
import {
  TARGET_METRICS,
  type Achievement,
  type Measure,
  type TargetMetric,
} from "@/features/targets/api/targets.schemas";
import { formatMeasure, formatShare, METRIC_LABELS } from "@/features/targets/lib/target-labels";
import { formatDateTime, formatMonth, shiftMonth, todayInIndia } from "@/lib/format";
import { cn } from "@/lib/utils";

import { SetTargetsDialog } from "./set-targets-dialog";

const parseAsMonth = createParser({
  parse: (value: string) => (/^\d{4}-(0[1-9]|1[0-2])$/.test(value) ? value : null),
  serialize: (value: string) => value,
});

/**
 * TGT-001, TGT-002 · Targets: your month against its targets, live, then a card per person
 * below you with theirs, and Set targets for those you may set. The month is in the URL.
 */
export function TargetsView(): React.JSX.Element {
  const thisMonth = todayInIndia().slice(0, 7);
  const [chosen, setChosen] = useQueryState("month", parseAsMonth);
  const month = chosen ?? thisMonth;
  const query = useQuery(achievementQueryOptions(month));

  const go = (next: string): void => {
    void setChosen(next === thisMonth ? null : next);
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="icon-md"
          aria-label="Previous month"
          onClick={() => {
            go(shiftMonth(month, -1));
          }}
        >
          <Icon icon={ArrowLeft01Icon} />
        </Button>
        <h2
          className="min-w-36 text-center text-lg font-semibold text-foreground"
          aria-live="polite"
        >
          {formatMonth(month)}
        </h2>
        <Button
          variant="outline"
          size="icon-md"
          aria-label="Next month"
          onClick={() => {
            go(shiftMonth(month, 1));
          }}
        >
          <Icon icon={ArrowRight01Icon} />
        </Button>
        {month === thisMonth ? null : (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              go(thisMonth);
            }}
          >
            This month
          </Button>
        )}
      </div>
      <QueryView
        query={query}
        pending={<TargetsSkeleton />}
        isEmpty={(data) => data.rows.length === 0}
        empty={
          <EmptyState
            icon={Target02Icon}
            title="No one here carries targets"
            description="Targets are set for staff who work leads and orders."
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => <TargetsBody data={data} month={month} pastMonth={month < thisMonth} />}
      </QueryView>
    </div>
  );
}

function TargetsBody({
  data,
  month,
  pastMonth,
}: {
  data: Achievement;
  month: string;
  pastMonth: boolean;
}): React.JSX.Element {
  const session = useSession();
  const canSet = useCan("targets", "create");
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);
  const meId = session.data?.user.id;
  const mine = data.rows.find((row) => row.user.id === meId);
  const team = data.rows.filter((row) => row.user.id !== meId);

  return (
    <div className="flex flex-col gap-6">
      <p className="text-xs text-muted-foreground">
        As of {formatDateTime(data.asOf)}.
        {data.saleCountedAt === null
          ? ""
          : ` Sales counted at: ${data.saleCountedAt.replaceAll("_", " ")}.`}
      </p>

      {mine === undefined ? null : (
        <section aria-labelledby="targets-mine" className="flex flex-col gap-3">
          <h3 id="targets-mine" className="text-base font-semibold text-foreground">
            Your month
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {TARGET_METRICS.map((metric) => (
              <MeasureCard key={metric} metric={metric} measure={mine.metrics[metric]} />
            ))}
          </div>
        </section>
      )}

      {team.length === 0 ? null : (
        <section aria-labelledby="targets-team" className="flex flex-col gap-3">
          <div className="flex flex-col gap-0.5">
            <h3 id="targets-team" className="text-base font-semibold text-foreground">
              {mine === undefined ? "Everyone" : "Your team"}
            </h3>
            <p className="text-sm text-muted-foreground">
              Everyone below you, with or without a target.
            </p>
          </div>
          <ul className="flex flex-col gap-3">
            {team.map((row) => (
              <li key={row.user.id}>
                <Card className="flex flex-col gap-3 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h4 className="font-medium text-foreground">{row.user.name}</h4>
                    {canSet ? (
                      <Button
                        variant="outline"
                        size="sm"
                        aria-label={`Set targets for ${row.user.name}`}
                        onClick={() => {
                          setEditing({ id: row.user.id, name: row.user.name });
                        }}
                      >
                        Set targets
                      </Button>
                    ) : null}
                  </div>
                  <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                    {TARGET_METRICS.map((metric) => (
                      <CompactMeasure key={metric} metric={metric} measure={row.metrics[metric]} />
                    ))}
                  </dl>
                </Card>
              </li>
            ))}
          </ul>
          <Card className="flex flex-col gap-3 bg-muted/40 p-4">
            <h4 className="font-medium text-foreground">All together</h4>
            <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {TARGET_METRICS.map((metric) => (
                <CompactMeasure key={metric} metric={metric} measure={data.totals[metric]} />
              ))}
            </dl>
          </Card>
        </section>
      )}

      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      >
        <DialogContent size="md">
          {editing === null ? null : (
            <SetTargetsDialog
              userId={editing.id}
              name={editing.name}
              month={month}
              pastMonth={pastMonth}
              onClose={() => {
                setEditing(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Achieved, read out as "not available" when withheld. */
function Achieved({
  metric,
  measure,
}: {
  metric: TargetMetric;
  measure: Measure;
}): React.ReactNode {
  return measure.achieved === null ? (
    <>
      <span aria-hidden className="text-muted-foreground">
        —
      </span>
      <span className="sr-only">Not available to you</span>
    </>
  ) : (
    formatMeasure(metric, measure.achieved)
  );
}

function progressOf(measure: Measure): { value: number; done: boolean } | null {
  if (measure.pct === null) return null;
  const pct = Number(measure.pct);
  return { value: pct, done: pct >= 100 };
}

function MeasureCard({
  metric,
  measure,
}: {
  metric: TargetMetric;
  measure: Measure;
}): React.JSX.Element {
  const progress = progressOf(measure);
  return (
    <Card className="flex flex-col gap-2 p-4">
      <span className="text-sm font-medium text-muted-foreground">{METRIC_LABELS[metric]}</span>
      <span className="text-2xl font-semibold text-foreground tabular-nums">
        <Achieved metric={metric} measure={measure} />
      </span>
      <span className="text-xs text-muted-foreground tabular-nums">
        {measure.target === null || Number(measure.target) === 0
          ? "No target set"
          : `of ${formatMeasure(metric, measure.target)}${progress === null ? "" : ` · ${formatShare(measure.pct ?? "0")}`}`}
      </span>
      {progress === null ? null : (
        <ProportionBar
          value={progress.value}
          max={100}
          tone={progress.done ? "success" : "primary"}
        />
      )}
    </Card>
  );
}

function CompactMeasure({
  metric,
  measure,
}: {
  metric: TargetMetric;
  measure: Measure;
}): React.JSX.Element {
  const progress = progressOf(measure);
  const target = measure.target === null || Number(measure.target) === 0 ? null : measure.target;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <dt className="text-xs text-muted-foreground">{METRIC_LABELS[metric]}</dt>
      <dd className="text-sm text-foreground tabular-nums">
        <Achieved metric={metric} measure={measure} />
        <span className="text-muted-foreground">
          {target === null ? " · no target" : ` of ${formatMeasure(metric, target)}`}
        </span>
      </dd>
      {progress === null ? null : (
        <dd
          className={cn(
            "flex items-center gap-2 text-xs tabular-nums",
            progress.done ? "text-success" : "text-muted-foreground",
          )}
        >
          <ProportionBar
            value={progress.value}
            max={100}
            tone={progress.done ? "success" : "primary"}
            className="h-1.5"
          />
          {formatShare(measure.pct ?? "0")}
        </dd>
      )}
    </div>
  );
}

function TargetsSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading targets" className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {TARGET_METRICS.map((metric) => (
          <Skeleton key={metric} className="h-28 w-full rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-32 w-full rounded-xl" />
    </div>
  );
}
