import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { Skeleton } from "@/components/ui/skeleton";
import { CreditsList } from "@/features/schemes/components/credits-list";

export const metadata: Metadata = { title: "Scheme credits" };

/** SCHM-004 · The status filter is read from the URL. */
export default function SchemeCreditsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
        <CreditsList />
      </Suspense>
    </PageTransition>
  );
}
