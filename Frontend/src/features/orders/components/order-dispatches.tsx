"use client";

import { DeliveryTruck01Icon } from "@hugeicons/core-free-icons";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Dispatch, Order } from "@/features/orders/api/orders.schemas";
import { useOrderActions } from "@/features/orders/hooks/use-order-actions";
import { formatOrderQty } from "@/features/orders/lib/order-labels";
import { EMPTY_VALUE, formatFullDate, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import { OrderActionDialog, type OrderDialog } from "./order-action-dialog";

/**
 * DISP-002 · What has left against the order, newest first. A voided dispatch stays on
 * record, marked, with the reason; its quantities are open again. Dispatch voids one here.
 */
export function OrderDispatches({ order }: { order: Order }): React.JSX.Element {
  const actions = useOrderActions(order);
  const [dialog, setDialog] = useState<OrderDialog | null>(null);
  const dispatches = [...order.dispatches].sort(
    (a, b) => Date.parse(b.dispatchedAt) - Date.parse(a.dispatchedAt),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle level={3}>
          Dispatches{" "}
          <span className="font-normal text-muted-foreground">
            ({formatNumber(order.dispatches.length)})
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {dispatches.length === 0 ? (
          <EmptyState
            icon={DeliveryTruck01Icon}
            title="Nothing has left yet"
            description="Dispatch records each consignment here, with its challan and invoice numbers."
          />
        ) : (
          <ol aria-label="Dispatches, newest first" className="flex flex-col gap-3">
            {dispatches.map((dispatch) => (
              <DispatchItem
                key={dispatch.id}
                dispatch={dispatch}
                order={order}
                canVoid={actions.voidDispatch ? dispatch.voidedAt === null : false}
                onVoid={() => {
                  setDialog({ kind: "void", dispatch });
                }}
              />
            ))}
          </ol>
        )}
      </CardContent>
      <OrderActionDialog
        order={order}
        dialog={dialog}
        onClose={() => {
          setDialog(null);
        }}
      />
    </Card>
  );
}

function DispatchItem({
  dispatch,
  order,
  canVoid,
  onVoid,
}: {
  dispatch: Dispatch;
  order: Order;
  canVoid: boolean;
  onVoid: () => void;
}): React.JSX.Element {
  const voided = dispatch.voidedAt !== null;
  return (
    <li
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-border p-3",
        voided && "bg-muted",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
            <span className={cn("font-mono", voided && "line-through")}>{dispatch.dispatchNo}</span>
            {voided ? <Badge variant="danger">Void</Badge> : null}
          </p>
          <p className="text-xs text-muted-foreground">
            Left <RelativeDate value={dispatch.dispatchedAt} />
            {dispatch.dispatchedBy === null ? null : (
              <> · recorded by {dispatch.dispatchedBy.name}</>
            )}
          </p>
        </div>
        {canVoid ? (
          <Button variant="outline" size="sm" onClick={onVoid}>
            Void…
          </Button>
        ) : null}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <DispatchField label="Challan">
          {dispatch.dcNo ?? EMPTY_VALUE}
          {dispatch.dcDate === null ? null : (
            <span className="block text-xs text-muted-foreground">
              {formatFullDate(dispatch.dcDate)}
            </span>
          )}
        </DispatchField>
        <DispatchField label="Invoice">
          {dispatch.invoiceNo ?? EMPTY_VALUE}
          {dispatch.invoiceDate === null ? null : (
            <span className="block text-xs text-muted-foreground">
              {formatFullDate(dispatch.invoiceDate)}
            </span>
          )}
        </DispatchField>
        <DispatchField label="Transporter">{dispatch.transporter ?? EMPTY_VALUE}</DispatchField>
        <DispatchField label="Vehicle">
          <span className="font-mono">{dispatch.vehicleNo ?? EMPTY_VALUE}</span>
        </DispatchField>
      </dl>
      <ul aria-label={`Items in ${dispatch.dispatchNo}`} className="flex flex-col gap-1 text-sm">
        {dispatch.lines.map((sent) => {
          const line = order.lines.find((item) => item.id === sent.orderLineId);
          return (
            <li key={sent.orderLineId} className="flex justify-between gap-3">
              <span className="min-w-0 truncate text-muted-foreground">
                {sent.lineNo}. {line?.description ?? "An item no longer on the order"}
              </span>
              <span className="shrink-0 tabular-nums">
                {formatOrderQty(sent.qty, line?.uomDecimals ?? 3)} {line?.uom ?? ""}
              </span>
            </li>
          );
        })}
      </ul>
      {voided ? (
        <p className="text-sm text-muted-foreground">
          Voided {dispatch.voidedAt === null ? null : formatFullDate(dispatch.voidedAt)}
          {dispatch.voidRemark === null ? null : `: “${dispatch.voidRemark}”`}
        </p>
      ) : null}
    </li>
  );
}

function DispatchField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 wrap-break-word text-foreground">{children}</dd>
    </div>
  );
}
