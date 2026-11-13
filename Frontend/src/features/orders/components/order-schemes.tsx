"use client";

import { GiftIcon } from "@hugeicons/core-free-icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect } from "react";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { orderKeys, orderSchemesQueryOptions } from "@/features/orders/api/orders.queries";
import type {
  Order,
  OrderBenefit,
  OrderBenefitKind,
  OrderSchemePreview,
  SchemeRef,
} from "@/features/orders/api/orders.schemas";
import { useCan } from "@/features/session/hooks/use-session";
import { isApiError } from "@/lib/api/errors";
import { formatInr, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

const BENEFIT_LABELS: Readonly<Record<OrderBenefitKind, string>> = {
  discount: "Scheme discount",
  entitlement_used: "Credit used",
  reward_redemption: "Reward points redeemed",
};

/**
 * SCHM-005 · Scheme benefits on an order (`schemes-contract.md`, FS-031). On a draft, what submit
 * would take off and what delivery would earn; after submit, the benefits it took. A benefit
 * lowers what is paid ("To pay"), never the invoice.
 */
export function OrderSchemesCard({ order }: { order: Order }): React.JSX.Element | null {
  if (order.status === "draft") {
    return order.lines.length === 0 ? null : <DraftSchemes order={order} />;
  }
  return order.benefits.length === 0 ? null : <AppliedBenefits order={order} />;
}

function SchemesCard({
  description,
  children,
}: {
  description: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section aria-labelledby="order-schemes-title">
      <Card>
        <CardHeader>
          <CardTitle level={3} id="order-schemes-title" className="flex items-center gap-2">
            <Icon icon={GiftIcon} size="sm" className="text-muted-foreground" />
            Schemes
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">{children}</CardContent>
      </Card>
    </section>
  );
}

/** The draft's preview, read again whenever the lines or the total change. */
function DraftSchemes({ order }: { order: Order }): React.JSX.Element | null {
  const queryClient = useQueryClient();
  const revision = `${order.totals.total}:${String(order.lines.length)}`;
  const preview = useQuery(orderSchemesQueryOptions(order.id, revision));
  const moved = isApiError(preview.error) && preview.error.code === "order_not_draft";

  // Submitted elsewhere: the order itself now carries the benefits, so read it again.
  useEffect(() => {
    if (moved) void queryClient.invalidateQueries({ queryKey: orderKeys.detail(order.id) });
  }, [moved, order.id, queryClient]);

  if (moved) return null;
  // A partner-less draft (a direct sale) shows the card only when a scheme applies.
  const quietWhenEmpty = order.partner === null;
  if (preview.status === "error") {
    if (isApiError(preview.error) && preview.error.status === 403) return null;
    return (
      <SchemesCard description="What submitting would take off, and what delivery would earn.">
        <ErrorState
          error={preview.error}
          onRetry={() => {
            void preview.refetch();
          }}
          className="border-0 p-2"
        />
      </SchemesCard>
    );
  }
  if (preview.status === "pending") {
    return quietWhenEmpty ? null : (
      <SchemesCard description="What submitting would take off, and what delivery would earn.">
        <div aria-busy="true" aria-label="Checking the schemes" className="flex flex-col gap-2">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-5 w-1/2" />
        </div>
      </SchemesCard>
    );
  }
  const data = preview.data;
  const empty =
    data.discounts.length === 0 && data.credits.length === 0 && data.onDelivery.length === 0;
  if (empty && quietWhenEmpty) return null;

  return (
    <SchemesCard description="What submitting would take off, and what delivery would earn. Worked out again as the items change.">
      {empty ? (
        <p className="text-sm text-muted-foreground">
          No scheme applies to this order as it stands.
        </p>
      ) : (
        <PreviewBody preview={data} total={order.totals.total} />
      )}
    </SchemesCard>
  );
}

function PreviewBody({
  preview,
  total,
}: {
  preview: OrderSchemePreview;
  total: string;
}): React.JSX.Element {
  const takesOff = preview.discounts.length > 0 || preview.credits.length > 0;
  return (
    <>
      {takesOff ? (
        <section aria-label="Taken off at submit" className="flex flex-col gap-2">
          <h4 className="text-xs font-medium text-muted-foreground">Taken off at submit</h4>
          <ul className="flex flex-col divide-y divide-border">
            {preview.discounts.map((discount) => (
              <BenefitRow
                key={`discount-${discount.scheme.id}`}
                label={BENEFIT_LABELS.discount}
                scheme={discount.scheme}
                detail={`On ${formatInr(discount.basis, { paise: true })} of items`}
                amount={discount.amount}
              />
            ))}
            {preview.credits.map((credit) => (
              <BenefitRow
                key={`credit-${credit.entitlementId}`}
                label={BENEFIT_LABELS.entitlement_used}
                scheme={credit.scheme}
                detail="Earned earlier, used on this order"
                amount={credit.amount}
              />
            ))}
          </ul>
        </section>
      ) : null}
      {preview.onDelivery.length > 0 ? (
        <section aria-label="Earned on delivery" className="flex flex-col gap-2">
          <h4 className="text-xs font-medium text-muted-foreground">Earned on delivery</h4>
          <ul className="flex flex-col divide-y divide-border">
            {preview.onDelivery.map((earned) => (
              <li
                key={`delivery-${earned.scheme.id}`}
                className="flex flex-col gap-0.5 py-2 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4"
              >
                <SchemeName scheme={earned.scheme} />
                <span className="text-sm text-foreground tabular-nums">
                  {earned.kind === "points"
                    ? `${formatNumber(earned.points ?? 0)} points`
                    : "A credit for the next order"}
                  <span className="block text-xs text-muted-foreground sm:text-right">
                    Counted on what is dispatched
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <ToPay
        owedLabel="Order total"
        owed={total}
        benefit={preview.totalBenefit}
        payable={preview.payable}
        future
      />
    </>
  );
}

/** After submit: the benefits the order took, a reversed one struck through. */
function AppliedBenefits({ order }: { order: Order }): React.JSX.Element {
  const applied = order.benefits.filter((benefit) => benefit.status === "applied");
  const sum = applied.reduce(
    (total, benefit) => total + Math.round(Number(benefit.amount) * 100),
    0,
  );
  return (
    <SchemesCard description="Applied at submit. They lower what is paid; the invoice stays at the total.">
      <ul aria-label="Scheme benefits" className="flex flex-col divide-y divide-border">
        {order.benefits.map((benefit) => (
          <AppliedRow key={benefit.id} benefit={benefit} />
        ))}
      </ul>
      {order.payable === null ? null : (
        <ToPay
          // On a subsidised order the farmer's share is what benefits come off.
          owedLabel={order.subsidy === null ? "Order total" : "The farmer's share"}
          owed={order.subsidy === null ? order.totals.total : order.subsidy.farmerPayable}
          benefit={(sum / 100).toFixed(2)}
          payable={order.payable}
          future={false}
        />
      )}
    </SchemesCard>
  );
}

function AppliedRow({ benefit }: { benefit: OrderBenefit }): React.JSX.Element {
  const reversed = benefit.status === "reversed";
  return (
    <li className="flex flex-col gap-0.5 py-2 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="flex flex-wrap items-center gap-2 text-sm text-foreground">
          <span className={cn(reversed && "text-muted-foreground line-through")}>
            {BENEFIT_LABELS[benefit.kind]}
          </span>
          {reversed ? (
            <Badge variant="neutral" size="sm">
              Reversed
            </Badge>
          ) : null}
        </span>
        {benefit.scheme === null ? null : <SchemeName scheme={benefit.scheme} subtle />}
      </span>
      <span
        className={cn(
          "text-sm tabular-nums",
          reversed ? "text-muted-foreground line-through" : "text-foreground",
        )}
      >
        {reversed ? <span className="sr-only">Reversed: </span> : null}−
        {formatInr(benefit.amount, { paise: true })}
      </span>
    </li>
  );
}

function BenefitRow({
  label,
  scheme,
  detail,
  amount,
}: {
  label: string;
  scheme: SchemeRef;
  detail: string;
  amount: string;
}): React.JSX.Element {
  return (
    <li className="flex flex-col gap-0.5 py-2 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm text-foreground">{label}</span>
        <SchemeName scheme={scheme} subtle />
        <span className="text-xs text-muted-foreground">{detail}</span>
      </span>
      <span className="text-sm text-foreground tabular-nums">
        −{formatInr(amount, { paise: true })}
      </span>
    </li>
  );
}

/** A scheme's name and code, linked for those who may open schemes. */
function SchemeName({
  scheme,
  subtle = false,
}: {
  scheme: SchemeRef;
  subtle?: boolean;
}): React.JSX.Element {
  const canView = useCan("schemes", "view");
  const text = (
    <>
      {scheme.name} <span className="font-mono text-xs">· {scheme.code}</span>
    </>
  );
  const tone = subtle ? "text-xs text-muted-foreground" : "text-sm text-foreground";
  return canView ? (
    <Link
      href={`/schemes/${scheme.id}`}
      className={cn(tone, "w-fit underline-offset-4 hover:text-primary-text hover:underline")}
    >
      {text}
    </Link>
  ) : (
    <span className={tone}>{text}</span>
  );
}

/** What is owed, less the scheme benefits, is what is paid. */
function ToPay({
  owedLabel,
  owed,
  benefit,
  payable,
  future,
}: {
  owedLabel: string;
  owed: string;
  benefit: string;
  payable: string;
  future: boolean;
}): React.JSX.Element {
  return (
    <div
      role="group"
      aria-label="To pay"
      className="ml-auto w-full max-w-sm border-t border-border pt-3"
    >
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-muted-foreground">{owedLabel}</dt>
        <dd className="text-right text-foreground tabular-nums">
          {formatInr(owed, { paise: true })}
        </dd>
        <dt className="text-muted-foreground">Scheme benefits</dt>
        <dd className="text-right text-foreground tabular-nums">
          −{formatInr(benefit, { paise: true })}
        </dd>
        <dt className="font-semibold text-foreground">
          {future ? "To pay, once submitted" : "To pay"}
        </dt>
        <dd className="text-right text-base font-semibold tabular-nums">
          {formatInr(payable, { paise: true })}
        </dd>
      </dl>
    </div>
  );
}
