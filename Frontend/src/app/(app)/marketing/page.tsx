import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { MarketingPage } from "@/features/marketing/components/marketing-page";

export const metadata: Metadata = { title: "Marketing material" };

/** MKT-002 … MKT-004 · The title and description sit in the top bar (APP-005). */
export default function MarketingRoute(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <MarketingPage />
      </PageContainer>
    </PageTransition>
  );
}
