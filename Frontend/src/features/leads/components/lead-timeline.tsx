"use client";

import {
  Activity01Icon,
  ArrowRight02Icon,
  CheckmarkBadge01Icon,
  Clock01Icon,
  Copy01Icon,
  Delete02Icon,
  Edit02Icon,
  GitMergeIcon,
  Invoice03Icon,
  Note01Icon,
  PlusSignCircleIcon,
  RotateLeft01Icon,
  UserSwitchIcon,
} from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Button } from "@/components/ui/button";
import { Icon, type IconGlyph } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { leadTimelineQueryOptions } from "@/features/leads/api/leads.queries";
import type { LeadStage, TimelineEvent } from "@/features/leads/api/leads.schemas";
import { LEAD_STAGE_LABELS } from "@/features/leads/lib/lead-labels";
import {
  joinFields,
  toTimelineEntry,
  type ChangeKind,
  type TimelineDocument,
  type TimelineEntry,
} from "@/features/leads/lib/timeline-entries";
import { lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";
import { LookupName } from "@/features/lookups/components/lookup-name";
import { findLookupNameById } from "@/features/lookups/lib/lookup-labels";
import { stepRoleLabel } from "@/features/orders/lib/order-labels";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Rows the skeleton draws — about what a fresh lead's first screen shows. */
const SKELETON_ROWS = 3;

type Tone = "neutral" | "primary" | "info" | "success" | "warning" | "danger";

const TONE_CLASSES: Readonly<Record<Tone, string>> = {
  neutral: "bg-muted text-muted-foreground",
  primary: "bg-primary-soft text-primary-text",
  info: "bg-info-soft text-info",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
};

export interface LeadTimelineProps {
  leadId: string;
}

/**
 * LEAD-005 · The lead's history, newest first: notes, stage changes, assignments, edits,
 * merges and the quotation and order events that touch the lead. "Show older activity"
 * loads the next page; a failure there keeps what is shown and offers a retry.
 */
export function LeadTimeline({ leadId }: LeadTimelineProps): React.JSX.Element {
  const query = useInfiniteQuery(leadTimelineQueryOptions(leadId));

  return (
    <QueryView
      query={query}
      pending={<LeadTimelineSkeleton />}
      isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
      empty={
        <EmptyState
          icon={Clock01Icon}
          title="No activity yet"
          description="Notes and every change to this lead will show here."
        />
      }
    >
      {(data) => (
        <div className="flex flex-col gap-4">
          <ol aria-label="Lead activity, newest first" className="flex flex-col">
            {data.pages.flatMap((page) =>
              page.items.map((event) => (
                <TimelineItem key={event.id} event={event} leadId={leadId} />
              )),
            )}
          </ol>
          {query.hasNextPage ? (
            <div className="flex flex-col items-start gap-2 pl-11">
              {query.isFetchNextPageError ? (
                <p role="alert" className="text-xs text-danger">
                  {toUserFacingError(query.error).title}. The activity above is still current.
                </p>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                state={query.isFetchingNextPage ? "loading" : "idle"}
                loadingLabel="Loading…"
                onClick={() => {
                  void query.fetchNextPage();
                }}
              >
                {query.isFetchNextPageError ? "Try again" : "Show older activity"}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </QueryView>
  );
}

function TimelineItem({
  event,
  leadId,
}: {
  event: TimelineEvent;
  leadId: string;
}): React.JSX.Element {
  const entry = toTimelineEntry(event, leadId);
  const { icon, tone } = appearanceOf(entry);

  return (
    <li className="group relative flex gap-3 pb-5 last:pb-0">
      {/* The rail joins one entry's icon to the next; the last entry has none. */}
      <span
        aria-hidden="true"
        className="absolute top-9 bottom-1 left-4 w-px bg-border group-last:hidden"
      />
      <span
        aria-hidden="true"
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-full",
          TONE_CLASSES[tone],
        )}
      >
        <Icon icon={icon} size="md" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1 pt-1">
        <p className="text-sm text-foreground">
          <span className="font-medium">{event.actor?.name ?? "Polysil"}</span>{" "}
          <EntrySentence entry={entry} />
        </p>
        <RelativeDate value={event.occurredAt} className="text-xs text-muted-foreground" />
        <EntryDetail entry={entry} />
      </div>
    </li>
  );
}

/** Red for lost, green for won, blue for every other move. */
function stageTone(to: LeadStage | null): Tone {
  if (to === "lost") {
    return "danger";
  }
  if (to === "won") {
    return "success";
  }
  return "info";
}

function appearanceOf(entry: TimelineEntry): { icon: IconGlyph; tone: Tone } {
  switch (entry.type) {
    case "created":
      return { icon: PlusSignCircleIcon, tone: "primary" };
    case "note":
      return { icon: Note01Icon, tone: "primary" };
    case "stage":
      return { icon: ArrowRight02Icon, tone: stageTone(entry.to) };
    case "reopened":
      return { icon: RotateLeft01Icon, tone: "warning" };
    case "assigned":
      return { icon: UserSwitchIcon, tone: "info" };
    case "updated":
      return { icon: Edit02Icon, tone: "neutral" };
    case "merged":
      return { icon: GitMergeIcon, tone: "neutral" };
    case "duplicate-flagged":
    case "duplicate-dismissed":
      return { icon: Copy01Icon, tone: "warning" };
    case "deleted":
      return { icon: Delete02Icon, tone: "danger" };
    case "approval":
      return {
        icon: CheckmarkBadge01Icon,
        tone:
          entry.decision === "approve"
            ? "success"
            : entry.decision === "reject"
              ? "danger"
              : "neutral",
      };
    case "document":
      return { icon: Invoice03Icon, tone: "neutral" };
    case "other":
      return { icon: Activity01Icon, tone: "neutral" };
  }
}

/** "approved the District Manager step" — the step by its desk, as approvals name it. */
function approvalSentence(decision: "approve" | "reject" | null, role: string | null): string {
  const step = role === null ? "an approval step" : `the ${stepRoleLabel(role)} step`;
  if (decision === "approve") {
    return `approved ${step}`;
  }
  return decision === "reject" ? `returned it at ${step}` : `decided ${step}`;
}

function DocumentLink({ document }: { document: TimelineDocument }): React.JSX.Element {
  return (
    <Link
      href={
        document.kind === "quotation"
          ? `/quotations/${document.id}`
          : `/sales-orders/${document.id}`
      }
      className="font-mono text-primary-text underline-offset-4 hover:underline"
    >
      {document.title}
    </Link>
  );
}

function stageName(stage: LeadStage | null): string {
  return stage === null ? "another stage" : LEAD_STAGE_LABELS[stage];
}

function assignmentSentence(owner: ChangeKind, partner: ChangeKind): string {
  if (owner === "set" && partner === "set") {
    return "changed the owner and the channel partner";
  }
  const parts: string[] = [];
  if (owner === "set") parts.push("changed the owner");
  if (owner === "cleared") parts.push("unassigned the owner");
  if (partner === "set") parts.push("changed the channel partner");
  if (partner === "cleared") parts.push("removed the channel partner");
  return parts.length === 0 ? "updated the assignment" : parts.join(" and ");
}

/** What the actor did, as the rest of a sentence that starts with their name. */
function EntrySentence({ entry }: { entry: TimelineEntry }): React.JSX.Element {
  switch (entry.type) {
    case "created":
      return (
        <>
          created the lead
          {entry.source === null ? null : (
            <>
              {" "}
              from <LookupName list="lead-sources" code={entry.source} />
            </>
          )}
        </>
      );
    case "note":
      return <>added a note</>;
    case "stage":
      return entry.from === null ? (
        <>moved the lead to {stageName(entry.to)}</>
      ) : (
        <>
          moved the lead from {stageName(entry.from)} to {stageName(entry.to)}
        </>
      );
    case "reopened":
      return <>reopened the lead{entry.to === null ? null : <> at {stageName(entry.to)}</>}</>;
    case "assigned":
      return <>{assignmentSentence(entry.owner, entry.partner)}</>;
    case "updated":
      return entry.fields.length === 0 ? (
        <>edited the lead</>
      ) : (
        <>changed the {joinFields(entry.fields)}</>
      );
    case "merged":
      return entry.role === "survivor" ? (
        <>
          merged{" "}
          <Link
            href={`/leads/${entry.otherLeadId}`}
            className="text-primary-text underline-offset-4 hover:underline"
          >
            another lead
          </Link>{" "}
          into this one
        </>
      ) : (
        <>
          merged this lead into{" "}
          <Link
            href={`/leads/${entry.otherLeadId}`}
            className="text-primary-text underline-offset-4 hover:underline"
          >
            another lead
          </Link>
        </>
      );
    case "duplicate-flagged":
      return entry.count === 1 ? (
        <>flagged a possible duplicate</>
      ) : (
        <>flagged {formatNumber(entry.count)} possible duplicates</>
      );
    case "duplicate-dismissed":
      return <>dismissed a possible duplicate</>;
    case "deleted":
      return <>deleted the lead</>;
    case "approval":
      return <>{approvalSentence(entry.decision, entry.role)}</>;
    case "document":
      return (
        <>
          · {entry.label}
          {entry.document === null ? null : (
            <>
              {" "}
              <DocumentLink document={entry.document} />
            </>
          )}
          {entry.dispatchNo === null ? null : (
            <>
              {" "}
              <span className="font-mono">{entry.dispatchNo}</span>
            </>
          )}
        </>
      );
    case "other":
      return <>· {entry.label}</>;
  }
}

/** A quoted block under the sentence: the note, the lost reason, the reopening note. */
function EntryDetail({ entry }: { entry: TimelineEntry }): React.JSX.Element | null {
  if (entry.type === "note") {
    return <Quote>{entry.note}</Quote>;
  }
  if (entry.type === "reopened" && entry.note !== null) {
    return <Quote>{entry.note}</Quote>;
  }
  if (entry.type === "stage" && entry.to === "lost") {
    return <LostDetail reasonId={entry.lostReasonId} note={entry.lostNote} />;
  }
  return null;
}

function LostDetail({
  reasonId,
  note,
}: {
  reasonId: string | null;
  note: string | null;
}): React.JSX.Element | null {
  const { data: reasons } = useQuery(lookupListQueryOptions("lost-reasons"));
  const reason = reasonId === null ? null : findLookupNameById(reasons, reasonId);

  if (reason === null && note === null) {
    return null;
  }
  return (
    <Quote>
      {reason === null ? null : <span className="font-medium">Reason: {reason}</span>}
      {reason !== null && note !== null ? <br /> : null}
      {note}
    </Quote>
  );
}

function Quote({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <p className="mt-1 rounded-md border border-border bg-panel px-3 py-2 text-sm wrap-break-word whitespace-pre-line text-foreground">
      {children}
    </p>
  );
}

/** Mirrors the timeline: an icon, a sentence and a time per row. */
export function LeadTimelineSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading activity" className="flex flex-col gap-5">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} className="flex gap-3">
          <Skeleton className="size-8 shrink-0 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5 pt-1">
            <Skeleton className="h-4 w-3/5" />
            <Skeleton className="h-3.5 w-20" />
          </div>
        </div>
      ))}
    </div>
  );
}
