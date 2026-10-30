import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { PersonDetail } from "@/features/users/components/person-detail";

export const metadata: Metadata = { title: "Person" };

/** ADMN-002 · One person, with what an administrator may do about them. */
export default async function PersonPage({
  params,
}: PageProps<"/users/[userId]">): Promise<React.JSX.Element> {
  const { userId } = await params;
  return (
    <PageTransition>
      <PageContainer>
        <PersonDetail userId={userId} />
      </PageContainer>
    </PageTransition>
  );
}
