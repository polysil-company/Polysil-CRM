import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { DealerApplicationDetail } from "@/features/dealer-applications/components/dealer-application-detail";

export const metadata: Metadata = { title: "Dealer application" };

export default async function DealerApplicationPage({
  params,
}: PageProps<"/partners/applications/[applicationId]">): Promise<React.JSX.Element> {
  const { applicationId } = await params;
  return (
    <PageTransition>
      <PageContainer>
        <DealerApplicationDetail applicationId={applicationId} />
      </PageContainer>
    </PageTransition>
  );
}
