import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { PartnerDetail } from "@/features/partners/components/partner-detail";

export const metadata: Metadata = { title: "Partner" };

/** CHNL-001 · One channel partner, with what may be done about it. */
export default async function PartnerPage({
  params,
}: PageProps<"/partners/[partnerId]">): Promise<React.JSX.Element> {
  const { partnerId } = await params;
  return (
    <PageTransition>
      <PageContainer>
        <PartnerDetail partnerId={partnerId} />
      </PageContainer>
    </PageTransition>
  );
}
