import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { OrgChartView } from "@/features/org-chart/components/org-chart-view";

export const metadata: Metadata = { title: "Org chart" };

/** ADMN-008 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function OrgChartPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <OrgChartView />
      </PageContainer>
    </PageTransition>
  );
}
