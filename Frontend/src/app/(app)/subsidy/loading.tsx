import type * as React from "react";

import { ApplicationsListSkeleton } from "@/features/subsidy/components/applications-list";

export default function SubsidyLoading(): React.JSX.Element {
  return <ApplicationsListSkeleton />;
}
