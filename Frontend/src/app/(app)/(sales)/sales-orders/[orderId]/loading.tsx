import type * as React from "react";

import { OrderDetailSkeleton } from "@/features/orders/components/order-detail";

export default function SalesOrderDetailLoading(): React.JSX.Element {
  return <OrderDetailSkeleton />;
}
