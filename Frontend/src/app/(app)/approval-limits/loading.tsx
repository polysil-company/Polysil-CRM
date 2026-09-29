import type * as React from "react";

import { ApprovalLimitsSkeleton } from "@/features/approvals/components/approval-limits";

export default function ApprovalLimitsLoading(): React.JSX.Element {
  return <ApprovalLimitsSkeleton />;
}
