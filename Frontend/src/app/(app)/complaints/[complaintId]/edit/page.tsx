import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { EditComplaint } from "@/features/complaints/components/complaint-pages";

export const metadata: Metadata = { title: "Edit complaint" };

export default async function EditComplaintPage({
  params,
}: PageProps<"/complaints/[complaintId]/edit">): Promise<React.JSX.Element> {
  const { complaintId } = await params;
  return (
    <PageTransition>
      <PageContainer>
        <EditComplaint complaintId={complaintId} />
      </PageContainer>
    </PageTransition>
  );
}
