"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { Order } from "@/features/orders/api/orders.schemas";
import { useOrderPoints } from "@/features/rewards/api/rewards.mutations";
import {
  balanceQueryOptions,
  redemptionsQueryOptions,
  rewardSettingsQueryOptions,
} from "@/features/rewards/api/rewards.queries";
import { pointsText } from "@/features/rewards/lib/reward-labels";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/rewards/components/order-points.tsx",
  dataId: "RWD-004",
});

const TITLE_ID = "order-points-title";

/**
 * RWD-004 · "Use points" on a dealer's own draft order. The points are held at once; at submit
 * they come off what is paid (never the invoice), in whole points, up to the limit, and any not
 * needed go back. Staff can't redeem yet (GAP-336), so this is for partner users only.
 */
export function OrderPoints({ order }: { order: Order }): React.JSX.Element | null {
  const isStaff = useIsStaff();
  const canRedeem = useCan("rewards", "create");
  const show = !isStaff && canRedeem && order.status === "draft" && order.lines.length > 0;
  if (!show) return null;
  return <PointsOnDraft order={order} />;
}

function PointsOnDraft({ order }: { order: Order }): React.JSX.Element {
  const balance = useQuery(balanceQueryOptions({ kind: "me" }));
  const settings = useQuery(rewardSettingsQueryOptions());
  const held = useInfiniteQuery(redemptionsQueryOptions({ status: "pending", kind: "order" }));
  const onThis = held.data?.pages
    .flatMap((page) => page.items)
    .find((row) => row.salesOrder?.id === order.id);

  if (balance.status !== "success" || settings.status !== "success" || held.status !== "success") {
    const failed = balance.isError || settings.isError || held.isError;
    return (
      <PointsCard description="Pay part of this order with your reward points.">
        {failed ? (
          <p role="alert" className="text-sm text-danger">
            Your points couldn&apos;t be loaded.{" "}
            <Button
              variant="link"
              className="h-auto p-0"
              onClick={() => {
                void balance.refetch();
                void settings.refetch();
                void held.refetch();
              }}
            >
              Try again
            </Button>
          </p>
        ) : (
          <div aria-busy="true" aria-label="Loading your points" className="flex flex-col gap-2">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-9 w-1/2" />
          </div>
        )}
      </PointsCard>
    );
  }

  const pointValue = Number(settings.data.pointValue);
  const pct = Number(settings.data.maxRedeemPct);
  const limitRupees = (Number(order.totals.total) * pct) / 100;
  // Whole points only: the most this order takes, and the most the balance covers.
  const orderMax = pointValue > 0 ? Math.floor(limitRupees / pointValue) : 0;
  const most = Math.max(0, Math.min(orderMax, balance.data.points));

  return (
    <PointsCard
      description={`At most ${String(pct)}% of the order total, ${formatInr(limitRupees.toFixed(2), { paise: true })}, at ${formatInr(settings.data.pointValue, { paise: true })} a point.`}
    >
      {onThis === undefined ? (
        <UseForm
          order={order}
          available={balance.data.points}
          most={most}
          pointValue={pointValue}
        />
      ) : (
        <Held order={order} points={onThis.points} pointValue={pointValue} />
      )}
    </PointsCard>
  );
}

function PointsCard({
  description,
  children,
}: {
  description: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section aria-labelledby={TITLE_ID}>
      <Card>
        <CardHeader>
          <CardTitle level={3} id={TITLE_ID}>
            Reward points
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">{children}</CardContent>
      </Card>
    </section>
  );
}

