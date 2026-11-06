"use client";

import { Shield01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import type { Order } from "@/features/orders/api/orders.schemas";
import { formatOrderQty } from "@/features/orders/lib/order-labels";
import { useCan } from "@/features/session/hooks/use-session";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { orderWarrantyQueryOptions } from "@/features/warranty/api/warranty.queries";
import type { WarrantyLine } from "@/features/warranty/api/warranty.schemas";
import {
  CLAIM_WARRANTY_BADGE,
  CLAIM_WARRANTY_LABELS,
  LINE_WARRANTY_BADGE,
  lineWarrantyText,
  monthsText,
} from "@/features/warranty/lib/warranty-labels";
import { isApiError } from "@/lib/api/errors";

const TITLE_ID = "order-warranty-title";

/** An order's goods are under warranty once something has shipped. */
const SHIPPING = new Set(["partially_dispatched", "dispatched", "closed_short"]);

/**
 * SO-009 · The order's warranty, line by line: each dispatch's period (from its DC date, else the
 * dispatch day), the line's status from its latest-ending dispatch, and the complaints raised on
 * the product. For those who see orders and dispatches; a 403 hides it.
 */
export function OrderWarrantyCard({ order }: { order: Order }): React.JSX.Element | null {
  const canSeeOrders = useCan("sales_orders", "view");
  const canSeeDispatch = useCan("dispatch", "view");
  const canSee = canSeeOrders && canSeeDispatch;
  const shipped = SHIPPING.has(order.status);
  const query = useQuery({ ...orderWarrantyQueryOptions(order.id), enabled: canSee && shipped });
  if (!canSee || !shipped) return null;
  if (query.status === "error" && isApiError(query.error) && query.error.status === 403)
    return null;

  return (
    <section aria-labelledby={TITLE_ID}>
      <Card>
        <CardHeader className="flex-col gap-0.5">
          <CardTitle level={3} id={TITLE_ID} className="flex items-center gap-2">
            <Icon icon={Shield01Icon} size="sm" className="text-muted-foreground" />
            Warranty
          </CardTitle>
          <CardDescription>
            Each dispatch starts its own period, from the DC date or the day it left.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {query.status === "pending" ? (
            <div aria-busy="true" aria-label="Loading the warranty" className="flex flex-col gap-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : query.status === "error" ? (
            <ErrorState
              error={query.error}
              onRetry={() => {
                void query.refetch();
              }}
            />
          ) : (
            <div className="flex flex-col gap-3">
              {query.data.replacementFor === null ? null : (
                <p className="text-sm text-muted-foreground">
                  A replacement for complaint{" "}
                  <Link
                    href={`/complaints/${query.data.replacementFor.id}`}
                    className="font-mono text-primary-text underline-offset-4 hover:underline"
                  >
                    {query.data.replacementFor.code ?? "the complaint"}
                  </Link>
                  .
                </p>
              )}
              <ul aria-label="Warranty by item" className="flex flex-col divide-y divide-border">
                {query.data.lines.map((line) => {
                  const ordered = order.lines.find((item) => item.id === line.id);
                  return (
                    <WarrantyRow
                      key={line.id}
                      line={line}
                      unit={{ uom: ordered?.uom ?? "", decimals: ordered?.uomDecimals ?? 3 }}
                    />
                  );
                })}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

interface Unit {
  readonly uom: string;
  readonly decimals: number;
}

function WarrantyRow({ line, unit }: { line: WarrantyLine; unit: Unit }): React.JSX.Element {
  const qty = (value: string): string =>
    `${formatOrderQty(value, unit.decimals)} ${unit.uom}`.trim();
  const latestEnd =
    [...line.dispatches].sort((left, right) => (right.end ?? "").localeCompare(left.end ?? ""))[0]
      ?.end ?? null;
  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <span className="text-sm font-medium text-foreground">{line.product.description}</span>
        <Badge variant={LINE_WARRANTY_BADGE[line.status]} size="sm">
          {lineWarrantyText(line.status, latestEnd)}
        </Badge>
      </div>
      {line.dispatches.length === 0 ? null : (
        <ul
          aria-label={`Dispatches of ${line.product.description}`}
          className="flex flex-col gap-1 text-xs text-muted-foreground"
        >
          {line.dispatches.map((dispatch) => (
            <li key={dispatch.id} className="flex flex-wrap gap-x-2 tabular-nums">
              <span className="font-mono text-foreground">{dispatch.dispatchNo}</span>
              <span>{qty(dispatch.qty)} sent</span>
              <span>
                from {formatBusinessDay(dispatch.start)}
                {dispatch.startBasis === "dc_date" ? " (DC date)" : " (left that day)"}
              </span>
              {dispatch.months === null ? (
                <span>no period on record</span>
              ) : (
                <span>
                  {monthsText(dispatch.months)}
                  {dispatch.end === null ? "" : `, until ${formatBusinessDay(dispatch.end)}`}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {line.claims.length === 0 ? null : (
        <ul
          aria-label={`Complaints on ${line.product.description}`}
          className="flex flex-col gap-1 text-xs"
        >
          {line.claims.map((claim) => (
            <li key={claim.id} className="flex flex-wrap items-center gap-2">
              <Link
                href={`/complaints/${claim.id}`}
                className="font-mono text-primary-text underline-offset-4 hover:underline"
              >
                {claim.code ?? "A complaint"}
              </Link>
              <span className="text-muted-foreground tabular-nums">
                {qty(claim.defectiveQty)} defective
                {claim.raisedOn === null ? "" : `, raised ${formatBusinessDay(claim.raisedOn)}`}
              </span>
              <Badge variant={CLAIM_WARRANTY_BADGE[claim.warrantyStatus]} size="sm">
                {CLAIM_WARRANTY_LABELS[claim.warrantyStatus]}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
