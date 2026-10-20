"use client";

import { Cancel01Icon, Coupon01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { parseAsStringLiteral, useQueryStates } from "nuqs";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { SingleFilterPill } from "@/components/patterns/filter-pill";
import { QueryView } from "@/components/patterns/query-view";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { creditListQueryOptions } from "@/features/schemes/api/schemes.queries";
import {
  ENTITLEMENT_STATUSES,
  type Entitlement,
  type EntitlementStatus,
} from "@/features/schemes/api/schemes.schemas";
import { ENTITLEMENT_STATUS_LABELS } from "@/features/schemes/lib/scheme-labels";
import { useIsStaff } from "@/features/session/hooks/use-session";
import { formatCalendarDay, formatDate, formatInr, formatNumber } from "@/lib/format";

import { PartnerSearchPicker, type PickedRecord } from "./record-pickers";

const STATUS_OPTIONS = ENTITLEMENT_STATUSES.map((status) => ({
  value: status,
  label: ENTITLEMENT_STATUS_LABELS[status],
}));

const STATUS_BADGE: Readonly<Record<EntitlementStatus, BadgeVariant>> = {
  available: "success",
  consumed: "neutral",
  expired: "outline",
  reversed: "warning",
};

/** "5% of a later order, up to ₹5,000", or "₹3,000". */
function creditValue(credit: Entitlement): string {
  const cap = credit.cap === null ? "" : `, up to ${formatInr(credit.cap)}`;
  return credit.kind === "pct"
    ? `${formatNumber(Number(credit.value), Number.isInteger(Number(credit.value)) ? 0 : 2)}% of a later order${cap}`
    : formatInr(credit.value);
}

/**
 * SCHM-004 · Credits from next-order and period schemes, newest first. A dealer sees its own,
 * the available ones first; staff see the partners they can see, and may narrow to one. An
 * available credit is used by itself on the next order it fits, the earliest expiry first.
 */
export function CreditsList(): React.JSX.Element {
  const staff = useIsStaff();
  const [values, setValues] = useQueryStates({
    status: parseAsStringLiteral([...ENTITLEMENT_STATUSES, "all"] as const),
  });
  const [partner, setPartner] = useState<PickedRecord | null>(null);
  const status: EntitlementStatus | null =
    values.status === null
      ? staff
        ? null
        : "available"
      : values.status === "all"
        ? null
        : values.status;
  const query = useInfiniteQuery(
    creditListQueryOptions({ status, partnerId: staff ? (partner?.id ?? null) : null }),
  );

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-prose text-sm text-muted-foreground">
        An available credit is used by itself on the next order it fits, the earliest to expire
        first. One worth more than an order waits for a bigger one.
      </p>
      <div className="flex flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
        <SingleFilterPill
          label="Status"
          options={STATUS_OPTIONS}
          selected={status}
          onChange={(next) => {
            void setValues({ status: next ?? (staff ? null : "all") });
          }}
        />
        {staff ? (
          partner === null ? (
            <div className="md:w-80">
              <PartnerSearchPicker
                id="credits-partner"
                placeholder="One partner's credits"
                onPick={setPartner}
              />
            </div>
          ) : (
            <span className="flex items-center gap-1 rounded-full border border-border py-0.5 pr-1 pl-3 text-sm">
              {partner.name}
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`Show every partner's credits, not only ${partner.name}'s`}
                onClick={() => {
                  setPartner(null);
                }}
              >
                <Icon icon={Cancel01Icon} />
              </Button>
            </span>
          )
        ) : null}
      </div>
      <QueryView
        query={query}
        pending={
          <div role="status" aria-label="Loading credits" className="flex flex-col gap-3">
            {[0, 1, 2].map((row) => (
              <Skeleton key={row} className="h-24 w-full rounded-xl" />
            ))}
          </div>
        }
        isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
        empty={
          <EmptyState
            icon={Coupon01Icon}
            title={status === "available" ? "No credits to use" : "No credits"}
            description="A credit is earned when an order under a next-order scheme is delivered, or when a period's target is met."
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <ul className="flex flex-col gap-3">
              {data.pages
                .flatMap((page) => page.items)
                .map((credit) => (
                  <li key={credit.id}>
                    <CreditRow credit={credit} staff={staff} />
                  </li>
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
                {query.isFetchingNextPage ? "Loading…" : "Load more"}
              </Button>
            ) : null}
          </div>
        )}
      </QueryView>
    </div>
  );
}

function CreditRow({ credit, staff }: { credit: Entitlement; staff: boolean }): React.JSX.Element {
  return (
    <Card className="flex flex-col gap-2 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-lg font-semibold text-foreground tabular-nums">
            {creditValue(credit)}
          </span>
          <Link
            href={`/schemes/${credit.scheme.id}`}
            className="text-sm text-foreground underline underline-offset-4"
          >
            {credit.scheme.name}
          </Link>
        </div>
        <Badge variant={STATUS_BADGE[credit.status]}>
          {ENTITLEMENT_STATUS_LABELS[credit.status]}
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">
        {staff ? `${credit.partner.name} · ` : ""}
        Earned {formatDate(credit.earnedAt)}
        {credit.sourceOrder === null ? null : (
          <>
            {" on order "}
            <Link
              href={`/sales-orders/${credit.sourceOrder.id}`}
              className="text-foreground underline underline-offset-4"
            >
              {credit.sourceOrder.orderNo ?? "a draft"}
            </Link>
          </>
        )}
        {credit.periodStart === null || credit.periodEnd === null
          ? ""
          : ` for ${formatCalendarDay(credit.periodStart)} to ${formatCalendarDay(credit.periodEnd)}`}
        {credit.status === "available" ? ` · use by ${formatDate(credit.expiresAt)}` : ""}
        {credit.consumedOrder === null ? null : (
          <>
            {" · used on order "}
            <Link
              href={`/sales-orders/${credit.consumedOrder.id}`}
              className="text-foreground underline underline-offset-4"
            >
              {credit.consumedOrder.orderNo ?? "a draft"}
            </Link>
          </>
        )}
      </p>
    </Card>
  );
}
