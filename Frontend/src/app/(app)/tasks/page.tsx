import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { PlannerDaySkeleton } from "@/features/tasks/components/planner-day";
import { TasksView } from "@/features/tasks/components/tasks-view";

export const metadata: Metadata = { title: "Tasks" };

/** TASK-001 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function TasksPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        {/* The day, the view and whose day are read from the URL, which needs a Suspense boundary. */}
        <Suspense fallback={<PlannerDaySkeleton />}>
          <TasksView />
        </Suspense>
      </PageContainer>
    </PageTransition>
  );
}
