import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { PlannerDaySkeleton } from "@/features/tasks/components/planner-day";

export default function TasksLoading(): React.JSX.Element {
  return (
    <PageContainer>
      <PlannerDaySkeleton />
    </PageContainer>
  );
}
