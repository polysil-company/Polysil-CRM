"use client";

import { Add01Icon, GiftIcon } from "@hugeicons/core-free-icons";
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
import { Checkbox } from "@/components/ui/checkbox";
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
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useRequestGift, useSaveGift } from "@/features/rewards/api/rewards.mutations";
import {
  balanceQueryOptions,
  giftsQueryOptions,
  redemptionsQueryOptions,
} from "@/features/rewards/api/rewards.queries";
import type { Gift, Redemption } from "@/features/rewards/api/rewards.schemas";
import {
  REDEMPTION_STATUS_BADGE,
  REDEMPTION_STATUS_LABELS,
  pointsText,
} from "@/features/rewards/lib/reward-labels";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { RedemptionDecisionForm } from "./reward-dialogs";

const log = createLogger({
  file: "features/rewards/components/gifts-panel.tsx",
  dataId: "RWD-001",
});

/**
 * RWD-001 · The gift catalogue. A dealer asks for a gift its points cover (they are held at
 * once) and follows its requests; staff below Admin can't redeem yet (GAP-336). RWD-003 · Admin
 * adds gifts, changes them and switches them off.
 */
export function GiftsPanel(): React.JSX.Element {
  const isStaff = useIsStaff();
  const canRedeem = useCan("rewards", "create") && !isStaff;
  const canEdit = useCan("rewards", "edit") && isStaff;
  const gifts = useQuery(giftsQueryOptions(!canEdit));
  const balance = useQuery({ ...balanceQueryOptions({ kind: "me" }), enabled: canRedeem });
  const [editing, setEditing] = useState<Gift | "new" | null>(null);
  const [asking, setAsking] = useState<Gift | null>(null);
  const points = balance.data?.points ?? null;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
          <div className="flex flex-col gap-0.5">
            <CardTitle level={3}>Gifts</CardTitle>
            <CardDescription>
              {canRedeem
                ? points === null
                  ? "Ask for a gift your points cover; they are held until it is sent."
                  : `You have ${pointsText(points)}. Ask for a gift your points cover; they are held until it is sent.`
                : canEdit
                  ? "What dealers can ask for with their points, cheapest first."
                  : "What dealers can ask for with their points, cheapest first. Staff can't redeem points yet."}
            </CardDescription>
          </div>
          {canEdit ? (
            <Button
              variant="outline"
              onClick={() => {
                setEditing("new");
              }}
            >
              <Icon icon={Add01Icon} />
              Add a gift
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {gifts.status === "pending" ? (
            <div
              aria-busy="true"
              aria-label="Loading gifts"
              className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
            >
              {[0, 1, 2].map((row) => (
                <Skeleton key={row} className="h-28 rounded-xl" />
              ))}
            </div>
          ) : gifts.status === "error" ? (
            <ErrorState
              error={gifts.error}
              onRetry={() => {
                void gifts.refetch();
              }}
              className="border-0 p-2"
            />
          ) : gifts.data.length === 0 ? (
            <EmptyState
              icon={GiftIcon}
              title="No gifts offered"
              description={canEdit ? "Add one for dealers to ask for." : "Admin adds the gifts."}
              className="border-0"
            />
          ) : (
            <ul aria-label="Gifts" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {gifts.data.map((gift) => {
                const short = points !== null && points < gift.pointsCost;
                return (
                  <li
                    key={gift.id}
                    className="flex flex-col justify-between gap-3 rounded-xl border border-border bg-card p-3 sm:p-4"
                  >
                    <span className="flex flex-col gap-1">
                      <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
                        {gift.name}
                        {gift.active ? null : (
                          <Badge variant="neutral" size="sm">
                            Switched off
                          </Badge>
                        )}
                      </span>
                      {gift.description === null ? null : (
                        <span className="text-xs text-muted-foreground">{gift.description}</span>
                      )}
                      <span className="text-sm font-medium text-foreground tabular-nums">
                        {pointsText(gift.pointsCost)}
                      </span>
                    </span>
                    {canRedeem ? (
                      <span className="flex flex-col gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={short}
                          aria-label={`Ask for ${gift.name}`}
                          aria-describedby={short ? `gift-${gift.id}-short` : undefined}
                          onClick={() => {
                            setAsking(gift);
                          }}
                        >
                          Ask for it
                        </Button>
                        {short ? (
                          <span
                            id={`gift-${gift.id}-short`}
                            className="text-xs text-muted-foreground"
                          >
                            {formatNumber(gift.pointsCost - (points ?? 0))} more points needed.
                          </span>
                        ) : null}
                      </span>
                    ) : canEdit ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="self-start"
                        aria-label={`Change ${gift.name}`}
                        onClick={() => {
                          setEditing(gift);
                        }}
                      >
                        Change
                      </Button>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {canRedeem ? <MyRequests /> : null}

      <Dialog
        open={asking !== null}
        onOpenChange={(open) => {
          if (!open) setAsking(null);
        }}
      >
        <DialogContent size="sm">
          {asking === null ? null : (
            <AskForm
              gift={asking}
              points={points}
              onClose={() => {
                setAsking(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      >
        <DialogContent size="sm">
          {editing === null ? null : (
            <GiftForm
              gift={editing === "new" ? null : editing}
              onClose={() => {
                setEditing(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MyRequests(): React.JSX.Element {
  const query = useInfiniteQuery(redemptionsQueryOptions({ status: null, kind: "gift" }));
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];
  const [withdrawing, setWithdrawing] = useState<Redemption | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle level={3}>Your requests</CardTitle>
        <CardDescription>Newest first. A waiting request can be withdrawn.</CardDescription>
      </CardHeader>
      <CardContent>
        {query.status === "pending" ? (
          <Skeleton className="h-16 w-full" />
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
            className="border-0 p-2"
          />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No gifts asked for yet.</p>
        ) : (
          <ul aria-label="Your gift requests" className="flex flex-col divide-y divide-border">
            {rows.map((row) => (
              <li
                key={row.id}
                className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:justify-between"
              >
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="flex flex-wrap items-center gap-2 text-sm text-foreground">
                    {row.gift?.name ?? "A gift"}
                    <Badge variant={REDEMPTION_STATUS_BADGE[row.status]} size="sm" dot>
                      {REDEMPTION_STATUS_LABELS[row.status]}
                    </Badge>
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {pointsText(row.points)} · asked <RelativeDate value={row.createdAt} />
                    {row.remark === null ? "" : ` · ${row.remark}`}
                  </span>
                </span>
                {row.status === "pending" ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="self-start sm:self-auto"
                    aria-label={`Withdraw the request for ${row.gift?.name ?? "the gift"}`}
                    onClick={() => {
                      setWithdrawing(row);
                    }}
                  >
                    Withdraw
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        <Dialog
          open={withdrawing !== null}
          onOpenChange={(open) => {
            if (!open) setWithdrawing(null);
          }}
        >
          <DialogContent size="sm">
            {withdrawing === null ? null : (
              <RedemptionDecisionForm
                redemption={withdrawing}
                decision="withdraw"
                onClose={() => {
                  setWithdrawing(null);
                }}
              />
            )}
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}

function AskForm({
  gift,
  points,
  onClose,
}: {
  gift: Gift;
  points: number | null;
  onClose: () => void;
}): React.JSX.Element {
  const ask = useRequestGift();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const [refusal, setRefusal] = useState<string | null>(null);

  const submit = useAsyncAction({
    action: () => {
      const body = { gift_id: gift.id };
      return ask.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleRequestGift",
    dataId: "RWD-001",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Gift asked for", {
        description: `${pointsText(gift.pointsCost)} are held until it is sent.`,
      });
      closeSoon();
    },
    onError: (error) => {
      setRefusal(
        isApiError(error) && error.code === "insufficient_points"
          ? "Your points don't cover it any more."
          : (readFieldErrors(error)?.gift_id ?? toUserFacingError(error).title),
      );
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setRefusal(null);
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Ask for {gift.name}?</DialogTitle>
        <DialogDescription>
          {pointsText(gift.pointsCost)}
          {points === null ? "" : ` of your ${pointsText(points)}`}.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          The points are held now. If the request is refused or you withdraw it, they come back.
        </p>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Not now
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Asking…"
          successLabel="Asked"
          errorLabel="Not asked"
        >
          Ask for it
        </Button>
      </DialogFooter>
    </form>
  );
}

function GiftForm({
  gift,
  onClose,
}: {
  gift: Gift | null;
  onClose: () => void;
}): React.JSX.Element {
  const save = useSaveGift();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const [name, setName] = useState(gift?.name ?? "");
  const [description, setDescription] = useState(gift?.description ?? "");
  const [cost, setCost] = useState(gift === null ? "" : String(gift.pointsCost));
  const [active, setActive] = useState(gift?.active ?? true);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const problems = {
    name: name.trim() === "" ? "Name it." : null,
    cost: /^\d+$/.test(cost.trim()) && Number(cost) > 0 ? null : "Whole points, at least 1.",
  };

  const submit = useAsyncAction({
    action: () => {
      const body = {
        name: name.trim(),
        description: description.trim() === "" ? null : description.trim(),
        points_cost: Number(cost),
      };
      return gift === null
        ? save.mutateAsync({ giftId: null, body, idempotencyKey: idempotency.keyFor(body) })
        : save.mutateAsync({
            giftId: gift.id,
            body: { ...body, is_active: active },
            idempotencyKey: idempotency.keyFor({ id: gift.id, ...body, active }),
          });
    },
    logger: log,
    fn: gift === null ? "handleAddGift" : "handleChangeGift",
    dataId: "RWD-003",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(gift === null ? "Gift added" : "Gift changed", { description: saved.name });
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
      aria-label={gift === null ? "Add a gift" : `Change ${gift.name}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (problems.name !== null || problems.cost !== null) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>{gift === null ? "Add a gift" : `Change ${gift.name}`}</DialogTitle>
        <DialogDescription>
          {gift === null
            ? "Dealers can ask for it as soon as it is added."
            : "A request already waiting keeps the points it was asked at."}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={shown && problems.name !== null ? true : undefined}>
          <FieldLabel htmlFor="gift-name">Name</FieldLabel>
          <Input
            id="gift-name"
            maxLength={120}
            autoComplete="off"
            value={name}
            aria-invalid={shown && problems.name !== null ? true : undefined}
            aria-describedby={shown && problems.name !== null ? "gift-name-error" : undefined}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
          {shown && problems.name !== null ? (
            <FieldError id="gift-name-error">{problems.name}</FieldError>
          ) : null}
        </Field>
        <Field data-invalid={shown && problems.cost !== null ? true : undefined}>
          <FieldLabel htmlFor="gift-cost">Points</FieldLabel>
          <Input
            id="gift-cost"
            inputMode="numeric"
            autoComplete="off"
            className="tabular-nums"
            value={cost}
            aria-invalid={shown && problems.cost !== null ? true : undefined}
            aria-describedby={shown && problems.cost !== null ? "gift-cost-error" : undefined}
            onChange={(event) => {
              setCost(event.target.value);
            }}
          />
          {shown && problems.cost !== null ? (
            <FieldError id="gift-cost-error">{problems.cost}</FieldError>
          ) : null}
        </Field>
        <Field>
          <FieldLabel htmlFor="gift-description">
            Description <span className="font-normal text-muted-foreground">(optional)</span>
          </FieldLabel>
          <Textarea
            id="gift-description"
            rows={2}
            maxLength={300}
            value={description}
            onChange={(event) => {
              setDescription(event.target.value);
            }}
          />
        </Field>
        {gift === null ? null : (
          <div className="flex items-center gap-2">
            <Checkbox
              id="gift-active"
              checked={active}
              onCheckedChange={(checked) => {
                setActive(checked);
              }}
            />
            <Label htmlFor="gift-active">Offered to dealers</Label>
          </div>
        )}
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
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {gift === null ? "Add gift" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
