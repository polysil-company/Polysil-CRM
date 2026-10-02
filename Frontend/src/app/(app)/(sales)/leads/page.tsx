import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { LeadsPageSkeleton } from "@/features/leads/components/leads-page-skeleton";
import { LeadsTable } from "@/features/leads/components/leads-table";
import { LeadsToolbar } from "@/features/leads/components/leads-toolbar";

export const metadata: Metadata = { title: "Leads" };

export default function LeadsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <section aria-label="Leads" data-page-fill className="flex min-h-0 flex-1 flex-col gap-4">
        {/* Filters are read from the URL, which needs a Suspense boundary during prerendering. */}
        <Suspense fallback={<LeadsPageSkeleton />}>
          <LeadsToolbar />
          <LeadsTable />
        </Suspense>
      </section>
    </PageTransition>
  );
}
