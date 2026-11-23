import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import type { OrderStatus } from "@/features/orders/api/orders.schemas";
import { ORDER_STATUS_BADGE, ORDER_STATUS_LABELS } from "@/features/orders/lib/order-labels";

export interface OrderStatusBadgeProps {
  status: OrderStatus;
  className?: string;
}

/** SO-001 · An order's status, as a labelled chip. */
export function OrderStatusBadge({ status, className }: OrderStatusBadgeProps): React.JSX.Element {
  return (
    <Badge variant={ORDER_STATUS_BADGE[status]} dot className={className}>
      {ORDER_STATUS_LABELS[status]}
    </Badge>
  );
}
