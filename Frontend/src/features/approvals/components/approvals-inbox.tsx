"use client";

import { CheckmarkBadge01Icon, Invoice03Icon, PackageIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { parseAsBoolean, useQueryState } from "nuqs";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Checkbox } from "@/components/ui/checkbox";
import { Icon } from "@/components/ui/icon";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { approvalQueueQueryOptions } from "@/features/approvals/api/approvals.queries";
import type { QueueRow } from "@/features/approvals/api/approvals.schemas";
import {
  DOC_TYPE_LABELS,
  documentTitle,
  stepOwnerLabel,
} from "@/features/approvals/lib/approval-labels";
import { formatRate } from "@/features/quotations/lib/quotation-labels";
import { roleLabel } from "@/features/quotations/lib/quotation-lifecycle";
import { useCanApprove, useSession } from "@/features/session/hooks/use-session";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatCount, formatInr } from "@/lib/format";

import { ApprovalDecisionDialog, type PendingDecision } from "./approval-decision-dialog";

const SKELETON_ROWS = 3;

/** The backend's approving role for the signed-in user's role, where the names differ. */
function approvingRole(code: string | null): string | null {
  return code === "admin" ? "admin_sales" : code;
}

/**
 * APPR-001 · What waits on the signed-in manager, oldest first: quotation discounts and sales
 * orders side by side. Each row says what is asked, by whom and since when, and is approved
 * or rejected in place. "Include steps below me" (kept in the URL) adds lower managers'
 * steps, to cover one on leave; a stalled step — nobody of its role covers it — always shows.
 * The inbox re-reads itself every minute.
 */
