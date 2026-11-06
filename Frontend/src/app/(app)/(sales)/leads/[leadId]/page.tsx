import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { LeadDetail } from "@/features/leads/components/lead-detail";

export const metadata: Metadata = { title: "Lead" };

export default async function LeadDetailPage({
  params,
}: PageProps<"/leads/[leadId]">): Promise<React.JSX.Element> {
  const { leadId } = await params;

  return (
    <PageTransition>
      <section aria-label="Lead" className="flex flex-col">
        <LeadDetail leadId={leadId} />
      </section>
    </PageTransition>
  );
}
