import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { OrdersTable, OrdersTableSkeleton } from "@/features/orders/components/orders-table";
import { OrdersToolbar, OrdersToolbarSkeleton } from "@/features/orders/components/orders-toolbar";

export const metadata: Metadata = { title: "Sales orders" };

export default function SalesOrdersPage(): React.JSX.Element {
  return (
    <PageTransition>
      <section
        aria-label="Sales orders"
        data-page-fill
        className="flex min-h-0 flex-1 flex-col gap-4"
      >
        {/* Filters are read from the URL, which needs a Suspense boundary during prerendering. */}
        <Suspense
          fallback={
            <>
              <OrdersToolbarSkeleton />
              <OrdersTableSkeleton />
            </>
          }
        >
          <OrdersToolbar />
          <OrdersTable />
        </Suspense>
      </section>
    </PageTransition>
  );
}
