import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import {
  ApprovalsInbox,
  ApprovalsInboxSkeleton,
} from "@/features/approvals/components/approvals-inbox";

export const metadata: Metadata = { title: "Approvals" };

/** APPR-001 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function ApprovalsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        {/* "Include steps below me" is read from the URL, which needs a Suspense boundary. */}
        <Suspense fallback={<ApprovalsInboxSkeleton />}>
          <ApprovalsInbox />
        </Suspense>
      </PageContainer>
    </PageTransition>
  );
}
