import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { DispatchQueue, DispatchQueueSkeleton } from "@/features/orders/components/dispatch-queue";

export const metadata: Metadata = { title: "Dispatch queue" };

/** DISP-001 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function DispatchQueuePage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        {/* The tab and the days are read from the URL, which needs a Suspense boundary. */}
        <Suspense fallback={<DispatchQueueSkeleton />}>
          <DispatchQueue />
        </Suspense>
      </PageContainer>
    </PageTransition>
  );
}
