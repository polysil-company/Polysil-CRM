import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { Skeleton } from "@/components/ui/skeleton";
import { SubsidyMasters } from "@/features/subsidy/components/subsidy-masters";

export const metadata: Metadata = { title: "Subsidy masters" };

/** SUBS-012, SUBS-013 · The table and the date are read from the URL. */
export default function SubsidyMastersPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
          <SubsidyMasters />
        </Suspense>
      </PageContainer>
    </PageTransition>
  );
}
