import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import {
  QuotationsTable,
  QuotationsTableSkeleton,
} from "@/features/quotations/components/quotations-table";
import {
  QuotationsToolbar,
  QuotationsToolbarSkeleton,
} from "@/features/quotations/components/quotations-toolbar";

export const metadata: Metadata = { title: "Quotations" };

export default function QuotationsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <section aria-label="Quotations" className="flex min-h-0 flex-1 flex-col gap-4">
        {/* Filters are read from the URL, which needs a Suspense boundary during prerendering. */}
        <Suspense
          fallback={
            <>
              <QuotationsToolbarSkeleton />
              <QuotationsTableSkeleton />
            </>
          }
        >
          <QuotationsToolbar />
          <QuotationsTable />
        </Suspense>
      </section>
    </PageTransition>
  );
}
