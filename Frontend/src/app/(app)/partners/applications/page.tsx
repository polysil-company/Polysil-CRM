import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import {
  DealerApplicationsList,
  DealerApplicationsSkeleton,
} from "@/features/dealer-applications/components/dealer-applications-list";
import { PartnersTabs } from "@/features/partners/components/partners-tabs";

export const metadata: Metadata = { title: "Dealer applications" };

/** CHNL-007 · The filters are read from the URL, which needs a Suspense boundary. */
export default function DealerApplicationsPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <div className="flex flex-col gap-4">
          <PartnersTabs />
          <Suspense fallback={<DealerApplicationsSkeleton />}>
            <DealerApplicationsList />
          </Suspense>
        </div>
      </PageContainer>
    </PageTransition>
  );
}
