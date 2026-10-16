import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { ComplaintDetail } from "@/features/complaints/components/complaint-detail";

export const metadata: Metadata = { title: "Complaint" };

export default async function ComplaintPage({
  params,
}: PageProps<"/complaints/[complaintId]">): Promise<React.JSX.Element> {
  const { complaintId } = await params;
  return (
    <PageTransition>
      <PageContainer>
        <ComplaintDetail complaintId={complaintId} />
      </PageContainer>
    </PageTransition>
  );
}
