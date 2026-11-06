import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { DashboardOverviewSkeleton } from "@/features/dashboard/components/dashboard-overview";

export default function DashboardLoading(): React.JSX.Element {
  return (
    <PageContainer>
      <DashboardOverviewSkeleton />
    </PageContainer>
  );
}
