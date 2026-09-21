import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { PageHeader } from "@/components/patterns/page-header";
import { DashboardOverviewSkeleton } from "@/features/dashboard/components/dashboard-overview";

export default function DashboardLoading(): React.JSX.Element {
  return (
    <PageContainer>
      <PageHeader title="Dashboard" description="Your territory at a glance." />
      <DashboardOverviewSkeleton />
    </PageContainer>
  );
}
