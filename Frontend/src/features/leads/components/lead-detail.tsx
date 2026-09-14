"use client";

import { ArrowLeft01Icon, Call02Icon, WhatsappIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { SegmentedMeter } from "@/components/patterns/segmented-meter";
import { describeTrend, Sparkline } from "@/components/patterns/sparkline";
import { TagList } from "@/components/patterns/tag";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { leadDetailQueryOptions } from "@/features/leads/api/leads.queries";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { LEAD_SOURCE_LABELS, ORDER_TYPE_LABELS } from "@/features/leads/lib/lead-labels";
import { isApiError } from "@/lib/api/errors";
import {
  EMPTY_VALUE,
  formatFullDate,
  formatIndianPhone,
  formatInr,
  formatNumber,
} from "@/lib/format";
import { cn } from "@/lib/utils";

import { LeadStatusBadge } from "./lead-status-badge";

/** LEAD-003 · Lead detail. A 404 renders the route's not-found page. */
export function LeadDetail({ leadId }: { leadId: string }): React.JSX.Element {
  const query = useQuery(leadDetailQueryOptions(leadId));

  if (query.status === "error" && isApiError(query.error) && query.error.status === 404) {
    notFound();
  }

  return (
    <QueryView query={query} pending={<LeadDetailSkeleton />} isEmpty={() => false} empty={null}>
      {(lead) => <LeadDetailView lead={lead} />}
    </QueryView>
  );
}

function DetailItem({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm text-foreground">{children}</dd>
    </div>
  );
}

function LeadDetailView({ lead }: { lead: Lead }): React.JSX.Element {
  const whatsappNumber = lead.phone.replace(/\D/g, "");
  const location = [lead.village, lead.district, lead.state].filter(Boolean).join(", ");

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Link
            href="/leads"
            transitionTypes={["nav-back"]}
            className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
          >
            <Icon icon={ArrowLeft01Icon} size="sm" />
            All leads
          </Link>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="truncate text-xl font-semibold text-foreground">{lead.customerName}</h2>
            <LeadStatusBadge status={lead.status} />
          </div>
          <p className="text-sm text-muted-foreground">
            <span className="font-mono">{lead.code}</span> · {ORDER_TYPE_LABELS[lead.type]} ·{" "}
            {LEAD_SOURCE_LABELS[lead.source]}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a href={`tel:${lead.phone}`} className={buttonVariants({ variant: "outline" })}>
            <Icon icon={Call02Icon} />
            Call
          </a>
          <a
            href={`https://wa.me/${whatsappNumber}`}
            target="_blank"
            rel="noreferrer"
            className={buttonVariants({ variant: "outline" })}
          >
            <Icon icon={WhatsappIcon} />
            WhatsApp
          </a>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle level={3}>Details</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <DetailItem label="Mobile">{formatIndianPhone(lead.phone)}</DetailItem>
              <DetailItem label="Location">{location || EMPTY_VALUE}</DetailItem>
              <DetailItem label="Estimated value">{formatInr(lead.estimatedValue)}</DetailItem>
              <DetailItem label="Land">
                {lead.acreage === null ? EMPTY_VALUE : `${formatNumber(lead.acreage)} acres`}
              </DetailItem>
              <DetailItem label="Crops">
                <TagList items={lead.crops.map((crop) => ({ id: crop, label: crop }))} max={6} />
              </DetailItem>
              <DetailItem label="Owner">
                <AvatarLabel name={lead.owner.name} imageUrl={lead.owner.avatarUrl} size="xs" />
              </DetailItem>
              <DetailItem label="Channel partner">
                {lead.channelPartner?.name ?? EMPTY_VALUE}
              </DetailItem>
              <DetailItem label="Follow-up">
                <RelativeDate value={lead.followUpAt} highlightOverdue />
              </DetailItem>
              <DetailItem label="Last activity">
                <RelativeDate value={lead.lastActivityAt} />
              </DetailItem>
              <DetailItem label="Created">{formatFullDate(lead.createdAt)}</DetailItem>
              {lead.lostReason ? (
                <DetailItem label="Lost reason" className="sm:col-span-2">
                  {lead.lostReason}
                </DetailItem>
              ) : null}
            </dl>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle level={3}>Win probability</CardTitle>
            </CardHeader>
            <CardContent>
              <SegmentedMeter value={lead.winProbability} segments={10} label="Win probability" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-0.5">
                <CardTitle level={3}>Engagement</CardTitle>
                <CardDescription>Interactions per week, last 12 weeks</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <Sparkline
                values={lead.engagement}
                label={describeTrend(lead.engagement, "Interactions per week")}
                className="h-12 w-40"
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

/** Mirrors LeadDetailView block for block. */
export function LeadDetailSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading lead" className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-5 w-20" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-7 w-56" />
            <Skeleton className="h-6 w-20 rounded-full" />
          </div>
          <Skeleton className="h-5 w-64" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="h-control-md w-20 rounded-md" />
          <Skeleton className="h-control-md w-28 rounded-md" />
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <Skeleton className="h-6 w-20" />
          </CardHeader>
          <CardContent>
            <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              {Array.from({ length: 10 }, (_, index) => (
                <div key={index} className="flex flex-col gap-1">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-5 w-36" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-32" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-3 w-40" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-0.5">
                <Skeleton className="h-6 w-28" />
                <Skeleton className="h-5 w-52" />
              </div>
            </CardHeader>
            <CardContent>
              <Skeleton className="h-12 w-40" />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
