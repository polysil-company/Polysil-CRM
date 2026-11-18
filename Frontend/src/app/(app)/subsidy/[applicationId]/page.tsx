import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { ApplicationDetail } from "@/features/subsidy/components/application-detail";

export const metadata: Metadata = { title: "Subsidy application" };

export default async function SubsidyApplicationPage({
  params,
}: PageProps<"/subsidy/[applicationId]">): Promise<React.JSX.Element> {
  const { applicationId } = await params;
  return (
    <PageTransition>
      <ApplicationDetail applicationId={applicationId} />
    </PageTransition>
  );
}
