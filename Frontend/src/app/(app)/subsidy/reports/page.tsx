import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { Skeleton } from "@/components/ui/skeleton";
import { SubsidyReports } from "@/features/subsidy/components/subsidy-reports";

export const metadata: Metadata = { title: "Subsidy reports" };

/** SUBS-009 … SUBS-011 · The report and its filters are read from the URL. */
export default function SubsidyReportsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
        <SubsidyReports />
      </Suspense>
    </PageTransition>
  );
}
