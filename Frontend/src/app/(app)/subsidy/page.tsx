import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import {
  ApplicationsList,
  ApplicationsListSkeleton,
} from "@/features/subsidy/components/applications-list";

export const metadata: Metadata = { title: "Subsidy applications" };

/** SUBS-005 · The filters are read from the URL, which needs a Suspense boundary. */
export default function SubsidyApplicationsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <Suspense fallback={<ApplicationsListSkeleton />}>
        <ApplicationsList />
      </Suspense>
    </PageTransition>
  );
}
