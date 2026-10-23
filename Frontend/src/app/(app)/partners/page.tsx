import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { PartnersList, PartnersListSkeleton } from "@/features/partners/components/partners-list";
import { PartnersTabs } from "@/features/partners/components/partners-tabs";

export const metadata: Metadata = { title: "Channel partners" };

/** CHNL-001 · The title and description sit in the top bar (APP-005), from the navigation map. */
export default function PartnersPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <div className="flex flex-col gap-4">
          <PartnersTabs />
          {/* The filters are read from the URL, which needs a Suspense boundary. */}
          <Suspense fallback={<PartnersListSkeleton />}>
            <PartnersList />
          </Suspense>
        </div>
      </PageContainer>
    </PageTransition>
  );
}
