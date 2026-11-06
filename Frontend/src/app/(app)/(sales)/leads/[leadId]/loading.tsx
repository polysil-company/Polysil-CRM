import type * as React from "react";

import { LeadDetailSkeleton } from "@/features/leads/components/lead-detail";

export default function LeadDetailLoading(): React.JSX.Element {
  return <LeadDetailSkeleton />;
}
