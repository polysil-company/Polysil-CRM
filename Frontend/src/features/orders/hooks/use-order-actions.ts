"use client";

import type { Order } from "@/features/orders/api/orders.schemas";
import {
  orderActions,
  type OrderActions,
  type OrderState,
} from "@/features/orders/lib/order-lifecycle";
import { useCan, useSession } from "@/features/session/hooks/use-session";

/** SO-003, SO-004, DISP-002 · What the signed-in user may do with this order now. */
export function useOrderActions(order: OrderState & Pick<Order, "owner">): OrderActions {
  const session = useSession();
  const editOrders = useCan("sales_orders", "edit");
  const deleteOrders = useCan("sales_orders", "delete");
  const recordDispatch = useCan("dispatch", "create");
  const editDispatch = useCan("dispatch", "edit");
  const userId = session.data?.user.id;
  return orderActions(order, {
    editOrders,
    deleteOrders,
    recordDispatch,
    editDispatch,
    isOwner: userId !== undefined && order.owner?.id === userId,
  });
}
