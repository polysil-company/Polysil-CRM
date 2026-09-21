import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { DashboardOverview } from "@/features/dashboard/components/dashboard-overview";

export const metadata: Metadata = { title: "Dashboard" };

/** The title and description sit in the top bar (APP-005), from the navigation map. */
export default function DashboardPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <DashboardOverview />
      </PageContainer>
    </PageTransition>
  );
}
