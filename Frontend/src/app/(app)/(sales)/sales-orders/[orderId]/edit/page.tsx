import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { EditOrderDraft } from "@/features/orders/components/order-builder-pages";

export const metadata: Metadata = { title: "Edit order" };

/** SO-005 · A draft's items and header. */
export default async function EditOrderPage({
  params,
}: PageProps<"/sales-orders/[orderId]/edit">): Promise<React.JSX.Element> {
  const { orderId } = await params;

  return (
    <PageTransition>
      <section aria-label="Edit order" className="flex flex-col">
        <EditOrderDraft orderId={orderId} />
      </section>
    </PageTransition>
  );
}
