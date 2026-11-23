import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { CampaignsPage } from "@/features/campaigns/components/campaigns-page";

export const metadata: Metadata = { title: "Campaigns" };

/** MKT-005 · The title and description sit in the top bar (APP-005). */
export default function CampaignsRoute(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <CampaignsPage />
      </PageContainer>
    </PageTransition>
  );
}
