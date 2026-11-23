import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { NewPartner } from "@/features/partners/components/partner-pages";

export const metadata: Metadata = { title: "New partner" };

/** CHNL-002 · Add a distributor, or a dealer or sub-dealer under one (`?parent=` from its page). */
export default async function NewPartnerPage({
  searchParams,
}: PageProps<"/partners/new">): Promise<React.JSX.Element> {
  const { parent } = await searchParams;
  return (
    <PageTransition>
      <PageContainer>
        <NewPartner parentId={typeof parent === "string" && parent !== "" ? parent : null} />
      </PageContainer>
    </PageTransition>
  );
}
