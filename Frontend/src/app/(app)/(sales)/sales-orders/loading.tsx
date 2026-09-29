import type * as React from "react";

import { OrdersTableSkeleton } from "@/features/orders/components/orders-table";
import { OrdersToolbarSkeleton } from "@/features/orders/components/orders-toolbar";

export default function SalesOrdersLoading(): React.JSX.Element {
  return (
    <section aria-label="Loading sales orders" className="flex min-h-0 flex-1 flex-col gap-4">
      <OrdersToolbarSkeleton />
      <OrdersTableSkeleton />
    </section>
  );
}