function Held({
  order,
  points,
  pointValue,
}: {
  order: Order;
  points: number;
  pointValue: number;
}): React.JSX.Element {
  const change = useOrderPoints();
  const idempotency = useIdempotencyKey();
  const remove = useAsyncAction({
    action: () =>
      change.mutateAsync({
        orderId: order.id,
        points: null,
        idempotencyKey: idempotency.keyFor({ orderId: order.id, remove: true }),
      }),
    logger: log,
    fn: "handleRemoveOrderPoints",
    dataId: "RWD-004",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Points taken off", { description: "They are back in your balance." });
    },
  });
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm text-foreground">
        <span className="font-semibold tabular-nums">{pointsText(points)}</span> on this order,
        worth {formatInr((points * pointValue).toFixed(2), { paise: true })}. They come off what you
        pay when it is submitted; the invoice stays at the total.
      </p>
      <Button
        variant="outline"
        className="shrink-0"
        state={remove.state}
        loadingLabel="Taking off…"
        successLabel="Taken off"
        errorLabel="Not taken off"
        onClick={() => {
          void remove.run();
        }}
      >
        Take them off
      </Button>
    </div>
  );
}

function UseForm({
  order,
  available,
  most,
  pointValue,
}: {
  order: Order;
  available: number;
  most: number;
  pointValue: number;
}): React.JSX.Element {
  const change = useOrderPoints();
  const idempotency = useIdempotencyKey();
  const [value, setValue] = useState("");
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<string | null>(null);
  const points = Number(value.trim());
  const clientProblem =
    !/^\d+$/.test(value.trim()) || points === 0
      ? "Whole points, at least 1."
      : points > most
        ? `Up to ${pointsText(most)} on this order.`
        : null;
  const problem = server ?? clientProblem;

  const use = useAsyncAction({
    action: () =>
      change.mutateAsync({
        orderId: order.id,
        points,
        idempotencyKey: idempotency.keyFor({ orderId: order.id, points }),
      }),
    logger: log,
    fn: "handleUseOrderPoints",
    dataId: "RWD-004",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Points on the order", {
        description: `${pointsText(points)} are held; they come off what you pay at submit.`,
      });
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "insufficient_points") {
        setServer("More than your balance now.");
      } else if (isApiError(error) && error.code === "over_redeem_limit") {
        setServer("More than points may pay on this order.");
      } else {
        setServer(readFieldErrors(error)?.points ?? toUserFacingError(error).title);
      }
    },
  });

  if (most === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {available <= 0
          ? "You have no points to spend yet."
          : "This order is too small to pay with points."}
      </p>
    );
  }

  const visible = shown || server !== null;
  return (
    <form
      noValidate
      aria-label="Use points on this order"
      className="flex flex-col gap-3 sm:flex-row sm:items-start"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServer(null);
        if (clientProblem !== null) return;
        void use.run();
      }}
    >
      <Field data-invalid={visible && problem !== null ? true : undefined} className="sm:max-w-56">
        <FieldLabel htmlFor="order-points">Points to use</FieldLabel>
        <Input
          id="order-points"
          inputMode="numeric"
          autoComplete="off"
          className="tabular-nums"
          placeholder={String(most)}
          value={value}
          aria-invalid={visible && problem !== null ? true : undefined}
          aria-describedby={
            visible && problem !== null ? "order-points-error" : "order-points-hint"
          }
          onChange={(event) => {
            setValue(event.target.value);
            setServer(null);
          }}
        />
        {visible && problem !== null ? (
          <FieldError id="order-points-error">{problem}</FieldError>
        ) : (
          <FieldDescription id="order-points-hint">
            You have {pointsText(available)}; up to {pointsText(most)} on this order
            {Number.isInteger(points) && points > 0
              ? `, worth ${formatInr((points * pointValue).toFixed(2), { paise: true })}`
              : ""}
            .
          </FieldDescription>
        )}
      </Field>
      <div className="flex flex-wrap gap-2 sm:pt-6">
        <Button
          type="submit"
          state={use.state}
          loadingLabel="Holding…"
          successLabel="Held"
          errorLabel="Not held"
        >
          Use points
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setValue(String(most));
            setServer(null);
          }}
        >
          Use {pointsText(most)}
        </Button>
      </div>
    </form>
  );
}
