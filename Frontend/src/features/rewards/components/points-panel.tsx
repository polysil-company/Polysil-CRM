"use client";

import { Cancel01Icon, CoinsDollarIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAdjustPoints } from "@/features/rewards/api/rewards.mutations";
import { balanceQueryOptions, ledgerQueryOptions } from "@/features/rewards/api/rewards.queries";
import type { Balance, HolderQuery, LedgerRow } from "@/features/rewards/api/rewards.schemas";
import {
  LEDGER_KIND_LABELS,
  pointsText,
  pointsWorth,
  signedPoints,
} from "@/features/rewards/lib/reward-labels";
import { PartnerSearchPicker } from "@/features/schemes/components/record-pickers";
import { useCan, useIsStaff, useSession } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { readFieldErrors } from "@/lib/api/errors";
import { formatDate, formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/rewards/components/points-panel.tsx",
  dataId: "RWD-001",
});

const ME: HolderQuery = { kind: "me" };

/**
 * RWD-001 · A balance and its history. A dealer sees its own; staff their own, and a manager or
 * Admin may look up a dealer's (a field officer sees only their own: rewards V:own). Admin
 * adjusts a balance by hand, with a reason (RWD-003).
 */
export function PointsPanel(): React.JSX.Element {
  const isStaff = useIsStaff();
  const session = useSession();
  const scope = session.data?.permissions.find((entry) => entry.module === "rewards")?.scope;
  const looksUp = isStaff && scope !== "own";
  const [partner, setPartner] = useState<{ id: string; name: string } | null>(null);
  const holder: HolderQuery = partner === null ? ME : { kind: "partner", id: partner.id };

  return (
    <div className="flex flex-col gap-4">
      {looksUp ? (
        <Field className="max-w-md">
          <FieldLabel htmlFor="points-holder">Whose points</FieldLabel>
          {partner === null ? (
            <PartnerSearchPicker
              id="points-holder"
              placeholder="Yours, or search a dealer"
              aria-describedby="points-holder-hint"
              onPick={(picked) => {
                setPartner({ id: picked.id, name: picked.name });
              }}
            />
          ) : (
            <div className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm">
              <span className="text-foreground">{partner.name}</span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Back to your own points, not ${partner.name}'s`}
                onClick={() => {
                  setPartner(null);
                }}
              >
                <Icon icon={Cancel01Icon} />
              </Button>
            </div>
          )}
          <FieldDescription id="points-holder-hint">
            {partner === null ? "Showing your own points." : "Clear it to see your own."}
          </FieldDescription>
        </Field>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-3 lg:items-start">
        <BalanceCard holder={holder} />
        <History holder={holder} className="lg:col-span-2" />
      </div>
    </div>
  );
}

function BalanceCard({ holder }: { holder: HolderQuery }): React.JSX.Element {
  const query = useQuery(balanceQueryOptions(holder));
  const canEdit = useCan("rewards", "edit");
  const isStaff = useIsStaff();
  // Partner users never adjust, whatever they hold (the backend refuses them).
  const canAdjust = canEdit && isStaff;
  const [adjusting, setAdjusting] = useState(false);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Balance</CardTitle>
        <CardDescription>
          {query.data === undefined
            ? "Points to spend."
            : `${query.data.holder.name ?? "This holder"}'s points to spend.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {query.status === "pending" ? (
          <div aria-busy="true" aria-label="Loading the balance" className="flex flex-col gap-2">
            <Skeleton className="h-9 w-32" />
            <Skeleton className="h-4 w-48" />
          </div>
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
            className="border-0 p-2"
          />
        ) : (
          <>
            <p className="flex flex-col gap-0.5">
              <span
                className={cn(
                  "text-3xl font-semibold tabular-nums",
                  query.data.points < 0 ? "text-danger" : "text-foreground",
                )}
              >
                {pointsText(query.data.points)}
              </span>
              <span className="text-sm text-muted-foreground">
                Worth {pointsWorth(query.data.points, query.data.pointValue)} on an order, at{" "}
                {formatInr(query.data.pointValue, { paise: true })} a point today.
              </span>
            </p>
            {query.data.points < 0 ? (
              <p className="text-xs text-muted-foreground">
                Below zero after points were taken back; new points fill it first.
              </p>
            ) : null}
            {canAdjust ? (
              <Button
                variant="outline"
                className="self-start"
                onClick={() => {
                  setAdjusting(true);
                }}
              >
                Adjust points
              </Button>
            ) : null}
            <Dialog open={adjusting} onOpenChange={setAdjusting}>
              <DialogContent size="sm">
                {adjusting ? (
                  <AdjustForm
                    balance={query.data}
                    onClose={() => {
                      setAdjusting(false);
                    }}
                  />
                ) : null}
              </DialogContent>
            </Dialog>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function History({
  holder,
  className,
}: {
  holder: HolderQuery;
  className?: string;
}): React.JSX.Element {
  const query = useInfiniteQuery(ledgerQueryOptions(holder));
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>History</CardTitle>
        <CardDescription>Every change to the balance, newest first.</CardDescription>
      </CardHeader>
      <CardContent>
        {query.status === "pending" ? (
          <div aria-busy="true" aria-label="Loading the history" className="flex flex-col gap-2">
            {[0, 1, 2, 3].map((row) => (
              <Skeleton key={row} className="h-10 w-full" />
            ))}
          </div>
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
            className="border-0 p-2"
          />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={CoinsDollarIcon}
            title="No points yet"
            description="Points arrive when an order is delivered, a lead is won or a scheme pays them."
            className="border-0"
          />
        ) : (
          <div className="flex flex-col gap-3">
            <ul aria-label="Points history" className="flex flex-col divide-y divide-border">
              {rows.map((row) => (
                <HistoryRow key={row.id} row={row} />
              ))}
            </ul>
            {query.hasNextPage ? (
              <Button
                variant="outline"
                className="self-center"
                disabled={query.isFetchingNextPage}
                onClick={() => {
                  void query.fetchNextPage();
                }}
              >
                {query.isFetchingNextPage ? "Loading…" : "Show more"}
              </Button>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function HistoryRow({ row }: { row: LedgerRow }): React.JSX.Element {
  return (
    <li className="flex items-start justify-between gap-3 py-2.5">
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="flex flex-wrap items-center gap-2">
          <Badge variant={row.points > 0 ? "success" : "neutral"} size="sm">
            {LEDGER_KIND_LABELS[row.kind]}
          </Badge>
          <span className="text-xs text-muted-foreground">
            <RelativeDate value={row.at} />
          </span>
        </span>
        <span className="text-sm text-foreground">{row.reason}</span>
        {row.expiresAt === null ? null : (
          <span className="text-xs text-muted-foreground">Expires {formatDate(row.expiresAt)}</span>
        )}
      </span>
      <span
        className={cn(
          "shrink-0 text-sm font-medium tabular-nums",
          row.points > 0 ? "text-success" : "text-foreground",
        )}
      >
        {signedPoints(row.points)}
      </span>
    </li>
  );
}

function AdjustForm({
  balance,
  onClose,
}: {
  balance: Balance;
  onClose: () => void;
}): React.JSX.Element {
  const adjust = useAdjustPoints();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const [points, setPoints] = useState("");
  const [reason, setReason] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const parsed = Number(points.trim());
  const problems = {
    points: !/^[-+]?\d+$/.test(points.trim())
      ? "A whole number: 50 adds, -50 takes away."
      : parsed === 0
        ? "Not zero."
        : null,
    reason: reason.trim() === "" ? "Say why, for the history." : null,
  };
  const holderName = balance.holder.name ?? "This holder";

  const submit = useAsyncAction({
    action: () => {
      const body = {
        partner_id: balance.holder.type === "partner" ? balance.holder.id : null,
        user_id: balance.holder.type === "user" ? balance.holder.id : null,
        points: parsed,
        reason: reason.trim(),
      };
      return adjust.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleAdjustPoints",
    dataId: "RWD-003",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Points adjusted", {
        description: `${signedPoints(parsed)} for ${holderName}.`,
      });
      closeSoon();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      setRefusal(
        fields === null ? toUserFacingError(error).title : Object.values(fields).join(" "),
      );
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (problems.points !== null || problems.reason !== null) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Adjust points</DialogTitle>
        <DialogDescription>
          {holderName} has {pointsText(balance.points)}. An adjustment shows in the history with
          your reason, and may take the balance below zero.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={shown && problems.points !== null ? true : undefined}>
          <FieldLabel htmlFor="adjust-points">Points</FieldLabel>
          <Input
            id="adjust-points"
            inputMode="numeric"
            autoComplete="off"
            className="tabular-nums"
            placeholder="50 or -50"
            value={points}
            aria-invalid={shown && problems.points !== null ? true : undefined}
            aria-describedby={
              shown && problems.points !== null ? "adjust-points-error" : "adjust-points-hint"
            }
            onChange={(event) => {
              setPoints(event.target.value);
            }}
          />
          {shown && problems.points !== null ? (
            <FieldError id="adjust-points-error">{problems.points}</FieldError>
          ) : (
            <FieldDescription id="adjust-points-hint">
              {Number.isInteger(parsed) && parsed !== 0
                ? `The balance becomes ${pointsText(balance.points + parsed)}.`
                : "Positive adds, negative takes away."}
            </FieldDescription>
          )}
        </Field>
        <Field data-invalid={shown && problems.reason !== null ? true : undefined}>
          <FieldLabel htmlFor="adjust-reason">Reason</FieldLabel>
          <Textarea
            id="adjust-reason"
            rows={2}
            maxLength={300}
            value={reason}
            aria-invalid={shown && problems.reason !== null ? true : undefined}
            aria-describedby={shown && problems.reason !== null ? "adjust-reason-error" : undefined}
            onChange={(event) => {
              setReason(event.target.value);
            }}
          />
          {shown && problems.reason !== null ? (
            <FieldError id="adjust-reason-error">{problems.reason}</FieldError>
          ) : null}
        </Field>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Adjusted"
          errorLabel="Not adjusted"
        >
          Adjust
        </Button>
      </DialogFooter>
    </form>
  );
}
