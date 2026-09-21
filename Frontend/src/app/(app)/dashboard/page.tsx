import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { PageHeader } from "@/components/patterns/page-header";
import { DashboardOverview } from "@/features/dashboard/components/dashboard-overview";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <PageHeader title="Dashboard" description="Your territory at a glance." />
        <DashboardOverview />
      </PageContainer>
    </PageTransition>
  );
}
