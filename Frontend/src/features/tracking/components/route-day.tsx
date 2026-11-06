"use client";

import { ArrowLeft01Icon, ArrowRight01Icon, Route01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import { useMemo } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { MapView, type MapMarker, type MapPath } from "@/components/patterns/map-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { routeQueryOptions } from "@/features/tracking/api/tracking.queries";
import type { Route } from "@/features/tracking/api/tracking.schemas";
import { isCalendarDay, useDayParam } from "@/features/tracking/hooks/use-day-param";
import {
  dutyEndText,
  minutesText,
  VISIT_OUTCOME_LABELS,
} from "@/features/tracking/lib/tracking-labels";
import { isApiError } from "@/lib/api/errors";
import {
  formatCalendarDay,
  formatNumber,
  formatTime,
  shiftCalendarDay,
  todayInIndia,
} from "@/lib/format";

/**
 * TRK-002 · One person's day: the path, their stops and visits, their duty, and how far they
 * went. Everything on the map is also listed in words. Another person's route is logged by
 * the backend; 404 opens the not-found page.
 */
export function RouteDay({ userId }: { userId: string }): React.JSX.Element {
  const [day, setDay] = useDayParam();
  const today = todayInIndia();
  const query = useQuery(routeQueryOptions(userId, day));
  if (query.status === "error" && isApiError(query.error) && query.error.status === 404) {
    notFound();
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <Link
            href="/team-map"
            transitionTypes={["nav-back"]}
            className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
          >
            <Icon icon={ArrowLeft01Icon} size="sm" />
            Team map
          </Link>
          <h2 className="text-xl font-semibold text-foreground">
            {query.status === "success" ? query.data.user.name : "Route"}
          </h2>
          <p className="text-sm text-muted-foreground">{formatCalendarDay(day)}</p>
        </div>
        <div className="flex items-end gap-2">
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
            <Label htmlFor="route-day">Day</Label>
            <Input
              id="route-day"
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
        </div>
      </div>

      {query.status === "pending" ? (
        <RouteDaySkeleton />
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : query.data.duty.length === 0 && query.data.points.length === 0 ? (
        <EmptyState
          icon={Route01Icon}
          title="No duty this day"
          description="Nothing was tracked. Pick another day."
          className="rounded-xl border border-dashed border-border py-12"
        />
      ) : (
        <RouteView route={query.data} />
      )}
    </div>
  );
}

function RouteView({ route }: { route: Route }): React.JSX.Element {
  const paths = useMemo(
    (): MapPath[] => [
      {
        id: "path",
        tone: "primary",
        points: route.points.map((point): readonly [number, number] => [point.lat, point.lng]),
      },
    ],
    [route.points],
  );
  const markers = useMemo((): MapMarker[] => {
    const visitIds = new Set(route.visits.map((visit) => visit.id));
    const stops: MapMarker[] = route.stops
      .filter((stop) => stop.visitId === null || !visitIds.has(stop.visitId))
      .map((stop, index) => ({
        id: `stop-${String(index)}`,
        lat: stop.lat,
        lng: stop.lng,
        label: `Stop, ${minutesText(stop.minutes)} from ${formatTime(stop.from)}`,
        tone: "muted",
        size: "sm",
      }));
    const visits: MapMarker[] = route.visits.map((visit) => ({
      id: visit.id,
      lat: visit.checkin.lat,
      lng: visit.checkin.lng,
      label: `Visit to ${visit.label} at ${formatTime(visit.checkinAt)}`,
      tone: "success",
      size: "lg",
    }));
    const first = route.points[0];
    const last = route.points[route.points.length - 1];
    const ends: MapMarker[] = [
      ...(first === undefined
        ? []
        : [
            {
              id: "start",
              lat: first.lat,
              lng: first.lng,
              label: `Start, ${formatTime(first.at)}`,
              tone: "info",
              size: "md",
            } satisfies MapMarker,
          ]),
      ...(last === undefined || route.points.length < 2
        ? []
        : [
            {
              id: "end",
              lat: last.lat,
              lng: last.lng,
              label: `Last point, ${formatTime(last.at)}`,
              tone: "danger",
              size: "md",
            } satisfies MapMarker,
          ]),
    ];
    return [...stops, ...visits, ...ends];
  }, [route.points, route.stops, route.visits]);

  // An open duty runs to its last recorded point: the page never reads the clock while drawing.
  const lastAt = route.points[route.points.length - 1]?.at ?? null;
  const dutyMinutes = route.duty.reduce((sum, span) => {
    const end = Date.parse(span.endedAt ?? lastAt ?? span.startedAt);
    return sum + Math.max(0, Math.round((end - Date.parse(span.startedAt)) / 60_000));
  }, 0);

  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Figure label="Distance" value={`${formatNumber(route.distanceKm, 1)} km`} />
        <Figure label="On duty" value={minutesText(dutyMinutes)} />
        <Figure label="Stops" value={formatNumber(route.stops.length)} />
        <Figure label="Visits" value={formatNumber(route.visits.length)} />
      </dl>
      <p className="text-xs text-muted-foreground">
        {formatNumber(route.pointCount)} points recorded
        {route.droppedPoints === 0
          ? ""
          : ` · ${formatNumber(route.droppedPoints)} left out for poor accuracy or impossible jumps`}
      </p>
      {route.mockPoints === 0 ? null : (
        <p role="note" className="text-sm font-medium text-danger">
          The phone reported a fake location for {formatNumber(route.mockPoints)}{" "}
          {route.mockPoints === 1 ? "point" : "points"} this day.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <MapView
            markers={markers}
            paths={paths}
            label={`Route of ${route.user.name}`}
            className="h-80 sm:h-96 lg:h-144"
          />
        </div>
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle level={3}>Duty</CardTitle>
            </CardHeader>
            <CardContent>
              <ul aria-label="Duty" className="flex flex-col gap-1.5 text-sm">
                {route.duty.map((span) => (
                  <li key={span.id} className="text-foreground tabular-nums">
                    {formatTime(span.startedAt)} to{" "}
                    {span.endedAt === null ? "now, still on duty" : formatTime(span.endedAt)}
                    {span.endReason === null ? null : (
                      <span className="text-muted-foreground">
                        {" "}
                        · {dutyEndText(span.endReason)}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle level={3}>Visits and stops</CardTitle>
            </CardHeader>
            <CardContent>
              {route.stops.length === 0 && route.visits.length === 0 ? (
                <p className="text-sm text-muted-foreground">No stops of 10 minutes or more.</p>
              ) : (
                <ol aria-label="Visits and stops" className="flex flex-col divide-y divide-border">
                  {route.stops.map((stop, index) => {
                    const visit = route.visits.find((item) => item.id === stop.visitId);
                    return (
                      <li
                        key={`${stop.from}-${String(index)}`}
                        className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm text-foreground tabular-nums">
                            {formatTime(stop.from)} to {formatTime(stop.to)}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {minutesText(stop.minutes)}
                          </span>
                          {visit === undefined ? (
                            <Badge variant="neutral" size="sm">
                              Stop
                            </Badge>
                          ) : (
                            <Badge variant="success" size="sm">
                              Visit
                            </Badge>
                          )}
                        </div>
                        {visit === undefined ? null : (
                          <div className="flex flex-col gap-0.5 text-xs">
                            {visit.lead === null ? (
                              <span className="font-mono text-foreground">{visit.label}</span>
                            ) : (
                              <Link
                                href={`/leads/${visit.lead.id}`}
                                className="font-mono text-primary-text underline-offset-4 hover:underline"
                              >
                                {visit.label}
                              </Link>
                            )}
                            <span className="text-muted-foreground">
                              {visit.outcome === null
                                ? "Still open"
                                : VISIT_OUTCOME_LABELS[visit.outcome]}
                              {visit.durationMinutes === null
                                ? ""
                                : ` · ${minutesText(visit.durationMinutes)}`}
                              {visit.photoCount === 0
                                ? ""
                                : ` · ${formatNumber(visit.photoCount)} photo${visit.photoCount === 1 ? "" : "s"}`}
                              {visit.autoClosed ? " · closed by itself after 12 hours" : ""}
                            </span>
                            {visit.note === null ? null : (
                              <span className="text-foreground">&ldquo;{visit.note}&rdquo;</span>
                            )}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Figure({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="flex flex-col gap-0.5 rounded-xl border border-border bg-card p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-lg font-semibold text-foreground tabular-nums">{value}</dd>
    </div>
  );
}

export function RouteDaySkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the route" className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
      <Skeleton className="h-80 w-full rounded-xl sm:h-96 lg:h-144" />
    </div>
  );
}