export function ApprovalsInbox(): React.JSX.Element {
  const [includeBelow, setIncludeBelow] = useQueryState("below", parseAsBoolean.withDefault(false));
  const query = useInfiniteQuery(approvalQueueQueryOptions({ includeBelow }));
  const canApprove = useCanApprove();
  const session = useSession();
  const myRole = approvingRole(session.data?.role?.code ?? null);
  const [pending, setPending] = useState<PendingDecision | null>(null);
  const total = query.data?.pages[0]?.total ?? null;
  const capped = query.data?.pages[0]?.totalCapped ?? false;

  return (
    <section aria-label="Approvals" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p aria-live="polite" className="text-sm text-muted-foreground">
          {total === null
            ? "Requests waiting for your decision, oldest first."
            : total === 0
              ? "Nothing is waiting for you."
              : `${formatCount(total, { atLeast: capped })} waiting for your decision, oldest first.`}
        </p>
        <div className="flex items-center gap-2">
          <Checkbox
            id="approvals-include-below"
            checked={includeBelow}
            onCheckedChange={(checked) => {
              void setIncludeBelow(checked ? true : null);
            }}
          />
          <Label htmlFor="approvals-include-below" className="text-sm">
            Include steps below me
          </Label>
        </div>
      </div>

      <QueryView
        query={query}
        pending={<ApprovalsInboxSkeleton />}
        isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
        empty={
          <EmptyState
            icon={CheckmarkBadge01Icon}
            title="Nothing waits on you"
            description={
              includeBelow
                ? "No request is waiting at your level or below. New ones appear here; the page checks every minute."
                : "New requests appear here; the page checks every minute. Covering for a manager on leave? Include steps below you."
            }
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <ol
              aria-label="Waiting for your decision, oldest first"
              className="flex flex-col gap-3"
            >
              {data.pages.flatMap((page) =>
                page.items.map((row) => (
                  <ApprovalRow
                    key={row.stepId}
                    row={row}
                    mine={row.role === myRole}
                    canDecide={canApprove}
                    onDecide={(decision) => {
                      setPending({ row, decision });
                    }}
                  />
                )),
              )}
            </ol>
            {query.hasNextPage ? (
              <div className="flex flex-col items-start gap-2">
                {query.isFetchNextPageError ? (
                  <p role="alert" className="text-xs text-danger">
                    {toUserFacingError(query.error).title}. The requests above are still current.
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
                  {query.isFetchNextPageError ? "Try again" : "Show more"}
                </Button>
              </div>
            ) : null}
          </div>
        )}
      </QueryView>

      <ApprovalDecisionDialog
        pending={pending}
        onClose={() => {
          setPending(null);
        }}
      />
    </section>
  );
}

function ApprovalRow({
  row,
  mine,
  canDecide,
  onDecide,
}: {
  row: QueueRow;
  /** The step waits on the user's own role; otherwise they are covering for someone. */
  mine: boolean;
  canDecide: boolean;
  onDecide: (decision: "approve" | "reject") => void;
}): React.JSX.Element {
  const { document } = row;
  const title = documentTitle(row.docType, document.number);

  return (
    <li
      aria-label={`${DOC_TYPE_LABELS[row.docType]}: ${title}, ${document.partyName}`}
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={row.docType === "quotation" ? "primary" : "info"}>
              {DOC_TYPE_LABELS[row.docType]}
            </Badge>
            <span className="font-mono text-sm font-semibold text-foreground">{title}</span>
            {row.stalled ? (
              <Badge variant="warning">No {roleLabel(row.role)} to decide</Badge>
            ) : null}
            {!mine && !row.stalled ? (
              <Badge variant="outline">{stepOwnerLabel(row.role)}</Badge>
            ) : null}
          </div>
          <p className="truncate text-base font-medium text-foreground">{document.partyName}</p>
          <p className="text-xs text-muted-foreground">
            {document.raisedBy === null ? "Raised" : `Raised by ${document.raisedBy.name}`}{" "}
            <RelativeDate value={document.raisedAt} /> · waiting since{" "}
            <RelativeDate value={row.waitingSince} />
          </p>
        </div>
        <div className="flex shrink-0 flex-row items-baseline gap-3 sm:flex-col sm:items-end sm:gap-1">
          <span className="text-lg font-semibold text-foreground tabular-nums">
            {formatInr(document.total, { paise: true })}
          </span>
          {document.discountPct === null ? null : (
            <span className="text-sm font-medium text-warning">
              {formatRate(document.discountPct)} discount asked
            </span>
          )}
          {document.isProvisional ? (
            <span className="text-xs text-muted-foreground">Indicative pricing</span>
          ) : null}
        </div>
      </div>

      <div className="flex flex-col-reverse gap-2 border-t border-border pt-3 sm:flex-row sm:items-center sm:justify-between">
        {row.docType === "quotation" ? (
          <Link
            href={`/quotations/${document.id}`}
            className={buttonVariants({ variant: "ghost", size: "sm", className: "self-start" })}
          >
            <Icon icon={Invoice03Icon} />
            Open the quotation
          </Link>
        ) : (
          <Link
            href={`/sales-orders/${document.id}`}
            className={buttonVariants({ variant: "ghost", size: "sm", className: "self-start" })}
          >
            <Icon icon={PackageIcon} />
            Open the order
          </Link>
        )}
        {canDecide ? (
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1 sm:flex-none"
              aria-label={`Reject ${title} for ${document.partyName}`}
              onClick={() => {
                onDecide("reject");
              }}
            >
              Reject
            </Button>
            <Button
              className="flex-1 sm:flex-none"
              aria-label={`Approve ${title} for ${document.partyName}`}
              onClick={() => {
                onDecide("approve");
              }}
            >
              Approve
            </Button>
          </div>
        ) : null}
      </div>
    </li>
  );
}

export function ApprovalsInboxSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading approvals" className="flex flex-col gap-3">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} className="flex flex-col gap-3 rounded-xl border border-border p-4 sm:p-5">
          <div className="flex justify-between gap-4">
            <div className="flex flex-col gap-2">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-3 w-56" />
            </div>
            <Skeleton className="h-6 w-28" />
          </div>
          <Skeleton className="h-9 w-full" />
        </div>
      ))}
    </div>
  );
}
