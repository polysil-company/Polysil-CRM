import type * as React from "react";

import { ComplaintTargetsSkeleton } from "@/features/complaints/components/complaint-targets";

export default function ComplaintTargetsLoading(): React.JSX.Element {
  return <ComplaintTargetsSkeleton />;
}
