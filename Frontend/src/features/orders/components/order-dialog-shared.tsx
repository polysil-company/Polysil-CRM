"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { orderKeys } from "@/features/orders/api/orders.queries";
import { orderRefusal, type OrderRefusal } from "@/features/orders/lib/order-lifecycle";

/** A refusal: stale ones close the dialog with a toast and re-read the order. */
export function useOrderRefusal(
  orderId: string,
  onClose: () => void,
): { refusal: OrderRefusal | null; handle: (error: unknown) => void; clear: () => void } {
  const [refusal, setRefusal] = useState<OrderRefusal | null>(null);
  const queryClient = useQueryClient();
  return {
    refusal,
    handle: (error) => {
      const view = orderRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        void queryClient.invalidateQueries({ queryKey: orderKeys.detail(orderId) });
        void queryClient.invalidateQueries({ queryKey: orderKeys.timeline(orderId) });
        onClose();
        return;
      }
      setRefusal(view);
    },
    clear: () => {
      setRefusal(null);
    },
  };
}

export function RefusalAlert({
  refusal,
}: {
  refusal: OrderRefusal | null;
}): React.JSX.Element | null {
  if (refusal === null) {
    return null;
  }
  return (
    <div
      role="alert"
      className="mt-4 flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
    >
      <p className="font-medium text-danger">{refusal.title}</p>
      <p className="text-foreground">{refusal.message}</p>
    </div>
  );
}
