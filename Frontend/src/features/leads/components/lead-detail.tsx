"use client";

import {
  AlertCircleIcon,
  ArrowLeft01Icon,
  Call02Icon,
  Share08Icon,
  PackageIcon,
  WhatsappIcon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Tag, toneForLabel } from "@/components/patterns/tag";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { RelatedComplaints } from "@/features/complaints/components/related-complaints";
import { leadDetailQueryOptions } from "@/features/leads/api/leads.queries";
import type { Lead, LeadStage } from "@/features/leads/api/leads.schemas";
import {
  DUPLICATE_SIGNAL_LABELS,
  formatAcres,
  LEAD_INQUIRY_TYPE_LABELS,
  LEAD_PRIORITY_BADGE,
  LEAD_PRIORITY_LABELS,
  partnerTypeLabel,
} from "@/features/leads/lib/lead-labels";
import { LookupName } from "@/features/lookups/components/lookup-name";
import { formatTerritory } from "@/features/lookups/lib/lookup-labels";
import { toShareParam } from "@/features/messages/lib/share-attachment";
import { LeadQuotations } from "@/features/quotations/components/lead-quotations";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { LeadMinutes } from "@/features/tasks/components/lead-minutes";
import { LeadTasks } from "@/features/tasks/components/lead-tasks";
import { isApiError } from "@/lib/api/errors";
import {
  EMPTY_VALUE,
  formatFullDate,
  formatIndianPhone,
  formatInr,
  formatNumber,
} from "@/lib/format";
import { cn } from "@/lib/utils";

import { LeadAssignDialog } from "./lead-assign-dialog";
import { LeadNoteComposer } from "./lead-note-composer";
import { LeadStageBadge } from "./lead-stage-badge";
import { LeadStageMenu } from "./lead-stage-menu";
import { LeadTimeline, LeadTimelineSkeleton } from "./lead-timeline";

/** Stages the backend closes to reassignment (`TERMINAL` in backend/api/domain/leads.py). */
const CLOSED_STAGES: ReadonlySet<LeadStage> = new Set(["won", "lost", "merged"]);
/** The stages an order may be placed on, as the backend allows (SO-005). */
const ORDERABLE_STAGES: ReadonlySet<LeadStage> = new Set([
  "qualified",
  "quoted",
  "negotiation",
  "won",
]);

/** Detail rows that always render — the skeleton draws the same number. */
const DETAIL_ROW_COUNT = 15;

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
      <dd className="min-w-0 text-sm wrap-break-word text-foreground">{children}</dd>
    </div>
  );
}

/**
 * A lead's next follow-up is a task on the backend (BE-002). TODO(TASK-001): show it once
 * the tasks module is connected.
 */
function NotRecorded(): React.JSX.Element {
  return <span className="text-subtle-foreground">{EMPTY_VALUE}</span>;
}

/** A notice above the details: a merged lead, or possible duplicates. */
function LeadNotice({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-border bg-warning-soft p-3 text-sm text-foreground">
      <Icon icon={AlertCircleIcon} className="mt-0.5 text-warning" />
      <div className="flex min-w-0 flex-col gap-1">{children}</div>
    </div>
  );
}

function LeadNotices({ lead }: { lead: Lead }): React.JSX.Element | null {
  const pending = lead.duplicates.filter((duplicate) => duplicate.state === "pending");

  if (lead.mergedInto) {
    return (
      <LeadNotice>
        <p>
          This lead was merged into{" "}
          <Link
            href={`/leads/${lead.mergedInto.id}`}
            className="font-mono font-medium text-primary-text underline-offset-4 hover:underline"
          >
            {lead.mergedInto.code}
          </Link>
          . Work on that lead instead.
        </p>
      </LeadNotice>
    );
  }

  if (pending.length === 0) {
    return null;
  }

  return (
    <LeadNotice>
      <p className="font-medium">
        {pending.length === 1 ? "Possible duplicate" : `${pending.length} possible duplicates`}
      </p>
      <ul className="flex flex-col gap-0.5 text-muted-foreground">
        {pending.map((duplicate) => (
          <li key={duplicate.linkId}>
            <Link
              href={`/leads/${duplicate.leadId}`}
              className="font-mono text-primary-text underline-offset-4 hover:underline"
            >
              {duplicate.code}
            </Link>
            : {DUPLICATE_SIGNAL_LABELS[duplicate.signal]}
          </li>
        ))}
      </ul>
    </LeadNotice>
  );
}

