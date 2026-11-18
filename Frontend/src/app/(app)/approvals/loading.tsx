import type * as React from "react";

import { PageContainer } from "@/components/patterns/page-container";
import { ApprovalsInboxSkeleton } from "@/features/approvals/components/approvals-inbox";

export default function ApprovalsLoading(): React.JSX.Element {
  return (
    <PageContainer>
      <ApprovalsInboxSkeleton />
    </PageContainer>
  );
}
