import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { EditPartner } from "@/features/partners/components/partner-pages";

export const metadata: Metadata = { title: "Edit partner" };

/** CHNL-003 · Correct a partner's details, territory or credit terms. */
export default async function EditPartnerPage({
  params,
}: PageProps<"/partners/[partnerId]/edit">): Promise<React.JSX.Element> {
  const { partnerId } = await params;
  return (
    <PageTransition>
      <PageContainer>
        <EditPartner partnerId={partnerId} />
      </PageContainer>
    </PageTransition>
  );
}
