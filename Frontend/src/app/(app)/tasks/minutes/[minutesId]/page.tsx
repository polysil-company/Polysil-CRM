import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { MinutesDetail } from "@/features/tasks/components/minutes-detail";

export const metadata: Metadata = { title: "Meeting minutes" };

export default async function MinutesPage({
  params,
}: PageProps<"/tasks/minutes/[minutesId]">): Promise<React.JSX.Element> {
  const { minutesId } = await params;
  return (
    <PageTransition>
      <PageContainer>
        <MinutesDetail minutesId={minutesId} />
      </PageContainer>
    </PageTransition>
  );
}
