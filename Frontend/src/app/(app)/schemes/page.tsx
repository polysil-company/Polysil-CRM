import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { Skeleton } from "@/components/ui/skeleton";
import { SchemesList } from "@/features/schemes/components/schemes-list";

export const metadata: Metadata = { title: "Schemes" };

/** SCHM-001 · The filters are read from the URL. */
export default function SchemesPage(): React.JSX.Element {
  return (
    <PageTransition>
      <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
        <SchemesList />
      </Suspense>
    </PageTransition>
  );
}
