import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { DealerTasks } from "@/features/tasks/components/dealer-tasks";

export const metadata: Metadata = { title: "Tasks" };

/** TASK-009 · A dealer's tasks. The title and description sit in the top bar, from the navigation map. */
export default function DealerTasksPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <DealerTasks />
      </PageContainer>
    </PageTransition>
  );
}
