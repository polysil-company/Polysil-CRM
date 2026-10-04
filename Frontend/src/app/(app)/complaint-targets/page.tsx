import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { ComplaintTargets } from "@/features/complaints/components/complaint-targets";

export const metadata: Metadata = { title: "Complaint targets" };

/** CMPL-008 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function ComplaintTargetsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <ComplaintTargets />
      </PageContainer>
    </PageTransition>
  );
}
