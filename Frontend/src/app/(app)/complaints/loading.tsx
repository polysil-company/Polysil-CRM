import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { ComplaintsListSkeleton } from "@/features/complaints/components/complaints-list";

export default function ComplaintsLoading(): React.JSX.Element {
  return (
    <PageContainer>
      <ComplaintsListSkeleton />
    </PageContainer>
  );
}
