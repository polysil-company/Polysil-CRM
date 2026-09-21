import type * as React from "react";

import { LeadsPageSkeleton } from "@/features/leads/components/leads-page-skeleton";

export default function LeadsLoading(): React.JSX.Element {
  return (
    <section aria-label="Loading leads" className="flex min-h-0 flex-1 flex-col gap-4">
      <LeadsPageSkeleton />
    </section>
  );
}
