import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { DispatchQueueSkeleton } from "@/features/orders/components/dispatch-queue";

export default function DispatchQueueLoading(): React.JSX.Element {
  return (
    <PageContainer>
      <DispatchQueueSkeleton />
    </PageContainer>
  );
}
