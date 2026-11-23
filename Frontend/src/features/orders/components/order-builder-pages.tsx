"use client";

import { LockIcon, PackageIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { buttonVariants } from "@/components/ui/button-variants";
import { leadDetailQueryOptions } from "@/features/leads/api/leads.queries";
import type { LeadStage } from "@/features/leads/api/leads.schemas";
import { orderDetailQueryOptions } from "@/features/orders/api/orders.queries";
import { orderNumber } from "@/features/orders/lib/order-labels";
import { BuilderSkeleton } from "@/features/quotations/components/quotation-builder-pages";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { isApiError } from "@/lib/api/errors";

import { OrderBuilder } from "./order-builder";

const FRAME = "rounded-xl border border-dashed border-border";

/** The lead stages an order may be placed on, as the backend allows. */
const ORDERABLE_STAGES: ReadonlySet<LeadStage> = new Set([
  "qualified",
  "quoted",
  "negotiation",
  "won",
]);

/**
 * SO-005 · A new order typed in: about `leadId` once the lead is qualified, or afresh. Only for
 * whoever may create orders.
 */
export function NewDirectOrder({ leadId }: { leadId: string | null }): React.JSX.Element {
  const canCreate = useCan("sales_orders", "create");
  const session = useSession();
  const lead = useQuery({ ...leadDetailQueryOptions(leadId ?? ""), enabled: leadId !== null });

  if (session.isSuccess && !canCreate) {
    return <NoAccess what="place orders" />;
  }
  if (leadId === null) {
    return <OrderBuilder source={{ mode: "create", lead: null }} />;
  }
  if (lead.status === "error" && isApiError(lead.error) && lead.error.status === 404) {
    return (
      <EmptyState
        icon={PackageIcon}
        title="Lead not found"
        description="It may have been removed, merged, or reassigned outside your territory."
        action={
          <Link href="/leads" className={buttonVariants({ variant: "outline" })}>
            Back to all leads
          </Link>
        }
        className={FRAME}
      />
    );
  }
  return (
    <QueryView query={lead} pending={<BuilderSkeleton />} isEmpty={() => false} empty={null}>
      {(loaded) =>
        ORDERABLE_STAGES.has(loaded.stage) ? (
          <OrderBuilder source={{ mode: "create", lead: loaded }} />
        ) : (
          <EmptyState
            icon={PackageIcon}
            title={`${loaded.customerName} can't take an order yet`}
            description="Orders are placed on qualified leads, or ones further on. Qualify the lead first."
            action={
              <Link href={`/leads/${loaded.id}`} className={buttonVariants({ variant: "outline" })}>
                Back to the lead
              </Link>
            }
            className={FRAME}
          />
        )
      }
    </QueryView>
  );
}

/** SO-005 · Edit a draft's items and header. A submitted order is never edited here. */
export function EditOrderDraft({ orderId }: { orderId: string }): React.JSX.Element {
  const canEdit = useCan("sales_orders", "edit");
  const session = useSession();
  const order = useQuery(orderDetailQueryOptions(orderId));

  if (session.isSuccess && !canEdit) {
    return <NoAccess what="change orders" />;
  }
  if (order.status === "error" && isApiError(order.error) && order.error.status === 404) {
    return (
      <EmptyState
        icon={PackageIcon}
        title="Order not found"
        description="It may have been a draft that was deleted, or it is outside your territory."
        action={
          <Link href="/sales-orders" className={buttonVariants({ variant: "outline" })}>
            Back to all orders
          </Link>
        }
        className={FRAME}
      />
    );
  }
  return (
    <QueryView query={order} pending={<BuilderSkeleton />} isEmpty={() => false} empty={null}>
      {(loaded) =>
        loaded.status === "draft" ? (
          <OrderBuilder source={{ mode: "edit", order: loaded }} />
        ) : (
          <EmptyState
            icon={LockIcon}
            title={`${orderNumber(loaded)} was submitted`}
            description="A submitted order keeps its items. Cancel it and place a new one to change them."
            action={
              <Link
                href={`/sales-orders/${loaded.id}`}
                className={buttonVariants({ variant: "outline" })}
              >
                Open the order
              </Link>
            }
            className={FRAME}
          />
        )
      }
    </QueryView>
  );
}

function NoAccess({ what }: { what: string }): React.JSX.Element {
  return (
    <EmptyState
      icon={LockIcon}
      title="You don't have access to this"
      description={`Your role cannot ${what}. Ask your manager or an admin if you need to.`}
      className={FRAME}
    />
  );
}
