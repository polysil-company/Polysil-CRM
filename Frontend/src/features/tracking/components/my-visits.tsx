"use client";

import { ArrowLeft01Icon, ArrowRight01Icon, Location01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { parseAsString, useQueryState } from "nuqs";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import type { Visit } from "@/features/tracking/api/tracking.schemas";
import {
  myVisitsQueryOptions,
  trackingConfigQueryOptions,
  visitQueryOptions,
} from "@/features/tracking/api/visits.queries";
import { isCalendarDay, useDayParam } from "@/features/tracking/hooks/use-day-param";
import { minutesText, VISIT_OUTCOME_LABELS } from "@/features/tracking/lib/tracking-labels";
import {
  formatCalendarDay,
  formatNumber,
  formatTime,
  shiftCalendarDay,
  todayInIndia,
} from "@/lib/format";

import { CheckInForm } from "./check-in-form";
import { OpenVisitCard } from "./open-visit";

/**
 * TRK-003 … TRK-005 · My visits: **Check in** at a lead, a dealer or a place; the open visit with
 * its photos and **Check out**; and the day's visits. The day is in the URL; an open visit named
 * by a refusal opens through `?visit=`.
 */
export function MyVisits(): React.JSX.Element {
  const config = useQuery(trackingConfigQueryOptions());
  const [day, setDay] = useDayParam();
  const today = todayInIndia();
  const [visitParam, setVisitParam] = useQueryState("visit", parseAsString);
  const [checkingIn, setCheckingIn] = useState(false);
  const visits = useInfiniteQuery({
    ...myVisitsQueryOptions(day),
    enabled: config.data?.trackingAllowed === true,
  });
  const named = useQuery({
    ...visitQueryOptions(visitParam ?? ""),
    enabled: visitParam !== null && config.data?.trackingAllowed === true,
  });

  if (config.status === "pending") return <MyVisitsSkeleton />;
  if (config.status === "error") {
    return (
      <ErrorState
        error={config.error}
        onRetry={() => {
          void config.refetch();
        }}
      />
    );
  }
  if (!config.data.trackingAllowed) {
    return (
      <EmptyState
        icon={Location01Icon}
        title="Your role doesn't record visits"
        description="Visits are checked in by those who work in the field."
        className="rounded-xl border border-dashed border-border py-12"
      />
    );
  }

  const list = visits.data?.pages.flatMap((page) => page.items) ?? [];
  const openVisit: Visit | undefined =
    (named.data !== undefined && named.data.checkoutAt === null ? named.data : undefined) ??
    list.find((visit) => visit.checkoutAt === null);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-lg font-semibold text-foreground">{formatCalendarDay(day)}</h2>
          <p className="text-sm text-muted-foreground">
            {visits.status === "success"
              ? `${formatNumber(list.length)} ${list.length === 1 ? "visit" : "visits"}`
              : "Your visits"}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <Button
            variant="outline"
            size="icon-md"
            aria-label="The day before"
            onClick={() => {
              setDay(shiftCalendarDay(day, -1));
            }}
          >
            <Icon icon={ArrowLeft01Icon} />
          </Button>
          <div className="flex flex-col gap-1">
            <Label htmlFor="visits-day">Day</Label>
            <Input
              id="visits-day"
              type="date"
              value={day}
              max={today}
              onChange={(event) => {
                if (isCalendarDay(event.target.value)) setDay(event.target.value);
              }}
              className="w-40"
            />
          </div>
          <Button
            variant="outline"
            size="icon-md"
            aria-label="The day after"
            disabled={day >= today}
            onClick={() => {
              setDay(shiftCalendarDay(day, 1));
            }}
          >
            <Icon icon={ArrowRight01Icon} />
          </Button>
          {openVisit === undefined ? (
            <Button
              onClick={() => {
                setCheckingIn(true);
              }}
            >
              <Icon icon={Location01Icon} />
              Check in
            </Button>
          ) : null}
        </div>
      </div>

      {openVisit === undefined ? null : (
        <OpenVisitCard visit={openVisit} photoRequired={config.data.visitPhotoRequired} />
      )}

      {visits.status === "pending" ? (
        <MyVisitsSkeleton />
      ) : visits.status === "error" ? (
        <ErrorState
          error={visits.error}
          onRetry={() => {
            void visits.refetch();
          }}
        />
      ) : list.length === 0 ? (
        <EmptyState
          icon={Location01Icon}
          title={day === today ? "No visits yet today" : "No visits this day"}
          description={
            day === today
              ? "Check in when you reach a farmer, a dealer or a place."
              : "Pick another day."
          }
          className="rounded-xl border border-dashed border-border py-12"
        />
      ) : (
        <Card>
          <CardContent className="pt-4">
            <ol aria-label="Visits" className="flex flex-col divide-y divide-border">
              {list.map((visit) => (
                <VisitRow key={visit.id} visit={visit} />
              ))}
            </ol>
            {visits.hasNextPage ? (
              <div className="mt-4 flex justify-center">
                <Button
                  variant="outline"
                  size="sm"
                  state={visits.isFetchingNextPage ? "loading" : "idle"}
                  loadingLabel="Loading…"
                  onClick={() => {
                    void visits.fetchNextPage();
                  }}
                >
                  Show more
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}

      <Dialog open={checkingIn} onOpenChange={setCheckingIn}>
        <DialogContent size="md">
          {checkingIn ? (
            <CheckInForm
              config={config.data}
              onDone={() => {
                setCheckingIn(false);
                if (day !== today) setDay(today);
              }}
              onOpenVisit={(visitId) => {
                setCheckingIn(false);
                void setVisitParam(visitId);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function VisitRow({ visit }: { visit: Visit }): React.JSX.Element {
  return (
    <li className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-foreground tabular-nums">
          {formatTime(visit.checkinAt)}
          {visit.checkoutAt === null ? "" : ` to ${formatTime(visit.checkoutAt)}`}
        </span>
        {visit.lead === null ? (
          <span className="text-sm font-medium text-foreground">{visit.label}</span>
        ) : (
          <Link
            href={`/leads/${visit.lead.id}`}
            className="font-mono text-sm text-primary-text underline-offset-4 hover:underline"
          >
            {visit.label}
          </Link>
        )}
        {visit.checkoutAt === null ? (
          <Badge variant="success" size="sm" dot>
            Open
          </Badge>
        ) : visit.outcome === null ? null : (
          <Badge variant="neutral" size="sm">
            {VISIT_OUTCOME_LABELS[visit.outcome]}
          </Badge>
        )}
      </div>
      <span className="text-xs text-muted-foreground">
        {visit.durationMinutes === null ? "" : minutesText(visit.durationMinutes)}
        {visit.photoCount === 0
          ? ""
          : `${visit.durationMinutes === null ? "" : " · "}${formatNumber(visit.photoCount)} photo${visit.photoCount === 1 ? "" : "s"}`}
        {visit.autoClosed ? " · closed by itself after 12 hours" : ""}
      </span>
      {visit.note === null ? null : (
        <p className="text-sm text-foreground">&ldquo;{visit.note}&rdquo;</p>
      )}
    </li>
  );
}

export function MyVisitsSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading your visits" className="flex flex-col gap-2">
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-16 w-full rounded-xl" />
    </div>
  );
}
