"use client";

import { GiftIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { RedemptionDecision } from "@/features/rewards/api/rewards.api";
import { redemptionsQueryOptions } from "@/features/rewards/api/rewards.queries";
import type { Redemption } from "@/features/rewards/api/rewards.schemas";
import {
  REDEMPTION_STATUS_BADGE,
  REDEMPTION_STATUS_LABELS,
  pointsText,
} from "@/features/rewards/lib/reward-labels";
import { formatCount } from "@/lib/format";

import { RedemptionDecisionForm } from "./reward-dialogs";

const VIEWS = ["waiting", "all"] as const;
type View = (typeof VIEWS)[number];

/**
 * RWD-002 · The gift desk: what dealers asked for, newest first. Mark a gift
 * sent, or refuse it with a reason (the points go back). Not for the one who asked.
 */
export function GiftDesk(): React.JSX.Element {
  const [view, setView] = useState<View>("waiting");
  const query = useInfiniteQuery(
    redemptionsQueryOptions({ status: view === "waiting" ? "pending" : null, kind: "gift" }),
  );
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];
  const [opened, setOpened] = useState<{
    redemption: Redemption;
    decision: RedemptionDecision;
  } | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <ToggleGroup
        aria-label="Which requests"
        value={[view]}
        onValueChange={(next) => {
          const chosen = VIEWS.find((value) => value === next[0]);
          if (chosen !== undefined) setView(chosen);
        }}
      >
        <ToggleGroupItem value="waiting">Waiting</ToggleGroupItem>
        <ToggleGroupItem value="all">All</ToggleGroupItem>
      </ToggleGroup>

      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading requests" className="flex flex-col gap-2">
          {[0, 1].map((row) => (
            <Skeleton key={row} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={GiftIcon}
          title={view === "waiting" ? "Nothing waiting" : "No gift requests yet"}
          description="When a dealer asks for a gift, it waits here to be sent or refused."
          className="rounded-xl border border-dashed border-border"
        />
      ) : (
        <div className="flex flex-col gap-3">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {formatCount(rows.length)} {rows.length === 1 ? "request" : "requests"}, newest first.
          </p>
          <ul aria-label="Gift requests" className="flex flex-col gap-2">
            {rows.map((row) => (
              <li
                key={row.id}
                className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4"
              >
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
                    {row.gift?.name ?? "A gift"}
                    <Badge variant={REDEMPTION_STATUS_BADGE[row.status]} size="sm" dot>
                      {REDEMPTION_STATUS_LABELS[row.status]}
                    </Badge>
                  </span>
                  <span className="text-sm text-foreground">
                    {row.holder.name ?? "A dealer"} · {pointsText(row.points)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Asked <RelativeDate value={row.createdAt} />
                    {row.remark === null ? "" : ` · ${row.remark}`}
                  </span>
                </span>
                {row.status === "pending" ? (
                  <span className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      aria-label={`Mark ${row.gift?.name ?? "the gift"} sent to ${row.holder.name ?? "the dealer"}`}
                      onClick={() => {
                        setOpened({ redemption: row, decision: "fulfil" });
                      }}
                    >
                      Mark sent
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Refuse ${row.gift?.name ?? "the gift"} for ${row.holder.name ?? "the dealer"}`}
                      onClick={() => {
                        setOpened({ redemption: row, decision: "reject" });
                      }}
                    >
                      Refuse
                    </Button>
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Dialog
        open={opened !== null}
        onOpenChange={(open) => {
          if (!open) setOpened(null);
        }}
      >
        <DialogContent size="sm">
          {opened === null ? null : (
            <RedemptionDecisionForm
              redemption={opened.redemption}
              decision={opened.decision}
              onClose={() => {
                setOpened(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
