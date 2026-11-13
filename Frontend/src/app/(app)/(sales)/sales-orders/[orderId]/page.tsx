import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { OrderDetail } from "@/features/orders/components/order-detail";

export const metadata: Metadata = { title: "Sales order" };

export default async function SalesOrderDetailPage({
  params,
}: PageProps<"/sales-orders/[orderId]">): Promise<React.JSX.Element> {
  const { orderId } = await params;

  return (
    <PageTransition>
      <section aria-label="Sales order" className="flex flex-col">
        <OrderDetail orderId={orderId} />
      </section>
    </PageTransition>
  );
}
