"use client";

import { Location01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { MapView, type MapMarker } from "@/components/patterns/map-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { teamLatestQueryOptions } from "@/features/tracking/api/tracking.queries";
import type { TeamMember } from "@/features/tracking/api/tracking.schemas";
import { LOW_BATTERY_PCT, MEMBER_STATE, roleText } from "@/features/tracking/lib/tracking-labels";
import { isApiError } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";

/**
 * TRK-001 · Where everyone the user may track was last seen while on duty, refreshed every
 * minute. Each person is listed in words beside the map: their state, when they were last
 * heard from, their battery, an open visit, and a faked location if the phone reported one.
 * A person opens their day's route.
 */
export function TeamMap(): React.JSX.Element {
  const query = useQuery(teamLatestQueryOptions());
  const router = useRouter();
  const people = useMemo(() => query.data ?? [], [query.data]);
  const markers = useMemo(
    (): MapMarker[] =>
      people.flatMap((person) =>
        person.position === null
          ? []
          : [
              {
                id: person.id,
                lat: person.position.lat,
                lng: person.position.lng,
                label: `${person.name}, ${MEMBER_STATE[person.state].label.toLowerCase()}${person.isMock ? ", fake location" : ""}`,
                tone: person.isMock ? "danger" : MEMBER_STATE[person.state].tone,
                size: "lg",
                hollow: person.isMock,
                onSelect: () => {
                  router.push(`/team-map/${person.id}`);
                },
              },
            ],
      ),
    [people, router],
  );

  if (query.status === "pending") return <TeamMapSkeleton />;
  if (query.status === "error") {
    return isApiError(query.error) && query.error.status === 403 ? (
      <EmptyState
        icon={Location01Icon}
        title="Your role has no tracking"
        description="The team map is for those who manage field staff."
        className="rounded-xl border border-dashed border-border py-12"
      />
    ) : (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  if (people.length === 0) {
    return (
      <EmptyState
        icon={Location01Icon}
        title="Nobody to show yet"
        description="People appear here once someone in your team tracks their duty."
        className="rounded-xl border border-dashed border-border py-12"
      />
    );
  }

  const onDuty = people.filter((person) => person.state !== "off_duty").length;
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="flex min-w-0 flex-col gap-3 lg:col-span-2">
        <p className="text-sm text-muted-foreground">
          {formatNumber(onDuty)} of {formatNumber(people.length)} on duty · updates every minute
        </p>
        <ul aria-label="Team" className="flex flex-col gap-2">
          {people.map((person) => (
            <li key={person.id}>
              <PersonCard person={person} />
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-col gap-2 lg:col-span-3">
        <MapView markers={markers} label="Team map" className="h-80 sm:h-96 lg:h-144" />
        <Legend />
      </div>
    </div>
  );
}

function PersonCard({ person }: { person: TeamMember }): React.JSX.Element {
  const state = MEMBER_STATE[person.state];
  const lowBattery = person.batteryPct !== null && person.batteryPct < LOW_BATTERY_PCT;
  return (
    <Link
      href={`/team-map/${person.id}`}
      className="flex flex-col gap-1.5 rounded-xl border border-border bg-card p-3 focus-ring-inset transition-colors duration-fast hover:bg-muted/50"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-foreground">{person.name}</span>
        <div className="flex flex-wrap items-center gap-1.5">
          {person.isMock ? (
            <Badge variant="danger" size="sm">
              Fake location
            </Badge>
          ) : null}
          <Badge variant={state.badge} size="sm" dot>
            {state.label}
          </Badge>
        </div>
      </div>
      <span className="text-xs text-muted-foreground">
        {roleText(person.role)}
        {person.lastSeenAt === null ? null : (
          <>
            {" · last seen "}
            <RelativeDate value={person.lastSeenAt} />
          </>
        )}
        {person.batteryPct === null ? "" : ` · battery ${formatNumber(person.batteryPct)}%`}
      </span>
      {lowBattery ? (
        <span className="text-xs font-medium text-warning">
          Battery low: tracking stops if the phone dies.
        </span>
      ) : null}
      {person.openVisit === null ? null : (
        <span className="text-xs text-foreground">
          On a visit to <span className="font-mono">{person.openVisit.label}</span> since{" "}
          <RelativeDate value={person.openVisit.since} />
        </span>
      )}
    </Link>
  );
}

function Legend(): React.JSX.Element {
  return (
    <ul
      aria-label="Map key"
      className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground"
    >
      <li className="flex items-center gap-1.5">
        <span aria-hidden="true" className="size-2.5 rounded-full bg-success" />
        On duty
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden="true" className="size-2.5 rounded-full bg-muted-foreground" />
        Not heard from in 15 minutes
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden="true" className="size-2.5 rounded-full border-2 border-danger" />
        Fake location reported
      </li>
    </ul>
  );
}

export function TeamMapSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the team map" className="grid gap-4 lg:grid-cols-5">
      <div className="flex flex-col gap-2 lg:col-span-2">
        <Skeleton className="h-20 w-full rounded-xl" />
        <Skeleton className="h-20 w-full rounded-xl" />
        <Skeleton className="h-20 w-full rounded-xl" />
      </div>
      <Card className="lg:col-span-3">
        <CardContent>
          <Skeleton className="h-80 w-full rounded-xl sm:h-96 lg:h-144" />
        </CardContent>
      </Card>
    </div>
  );
}
