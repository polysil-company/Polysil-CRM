import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { ApprovalLimits } from "@/features/approvals/components/approval-limits";

export const metadata: Metadata = { title: "Approval limits" };

/** APPR-002 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function ApprovalLimitsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <ApprovalLimits />
      </PageContainer>
    </PageTransition>
  );
}
