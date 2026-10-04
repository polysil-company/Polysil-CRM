"use client";

import { ArrowLeft01Icon, Clock01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import {
  complaintDetailQueryOptions,
  complaintTimelineQueryOptions,
} from "@/features/complaints/api/complaints.queries";
import type { Complaint } from "@/features/complaints/api/complaints.schemas";
import {
  COMPLAINT_STATUS_BADGE,
  COMPLAINT_STATUS_LABELS,
  complaintHistoryEntry,
  SEVERITY_BADGE,
  SEVERITY_LABELS,
} from "@/features/complaints/lib/complaint-labels";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { formatDate, formatDateTime, formatIndianPhone, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import { AttachmentsCard } from "./attachments-card";
import { ComplaintActions } from "./complaint-actions";
import { RemedyCard } from "./remedy-card";

const DOT: Readonly<Record<string, string>> = {
  neutral: "bg-subtle-foreground",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

/**
 * CMPL-002 · One complaint: what happened and to what, who to contact, the products, the
 * files, the targets with their due times, the manager's check, the QC verdict, the remedy,
 * and the history. A returned draft says what to fix. Buttons follow the complaint's `can`.
 */
export function ComplaintDetail({ complaintId }: { complaintId: string }): React.JSX.Element {
  const query = useQuery(complaintDetailQueryOptions(complaintId));

  if (query.status === "pending") return <ComplaintDetailSkeleton />;
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
  return <ComplaintView complaint={query.data} />;
}

function Item({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm wrap-break-word text-foreground">{children}</dd>
    </div>
  );
}

function Missing({ text = "Not recorded" }: { text?: string }): React.JSX.Element {
  return <span className="text-subtle-foreground">{text}</span>;
}

function Notice({
  tone,
  title,
  children,
}: {
  tone: "warning" | "danger" | "neutral";
  title: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div
      role="note"
      className={cn(
        "flex flex-col gap-1 rounded-xl border p-3 text-sm sm:p-4",
        tone === "warning"
          ? "border-warning/40 bg-warning-soft"
          : tone === "danger"
            ? "border-danger/40 bg-danger-soft"
            : "border-border bg-muted",
      )}
    >
      <p className="font-medium text-foreground">{title}</p>
      <div className="text-pretty text-foreground">{children}</div>
    </div>
  );
}

function ComplaintView({ complaint }: { complaint: Complaint }): React.JSX.Element {
  const returned = complaint.status === "draft" && complaint.check?.decision === "return";
  const late =
    complaint.sla?.responseBreached === true || complaint.sla?.resolutionBreached === true;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Link
            href="/complaints"
            transitionTypes={["nav-back"]}
            className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
          >
            <Icon icon={ArrowLeft01Icon} size="sm" />
            All complaints
          </Link>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="truncate font-mono text-xl font-semibold text-foreground">
              {complaint.number ?? "Draft complaint"}
            </h2>
            <Badge variant={COMPLAINT_STATUS_BADGE[complaint.status]} dot>
              {COMPLAINT_STATUS_LABELS[complaint.status]}
            </Badge>
            <Badge variant={SEVERITY_BADGE[complaint.severity]}>
              {SEVERITY_LABELS[complaint.severity]}
            </Badge>
            {late ? <Badge variant="danger">Late</Badge> : null}
          </div>
          <p className="text-sm text-muted-foreground">
            {complaint.type.name} · {complaint.contactName} · {complaint.territory.name}
          </p>
        </div>
        <ComplaintActions complaint={complaint} />
      </div>

      {returned && complaint.check !== null ? (
        <Notice
          tone="warning"
          title={`Returned to fix${complaint.check.by === null ? "" : ` by ${complaint.check.by.name}`}`}
        >
          {complaint.check.remark} Edit the draft, then submit it again.
        </Notice>
      ) : null}
      {complaint.status === "cancelled" && complaint.cancellation !== null ? (
        <Notice
          tone="neutral"
          title={`Cancelled${complaint.cancellation.by === null ? "" : ` by ${complaint.cancellation.by.name}`}`}
        >
          {complaint.cancellation.reason}
        </Notice>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle level={3}>What happened</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <p className="text-sm text-pretty whitespace-pre-line text-foreground">
                {complaint.description}
              </p>
              <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
                <Item label="Contact">
                  {complaint.contactName} ·{" "}
                  <a
                    href={`tel:${complaint.contactMobile}`}
                    className="underline-offset-2 hover:underline"
                  >
                    {formatIndianPhone(complaint.contactMobile)}
                  </a>
                </Item>
                <Item label="Installed at">{complaint.territory.name}</Item>
                <Item label="Dealer">
                  {complaint.partner === null ? (
                    <Missing text="None" />
                  ) : complaint.partner.hidden ? (
                    <Missing text="Not visible to you" />
                  ) : (
                    complaint.partner.name
                  )}
                </Item>
                <Item label="Lead">
                  {complaint.lead === null ? (
                    <Missing text="None" />
                  ) : complaint.lead.hidden ? (
                    <Missing text="Not visible to you" />
                  ) : (
                    <Link
                      href={`/leads/${complaint.lead.id}`}
                      className="font-medium underline-offset-2 hover:underline"
                    >
                      {[complaint.lead.farmerName, complaint.lead.inquiryNo]
                        .filter(Boolean)
                        .join(" · ")}
                    </Link>
                  )}
                </Item>
                <Item label="Sales order">
                  {complaint.salesOrder === null ? (
                    <Missing text="None" />
                  ) : complaint.salesOrder.hidden ? (
                    <Missing text="Not visible to you" />
                  ) : (
                    <Link
                      href={`/sales-orders/${complaint.salesOrder.id}`}
                      className="font-medium underline-offset-2 hover:underline"
                    >
                      {complaint.salesOrder.orderNo ?? "Draft order"}
                    </Link>
                  )}
                </Item>
                <Item label="Challan">
                  {complaint.dcNo ?? <Missing text="Needed to submit" />}
                  {complaint.supplyDate === null
                    ? null
                    : ` · supplied ${formatDate(complaint.supplyDate)}`}
                </Item>
                {complaint.regNo === null ? null : (
                  <Item label="Registration number">{complaint.regNo}</Item>
                )}
                {complaint.pimsNo === null ? null : (
                  <Item label="PIMS number">{complaint.pimsNo}</Item>
                )}
                {complaint.sampleCourierDate === null &&
                complaint.sampleCourierDetail === null ? null : (
                  <Item label="Sample sent">
                    {[
                      complaint.sampleCourierDate === null
                        ? null
                        : formatDate(complaint.sampleCourierDate),
                      complaint.sampleCourierDetail,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </Item>
                )}
                <Item label="Owner">
                  {complaint.owner?.name ?? <Missing text="No owner yet" />}
                </Item>
                <Item label="Raised">
                  {complaint.raisedBy?.name ?? "—"} · <RelativeDate value={complaint.createdAt} />
                </Item>
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle level={3}>Products</CardTitle>
            </CardHeader>
            <CardContent>
              <ul aria-label="Products" className="flex flex-col divide-y divide-border">
                {complaint.lines.map((line) => (
                  <li
                    key={line.id}
                    className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4"
                  >
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <p className="text-sm font-medium text-foreground">
                        {line.product.description}
                      </p>
                      {line.failureFrequency === null && line.remark === null ? null : (
                        <p className="text-xs text-muted-foreground">
                          {[
                            line.failureFrequency === null
                              ? null
                              : `Fails ${line.failureFrequency}`,
                            line.remark,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                      )}
                    </div>
                    <p className="shrink-0 text-sm text-muted-foreground tabular-nums">
                      <span
                        className={cn(Number(line.defectiveQty) > 0 && "font-semibold text-danger")}
                      >
                        {formatNumber(Number(line.defectiveQty), 2)} defective
                      </span>{" "}
                      of {formatNumber(Number(line.suppliedQty), 2)} {line.uom ?? ""}
                    </p>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <AttachmentsCard complaint={complaint} />

          <Card>
            <CardHeader>
              <div className="flex flex-col gap-0.5">
                <CardTitle level={3}>History</CardTitle>
                <CardDescription>Newest first</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <ComplaintHistory complaintId={complaint.id} />
            </CardContent>
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <RemedyCard complaint={complaint} />
          <TargetsCard complaint={complaint} />
          {complaint.check === null || returned ? null : (
            <DecisionCard
              title="Manager's check"
              verdict={complaint.check.decision === "approve" ? "Approved" : "Returned"}
              good={complaint.check.decision === "approve"}
              remark={complaint.check.remark}
              by={complaint.check.by?.name ?? null}
              at={complaint.check.at}
              note={complaint.check.internalNote}
            />
          )}
          {complaint.quality === null ? null : (
            <DecisionCard
              title="QC verdict"
              verdict={
                complaint.quality.verdict === "approved"
                  ? "Approved: a defect"
                  : "Rejected: no defect"
              }
              good={complaint.quality.verdict === "approved"}
              remark={complaint.quality.remark}
              by={complaint.quality.by?.name ?? null}
              at={complaint.quality.at}
              note={complaint.quality.internalNote}
              extra={[
                complaint.quality.sampleReceivedOn === null
                  ? null
                  : `Sample received ${formatDate(complaint.quality.sampleReceivedOn)}`,
                complaint.quality.testedOn === null
                  ? null
                  : `Tested ${formatDate(complaint.quality.testedOn)}`,
                complaint.quality.fieldVisitOn === null
                  ? null
                  : `Field visit ${formatDate(complaint.quality.fieldVisitOn)}`,
              ].filter((part): part is string => part !== null)}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/** The response and resolution targets, with their due times; "no target" is never red. */
function TargetsCard({ complaint }: { complaint: Complaint }): React.JSX.Element {
  const { sla } = complaint;
  return (
    <Card>
      <CardHeader>
        <CardTitle level={3}>Targets</CardTitle>
      </CardHeader>
      <CardContent>
        {sla === null ? (
          <p className="text-sm text-muted-foreground">
            They start when the complaint is submitted.
          </p>
        ) : sla.policy === "none" ? (
          <p className="text-sm text-muted-foreground">No target applies to this complaint.</p>
        ) : (
          <dl className="flex flex-col gap-3">
            <Target
              label="First response"
              due={sla.responseDueAt}
              met={sla.respondedAt}
              breached={sla.responseBreached}
            />
            <Target
              label="Resolution"
              due={sla.resolutionDueAt}
              met={sla.resolvedAt}
              breached={sla.resolutionBreached}
            />
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

function Target({
  label,
  due,
  met,
  breached,
}: {
  label: string;
  due: string | null;
  met: string | null;
  breached: boolean;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="flex items-center gap-2 text-xs text-muted-foreground">
        {label}
        {breached ? (
          <Badge variant="danger" size="sm">
            Missed
          </Badge>
        ) : met !== null ? (
          <Badge variant="success" size="sm">
            Met
          </Badge>
        ) : null}
      </dt>
      <dd className="text-sm text-foreground">
        {met !== null
          ? `Done ${formatDateTime(met)}`
          : due === null
            ? "—"
            : `Due ${formatDateTime(due)}`}
        {met !== null && due !== null ? (
          <span className="text-muted-foreground"> · due {formatDateTime(due)}</span>
        ) : null}
      </dd>
    </div>
  );
}

function DecisionCard({
  title,
  verdict,
  good,
  remark,
  by,
  at,
  note,
  extra = [],
}: {
  title: string;
  verdict: string;
  good: boolean;
  remark: string;
  by: string | null;
  at: string;
  note: string | null;
  extra?: readonly string[];
}): React.JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle level={3}>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <Badge variant={good ? "success" : "danger"}>{verdict}</Badge>
        <p className="text-sm text-pretty text-foreground">{remark}</p>
        {extra.length === 0 ? null : (
          <p className="text-xs text-muted-foreground">{extra.join(" · ")}</p>
        )}
        {note === null ? null : (
          <p className="rounded-md bg-muted p-2 text-xs text-muted-foreground">
            <span className="font-medium">Internal note:</span> {note}
          </p>
        )}
        <p className="text-xs text-subtle-foreground">
          {by === null ? "" : `${by} · `}
          <RelativeDate value={at} />
        </p>
      </CardContent>
    </Card>
  );
}

function ComplaintHistory({ complaintId }: { complaintId: string }): React.JSX.Element {
  const query = useInfiniteQuery(complaintTimelineQueryOptions(complaintId));
  if (query.status === "pending") {
    return (
      <div role="status" aria-label="Loading the history" className="flex flex-col gap-3">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-4 w-40" />
      </div>
    );
  }
  if (query.status === "error") {
    return (
      <div className="flex flex-col items-start gap-2">
        <p role="alert" className="text-sm text-muted-foreground">
          {toUserFacingError(query.error).title}.
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            void query.refetch();
          }}
        >
          Try again
        </Button>
      </div>
    );
  }
  const events = query.data.pages.flatMap((page) => page.items);
  if (events.length === 0) {
    return (
      <EmptyState icon={Clock01Icon} title="No history yet" description="Every step shows here." />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <ol aria-label="Complaint history, newest first" className="flex flex-col">
        {events.map((event) => {
          const entry = complaintHistoryEntry(event.kind, event.payload);
          return (
            <li key={event.id} className="group relative flex gap-3 pb-4 last:pb-0">
              <span
                aria-hidden="true"
                className="absolute top-4 bottom-0 left-1 w-px bg-border group-last:hidden"
              />
              <span
                aria-hidden="true"
                className={cn("mt-1.5 size-2 shrink-0 rounded-full", DOT[entry.tone])}
              />
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <p className="text-sm text-foreground">
                  <span className="font-medium">{entry.title}</span>
                  {event.actor?.name == null ? null : (
                    <span className="text-muted-foreground"> · {event.actor.name}</span>
                  )}
                </p>
                {entry.detail === null ? null : (
                  <p className="text-sm wrap-break-word whitespace-pre-line text-muted-foreground">
                    {entry.detail}
                  </p>
                )}
                <RelativeDate value={event.occurredAt} className="text-xs text-muted-foreground" />
              </div>
            </li>
          );
        })}
      </ol>
      {query.hasNextPage ? (
        <Button
          variant="outline"
          size="sm"
          className="self-start"
          state={query.isFetchingNextPage ? "loading" : "idle"}
          loadingLabel="Loading…"
          onClick={() => {
            void query.fetchNextPage();
          }}
        >
          Show older
        </Button>
      ) : null}
    </div>
  );
}

export function ComplaintDetailSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the complaint" className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-4 w-56" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-64 rounded-xl lg:col-span-2" />
        <Skeleton className="h-40 rounded-xl" />
      </div>
    </div>
  );
}