function LeadDetailView({ lead }: { lead: Lead }): React.JSX.Element {
  const { data: session } = useSession();
  const canEdit = useCan("leads", "edit");
  const canSeeQuotations = useCan("quotations");
  const canOrder = useCan("sales_orders", "create");
  const canSeeTasks = useCan("tasks") && session?.userType === "staff";
  const whatsappNumber = lead.phone.replace(/\D/g, "");
  const lost = lead.stage === "lost";

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
            <LeadStageBadge stage={lead.stage} />
            {/* Hot, warm or cold ranks open leads; a closed one no longer needs ranking. */}
            {lead.priority && !CLOSED_STAGES.has(lead.stage) ? (
              <Badge variant={LEAD_PRIORITY_BADGE[lead.priority]}>
                {LEAD_PRIORITY_LABELS[lead.priority]}
              </Badge>
            ) : null}
          </div>
          <p className="text-sm text-muted-foreground">
            <span className="font-mono">{lead.code}</span> · {LEAD_INQUIRY_TYPE_LABELS[lead.type]} ·{" "}
            <LookupName list="lead-sources" code={lead.source} />
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
          {/* MSG-003 · Messaging is for staff. Opens New message with this lead attached. */}
          {session?.userType === "staff" ? (
            <Link
              href={{
                pathname: "/messages",
                query: { share: toShareParam({ type: "lead", id: lead.id }) },
              }}
              className={buttonVariants({ variant: "outline" })}
            >
              <Icon icon={Share08Icon} />
              Share with a colleague
            </Link>
          ) : null}
          {/* SO-005 · An order typed in without a quotation, once the lead is qualified. */}
          {canOrder && ORDERABLE_STAGES.has(lead.stage) ? (
            <Link
              href={`/sales-orders/new?lead=${lead.id}`}
              className={buttonVariants({ variant: "outline" })}
            >
              <Icon icon={PackageIcon} />
              New order
            </Link>
          ) : null}
          {/* LEAD-007 · The main action on a lead, for whoever may edit it. */}
          {canEdit ? <LeadStageMenu lead={lead} /> : null}
        </div>
      </div>

      <LeadNotices lead={lead} />

      <div className="flex min-w-0 flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle level={3}>Details</CardTitle>
            {/* LEAD-008 · A closed lead (won, lost, merged) cannot be reassigned. */}
            {canEdit && !CLOSED_STAGES.has(lead.stage) ? <LeadAssignDialog lead={lead} /> : null}
          </CardHeader>
          <CardContent>
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <DetailItem label="Mobile">{formatIndianPhone(lead.phone)}</DetailItem>
              <DetailItem label="Email">{lead.email ?? EMPTY_VALUE}</DetailItem>
              <DetailItem label="Territory">{formatTerritory(lead.territory)}</DetailItem>
              <DetailItem label="Village">{lead.village ?? EMPTY_VALUE}</DetailItem>
              <DetailItem label="Irrigation system">
                <LookupName list="mis-systems" code={lead.misSystem} />
              </DetailItem>
              <DetailItem label="Estimated value">{formatInr(lead.estimatedValue)}</DetailItem>
              <DetailItem label="Owner">
                {lead.owner ? (
                  <AvatarLabel
                    name={lead.owner.name}
                    secondary={lead.ownerOrgUnit.name}
                    size="xs"
                  />
                ) : (
                  <span className="text-muted-foreground">
                    Unassigned · {lead.ownerOrgUnit.name}
                  </span>
                )}
              </DetailItem>
              <DetailItem label="Channel partner">
                {lead.channelPartner
                  ? `${lead.channelPartner.name} · ${partnerTypeLabel(lead.channelPartner.partnerType)}`
                  : EMPTY_VALUE}
              </DetailItem>
              <DetailItem label="Score">{lead.score ?? EMPTY_VALUE}</DetailItem>
              <DetailItem label="Land">
                {lead.landAcres === null ? EMPTY_VALUE : `${formatAcres(lead.landAcres)} acres`}
              </DetailItem>
              <DetailItem label="Crops">
                {lead.crops.length === 0 ? (
                  EMPTY_VALUE
                ) : (
                  <span className="flex flex-wrap gap-1.5">
                    {lead.crops.map((crop) => (
                      <Tag
                        key={crop.code}
                        tone={toneForLabel(crop.name)}
                        className={crop.isActive ? undefined : "opacity-60"}
                        title={crop.isActive ? undefined : "No longer in the crops list"}
                      >
                        {crop.name}
                      </Tag>
                    ))}
                  </span>
                )}
              </DetailItem>
              <DetailItem label="Follow-up">
                <NotRecorded />
              </DetailItem>
              <DetailItem label="First contacted">
                {lead.firstContactedAt === null ? (
                  "Not yet"
                ) : (
                  <RelativeDate value={lead.firstContactedAt} />
                )}
              </DetailItem>
              <DetailItem label="Last activity">
                <RelativeDate value={lead.lastActivityAt} />
              </DetailItem>
              <DetailItem label="Created">
                {formatFullDate(lead.createdAt)}
                {lead.createdBy ? (
                  <span className="text-muted-foreground"> · by {lead.createdBy.name}</span>
                ) : null}
              </DetailItem>
              {lead.reopenCount > 0 ? (
                <DetailItem label="Reopened">
                  {lead.reopenCount === 1 ? "Once" : `${formatNumber(lead.reopenCount)} times`}
                </DetailItem>
              ) : null}
              {lost ? (
                <DetailItem label="Lost reason" className="sm:col-span-2">
                  {lead.lostReason?.name ?? EMPTY_VALUE}
                  {lead.lostNote ? (
                    <span className="mt-1 block text-muted-foreground">{lead.lostNote}</span>
                  ) : null}
                </DetailItem>
              ) : null}
            </dl>
          </CardContent>
        </Card>

        {/* QUOT-001 · The lead's quotations, for whoever may see quotations. */}
        {canSeeQuotations ? <LeadQuotations leadId={lead.id} leadStage={lead.stage} /> : null}

        {/* CMPL-001 · Complaints about this lead, and raising one. */}
        <RelatedComplaints about={{ leadId: lead.id }} readOnly={lead.stage === "merged"} />

        {/* TASK-003, TASK-007 · Calls, visits and meetings about this lead, and their minutes. */}
        {canSeeTasks ? (
          <>
            <LeadTasks
              leadId={lead.id}
              leadName={lead.customerName}
              merged={lead.stage === "merged"}
            />
            <LeadMinutes
              leadId={lead.id}
              leadName={lead.customerName}
              merged={lead.stage === "merged"}
            />
          </>
        ) : null}

        {/* LEAD-005, LEAD-006 · Notes and the lead's history. A merged lead is read-only. */}
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-0.5">
              <CardTitle level={3}>Activity</CardTitle>
              <CardDescription>Notes and every change, newest first</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            {canEdit && lead.stage !== "merged" ? <LeadNoteComposer leadId={lead.id} /> : null}
            <LeadTimeline leadId={lead.id} />
          </CardContent>
        </Card>
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
      <div className="flex min-w-0 flex-col gap-4">
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-20" />
          </CardHeader>
          <CardContent>
            <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              {Array.from({ length: DETAIL_ROW_COUNT }, (_, index) => (
                <div key={index} className="flex flex-col gap-1">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-5 w-36" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-0.5">
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-5 w-56" />
            </div>
          </CardHeader>
          <CardContent>
            <LeadTimelineSkeleton />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
