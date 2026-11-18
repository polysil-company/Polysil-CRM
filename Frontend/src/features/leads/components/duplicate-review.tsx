"use client";

import { ArrowLeft01Icon, UserMultiple02Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useDismissDuplicate, useMergeLead } from "@/features/leads/api/leads.mutations";
import { duplicatesQueryOptions } from "@/features/leads/api/leads.queries";
import type { DuplicatePair, Lead } from "@/features/leads/api/leads.schemas";
import { DUPLICATE_SIGNAL_LABELS } from "@/features/leads/lib/lead-labels";
import { formatTerritory } from "@/features/lookups/lib/lookup-labels";
import { useCan } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { formatIndianPhone, formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { LeadStageBadge } from "./lead-stage-badge";

const log = createLogger({
  file: "features/leads/components/duplicate-review.tsx",
  dataId: "LEAD-012",
});

const CLOSED_STAGES: ReadonlySet<Lead["stage"]> = new Set(["won", "lost", "merged"]);

/** A merge the user picked: `loser` folds into `survivor`. */
interface MergeChoice {
  readonly pair: DuplicatePair;
  readonly survivor: Lead;
  readonly loser: Lead;
}

/** The backend's merge refusals in plain words. */
function mergeRefusal(error: unknown): { title: string; description: string } {
  if (isApiError(error) && error.code === "merge_terminal") {
    return {
      title: "One of them is closed",
      description:
        "A won, lost or merged lead can't be merged. Reopen it first, or dismiss the pair.",
    };
  }
  const view = toUserFacingError(error);
  return { title: view.title, description: view.description };
}

/**
 * LEAD-012 · Possible duplicates, newest first: each pair side by side with what matched. Keep
 * one and merge the other into it — the merged lead's history moves to the one kept, and it
 * points there from then on — or mark the pair "Not a duplicate". Both need `leads.edit`.
 */
export function DuplicateReview(): React.JSX.Element {
  const query = useInfiniteQuery(duplicatesQueryOptions());
  const canDecide = useCan("leads", "edit");
  const [merging, setMerging] = useState<MergeChoice | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Link
          href="/leads"
          transitionTypes={["nav-back"]}
          className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
        >
          <Icon icon={ArrowLeft01Icon} size="sm" />
          All leads
        </Link>
        <h2 className="text-xl font-semibold text-foreground">Possible duplicates</h2>
        <p className="max-w-prose text-sm text-muted-foreground">
          Leads that share a mobile, an email, or a name in the same place. Keep one and merge the
          other into it, or mark them as different people.
        </p>
      </div>

      <QueryView
        query={query}
        pending={<DuplicateReviewSkeleton />}
        isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
        empty={
          <EmptyState
            icon={UserMultiple02Icon}
            title="No possible duplicates"
            description="When a new lead matches one you can see, the pair waits here for review."
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <ul aria-label="Possible duplicates" className="flex flex-col gap-3">
              {data.pages.flatMap((page) =>
                page.items.map((pair) => (
                  <PairCard
                    key={pair.linkId}
                    pair={pair}
                    canDecide={canDecide}
                    onMerge={(survivor, loser) => {
                      setMerging({ pair, survivor, loser });
                    }}
                  />
                )),
              )}
            </ul>
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
                Show more
              </Button>
            ) : null}
          </div>
        )}
      </QueryView>

      <Dialog
        open={merging !== null}
        onOpenChange={(open) => {
          if (!open) setMerging(null);
        }}
      >
        <DialogContent size="sm">
          {merging === null ? null : (
            <MergeForm
              choice={merging}
              onClose={() => {
                setMerging(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PairCard({
  pair,
  canDecide,
  onMerge,
}: {
  pair: DuplicatePair;
  canDecide: boolean;
  onMerge: (survivor: Lead, loser: Lead) => void;
}): React.JSX.Element {
  const dismiss = useDismissDuplicate();
  const idempotency = useIdempotencyKey();
  const run = useAsyncAction({
    action: () =>
      dismiss.mutateAsync({
        linkId: pair.linkId,
        idempotencyKey: idempotency.keyFor({ dismiss: pair.linkId }),
      }),
    logger: log,
    fn: "handleDismissDuplicate",
    dataId: "LEAD-012",
    onSuccess: () => {
      toast.success("Marked as different people", {
        description: `${pair.leadA.code} and ${pair.leadB.code}`,
      });
    },
    onError: (error) => {
      const view = toUserFacingError(error);
      toast.error(view.title, { description: view.description });
    },
  });
  const label = `${pair.leadA.customerName} and ${pair.leadB.customerName}`;
  // The backend refuses to merge a won, lost or merged lead (merge_terminal).
  const closed = [pair.leadA, pair.leadB].some((lead) => CLOSED_STAGES.has(lead.stage));

  return (
    <li
      aria-label={label}
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 sm:p-4"
    >
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="warning">{DUPLICATE_SIGNAL_LABELS[pair.signal]}</Badge>
        {pair.score === null ? null : (
          <span className="text-xs text-muted-foreground">
            Match {Math.round(Number(pair.score) * 100)}%
          </span>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          Flagged <RelativeDate value={pair.createdAt} />
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <LeadSide lead={pair.leadA} />
        <LeadSide lead={pair.leadB} />
      </div>
      {canDecide ? (
        <div className="flex flex-wrap gap-2">
          {closed ? (
            <p role="note" className="w-full text-xs text-muted-foreground">
              One of them is closed, so they can&apos;t be merged. Reopen it first, or mark them as
              different people.
            </p>
          ) : (
            <>
              <Button
                size="sm"
                onClick={() => {
                  onMerge(pair.leadA, pair.leadB);
                }}
              >
                Keep {pair.leadA.code}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  onMerge(pair.leadB, pair.leadA);
                }}
              >
                Keep {pair.leadB.code}
              </Button>
            </>
          )}
          <Button
            size="sm"
            variant="ghost"
            state={run.state}
            loadingLabel="Saving…"
            successLabel="Done"
            errorLabel="Not saved"
            onClick={() => {
              void run.run();
            }}
          >
            Not a duplicate
          </Button>
        </div>
      ) : null}
    </li>
  );
}

function LeadSide({ lead }: { lead: Lead }): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-lg border border-border p-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Link
          href={`/leads/${lead.id}`}
          className="truncate font-medium text-foreground underline-offset-4 hover:underline"
        >
          {lead.customerName}
        </Link>
        <LeadStageBadge stage={lead.stage} />
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
        <dt className="text-muted-foreground">Inquiry</dt>
        <dd className="font-mono text-foreground">{lead.code}</dd>
        <dt className="text-muted-foreground">Mobile</dt>
        <dd className="text-foreground">{formatIndianPhone(lead.phone)}</dd>
        <dt className="text-muted-foreground">Place</dt>
        <dd className="truncate text-foreground">
          {[lead.village, formatTerritory(lead.territory)].filter(Boolean).join(", ")}
        </dd>
        <dt className="text-muted-foreground">Owner</dt>
        <dd className="text-foreground">{lead.owner?.name ?? "Unassigned"}</dd>
        <dt className="text-muted-foreground">Value</dt>
        <dd className="text-foreground">
          {lead.estimatedValue === null ? "—" : formatInr(lead.estimatedValue)}
        </dd>
      </dl>
      <p className="text-xs text-subtle-foreground">
        Created <RelativeDate value={lead.createdAt} />
      </p>
    </div>
  );
}

function MergeForm({
  choice,
  onClose,
}: {
  choice: MergeChoice;
  onClose: () => void;
}): React.JSX.Element {
  const merge = useMergeLead();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<{ title: string; description: string } | null>(null);
  const { survivor, loser } = choice;
  const run = useAsyncAction({
    action: () => {
      const body = { into_lead_id: survivor.id };
      return merge.mutateAsync({
        leadId: loser.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: loser.id, ...body }),
      });
    },
    logger: log,
    fn: "handleMergeLead",
    dataId: "LEAD-012",
    onSuccess: () => {
      toast.success("Leads merged", { description: `${loser.code} → ${survivor.code}` });
      onClose();
    },
    onError: (error) => {
      setRefusal(mergeRefusal(error));
    },
  });

  return (
    <>
      <DialogHeader>
        <DialogTitle>Keep {survivor.code}?</DialogTitle>
        <DialogDescription>
          {loser.code} ({loser.customerName}) is merged into it: its history moves across, and it
          points to {survivor.code} from now on. This can&apos;t be undone.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        {refusal === null ? null : (
          <div
            role="alert"
            className="flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
          >
            <p className="font-medium text-danger">{refusal.title}</p>
            <p className="text-muted-foreground">{refusal.description}</p>
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={run.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          state={run.state}
          loadingLabel="Merging…"
          successLabel="Merged"
          errorLabel="Not merged"
          onClick={() => {
            setRefusal(null);
            void run.run();
          }}
        >
          Merge into {survivor.code}
        </Button>
      </DialogFooter>
    </>
  );
}

export function DuplicateReviewSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading possible duplicates" className="flex flex-col gap-3">
      {[0, 1].map((key) => (
        <div key={key} className="flex flex-col gap-3 rounded-xl border border-border p-4">
          <Skeleton className="h-5 w-40" />
          <div className="grid gap-3 md:grid-cols-2">
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
        </div>
      ))}
    </div>
  );
}
