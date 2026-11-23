import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { Skeleton } from "@/components/ui/skeleton";
import { Masters } from "@/features/masters/components/masters";

export const metadata: Metadata = { title: "Masters" };

/** MSTR-001 · The open tab is read from the URL. */
export default function MastersPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
          <Masters />
        </Suspense>
      </PageContainer>
    </PageTransition>
  );
}
