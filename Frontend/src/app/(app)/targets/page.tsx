import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { Skeleton } from "@/components/ui/skeleton";
import { TargetsView } from "@/features/targets/components/targets-view";

export const metadata: Metadata = { title: "Targets" };

/** TGT-001 · The month is read from the URL. */
export default function TargetsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
          <TargetsView />
        </Suspense>
      </PageContainer>
    </PageTransition>
  );
}
