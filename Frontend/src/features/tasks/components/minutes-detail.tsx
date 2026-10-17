"use client";

import { ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { Card, CardContent } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { minutesQueryOptions } from "@/features/tasks/api/tasks.queries";
import type { Minutes } from "@/features/tasks/api/tasks.schemas";
import { isApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";

import { MinutesContent } from "./lead-minutes";

/**
 * TASK-007 · One set of meeting minutes on its own page (`GET /minutes/{id}`), opened from an
 * action item's task ("From meeting minutes"): what was agreed and what came of each item, with
 * the lead or partner it was about. Staff only; out of scope is a 404.
 */
export function MinutesDetail({ minutesId }: { minutesId: string }): React.JSX.Element {
  const query = useQuery(minutesQueryOptions(minutesId));

  if (query.status === "pending") return <MinutesDetailSkeleton />;
  if (query.status === "error") {
    if (isApiError(query.error) && query.error.status === 404) notFound();
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  return <MinutesView minutes={query.data} />;
}

function MinutesView({ minutes }: { minutes: Minutes }): React.JSX.Element {
  const about = subjectOf(minutes);

  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <div className="flex min-w-0 flex-col gap-1.5">
        <Link
          href="/tasks"
          transitionTypes={["nav-back"]}
          className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
        >
          <Icon icon={ArrowLeft01Icon} size="sm" />
          Tasks
        </Link>
        <h2 className="text-xl font-semibold text-foreground">
          Meeting on {formatDate(minutes.heldAt)}
        </h2>
        {about === null ? null : (
          <p className="text-sm text-muted-foreground">
            About{" "}
            {about.href === null ? (
              <span className="text-foreground">{about.label}</span>
            ) : (
              <Link
                href={about.href}
                className="font-medium text-foreground underline-offset-2 hover:underline"
              >
                {about.label}
              </Link>
            )}
          </p>
        )}
      </div>
      <Card>
        <CardContent className="flex flex-col gap-2 pt-4">
          <MinutesContent minutes={minutes} />
        </CardContent>
      </Card>
    </div>
  );
}

/** The lead (linked) or the partner the meeting was about; hidden ones say so. */
function subjectOf(
  minutes: Minutes,
): { label: string; href: `/leads/${string}` | `/partners/${string}` | null } | null {
  if (minutes.lead !== null) {
    if (minutes.lead.hidden) return { label: "a lead not visible to you", href: null };
    const label =
      [minutes.lead.farmerName, minutes.lead.inquiryNo].filter(Boolean).join(" · ") || "a lead";
    return { label, href: `/leads/${minutes.lead.id}` };
  }
  if (minutes.partner !== null) {
    if (minutes.partner.hidden) return { label: "a partner not visible to you", href: null };
    return { label: minutes.partner.name ?? "a partner", href: `/partners/${minutes.partner.id}` };
  }
  return null;
}

function MinutesDetailSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the minutes" className="flex max-w-3xl flex-col gap-5">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-4 w-48" />
      </div>
      <Skeleton className="h-48 w-full rounded-xl" />
    </div>
  );
}
