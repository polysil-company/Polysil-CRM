import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { RewardsPage } from "@/features/rewards/components/rewards-page";

export const metadata: Metadata = { title: "Rewards" };

/** RWD-001 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function RewardsRoute(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <RewardsPage />
      </PageContainer>
    </PageTransition>
  );
}
