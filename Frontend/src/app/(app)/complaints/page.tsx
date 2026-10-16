import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import {
  ComplaintsList,
  ComplaintsListSkeleton,
} from "@/features/complaints/components/complaints-list";

export const metadata: Metadata = { title: "Complaints" };

/** CMPL-001 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function ComplaintsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        {/* The view and the filters are read from the URL, which needs a Suspense boundary. */}
        <Suspense fallback={<ComplaintsListSkeleton />}>
          <ComplaintsList />
        </Suspense>
      </PageContainer>
    </PageTransition>
  );
}
